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
    write(base, "Monza.json", circle_track("Monza", radius=600))
    write(pr, "Spa.json", circle_track("Spa"))
    write(pr, "Monza.json", circle_track("Monza", radius=650))  # mise à jour du tracé
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
    assert "Longueur de la boucle : 3.15 km" in md


def test_preview_flags_resubmitted_identical_track(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    write(base, "Spa.json", circle_track("Spa"))
    info = track_preview.describe(write(tmp_path, "Spa.json", circle_track("Spa")), str(base))
    assert info["existing"] and info["errors"] == ["doublon exact de Spa.json"]


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


# ---------------------------------------------------------------- validation stricte et schéma


def demo_track():
    from readers import DemoReader

    pts = [[round(v) for v in DemoReader.track_xy(i / 360)] for i in range(360)]
    return {"v": 1, "key": "Circuit de la Sarthe", "pts": pts, "sectors": [0.31, 0.68]}


@pytest.mark.parametrize("track", [circle_track("Spa"), circle_track("Spa", missing=10), demo_track()])
def test_strict_accepts_real_tracks(tmp_path, track):
    from store import slug

    path = write(tmp_path, slug(track["key"]) + ".json", track)
    assert validate_tracks.check_file(path, strict=True, schema=True) == []


def broken(**changes):
    o = circle_track("Spa")
    o.update(changes)
    return o


def spike():
    o = circle_track("Spa")
    o["pts"][100] = [5000, 5000]
    return o


@pytest.mark.parametrize(
    "track,expected",
    [
        (broken(shared=True), "champs inattendus : shared"),
        (broken(v=2), "version de format"),
        (circle_track("Spa", radius=100), "longueur de boucle peu plausible : 0.6 km"),
        (circle_track("Spa", radius=6000), "longueur de boucle peu plausible : 37.7 km"),
        (spike(), "point(s) aberrant(s)"),
        (circle_track("Spa", sectors=(0.03, 0.5)), "secteur trop court (3.0 %"),
        (circle_track("Spa", sectors=(0.5, 0.97)), "secteur trop court (3.0 %"),
    ],
)
def test_strict_rejects(tmp_path, track, expected):
    path = write(tmp_path, "Spa.json", track)
    assert validate_tracks.check_file(path) == []  # l'application l'accepterait...
    errors = validate_tracks.check_file(path, strict=True)
    assert any(expected in e for e in errors), errors  # ... mais pas le dépôt


def test_strict_detects_exact_duplicate(tmp_path):
    a = write(tmp_path, "Spa.json", circle_track("Spa"))
    b = write(tmp_path, "Spa_2024.json", circle_track("Spa 2024"))  # même tracé, autre nom
    c = write(tmp_path, "Monza.json", circle_track("Monza", radius=700))
    others = [a, b, c]
    assert validate_tracks.check_file(b, strict=True, others=others) == ["doublon exact de Spa.json"]
    assert validate_tracks.check_file(c, strict=True, others=others) == []
    assert validate_tracks.main(["--strict", a, b, c]) == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.update(pts=o["pts"][:-1]),
        lambda o: o["pts"].__setitem__(3, [True, 1]),
        lambda o: o["pts"].__setitem__(3, [1, 2, 3]),
        lambda o: o["pts"].__setitem__(3, [100000, 1]),
        lambda o: o.update(sectors=[0.01, 0.5]),
        lambda o: o.update(sectors=None),
        lambda o: o.update(key=""),
        lambda o: o.update(extra=1),
        lambda o: o.pop("v"),
    ],
)
def test_schema_rejects(mutate):
    o = circle_track("Spa")
    mutate(o)
    assert validate_tracks.schema_errors(o)


def test_schema_accepts_export_format():
    assert validate_tracks.schema_errors(circle_track("Spa")) == []
    assert validate_tracks.schema_errors(circle_track("Spa", missing=10)) == []


def test_repository_tracks_strict():
    assert validate_tracks.main(["--strict", "--schema"]) == 0


def test_track_files_skip_index_and_schema(tmp_path):
    for name in ("index.json", "schema.json", "Spa.json"):
        write(tmp_path, name, {})
    assert [os.path.basename(f) for f in validate_tracks.track_files(str(tmp_path))] == ["Spa.json"]


# ---------------------------------------------------------------- index et publication


def test_build_index(tmp_path):
    import build_index

    write(tmp_path, "Spa.json", circle_track("Spa"))
    write(tmp_path, "Bad.json", {"key": "Bad"})
    write(tmp_path, "schema.json", {"type": "object"})
    write(tmp_path, "index.json", {"v": 1, "tracks": []})
    assert build_index.build(str(tmp_path)) == [{"key": "Spa", "file": "Spa.json"}]


def test_push_tracks_dry_run(tmp_path, monkeypatch, capsys):
    import push_tracks

    data = tmp_path / "data" / "tracks"
    data.mkdir(parents=True)
    write(data, "Nouveau.json", {**circle_track("Circuit inédit"), "shared": False, "saved": 1})
    write(data, "Incomplet.json", circle_track("Incomplet", sectors=(0.3, None)))
    monkeypatch.setattr(sys, "argv", ["push_tracks.py", "--data", str(tmp_path / "data"), "--dry-run"])
    assert push_tracks.main() == 0
    out = capsys.readouterr().out
    assert "+ Circuit inédit" in out
    assert "Incomplet.json ignorée" in out
