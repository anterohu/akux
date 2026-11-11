"""Akunhallinnan ilmoittaman alkuperäisen energian tarkistukset.

Arvoa käytetään akun kunnon vertailukohtana vain, jos se on mahdollinen tälle akulle. Virheellinen arvo
(esimerkiksi 76,9 kWh 55 kWh:n LFP-akussa, mittaus 2026-00009) ei saa vääristää kuntoprosenttia.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux import analysis as A  # noqa: E402
from akux import profiles  # noqa: E402

LFP55 = profiles.get("m3-srplus-2021-lfp")
LR = profiles.get("m3-lr-2021-lg")


def snaps(vals):
    return [{"data": {"bol_kwh": v}} for v in vals]


def test_mallin_tarkistus():
    assert A.bol_tarkistus(76.9, LFP55, 51.4, 106) and "ei sovi" in A.bol_tarkistus(76.9, LFP55, 51.4, 106)
    # Oikea arvo poikkeaa mallitaulukosta vain vähän: kelpaa
    assert A.bol_sopii(54.3, LFP55, 51.4, 106)
    assert A.bol_sopii(LR["viite_kwh"] * 0.96, LR, 70.0, 96)
    # Yli 8 %:n poikkeama ei kelpaa
    assert not A.bol_sopii(LFP55["viite_kwh"] * 1.10, LFP55, 51.4, 106)
    print("OK mallin tarkistus")


def test_fysikaalinen_raja():
    # Ilman mallia: energia kennoryhmää kohden 0,2–1,4 kWh
    assert A.bol_sopii(55.0, None, 50.0, 106)
    assert not A.bol_sopii(30.5, None, 25.0, 160)          # 0,19 kWh/ryhmä
    assert not A.bol_sopii(140.0, None, 50.0, 96)          # 1,46 kWh/ryhmä
    # Akku ei voi olla nyt selvästi suurempi kuin uutena
    assert "enemmän energiaa" in A.bol_tarkistus(50.0, None, 54.0, 106)
    print("OK fysikaalinen raja")


def test_vaihteleva_arvo():
    assert A.bol_mittauksesta(snaps([76.9] * 40)) == (76.9, None)
    assert A.bol_mittauksesta(snaps([54.3] * 38 + [54.4, 54.2])) == (54.3, None)
    v, syy = A.bol_mittauksesta(snaps([54.3] * 30 + [76.9] * 10))
    assert v is None and "vaihteli" in syy, (v, syy)
    assert A.bol_mittauksesta(snaps([None, None])) == (None, None)
    # Mittaus 2026-00009: kenttä tyhjä 161 tilannekuvassa, 33 kertaa 51,3 kWh ja kerran 76,9 kWh
    v, syy = A.bol_mittauksesta(snaps([None] * 161 + [51.3] * 33 + [76.9]))
    assert v is None and "17 %" in syy, (v, syy)
    print("OK vaihteleva arvo")


def test_mitattu_suurempi_kuin_uutena():
    # Akunhallinta ilmoittaa 50 kWh, mutta mitattu kapasiteetti on 54 kWh: akunhallinnan arvo hylätään
    res = {"viite": {"kwh": 50.0, "lahde": "Auton akunhallinta"}, "huomiot": [],
           "kapasiteetti": {"valmis": True, "taysi_kwh": 54.0, "epavarmuus_kwh": 0.6, "soh_pct": 108.0},
           "bms": {"soh_pct": 102.0}}
    A._tarkista_viite_mittauksella(res, LFP55, 51.0)
    assert res["viite"]["kwh"] == LFP55["viite_kwh"] and res["viite"]["hylatty_bol_kwh"] == 50.0
    assert abs(res["kapasiteetti"]["soh_pct"] - 54.0 / LFP55["viite_kwh"] * 100) < 0.01
    assert "mitattu kapasiteetti" in res["huomiot"][0]
    # Mittaus mahtuu akunhallinnan arvoon: ei muutosta
    res2 = {"viite": {"kwh": 55.0, "lahde": "Auton akunhallinta"}, "huomiot": [],
            "kapasiteetti": {"valmis": True, "taysi_kwh": 55.8, "epavarmuus_kwh": 0.6, "soh_pct": 101.5}}
    A._tarkista_viite_mittauksella(res2, LFP55, 51.0)
    assert res2["viite"]["kwh"] == 55.0 and not res2["huomiot"]
    print("OK mitattu kapasiteetti suurempi kuin uutena")


def test_kaikki_mallipohjat():
    # Jokaisen mallipohjan oma kapasiteetti läpäisee tarkistuksen omalla kennoryhmämäärällään
    for m in profiles.models():
        ns = m.get("sarjakennot")
        for n in (ns if isinstance(ns, list) else [ns]):
            assert A.bol_sopii(m["viite_kwh"], m, m["viite_kwh"] * 0.9, n), (m["id"], n)
    print("OK kaikki mallipohjat")


if __name__ == "__main__":
    test_mallin_tarkistus()
    test_fysikaalinen_raja()
    test_vaihteleva_arvo()
    test_mitattu_suurempi_kuin_uutena()
    test_kaikki_mallipohjat()
