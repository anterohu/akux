"""Nissan Leaf: akun tiedot luetaan kyselyinä akunhallinnalta (LBC, osoite 79B, vastaus 7BB).

Kyselyt ja arvojen sijainnit perustuvat avoimiin lähteisiin: Open Vehicle Monitoring System (MIT-lisenssi,
vehicle_nissanleaf), Battery-Emulator (Nissan Leaf -akun tulkinta) ja py-nissan-leaf-obd-ble (ELM327-
sovittimella toimiva toteutus). Kaikissa lähteissä ryhmien 01, 02, 04 ja 61 rakenne on sama.

Ryhmä 01 (palvelu 21, vastauksen tavut ilman alkua 61 01):
    [0..3]  virta, etumerkillinen 32-bittinen, 1/1024 A
    [18..19] akun jännite, 1/100 V
    ZE0 / AZE0 (39 tai 41 tavua): [26..27] Hx 1/100 %, [28..31] varaustila 1/10000 %, [32..35] Ah 1/10000
    ZE1 (51 tavua):               [28..29] Hx 1/102,4 %, [30..33] varaustila 1/10000 %, [34..37] Ah 1/10000
Ryhmä 02: 96 kennoa, 2 tavua kukin, millivoltteina (1 mV:n tarkkuus); [192..193] akun jännite 1/100 V.
Ryhmä 04: lämpöanturit, °C tavuissa 2, 5, 8 ja 11 (FF = anturia ei ole).
Ryhmä 61 (vain ZE1, 40 ja 62 kWh): [2..3] akunhallinnan kuntoarvio (SOH) 1/100 %.
Valmistenumero: ohjauslaite 797, kysely 21 81. Mittarilukema: mittaristo 743, kysely 22 0E 01.

Virran etumerkkiä ei ole yksiselitteisesti dokumentoitu. Tulkitsija päättelee sen varaustilan muutoksesta:
kun varaustila on muuttunut vähintään 0,5 %-yksikköä, purkuvirran suunta lukitaan. Ennen lukitusta
käytetään yleisintä tulkintaa (negatiivinen = purku).
"""
from __future__ import annotations

PLATFORM = "leaf"
NIMI = "Nissan Leaf"
MERKIT = ("Nissan",)
BMS = "79B"
VCM = "797"
METER = "743"

L_MAIN = 0x7B2101
L_CELLS = 0x7B2102
L_TEMP = 0x7B2104
L_SOH = 0x7B2161
L_VIN = 0x7A2181
L_ODO = 0x76220E

TUNNISTEET = [L_MAIN, L_CELLS, L_TEMP, L_SOH, L_ODO, L_VIN]
PAKOLLISET = [L_MAIN, L_CELLS]
KUVAUS = {
    L_MAIN: "Akun jännite, virta, varaustila ja kapasiteetti (Ah)",
    L_CELLS: "Kennojännitteet",
    L_TEMP: "Akun lämpötilat",
    L_SOH: "Akunhallinnan kuntoarvio (40 ja 62 kWh)",
    L_ODO: "Mittarilukema",
    L_VIN: "Valmistenumero",
}
NAYTTO = {L_MAIN: "79B 2101", L_CELLS: "79B 2102", L_TEMP: "79B 2104", L_SOH: "79B 2161",
          L_ODO: "743 220E01", L_VIN: "797 2181"}

RESOLUUTIO_MV = 1.0
ITSEPURKAUS_OK = True
ELINKAARILASKURIT = False     # energia lasketaan jännitteestä ja virrasta
RX = {BMS: "7BB", VCM: "79A", METER: "763"}
LAHDE = ("avoimiin Nissan Leaf -tietolähteisiin (Open Vehicle Monitoring System, Battery-Emulator ja "
         "py-nissan-leaf-obd-ble)")
OHJE = {"liitin": "OBD-II-diagnostiikkaliitin",
        "ohje": "Leafin diagnostiikkaliitin on kuljettajan jalkatilassa ohjauspyörän alapuolella; välikaapelia ei "
                "tarvita. Valitse yhdistettäessä auton malli ja akun koko. Akunhallinta vastaa kyselyihin, kun auto "
                "on käynnistetty (READY tai virta päällä) tai latautuu. Mittauksen lepojaksojen lopussa auto on "
                "käynnistettävä hetkeksi, jotta loppuarvot saadaan luettua.",
        "varmistettu": False}
