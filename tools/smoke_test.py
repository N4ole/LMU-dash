#!/usr/bin/env python3
"""Test de démarrage : lance LMU Dash en mode --demo et vérifie que le serveur répond.

python tools/smoke_test.py dist/LMU-Dash.exe       # l'exécutable construit
python tools/smoke_test.py                         # python server.py
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from version import VERSION  # noqa: E402

TIMEOUT = 60


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    target = sys.argv[1:] or [sys.executable, os.path.join(ROOT, "server.py")]
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as data:
        cmd = [*target, "--demo", "--no-browser", "--port", str(port), "--data-dir", data]
        print("Lancement :", " ".join(cmd))
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + TIMEOUT
            while True:
                if proc.poll() is not None:
                    print(proc.stdout.read().decode("utf-8", "replace"))
                    print(f"ÉCHEC : le programme s'est arrêté (code {proc.returncode})")
                    return 1
                try:
                    ver = get_json(base + "/api/version")
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        print(f"ÉCHEC : pas de réponse sur le port {port} après {TIMEOUT} s")
                        return 1
                    time.sleep(0.5)
            if ver.get("version") != VERSION:
                print(f"ÉCHEC : version {ver.get('version')!r}, attendu {VERSION!r}")
                return 1
            if ver.get("enabled"):
                print("ÉCHEC : la recherche de mise à jour devrait être désactivée en démo")
                return 1
            for _ in range(20):  # la démo produit des données en continu
                snap = get_json(base + "/snapshot")
                if snap.get("demo") and snap.get("connected"):
                    break
                time.sleep(0.25)
            else:
                print("ÉCHEC : /snapshot ne renvoie pas de données de démo")
                return 1
            with urllib.request.urlopen(base + "/", timeout=3) as r:
                if r.status != 200 or b"LMU" not in r.read():
                    print("ÉCHEC : la page web n'est pas servie")
                    return 1
            print(f"OK : LMU Dash {VERSION} répond sur {base}")
            return 0
        finally:
            proc.kill()
            proc.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
