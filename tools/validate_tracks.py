#!/usr/bin/env python3
"""Vérifie les cartes partagées (tracks/*.json) : format, 360 points, secteurs, nom de fichier."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from store import slug, validate_track  # noqa: E402

bad = 0
for f in sorted(glob.glob("tracks/*.json")):
    name = os.path.basename(f)
    if name == "index.json":
        continue
    try:
        if os.path.getsize(f) > 200_000:
            raise ValueError("fichier trop gros")
        with open(f, encoding="utf-8") as fh:
            o = json.load(fh)
        if not validate_track(o):
            raise ValueError("carte invalide (360 points, ≥97 % remplis, 2 secteurs croissants)")
        if name != slug(o["key"]) + ".json":
            raise ValueError(f"nom attendu : {slug(o['key'])}.json")
        if o.get("sectors") is None or None in o["sectors"]:
            raise ValueError("secteurs manquants")
    except Exception as e:  # noqa: BLE001
        bad += 1
        print(f"ERREUR {name} : {e}")
print("OK" if not bad else f"{bad} fichier(s) invalide(s)")
sys.exit(1 if bad else 0)
