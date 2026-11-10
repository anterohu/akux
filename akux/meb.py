"""Volkswagen-konsernin MEB-alusta (VW ID.3, ID.4, ID.5, Škoda Enyaq, Audi Q4 e-tron, Cupra Born).

Akun tiedot luetaan kyselyinä akunhallinnalta (osoite 17FC007B, vastaus 17FE007B; 29-bittiset tunnisteet,
OBD-protokolla 7). Kyselyt ja skaalaukset perustuvat avoimiin lähteisiin: evDash (MIT-lisenssi, CarVWID3)
ja Battery-Emulator (MEB-akun tulkinta). Molemmissa skaalaukset ovat samat.

Vastausten arvot (tavut kyselyn tunnisteen jälkeen):
    22 028C  varaustila (akunhallinta): tavu / 2,5 %; näytön varaustila tavu · 0,4425 − 6,1947 %
    22 1E3B  akun jännite: u16 / 4 V
    22 1E3D  virta: (u32 − 150 000) / 100 A, positiivinen = purku
    22 1E0E / 1E0F  korkein / matalin lämpötila: u16 / 64 °C
    22 1E32  elinkaarilaskurit: [8..11] ladattu, [12..15] purettu (etumerkillinen), yksikkö 1/8583,07 kWh
    22 1E40 … 1EAB  kennon 1–108 jännite: u16 + 1000 mV; 0FFE = kennoa ei ole
    22 50CE  akunhallinnan kuntoarvio (SOH) 1/100 % (vain uudemmissa ohjelmistoversioissa)
    Mittaristo 17FC0076: 22 295A mittarilukema (u24 km), 22 F802 valmistenumero.
    Yhdyskäytävä 710: 22 2AB2 akun suurin energiasisältö, u32 / 1310,77 kWh.

Kennojä kysytään yksi kerrallaan, joten koko akun kennokierros kestää noin 10 sekuntia.
"""
from __future__ import annotations

PLATFORM = "meb"
NIMI = "Volkswagen-konsernin MEB"
MERKIT = ("Volkswagen", "Škoda", "Audi", "Cupra")
BMS = "17FC007B"
METER = "17FC0076"
GATEWAY = "710"

M_SOC = 0x7B028C
M_V = 0x7B1E3B
M_I = 0x7B1E3D
M_TMAX = 0x7B1E0E
M_TMIN = 0x7B1E0F
M_LIFE = 0x7B1E32
M_SOH = 0x7B50CE
M_CELL0 = 0x7B1E40                    # kenno 1; kenno k = M_CELL0 + k - 1
M_ODO = 0x76295A
M_VIN = 0x76F802
M_ENERGY = 0x712AB2
MAX_CELLS = 108

TUNNISTEET = [M_V, M_I, M_SOC, M_TMAX, M_TMIN, M_CELL0, M_LIFE, M_SOH, M_ENERGY, M_ODO, M_VIN]
PAKOLLISET = [M_V, M_I, M_SOC, M_CELL0]
KUVAUS = {
    M_V: "Akun jännite", M_I: "Akun virta", M_SOC: "Varaustila", M_TMAX: "Korkein lämpötila",
    M_TMIN: "Matalin lämpötila", M_CELL0: "Kennojännitteet", M_LIFE: "Elinkaaren energialaskurit",
    M_SOH: "Akunhallinnan kuntoarvio", M_ENERGY: "Akun suurin energiasisältö", M_ODO: "Mittarilukema",
    M_VIN: "Valmistenumero",
}
NAYTTO = {M_V: "BMS 221E3B", M_I: "BMS 221E3D", M_SOC: "BMS 22028C", M_TMAX: "BMS 221E0E", M_TMIN: "BMS 221E0F",
          M_CELL0: "BMS 221E40–", M_LIFE: "BMS 221E32", M_SOH: "BMS 2250CE", M_ENERGY: "710 222AB2",
          M_ODO: "17FC0076 22295A", M_VIN: "17FC0076 22F802"}

