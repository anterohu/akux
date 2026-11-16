"""MG (SAIC Motor): MG4, MG5 ja MG ZS EV.

Akun tiedot luetaan kyselyinä akunhallinnalta (palvelu 22, 11-bittiset tunnisteet, 500 kbit/s). Kyselyt ja
skaalaukset perustuvat avoimeen Open Vehicle Monitoring System -projektiin (OVMS 3, vehicle_mgev, MIT-lisenssi).

Akunhallinnan osoite mallin mukaan:
    MG ZS EV 2019–2021          781 (vastaus 789)
    MG ZS EV 2022– ja MG5       7E5 (vastaus 7ED)
    MG4                         7DF (yleiskysely, vastaus 7ED, vuonohjaus 7E5)

Vastausten arvot (tavut kyselyn tunnisteen jälkeen, iso tavujärjestys):
    22 B042  akun jännite: u16 / 4 V
    22 B043  virta: (u16 − 40 000) / 40 A, positiivinen = purku
    22 B046  varaustila koko akun alueella: u16 / 10 % (MG ZS EV)
    01 5B    näytön varaustila: tavu · 100 / 255 % (MG4 ja MG5)
    22 B056  akun lämpötila: tavu · 0,5 − 40 °C
    22 B058 / B059  korkein / matalin kennojännite: u16 / 1000 V
    22 B061  akunhallinnan kuntoarvio (SOH): u16 / 100 %
    22 B001 …  lohkon tiedot: matalin ja korkein kennojännite u16 / 2000 + 1 V, matalin ja korkein lämpötila
               tavu · 0,5 − 40 °C. Lohkoja on 9 (ZS EV 2019–2021), 21 (MG5) tai 24 (ZS EV 2022–, MG4).
    Valmistenumero 22 F190 ja mittarilukema (u24 km): ohjausyksikkö 7E3 (22 E101) tai yhdyskäytävä 710 (22 B921).

Akunhallinta ilmoittaa kennojännitteet lohkoittain (lohkon matalin ja korkein kenno), ei jokaista kennoa erikseen.
Varaustilan näyttöalue on akunhallinnan käyttöalue: näytön 0–100 % vastaa koko akun aluetta mallikohtaisesti.
"""
from __future__ import annotations

PLATFORM = "mg"
NIMI = "MG"
MERKIT = ("MG",)

_B = 0x4D0000                         # virtuaalitunnisteiden alue
M_V = _B + 0xB042
M_I = _B + 0xB043
M_SOC_RAW = _B + 0xB046
M_SOC_UI = _B + 0x015B
M_TEMP = _B + 0xB056
M_CMAX = _B + 0xB058
M_CMIN = _B + 0xB059
M_SOH = _B + 0xB061
M_BLK0 = _B + 0x10000                 # lohko 1; lohko k = M_BLK0 + k - 1
M_VIN = _B + 0xF190
M_ODO = _B + 0xE101
MAX_LOHKOT = 24
# Lohkojen kyselytunnisteet (OVMS mg_obd_pids.h)
LOHKO_PID = [0xB001, 0xB009, 0xB011, 0xB019, 0xB021, 0xB029, 0xB0A3, 0xB0AB, 0xB0B3, 0xB0BB, 0xB0C3, 0xB0CB,
             0xB0DB, 0xB0DC, 0xB0DD, 0xB0DE, 0xB10E, 0xB10F, 0xB110, 0xB111, 0xB112, 0xB113, 0xB114, 0xB115]

# Kyselyryhmät: akunhallinnan osoite, lohkojen määrä, varaustilan lähde ja muiden tietojen osoitteet
RYHMAT = {
    "mg-zs1": {"bms": "781", "lohkot": 9, "soc": "raw", "vin": ("7E3", "22F190"), "odo": ("7E3", "22E101")},
    "mg-zs2": {"bms": "7E5", "lohkot": 24, "soc": "raw", "vin": ("7E3", "22F190"), "odo": ("7E3", "22E101")},
    "mg5": {"bms": "7E5", "lohkot": 21, "soc": "ui", "vin": ("710", "22F190"), "odo": ("710", "22B921")},
    "mg4": {"bms": "7DF", "lohkot": 24, "soc": "ui", "vin": ("710", "22F190"), "odo": ("710", "22B921")},
}

TUNNISTEET = [M_V, M_I, M_SOC_RAW, M_SOC_UI, M_TEMP, M_CMAX, M_CMIN, M_BLK0, M_SOH, M_ODO, M_VIN]
PAKOLLISET = [M_V, M_I, M_BLK0, M_SOH]
KUVAUS = {
    M_V: "Akun jännite", M_I: "Akun virta", M_SOC_RAW: "Varaustila (akunhallinta)", M_SOC_UI: "Varaustila (mittaristo)",
    M_TEMP: "Akun lämpötila", M_CMAX: "Korkein kennojännite", M_CMIN: "Matalin kennojännite",
    M_BLK0: "Kennojännitteet lohkoittain", M_SOH: "Akunhallinnan kuntoarvio", M_ODO: "Mittarilukema",
    M_VIN: "Valmistenumero",
}
NAYTTO = {M_V: "BMS 22B042", M_I: "BMS 22B043", M_SOC_RAW: "BMS 22B046", M_SOC_UI: "BMS 015B", M_TEMP: "BMS 22B056",
          M_CMAX: "BMS 22B058", M_CMIN: "BMS 22B059", M_BLK0: "BMS 22B001–", M_SOH: "BMS 22B061",
          M_ODO: "22E101 / 22B921", M_VIN: "22F190"}

