#!/usr/bin/env python3
"""Régénère tracks/index.json à partir des cartes valides."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from store import validate_track  # noqa: E402

items = []
for f in sorted(glob.glob("tracks/*.json")):
    if os.path.basename(f) == "index.json":
        continue
    try:
        with open(f, encoding="utf-8") as fh:
            o = json.load(fh)
        if validate_track(o):
            items.append({"key": o["key"], "file": os.path.basename(f)})
    except Exception:  # noqa: BLE001
        pass
with open("tracks/index.json", "w", encoding="utf-8") as fh:
    json.dump({"v": 1, "tracks": items}, fh, indent=1, ensure_ascii=False)
print(len(items), "circuit(s) dans l'index")
