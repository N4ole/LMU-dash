#!/usr/bin/env python3
"""Construit le site GitHub Pages (_site/) à partir de docs/ et de la liste des circuits (tracks/index.json).

python tools/build_site.py            # -> _site/
python tools/build_site.py --out dossier
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from track_svg import render_svg  # noqa: E402

from store import slug, validate_track  # noqa: E402

START, END = "<!-- TRACKS -->", "<!-- /TRACKS -->"
ASSETS = (".png", ".jpg", ".svg", ".ico", ".webp")


def load_tracks(tracks_dir: str) -> list[dict]:
    """Circuits listés dans l'index ET présents/valides (l'index peut avoir un temps de retard)."""
    try:
        with open(os.path.join(tracks_dir, "index.json"), encoding="utf-8") as f:
            items = json.load(f).get("tracks") or []
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for it in items:
        name = it.get("file") if isinstance(it, dict) else None
        if not isinstance(name, str) or os.path.basename(name) != name:
            continue
        try:
            with open(os.path.join(tracks_dir, name), encoding="utf-8") as f:
                o = json.load(f)
        except (OSError, ValueError):
            continue
        if validate_track(o):
            out.append(o)
    return sorted(out, key=lambda o: o["key"].lower())


def tracks_html(tracks: list[dict]) -> str:
    if not tracks:
        return (
            '<div class="empty">Aucun circuit partagé pour l\'instant : sois le premier à '
            '<a href="#contribuer">en proposer un</a> !</div>'
        )
    cards = [
        f'<figure class="track"><img src="tracks/{escape(slug(o["key"]))}.svg" width="360" height="360" '
        f'loading="lazy" alt="Tracé de {escape(o["key"])}"><span>{escape(o["key"])}</span></figure>'
        for o in tracks
    ]
    count = f'<p class="lead" style="margin-top:-8px">{len(tracks)} circuit(s) disponible(s).</p>'
    return count + '<div class="tracks">' + "".join(cards) + "</div>"


def build(out: str, docs: str = os.path.join(ROOT, "docs"), tracks_dir: str = os.path.join(ROOT, "tracks")) -> int:
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "tracks"))
    for name in os.listdir(docs):
        if name.lower().endswith(ASSETS):
            shutil.copy2(os.path.join(docs, name), os.path.join(out, name))
    tracks = load_tracks(tracks_dir)
    for o in tracks:
        with open(os.path.join(out, "tracks", slug(o["key"]) + ".svg"), "w", encoding="utf-8") as f:
            f.write(render_svg(o))
    with open(os.path.join(docs, "index.html"), encoding="utf-8") as f:
        page = f.read()
    a, b = page.index(START), page.index(END) + len(END)
    page = page[:a] + tracks_html(tracks) + page[b:]
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(out, ".nojekyll"), "w") as f:
        f.write("")
    return len(tracks)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    a = ap.parse_args()
    n = build(a.out)
    print(f"Site généré dans {a.out} ({n} circuit(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
