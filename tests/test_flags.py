import pytest

import flags
from flags import FlagWatch, sector_of
from store import Settings

LENGTH = 3000.0
BOUNDS = [0.33, 0.66]


@pytest.fixture
def settings(tmp_path):
    return Settings(str(tmp_path / "settings.json"))


@pytest.fixture
def clock(monkeypatch):
    """Horloge contrôlée : FlagWatch n'enregistre qu'un vote toutes les 5 s."""
    now = [1000.0]
    monkeypatch.setattr(flags.time, "monotonic", lambda: now[0])
    return now


def payload(*, sector_flags, phase=5, yellow=0, my_d=100.0, my_sector=1, others=(), flag=0):
    rows = [{"me": True, "d": my_d, "spd": 200}] + [dict(r) for r in others]
    return {
        "session": {"trackLength": LENGTH, "phase": phase, "yellow": yellow, "sectorFlags": sector_flags},
        "timing": {"sector": my_sector, "flag": flag},
        "standings": rows,
        "car": {"inPits": False},
    }


def test_sector_of():
    assert sector_of(0.1, BOUNDS) == 1
    assert sector_of(0.5, BOUNDS) == 2
    assert sector_of(0.9, BOUNDS) == 3
    assert sector_of(0.5, None) is None
    assert sector_of(0.5, [None, 0.6]) is None


def test_learns_quirk_mapping(settings, clock):
    """Le jeu met le jaune de S1 dans mSectorFlag[1] : 3 votes concordants suffisent pour l'apprendre."""
    fw = FlagWatch(settings)
    assert fw.mapping() == "direct"
    stopped = [{"d": 500.0, "spd": 0, "name": "X"}]  # voiture arrêtée en S1
    for _ in range(3):
        fw.update(payload(sector_flags=[0, 1, 0], others=stopped), BOUNDS)
        clock[0] += 6
    assert fw.votes == {"direct": 0, "quirk": 3}
    assert fw.mapping() == "quirk"
    assert settings.get()["flagMap"] == "quirk"  # mémorisé dans settings.json
    r = fw.update(payload(sector_flags=[0, 1, 0], others=stopped), BOUNDS)
    assert r["local"] == [True, False, False]
    items = {i["id"]: i for i in r["items"]}
    assert items["y1"]["level"] == 2  # jaune dans MON secteur
    assert "hazard" in items


def test_learns_direct_mapping(settings, clock):
    settings.update({"flagMap": "quirk"})
    fw = FlagWatch(settings)
    stopped = [{"d": 1500.0, "spd": 0}]  # voiture arrêtée en S2, jaune dans mSectorFlag[1]
    for _ in range(3):
        fw.update(payload(sector_flags=[0, 1, 0], others=stopped), BOUNDS)
        clock[0] += 6
    assert fw.mapping() == "direct"


def test_votes_are_rate_limited(settings, clock):
    fw = FlagWatch(settings)
    stopped = [{"d": 500.0, "spd": 0}]
    for _ in range(10):
        fw.update(payload(sector_flags=[0, 1, 0], others=stopped), BOUNDS)  # même instant
    assert fw.votes["quirk"] == 1
    assert fw.mapping() == "direct"


def test_ambiguous_situations_do_not_vote(settings, clock):
    fw = FlagWatch(settings)
    two = [{"d": 500.0, "spd": 0}, {"d": 1500.0, "spd": 0}]
    fw.update(payload(sector_flags=[0, 1, 0], others=two), BOUNDS)  # deux voitures arrêtées
    clock[0] += 6
    fw.update(payload(sector_flags=[1, 1, 0], others=[two[0]]), BOUNDS)  # deux secteurs jaunes
    assert fw.votes == {"direct": 0, "quirk": 0}


def test_fcy_red_and_blue(settings):
    fw = FlagWatch(settings)
    r = fw.update(payload(sector_flags=[0, 0, 0], yellow=2), BOUNDS)
    assert r["fcy"] is True
    assert r["items"][0]["text"] == "FCY — stands fermés"
    r = fw.update(payload(sector_flags=[0, 0, 0], phase=7), BOUNDS)
    assert r["items"][0]["kind"] == "red"
    r = fw.update(payload(sector_flags=[0, 0, 0], flag=6), BOUNDS)
    assert any(i["id"] == "blue" for i in r["items"])


def test_yellow_next_sector_and_elsewhere(settings):
    fw = FlagWatch(settings)
    r = fw.update(payload(sector_flags=[0, 1, 1], my_sector=1), BOUNDS)
    assert {i["id"]: i["level"] for i in r["items"]} == {"y2": 1, "y3": 0}


def test_hazard_ahead_across_the_line(settings):
    fw = FlagWatch(settings)
    r = fw.update(payload(sector_flags=[0, 0, 0], my_d=2900.0, others=[{"d": 200.0, "spd": 5}]), BOUNDS)
    hz = next(i for i in r["items"] if i["id"] == "hazard")
    assert hz["text"].startswith("Voiture à l'arrêt à 300 m")
    assert hz["level"] == 2
