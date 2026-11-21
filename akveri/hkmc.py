"""Hyundai ja Kia: akun tiedot luetaan kyselyinä akunhallinnalta (BMS, osoite 7E4).

Teslan akunhallinta lähettää tietonsa väylälle jatkuvasti, mutta Hyundai ja Kia vastaavat vain kyselyihin.
Sovitin kysyy tiedot vuorotellen, ja vastaukset käsitellään samoina mittaustietoina kuin Teslan viestit.

Kyselyt ja arvojen sijainnit perustuvat avoimiin, laajasti käytettyihin lähteisiin:
JejuSoul: OBD-PIDs-for-HKMC-EVs (Ioniq Electric, Kona, e-Niro, Soul) ja evDash (E-GMP: Ioniq 5, Ioniq 6, EV6).
Kaikissa malleissa pääkyselyn (01 01) rakenne on sama; erot ovat kennomäärässä ja kennokyselyissä.

Vastaukset välitetään tulkitsijalle virtuaalisilla tunnisteilla (palvelu ja tunniste yhdessä, esimerkiksi
0x220101). Ioniq Electric 28 kWh käyttää palvelua 21 (2101); sen vastaus välitetään samalla tunnisteella,
koska tietojen järjestys on sama.
"""
from __future__ import annotations

PLATFORM = "hkmc"
BMS = "7E4"
CLUSTER = "7C6"              # mittaristo: mittarilukema
BROADCAST = "7DF"            # OBD-standardin yleiskysely: valmistenumero

P_MAIN = 0x220101            # jännite, virta, varaustila, lämpötilat, elinkaarilaskurit
P_STATUS = 0x220105          # akunhallinnan kuntoarvio (SOH), näytön varaustila
P_CELLS = [0x220102, 0x220103, 0x220104, 0x22010A, 0x22010B, 0x22010C]   # 32 kennoa kussakin
P_ODO = 0x22B002
P_VIN = 0x0902

KUNTO_TUNNISTEET = (P_STATUS,)
TUNNISTEET = [P_MAIN, P_STATUS, P_CELLS[0], P_ODO, P_VIN]
PAKOLLISET = [P_MAIN, P_STATUS, P_CELLS[0]]
KUVAUS = {
    P_MAIN: "Akun jännite, virta, varaustila ja energialaskurit",
    P_STATUS: "Akunhallinnan kuntoarvio ja näytön varaustila",
    P_CELLS[0]: "Kennojännitteet",
    P_CELLS[1]: "Kennojännitteet",
    P_CELLS[2]: "Kennojännitteet",
    P_CELLS[3]: "Kennojännitteet",
    P_CELLS[4]: "Kennojännitteet",
    P_CELLS[5]: "Kennojännitteet",
    P_ODO: "Mittarilukema",
    P_VIN: "Valmistenumero",
}

# Mallikohtainen kyselyryhmä: palvelu (21 tai 22), kennosivujen määrä ja lisäkennot tilakyselyssä.
RYHMAT = {
    "ioniq28": {"palvelu": "21", "sivut": 3, "lisakennot": 0},
    "ioniq38": {"palvelu": "22", "sivut": 3, "lisakennot": 0},  # uudistettu Ioniq Electric (2019–2022), 88 kennoa
    "kona": {"palvelu": "22", "sivut": 3, "lisakennot": 2},     # Kona, e-Niro, Soul 64 kWh: 98 kennoa
    "egmp": {"palvelu": "22", "sivut": 6, "lisakennot": 0},     # Ioniq 5, Ioniq 6, EV6
}