SOH_HUOM = ("{gen} akunhallinta ilmoittaa akun jäljellä olevan kapasiteetin ampeeritunteina (40 ja 62 kWh:n "
            "akuissa myös kuntoprosenttina). Akunhallinnan täyden akun energia on laskettu tästä ja mallin "
            "ilmoitetusta kapasiteetista.")


def requests_for(model: dict) -> tuple[list, list]:
    loop = [(BMS, "2101", L_MAIN), (BMS, "2102", L_CELLS), (BMS, "2101", L_MAIN), (BMS, "2104", L_TEMP)]
    if model.get("kyselyryhma") == "ze1":
        loop += [(BMS, "2101", L_MAIN), (BMS, "2161", L_SOH)]
    rare = [(VCM, "2181", L_VIN), (METER, "220E01", L_ODO)]
    return loop, rare


def decoder_opts(model: dict) -> dict:
    return {"cells": model.get("sarjakennot") or 96, "ref_kwh": model["viite_kwh"], "ref_ah": model.get("viite_ah"),
            "malli_id": model["id"]}


def simulator(model: dict, **opts):
    from .simulator import LeafSimulator
    return LeafSimulator(ze1=model.get("kyselyryhma") == "ze1", ref_ah=model.get("viite_ah"), **opts)


# ----------------------------------------------------------------------
def _u(d, i, n):
    return int.from_bytes(bytes(d[i:i + n]), "big")


def _s32(d, i):
    v = _u(d, i, 4)
    return v - (1 << 32) if v & 0x80000000 else v


def _s8(b):
    return b - 256 if b > 127 else b


def _update_nfp(dec):
    st = dec.state
    ref = dec.hk.get("ref_kwh")
    soh = st.bms_soh_pct
    if soh is None and dec.hk.get("ah") and dec.hk.get("ref_ah"):
        soh = dec.hk["ah"] / dec.hk["ref_ah"] * 100
    if ref and soh and 40 <= soh <= 115:
        st.bol_kwh = ref
        st.nfp_kwh = ref * min(soh, 100.0) / 100
        if st.soc_avg is not None:
            st.nominal_remaining_kwh = st.nfp_kwh * st.soc_avg / 100


def _learn_sign(dec, t, raw_i, soc):
    """Purkuvirran suunta päätellään varaustilan muutoksesta (ks. moduulin kuvaus)."""
    hk = dec.hk
    if hk.get("sign_locked"):
        return
    last = hk.get("_sl_t")
    hk["_sl_t"] = t
    if last is None or soc is None:
        hk["_sl_soc0"], hk["_sl_ah"] = soc, 0.0
        return
    dt = t - last
    if 0 < dt < 30:
        hk["_sl_ah"] = hk.get("_sl_ah", 0.0) + raw_i * dt / 3600
    dsoc = soc - (hk.get("_sl_soc0") if hk.get("_sl_soc0") is not None else soc)
    ah = hk.get("_sl_ah", 0.0)
    if abs(dsoc) >= 0.5 and abs(ah) >= 0.2:
        # varaustila laskee purussa: purun raakavirran etumerkki on sama kuin -ΔSOC:n
        hk["sign"] = 1 if (ah > 0) == (dsoc < 0) else -1
        hk["sign_locked"] = True


def _main(dec, t, d):
    n = len(d)
    if n < 36:
        return
    st = dec.state
    v = _u(d, 18, 2) / 100
    if not (150.0 < v < 450.0):
        return
    raw_i = _s32(d, 0) / 1024
    if n not in (39, 41) and n < 48:
        return                                 # ZE1 vastaa käynnistyksen jälkeen hetken toisella rakenteella
    ze1 = n >= 48
    soc = (_u(d, 30, 4) if ze1 else _u(d, 28, 4)) / 10000
    ah = (_u(d, 34, 4) if ze1 and n >= 38 else _u(d, 32, 4)) / 10000
    soc = soc if 0 <= soc <= 100 else None
    _learn_sign(dec, t, raw_i, soc)
    i = raw_i * dec.hk.get("sign", -1)        # AKVERIn tiedoissa positiivinen = purku
    if soc is not None:
        st.soc_avg = st.soc_min = st.soc_max = soc
    if 5 < ah < 400:
        dec.hk["ah"] = ah
        _update_nfp(dec)
    st.pack_v, st.pack_i = v, i
    st.power_state = "lataus" if i < -1.0 and dec.hk.get("sign_locked") else None
    for fn in list(dec._hv_listeners):
        dec._pending.append((fn, (t, v, i)))