RESOLUUTIO_MV = 1.0
ITSEPURKAUS_OK = True
ELINKAARILASKURIT = True
PROTOKOLLA = "7"                      # ISO 15765-4, 29-bittiset tunnisteet, 500 kbit/s
RX = {BMS: "17FE007B", METER: "17FE0076", GATEWAY: None}
LAHDE = "avoimiin MEB-alustan tietolähteisiin (evDash ja Battery-Emulator)"
OHJE = {"liitin": "OBD-II-diagnostiikkaliitin",
        "ohje": "Diagnostiikkaliitin on kuljettajan jalkatilassa kojelaudan alla; välikaapelia ei tarvita. Valitse "
                "yhdistettäessä auton malli ja akun koko. Akunhallinta vastaa kyselyihin, kun auto on käynnistetty "
                "tai latautuu. Mittauksen lepojaksojen lopussa auto on käynnistettävä hetkeksi, jotta loppuarvot "
                "saadaan luettua.",
        "varmistettu": False}
SOH_HUOM = ("{gen} akunhallinta ilmoittaa akun kuntoarvion vain uudemmissa ohjelmistoversioissa. Jos sitä ei "
            "saatu, akunhallinnan energia-arvio on luettu akun suurimmasta energiasisällöstä.")


def requests_for(model: dict) -> tuple[list, list]:
    cells = model.get("sarjakennot") or MAX_CELLS
    core = [(BMS, "221E3B", M_V), (BMS, "221E3D", M_I)]
    loop = []
    for k0 in range(0, cells, 8):
        loop += core
        loop += [(BMS, f"22{0x1E40 + k:04X}", M_CELL0 + k) for k in range(k0, min(k0 + 8, cells))]
    loop += core + [(BMS, "22028C", M_SOC), (BMS, "221E0E", M_TMAX), (BMS, "221E0F", M_TMIN)]
    rare = [(METER, "22F802", M_VIN), (METER, "22295A", M_ODO), (BMS, "221E32", M_LIFE),
            (BMS, "2250CE", M_SOH), (GATEWAY, "222AB2", M_ENERGY)]
    return loop, rare


def decoder_opts(model: dict) -> dict:
    return {"cells": model.get("sarjakennot"), "ref_kwh": model["viite_kwh"], "malli_id": model["id"]}


def simulator(model: dict, **opts):
    from .simulator import MebSimulator
    return MebSimulator(**opts)


# ----------------------------------------------------------------------
def _u(d, i, n):
    return int.from_bytes(bytes(d[i:i + n]), "big")


def _emit(dec, t):
    st = dec.state
    if st.pack_v is not None and st.pack_i is not None:
        for fn in list(dec._hv_listeners):
            dec._pending.append((fn, (t, st.pack_v, st.pack_i)))


def _v(dec, t, d):
    if len(d) >= 2:
        v = _u(d, 0, 2) / 4
        if 150.0 < v < 900.0:
            dec.state.pack_v = v


def _i(dec, t, d):
    if len(d) >= 4:
        i = (_u(d, 0, 4) - 150000) / 100
        if -1500 < i < 1500:
            st = dec.state
            st.pack_i = i
            st.power_state = "lataus" if i < -1.0 else None
            _emit(dec, t)


def _soc(dec, t, d):
    if len(d) >= 1:
        st = dec.state
        soc = d[0] / 2.5
        if 0 <= soc <= 100:
            st.soc_avg = st.soc_min = st.soc_max = soc
            ui = d[0] * 0.4425 - 6.1947
            st.soc_ui = max(0.0, min(100.0, ui))
            if st.nfp_kwh:
                st.nominal_remaining_kwh = st.nfp_kwh * soc / 100


def _temp(which):
    def h(dec, t, d):
        if len(d) >= 2:
            c = _u(d, 0, 2) / 64
            if c > 512:
                c -= 1024                   # etumerkillinen arvo
            if -40 <= c <= 80:
                setattr(dec.state, which, c)
    return h


def _cell(k):
    def h(dec, t, d):
        if len(d) < 2:
            return
        raw = _u(d, 0, 2)
        n = dec.hk.get("cells")
        if raw == 0x0FFE:
            # kennoa ei ole: akun kennomäärä selviää ensimmäisestä puuttuvasta kennosta (84, 96 tai 104)
            if k - 1 >= 80 and (not n or k <= n):
                dec.hk["cells"] = k - 1
                dec.state.brick_count = k - 1
            return
        mv = raw + 1000
        if 2000 <= mv <= 4500 and (not n or k <= n):
            dec._brick_value(t, k, mv / 1000)
            st = dec.state
            st.brick_count = n or max(st.bricks)
            vals = st.bricks
            hi = max(vals, key=lambda x: vals[x])
            lo = min(vals, key=lambda x: vals[x])
            st.cell_v_max, st.cell_v_max_num = vals[hi], hi
            st.cell_v_min, st.cell_v_min_num = vals[lo], lo
    return h


