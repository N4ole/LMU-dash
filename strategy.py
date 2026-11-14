"""Calculs de stratégie : conso carburant/énergie, usure pneus, temps perdu aux stands,
tours restants et plan d'arrêts. Aucune dépendance au jeu : tout est testable seul."""
from __future__ import annotations

import math


def _avg(v: list[float]) -> float:
    return sum(v) / len(v) if v else 0.0


def _median(v: list[float]) -> float:
    s = sorted(v)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# --------------------------------------------------------------------------
# Mesures par tour
# --------------------------------------------------------------------------


class RaceStats:
    """Mesure, tour par tour : carburant, énergie, usure, temps au tour, temps perdu aux stands.

    - Un tour est ignoré s'il a été couru sous Safety Car / FCY (« neutralisé »).
    - Un tour avec passage aux stands n'est jamais compté dans la conso, mais sert à mesurer le
      temps perdu : (tour d'entrée + tour de sortie) - 2 x tour de référence.
    - Le changement de tour est détecté sur les tours TERMINÉS du scoring, pour lire un temps au
      tour cohérent (la télémétrie et le scoring ne sont pas rafraîchis en même temps).
    """

    KEEP = 5

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.laps: int | None = None
        self.start_fuel = 0.0
        self.start_energy = 0.0
        self.start_wear: list[float] = []
        self.had_pit = False
        self.dirty = False
        self.fuel_hist: list[float] = []
        self.energy_hist: list[float] = []
        self.laptime_hist: list[float] = []
        self.wear_hist: list[float] = []
        self.pit_acc: list[float] = []
        self.pit_acc_dirty = False
        self.pit_loss_hist: list[float] = []
        self.stint_start = 0

    # ---- mise à jour ----

    def _begin(self, laps: int, fuel: float, energy: float, wear: list[float], in_pits: bool, neutral: bool) -> None:
        self.laps, self.start_fuel, self.start_energy = laps, fuel, energy
        self.start_wear = list(wear)
        self.had_pit = in_pits
        self.dirty = neutral

    def update(self, laps: int, fuel: float, energy: float, wear: list[float], in_pits: bool,
               last_lap: float, neutral: bool) -> None:
        if self.laps is None or laps < self.laps:  # première lecture / retour garage / nouvelle session
            self._begin(laps, fuel, energy, wear, in_pits, neutral)
            self.stint_start = laps
            return
        if laps - self.laps > 1:  # tours manqués (reprise après coupure) : on repart de zéro sans rien apprendre
            self._begin(laps, fuel, energy, wear, in_pits, neutral)
            self.pit_acc, self.pit_acc_dirty = [], False
            return
        if in_pits:
            self.had_pit = True
            self.stint_start = laps
        if neutral:
            self.dirty = True
        # pneus neufs : l'usure restante remonte nettement
        if self.start_wear and any(w - s > 0.1 for w, s in zip(wear, self.start_wear)):
            self.wear_hist = []
            self.start_wear = list(wear)
            self.stint_start = laps
        if laps != self.laps:
            self._complete(laps, fuel, energy, wear, in_pits, last_lap, neutral)

    def _complete(self, laps: int, fuel: float, energy: float, wear: list[float], in_pits: bool,
                  last_lap: float, neutral: bool) -> None:
        t = last_lap if last_lap and last_lap > 30 else 0.0
        if self.had_pit:
            if t:
                self.pit_acc.append(t)
            self.pit_acc_dirty = self.pit_acc_dirty or self.dirty
        elif not self.dirty:
            used = self.start_fuel - fuel
            if 0.05 < used < 40:
                self.fuel_hist = (self.fuel_hist + [used])[-self.KEEP:]
            used_e = self.start_energy - energy
            if 0.0005 < used_e < 0.5:
                self.energy_hist = (self.energy_hist + [used_e])[-self.KEEP:]
            if self.start_wear and len(self.start_wear) == len(wear):
                worst = max(s - w for w, s in zip(wear, self.start_wear))
                if 0.0005 < worst < 0.2:
                    self.wear_hist = (self.wear_hist + [worst])[-self.KEEP:]
            self._close_pit_window(t)
            if t:
                self.laptime_hist = (self.laptime_hist + [t])[-self.KEEP:]
        else:  # tour neutralisé : on n'apprend rien
            self.pit_acc, self.pit_acc_dirty = [], False
        self._begin(laps, fuel, energy, wear, in_pits, neutral)

    def _close_pit_window(self, clean_lap: float) -> None:
        """Appelé sur le premier tour propre après un arrêt : calcule le temps perdu."""
        if not self.pit_acc:
            return
        ref = _median(self.laptime_hist) or clean_lap
        if ref and not self.pit_acc_dirty and len(self.pit_acc) <= 3:
            loss = sum(self.pit_acc) - len(self.pit_acc) * ref
            if 8 < loss < 240:
                self.pit_loss_hist = (self.pit_loss_hist + [loss])[-3:]
        self.pit_acc, self.pit_acc_dirty = [], False

    # ---- lectures ----

    @property
    def fuel_per_lap(self) -> float:
        return _avg(self.fuel_hist)

    @property
    def energy_per_lap(self) -> float:
        return _avg(self.energy_hist)

    @property
    def avg_lap_time(self) -> float:
        return _avg(self.laptime_hist)

    @property
    def wear_per_lap(self) -> float:
        return _avg(self.wear_hist)

    def stint_lap(self, laps: int) -> int:
        return max(0, laps - self.stint_start)

    def pit_loss(self, default: float, auto: bool = True) -> tuple[float, bool]:
        """(secondes, mesuré ?)"""
        if auto and self.pit_loss_hist:
            return _avg(self.pit_loss_hist), True
        return default, False

    # ---- persistance ----

    _FIELDS = ("laps", "start_fuel", "start_energy", "start_wear", "had_pit", "dirty", "fuel_hist", "energy_hist",
               "laptime_hist", "wear_hist", "pit_acc", "pit_acc_dirty", "pit_loss_hist", "stint_start")

    def snapshot(self) -> dict:
        return {k: getattr(self, k) for k in self._FIELDS}

    def restore(self, d: dict) -> None:
        self.reset()
        for k in self._FIELDS:
            if k not in d:
                continue
            v, cur = d[k], getattr(self, k)
            if k == "laps":
                ok = v is None or (isinstance(v, int) and not isinstance(v, bool))
            elif isinstance(cur, bool):
                ok = isinstance(v, bool)
            elif isinstance(cur, (int, float)):
                ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            else:
                ok = isinstance(v, list)
            if ok:
                setattr(self, k, v)


