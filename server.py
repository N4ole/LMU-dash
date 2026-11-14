#!/usr/bin/env python3
"""
LMU Dash - dashboard second écran pour Le Mans Ultimate.

Lit la mémoire partagée native de LMU (Windows), calcule les données dérivées (conso, stratégie,
relais, carte...) et les envoie en continu (SSE) vers la page web du dossier ./web.

Usage :
    python server.py                 # lit le vrai jeu
    python server.py --demo          # données simulées (pour tester sans le jeu)
    python server.py --host 0.0.0.0  # accessible depuis une tablette / un autre PC
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import traceback
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from endurance import Endurance  # noqa: E402
from flags import FlagWatch  # noqa: E402
from shared import DEFAULT_REPO, Shared  # noqa: E402
from store import Profiles, Records, Settings, StateFile, TrackStore, data_dir, resource_dir  # noqa: E402

WEB_DIR = os.path.join(resource_dir(), "web")
SEND_HZ = 20          # fréquence d'envoi vers le navigateur
SAVE_EVERY = 10.0     # sauvegarde de l'état de course (s)
MAX_BODY = 64 * 1024


# --------------------------------------------------------------------------
# Moteur : lecteur + endurance + cartes + persistance
# --------------------------------------------------------------------------


class Engine:
    def __init__(self, reader, settings: Settings, folder: str, profiles: Profiles) -> None:
        self.profiles = profiles
        self.reader = reader
        self.settings = settings
        self.endu = Endurance()
        self.tracks = TrackStore(folder)
        self.state = StateFile(profiles.path())
        self.records = Records(profiles.path())
        self.flagwatch = FlagWatch(settings)
        self.key: str | None = None
        self.label = ""
        self.last_et = 0.0
        self.last_save = 0.0
        self.lock = threading.Lock()

    # ---- session ----
    def _archive(self) -> None:
        if self.endu.laps:
            self.state.archive(self.label, self.endu.laps_csv(), self.endu.stints_csv(self.last_et))

    def _new_session(self, key: str, label: str, et: float) -> None:
        self._archive()
        self.endu.reset()
        self.reader.reset_stats()
        saved = self.state.load(key, et)
        if saved:
            self.endu.from_dict(saved.get("endurance") or {})
            if saved.get("stats"):
                self.reader.restore(saved["stats"])
            print(f"[reprise] état de course restauré ({len(self.endu.laps)} tours en mémoire)")
        self.key, self.label = key, label

    def reset_session(self) -> None:
        """Nouvelle session manuelle : archive puis remet à zéro relais + stratégie."""
        with self.lock:
            self._archive()
            self.endu.reset()
            self.reader.reset_stats()
            self.last_save = 0.0

    def use_profile(self, name: str) -> bool:
        """Change de joueur : archive la session en cours, puis recharge réglages, records et état."""
        with self.lock:
            if name not in self.profiles.names or name == self.profiles.active:
                return False
            self._archive()
            if self.key:
                self.state.save(self.key, self.last_et, self.reader.snapshot(), self.endu.to_dict())
            self.profiles.switch(name)
            folder = self.profiles.path()
            self.settings.rebind(os.path.join(folder, "settings.json"))
            self.state.rebind(folder)
            self.records.rebind(folder)
            self.endu.reset()
            self.reader.reset_stats()
            self.key, self.last_et, self.last_save = None, 0.0, 0.0
            return True

    # ---- boucle ----
    def step(self) -> dict:
        data = self.reader.read()
        with self.lock:
            if data.get("connected") and data.get("car"):
                s, c = data["session"], data["car"]
                key = f"{s['track']}|{s['type']}|{c['name']}"
                et = float(s.get("elapsed") or 0.0)
                if key != self.key or et < self.last_et - 5:
                    self._new_session(key, f"{s['track']}_{s['type']}", et)
                self.last_et = et
                self.endu.update(data)
                data["endurance"] = self.endu.summary(et, bool(c.get("inPits")))
                if time.monotonic() - self.last_save > SAVE_EVERY:
                    self.last_save = time.monotonic()
                    self.state.save(self.key, et, self.reader.snapshot(), self.endu.to_dict())
            self.tracks.update(data)
            if data.get("connected"):
                tm = self.tracks.info()
                data["trackmap"] = tm
                if data.get("car"):
                    data["flags"] = self.flagwatch.update(data, tm.get("sectors"))
                    self.records.update(data)
                    data["records"] = self.records.current()
        return data

    def history(self) -> dict:
        with self.lock:
            return self.endu.history(self.last_et)

    def shutdown(self) -> None:
        with self.lock:
            try:
                if self.key:
                    self.state.save(self.key, self.last_et, self.reader.snapshot(), self.endu.to_dict())
                self.tracks.flush()
            except Exception as e:  # noqa: BLE001
                print(f"[arrêt] {e}")


# --------------------------------------------------------------------------
# Serveur HTTP + SSE
# --------------------------------------------------------------------------


class Hub:
    def __init__(self) -> None:
        self.clients: set[queue.Queue] = set()
        self.lock = threading.Lock()
        self.latest = '{"connected": false, "state": "waiting"}'

    def publish(self, payload: str) -> None:
        self.latest = payload
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    try:
                        q.get_nowait()
                        q.put_nowait(payload)
                    except queue.Empty:
                        pass

    def add(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=4)
        with self.lock:
            self.clients.add(q)
        return q

    def remove(self, q: queue.Queue) -> None:
        with self.lock:
            self.clients.discard(q)


HUB = Hub()
ENGINE: Engine | None = None
SHARED: Shared | None = None
SETTINGS: Settings | None = None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB_DIR, **kw)

    def log_message(self, *a):  # silence
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ---- helpers ----
    def _send(self, body: bytes, ctype: str, status: int = 200, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(json.dumps(obj, separators=(",", ":"), allow_nan=False, default=str).encode(),
                   "application/json", status)

    def _body_json(self) -> dict | None:
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":  # force un preflight CORS : bloque les POST venus d'autres sites
            return None
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return None
            data = json.loads(self.rfile.read(n) or b"{}")
            return data if isinstance(data, dict) else None
        except (ValueError, OSError):
            return None

    def _csv(self, text: str, name: str) -> None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._send(("﻿" + text).encode("utf-8"), "text/csv; charset=utf-8",
                   extra={"Content-Disposition": f'attachment; filename="{stamp}_{name}"'})

    # ---- GET ----
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/stream":
            return self._stream()
        if path == "/snapshot":
            return self._send(HUB.latest.encode(), "application/json")
        if path == "/api/settings":
            return self._json(SETTINGS.get())
        if path == "/api/trackmap":
            return self._json(ENGINE.tracks.current())
        if path == "/api/profiles":
            return self._json(ENGINE.profiles.info())
        if path == "/api/shared":
            return self._json(SHARED.info())
        if path == "/api/export/track.json":
            o = ENGINE.tracks.export()
            if not o:
                return self._json({"error": "pas de carte"}, 404)
            from store import slug
            return self._send(json.dumps(o, separators=(",", ":")).encode(), "application/json",
                              extra={"Content-Disposition": f'attachment; filename="{slug(o["key"])}.json"'})
        if path == "/api/records":
            return self._json(ENGINE.records.all())
        if path == "/api/history":
            return self._json(ENGINE.history())
        if path == "/api/export/laps.csv":
            return self._csv(ENGINE.endu.laps_csv(), "tours.csv")
        if path == "/api/export/stints.csv":
            return self._csv(ENGINE.endu.stints_csv(ENGINE.last_et), "relais.csv")
        super().do_GET()

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = HUB.add()
        try:
            self.wfile.write(f"data: {HUB.latest}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=10)
                    self.wfile.write(f"data: {msg}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            HUB.remove(q)

    # ---- POST ----
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        body = self._body_json()
        if body is None:
            return self._json({"error": "requête invalide (JSON attendu)"}, 400)
        if path == "/api/settings":
            return self._json(SETTINGS.update(body))
        if path == "/api/trackmap/reset":
            ENGINE.tracks.reset()
            return self._json({"ok": True})
        if path == "/api/profiles":
            act, name = body.get("action"), str(body.get("name") or "")
            pr = ENGINE.profiles
            ok = (pr.create(name) if act == "create" else ENGINE.use_profile(name) if act == "switch"
                  else pr.delete(name) if act == "delete" else False)
            if act == "create" and ok and body.get("switch"):
                ENGINE.use_profile(pr.clean(name))
            return self._json({"ok": ok, **pr.info()})
        if path == "/api/shared/sync":
            threading.Thread(target=SHARED.sync, daemon=True).start()
            return self._json({"ok": True})
        if path == "/api/session/reset":
            ENGINE.reset_session()
            return self._json({"ok": True})
        self._json({"error": "inconnu"}, 404)


def producer(engine: Engine) -> None:
    period = 1.0 / SEND_HZ
    err_shown = 0.0
    while True:
        t0 = time.monotonic()
        try:
            data = engine.step()
        except Exception as e:  # noqa: BLE001  le jeu n'est pas lancé, mmap indisponible...
            data = {"connected": False, "state": "error", "error": str(e)}
            if time.monotonic() - err_shown > 10:
                print(f"[lecture] {e}")
                err_shown = time.monotonic()
        HUB.publish(json.dumps(data, separators=(",", ":"), allow_nan=False, default=str))
        time.sleep(max(0.0, period - (time.monotonic() - t0)))


def main() -> None:
    global ENGINE, SETTINGS, SHARED
    ap = argparse.ArgumentParser(description="LMU Dash - dashboard second écran pour Le Mans Ultimate")
    ap.add_argument("--demo", action="store_true", help="données simulées (sans le jeu)")
    ap.add_argument("--demo-speed", type=float, default=1.0, help="accélère la démo (ex: 20)")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 pour y accéder depuis un autre appareil du réseau")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--pit-loss", type=float, default=None, help="temps perdu par arrêt (s) tant qu'aucun n'est mesuré")
    ap.add_argument("--data-dir", default=None, help="dossier de sauvegarde (par défaut : ./data à côté du programme)")
    ap.add_argument("--profile", default=None, help="joueur (profil) à utiliser ; créé s'il n'existe pas")
    ap.add_argument("--shared-repo", default=DEFAULT_REPO, help="dépôt GitHub des cartes partagées (owner/nom)")
    ap.add_argument("--no-sync", action="store_true", help="ne pas télécharger les cartes partagées")
    ap.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur au démarrage")
    args = ap.parse_args()

    folder = args.data_dir or data_dir(demo=args.demo)
    os.makedirs(folder, exist_ok=True)
    profiles = Profiles(folder)
    if args.profile:
        profiles.create(args.profile)
        profiles.switch(next((n for n in profiles.names if n.lower() == profiles.clean(args.profile).lower()), profiles.active))
    SETTINGS = Settings(os.path.join(profiles.path(), "settings.json"))
    if args.pit_loss is not None:
        SETTINGS.update({"pitLoss": args.pit_loss})

    if args.demo:
        from readers import DemoReader
        reader = DemoReader(SETTINGS, args.demo_speed)
    else:
        from readers import LMUReader
        reader = LMUReader(SETTINGS)
    ENGINE = Engine(reader, SETTINGS, folder, profiles)
    SHARED = Shared(args.shared_repo, ENGINE.tracks, enabled=not args.no_sync and not args.demo)

    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    url = f"http://{shown}:{args.port}"
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError:
        print(f"Le port {args.port} est déjà utilisé : LMU Dash tourne peut-être déjà. Ouverture de {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return
    srv.daemon_threads = True
    threading.Thread(target=producer, args=(ENGINE,), daemon=True).start()
    SHARED.start()

    print(f"LMU Dash {'(DEMO) ' if args.demo else ''}prêt -> {url}")
    print(f"Données sauvegardées dans : {folder}  (joueur : {profiles.active})")
    if args.host == "0.0.0.0":
        print("Accessible depuis ton réseau local avec l'IP de ce PC (ex: http://192.168.x.x:%d)" % args.port)
    print("Ctrl+C pour arrêter.")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ENGINE.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        if getattr(sys, "frozen", False):
            input("\nErreur - appuie sur Entrée pour fermer cette fenêtre…")
        sys.exit(1)
