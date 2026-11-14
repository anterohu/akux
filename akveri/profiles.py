"""Automallipohjat ja auton tunnistus."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


PROFILE_FILE = Path(__file__).parent / "data" / "profiles.json"


@lru_cache(maxsize=1)
def load() -> dict:
    with open(PROFILE_FILE, encoding="utf-8") as f:
        return json.load(f)


def models() -> list[dict]:
    return load()["mallit"]


def chemistry(key: str) -> dict:
    return load()["kemiat"].get(key or "NCA", load()["kemiat"]["NCA"])


def warranty(model: dict | None) -> dict:
    key = (model or {}).get("takuu", "vakio")
    return load()["takuu"][key]


def get(model_id: str | None) -> dict | None:
    for m in models():
        if m["id"] == model_id:
            return m
    return None


def _cells_match(m: dict, n: int) -> bool:
    sc = m.get("sarjakennot")
    if sc is None:
        return False
    return n in sc if isinstance(sc, list) else n == sc


def identify(vin_info: dict | None = None, *, bol_kwh: float | None = None,
             brick_count: int | None = None, cell_v_max: float | None = None,
             soc: float | None = None, platform: str | None = None,
             nfp_kwh: float | None = None) -> tuple[dict | None, list[str]]:
    """Valitsee todennäköisimmän mallipohjan. Palauttaa (pohja, perustelut)."""
    reasons: list[str] = []
    cands = models()
    if platform:
        by_plat = [m for m in cands if m.get("alusta", "m3") == platform]
        if by_plat:
            cands = by_plat
    brand = (vin_info or {}).get("merkki") if (vin_info or {}).get("kelvollinen") else None
    if brand:
        # Valmistaja tiedetään varmasti VIN:n valmistajatunnuksesta: muiden merkkien pohjia ei koskaan valita
        cands = [m for m in cands if m.get("merkki", "Tesla") == brand]
        if not cands:
            return None, [f"merkkiä {brand} ei tueta"]
        reasons.append(f"valmistaja {brand}")
    if vin_info and vin_info.get("kelvollinen"):
        mk = vin_info.get("malli_koodi")
        by_model = [m for m in cands if mk and mk in m["malli_koodi"]]
        cands = by_model or cands
        year = vin_info.get("vuosimalli")
        if year:
            by_year = [m for m in cands if year in m["vuodet"]]
            if by_year:
                cands = by_year
                reasons.append(f"vuosimalli {year}")
        plant = vin_info.get("tehdas")
        if plant:
            by_plant = [m for m in cands if plant in m["tehtaat"]]
            if by_plant:
                cands = by_plant
                reasons.append(f"valmistustehdas {plant}")
        if vin_info.get("akku_koodi") == "F" and mk in ("3", "Y"):
            lfp = [m for m in cands if m["kemia"] == "LFP"]
            if lfp:
                cands = lfp
                reasons.append("VIN:n akkutunnus F (LFP)")
        veto = vin_info.get("veto")
        if veto:
            by_drive = [m for m in cands if veto in m["veto"]]
            if by_drive:
                cands = by_drive
                reasons.append(f"voimalinja {vin_info.get('voimalinja')}")

    if brick_count:
        # Tarkka osuma ensin; pohjat, joiden kennoryhmämäärää ei tunneta, kelpaavat varalle
        by_cells = [m for m in cands if _cells_match(m, brick_count)] or \
            [m for m in cands if m.get("sarjakennot") is None]
        if by_cells:
            cands = by_cells
            reasons.append(f"{brick_count} sarjaan kytkettyä kennoryhmää")
        elif brick_count >= 100:
            lfp = [m for m in models() if m["kemia"] == "LFP"]
            cands = lfp or cands
            reasons.append(f"{brick_count} kennoryhmää viittaa LFP-akkuun")

    if cell_v_max is not None and soc is not None and soc > 90:
        if cell_v_max < 3.7:
            lfp = [m for m in cands if m["kemia"] == "LFP"]
            if lfp:
                cands = lfp
                reasons.append("kennojännite täydessä akussa viittaa LFP-akkuun")

    if bol_kwh and len(cands) > 1:
        cands = sorted(cands, key=lambda m: abs(m["viite_kwh"] - bol_kwh))
        reasons.append(f"akunhallinnan alkuperäinen energia {bol_kwh:.1f} kWh")
    elif nfp_kwh and len(cands) > 1:
        # Ilman alkuperäistä energiaa valitaan pienin akku, johon nykyinen energia mahtuu.
        # Akun energia voi ikääntyessä vain pienentyä.
        fits = sorted((m for m in cands if m["viite_kwh"] >= nfp_kwh * 0.99), key=lambda m: m["viite_kwh"])
        if fits:
            cands = fits + [m for m in cands if m not in fits]
            reasons.append(f"akunhallinnan täyden akun energia {nfp_kwh:.1f} kWh")

    if brand and brand != "Tesla" and len({m["viite_kwh"] for m in cands}) > 1:
        # Hyundain ja Kian VIN ei kerro akun kokoa: malli valitaan käsin, ettei väärää viitearvoa käytetä
        return None, reasons + ["malli ja akun koko valitaan luettelosta"]
    return (cands[0] if cands else None), reasons


def connection_guide(malli_koodi: str | None, vuosimalli: int | None = None,
                     platform: str | None = None) -> dict:
    """Mihin sovitin kytketään ja millainen välikaapeli tarvitaan."""
    mk = (malli_koodi or "").upper()
    y = vuosimalli or 0
    from . import polled
    pm = polled.module(platform)
    if pm:
        return dict(pm.OHJE)
    if mk in ("3", "Y"):
        if mk == "3" and y >= 2024 or mk == "Y" and y >= 2025:
            return {"liitin": "Diagnostiikkaliitin, uudistettu malli",
                    "ohje": "Uudistetussa mallissa (Model 3 vuodesta 2024, Model Y vuodesta 2025) liitin ja sen paikka "
                            "poikkeavat aiemmista. Varmista välikaapelin myyjältä, että kaapeli on tehty juuri tälle mallille. "
                            "Jalkatilan OBD-liitäntä ei välitä akun tietoja.",
                    "varmistettu": False}
        pins = "20-pinninen" if y and y <= 2020 else "26-pinninen"
        return {"liitin": f"Diagnostiikkaliitin, {pins}",
                "ohje": "Liitin on keskikonsolin takapäässä takamatkustajien puolella paneelin takana. Vuosien 2019–2020 "
                        "autoissa liitin on 20-pinninen ja 2021 alkaen 26-pinninen. Vuodenvaihteen 2020–2021 autoissa "
                        "laske pinnit tai hanki sarja, jossa on molemmat kaapelit. Jalkatilan OBD-liitäntä ei välitä "
                        "akun tietoja.",
                "varmistettu": True}
    if mk in ("S", "X"):
        if platform == "sx" or (y and y <= 2020):
            return {"liitin": "Voimalinjan CAN-väylän diagnostiikkaliitin",
                    "ohje": "Model S 2012–2021 ja Model X 2015–2021 tarvitsevat välikaapelin, joka tuo voimalinjan "
                            "CAN-väylän OBD-liitännän nastoihin 6 ja 14. Liitin on erilainen vuosien 2012–09/2015 Model S:ssä "
                            "ja sitä uudemmissa (12-napainen musta liitin). Tarkista liittimen paikka ja kaapelin sopivuus "
                            "välikaapelin ohjeesta.",
                    "varmistettu": False}
        return {"liitin": "Diagnostiikkaliitin (Model S / X 2021–)",
                "ohje": "Vuosina 2021–04/2024 valmistetuissa autoissa sininen 20-napainen liitin on kosketusnäytön alla "
                        "langattoman latausalustan yläpuolella. Tarvitaan Model S/X:lle tehty välikaapeli, joka tuo "
                        "ajoneuvon CAN-väylän nastoihin 6 ja 14; Model 3:n kaapeli ei välttämättä sovi. Toukokuusta 2024 "
                        "valmistetuissa autoissa sovitin kytketään suoraan kuljettajan jalkatilan OBD-liitäntään.",
                "varmistettu": False}
    if mk == "C":
        return {"liitin": "Cybertruck",
                "ohje": "AKVERI ei vielä tue Cybertruckia.",
                "varmistettu": False}
    return {"liitin": "Diagnostiikkaliitin",
            "ohje": "Kytke sovitin auton diagnostiikkaliittimeen mallille sopivalla välikaapelilla.",
            "varmistettu": False}


def ocv_to_soc(cell_v: float, chem_key: str) -> float | None:
    chem = chemistry(chem_key)
    if not chem.get("ocv_soc_arvio"):
        return None
    curve = chem["ocv"]
    if cell_v <= curve[0]:
        return 0.0
    if cell_v >= curve[-1]:
        return 100.0
    for i in range(len(curve) - 1):
        a, b = curve[i], curve[i + 1]
        if a <= cell_v <= b:
            return 10 * i + 10 * (cell_v - a) / (b - a)
    return None


def mean_ocv(chem_key: str, soc_from: float, soc_to: float) -> float:
    """Kennon keskimääräinen lepojännite varaustilavälillä (lineaarinen interpolointi)."""
    curve = chemistry(chem_key)["ocv"]

    def v(s):
        s = min(100.0, max(0.0, s))
        i = min(9, int(s // 10))
        return curve[i] + (curve[i + 1] - curve[i]) * (s - 10 * i) / 10

    if soc_to <= soc_from:
        return v(soc_from)
    steps = 50
    total = 0.0
    for k in range(steps):
        s = soc_from + (soc_to - soc_from) * (k + 0.5) / steps
        total += v(s)
    return total / steps


def ocv_slope(chem_key: str, soc: float) -> float:
    """Lepojännitekäyrän jyrkkyys varaustilassa soc (mV kennoa kohden yhtä %-yksikköä kohden)."""
    curve = chemistry(chem_key)["ocv"]

    def v(s):
        s = min(100.0, max(0.0, s))
        i = min(9, int(s // 10))
        return curve[i] + (curve[i + 1] - curve[i]) * (s - 10 * i) / 10
    lo, hi = max(0.0, soc - 5), min(100.0, soc + 5)
    return (v(hi) - v(lo)) / (hi - lo) * 1000 if hi > lo else 1.0
