"""Cartes et secteurs partagés via un dépôt GitHub public (lecture seule depuis l'application).

- Au démarrage (puis toutes les 6 h) l'app lit `tracks/index.json` du dépôt et télécharge les circuits
  qui lui manquent. Chaque fichier est validé avant d'être utilisé.
- Pour contribuer, l'utilisateur exporte sa carte complète et la dépose via une Pull Request
  (page « Upload files » de GitHub) ; une vérification automatique contrôle le fichier avant fusion."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_REPO = "N4ole/lmu-dash"
BRANCH = "main"
MAX_BYTES = 200_000
SYNC_EVERY = 6 * 3600


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "LMU-Dash"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("fichier trop gros")
    return json.loads(raw.decode("utf-8"))


class Shared:
    def __init__(self, repo: str, tracks, enabled: bool = True) -> None:
        self.repo = repo
        self.tracks = tracks
        self.enabled = enabled and bool(repo)
        self.status = {
            "repo": repo,
            "enabled": self.enabled,
            "last": 0,
            "ok": None,
            "remote": 0,
            "added": 0,
            "error": "",
        }
        self.lock = threading.Lock()
        self.busy = False

    def url(self, path: str) -> str:
        return f"https://raw.githubusercontent.com/{self.repo}/{BRANCH}/{urllib.parse.quote(path)}"

    def upload_url(self) -> str:
        return f"https://github.com/{self.repo}/upload/{BRANCH}/tracks"

    def sync(self) -> None:
        if not self.enabled:
            return
        with self.lock:
            if self.busy:
                return
            self.busy = True
        added, remote, err = 0, 0, ""
        try:
            idx = _get(self.url("tracks/index.json"))
            items = idx.get("tracks") if isinstance(idx, dict) else None
            if not isinstance(items, list):
                raise ValueError("index invalide")
            remote = len(items)
            for it in items[:500]:
                f = it.get("file") if isinstance(it, dict) else None
                if not isinstance(f, str) or "/" in f or not f.endswith(".json"):
                    continue
                try:
                    if self.tracks.adopt(_get(self.url("tracks/" + f))):
                        added += 1
                except (urllib.error.URLError, ValueError, OSError):
                    continue
            ok = True
        except Exception as e:  # noqa: BLE001  hors-ligne, dépôt absent...
            ok, err = False, str(e)[:120]
        with self.lock:
            self.status.update(
                {"last": time.time(), "ok": ok, "remote": remote, "added": self.status["added"] + added, "error": err}
            )
            self.busy = False

    def start(self) -> None:
        def loop():
            while True:
                self.sync()
                time.sleep(SYNC_EVERY)

        if self.enabled:
            threading.Thread(target=loop, daemon=True).start()

    def info(self) -> dict:
        with self.lock:
            return {**self.status, "uploadUrl": self.upload_url(), "toShare": self.tracks.shareable()}
