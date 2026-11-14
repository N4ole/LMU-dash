"""Outils de la CI des cartes : validation, rendu SVG, aperçu de PR."""

import json
import os
import sys
import xml.etree.ElementTree as ET

import pytest
from helpers import circle_track

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import track_preview  # noqa: E402
import validate_tracks  # noqa: E402
from track_svg import SECTOR_COLORS, render_svg  # noqa: E402


def write(folder, name, obj):
    path = folder / name
    path.write_text(json.dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------- validate_tracks


def test_validate_ok(tmp_path):
    assert validate_tracks.check_file(write(tmp_path, "Spa.json", circle_track("Spa"))) == []


@pytest.mark.parametrize(
    "name,obj,expected",
    [
        ("Autre.json", circle_track("Spa"), "nom attendu : Spa.json"),
        ("Spa.json", circle_track("Spa", sectors=None), "secteurs manquants"),
        ("Spa.json", circle_track("Spa", sectors=(0.3, None)), "secteurs manquants"),
        ("Spa.json", {"key": "Spa"}, "carte invalide"),
        ("Spa.json", "{pas du json", "illisible"),
    ],
)
def test_validate_errors(tmp_path, name, obj, expected):
    errors = validate_tracks.check_file(write(tmp_path, name, obj))
    assert any(expected in e for e in errors), errors


def test_validate_too_big(tmp_path):
    path = write(tmp_path, "Spa.json", " " * (validate_tracks.MAX_BYTES + 1))
    assert "trop gros" in validate_tracks.check_file(path)[0]


def test_validate_main_exit_code(tmp_path):
    good = write(tmp_path, "Spa.json", circle_track("Spa"))
    bad = write(tmp_path, "Monza.json", circle_track("Spa"))
    assert validate_tracks.main([good]) == 0
    assert validate_tracks.main([good, bad]) == 1


def test_repository_tracks_are_valid():
    """Les cartes déjà publiées dans tracks/ passent la validation."""
    assert validate_tracks.main([]) == 0


# ---------------------------------------------------------------- SVG


def test_svg_is_well_formed_with_sector_colors():
    svg = render_svg(circle_track("Spa <test>"))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    for color in SECTOR_COLORS:
        assert color in svg
    assert "Spa &lt;test&gt;" in svg  # le nom est échappé


def test_svg_without_sectors_and_with_holes():
    ET.fromstring(render_svg(circle_track(sectors=None, missing=10)))
    assert SECTOR_COLORS[0] not in render_svg(circle_track(sectors=None))


def test_svg_empty_track():
    assert "Carte vide" in render_svg({"key": "x", "pts": [None] * 360})


# ---------------------------------------------------------------- aperçu de PR


def test_preview_report(tmp_path):
    pr = tmp_path / "pr"
    pr.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    write(base, "Monza.json", circle_track("Monza"))
    write(pr, "Spa.json", circle_track("Spa"))
    write(pr, "Monza.json", circle_track("Monza"))
    write(pr, "Bad.json", circle_track("@everyone `rm -rf` <script>"))
    out = tmp_path / "out"
    rc = track_preview.main(
        [
            "--input",
            str(pr),
            "--out",
            str(out),
            "--base",
            str(base),
            "--image-url",
            "https://x/y",
            "--deleted",
            "Old.json",
        ]
    )
    assert rc == 0
    md = (out / "report.md").read_text(encoding="utf-8")
    assert md.startswith(track_preview.MARKER)
    assert "**2/3** carte(s) valide(s)" in md
    assert "`Spa.json` — ✅ valide (nouvelle carte)" in md
    assert "`Monza.json` — ✅ valide (mise à jour d'une carte existante)" in md
    assert "❌ refusée" in md and "nom attendu" in md
    assert '<img src="https://x/y/Spa.svg"' in md
    assert "`Old.json`" in md
    # aucun texte venant de la PR ne peut injecter de HTML, de mention ou casser le Markdown
    assert "<script>" not in md and "@everyone" not in md and "`rm" not in md
    assert sorted(os.listdir(out)) == ["Bad.svg", "Monza.svg", "Spa.svg", "report.md"]


def test_preview_rejects_strange_file_names(tmp_path):
    info = track_preview.describe(write(tmp_path, "a b.json", circle_track("a b")), str(tmp_path))
    assert info["errors"] and "nom de fichier" in info["errors"][0]


@pytest.mark.parametrize("text", ["<img src=x onerror=alert(1)>", "[lien](http://evil)", "@N4ole", "a\nb|c"])
def test_safe_text(text):
    out = track_preview.safe_text(text)
    for bad in "<>[]@\n|":
        assert bad not in out


# ---------------------------------------------------------------- site GitHub Pages


def test_build_site(tmp_path):
    import build_site

    tracks = tmp_path / "tracks"
    tracks.mkdir()
    write(tracks, "Spa.json", circle_track("Spa <b>"))
    write(tracks, "Bad.json", {"key": "Bad"})
    index = {
        "v": 1,
        "tracks": [{"key": "Spa", "file": "Spa.json"}, {"key": "x", "file": "../../etc"}, {"file": "Bad.json"}],
    }
    write(tracks, "index.json", index)
    out = tmp_path / "site"
    assert build_site.build(str(out), tracks_dir=str(tracks)) == 1
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "1 circuit(s) disponible(s)" in html
    assert "Spa &lt;b&gt;" in html and "<!-- TRACKS -->" not in html
    assert (out / "tracks" / "Spa_b.svg").exists()
    assert (out / "screenshot.png").exists() and (out / ".nojekyll").exists()


def test_build_site_without_tracks(tmp_path):
    import build_site

    assert build_site.build(str(tmp_path / "site"), tracks_dir=str(tmp_path)) == 0
    assert "Aucun circuit partagé" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
