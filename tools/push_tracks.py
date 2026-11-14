#!/usr/bin/env python3
"""Publie sur GitHub les cartes apprises pendant tes sessions.

À lancer depuis ton clone du dépôt (ou via pousser_cartes.bat) :
    python tools/push_tracks.py                      # data/ du clone
    python tools/push_tracks.py --data "D:\\LMU\\data" # dossier data de l'exe
Options : --no-push (commit seulement), --force (remplace une carte déjà présente), --dry-run.

Étapes : cartes complètes avec secteurs -> branche cartes/<date> depuis origin/main -> copie dans tracks/
-> validation stricte -> commit -> push -> Pull Request (gh si installé, sinon lien affiché).
L'index (tracks/index.json) est régénéré automatiquement après la fusion.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

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

    branch = "cartes/" + time.strftime("%Y%m%d-%H%M%S")
    previous = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    # main est protégée : les cartes partent sur une branche dédiée, créée depuis origin/main à jour
    if (
        git("fetch", "origin", "main", check=False).returncode
        or git("switch", "-c", branch, "origin/main", check=False).returncode
    ):
        print("Impossible de créer la branche (modifications en cours dans tracks/ ?). Rien n'est publié.")
        return 1
    for _key, _p, target, out in added:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(out, f, separators=(",", ":"))
    files = [t for _k, _p, t, _o in added]
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "validate_tracks.py"), "--strict", *files], cwd=ROOT
    )
    if r.returncode:
        print("Validation échouée, rien n'est publié.")
        for t in files:
            os.remove(t)
        git("switch", previous, check=False)
        git("branch", "-D", branch, check=False)
        return 1
    names = ", ".join(k for k, *_ in added)
    git("add", *files)
    c = git("commit", "-m", f"Ajouter les cartes : {names}", check=False)
    if c.returncode:
        print(c.stdout + c.stderr)
        return 1
    # ces cartes sont maintenant « partagées » : plus de rappel dans l'app
    for _key, p, _target, _out in added:
        o = read_json(p) or {}
        o["shared"] = True
        write_json(p, o)
    try:
        if a.no_push:
            print(f"Commit créé sur la branche {branch} (pas de push).")
            return 0
        r = git("push", "-u", "origin", branch, check=False)
        if r.returncode:
            print(r.stdout + r.stderr)
            print("Le push a échoué : vérifie ta connexion GitHub (git push à la main).")
            return r.returncode
        title = f"Ajouter les cartes : {names}"[:120]
        body = "Cartes publiées avec tools/push_tracks.py. L'index sera régénéré automatiquement après la fusion."
        if shutil.which("gh"):
            pr = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    "main",
                    "--head",
                    branch,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            print(pr.stdout + pr.stderr)
            if pr.returncode == 0:
                print("PR ouverte : fusionne-la sur GitHub une fois la CI verte.")
                return 0
        print(f"Branche poussée. Ouvre la PR ici : https://github.com/N4ole/LMU-dash/compare/main...{branch}?expand=1")
        return 0
    finally:
        git("switch", previous, check=False)


if __name__ == "__main__":
    sys.exit(main())
