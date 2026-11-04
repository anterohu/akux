"""Teslan valmistenumeron (VIN) purku ilman verkkoyhteyttä."""
from __future__ import annotations

VALMISTAJAT = {
    "5YJ": ("Tesla, Fremont (Yhdysvallat)", "Fremont"),
    "7SA": ("Tesla, Austin (Yhdysvallat)", "Austin"),
    "LRW": ("Tesla, Shanghai (Kiina)", "Shanghai"),
    "XP7": ("Tesla, Berliini (Saksa)", "Berliini"),
    "7G2": ("Tesla, Fremont (Yhdysvallat)", "Fremont"),
}

MALLIT = {"3": "Model 3", "Y": "Model Y", "S": "Model S", "X": "Model X"}

TEHTAAT = {"F": "Fremont", "C": "Shanghai", "B": "Berliini", "A": "Austin",
           "P": "Palo Alto", "R": "Fremont"}

VUODET = {"H": 2017, "J": 2018, "K": 2019, "L": 2020, "M": 2021, "N": 2022,
          "P": 2023, "R": 2024, "S": 2025, "T": 2026, "V": 2027, "W": 2028}

# 8. merkki: voimalinja (Model 3 / Model Y)
VOIMALINJAT = {
    "A": ("Yksi moottori", "RWD"),
    "B": ("Kaksi moottoria", "AWD"),
    "C": ("Kaksi moottoria, Performance", "PERF"),
    "D": ("Kaksi moottoria", "AWD"),
    "E": ("Kaksi moottoria", "AWD"),
    "F": ("Kaksi moottoria, Performance", "PERF"),
    "J": ("Yksi moottori", "RWD"),
    "K": ("Kaksi moottoria", "AWD"),
    "L": ("Kaksi moottoria, Performance", "PERF"),
    "R": ("Yksi moottori", "RWD"),
    "S": ("Yksi moottori", "RWD"),
    "T": ("Kaksi moottoria", "AWD"),
}

# 7. merkki: akkutyyppi
AKKUTYYPIT = {
    "E": "Litiumioniakku (NCA/NMC)",
    "F": "Litiumrautafosfaattiakku (LFP)",
    "H": "Suuren kapasiteetin akku",
    "S": "Vakiokapasiteetin akku",
    "V": "Suuren kapasiteetin akku",
}

KIELLETYT = set("IOQ")
PAINOT = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
ARVOT = {**{str(i): i for i in range(10)},
         "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
         "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
         "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9}


def normalize(vin: str) -> str:
    return "".join(ch for ch in (vin or "").upper() if ch.isalnum())


def check_digit_ok(vin: str) -> bool | None:
    """Pohjois-Amerikan tarkistusmerkki (9. merkki). Eurooppalaisissa
    valmistenumeroissa merkki ei ole pakollinen, joten tulos on vain lisätieto."""
    if len(vin) != 17:
        return None
    try:
        total = sum(ARVOT[c] * w for c, w in zip(vin, PAINOT))
    except KeyError:
        return None
    rem = total % 11
    expected = "X" if rem == 10 else str(rem)
    return vin[8] == expected


def decode(vin: str) -> dict:
    vin = normalize(vin)
    out = {"vin": vin, "kelvollinen": False, "virheet": []}
    if len(vin) != 17:
        out["virheet"].append("Valmistenumerossa pitää olla 17 merkkiä.")
        return out
    if KIELLETYT & set(vin):
        out["virheet"].append("Valmistenumerossa ei käytetä kirjaimia I, O tai Q.")
        return out
    wmi = vin[:3]
    valm = VALMISTAJAT.get(wmi)
    if not valm:
        out["virheet"].append(f"Valmistajatunnus {wmi} ei ole Teslan tunnus.")
        return out
    out["kelvollinen"] = True
    out["valmistaja"] = valm[0]
    out["malli"] = MALLIT.get(vin[3], f"Tuntematon ({vin[3]})")
    out["malli_koodi"] = vin[3]
    out["akkutyyppi"] = AKKUTYYPIT.get(vin[6])
    out["akku_koodi"] = vin[6]
    vl = VOIMALINJAT.get(vin[7])
    out["voimalinja"] = vl[0] if vl else None
    out["veto"] = vl[1] if vl else None
    out["vuosimalli"] = VUODET.get(vin[9])
    out["tehdas"] = TEHTAAT.get(vin[10], valm[1])
    out["sarjanumero"] = vin[11:]
    out["tarkistusmerkki"] = check_digit_ok(vin)
    return out
