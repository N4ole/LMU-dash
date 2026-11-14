#!/usr/bin/env python3
"""Vérifie les cartes partagées (tracks/*.json) : format, 360 points, secteurs, nom de fichier.

python tools/validate_tracks.py              # tout le dossier tracks/
python tools/validate_tracks.py a.json b.json
python tools/validate_tracks.py --strict     # + géométrie plausible, format exact, pas de doublon
python tools/validate_tracks.py --strict --schema   # + tracks/schema.json (nécessite jsonschema)

Le mode normal correspond à ce que l'application accepte (store.validate_track). Le mode strict, utilisé par
la CI pour les cartes du dépôt, refuse en plus les cartes manifestement fausses.
"""

from __future__ import annotations

import glob
import json
import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from store import slug, validate_track  # noqa: E402

MAX_BYTES = 200_000
NOT_TRACKS = {"index.json", "schema.json"}  # fichiers de tracks/ qui ne sont pas des cartes
SCHEMA = os.path.join(ROOT, "tracks", "schema.json")
EXPORT_KEYS = {"v", "key", "pts", "sectors"}  # format exact de « Exporter la carte actuelle »
MIN_LENGTH, MAX_LENGTH = 1_000, 30_000  # m : longueur plausible d'une boucle de circuit
MIN_SECTOR = 0.05  # chaque secteur fait au moins 5 % du tour
JUMP_FACTOR, JUMP_MIN = 8, 300  # un pas > max(8 x pas médian, 300 m) = point aberrant


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


def loop_steps(pts: list) -> list[float]:
    """Distances entre points consécutifs présents (en ignorant les trous), boucle refermée."""
    have = [p for p in pts if p]
    return [math.dist(have[i], have[(i + 1) % len(have)]) for i in range(len(have))] if len(have) > 1 else []


def strict_errors(o: dict) -> list[str]:
    """Contrôles supplémentaires sur une carte déjà valide (check_track sans erreur)."""
    errors = []
    extra = sorted(set(o) - EXPORT_KEYS)
    if extra:
        errors.append(f"champs inattendus : {', '.join(extra)} (utilise l'export de LMU Dash sans le modifier)")
    if o.get("v") != 1:
        errors.append('version de format attendue : "v": 1')
    steps = loop_steps(o["pts"])
    length = sum(steps)
    if not MIN_LENGTH <= length <= MAX_LENGTH:
        errors.append(f"longueur de boucle peu plausible : {length / 1000:.1f} km (attendu 1 à 30 km)")
    if steps:
        median = sorted(steps)[len(steps) // 2]
        limit = max(JUMP_FACTOR * median, JUMP_MIN)
        jumps = [i for i, d in enumerate(steps) if d > limit]
        if jumps:
            errors.append(f"{len(jumps)} point(s) aberrant(s) : saut de {max(steps):.0f} m (pas médian {median:.0f} m)")
    sec = o.get("sectors") or [None, None]
    if None not in sec:
        sizes = (sec[0], sec[1] - sec[0], 1 - sec[1])
        if min(sizes) < MIN_SECTOR:
            errors.append(f"secteur trop court ({min(sizes) * 100:.1f} % du tour)")
    return errors


def fingerprint(o: dict) -> str:
    return json.dumps([o.get("pts"), o.get("sectors")], separators=(",", ":"))


def duplicate_errors(path: str, o: dict, others: list[str]) -> list[str]:
    """Doublon exact (même tracé et mêmes secteurs) d'une autre carte du dossier."""
    fp = fingerprint(o)
    for other in others:
        if os.path.abspath(other) == os.path.abspath(path):
            continue
        try:
            if fingerprint(load(other)) == fp:
                return [f"doublon exact de {os.path.basename(other)}"]
        except (OSError, ValueError):
            continue
    return []


def schema_errors(o) -> list[str]:
    import jsonschema  # outil de dev (requirements-dev.txt) : pas une dépendance de l'application

    with open(SCHEMA, encoding="utf-8") as fh:
        schema = json.load(fh)
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"schéma : {'/'.join(str(x) for x in e.absolute_path) or 'racine'} : {e.message[:150]}"
        for e in sorted(validator.iter_errors(o), key=lambda e: list(e.absolute_path))[:5]
    ]


def check_file(path: str, strict: bool = False, schema: bool = False, others: list[str] | None = None) -> list[str]:
    try:
        o = load(path)
    except (OSError, ValueError) as e:
        return [f"illisible : {e}"]
    errors = schema_errors(o) if schema else []
    errors += check_track(o, os.path.basename(path))
    if strict and validate_track(o):
        errors += strict_errors(o)
        errors += duplicate_errors(path, o, others or [])
    return errors


def track_files(folder: str) -> list[str]:
    return [f for f in sorted(glob.glob(os.path.join(folder, "*.json"))) if os.path.basename(f) not in NOT_TRACKS]


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    schema = "--schema" in argv
    files = [a for a in argv if not a.startswith("--")] or track_files(os.path.join(ROOT, "tracks"))
    others = sorted(set(track_files(os.path.join(ROOT, "tracks"))) | set(files))
    bad = 0
    for f in files:
        errors = check_file(f, strict=strict, schema=schema, others=others)
        for e in errors:
            print(f"ERREUR {os.path.basename(f)} : {e}")
        bad += bool(errors)
    print(f"OK ({len(files)} carte(s))" if not bad else f"{bad} fichier(s) invalide(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