RESOLUUTIO_MV = 1.0
ITSEPURKAUS_OK = False                # kennot vain lohkon ääriarvoina: kennokohtaista itsepurkausta ei voi erottaa
ELINKAARILASKURIT = False
PROTOKOLLA = "6"                      # ISO 15765-4, 11-bittiset tunnisteet, 500 kbit/s
RX = {"781": "789", "7E5": "7ED", "7DF": "7ED", "7E3": "7EB", "710": "718"}
FC = {"7DF": "7E5"}                   # MG4: yleiskyselyn monikehyksisen vastauksen vuonohjaus akunhallinnalle
LAHDE = "avoimeen Open Vehicle Monitoring System -projektiin (OVMS)"
OHJE = {"liitin": "OBD-II-diagnostiikkaliitin",
        "ohje": "Diagnostiikkaliitin on kuljettajan jalkatilassa kojelaudan alla; välikaapelia ei tarvita. Valitse "
                "yhdistettäessä auton malli ja akun koko. Akunhallinta vastaa kyselyihin, kun auto on käynnistetty "
                "(READY) tai latautuu. Mittauksen lepojaksojen lopussa auto on käynnistettävä hetkeksi, jotta "
                "loppuarvot saadaan luettua.",
        "varmistettu": False}
KENNO_HUOM = ("{gen} akunhallinta ilmoittaa kennojännitteet lohkoittain: kunkin lohkon matalimman ja korkeimman "
              "kennon jännitteen. Kaaviossa ja taulukossa on lohkojen ääriarvot, ja jännite-ero on koko akun "
              "korkeimman ja matalimman kennon erotus.")


def ryhma(model: dict) -> dict:
    return RYHMAT[model.get("kyselyryhma") or "mg4"]


def requests_for(model: dict) -> tuple[list, list]:
    g = ryhma(model)
    bms = g["bms"]
    core = [(bms, "22B042", M_V), (bms, "22B043", M_I)]
    soc = (bms, "015B", M_SOC_UI) if g["soc"] == "ui" else (bms, "22B046", M_SOC_RAW)
    loop = []
    for k0 in range(0, g["lohkot"], 6):
        loop += core
        loop += [(bms, f"22{LOHKO_PID[k]:04X}", M_BLK0 + k) for k in range(k0, min(k0 + 6, g["lohkot"]))]
    loop += core + [soc, (bms, "22B056", M_TEMP), (bms, "22B058", M_CMAX), (bms, "22B059", M_CMIN)]
    rare = [(g["vin"][0], g["vin"][1], M_VIN), (g["odo"][0], g["odo"][1], M_ODO), (bms, "22B061", M_SOH)]
    return loop, rare


def decoder_opts(model: dict) -> dict:
    g = ryhma(model)
    ala, yla = model.get("soc_ikkuna") or (25.0, 930.0)
    return {"lohkot": g["lohkot"], "ref_kwh": model["viite_kwh"], "malli_id": model["id"],
            "soc_ala": float(ala), "soc_yla": float(yla)}


def simulator(model: dict, **opts):
    from .simulator import MgSimulator
    return MgSimulator(model=model, **opts)


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
    if len(d) >= 2:
        i = (_u(d, 0, 2) - 40000) / 40
        if -800 < i < 800:
            st = dec.state
            st.pack_i = i
            st.power_state = "lataus" if i < -1.0 else None
            _emit(dec, t)


def _set_soc(dec, raw_pct, ui_pct):
    st = dec.state
    if 0 <= raw_pct <= 100:
        st.soc_avg = st.soc_min = st.soc_max = raw_pct
        st.soc_ui = max(0.0, min(100.0, ui_pct))
        if st.nfp_kwh:
            st.nominal_remaining_kwh = st.nfp_kwh * raw_pct / 100


def _soc_raw(dec, t, d):
    # Koko akun alueen varaustila (0,1 %); näytön varaustila lasketaan akunhallinnan käyttöalueesta
    if len(d) >= 2:
        raw = _u(d, 0, 2)
        ala, yla = dec.hk.get("soc_ala", 25.0), dec.hk.get("soc_yla", 930.0)
        _set_soc(dec, raw / 10, (raw - ala) * 100 / (yla - ala))


