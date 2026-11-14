import json
import os

import pytest
from helpers import BINS, circle_track

from store import DEFAULTS, Profiles, Settings, TrackStore, read_json, slug, validate_track

# ---------------------------------------------------------------- validate_track


def test_valid_track():
    assert validate_track(circle_track())
    assert validate_track(circle_track(sectors=None))  # secteurs facultatifs pour l'app
    assert validate_track(circle_track(sectors=(0.3, None)))
    assert validate_track(circle_track(missing=10))  # 350/360 points = 97,2 %


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.update(pts=o["pts"][:-1]),  # 359 points
        lambda o: o.update(pts=o["pts"] + [[0, 0]]),  # 361 points
        lambda o: o.update(key=""),
        lambda o: o.update(key="x" * 121),
        lambda o: o.update(key=42),
        lambda o: o.pop("key"),
        lambda o: o["pts"].__setitem__(5, [1, 2, 3]),
        lambda o: o["pts"].__setitem__(5, [True, 2]),  # booléen déguisé en nombre
        lambda o: o["pts"].__setitem__(5, [100000, 2]),  # coordonnée absurde
        lambda o: o["pts"].__setitem__(5, ["1", 2]),
        lambda o: o["pts"].__setitem__(5, {"x": 1}),
        lambda o: o.update(sectors=[0.6, 0.3]),  # décroissants
        lambda o: o.update(sectors=[0.3, 0.3]),
        lambda o: o.update(sectors=[0.01, 0.5]),  # hors 2 %..98 %
        lambda o: o.update(sectors=[0.3, 0.99]),
        lambda o: o.update(sectors=[0.3]),
        lambda o: o.update(sectors="0.3,0.6"),
    ],
)
def test_invalid_tracks(mutate):
    o = circle_track()
    mutate(o)
    assert not validate_track(o)


def test_invalid_track_too_many_holes():
    assert not validate_track(circle_track(missing=11))  # 349/360 < 97 %


@pytest.mark.parametrize("obj", [None, [], "x", 3, {"key": "a", "pts": "nope"}])
def test_invalid_track_types(obj):
    assert not validate_track(obj)


# ---------------------------------------------------------------- TrackStore.adopt


def test_adopt_new_track(tmp_path):
    ts = TrackStore(str(tmp_path))
    assert ts.adopt(circle_track("Spa"))
    saved = read_json(str(tmp_path / "tracks" / "Spa.json"))
    assert saved["shared"] is True
    assert len(saved["pts"]) == BINS and saved["sectors"] == [0.33, 0.66]
    assert not ts.adopt(circle_track("Spa"))  # déjà complète : rien à apporter
    assert ts.shareable() == []  # une carte reçue n'est pas proposée au partage


def test_adopt_rejects_invalid(tmp_path):
    ts = TrackStore(str(tmp_path))
    bad = circle_track("Spa")
    bad["pts"] = bad["pts"][:100]
    assert not ts.adopt(bad)
    assert not os.path.exists(tmp_path / "tracks" / "Spa.json")


def test_adopt_only_sectors_keeps_local_points(tmp_path):
    ts = TrackStore(str(tmp_path))
    local = circle_track("Monza", radius=800, sectors=None)
    path = tmp_path / "tracks" / "Monza.json"
    path.write_text(json.dumps({"key": "Monza", "pts": local["pts"], "sectors": [None, None]}), encoding="utf-8")
    assert ts.adopt(circle_track("Monza", radius=500, sectors=(0.4, 0.7)))
    saved = read_json(str(path))
    assert saved["pts"] == local["pts"]  # notre tracé est conservé
    assert saved["sectors"] == [0.4, 0.7]


