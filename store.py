"""Persistance sur disque : réglages, cartes de circuit, état de course, archives de sessions.
Tout est écrit dans un dossier `data/` à côté du programme (ou dans %APPDATA%\\LMU-Dash si ce
dossier n'est pas inscriptible)."""

from __future__ import annotations

import contextlib
import copy
import json
import os
import re
import sys
import threading
import time


def app_dir() -> str:
    """Dossier du .exe (version packagée) ou du script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir() -> str:
    """Dossier des fichiers embarqués (web/) : _MEIPASS dans l'.exe, sinon le dossier du script."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_dir())
    return os.path.dirname(os.path.abspath(__file__))


def data_dir(demo: bool = False) -> str:
    candidates = [
        os.path.join(app_dir(), "data"),
        os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "LMU-Dash"),
    ]
    for base in candidates:
        try:
            path = os.path.join(base, "demo") if demo else base
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".write_test")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return path
        except OSError:
            continue
    raise RuntimeError("Aucun dossier inscriptible pour sauvegarder les données.")


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError as e:
        print(f"[sauvegarde] impossible d'écrire {os.path.basename(path)} : {e}")


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_.")[:80] or "x"


# --------------------------------------------------------------------------
# Réglages
# --------------------------------------------------------------------------

ALERT_IDS = ["fuel", "energy", "engine", "tyres", "box", "flags", "damage", "penalty", "rain", "stint"]

DEFAULTS: dict = {
    "pitLoss": 60.0,  # s, utilisé tant qu'aucun arrêt n'a été mesuré
    "pitLossAuto": True,  # mesurer le temps perdu aux stands
    "tyreMin": 25.0,  # % de bande restante considéré comme « pneu fini »
    "tyreMinByCompound": {},  # {"Soft": 30, ...}
    "margin": 0.5,  # marge de sécurité en tours
    "stintMaxMin": 0,  # 0 = pas de limite
    "driverMaxMin": 0,
    "sound": False,
    "volume": 0.6,
    "alerts": {k: True for k in ALERT_IDS},
    "classFilter": "ALL",
    "flagMap": "direct",  # indice de mSectorFlag <-> secteur (appris automatiquement)
    "tracks": {},  # {"clé circuit": {"rot": 0, "flip": false}}
}


def _num(v, lo, hi, default):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x:  # NaN
        return default
    return max(lo, min(hi, x))


class Settings:
    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data = copy.deepcopy(DEFAULTS)
        saved = read_json(path, {})
        if isinstance(saved, dict):
            self._apply(saved)

    def rebind(self, path: str) -> None:
        """Change de profil : recharge les réglages depuis un autre fichier."""
        with self.lock:
            self.path = path
            self.data = copy.deepcopy(DEFAULTS)
            saved = read_json(path, {})
            if isinstance(saved, dict):
                self._apply(saved)

    def _apply(self, patch: dict) -> None:
        d = self.data
        if "pitLoss" in patch:
            d["pitLoss"] = _num(patch["pitLoss"], 10, 300, d["pitLoss"])
        if "pitLossAuto" in patch:
            d["pitLossAuto"] = bool(patch["pitLossAuto"])
        if "tyreMin" in patch:
            d["tyreMin"] = _num(patch["tyreMin"], 5, 70, d["tyreMin"])
        if "margin" in patch:
            d["margin"] = _num(patch["margin"], 0, 3, d["margin"])
        if "stintMaxMin" in patch:
            d["stintMaxMin"] = _num(patch["stintMaxMin"], 0, 600, d["stintMaxMin"])
        if "driverMaxMin" in patch:
            d["driverMaxMin"] = _num(patch["driverMaxMin"], 0, 1500, d["driverMaxMin"])
        if "sound" in patch:
            d["sound"] = bool(patch["sound"])
        if "volume" in patch:
            d["volume"] = _num(patch["volume"], 0, 1, d["volume"])
        if patch.get("flagMap") in ("direct", "quirk"):
            d["flagMap"] = patch["flagMap"]
        if isinstance(patch.get("classFilter"), str):
            d["classFilter"] = patch["classFilter"][:40]
        if isinstance(patch.get("alerts"), dict):
            for k, v in patch["alerts"].items():
                if k in ALERT_IDS:
                    d["alerts"][k] = bool(v)
        if isinstance(patch.get("tyreMinByCompound"), dict):  # remplace entièrement (permet de supprimer)
            d["tyreMinByCompound"] = {str(k)[:40]: _num(v, 5, 70, 25.0) for k, v in patch["tyreMinByCompound"].items()}
        if isinstance(patch.get("tracks"), dict):
            for k, v in patch["tracks"].items():
                if isinstance(v, dict):
                    cur = d["tracks"].setdefault(str(k)[:120], {"rot": 0, "flip": False})
                    if "rot" in v:
                        cur["rot"] = int(_num(v["rot"], 0, 3, 0))
                    if "flip" in v:
                        cur["flip"] = bool(v["flip"])

    def update(self, patch: dict) -> dict:
        with self.lock:
            self._apply(patch)
            write_json(self.path, self.data)
            return copy.deepcopy(self.data)

    def get(self) -> dict:
        with self.lock:
            return copy.deepcopy(self.data)

    def tyre_min(self, compound: str) -> float:
        """Seuil d'usure (fraction 0..1) pour une gomme donnée."""
        with self.lock:
            by = self.data["tyreMinByCompound"]
            for k, v in by.items():
                if k.lower() == (compound or "").lower():
                    return v / 100.0
            return self.data["tyreMin"] / 100.0


