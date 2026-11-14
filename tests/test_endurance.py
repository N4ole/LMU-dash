import csv
import io

import pytest

from endurance import Endurance, fmt_clock, fmt_lap

# Chronologie simulée (1 s par lecture, comme le serveur qui lit en continu) :
#   tours bouclés à 100, 200, 300 (arrêt de 250 à 320 pendant le tour 3) et 420 s,
#   le pilote A est remplacé par B à l'arrêt (t = 310).
LAP_ENDS = [100, 200, 300, 420]


def payload(et: float, *, driver: str, in_pits: bool, neutral: bool = False, invalid: bool = False) -> dict:
    done = [x for x in LAP_ENDS if x <= et]
    last = (done[-1] - (done[-2] if len(done) > 1 else 0)) if done else 0
    return {
        "session": {"elapsed": et, "neutral": neutral},
        "car": {"driver": driver, "inPits": in_pits, "inGarage": False},
        "timing": {"laps": len(done), "last": last, "invalid": invalid},
        "energy": {"fuel": 50.0 - len(done) * 3.1},
        "tyres": {"wheels": [{"wear": 0.9}, {"wear": 0.85}, {"wear": 0.95}, {"wear": 0.9}]},
    }


def run_race(endu: Endurance, until: int = 449) -> None:
    for et in range(0, until + 1):
        endu.update(payload(float(et), driver="A" if et < 310 else "B", in_pits=250 <= et < 320))


@pytest.fixture
def endu() -> Endurance:
    e = Endurance()
    run_race(e)
    return e


def test_stint_closed_at_pit_exit(endu):
    assert len(endu.stints) == 1
    s = endu.stints[0]
    assert s["driver"] == "A"
    assert s["laps"] == 3  # le tour d'entrée appartient au relais
    assert s["firstLap"] == 1
    assert s["dur"] == pytest.approx(250.0)  # de 0 à l'entrée aux stands
    assert s["best"] == pytest.approx(100.0)


def test_driver_change_attributes_time_and_laps(endu):
    assert endu.driver == "B"
    assert endu.drivers["A"]["total"] == pytest.approx(310.0)
    assert endu.drivers["B"]["total"] == pytest.approx(139.0)
    assert [r["driver"] for r in endu.laps] == ["A", "A", "A", "B"]
    summary = endu.summary(449.0, False)
    assert summary["driver"] == "B"
    assert summary["stintNo"] == 2
    assert summary["stintLaps"] == 1
    assert summary["drivers"] == 2


def test_pit_laps_are_flagged_and_excluded(endu):
    assert [r["pit"] for r in endu.laps] == [False, False, True, True]  # tour d'entrée + tour de sortie
    h = endu.history(449.0)
    assert h["best"] == pytest.approx(100.0)
    assert h["avg"] == pytest.approx(100.0)
    assert h["stints"][-1]["current"] is True


def test_neutralised_lap_not_clean():
    e = Endurance()
    for et in range(0, 201):
        e.update(payload(float(et), driver="A", in_pits=False, neutral=150 <= et < 160))
    assert [r["neutral"] for r in e.laps] == [False, True]
    assert e.cur["times"] == [100]


def test_session_restart_resets():
    e = Endurance()
    run_race(e, 150)
    e.update(payload(10.0, driver="A", in_pits=False))  # chrono de session reparti en arrière
    assert e.laps == [] and e.stints == []


def test_laps_csv(endu):
    rows = list(csv.reader(io.StringIO(endu.laps_csv()), delimiter=";"))
    assert rows[0][:4] == ["tour", "temps_s", "temps", "pilote"]
    assert len(rows) == 1 + 4
    assert rows[1][1] == "100,000"  # virgule décimale (Excel FR)
    assert rows[1][2] == "1:40.000"
    assert rows[4][3] == "B"


def test_stints_csv(endu):
    rows = list(csv.reader(io.StringIO(endu.stints_csv(449.0)), delimiter=";"))
    assert rows[0][0] == "relais"
    assert [r[1] for r in rows[1:]] == ["A", "B"]
    assert rows[1][5] == "0:04:10"


def test_to_dict_roundtrip(endu):
    d = endu.to_dict()
    r = Endurance()
    r.from_dict(d)
    assert r.to_dict() == d
    r.from_dict({"drivers": "pas un dict"})  # sauvegarde corrompue : on repart de zéro
    assert r.laps == [] and r.drivers == {}


def test_formatters():
    assert fmt_lap(None) == "" and fmt_lap(0) == ""
    assert fmt_lap(83.456) == "1:23.456"
    assert fmt_clock(3725) == "1:02:05"
    assert fmt_clock(-5) == "0:00:00"