def test_adopt_does_not_overwrite_learned_sectors(tmp_path):
    ts = TrackStore(str(tmp_path))
    path = tmp_path / "tracks" / "Monza.json"
    path.write_text(json.dumps(circle_track("Monza", sectors=(0.3, 0.6))), encoding="utf-8")
    assert not ts.adopt(circle_track("Monza", sectors=(0.4, 0.7)))
    assert read_json(str(path))["sectors"] == [0.3, 0.6]


def test_adopt_key_cannot_escape_folder(tmp_path):
    ts = TrackStore(str(tmp_path))
    assert ts.adopt(circle_track("../../evil"))
    files = os.listdir(tmp_path / "tracks")
    assert files == ["evil.json"]
    assert not os.path.exists(tmp_path.parent / "evil.json")


def test_shareable_and_export(tmp_path):
    ts = TrackStore(str(tmp_path))
    (tmp_path / "tracks" / "Le_Mans.json").write_text(json.dumps(circle_track("Le Mans")), encoding="utf-8")
    assert ts.shareable() == [{"key": "Le Mans", "file": "Le_Mans.json"}]
    out = ts.export("Le Mans")
    assert out["v"] == 1 and out["key"] == "Le Mans" and validate_track(out)


def test_slug():
    assert slug("Circuit de la Sarthe") == "Circuit_de_la_Sarthe"
    assert slug("..") == "x"
    assert slug("../../etc/passwd") == "etc_passwd"
    assert len(slug("a" * 200)) == 80


# ---------------------------------------------------------------- Settings


def test_settings_defaults_and_persistence(tmp_path):
    p = str(tmp_path / "settings.json")
    s = Settings(p)
    assert s.get() == DEFAULTS
    s.update({"pitLoss": 45, "sound": 1})
    again = Settings(p)
    assert again.get()["pitLoss"] == 45.0 and again.get()["sound"] is True


@pytest.mark.parametrize(
    "patch,key,expected",
    [
        ({"pitLoss": 1}, "pitLoss", 10.0),
        ({"pitLoss": 9999}, "pitLoss", 300.0),
        ({"pitLoss": "abc"}, "pitLoss", 60.0),
        ({"pitLoss": float("nan")}, "pitLoss", 60.0),
        ({"pitLoss": None}, "pitLoss", 60.0),
        ({"tyreMin": 99}, "tyreMin", 70.0),
        ({"margin": -1}, "margin", 0.0),
        ({"volume": 5}, "volume", 1.0),
        ({"stintMaxMin": 1e9}, "stintMaxMin", 600.0),
        ({"flagMap": "n'importe quoi"}, "flagMap", "direct"),
        ({"flagMap": "quirk"}, "flagMap", "quirk"),
        ({"classFilter": "x" * 100}, "classFilter", "x" * 40),
        ({"classFilter": 12}, "classFilter", "ALL"),
    ],
)
def test_settings_sanitising(tmp_path, patch, key, expected):
    s = Settings(str(tmp_path / "settings.json"))
    assert s.update(patch)[key] == expected


def test_settings_ignores_unknown_and_nested_junk(tmp_path):
    s = Settings(str(tmp_path / "settings.json"))
    r = s.update(
        {
            "__proto__": 1,
            "evil": "x",
            "alerts": {"fuel": False, "inconnue": True},
            "tracks": {"Spa": {"rot": 17, "flip": "oui"}, "Monza": "pas un dict"},
            "tyreMinByCompound": {"Soft": 30, "Hard": "x", "Wet": 500},
        }
    )
    assert "evil" not in r and "__proto__" not in r
    assert r["alerts"]["fuel"] is False and "inconnue" not in r["alerts"]
    assert r["tracks"] == {"Spa": {"rot": 3, "flip": True}}
    assert r["tyreMinByCompound"] == {"Soft": 30.0, "Hard": 25.0, "Wet": 70.0}


