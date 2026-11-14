"""Lecteurs de données : le vrai jeu (mémoire partagée LMU, Windows) et un mode démo simulé.
Les deux produisent le même format de payload JSON pour le dashboard."""
from __future__ import annotations

import math
import mmap
import sys
import time

from store import Settings
from strategy import RaceStats, compute_strategy, remaining_laps

# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------


def txt(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("utf-8", "replace").strip()


def k2c(k: float) -> float:
    return k - 273.15 if k > 1 else 0.0


def finite(x: float, default: float = 0.0) -> float:
    return x if isinstance(x, (int, float)) and math.isfinite(x) else default


def byte_val(v) -> int:
    """mYellowFlagState est un c_char (bytes) ; on accepte aussi un entier."""
    if isinstance(v, (bytes, bytearray)):
        return v[0] if v else 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def build_strategy(stats: RaceStats, settings: Settings, *, lap: int, remaining: float, fuel: float,
                   capacity: float, ve: float, wear_now: list[float], compound: str) -> dict:
    cfg = settings.get()
    loss, measured = stats.pit_loss(cfg["pitLoss"], cfg["pitLossAuto"])
    return compute_strategy(
        lap=lap, remaining=remaining, fuel=fuel, capacity=capacity, fpl=stats.fuel_per_lap,
        ve=ve, epl=stats.energy_per_lap, wear_now=wear_now, wear_pl=stats.wear_per_lap,
        stint_lap=stats.stint_lap(stats.laps or 0), pit_loss=loss, pit_loss_measured=measured,
        tyre_min=settings.tyre_min(compound), margin=cfg["margin"])


# --------------------------------------------------------------------------
# Lecture du jeu
# --------------------------------------------------------------------------


class LMUReader:
    def __init__(self, settings: Settings) -> None:
        from pyLMUSharedMemory import lmu_data  # import tardif : la démo marche sans Windows

        self.lmu_data = lmu_data
        self.settings = settings
        self.size = lmu_data.ctypes.sizeof(lmu_data.LMUObjectOut)
        self.name = lmu_data.LMUConstants.LMU_SHARED_MEMORY_FILE
        self.mm = None
        self.buf = bytearray(self.size)
        self.stats = RaceStats()
        self.last_ok = 0.0
        self.last_open = 0.0
        self.session_key = None

    # ---- état persistant ----
    def snapshot(self) -> dict:
        return self.stats.snapshot()

    def restore(self, d: dict) -> None:
        self.stats.restore(d)

    def reset_stats(self) -> None:
        self.stats.reset()

    # ---- mémoire partagée ----
    def _open(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("La lecture du vrai jeu ne marche que sous Windows (utilise --demo pour tester).")
        self.mm = mmap.mmap(-1, self.size, self.name)
        self.last_open = time.monotonic()

    def _close(self) -> None:
        try:
            if self.mm:
                self.mm.close()
        finally:
            self.mm = None

    def read(self) -> dict:
        now = time.monotonic()
        if self.mm is None or (now - self.last_ok > 3 and now - self.last_open > 2):
            self._close()
            self._open()

        self.buf[:] = self.mm[0:self.size]
        d = self.lmu_data.LMUObjectOut.from_buffer(self.buf)

        sc = d.scoring.scoringInfo
        tel = d.telemetry
        n = max(0, min(sc.mNumVehicles, 104))
        if n == 0:
            return {"connected": False, "state": "waiting"}
        self.last_ok = now

        veh = d.scoring.vehScoringInfo
        pi = next((i for i in range(n) if veh[i].mIsPlayer), -1)

        out: dict = {
            "connected": True,
            "t": time.time(),
            "session": self._session(sc),
            "weather": self._weather(sc),
        }

        order = sorted(range(n), key=lambda i: veh[i].mPlace)
        out["standings"] = self._standings(veh, order)

        if pi < 0 or not tel.playerHasVehicle:
            out["state"] = "spectating"
            return out

        pv = veh[pi]
        tv = tel.telemInfo[tel.playerVehicleIdx]
        out["state"] = "driving" if sc.mInRealtime else "garage"

        key = (txt(sc.mTrackName), sc.mSession, txt(tv.mVehicleName))
        if key != self.session_key:
            self.session_key = key
            self.stats.reset()

        neutral = out["session"]["neutral"]
        wear_now = [max(0.0, min(1.0, finite(w.mWear))) for w in tv.mWheels]
        self.stats.update(pv.mTotalLaps, tv.mFuel, tv.mVirtualEnergy, wear_now, bool(pv.mInPits),
                          pv.mLastLapTime, neutral)

        out["car"] = self._car(tv, pv)
        out["timing"] = self._timing(sc, pv, tv, veh, order)
        out["tyres"] = self._tyres(tv)
        out["energy"] = self._energy(sc, tv, pv)
        e = out["energy"]
        out["strategy"] = build_strategy(
            self.stats, self.settings, lap=tv.mLapNumber, remaining=e["remainingLaps"], fuel=e["fuel"],
            capacity=e["capacity"], ve=e["virtualEnergy"], wear_now=wear_now,
            compound=out["tyres"]["front"])
        out["damage"] = self._damage(tv)
        return out

    # ----- blocs ---------------------------------------------------------

    def _session(self, sc) -> dict:
        yellow = byte_val(sc.mYellowFlagState)
        return {
            "track": txt(sc.mTrackName),
            "type": sc.mSession,
            "isRace": sc.mSession >= 10,
            "phase": sc.mGamePhase,
            "yellow": yellow,
            "neutral": sc.mGamePhase == 6 or 1 <= yellow <= 5,
            "sectorFlags": list(sc.mSectorFlag),
            "timeRemaining": finite(sc.mSessionTimeRemaining),
            "elapsed": finite(sc.mCurrentET),
            "endET": finite(sc.mEndET),
            "maxLaps": sc.mMaxLaps if sc.mMaxLaps < 100000 else 0,
            "trackLength": finite(sc.mLapDist),
            "timeOfDay": finite(sc.mTimeOfDay),
            "cars": sc.mNumVehicles,
            "inRealtime": bool(sc.mInRealtime),
        }

    def _weather(self, sc) -> dict:
        return {
            "ambient": finite(sc.mAmbientTemp),
            "track": finite(sc.mTrackTemp),
            "rain": finite(sc.mRaining),
            "wetnessAvg": finite(sc.mAvgPathWetness),
            "wetnessMax": finite(sc.mMaxPathWetness),
            "clouds": finite(sc.mDarkCloud),
            "grip": sc.mTrackGripLevel,
        }

    def _standings(self, veh, order: list[int]) -> list[dict]:
        rows = []
        class_pos: dict[str, int] = {}
        class_leader: dict[str, tuple[float, int]] = {}
        for i in order:
            v = veh[i]
            cls = txt(v.mVehicleClass)
            class_pos[cls] = class_pos.get(cls, 0) + 1
            if cls not in class_leader:
                class_leader[cls] = (v.mTimeBehindLeader, v.mLapsBehindLeader)
            lt, ll = class_leader[cls]
            if v.mLapsBehindLeader == ll:
                cgap, claps = max(0.0, v.mTimeBehindLeader - lt), 0
            else:
                cgap, claps = 0.0, v.mLapsBehindLeader - ll
            rows.append({
                "pos": v.mPlace,
                "cpos": class_pos[cls],
                "name": txt(v.mDriverName),
                "car": txt(v.mVehicleName),
                "cls": cls,
                "laps": v.mTotalLaps,
                "last": finite(v.mLastLapTime, -1),
                "best": finite(v.mBestLapTime, -1),
                "gapLeader": finite(v.mTimeBehindLeader),
                "lapsLeader": v.mLapsBehindLeader,
                "gapClass": finite(cgap),
                "lapsClass": claps,
                "gapNext": finite(v.mTimeBehindNext),
                "pits": v.mNumPitstops,
                "inPits": bool(v.mInPits),
                "pen": v.mNumPenalties,
                "me": bool(v.mIsPlayer),
                "ai": v.mControl == 1,
                "finish": v.mFinishStatus,
                "x": round(finite(v.mPos.x), 1),
                "z": round(finite(v.mPos.z), 1),
                "d": round(finite(v.mLapDist), 1),
                "garage": bool(v.mInGarageStall),
                "spd": round(math.sqrt(finite(v.mLocalVel.x) ** 2 + finite(v.mLocalVel.y) ** 2 + finite(v.mLocalVel.z) ** 2) * 3.6),
            })
        return rows

    @staticmethod
    def _sectors(pv):
        """Temps des 3 secteurs du dernier tour [S1, S2, S3] (le jeu donne S1 et S1+S2 cumulés), None si inconnu."""
        s1, s12, lap = finite(pv.mLastSector1, -1), finite(pv.mLastSector2, -1), finite(pv.mLastLapTime, -1)
        if s1 > 0 and s12 > s1 and lap > s12:
            return [round(s1, 3), round(s12 - s1, 3), round(lap - s12, 3)]
        return None

    def _car(self, tv, pv) -> dict:
        vx, vy, vz = tv.mLocalVel.x, tv.mLocalVel.y, tv.mLocalVel.z
        speed = math.sqrt(vx * vx + vy * vy + vz * vz) * 3.6
        return {
            "name": txt(tv.mVehicleName),
            "model": txt(tv.mVehicleModel),
            "class": txt(pv.mVehicleClass),
            "driver": txt(pv.mDriverName),
            "inGarage": bool(pv.mInGarageStall),
            "speed": speed,
            "gear": tv.mGear,
            "maxGears": tv.mMaxGears,
            "rpm": tv.mEngineRPM,
            "maxRpm": tv.mEngineMaxRPM,
            "throttle": tv.mUnfilteredThrottle,
            "brake": tv.mUnfilteredBrake,
            "clutch": tv.mUnfilteredClutch,
            "steer": tv.mUnfilteredSteering,
            "water": tv.mEngineWaterTemp,
            "oil": tv.mEngineOilTemp,
            "overheating": bool(tv.mOverheating),
            "headlights": bool(tv.mHeadlights),
            "limiter": bool(tv.mSpeedLimiterActive),
            "tc": tv.mTC, "tcMax": tv.mTCMax,
            "tcSlip": tv.mTCSlip, "tcSlipMax": tv.mTCSlipMax,
            "tcCut": tv.mTCCut, "tcCutMax": tv.mTCCutMax,
            "abs": tv.mABS, "absMax": tv.mABSMax,
            "tcActive": bool(tv.mTCActive),
            "absActive": bool(tv.mABSActive),
            "motorMap": tv.mMotorMap, "motorMapMax": tv.mMotorMapMax,
            "migration": tv.mMigration, "migrationMax": tv.mMigrationMax,
            "brakeBias": (1 - tv.mRearBrakeBias) * 100 if 0 < tv.mRearBrakeBias < 1 else 0,
            "wiper": tv.mWiperState,
            "boost": tv.mTurboBoostPressure,
            "regen": finite(tv.mRegen),
            "battery": tv.mBatteryChargeFraction,
            "boostMotorState": tv.mElectricBoostMotorState,
            "boostMotorTemp": tv.mElectricBoostMotorTemperature,
            "rearFlap": bool(tv.mRearFlapActivated),
            "inPits": bool(pv.mInPits),
            "pitState": pv.mPitState,
        }

    def _timing(self, sc, pv, tv, veh, order) -> dict:
        cls = txt(pv.mVehicleClass)
        cpos = sum(1 for i in order if txt(veh[i].mVehicleClass) == cls and veh[i].mPlace <= pv.mPlace)
        ctotal = sum(1 for i in order if txt(veh[i].mVehicleClass) == cls)
        time_into_lap = max(0.0, finite(sc.mCurrentET) - finite(tv.mLapStartET))
        return {
            "pos": pv.mPlace,
            "total": sc.mNumVehicles,
            "cpos": cpos,
            "ctotal": ctotal,
            "lap": tv.mLapNumber,
            "laps": pv.mTotalLaps,
            "lapTime": time_into_lap,
            "last": finite(pv.mLastLapTime, -1),
            "best": finite(pv.mBestLapTime, -1),
            "deltaBest": finite(tv.mDeltaBest),
            "gapAhead": finite(tv.mTimeGapCarAhead),
            "gapBehind": finite(tv.mTimeGapCarBehind),
            "gapAheadPlace": finite(tv.mTimeGapPlaceAhead),
            "gapBehindPlace": finite(tv.mTimeGapPlaceBehind),
            "sector": {0: 3, 1: 1, 2: 2}.get(pv.mSector, 0),
            "lastSectors": self._sectors(pv),
            "lapDist": finite(pv.mLapDist),
            "pitStops": pv.mNumPitstops,
            "penalties": pv.mNumPenalties,
            "invalid": bool(tv.mLapInvalidated),
            "trackLimits": tv.mTrackLimitsSteps,
            "flag": pv.mFlag,
            "underYellow": bool(pv.mUnderYellow),
            "avgLap": self.stats.avg_lap_time,
        }

    def _energy(self, sc, tv, pv) -> dict:
        st = self.stats
        fpl, epl = st.fuel_per_lap, st.energy_per_lap
        fuel, ve = finite(tv.mFuel), finite(tv.mVirtualEnergy)
        length = finite(sc.mLapDist)
        avg = st.avg_lap_time or (pv.mBestLapTime if pv.mBestLapTime > 0 else 0.0)
        rem, finish_laps = remaining_laps(
            is_race=sc.mSession >= 10,
            max_laps=sc.mMaxLaps,
            laps_done=pv.mTotalLaps,
            lap_frac=(finite(pv.mLapDist) / length) if length > 0 else 0.0,
            time_remaining=finite(sc.mSessionTimeRemaining),
            time_into_lap=finite(sc.mCurrentET) - finite(tv.mLapStartET),
            avg_lap=avg)
        return {
            "fuel": fuel,
            "capacity": finite(tv.mFuelCapacity),
            "fuelPerLap": fpl,
            "lapsFuel": fuel / fpl if fpl > 0 else 0.0,
            "virtualEnergy": ve,
            "energyPerLap": epl,
            "lapsEnergy": ve / epl if epl > 0 else 0.0,
            "remainingLaps": rem,
            "finishLaps": finish_laps,
            "samples": len(st.fuel_hist),
        }

    def _tyres(self, tv) -> dict:
        wheels = []
        for w in tv.mWheels:
            wheels.append({
                "tempL": k2c(w.mTemperature[0]),
                "tempC": k2c(w.mTemperature[1]),
                "tempR": k2c(w.mTemperature[2]),
                "carcass": k2c(w.mTireCarcassTemperature),
                "optimal": w.mOptimalTemp,
                "pressure": w.mPressure,
                "wear": max(0.0, min(1.0, finite(w.mWear))),  # bande de roulement restante (1.0 = neuf)
                "brake": w.mBrakeTemp,
                "flat": bool(w.mFlat),
                "detached": bool(w.mDetached),
                "surface": w.mSurfaceType,
            })
        return {
            "wheels": wheels,
            "front": txt(tv.mFrontTireCompoundName),
            "rear": txt(tv.mRearTireCompoundName),
        }

    def _damage(self, tv) -> dict:
        return {
            "dents": list(tv.mDentSeverity),
            "detached": bool(tv.mDetached),
            "lastImpact": finite(tv.mLastImpactMagnitude),
            "lastImpactET": finite(tv.mLastImpactET),
        }


# --------------------------------------------------------------------------
# Mode démo : données simulées, même format que le vrai
# (arrêts aux stands tous les 8 tours avec changement de pilote, Safety Car périodique)
# --------------------------------------------------------------------------


class DemoReader:
    TRACK_LEN = 13626.0  # Le Mans
    LAP_TIME = 205.0
    DRIVERS = ["A. Dupont", "M. Rossi", "K. Tanaka"]
    STOP_EVERY = 8

    def __init__(self, settings: Settings, speed: float = 1.0) -> None:
        self.settings = settings
        self.speed = speed
        self.stats = RaceStats()
        self.t0 = time.time()
        self.fuel = 85.0
        self.energy = 1.0
        self.laps_done = 12
        self.tyre_lap0 = 12
        self.last = 207.412
        self.best = 205.883
        self.prev_pos = 0.0

    def snapshot(self) -> dict:
        return self.stats.snapshot()

    def restore(self, d: dict) -> None:
        self.stats.restore(d)

    def reset_stats(self) -> None:
        self.stats.reset()

    def _pos(self, frac: float) -> dict:
        x, z = self.track_xy(frac)
        return {"x": round(x, 1), "z": round(z, 1), "d": round(frac * self.TRACK_LEN, 1), "garage": False, "spd": 200}

    @staticmethod
    def track_xy(frac: float) -> tuple[float, float]:
        a = 2 * math.pi * frac
        return 2600 * math.cos(a) + 800 * math.cos(3 * a), -(1500 * math.sin(a) + 550 * math.sin(2 * a))

    def read(self) -> dict:
        t = (time.time() - self.t0) * self.speed
        lap_pos = (t % self.LAP_TIME) / self.LAP_TIME
        k = self.STOP_EVERY
        neutral = (self.laps_done % 11) == 5

        if lap_pos < self.prev_pos:  # passage de ligne
            before = self.laps_done
            self.laps_done += 1
            base = self.LAP_TIME + 2.0 + 3 * math.sin(t)
            if before % k == k - 1:
                base += 30       # tour d'entrée
            elif before % k == 0:
                base += 15       # tour de sortie
            self.last = base
            if before % k not in (k - 1, 0):
                self.best = min(self.best, self.last)
            self.fuel -= 1.7 if neutral else 3.4
            self.energy -= 0.0225 if neutral else 0.045
            if self.laps_done % k == 0:  # arrêt : plein + pneus neufs
                self.fuel, self.energy, self.tyre_lap0 = 85.0, 1.0, self.laps_done
        self.prev_pos = lap_pos
        in_pits = (self.laps_done % k == k - 1 and lap_pos > 0.94) or (self.laps_done % k == 0 and lap_pos < 0.05)

        driver = self.DRIVERS[(self.laps_done // k) % len(self.DRIVERS)]
        s = 0.5 + 0.5 * math.sin(lap_pos * 2 * math.pi * 7)
        speed = 90 + 250 * s
        if in_pits:
            speed = 60
        gear = max(1, min(7, int(speed / 48) + 1))
        rpm = 4200 + (speed % 48) / 48 * 3300
        accel = math.cos(lap_pos * 2 * math.pi * 7)
        throttle = max(0.0, min(1.0, 0.5 + accel * 1.5))
        brake = max(0.0, min(1.0, -accel * 1.5 - 0.6))

        def wear_val(i: int) -> float:
            return max(0.0, 1 - (self.laps_done - self.tyre_lap0) * 0.012 - i * 0.004)

        def tyre(base: float, i: int) -> dict:
            return {
                "tempL": base + 4 + 2 * math.sin(t / 3 + i), "tempC": base + 2 * math.sin(t / 4 + i),
                "tempR": base - 4 + 2 * math.sin(t / 5 + i), "carcass": base - 8, "optimal": 90.0,
                "pressure": 172 + 8 * s + i, "wear": wear_val(i),
                "brake": 350 + 330 * max(0, -accel) + i * 20, "flat": False, "detached": False, "surface": 0,
            }

        wheels = [tyre(88, 0), tyre(87, 1), tyre(92, 2), tyre(93, 3)]
        wear_now = [w["wear"] for w in wheels]
        self.stats.update(self.laps_done, self.fuel, self.energy, wear_now, in_pits, self.last, neutral)

        names = ["Toyota GR010", "Ferrari 499P", "Porsche 963", "Cadillac V-Series.R", "Peugeot 9X8",
                 "BMW M Hybrid V8", "Alpine A424", "Aston Martin Valkyrie"]
        standings = []
        for i, nm in enumerate(names):
            standings.append({
                "pos": i + 1, "cpos": i + 1, "name": driver if i == 2 else f"Pilote {i + 1}", "car": nm, "cls": "Hypercar",
                "laps": self.laps_done + (1 if i < 2 else 0), "last": 205.0 + i * 0.7, "best": 204.2 + i * 0.5,
                "gapLeader": i * 4.3, "lapsLeader": 0, "gapClass": i * 4.3, "lapsClass": 0, "gapNext": 4.3 if i else 0,
                "pits": 2, "inPits": in_pits if i == 2 else False, "pen": 0, "me": i == 2, "ai": i != 2, "finish": 0,
                **self._pos((lap_pos - (i - 2) * 4.3 / self.LAP_TIME) % 1),
            })
        for i in range(3):
            standings.append({
                "pos": 9 + i, "cpos": i + 1, "name": f"GT3 {i + 1}", "car": "Corvette Z06 GT3.R", "cls": "LMGT3",
                "laps": self.laps_done - 2, "last": 225.0 + i, "best": 223.5 + i,
                "gapLeader": 50 + i * 3, "lapsLeader": 2, "gapClass": i * 3.0, "lapsClass": 0, "gapNext": 3.0,
                "pits": 2, "inPits": False, "pen": 0, "me": False, "ai": True, "finish": 0,
                **(self._pos(0.5) | {"spd": 0} if (i == 0 and self.laps_done % 7 == 3 and not neutral)
                   else self._pos((lap_pos * 0.9 + 0.15 + i * 0.09) % 1)),
            })

        remaining_t = max(0.0, 6 * 3600 - 2000 - t)
        avg = self.stats.avg_lap_time or self.LAP_TIME
        rem, finish_laps = remaining_laps(is_race=True, max_laps=0, laps_done=self.laps_done, lap_frac=lap_pos,
                                          time_remaining=remaining_t, time_into_lap=lap_pos * self.LAP_TIME, avg_lap=avg)
        fpl, epl = self.stats.fuel_per_lap, self.stats.energy_per_lap
        strategy = build_strategy(self.stats, self.settings, lap=self.laps_done + 1, remaining=rem, fuel=self.fuel,
                                  capacity=90.0, ve=self.energy, wear_now=wear_now, compound="Medium")
        return {
            "connected": True,
            "demo": True,
            "t": time.time(),
            "state": "driving",
            "session": {
                "track": "Circuit de la Sarthe", "type": 10, "isRace": True, "phase": 6 if neutral else 5,
                "yellow": 1 if neutral else 0, "neutral": neutral, "sectorFlags": [0, 1 if (self.laps_done % 7 == 3 and not neutral) else 0, 0],
                "timeRemaining": remaining_t, "elapsed": 2000 + t, "endET": 0, "maxLaps": 0,
                "trackLength": self.TRACK_LEN, "timeOfDay": 50000 + t * 4, "cars": len(standings), "inRealtime": True,
            },
            "weather": {"ambient": 22.0, "track": 31.0 + math.sin(t / 60), "rain": 0.0, "wetnessAvg": 0.0,
                        "wetnessMax": 0.0, "clouds": 0.2, "grip": 5},
            "standings": standings,
            "car": {
                "name": "Porsche 963 #6", "model": "963", "class": "Hypercar", "driver": driver, "inGarage": False,
                "speed": speed, "gear": gear, "maxGears": 7, "rpm": rpm, "maxRpm": 8000, "throttle": throttle,
                "brake": brake, "clutch": 0.0, "steer": math.sin(lap_pos * 40), "water": 88 + 3 * math.sin(t / 10),
                "oil": 104 + 2 * math.sin(t / 8), "overheating": False, "headlights": False, "limiter": in_pits,
                "tc": 4, "tcMax": 12, "tcSlip": 3, "tcSlipMax": 10, "tcCut": 2, "tcCutMax": 10,
                "abs": 6, "absMax": 12, "tcActive": throttle > 0.9 and gear < 3, "absActive": brake > 0.85,
                "motorMap": 1, "motorMapMax": 3, "migration": 3, "migrationMax": 10, "brakeBias": 56.5, "wiper": 0,
                "boost": 0, "regen": 0, "battery": 0.6, "boostMotorState": 2 if throttle > 0.8 else 1,
                "boostMotorTemp": 70, "rearFlap": False, "inPits": in_pits, "pitState": 0,
            },
            "timing": {
                "pos": 3, "total": len(standings), "cpos": 3, "ctotal": 8, "lap": self.laps_done + 1,
                "laps": self.laps_done, "lapTime": lap_pos * self.LAP_TIME, "last": self.last, "best": self.best,
                "deltaBest": 0.4 * math.sin(t / 7), "gapAhead": 4.3 + 0.3 * math.sin(t / 9),
                "gapBehind": 4.3 - 0.3 * math.sin(t / 9), "gapAheadPlace": 8.6, "gapBehindPlace": 4.3,
                "lastSectors": [round(self.last * f, 3) for f in (0.337, 0.335, 0.328)] if self.last and self.last > 30 else None,
                "sector": 1 + int(lap_pos * 3) % 3, "lapDist": lap_pos * self.TRACK_LEN, "pitStops": self.laps_done // k,
                "penalties": 0, "invalid": False, "trackLimits": 0, "flag": 0, "underYellow": neutral,
                "avgLap": self.stats.avg_lap_time,
            },
            "energy": {
                "fuel": self.fuel, "capacity": 90.0, "fuelPerLap": fpl, "lapsFuel": self.fuel / fpl if fpl else 0.0,
                "virtualEnergy": self.energy, "energyPerLap": epl, "lapsEnergy": self.energy / epl if epl else 0.0,
                "remainingLaps": rem, "finishLaps": finish_laps, "samples": len(self.stats.fuel_hist),
            },
            "tyres": {"wheels": wheels, "front": "Medium", "rear": "Medium"},
            "damage": {"dents": [0, 0, 1, 0, 0, 0, 0, 0], "detached": False, "lastImpact": 0, "lastImpactET": 0},
            "strategy": strategy,
        }
