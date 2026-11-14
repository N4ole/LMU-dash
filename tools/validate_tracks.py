#!/usr/bin/env python3
"""Vérifie les cartes partagées (tracks/*.json) : format, 360 points, secteurs, nom de fichier.

python tools/validate_tracks.py              # tout le dossier tracks/
python tools/validate_tracks.py a.json b.json
"""

from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from store import slug, validate_track  # noqa: E402

MAX_BYTES = 200_000


def load(path: str) -> dict:
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError(f"fichier trop gros (> {MAX_BYTES // 1000} ko)")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_track(o, name: str) -> list[str]:
    """Erreurs d'une carte déjà chargée (liste vide = carte acceptée)."""
    if not validate_track(o):
        return ["carte invalide (360 points, ≥97 % remplis, 2 secteurs croissants)"]
    errors = []
    if name != slug(o["key"]) + ".json":
        errors.append(f"nom attendu : {slug(o['key'])}.json")
    if o.get("sectors") is None or None in o["sectors"]:
        errors.append("secteurs manquants")
    return errors


def check_file(path: str) -> list[str]:
    try:
        o = load(path)
    except (OSError, ValueError) as e:
        return [f"illisible : {e}"]
    return check_track(o, os.path.basename(path))


def track_files(folder: str) -> list[str]:
    return [f for f in sorted(glob.glob(os.path.join(folder, "*.json"))) if os.path.basename(f) != "index.json"]


def main(argv: list[str]) -> int:
    files = argv or track_files(os.path.join(ROOT, "tracks"))
    bad = 0
    for f in files:
        errors = check_file(f)
        for e in errors:
            print(f"ERREUR {os.path.basename(f)} : {e}")
        bad += bool(errors)
    print(f"OK ({len(files)} carte(s))" if not bad else f"{bad} fichier(s) invalide(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
