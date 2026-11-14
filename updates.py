"""Indicateur « nouvelle version disponible ».

Interroge l'API GitHub Releases du dépôt officiel au démarrage puis une fois par jour.
Aucune donnée personnelle n'est envoyée ; en cas d'échec (hors-ligne, limite d'API...) on ne dit rien.
Désactivé par --no-sync (et en mode démo)."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request

from version import VERSION

CHECK_EVERY = 24 * 3600
MAX_BYTES = 512_000
_VER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(text) -> tuple[int, int, int] | None:
    """« v1.2.3 » ou « 1.2.3 » -> (1, 2, 3) ; None pour tout le reste (pré-versions comprises)."""
    m = _VER.match(str(text or "").strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _fetch_latest(repo: str) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={
            "User-Agent": f"LMU-Dash/{VERSION}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("réponse trop grosse")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("réponse inattendue")
    return data


class UpdateCheck:
    def __init__(self, repo: str, enabled: bool = True, current: str = VERSION, fetch=_fetch_latest) -> None:
        self.repo = repo
        self.enabled = enabled and bool(repo)
        self.current = current
        self._fetch = fetch
        self.lock = threading.Lock()
        self.latest: str | None = None
        self.url: str | None = None
        self.checked = 0.0

    def check(self) -> None:
        """Une vérification ; ne lève jamais d'exception."""
        if not self.enabled:
            return
        try:
            data = self._fetch(self.repo)
            tag = data.get("tag_name")
            url = data.get("html_url")
            if data.get("draft") or data.get("prerelease") or parse_version(tag) is None:
                return
            # on n'affiche qu'un lien vers les releases du dépôt attendu
            if not (
                isinstance(url, str) and url.lower().startswith(f"https://github.com/{self.repo.lower()}/releases/")
            ):
                url = f"https://github.com/{self.repo}/releases/latest"
            with self.lock:
                self.latest, self.url, self.checked = str(tag).lstrip("v"), url, time.time()
        except Exception:  # noqa: BLE001  hors-ligne, limite d'API, JSON invalide... : silence
            return

    def info(self) -> dict:
        with self.lock:
            cur, new = parse_version(self.current), parse_version(self.latest)
            available = bool(cur and new and new > cur)
            return {
                "version": self.current,
                "latest": self.latest,
                "update": available,
                "url": self.url if available else None,
                "checked": self.checked,
                "enabled": self.enabled,
            }

    def start(self) -> None:
        def loop() -> None:
            while True:
                self.check()
                time.sleep(CHECK_EVERY)

        if self.enabled:
            threading.Thread(target=loop, daemon=True, name="update-check").start()