# --------------------------------------------------------------------------
# Carte du circuit (apprise côté serveur)
# --------------------------------------------------------------------------

BINS = 360


def validate_track(o) -> bool:
    """Contrôle strict d'une carte reçue d'ailleurs (jamais de confiance aveugle)."""
    try:
        if not isinstance(o, dict) or not isinstance(o.get("key"), str) or not (0 < len(o["key"]) <= 120):
            return False
        pts = o.get("pts")
        if not isinstance(pts, list) or len(pts) != BINS:
            return False
        ok = 0
        for p in pts:
            if p is None:
                continue
            if not (
                isinstance(p, list)
                and len(p) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 100000 for v in p)
            ):
                return False
            ok += 1
        if ok < BINS * 0.97:
            return False
        sec = o.get("sectors")
        if sec is not None:
            if not (isinstance(sec, list) and len(sec) == 2):
                return False
            if any(v is not None and not (isinstance(v, (int, float)) and 0.02 < v < 0.98) for v in sec):
                return False
            if sec[0] is not None and sec[1] is not None and not sec[0] < sec[1]:
                return False
        return True
    except Exception:  # noqa: BLE001
        return False


class TrackStore:
    """Apprend le tracé à partir de la position de toutes les voitures, le mémorise sur disque."""

    def __init__(self, folder: str) -> None:
        self.dir = os.path.join(folder, "tracks")
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.Lock()
        self.key = ""
        self.pts: list = [None] * BINS
        self.filled = 0
        self.rev = 0
        self.dirty = False
        self.last_save = 0.0
        self.shared = False
        self.bsamp: list[list[float]] = [[], []]  # mesures des limites S1/S2 et S2/S3 (fraction du tour)
        self.prev_sector = 0

    def _path(self, key: str) -> str:
        return os.path.join(self.dir, slug(key) + ".json")

    def _load(self, key: str) -> None:
        self.key, self.pts, self.filled, self.dirty = key, [None] * BINS, 0, False
        self.bsamp, self.prev_sector, self.shared = [[], []], 0, False
        saved = read_json(self._path(key))
        if saved is None:  # anciennes sauvegardes (clé « nom|longueur »)
            try:
                old = sorted(f for f in os.listdir(self.dir) if f.startswith(slug(key) + "_") and f.endswith(".json"))
                if old:
                    saved = read_json(os.path.join(self.dir, old[0]))
            except OSError:
                pass
        if isinstance(saved, dict) and isinstance(saved.get("pts"), list) and len(saved["pts"]) == BINS:
            self.pts = [p if (isinstance(p, list) and len(p) == 2) else None for p in saved["pts"]]
            self.filled = sum(1 for p in self.pts if p)
            self.shared = bool(saved.get("shared"))
            sec = saved.get("sectors")
            if isinstance(sec, list) and len(sec) == 2:
                self.bsamp = [[float(x)] if isinstance(x, (int, float)) else [] for x in sec]
        self.rev += 1

    def _save(self) -> None:
        write_json(
            self._path(self.key),
            {"key": self.key, "pts": self.pts, "sectors": self._bounds(), "shared": self.shared, "saved": time.time()},
        )
        self.dirty = False
        self.last_save = time.monotonic()

    def _bounds(self):
        return [round(sum(b) / len(b), 4) if b else None for b in self.bsamp]

    def _learn_sector(self, payload: dict, length: float) -> None:
        tm = payload.get("timing") or {}
        sec = tm.get("sector") or 0
        me = next((r for r in payload.get("standings") or [] if r.get("me")), None)
        if (
            sec in (1, 2, 3)
            and self.prev_sector in (1, 2)
            and sec == self.prev_sector % 3 + 1
            and me
            and not me.get("inPits")
            and me.get("d") is not None
            and 0 <= me["d"] <= length
        ):
            i = self.prev_sector - 1
            f = me["d"] / length
            cur = self.bsamp[i]
            # la limite de secteur ne bouge pas : on ignore une mesure aberrante
            if not cur or abs(f - sum(cur) / len(cur)) < 0.03:
                self.bsamp[i] = (cur + [f])[-5:]
                self.rev += 1
                self.dirty = True
                self._save()  # rare : on écrit tout de suite pour ne jamais perdre les secteurs
        if sec in (1, 2, 3):
            self.prev_sector = sec

    @property
    def complete(self) -> bool:
        return self.filled >= BINS * 0.97

    def update(self, payload: dict) -> None:
        s = payload.get("session")
        rows = payload.get("standings")
        if not s or not rows:
            return
        length = s.get("trackLength") or 0
        if length <= 0 or not s.get("track"):
            return
        key = str(s["track"])
        with self.lock:
            if key != self.key:
                if self.dirty:
                    self._save()
                self._load(key)
            self._learn_sector(payload, length)
            if not self.complete:
                for r in rows:
                    d = r.get("d")
                    if r.get("inPits") or r.get("garage") or d is None or not (0 <= d <= length):
                        continue
                    b = int(d / length * BINS) % BINS
                    if self.pts[b] is None:
                        self.pts[b] = [round(r["x"]), round(r["z"])]
                        self.filled += 1
                        self.rev += 1
                        self.dirty = True
            if self.dirty and (self.complete or time.monotonic() - self.last_save > 30):
                self._save()

    def info(self) -> dict:
        with self.lock:
            return {
                "key": self.key,
                "rev": self.rev,
                "filled": self.filled,
                "complete": self.complete,
                "sectors": self._bounds(),
            }

    def current(self) -> dict:
        with self.lock:
            return {
                "key": self.key,
                "rev": self.rev,
                "filled": self.filled,
                "complete": self.complete,
                "sectors": self._bounds(),
                "pts": self.pts,
            }

    def reset(self) -> None:
        with self.lock:
            self.pts, self.filled, self.dirty = [None] * BINS, 0, False
            self.rev += 1
            with contextlib.suppress(OSError):
                os.remove(self._path(self.key))

    def adopt(self, obj: dict) -> bool:
        """Intègre une carte partagée (validée) si elle apporte quelque chose de plus que la nôtre."""
        if not validate_track(obj):
            return False
        key = obj["key"]
        with self.lock:
            path = self._path(key)
            local = read_json(path) if key != self.key else {"pts": self.pts, "sectors": self._bounds()}
            lpts = [p for p in (local or {}).get("pts") or [] if p]
            lsec = (local or {}).get("sectors") or [None, None]
            need_pts = len(lpts) < BINS * 0.97
            need_sec = any(v is None for v in lsec) and all(v is not None for v in (obj.get("sectors") or [None, None]))
            if not (need_pts or need_sec):
                return False
            pts = obj["pts"] if need_pts else local["pts"]
            sec = obj["sectors"] if need_sec else lsec
            write_json(path, {"key": key, "pts": pts, "sectors": sec, "shared": True, "saved": time.time()})
            if key == self.key:
                self._load(key)
            return True

    def shareable(self) -> list:
        """Cartes complètes apprises ici et pas encore partagées."""
        out = []
        try:
            names = sorted(os.listdir(self.dir))
        except OSError:
            return out
        for n in names:
            if not n.endswith(".json"):
                continue
            o = read_json(os.path.join(self.dir, n))
            if (
                isinstance(o, dict)
                and not o.get("shared")
                and validate_track(o)
                and (o.get("sectors") or [None])[0]
                and all(v is not None for v in o["sectors"])
            ):
                out.append({"key": o["key"], "file": n})
        return out

    def export(self, key: str | None = None) -> dict | None:
        with self.lock:
            k = key or self.key
            o = read_json(self._path(k)) if k else None
            if k == self.key:
                o = {"key": k, "pts": self.pts, "sectors": self._bounds()}
            if not isinstance(o, dict):
                return None
            return {"v": 1, "key": o.get("key", k), "pts": o["pts"], "sectors": o.get("sectors")}

    def flush(self) -> None:
        with self.lock:
            if self.dirty and self.key:
                self._save()