def _cells(dec, t, d):
    if len(d) < 192:
        return
    vals = []
    for k in range(96):
        mv = _u(d, 2 * k, 2)
        if 2000 <= mv <= 4500:
            dec._brick_value(t, k + 1, mv / 1000)
            vals.append((mv / 1000, k + 1))
    st = dec.state
    st.brick_count = dec.hk.get("cells") or 96
    if vals:
        (st.cell_v_max, st.cell_v_max_num), (st.cell_v_min, st.cell_v_min_num) = max(vals), min(vals)


def _temps(dec, t, d):
    if len(d) < 12:
        return
    ts = []
    for k in (0, 1, 2, 3):
        if _u(d, 3 * k, 2) == 0xFFFF or d[3 * k + 2] == 0xFF:
            continue
        c = _s8(d[3 * k + 2])
        if -40 <= c <= 80:
            ts.append(c)
    if ts:
        dec.state.temp_max, dec.state.temp_min = max(ts), min(ts)


def _soh(dec, t, d):
    if len(d) < 4:
        return
    soh = _u(d, 2, 2) / 100
    if 40 <= soh <= 115:
        dec.state.bms_soh_pct = soh
        _update_nfp(dec)


def _vin(dec, t, d):
    txt = bytes(b if 0x30 <= b <= 0x5A else 0x20 for b in d).decode("ascii", "ignore")
    m = __import__("re").search(r"[A-HJ-NPR-Z0-9]{17}", txt)
    if m:
        dec.state.vin = m.group(0)


def _odo(dec, t, d):
    if len(d) >= 3:
        km = _u(d, 0, 3)
        if 0 < km < 2_000_000:
            dec.state.odometer_km = float(km)


HANDLERS = {L_MAIN: _main, L_CELLS: _cells, L_TEMP: _temps, L_SOH: _soh, L_VIN: _vin, L_ODO: _odo}


# ----------------------------------------------------------------------
def encode_main(*, soc, v, i, ah, hx=95.0, ze1=True, sign=-1) -> bytes:
    """Ryhmän 01 vastaus ilman alkua 61 01 (esittelytila ja testit). i: positiivinen = purku."""
    d = bytearray(51 if ze1 else 39)
    d[0:4] = (round(i * sign * 1024) & 0xFFFFFFFF).to_bytes(4, "big")
    d[18:20] = round(v * 100).to_bytes(2, "big")
    d[20:22] = (12600).to_bytes(2, "big")
    if ze1:
        d[28:30] = round(hx * 102.4).to_bytes(2, "big")
        d[30:34] = round(soc * 10000).to_bytes(4, "big")
        d[34:38] = round(ah * 10000).to_bytes(4, "big")
    else:
        d[26:28] = round(hx * 100).to_bytes(2, "big")
        d[28:32] = round(soc * 10000).to_bytes(4, "big")
        d[32:36] = round(ah * 10000).to_bytes(4, "big")
    return bytes(d)


def encode_cells(volts: list, pack_v: float) -> bytes:
    d = bytearray(196)
    for k, v in enumerate(volts[:96]):
        d[2 * k:2 * k + 2] = round(v * 1000).to_bytes(2, "big")
    d[192:194] = round(pack_v * 100).to_bytes(2, "big")
    d[194:196] = round(pack_v * 100).to_bytes(2, "big")
    return bytes(d)


def encode_temps(temps: list) -> bytes:
    d = bytearray(b"\xff" * 14)
    for k, c in enumerate(temps[:4]):
        if c is None:
            continue
        d[3 * k:3 * k + 2] = (600).to_bytes(2, "big")
        d[3 * k + 2] = round(c) & 0xFF
    d[12], d[13] = round(temps[0]) & 0xFF, 0
    return bytes(d)


def encode_soh(soh: float) -> bytes:
    d = bytearray(329)
    d[2:4] = round(soh * 100).to_bytes(2, "big")
    return bytes(d)


def encode_vin(vin: str) -> bytes:
    return vin.encode("ascii") + b"\x00\x00"


def encode_odo(km: float) -> bytes:
    return int(km).to_bytes(3, "big") + b"\x00"
