#!/usr/bin/env python3
"""Régénère les captures d'écran de la documentation (docs/*.png) avec le mode --demo.

python -m pip install playwright && python -m playwright install chromium
python tools/screenshot.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from smoke_test import free_port  # noqa: E402

OUT = os.path.join(ROOT, "docs")


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    from playwright.sync_api import sync_playwright

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as data:
        cmd = [sys.executable, os.path.join(ROOT, "server.py"), "--demo", "--demo-speed", "25", "--no-browser"]
        proc = subprocess.Popen([*cmd, "--port", str(port), "--data-dir", data], stdout=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:  # attendre une carte complète avec ses secteurs
                try:
                    tm = get_json(base + "/api/trackmap")
                    if tm.get("complete") and None not in (tm.get("sectors") or [None]):
                        break
                except OSError:
                    pass
                time.sleep(1)
            time.sleep(4)  # quelques tours de plus pour la stratégie et l'historique
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_timeout(2500)
                page.screenshot(path=os.path.join(OUT, "screenshot.png"))
                page.click("#b-endu")
                page.wait_for_timeout(1500)
                page.screenshot(path=os.path.join(OUT, "endurance.png"))
                browser.close()
        finally:
            proc.kill()
            proc.wait(timeout=10)
    print("Captures écrites dans", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