# --------------------------------------------------------------------------
# État de course (reprise après plantage) + archives
# --------------------------------------------------------------------------


class StateFile:
    MAX_AGE = 30 * 60  # on ne reprend que si la sauvegarde a moins de 30 min

    def __init__(self, folder: str) -> None:
        self.path = os.path.join(folder, "state.json")
        self.archive_dir = os.path.join(folder, "sessions")
        os.makedirs(self.archive_dir, exist_ok=True)

    def rebind(self, folder: str) -> None:
        self.path = os.path.join(folder, "state.json")
        self.archive_dir = os.path.join(folder, "sessions")
        os.makedirs(self.archive_dir, exist_ok=True)

    def save(self, key: str, et: float, stats: dict | None, endurance: dict) -> None:
        write_json(self.path, {"key": key, "et": et, "savedAt": time.time(), "stats": stats, "endurance": endurance})

    def load(self, key: str, et: float) -> dict | None:
        d = read_json(self.path)
        if not isinstance(d, dict) or d.get("key") != key:
            return None
        if time.time() - float(d.get("savedAt") or 0) > self.MAX_AGE:
            return None
        if et + 2 < float(d.get("et") or 0):  # le chrono de session a reculé : autre session
            return None
        return d

    def archive(self, label: str, laps_csv: str, stints_csv: str) -> None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = os.path.join(self.archive_dir, f"{stamp}_{slug(label)}")
        for suffix, content in (("_tours.csv", laps_csv), ("_relais.csv", stints_csv)):
            try:
                with open(base + suffix, "w", encoding="utf-8-sig", newline="") as f:
                    f.write(content)
            except OSError as e:
                print(f"[archive] {e}")


