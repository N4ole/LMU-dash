"""Suivi d'endurance : pilotes, relais, historique des tours. Travaille sur le payload déjà
construit par le lecteur (jeu ou démo), donc identique dans les deux modes."""
from __future__ import annotations

import csv
import io
import threading

MAX_LAPS = 1500


def fmt_lap(t: float | None) -> str:
    if not t or t <= 0:
        return ""
    m = int(t // 60)
    return f"{m}:{t - m * 60:06.3f}"


def fmt_clock(s: float) -> str:
    s = int(max(0, s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


class Endurance:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.drivers: dict[str, dict] = {}   # nom -> {total, stints, laps, best}
            self.stints: list[dict] = []          # relais terminés
            self.laps: list[dict] = []
            self.cur: dict | None = None          # relais en cours
            self.driver: str | None = None
            self.last_et: float | None = None
            self.prev_in_pits: bool | None = None
            self.prev_laps: int | None = None
            self.flags = {"pit": False, "neutral": False, "invalid": False}

    # ------------------------------------------------------------------

    def _drv(self, name: str) -> dict:
        return self.drivers.setdefault(name, {"total": 0.0, "stints": 0, "laps": 0, "best": None})

    def _open(self, et: float, laps: int, driver: str) -> None:
        self.cur = {"driver": driver, "startET": et, "endET": None, "startLaps": laps, "times": [], "laps": 0, "best": None}

    def _finish_stint(self) -> None:
        c = self.cur
        if not c:
            return
        if c["laps"] >= 1:
            end = c["endET"] if c["endET"] is not None else c["startET"]
            t = c["times"]
            self.stints.append({
                "n": len(self.stints) + 1, "driver": c["driver"], "firstLap": c["startLaps"] + 1, "laps": c["laps"],
                "dur": round(max(0.0, end - c["startET"]), 1), "best": c["best"],
                "avg": round(sum(t) / len(t), 3) if t else None,
            })
            self._drv(c["driver"])["stints"] += 1
        self.cur = None

    def update(self, d: dict) -> None:
        s, c, t, e = d["session"], d["car"], d["timing"], d.get("energy") or {}
        et = float(s.get("elapsed") or 0.0)
        in_pits = bool(c.get("inPits"))
        garage = bool(c.get("inGarage"))
        driver = (c.get("driver") or "?").strip() or "?"
        laps = int(t.get("laps") or 0)
        with self.lock:
            if self.last_et is not None and et < self.last_et - 5:  # session relancée
                self.reset()
            if self.last_et is None:
                self.driver = driver
                self._open(et, laps, driver)
                self.prev_laps, self.prev_in_pits = laps, in_pits
            dt = et - self.last_et if self.last_et is not None else 0.0
            self.last_et = et
            if 0 < dt < 5 and not garage:
                self._drv(self.driver or driver)["total"] += dt

            # accumulation des drapeaux du tour en cours
            self.flags["pit"] = self.flags["pit"] or in_pits
            self.flags["neutral"] = self.flags["neutral"] or bool(s.get("neutral"))
            self.flags["invalid"] = self.flags["invalid"] or bool(t.get("invalid"))

            # tour(s) terminé(s) -- avant les changements de pilote / relais
            if self.prev_laps is not None and laps > self.prev_laps:
                last = t.get("last")
                lap_time = float(last) if last and last > 30 else None
                clean = lap_time is not None and not self.flags["pit"] and not self.flags["neutral"]
                wheels = (d.get("tyres") or {}).get("wheels") or []
                wear = min((w["wear"] for w in wheels), default=None)
                rec = {
                    "lap": laps, "time": lap_time, "driver": self.driver or driver,
                    "stint": (len(self.stints) + 1), "pit": self.flags["pit"], "neutral": self.flags["neutral"],
                    "invalid": self.flags["invalid"], "fuel": round(float(e.get("fuel") or 0), 1),
                    "wear": round(wear * 100) if isinstance(wear, (int, float)) else None,
                }
                self.laps.append(rec)
                if len(self.laps) > MAX_LAPS:
                    del self.laps[: len(self.laps) - MAX_LAPS]
                if self.cur is not None:
                    self.cur["laps"] += 1
                    if clean:
                        self.cur["times"].append(lap_time)
                        if self.cur["best"] is None or lap_time < self.cur["best"]:
                            self.cur["best"] = lap_time
                dr = self._drv(self.driver or driver)
                dr["laps"] += 1
                if clean and not self.flags["invalid"] and (dr["best"] is None or lap_time < dr["best"]):
                    dr["best"] = lap_time
                self.flags = {"pit": in_pits, "neutral": bool(s.get("neutral")), "invalid": False}
            self.prev_laps = laps

            # entrée aux stands : le relais s'arrête (mais le tour d'entrée lui appartient encore)
            if in_pits and self.prev_in_pits is False and self.cur is not None and self.cur["endET"] is None:
                self.cur["endET"] = et
            # sortie des stands : on referme l'ancien relais et on en ouvre un nouveau
            if self.prev_in_pits and not in_pits:
                self._finish_stint()
                self._open(et, laps, driver)
            self.prev_in_pits = in_pits
            # changement de pilote (à l'arrêt) : les temps suivants lui sont attribués
            if driver != self.driver:
                self.driver = driver
                self._drv(driver)

    # ------------------------------------------------------------------

    def summary(self, et: float, in_pits: bool) -> dict:
        with self.lock:
            c = self.cur
            name = self.driver or "?"
            stint_time = 0.0
            if c:
                stint_time = (c["endET"] if c["endET"] is not None else et) - c["startET"]
            dr = self.drivers.get(name, {})
            return {
                "driver": name,
                "stintNo": len(self.stints) + 1,
                "stintTime": round(max(0.0, stint_time), 1),
                "stintLaps": c["laps"] if c else 0,
                "stintBest": c["best"] if c else None,
                "inPit": in_pits,
                "driverTotal": round(dr.get("total", 0.0), 1),
                "driverStints": dr.get("stints", 0) + (1 if c and c["laps"] else 0),
                "drivers": len(self.drivers),
            }

    def history(self, et: float) -> dict:
        with self.lock:
            stints = list(self.stints)
            c = self.cur
            if c and (c["laps"] or not stints):
                t = c["times"]
                stints.append({
                    "n": len(self.stints) + 1, "driver": c["driver"], "firstLap": c["startLaps"] + 1, "laps": c["laps"],
                    "dur": round(max(0.0, (c["endET"] if c["endET"] is not None else et) - c["startET"]), 1),
                    "best": c["best"], "avg": round(sum(t) / len(t), 3) if t else None, "current": True,
                })
            drivers = sorted(({"name": k, **v} for k, v in self.drivers.items()), key=lambda x: -x["total"])
            for x in drivers:
                x["total"] = round(x["total"], 1)
            clean = [r["time"] for r in self.laps if r["time"] and not r["pit"] and not r["neutral"]]
            return {
                "laps": self.laps[-60:], "totalLaps": len(self.laps), "stints": stints, "drivers": drivers,
                "best": min(clean) if clean else None,
                "avg": round(sum(clean[-10:]) / len(clean[-10:]), 3) if clean else None,
            }

    # ------------------------------------------------------------------

    def laps_csv(self) -> str:
        with self.lock:
            buf = io.StringIO()
            w = csv.writer(buf, delimiter=";")
            w.writerow(["tour", "temps_s", "temps", "pilote", "relais", "stand", "neutralise", "invalide", "carburant_L", "usure_pneu_min_pct"])
            for r in self.laps:
                w.writerow([r["lap"], f"{r['time']:.3f}".replace(".", ",") if r["time"] else "", fmt_lap(r["time"]),
                            r["driver"], r["stint"], int(r["pit"]), int(r["neutral"]), int(r["invalid"]),
                            str(r["fuel"]).replace(".", ","), r["wear"] if r["wear"] is not None else ""])
            return buf.getvalue()

    def stints_csv(self, et: float = 0.0) -> str:
        h = self.history(et)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["relais", "pilote", "premier_tour", "tours", "duree_s", "duree", "meilleur", "moyenne"])
        for x in h["stints"]:
            w.writerow([x["n"], x["driver"], x["firstLap"], x["laps"], x["dur"], fmt_clock(x["dur"]),
                        fmt_lap(x["best"]), fmt_lap(x["avg"])])
        return buf.getvalue()

    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        with self.lock:
            return {"drivers": self.drivers, "stints": self.stints, "laps": self.laps, "cur": self.cur,
                    "driver": self.driver, "last_et": self.last_et, "prev_in_pits": self.prev_in_pits,
                    "prev_laps": self.prev_laps, "flags": self.flags}

    def from_dict(self, d: dict) -> None:
        with self.lock:
            self.reset()
            try:
                self.drivers = {str(k): dict(v) for k, v in dict(d.get("drivers") or {}).items()}
                self.stints = [dict(x) for x in d.get("stints") or []]
                self.laps = [dict(x) for x in d.get("laps") or []]
                self.cur = dict(d["cur"]) if d.get("cur") else None
                self.driver = d.get("driver")
                self.last_et = d.get("last_et")
                self.prev_in_pits = d.get("prev_in_pits")
                self.prev_laps = d.get("prev_laps")
                self.flags = dict(d.get("flags") or self.flags)
            except (TypeError, ValueError):
                self.reset()
