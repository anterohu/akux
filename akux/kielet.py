"""Käännökset: suomi (lähdekieli), englanti ja ruotsi.

Kaikki tekstit kirjoitetaan ohjelmaan suomeksi. Käännökset ovat tiedostoissa data/kielet/en.json ja sv.json muodossa
{"suomenkielinen teksti": "käännös"}. Tekstissä {} tarkoittaa vaihtuvaa osaa (luku, nimi): esimerkiksi
"Akun varaus on {} %." → "The battery charge is {} %.". Sama sanasto käytetään käyttöliittymässä (web/kaannos.js),
palvelimen viesteissä ja PDF-raportissa, joten jokainen teksti käännetään yhdessä paikassa.

Käännöstä vailla oleva teksti näytetään suomeksi. Testi tests/test_kielet.py varmistaa, ettei suomenkielistä tekstiä jää
näkyviin, kun kieli on englanti tai ruotsi.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

KIELET = {"fi": "Suomi", "en": "English", "sv": "Svenska"}
OLETUS = "fi"
KANSIO = Path(__file__).parent / "data" / "kielet"

_paikallinen = threading.local()
_oletus = OLETUS
_sanastot: dict[str, tuple[dict, list]] = {}


def aseta(kieli: str | None):
    """Ohjelman kieli (asetuksista). Säiekohtainen kieli (kaytossa) ohittaa tämän."""
    global _oletus
    _oletus = kieli if kieli in KIELET else OLETUS


def nykyinen() -> str:
    return getattr(_paikallinen, "kieli", None) or _oletus


class kaytossa:
    """with kielet.kaytossa("en"): ... — esim. raportti toisella kielellä."""
    def __init__(self, kieli):
        self.kieli = kieli if kieli in KIELET else None

    def __enter__(self):
        self.vanha = getattr(_paikallinen, "kieli", None)
        _paikallinen.kieli = self.kieli

    def __exit__(self, *a):
        _paikallinen.kieli = self.vanha


def sanasto(kieli: str) -> dict:
    if kieli not in KIELET or kieli == "fi":
        return {}
    p = KANSIO / f"{kieli}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _kaannos(kieli: str):
    if kieli not in _sanastot:
        d = sanasto(kieli)
        kuviot = []
        for k, v in d.items():
            if "{}" in k:
                osat = [re.escape(x) for x in k.split("{}")]
                kuviot.append((re.compile("^" + "(.+?)".join(osat) + "$", re.S), v, k.count("{}")))
        kuviot.sort(key=lambda x: -len(x[0].pattern))  # pisin (tarkin) ensin
        _sanastot[kieli] = (d, kuviot)
    return _sanastot[kieli]


def tyhjenna_valimuisti():
    _sanastot.clear()


# Merkin genetiivi suomessa → sanastossa käytetään muotoa "Teslan", ja käännökseen palautetaan oikea merkki.
MERKIT = {"Hyundain": "Hyundai", "Kian": "Kia", "Nissanin": "Nissan", "Volkswagenin": "Volkswagen", "Škodan": "Škoda",
          "Audin": "Audi", "Cupran": "Cupra"}
_MERKKI_RX = re.compile(r"\b(" + "|".join(MERKIT) + r")(?= )")
_LAUSE_RX = re.compile(r"(?<=[.!?])\s+(?=[A-ZÅÄÖ0-9(])")


# Desimaalierotin: suomessa ja ruotsissa pilkku, englannissa piste (12,3 kWh → 12.3 kWh). Vain numeroiden välissä
# oleva pilkku vaihdetaan, joten luettelot ("1, 2") säilyvät.
_DESIMAALI_RX = re.compile(r"(?<=\d),(?=\d)")


def desimaalit(teksti, kieli: str | None = None):
    if isinstance(teksti, str) and (kieli or nykyinen()) == "en":
        return _DESIMAALI_RX.sub(".", teksti)
    return teksti


def t(teksti, kieli: str | None = None):
    """Kääntää tekstin: ensin koko teksti, sitten lause kerrallaan. Merkin genetiivi (Kian, Audin…) käsitellään
    sanaston muodon "Teslan" kautta. Englanniksi desimaalipilkku muutetaan pisteeksi."""
    if not isinstance(teksti, str) or not teksti.strip():
        return teksti
    kieli = kieli or nykyinen()
    if kieli == "fi":
        return teksti
    m = _MERKKI_RX.search(teksti)
    if m:
        merkki = MERKIT[m.group(1)]
        tulos = _t(_MERKKI_RX.sub("Teslan", teksti), kieli).replace("Tesla", merkki)
    else:
        tulos = _t(teksti, kieli)
    return desimaalit(tulos, kieli)


def _t(teksti, kieli):
    d, kuviot = _kaannos(kieli)
    alku = teksti[: len(teksti) - len(teksti.lstrip())]
    loppu = teksti[len(teksti.rstrip()):]
    ydin = teksti.strip()
    if ydin in d:
        return alku + d[ydin] + loppu
    for rx, kohde, n in kuviot:
        m = rx.match(ydin)
        # Vaihtuva osa ei saa ylittää lauserajaa (muuten lyhyt kuvio nielaisisi kokonaisia lauseita).
        if m and not any(_LAUSE_RX.search(g) for g in m.groups()):
            osat = kohde.split("{}")
            tulos = osat[0]
            for i, g in enumerate(m.groups()):
                tulos += _t(g, kieli) + (osat[i + 1] if i + 1 < len(osat) else "")
            return alku + tulos + loppu
    lauseet = _LAUSE_RX.split(ydin)
    if len(lauseet) > 1:
        return alku + " ".join(_t(x, kieli) for x in lauseet) + loppu
    _puuttuu(ydin)
    return teksti


def _puuttuu(teksti):
    """Kehitystyökalu: AKUX_PUUTTUVAT=<tiedosto> kirjaa kääntämättömät tekstit (sanaston täydentämiseen)."""
    polku = os.environ.get("AKUX_PUUTTUVAT")
    if polku and re.search(r"[A-Za-zÅÄÖåäö]{2}", teksti):
        with open(polku, "a", encoding="utf-8") as f:
            f.write(json.dumps(teksti, ensure_ascii=False) + "\n")


_TAGI_RX = re.compile(r"(<[^>]+>)")


def t_html(teksti, kieli: str | None = None):
    """Kääntää HTML-merkintää sisältävän tekstin osissa samoin kuin selain tekstisolmuina (merkinnät säilyvät)."""
    if not isinstance(teksti, str) or (kieli or nykyinen()) == "fi":
        return teksti
    if "<" not in teksti:
        return t(teksti, kieli)
    if teksti.strip() in _kaannos(kieli or nykyinen())[0]:
        return t(teksti, kieli)
    return "".join(osa if osa.startswith("<") else t(osa, kieli) for osa in _TAGI_RX.split(teksti))
