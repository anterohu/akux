"""Automallipohjat ja auton tunnistus."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import vin as vinmod

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


def identify(vin_info: dict | None = None, *, bol_kwh: float | None = None,
             brick_count: int | None = None, cell_v_max: float | None = None,
             soc: float | None = None) -> tuple[dict | None, list[str]]:
    """Valitsee todennäköisimmän mallipohjan. Palauttaa (pohja, perustelut)."""
    reasons: list[str] = []
    cands = models()
    if vin_info and vin_info.get("kelvollinen"):
        mk = vin_info.get("malli_koodi")
        cands = [m for m in cands if m["malli_koodi"] == mk] or cands
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
        if vin_info.get("akku_koodi") == "F":
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
        by_cells = [m for m in cands if m["sarjakennot"] == brick_count]
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

    return (cands[0] if cands else None), reasons


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