# --------------------------------------------------------------------------
# Records (toutes sessions confondues)
# --------------------------------------------------------------------------


class Records:
    """Meilleur tour et meilleurs secteurs par circuit + voiture, conservés d'une session à l'autre."""

    def __init__(self, folder: str) -> None:
        self.path = os.path.join(folder, "records.json")
        self.lock = threading.Lock()
        d = read_json(self.path, {})
        self.data: dict = d if isinstance(d, dict) else {}
        self.key = ""
        self.prev_laps: int | None = None
        self.flags = {"pit": False, "neutral": False, "invalid": False}

    def rebind(self, folder: str) -> None:
        with self.lock:
            self.path = os.path.join(folder, "records.json")
            d = read_json(self.path, {})
            self.data = d if isinstance(d, dict) else {}
            self.key, self.prev_laps = "", None
            self.flags = {"pit": False, "neutral": False, "invalid": False}

    @staticmethod
    def _entry() -> dict:
        return {
            "track": "",
            "car": "",
            "lap": None,
            "lapSectors": None,
            "lapDriver": "",
            "lapDate": "",
            "sectors": [None, None, None],
        }

    def update(self, d: dict) -> None:
        s, c, t = d.get("session"), d.get("car"), d.get("timing")
        if not (s and c and t) or not s.get("track"):
            return
        key = f"{s['track']}|{c.get('model') or c.get('name') or '?'}"
        laps = int(t.get("laps") or 0)
        with self.lock:
            if key != self.key:
                self.key, self.prev_laps = key, laps
                self.flags = {"pit": False, "neutral": False, "invalid": False}
            self.flags["pit"] |= bool(c.get("inPits"))
            self.flags["neutral"] |= bool(s.get("neutral"))
            self.flags["invalid"] |= bool(t.get("invalid"))
            if self.prev_laps is not None and laps == self.prev_laps + 1:
                last, sec = t.get("last"), t.get("lastSectors")
                clean = last and last > 30 and not any(self.flags.values())
                if clean:
                    self._submit(key, s["track"], c, float(last), sec)
                self.flags = {"pit": bool(c.get("inPits")), "neutral": bool(s.get("neutral")), "invalid": False}
            elif self.prev_laps is not None and laps != self.prev_laps:
                self.flags = {"pit": False, "neutral": False, "invalid": False}
            self.prev_laps = laps

    def _submit(self, key: str, track: str, c: dict, lap: float, sec) -> None:
        e = self.data.setdefault(key, self._entry())
        e["track"], e["car"] = track, c.get("model") or c.get("name") or ""
        changed = False
        if e["lap"] is None or lap < e["lap"]:
            e["lap"], e["lapSectors"] = round(lap, 3), sec
            e["lapDriver"], e["lapDate"] = c.get("driver") or "", time.strftime("%Y-%m-%d")
            changed = True
        if sec:
            for i, v in enumerate(sec):
                if v and v > 5 and (e["sectors"][i] is None or v < e["sectors"][i]):
                    e["sectors"][i] = round(v, 3)
                    changed = True
        if changed:
            write_json(self.path, self.data)

    def current(self) -> dict | None:
        with self.lock:
            e = self.data.get(self.key)
            if not e:
                return None
            sec = e["sectors"]
            theo = round(sum(sec), 3) if all(sec) else None
            return {
                "lap": e["lap"],
                "lapSectors": e["lapSectors"],
                "lapDriver": e["lapDriver"],
                "lapDate": e["lapDate"],
                "sectors": sec,
                "theoretical": theo,
                "car": e["car"],
            }

    def all(self) -> list:
        with self.lock:
            out = []
            for e in self.data.values():
                sec = e["sectors"]
                out.append({**e, "theoretical": round(sum(sec), 3) if all(sec) else None})
            return sorted(out, key=lambda x: (x["track"], x["car"]))


