#!/usr/bin/env python3
"""Prépare l'aperçu d'une PR de cartes : un SVG par carte + un rapport Markdown (commentaire de PR).

    python tools/track_preview.py --input pr_tracks/ --out preview/ --image-url https://.../pr-12/abc123

Les fichiers d'entrée viennent d'une PR (données non fiables) : ils sont seulement lus comme JSON,
validés, et tout texte qui en provient est neutralisé avant d'être écrit dans le Markdown."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from track_svg import render_svg  # noqa: E402
from validate_tracks import ROOT, check_track, load  # noqa: E402

MARKER = "<!-- track-preview -->"
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.json$")


def safe_text(value, limit: int = 120) -> str:
    """Texte venant d'une PR -> sûr dans du Markdown (pas de HTML, de lien, ni de mention)."""
    text = re.sub(r"[\x00-\x1f`<>\[\]|*_~#@\\]", " ", str(value))[:limit].strip()
    return text or "?"


def pct(v) -> str:
    return f"{v * 100:.1f} %" if isinstance(v, (int, float)) and not isinstance(v, bool) else "?"


def describe(path: str, base_dir: str) -> dict:
    name = os.path.basename(path)
    info = {"name": name, "errors": [], "track": None, "existing": os.path.exists(os.path.join(base_dir, name))}
    if not SAFE_NAME.match(name):
        info["errors"].append("nom de fichier refusé (lettres, chiffres, . _ - uniquement)")
        return info
    try:
        o = load(path)
    except (OSError, ValueError) as e:
        info["errors"].append(f"JSON illisible : {safe_text(e)}")
        return info
    info["track"] = o if isinstance(o, dict) else None
    info["errors"] = check_track(o, name)
    return info


def report(items: list[dict], image_url: str | None, deleted: list[str]) -> str:
    ok = sum(1 for i in items if not i["errors"])
    lines = [MARKER, "## 🗺️ Aperçu des cartes", ""]
    if items:
        lines.append(f"**{ok}/{len(items)}** carte(s) valide(s).")
    if deleted:
        lines.append("")
        lines.append("⚠️ Cartes **supprimées** par cette PR : " + ", ".join(f"`{safe_text(d)}`" for d in deleted))
    for i in items:
        t = i["track"] if isinstance(i["track"], dict) else {}
        status = "✅ valide" if not i["errors"] else "❌ refusée"
        kind = "mise à jour d'une carte existante" if i["existing"] else "nouvelle carte"
        lines += ["", f"### `{safe_text(i['name'])}` — {status} ({kind})", ""]
        if image_url and t and not any(e.startswith(("JSON", "nom de fichier")) for e in i["errors"]):
            stem = i["name"][: -len(".json")]
            lines.append(f'<img src="{image_url}/{stem}.svg" width="360" alt="tracé">')
            lines.append("")
        pts = t.get("pts") if isinstance(t.get("pts"), list) else []
        filled = sum(1 for p in pts if p)
        lines.append(f"- Circuit : `{safe_text(t.get('key', '?'))}`")
        lines.append(f"- Points : {filled}/{len(pts)}")
        sec = t.get("sectors")
        if isinstance(sec, list) and len(sec) == 2:
            lines.append(f"- Secteurs : S1 → {pct(sec[0])}, S2 → {pct(sec[1])}")
        else:
            lines.append("- Secteurs : absents")
        for e in i["errors"]:
            lines.append(f"- ❌ {safe_text(e, 300)}")
    lines += ["", "<sub>Généré automatiquement à partir des fichiers de la PR (`tools/track_preview.py`).</sub>"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="dossier des cartes de la PR")
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default=os.path.join(ROOT, "tracks"), help="cartes déjà publiées")
    ap.add_argument("--image-url", default=None, help="URL publique du dossier où seront poussés les SVG")
    ap.add_argument("--deleted", nargs="*", default=[])
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    files = sorted(f for f in os.listdir(a.input) if f.endswith(".json"))
    items = [describe(os.path.join(a.input, f), a.base) for f in files]
    for i in items:
        if isinstance(i["track"], dict) and SAFE_NAME.match(i["name"]):
            with open(os.path.join(a.out, i["name"][: -len(".json")] + ".svg"), "w", encoding="utf-8") as fh:
                fh.write(render_svg(i["track"]))
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(report(items, a.image_url, a.deleted))
    print(json.dumps({"files": len(items), "valid": sum(1 for i in items if not i["errors"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
