import pytest

from strategy import RaceStats, compute_strategy, remaining_laps

WEAR = [1.0, 1.0, 1.0, 1.0]


def lap(stats: RaceStats, laps: int, fuel: float, last: float, *, in_pits=False, neutral=False, energy=0.9, wear=None):
    stats.update(laps, fuel, energy, wear or WEAR, in_pits, last, neutral)


# ---------------------------------------------------------------- RaceStats


def test_fuel_per_lap_from_clean_laps():
    s = RaceStats()
    lap(s, 0, 100.0, 0)
    lap(s, 1, 97.0, 100.0)
    lap(s, 2, 94.0, 100.0)
    assert s.fuel_per_lap == pytest.approx(3.0)
    assert s.avg_lap_time == pytest.approx(100.0)


def test_neutralised_lap_is_ignored():
    """Un tour couru (même en partie) sous SC/FCY ne compte ni dans la conso ni dans le temps moyen."""
    s = RaceStats()
    lap(s, 0, 100.0, 0)
    lap(s, 1, 97.0, 100.0)
    lap(s, 1, 96.0, 100.0, neutral=True)  # FCY déployé pendant le tour 2
    lap(s, 2, 95.0, 140.0)  # tour lent et peu gourmand : ne doit pas être appris
    lap(s, 3, 92.0, 100.0)
    assert s.fuel_hist == [3.0, 3.0]
    assert s.laptime_hist == [100.0, 100.0]


def test_pit_lap_not_counted_in_consumption():
    s = RaceStats()
    lap(s, 0, 30.0, 0)
    lap(s, 1, 27.0, 100.0)
    lap(s, 1, 26.0, 100.0, in_pits=True)
    lap(s, 2, 90.0, 130.0, in_pits=True)  # ravitaillement : la conso « négative » est ignorée
    assert s.fuel_hist == [3.0]


def test_pit_loss_is_measured():
    """(tour d'entrée + tour de sortie) - 2 x tour de référence."""
    s = RaceStats()
    lap(s, 0, 100.0, 0)
    lap(s, 1, 97.0, 100.0)
    lap(s, 2, 94.0, 100.0)
    lap(s, 2, 93.0, 100.0, in_pits=True)  # entrée aux stands pendant le tour 3
    lap(s, 3, 100.0, 130.0, in_pits=True)  # tour d'entrée : 130 s
    lap(s, 3, 100.0, 130.0)  # sortie des stands
    lap(s, 4, 97.0, 125.0)  # tour de sortie : 125 s
    assert s.pit_loss(60.0) == (60.0, False)  # pas encore de tour propre de référence
    lap(s, 5, 94.0, 100.0)  # premier tour propre : la fenêtre se ferme
    loss, measured = s.pit_loss(60.0)
    assert measured is True
    assert loss == pytest.approx(130 + 125 - 2 * 100)


def test_pit_loss_falls_back_to_setting():
    s = RaceStats()
    assert s.pit_loss(42.0) == (42.0, False)
    s.pit_loss_hist = [50.0]
    assert s.pit_loss(42.0, auto=False) == (42.0, False)
    assert s.pit_loss(42.0) == (50.0, True)


def test_pit_window_under_fcy_is_discarded():
    s = RaceStats()
    lap(s, 0, 100.0, 0)
    lap(s, 1, 97.0, 100.0)
    lap(s, 1, 96.0, 100.0, in_pits=True, neutral=True)  # arrêt sous FCY : perte non représentative
    lap(s, 2, 100.0, 150.0, in_pits=True, neutral=True)
    lap(s, 3, 97.0, 120.0)
    lap(s, 4, 94.0, 100.0)
    assert s.pit_loss_hist == []


def test_skipped_laps_reset_without_learning():
    s = RaceStats()
    lap(s, 0, 100.0, 0)
    lap(s, 3, 80.0, 100.0)  # reprise après coupure : 3 tours d'un coup
    assert s.fuel_hist == []
    assert s.laps == 3