# --------------------------------------------------------------------------
# Profils (un dossier de données par joueur ; les cartes restent communes)
# --------------------------------------------------------------------------


class Profiles:
    MOVE = ("settings.json", "records.json", "state.json", "sessions")

    def __init__(self, root: str) -> None:
        self.root = root
        self.dir = os.path.join(root, "profiles")
        self.meta = os.path.join(root, "profiles.json")
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.Lock()
        m = read_json(self.meta)
        fresh = not isinstance(m, dict) or not m.get("profiles")
        self.names: list[str] = [] if fresh else [str(x) for x in m["profiles"]]
        self.active: str = "" if fresh else str(m.get("active") or "")
        if fresh:
            self.names, self.active = ["Joueur"], "Joueur"
            self._migrate_legacy()
        if self.active not in self.names:
            self.active = self.names[0]
        os.makedirs(self.path(), exist_ok=True)
        self._save()

    def _migrate_legacy(self) -> None:
        dst = self.path("Joueur")
        os.makedirs(dst, exist_ok=True)
        for n in self.MOVE:
            src = os.path.join(self.root, n)
            if os.path.exists(src):
                with contextlib.suppress(OSError):
                    os.replace(src, os.path.join(dst, n))

    def _save(self) -> None:
        write_json(self.meta, {"active": self.active, "profiles": self.names})

    @staticmethod
    def clean(name: str) -> str:
        return re.sub(r"\s+", " ", str(name or "")).strip()[:30]

    def path(self, name: str | None = None) -> str:
        return os.path.join(self.dir, slug(name or self.active))

    def info(self) -> dict:
        with self.lock:
            return {"active": self.active, "profiles": list(self.names)}

    def create(self, name: str) -> bool:
        name = self.clean(name)
        with self.lock:
            if not name or any(slug(n).lower() == slug(name).lower() for n in self.names):
                return False
            self.names.append(name)
            os.makedirs(self.path(name), exist_ok=True)
            self._save()
            return True

    def switch(self, name: str) -> bool:
        with self.lock:
            if name not in self.names:
                return False
            self.active = name
            os.makedirs(self.path(), exist_ok=True)
            self._save()
            return True

    def delete(self, name: str) -> bool:
        import shutil

        with self.lock:
            if name not in self.names or name == self.active or len(self.names) <= 1:
                return False
            self.names.remove(name)
            shutil.rmtree(self.path(name), ignore_errors=True)
            self._save()
            return True
