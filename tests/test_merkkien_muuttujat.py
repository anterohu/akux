"""Merkkien ja mallien muuttujat: kennomäärät, kyselysivut, lisäkennot ja akunhallinnan kuntoarvion luotettavuus."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akveri import analysis, hkmc, polled, profiles  # noqa: E402
from akveri.decoder import TeslaDecoder as Decoder  # noqa: E402


def _mallit():
    return [m for m in profiles.models() if polled.is_polled(m.get("alusta"))]


def test_kyselymallien_perustiedot():
    for m in _mallit():
        pm = polled.module(m["alusta"])
        assert m.get("viite_kwh") and 10 < m["viite_kwh"] < 130, m["id"]
        assert m.get("kemia") in ("NMC", "LFP", "NCA"), m["id"]
        n = m.get("sarjakennot")
        assert n is None or 60 <= n <= 216, m["id"]
        assert pm.RESOLUUTIO_MV and pm.RESOLUUTIO_MV >= 1, m["id"]


def test_hkmc_kennosivut_riittavat_kennomaaralle():
    for m in _mallit():
        if m["alusta"] != "hkmc":
            continue
        loop, rare = hkmc.requests_for(m)
        sivut = len({c for _, _, c in loop if c in hkmc.P_CELLS})
        lisa = hkmc.decoder_opts(m)["lisakennot"]
        n = m.get("sarjakennot")
        if n:
            assert sivut * 32 + lisa >= n, m["id"]
        # Lisäkennot luetaan tilakyselystä vain 98-kennoisista akuista
        assert lisa == (2 if n == 98 else 0), m["id"]
        assert any(c == hkmc.P_VIN for _, _, c in rare), m["id"]


def test_hkmc_ei_haamukennoja_tilakyselysta():
    dec = Decoder()
    m = profiles.get("hy-kona-39")
    dec.configure("hkmc", **hkmc.decoder_opts(m))
    dec.feed(1.0, hkmc.P_STATUS, hkmc.encode_status(soh=97.0, soc_disp=50, extra=[3.8, 3.8]))
    assert 97 not in dec.state.bricks and 98 not in dec.state.bricks


def test_hkmc_valmistenumero_luetaan():
    dec = Decoder()
    dec.configure("hkmc", **hkmc.decoder_opts(profiles.get("hy-ioniq-38")))
    dec.feed(1.0, hkmc.P_VIN, bytes([1]) + b"KMHC851HFLU012345")
    assert dec.state.vin == "KMHC851HFLU012345"


def _res(alusta, soh):
    return {"ajoneuvo": {"alusta": alusta, "kemia": "NMC", "merkki": "Hyundai"}, "arviot": [], "huomiot": [],
            "viite": {"kwh": 38.3}, "bms": {"soh_pct": soh, "nfp_kwh": 38.3 * soh / 100}}


def test_hkmc_akunhallinnan_100_prosenttia_ei_ole_kunto():
    res = _res("hkmc", 100.0)
    analysis._summarize(res)
    assert res["yhteenveto"].get("kunto_pct") is None if "yhteenveto" in res else True
    assert not any(a["nimi"] == "Akun kunto (SOH)" for a in res["arviot"])
    assert any("kapasiteettimittauksella" in h for h in res["huomiot"])


def test_hkmc_alentunut_kunto_naytetaan():
    res = _res("hkmc", 91.0)
    analysis._summarize(res)
    assert any(a["nimi"] == "Akun kunto (SOH)" for a in res["arviot"])


def test_muut_alustat_eivat_muutu():
    for alusta in ("leaf", "meb", "mg"):
        res = _res(alusta, 100.0)
        analysis._summarize(res)
        assert any(a["nimi"] == "Akun kunto (SOH)" for a in res["arviot"]), alusta