def requests(ryhma: str, cells: int | None) -> tuple[list, list]:
    """Kyselyt (osoite, komento, virtuaalitunniste). Palauttaa (toistuvat, harvat).

    Pääkysely on joka toinen kysely, jotta jännite ja virta saadaan riittävän tiheästi energian laskentaan.
    """
    g = RYHMAT[ryhma]
    svc = g["palvelu"]

    def cmd(pid: int) -> str:
        return f"{svc}{pid & 0xFF:02X}" if svc == "21" else f"22{pid & 0xFFFF:04X}"

    pages = g["sivut"]
    if cells and ryhma == "egmp":
        pages = min(6, -(-cells // 32))
    loop = []
    for pid in P_CELLS[:pages] + [P_STATUS]:
        loop.append((BMS, cmd(P_MAIN), P_MAIN))
        loop.append((BMS, cmd(pid), pid))
    rare = [(BROADCAST, "0902", P_VIN), (CLUSTER, "22B002", P_ODO)]
    return loop, rare


NIMI = "Hyundai ja Kia"
MERKIT = ("Hyundai", "Kia")
KENNOLUKUTAPA = "Akunhallinta ilmoittaa kennojännitteet 32 kennon ryhmissä 20 mV:n tarkkuudella ja lämpötilat moduuleittain."
RESOLUUTIO_MV = 20.0            # kennojännitteet 20 mV:n portain
ITSEPURKAUS_OK = False
ELINKAARILASKURIT = True
# Hyundain ja Kian akunhallinta pitää kuntoarvion (SOH) 100 %:ssa usein vuosia, vaikka kapasiteetti on jo alentunut.
# Tätä suurempaa lukemaa ei käytetä akun kuntona; kunto saadaan kapasiteettimittauksesta.
SOH_JUMISSA_YLI = 99.5
# Testit, joita ei tehdä tälle alustalle, ja syy, joka näytetään käyttäjälle.
EI_TESTIT = {
    "pikatarkastus": "Pikatarkastusta ei tehdä Hyundaille eikä Kialle: akunhallinnan kuntoarvio pysyy usein 100 "
                     "%:ssa, vaikka akku on jo kulunut. Akun kunto mitataan kapasiteettimittauksella.",
    "itsepurkaus": "Itsepurkaustestiä ei tehdä Hyundaille eikä Kialle: akunhallinta ilmoittaa kennojännitteet 20 "
                   "mV:n tarkkuudella, mutta itsepurkauksen havaitseminen vaatii alle 1 mV:n tarkkuuden.",
}
RX = {BMS: "7EC", CLUSTER: "7CE"}
LAHDE = ("avoimiin, laajasti käytettyihin Hyundai- ja Kia-sähköautojen tietolähteisiin (OBD-PIDs-for-HKMC-EVs "
         "ja evDash)")
OHJE = {"liitin": "OBD-II-diagnostiikkaliitin",
        "ohje": "Hyundain ja Kian diagnostiikkaliitin on kuljettajan jalkatilassa kojelaudan alla; välikaapelia "
                "ei tarvita. Valitse yhdistettäessä auton malli. Akunhallinta vastaa kyselyihin vain, kun auto on "
                "käynnistetty (READY tai virta päällä) tai latautuu. Mittauksen lepojaksojen lopussa auto on "
                "käynnistettävä hetkeksi, jotta loppuarvot saadaan luettua.",
        "varmistettu": False}
SOH_HUOM = ("{gen} akunhallinta ilmoittaa akun kunnon prosentteina. Akunhallinnan ilmoittama täyden akun energia "
            "on laskettu tästä prosentista ja mallin ilmoitetusta kapasiteetista.")


def requests_for(model: dict) -> tuple[list, list]:
    return requests(model["kyselyryhma"], model.get("sarjakennot"))


def vaihtoehto_for(model: dict) -> list:
    """Toinen kyselytapa (palvelu 21 tai 22), jos akunhallinta ei vastaa mallin oletuskyselyyn.

    Saman mallin eri vuosien akunhallinnat voivat käyttää eri palvelua. Vastausten sisältö on sama, joten
    tulkinta ei muutu.
    """
    g = dict(RYHMAT[model["kyselyryhma"]])
    toinen = "22" if g["palvelu"] == "21" else "21"
    RYHMAT["_vaihto"] = {**g, "palvelu": toinen}
    try:
        loop, _ = requests("_vaihto", model.get("sarjakennot"))
    finally:
        RYHMAT.pop("_vaihto", None)
    return loop


def decoder_opts(model: dict) -> dict:
    g = RYHMAT[model["kyselyryhma"]]
    # Kennot 97 ja 98 ovat tilakyselyssä vain 98-kennoisissa akuissa (64 kWh); muissa tavut ovat muuta tietoa.
    lisa = g["lisakennot"] if model.get("sarjakennot") == 98 else 0
    return {"cells": model.get("sarjakennot"), "ref_kwh": model["viite_kwh"], "lisakennot": lisa,
            "malli_id": model["id"]}


def simulator(model: dict, **opts):
    from .simulator import HkmcSimulator
    return HkmcSimulator(ryhma=model["kyselyryhma"], **opts)


# ----------------------------------------------------------------------
def _u(d, i, n):
    return int.from_bytes(bytes(d[i:i + n]), "big")


def _s8(b):
    return b - 256 if b > 127 else b


def _s16(d, i):
    v = _u(d, i, 2)
    return v - 65536 if v > 32767 else v


def _main(dec, t, d):
    if len(d) < 46:
        return
    st = dec.state
    v = _u(d, 12, 2) / 10
    i = _s16(d, 10) / 10              # positiivinen = purku, kuten Teslan tiedoissa
    if not (100.0 < v < 900.0):
        return
    soc = d[4] / 2
    if 0 <= soc <= 100:
        st.soc_avg = soc
        st.soc_min = st.soc_max = soc
    st.temp_max, st.temp_min = _s8(d[14]), _s8(d[15])
    if d[23] and d[25]:
        st.cell_v_max, st.cell_v_max_num = d[23] / 50, d[24]
        st.cell_v_min, st.cell_v_min_num = d[25] / 50, d[26]
    cec, ced = _u(d, 38, 4) / 10, _u(d, 42, 4) / 10
    if 0 < cec < 2_000_000 and 0 < ced < 2_000_000:
        st.total_charge_kwh, st.total_discharge_kwh = cec, ced
        st.counters_raw = (ced, cec)
    st.power_state = "lataus" if d[9] & 0x80 else None
    st.pack_v, st.pack_i = v, i
    if st.nfp_kwh and st.soc_avg is not None:
        st.nominal_remaining_kwh = st.nfp_kwh * st.soc_avg / 100
    for fn in list(dec._hv_listeners):
        dec._pending.append((fn, (t, v, i)))


def _cells(page):
    def h(dec, t, d):
        # Osa akunhallinnoista jättää sivun lopusta täytetavuja pois, joten luetaan ne kennot, jotka vastauksessa on.
        if len(d) < 5:
            return
        n = dec.hk.get("cells")
        for j in range(min(32, len(d) - 4)):
            k = page * 32 + j + 1
            if n and k > n:
                break
            raw = d[4 + j]
            if 100 <= raw <= 225:           # 2,0–4,5 V; muu arvo tarkoittaa puuttuvaa kennoa
                dec._brick_value(t, k, raw / 50)
                dec.hk["_max_sivuilta"] = max(dec.hk.get("_max_sivuilta", 0), k)
        dec.hk.setdefault("_sivut", set()).add(page)
        _tunnista_kennomaara(dec)
        _count(dec)
    return h


def _tunnista_kennomaara(dec):
    """Korjaa kennomäärän auton ilmoittaman mukaiseksi.

    Jos yhdistettäessä on valittu malli, jossa on enemmän kennoja kuin autossa (esimerkiksi Kona-asetukset
    Ioniq Electricissä), kennosivujen lopussa ei ole jännitteitä. Kun kaikki sivut on luettu kahdesti, kennomäärä
    asetetaan sivuilta luettujen kennojen mukaan, jotta mittaus ei jää odottamaan kennoja, joita autossa ei ole.
    """
    n = dec.hk.get("cells")
    lisa = dec.hk.get("lisakennot") or 0
    sivuja = -(-(n - lisa) // 32) if n else 0
    dec.hk["_kierroksia"] = dec.hk.get("_kierroksia", 0) + (1 if len(dec.hk.get("_sivut", ())) >= sivuja else 0)
    if not n or dec.hk.get("kennomaara_korjattu") or len(dec.hk["_sivut"]) < sivuja or dec.hk["_kierroksia"] < 2 * sivuja:
        return
    havaittu = dec.hk.get("_max_sivuilta", 0)
    if 0 < havaittu < n - lisa:
        dec.hk["kennomaara_valittu"] = n
        dec.hk["cells"] = havaittu
        dec.hk["lisakennot"] = 0
        for k in [k for k in dec.state.bricks if k > havaittu]:
            del dec.state.bricks[k]
    dec.hk["kennomaara_korjattu"] = True


def _count(dec):
    st = dec.state
    st.brick_count = dec.hk.get("cells") or (max(st.bricks) if st.bricks else None)


def _status(dec, t, d):
    if len(d) < 32:
        return
    st = dec.state
    soh = _u(d, 25, 2) / 10
    if 50 <= soh <= 110:
        st.bms_soh_pct = soh
        ref = dec.hk.get("ref_kwh")
        if ref:
            st.bol_kwh = ref
            st.nfp_kwh = ref * min(soh, 100.0) / 100
            if st.soc_avg is not None:
                st.nominal_remaining_kwh = st.nfp_kwh * st.soc_avg / 100
    disp = d[31] / 2
    if 0 <= disp <= 100:
        st.soc_ui = disp
    if dec.hk.get("lisakennot") and len(d) >= 36:
        for j, raw in enumerate((d[34], d[35])):
            if 100 <= raw <= 225:
                dec._brick_value(t, 97 + j, raw / 50)
        _count(dec)


def _odo(dec, t, d):
    if len(d) >= 9:
        km = _u(d, 6, 3)
        if 0 < km < 2_000_000:
            dec.state.odometer_km = float(km)


def _vin(dec, t, d):
    txt = bytes(b for b in d if 0x30 <= b <= 0x5A).decode("ascii", "ignore")
    m = __import__("re").search(r"[A-HJ-NPR-Z0-9]{17}", txt)
    if m:
        dec.state.vin = m.group(0)


HANDLERS = {P_MAIN: _main, P_STATUS: _status, P_ODO: _odo, P_VIN: _vin,
            **{pid: _cells(k) for k, pid in enumerate(P_CELLS)}}


# ----------------------------------------------------------------------
def encode_main(*, soc, v, i, t_max, t_min, c_max, c_max_no, c_min, c_min_no, cec, ced, charging) -> bytes:
    """Pääkyselyn vastaus (esittelytila ja testit)."""
    d = bytearray(62)
    d[4] = max(0, min(200, round(soc * 2)))
    d[9] = 0x80 if charging else 0x00
    d[10:12] = (round(i * 10) & 0xFFFF).to_bytes(2, "big")
    d[12:14] = round(v * 10).to_bytes(2, "big")
    d[14], d[15] = round(t_max) & 0xFF, round(t_min) & 0xFF
    for k in range(16, 21):
        d[k] = round((t_max + t_min) / 2) & 0xFF
    d[23], d[24] = round(c_max * 50), c_max_no
    d[25], d[26] = round(c_min * 50), c_min_no
    d[29] = 140
    d[38:42] = round(cec * 10).to_bytes(4, "big")
    d[42:46] = round(ced * 10).to_bytes(4, "big")
    return bytes(d)


def encode_cells(volts: list) -> bytes:
    d = bytearray(38)
    for j, v in enumerate(volts[:32]):
        d[4 + j] = round(v * 50) if v else 0
    return bytes(d)


def encode_status(*, soh, soc_disp, extra=()) -> bytes:
    d = bytearray(42)
    d[25:27] = round(soh * 10).to_bytes(2, "big")
    d[31] = round(soc_disp * 2)
    for j, v in enumerate(extra[:2]):
        d[34 + j] = round(v * 50)
    return bytes(d)


def encode_odo(km: float) -> bytes:
    d = bytearray(10)
    d[6:9] = int(km).to_bytes(3, "big")
    return bytes(d)
