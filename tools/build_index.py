#!/usr/bin/env python3
"""Régénère tracks/index.json à partir des cartes valides (lu par l'application pour la synchro)."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate_tracks import ROOT, load, track_files  # noqa: E402

from store import validate_track  # noqa: E402


def build(folder: str) -> list[dict]:
    items = []
    for f in track_files(folder):
        try:
            o = load(f)
        except (OSError, ValueError):
            continue
        if validate_track(o):
            items.append({"key": o["key"], "file": os.path.basename(f)})
    return items


def main() -> int:
    folder = os.path.join(ROOT, "tracks")
    items = build(folder)
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"v": 1, "tracks": items}, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(len(items), "circuit(s) dans l'index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