def _life(dec, t, d):
    if len(d) >= 16:
        chg = _u(d, 8, 4) / 8583.07123641215
        dis_raw = _u(d, 12, 4)
        dis = abs((dis_raw - (1 << 32) if dis_raw & 0x80000000 else dis_raw) / 8583.07123641215)
        if 0 < chg < 2_000_000 and 0 < dis < 2_000_000:
            st = dec.state
            st.total_charge_kwh, st.total_discharge_kwh = chg, dis
            st.counters_raw = (dis, chg)


def _set_nfp(dec, kwh):
    st = dec.state
    ref = dec.hk.get("ref_kwh")
    if ref and 0.4 * ref <= kwh <= 1.1 * ref:
        st.bol_kwh = ref
        st.nfp_kwh = kwh
        if st.soc_avg is not None:
            st.nominal_remaining_kwh = kwh * st.soc_avg / 100


def _soh(dec, t, d):
    if len(d) >= 2:
        soh = _u(d, 0, 2) / 100
        if 40 <= soh <= 110:
            dec.state.bms_soh_pct = soh
            dec.hk["soh_ok"] = True
            if dec.hk.get("ref_kwh"):
                _set_nfp(dec, dec.hk["ref_kwh"] * min(soh, 100.0) / 100)


def _energy(dec, t, d):
    if len(d) >= 4 and not dec.hk.get("soh_ok"):
        _set_nfp(dec, _u(d, 0, 4) / 1310.77)


def _odo(dec, t, d):
    if len(d) >= 3:
        km = _u(d, 0, 3)
        if 0 < km < 2_000_000:
            dec.state.odometer_km = float(km)


def _vin(dec, t, d):
    txt = bytes(b if 0x30 <= b <= 0x5A else 0x20 for b in d).decode("ascii", "ignore")
    m = __import__("re").search(r"[A-HJ-NPR-Z0-9]{17}", txt)
    if m:
        dec.state.vin = m.group(0)


HANDLERS = {M_V: _v, M_I: _i, M_SOC: _soc, M_TMAX: _temp("temp_max"), M_TMIN: _temp("temp_min"),
            M_LIFE: _life, M_SOH: _soh, M_ENERGY: _energy, M_ODO: _odo, M_VIN: _vin,
            **{M_CELL0 + k: _cell(k + 1) for k in range(MAX_CELLS)}}


# ----------------------------------------------------------------------
def encode(cid: int, **kw) -> bytes:
    """Vastausten tavut (esittelytila ja testit)."""
    if cid == M_V:
        return round(kw["v"] * 4).to_bytes(2, "big")
    if cid == M_I:
        return (round(kw["i"] * 100) + 150000).to_bytes(4, "big")
    if cid == M_SOC:
        return bytes([max(0, min(250, round(kw["soc"] * 2.5)))])
    if cid in (M_TMAX, M_TMIN):
        return (round(kw["c"] * 64) & 0xFFFF).to_bytes(2, "big")
    if M_CELL0 <= cid < M_CELL0 + MAX_CELLS:
        v = kw.get("v")
        return (0x0FFE if v is None else round(v * 1000) - 1000).to_bytes(2, "big")
    if cid == M_LIFE:
        d = bytearray(16)
        d[8:12] = round(kw["chg"] * 8583.07123641215).to_bytes(4, "big")
        d[12:16] = (-round(kw["dis"] * 8583.07123641215) & 0xFFFFFFFF).to_bytes(4, "big")
        return bytes(d)
    if cid == M_SOH:
        return round(kw["soh"] * 100).to_bytes(2, "big")
    if cid == M_ENERGY:
        return round(kw["kwh"] * 1310.77).to_bytes(4, "big")
    if cid == M_ODO:
        return int(kw["km"]).to_bytes(3, "big")
    if cid == M_VIN:
        return kw["vin"].encode("ascii")
    raise ValueError(cid)
