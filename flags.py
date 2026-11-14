"""Suivi des drapeaux : FCY / Safety car, jaunes locaux (avec le bon secteur), voiture arrêtée devant,
drapeau bleu, rouge. Produit une liste d'« items » unique, utilisée par la bannière ET les alertes."""
from __future__ import annotations

import time

FCY_TEXT = {1: "FCY en préparation", 2: "FCY — stands fermés", 3: "FCY — stands ouverts aux leaders",
            4: "FCY — stands ouverts", 5: "FCY — dernier tour", 6: "Reprise imminente"}

# Pour chaque secteur S1..S3, l'indice correspondant dans mSectorFlag.
# Le jeu documente le doute (« not sure if sector 0 is first or last »), donc on l'apprend en roulant.
MAPS = {"direct": (0, 1, 2), "quirk": (1, 2, 0)}


def sector_of(frac: float, bounds) -> int | None:
    if bounds is None or bounds[0] is None or bounds[1] is None:
        return None
    return 1 if frac < bounds[0] else 2 if frac < bounds[1] else 3


class FlagWatch:
    HAZARD_SPEED = 25      # km/h : en dessous, une voiture en piste est considérée à l'arrêt
    HAZARD_RANGE = 1500    # m devant nous

    def __init__(self, settings) -> None:
        self.settings = settings
        self.votes = {"direct": 0, "quirk": 0}
        self.last_vote = 0.0

    def mapping(self) -> str:
        m = self.settings.get().get("flagMap")
        return m if m in MAPS else "direct"

    def _vote(self, raw, hazards, bounds, length) -> None:
        on = [i for i, v in enumerate(raw) if v]
        if len(on) != 1 or len(hazards) != 1 or time.monotonic() - self.last_vote < 5:
            return
        sec = sector_of(hazards[0]["d"] / length, bounds)
        if not sec:
            return
        for name, m in MAPS.items():
            if m[sec - 1] == on[0]:
                self.votes[name] += 1
        self.last_vote = time.monotonic()
        a, b = sorted(self.votes.items(), key=lambda kv: -kv[1])
        if a[1] >= 3 and a[1] - b[1] >= 2 and a[0] != self.mapping():
            self.settings.update({"flagMap": a[0]})

    def update(self, d: dict, bounds) -> dict:
        s, t = d["session"], d.get("timing") or {}
        rows = d.get("standings") or []
        length = float(s.get("trackLength") or 0)
        phase, yellow = s.get("phase"), s.get("yellow") or 0
        items: list[dict] = []

        fcy = phase == 6 or 1 <= yellow <= 5
        raw = [bool(x) for x in (s.get("sectorFlags") or [False, False, False])][:3]
        raw += [False] * (3 - len(raw))
        m = MAPS[self.mapping()]
        local = [raw[m[i]] for i in range(3)]          # indexé S1..S3

        me = next((r for r in rows if r.get("me")), None)
        my_sec = t.get("sector") or (sector_of(me["d"] / length, bounds) if me and length else None)

        hazards = []
        if me and length > 0 and phase == 5 and not fcy and not (d.get("car") or {}).get("inPits"):
            for r in rows:
                if r.get("me") or r.get("inPits") or r.get("garage") or r.get("d") is None or r.get("spd") is None:
                    continue
                if r["spd"] < self.HAZARD_SPEED and 0 <= r["d"] <= length:
                    ahead = (r["d"] - me["d"]) % length
                    hazards.append({"d": r["d"], "ahead": ahead, "name": r.get("name"), "cls": r.get("cls")})
            self._vote(raw, hazards, bounds, length)
            hazards = sorted((h for h in hazards if h["ahead"] < self.HAZARD_RANGE), key=lambda h: h["ahead"])

        if phase == 7:
            items.append({"id": "red", "kind": "red", "level": 2, "text": "Drapeau rouge — session arrêtée"})
        elif fcy:
            items.append({"id": "fcy", "kind": "yellow", "level": 1, "text": FCY_TEXT.get(yellow, "Full course yellow / Safety car")})
        else:
            for i, on in enumerate(local):
                if not on:
                    continue
                sec = i + 1
                if my_sec == sec:
                    items.append({"id": f"y{sec}", "kind": "yellow", "level": 2, "text": f"Jaune dans TON secteur (S{sec})"})
                elif my_sec and sec == my_sec % 3 + 1:
                    items.append({"id": f"y{sec}", "kind": "yellow", "level": 1, "text": f"Jaune dans le prochain secteur (S{sec})"})
                else:
                    items.append({"id": f"y{sec}", "kind": "yellow", "level": 0, "text": f"Jaune secteur S{sec}"})
            if hazards:
                h = hazards[0]
                sec = sector_of(h["d"] / length, bounds)
                items.append({"id": "hazard", "kind": "yellow", "level": 2 if h["ahead"] < 500 else 1,
                              "text": f"Voiture à l'arrêt à {int(round(h['ahead'], -1))} m" + (f" (S{sec})" if sec else "")})
        if t.get("flag") == 6:
            items.append({"id": "blue", "kind": "blue", "level": 1, "text": "Drapeau bleu — laisse passer"})
        if phase == 8:
            items.append({"id": "over", "kind": "green", "level": 0, "text": "Session terminée"})
        elif phase == 4:
            items.append({"id": "start", "kind": "green", "level": 0, "text": "Départ imminent"})
        return {"fcy": fcy, "local": local, "mySector": my_sec, "map": self.mapping(),
                "votes": dict(self.votes), "items": items}
