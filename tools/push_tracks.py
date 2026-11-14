#!/usr/bin/env python3
"""Publie sur GitHub les cartes apprises pendant tes sessions.

À lancer depuis ton clone du dépôt (ou via pousser_cartes.bat) :
    python tools/push_tracks.py                      # data/ du clone
    python tools/push_tracks.py --data "D:\\LMU\\data" # dossier data de l'exe
Options : --no-push (commit seulement), --force (remplace une carte déjà présente), --dry-run.

Étapes : cartes complètes avec secteurs -> validation -> copie dans tracks/ -> index -> git commit + push.
"""

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from store import read_json, slug, validate_track, write_json  # noqa: E402


def git(*a, check=True):
    return subprocess.run(["git", "-C", ROOT, *a], check=check, capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    src = os.path.join(a.data, "tracks")
    if not os.path.isdir(src):
        print(f"Aucun dossier de cartes : {src}")
        return 1
    dst = os.path.join(ROOT, "tracks")
    os.makedirs(dst, exist_ok=True)
    added, skipped = [], []
    for n in sorted(os.listdir(src)):
        if not n.endswith(".json"):
            continue
        p = os.path.join(src, n)
        o = read_json(p)
        if not validate_track(o) or not o.get("sectors") or None in o["sectors"]:
            skipped.append((n, "incomplète (tracé < 97 % ou secteurs non appris)"))
            continue
        out = {"v": 1, "key": o["key"], "pts": o["pts"], "sectors": o["sectors"]}
        target = os.path.join(dst, slug(o["key"]) + ".json")
        if os.path.exists(target) and not a.force:
            skipped.append((n, "déjà dans le dépôt (--force pour remplacer)"))
            continue
        added.append((o["key"], p, target, out))

    for n, why in skipped:
        print(f"  - {n} ignorée : {why}")
    if not added:
        print("Rien à publier.")
        return 0
    for key, _, _, _ in added:
        print(f"  + {key}")
    if a.dry_run:
        return 0

    for _key, _p, target, out in added:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(out, f, separators=(",", ":"))
    # index + validation
    for script in ("validate_tracks.py", "build_index.py"):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", script)], cwd=ROOT)
        if r.returncode:
            print("Validation échouée, rien n'est poussé.")
            return 1
    names = ", ".join(k for k, *_ in added)
    git("add", "tracks")
    c = git("commit", "-m", f"Cartes : {names}", check=False)
    if c.returncode:
        print(c.stdout + c.stderr)
        return 1
    # ces cartes sont maintenant « partagées » : plus de rappel dans l'app
    for _key, p, _target, _out in added:
        o = read_json(p) or {}
        o["shared"] = True
        write_json(p, o)
    if a.no_push:
        print("Commit créé (pas de push).")
        return 0
    r = git("push", check=False)
    print(r.stdout + r.stderr)
    print("Publié." if r.returncode == 0 else "Le push a échoué : vérifie ta connexion GitHub (git push à la main).")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