def _soc_ui(dec, t, d):
    # Näytön varaustila; koko akun alueen varaustila lasketaan käänteisesti akunhallinnan käyttöalueesta
    if len(d) >= 1:
        ui = d[0] * 100 / 255
        ala, yla = dec.hk.get("soc_ala", 25.0), dec.hk.get("soc_yla", 930.0)
        _set_soc(dec, (ala + ui * (yla - ala) / 100) / 10, ui)


def _temp(dec, t, d):
    if len(d) >= 1:
        c = d[0] * 0.5 - 40
        if -40 <= c <= 80 and not dec.hk.get("lohkolampo"):
            dec.state.temp_min = dec.state.temp_max = c       # lohkojen lämpötilat ovat tarkempia, kun ne on saatu


def _cell_extreme(which):
    def h(dec, t, d):
        if len(d) >= 2:
            v = _u(d, 0, 2) / 1000
            if 2.0 <= v <= 4.5:
                dec.hk[which] = v                         # akunhallinnan oma ääriarvo (vertailuun)
    return h


def _blk(k):
    """Lohko k (1…): matalin ja korkein kennojännite sekä lämpötilat. Lohkon ääriarvot tallennetaan kennoryhminä
    2k−1 (matalin) ja 2k (korkein)."""
    def h(dec, t, d):
        if len(d) < 6:
            return
        n = dec.hk.get("lohkot") or MAX_LOHKOT
        if k > n:
            return
        vmin, vmax = _u(d, 0, 2) / 2000 + 1.0, _u(d, 2, 2) / 2000 + 1.0
        if not (2.0 <= vmin <= 4.5 and 2.0 <= vmax <= 4.5 and vmin <= vmax + 0.001):
            return
        dec._brick_value(t, 2 * k - 1, vmin)
        dec._brick_value(t, 2 * k, vmax)
        st = dec.state
        st.brick_count = 2 * n
        vals = st.bricks
        hi = max(vals, key=lambda x: vals[x])
        lo = min(vals, key=lambda x: vals[x])
        st.cell_v_max, st.cell_v_max_num = vals[hi], hi
        st.cell_v_min, st.cell_v_min_num = vals[lo], lo
        tmin, tmax = d[4] * 0.5 - 40, d[5] * 0.5 - 40
        if -40 <= tmin <= tmax <= 80:
            lt = dec.hk.setdefault("lohkolampo", {})
            lt[k] = (tmin, tmax)
            st.temp_min = min(x[0] for x in lt.values())
            st.temp_max = max(x[1] for x in lt.values())
    return h


def _soh(dec, t, d):
    if len(d) >= 2:
        soh = _u(d, 0, 2) / 100
        if 40 <= soh <= 110:
            st = dec.state
            st.bms_soh_pct = soh
            ref = dec.hk.get("ref_kwh")
            if ref:
                # Akunhallinta ei ilmoita alkuperäistä energiaa: viitteenä on mallin akun koko (mallitaulukko)
                st.nfp_kwh = ref * min(soh, 100.0) / 100
                if st.soc_avg is not None:
                    st.nominal_remaining_kwh = st.nfp_kwh * st.soc_avg / 100


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


HANDLERS = {M_V: _v, M_I: _i, M_SOC_RAW: _soc_raw, M_SOC_UI: _soc_ui, M_TEMP: _temp,
            M_CMAX: _cell_extreme("cell_v_max_bms"), M_CMIN: _cell_extreme("cell_v_min_bms"),
            M_SOH: _soh, M_ODO: _odo, M_VIN: _vin,
            **{M_BLK0 + k: _blk(k + 1) for k in range(MAX_LOHKOT)}}


# ----------------------------------------------------------------------
def encode(cid: int, **kw) -> bytes:
    """Vastausten tavut (esittelytila ja testit)."""
    if cid == M_V:
        return round(kw["v"] * 4).to_bytes(2, "big")
    if cid == M_I:
        return (round(kw["i"] * 40) + 40000).to_bytes(2, "big")
    if cid == M_SOC_RAW:
        return round(kw["raw"] * 10).to_bytes(2, "big")
    if cid == M_SOC_UI:
        return bytes([max(0, min(255, round(kw["ui"] * 255 / 100)))])
    if cid == M_TEMP:
        return bytes([round((kw["c"] + 40) * 2)])
    if cid in (M_CMAX, M_CMIN):
        return round(kw["v"] * 1000).to_bytes(2, "big")
    if M_BLK0 <= cid < M_BLK0 + MAX_LOHKOT:
        return (round((kw["vmin"] - 1.0) * 2000).to_bytes(2, "big") + round((kw["vmax"] - 1.0) * 2000).to_bytes(2, "big")
                + bytes([round((kw["tmin"] + 40) * 2), round((kw["tmax"] + 40) * 2)]))
    if cid == M_SOH:
        return round(kw["soh"] * 100).to_bytes(2, "big")
    if cid == M_ODO:
        return int(kw["km"]).to_bytes(3, "big")
    if cid == M_VIN:
        return kw["vin"].encode("ascii")
    raise ValueError(cid)
