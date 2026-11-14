"""Petits constructeurs de données partagés par les tests."""

from __future__ import annotations

import math

BINS = 360


def circle_track(key: str = "Circuit Test", radius: float = 500.0, sectors=(0.33, 0.66), missing: int = 0) -> dict:
    """Carte valide : 360 points sur un cercle (périmètre ≈ 3,1 km)."""
    pts: list = [
        [round(radius * math.cos(2 * math.pi * i / BINS)), round(radius * math.sin(2 * math.pi * i / BINS))]
        for i in range(BINS)
    ]
    for i in range(missing):
        pts[i * 7 % BINS] = None
    return {"v": 1, "key": key, "pts": pts, "sectors": list(sectors) if sectors is not None else None}
