#!/usr/bin/env python3
"""Dessine une carte de circuit (tracks/*.json) en SVG, comme dans le dashboard :
tracé de 360 points, secteurs S1 bleu / S2 violet / S3 vert, repère de ligne de départ.

    python tools/track_svg.py tracks/Spa.json > spa.svg
"""

from __future__ import annotations

import json
import sys
from html import escape

BINS = 360
SECTOR_COLORS = ("#4aa8ff", "#b46bff", "#32d27b")
BG_COLOR = "#2a323d"
NEUTRAL_COLOR = "#566273"
TEXT_COLOR = "#e8edf2"


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _points(track: dict) -> list:
    """Points [x, -z] (même orientation que le dashboard), None pour les trous."""
    out = []
    for p in (track.get("pts") or [])[:BINS]:
        if isinstance(p, list) and len(p) == 2 and _num(p[0]) and _num(p[1]):
            out.append((float(p[0]), -float(p[1])))
        else:
            out.append(None)
    return out


def _bounds(sectors) -> tuple[int, int] | None:
    if not (isinstance(sectors, list) and len(sectors) == 2 and all(_num(v) for v in sectors)):
        return None
    a, b = round(sectors[0] * BINS), round(sectors[1] * BINS)
    return (a, b) if 0 < a < b < BINS else None


def render_svg(track: dict, size: int = 360, pad: int = 18, title: str | None = None) -> str:
    pts = _points(track)
    have = [p for p in pts if p]
    label = escape(str(title if title is not None else track.get("key", "")))
    if len(have) < 8:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<rect width="100%" height="100%" fill="#10141a"/><text x="50%" y="50%" fill="{TEXT_COLOR}" '
            f'font-family="sans-serif" font-size="14" text-anchor="middle">Carte vide</text></svg>'
        )
    minx, maxx = min(p[0] for p in have), max(p[0] for p in have)
    miny, maxy = min(p[1] for p in have), max(p[1] for p in have)
    bw, bh = max(1.0, maxx - minx), max(1.0, maxy - miny)
    sc = min((size - 2 * pad) / bw, (size - 2 * pad) / bh)
    ox = (size - bw * sc) / 2 - minx * sc
    oy = (size - bh * sc) / 2 - miny * sc

    def xy(p) -> str:
        return f"{p[0] * sc + ox:.1f},{p[1] * sc + oy:.1f}"

    def path(a: int, b: int) -> str:
        """Segments continus entre les indices a et b (inclus, b peut valoir BINS pour refermer la boucle)."""
        parts, cur = [], []
        for i in range(a, b + 1):
            p = pts[i % BINS]
            if p is None:
                if len(cur) > 1:
                    parts.append(cur)
                cur = []
            else:
                cur.append(p)
        if len(cur) > 1:
            parts.append(cur)
        return " ".join("M" + " L".join(xy(p) for p in seg) for seg in parts)

    bnd = _bounds(track.get("sectors"))
    ranges = [(0, bnd[0]), (bnd[0], bnd[1]), (bnd[1], BINS)] if bnd else [(0, BINS)]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'role="img" aria-label="{label}">',
        f"<title>{label}</title>",
        '<rect width="100%" height="100%" rx="12" fill="#10141a"/>',
        '<g fill="none" stroke-linejoin="round" stroke-linecap="round">',
        f'<path d="{path(0, BINS)}" stroke="{BG_COLOR}" stroke-width="10"/>',
    ]
    for i, (a, b) in enumerate(ranges):
        color = SECTOR_COLORS[i] if bnd else NEUTRAL_COLOR
        out.append(f'<path d="{path(a, b)}" stroke="{color}" stroke-width="3"/>')
    out.append("</g>")
    if bnd:
        for i, (a, b) in enumerate(ranges):
            edge = pts[a % BINS] if i > 0 else None
            mid = pts[((a + b) // 2) % BINS]
            if edge:
                x, y = xy(edge).split(",")
                out.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{TEXT_COLOR}"/>')
            if mid:
                x, y = xy(mid).split(",")
                out.append(
                    f'<text x="{x}" y="{float(y) - 12:.1f}" fill="{SECTOR_COLORS[i]}" font-family="sans-serif" '
                    f'font-size="12" font-weight="800" text-anchor="middle">S{i + 1}</text>'
                )
    start = next((p for p in pts if p), None)
    if start:
        x, y = (float(v) for v in xy(start).split(","))
        out.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" fill="{TEXT_COLOR}"/>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        sys.stdout.write(render_svg(json.load(f)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