def test_settings_corrupted_file(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{pas du json", encoding="utf-8")
    assert Settings(str(p)).get() == DEFAULTS
    p.write_text("[1, 2]", encoding="utf-8")
    assert Settings(str(p)).get() == DEFAULTS


def test_tyre_min_by_compound(tmp_path):
    s = Settings(str(tmp_path / "settings.json"))
    s.update({"tyreMin": 20, "tyreMinByCompound": {"Soft": 30}})
    assert s.tyre_min("soft") == pytest.approx(0.30)
    assert s.tyre_min("Hard") == pytest.approx(0.20)
    assert s.tyre_min(None) == pytest.approx(0.20)


def test_settings_rebind(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    s = Settings(str(a))
    s.update({"pitLoss": 30})
    s.rebind(str(b))
    assert s.get()["pitLoss"] == 60.0
    s.rebind(str(a))
    assert s.get()["pitLoss"] == 30.0


# ---------------------------------------------------------------- Profiles


def test_profiles_fresh(tmp_path):
    p = Profiles(str(tmp_path))
    assert p.info() == {"active": "Joueur", "profiles": ["Joueur"]}
    assert os.path.isdir(tmp_path / "profiles" / "Joueur")
    assert read_json(str(tmp_path / "profiles.json")) == {"active": "Joueur", "profiles": ["Joueur"]}


def test_profiles_migrate_legacy_data(tmp_path):
    """Les données d'avant les profils (data/settings.json...) sont reprises dans « Joueur »."""
    (tmp_path / "settings.json").write_text('{"pitLoss": 42}', encoding="utf-8")
    (tmp_path / "records.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "a.csv").write_text("x", encoding="utf-8")
    (tmp_path / "tracks").mkdir()  # les cartes restent communes
    p = Profiles(str(tmp_path))
    dst = tmp_path / "profiles" / "Joueur"
    assert (dst / "settings.json").exists() and not (tmp_path / "settings.json").exists()
    assert (dst / "records.json").exists()
    assert (dst / "sessions" / "a.csv").exists()
    assert (tmp_path / "tracks").is_dir()
    assert Settings(os.path.join(p.path(), "settings.json")).get()["pitLoss"] == 42.0


def test_profiles_existing_meta_not_migrated_again(tmp_path):
    Profiles(str(tmp_path)).create("Alice")
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")
    p = Profiles(str(tmp_path))
    assert p.names == ["Joueur", "Alice"]
    assert (tmp_path / "settings.json").exists()


def test_profiles_create_switch_delete(tmp_path):
    p = Profiles(str(tmp_path))
    assert p.create("  Alice   Martin ")
    assert "Alice Martin" in p.names
    assert not p.create("alice martin")  # doublon (insensible à la casse)
    assert not p.create("   ")
    assert p.switch("Alice Martin") and p.active == "Alice Martin"
    assert not p.delete("Alice Martin")  # profil actif
    assert not p.delete("Inconnu")
    assert p.switch("Joueur")
    assert p.delete("Alice Martin")
    assert not os.path.exists(tmp_path / "profiles" / "Alice_Martin")
    assert not p.delete("Joueur")  # dernier profil


def test_profiles_name_length(tmp_path):
    p = Profiles(str(tmp_path))
    p.create("x" * 100)
    assert "x" * 30 in p.names


@pytest.mark.parametrize("name", ["..", "../..", "../../escape", "..\\..\\escape", "/etc", "C:\\Windows", "a/../../b"])
def test_profiles_path_traversal(tmp_path, name):
    root = tmp_path / "data"
    p = Profiles(str(root))
    p.create(name)
    profiles_dir = os.path.realpath(root / "profiles")
    for n in p.names:
        path = os.path.realpath(p.path(n))
        assert os.path.commonpath([path, profiles_dir]) == profiles_dir
        assert path != profiles_dir
    # supprimer ne peut jamais effacer en dehors de profiles/
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
    for n in list(p.names):
        if n != p.active:
            p.delete(n)
    assert (tmp_path / "keep.txt").exists()
    assert os.path.isdir(root / "profiles" / "Joueur")