def test_snapshot_restore_roundtrip_and_type_checks():
    s = RaceStats()
    lap(s, 0, 100.0, 0)
    lap(s, 1, 97.0, 100.0)
    snap = s.snapshot()
    r = RaceStats()
    r.restore(snap)
    assert r.snapshot() == snap
    r.restore({"laps": "x", "fuel_hist": "pas une liste", "had_pit": 1})
    assert r.laps is None and r.fuel_hist == [] and r.had_pit is False


# ---------------------------------------------------------------- tours restants


def test_remaining_laps_not_race():
    assert remaining_laps(
        is_race=False, max_laps=10, laps_done=0, lap_frac=0, time_remaining=100, time_into_lap=0, avg_lap=90
    ) == (0.0, 0)


def test_remaining_laps_lap_race():
    rem, n = remaining_laps(
        is_race=True, max_laps=20, laps_done=5, lap_frac=0.5, time_remaining=0, time_into_lap=0, avg_lap=100
    )
    assert rem == pytest.approx(14.5)
    assert n == 15


def test_remaining_laps_timed_race_counts_extra_lap():
    """Course au temps : on finit au premier passage de ligne APRÈS la fin du chrono."""
    rem, n = remaining_laps(
        is_race=True, max_laps=0, laps_done=10, lap_frac=0.3, time_remaining=950, time_into_lap=30, avg_lap=100
    )
    assert n == 10  # ceil((950 + 30) / 100)
    assert rem == pytest.approx(9.7)


def test_remaining_laps_timed_race_unknown_pace():
    assert remaining_laps(
        is_race=True, max_laps=0, laps_done=0, lap_frac=0, time_remaining=600, time_into_lap=0, avg_lap=0
    ) == (0.0, 0)


# ---------------------------------------------------------------- plan d'arrêts


def strat(**kw):
    base = dict(
        lap=10,
        remaining=20.0,
        fuel=30.0,
        capacity=90.0,
        fpl=3.0,
        ve=0.0,
        epl=0.0,
        wear_now=[],
        wear_pl=0.0,
        stint_lap=5,
        pit_loss=60.0,
    )
    base.update(kw)
    return compute_strategy(**base)


def test_strategy_unknown_without_data():
    assert strat(fpl=0.0) == {"known": False, "stintLap": 5}


def test_strategy_fuel_limited_one_stop():
    r = strat()
    assert r["known"] and r["limiting"] == "Carburant"
    assert r["pitIn"] == 9  # floor(10 - 0.5)
    assert r["pitLap"] == 18
    assert r["stops"] == 1
    assert r["fuelAdd"] == pytest.approx(34.5)  # (20 - 9 + 0.5) * 3
    assert r["status"] == "ok"
    assert r["timeCost"] == 60


def test_strategy_can_finish():
    r = strat(remaining=5.0)
    assert r["status"] == "finish" and r["stops"] == 0 and r["timeCost"] == 0


def test_strategy_box_now():
    r = strat(fuel=4.0)
    assert r["status"] == "box_now"


def test_strategy_tyres_limiting():
    r = strat(wear_now=[0.5, 0.6, 0.7, 0.8], wear_pl=0.05, tyre_min=0.25)
    assert r["limiting"] == "Pneus"
    assert r["pitIn"] == 4  # (0.5 - 0.25) / 0.05 = 5 tours, moins la marge


def test_strategy_energy_add_in_percent():
    r = strat(ve=0.4, epl=0.05, fuel=80.0)
    assert r["limiting"] == "Énergie"
    assert r["energyAdd"] is not None and 0 < r["energyAdd"] <= 100


def test_strategy_suggests_saving():
    r = strat(remaining=10.5, fuel=30.0)  # 10 tours de carburant pour 10,5 + marge
    assert r["save"] == {"resource": "Carburant", "pct": pytest.approx(9.1, abs=0.1)}


def test_strategy_uses_measured_pit_loss_flag():
    r = strat(pit_loss=48.4, pit_loss_measured=True)
    assert r["pitLoss"] == 48 and r["pitLossMeasured"] is True