# --------------------------------------------------------------------------
# Tours restants
# --------------------------------------------------------------------------


def remaining_laps(*, is_race: bool, max_laps: int, laps_done: int, lap_frac: float,
                   time_remaining: float, time_into_lap: float, avg_lap: float) -> tuple[float, int]:
    """(tours restants fractionnaires, nombre de passages de ligne à effectuer).

    Course au temps : on finit au premier passage de ligne APRÈS la fin du chrono, donc le nombre de
    passages est ceil((temps restant + temps déjà passé dans le tour) / tour moyen)."""
    if not is_race:
        return 0.0, 0
    if 0 < max_laps < 100000:
        rem = max(0.0, max_laps - laps_done - lap_frac)
        return rem, math.ceil(rem - 1e-9)
    if avg_lap > 0 and time_remaining > 0:
        e = max(0.0, time_into_lap)
        n = math.ceil((time_remaining + e) / avg_lap)
        return max(0.0, n - e / avg_lap), n
    return 0.0, 0


# --------------------------------------------------------------------------
# Plan d'arrêts
# --------------------------------------------------------------------------


def compute_strategy(*, lap: int, remaining: float, fuel: float, capacity: float, fpl: float,
                     ve: float, epl: float, wear_now: list[float], wear_pl: float, stint_lap: int,
                     pit_loss: float, pit_loss_measured: bool = False,
                     tyre_min: float = 0.25, margin: float = 0.5) -> dict:
    """Ressource limitante, prochain arrêt, arrêts pour finir, ajouts carburant / énergie."""
    avail: dict[str, float] = {}
    full: dict[str, float] = {}
    if fpl > 0:
        avail["Carburant"] = fuel / fpl
        full["Carburant"] = capacity / fpl if capacity > 0 else 0.0
    has_ve = epl > 0 and 0 < ve <= 1.0001
    if has_ve:
        avail["Énergie"] = ve / epl
        full["Énergie"] = 1.0 / epl
    if wear_pl > 0 and wear_now:
        avail["Pneus"] = max(0.0, (min(wear_now) - tyre_min) / wear_pl)
        full["Pneus"] = (1.0 - tyre_min) / wear_pl
    if not avail:
        return {"known": False, "stintLap": stint_lap}

    limiting = min(avail, key=avail.get)
    usable = max(0.0, avail[limiting] - margin)
    pit_in = int(math.floor(usable))  # tours complets encore faisables, tour en cours inclus
    pit_lap = lap + max(0, pit_in - 1)

    can_finish = remaining > 0 and all(v - margin >= remaining for v in avail.values())
    stops = None
    if remaining > 0:
        if can_finish:
            stops = 0
        else:
            positive = [v for v in full.values() if v > 0]
            stint_cap = max(1.0, min(positive) - margin) if positive else 1.0
            stops = max(1, math.ceil((remaining - usable) / stint_cap))

    laps_after = (remaining - pit_in) if remaining > 0 else None
    fuel_add = energy_add = None
    if fpl > 0:
        fuel_at_pit = max(0.0, fuel - pit_in * fpl)
        la = laps_after if laps_after is not None else full.get("Carburant", 0.0)
        need = max(0.0, la + margin) * fpl
        fuel_add = round(max(0.0, min(capacity - fuel_at_pit, need)) if capacity > 0 else need, 1)
    if has_ve:
        ve_at_pit = max(0.0, ve - pit_in * epl)
        la = laps_after if laps_after is not None else full.get("Énergie", 0.0)
        need_e = max(0.0, la + margin) * epl
        energy_add = round(max(0.0, min(1.0 - ve_at_pit, need_e)) * 100, 1)

    save = None  # économie qui permettrait d'éviter un arrêt
    if remaining > 0 and not can_finish:
        for name in ("Carburant", "Énergie"):
            if name not in avail:
                continue
            others_ok = all(v - margin >= remaining for k, v in avail.items() if k != name)
            ratio = avail[name] / (remaining + margin)
            if others_ok and 0.88 <= ratio < 1.0:
                save = {"resource": name, "pct": round((1 - ratio) * 100, 1)}
                break

    if can_finish:
        status = "finish"
    elif pit_in <= 1:
        status = "box_now"
    elif pit_in <= 3:
        status = "box_soon"
    else:
        status = "ok"

    return {
        "known": True,
        "status": status,
        "limiting": limiting,
        "stintLaps": round(usable, 1),
        "pitIn": pit_in,
        "pitLap": pit_lap,
        "stops": stops,
        "fuelAdd": fuel_add,
        "energyAdd": energy_add,
        "save": save,
        "stintLap": stint_lap,
        "tyreWearPerLap": round(wear_pl * 100, 2),
        "tyreMin": round(tyre_min * 100),
        "pitLoss": round(pit_loss),
        "pitLossMeasured": pit_loss_measured,
        "timeCost": round(stops * pit_loss) if stops else 0,
        "remaining": remaining,
        "bars": [{"name": n, "laps": round(avail[n], 1)} for n in ("Carburant", "Énergie", "Pneus") if n in avail],
    }
