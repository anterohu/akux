"""Järkevyystarkistus: mahdotonta tulosta ei rekisteröidä raportiksi, vaan krediitit palautetaan automaattisesti
(lupa perutaan tai lähetetään hyvityspyyntö). Esimerkkimittaukset läpäisevät tarkistuksen.

Ajo: python tests/test_uskottavuus.py
"""
import copy
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux import analysis, krediitit as kr, mittaustiedosto  # noqa: E402
from akux.storage import Storage  # noqa: E402

ESIM = Path(__file__).resolve().parents[1] / "akux" / "data" / "esimerkit"


def test_esimerkit_ovat_uskottavia():
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d))
        n = 0
        for f in sorted(ESIM.glob("*.akveri")):
            tid = mittaustiedosto.import_file(st, f.read_bytes())["id"]
            analysis.reanalyze(st, tid)
            assert analysis.uskottavuus(st.test(tid)["tulos"]) == [], f.name
            n += 1
        assert n >= 20


def test_mahdottomat_arvot_tunnistetaan():
    r = {"yhteenveto": {"kunto_pct": 92.0, "kapasiteetti_kwh": 60.0}, "viite": {"kwh": 64.0},
         "kennot": {"lkm": 98, "min_v": 3.6, "max_v": 3.62, "ero_mv": 20}}
    assert analysis.uskottavuus(r) == []
    v = copy.deepcopy(r); v["yhteenveto"]["kunto_pct"] = 160.0
    assert "160" in analysis.uskottavuus(v)[0]
    v = copy.deepcopy(r); v["viite"]["kwh"] = 39.2           # väärin valittu malli: 39 kWh, mitattu 60 kWh
    assert any("Tarkista, että auton malli" in s for s in analysis.uskottavuus(v))
    v = copy.deepcopy(r); v["kennot"]["max_v"] = 6.5
    assert analysis.uskottavuus(v) == ["Kennoryhmien jännitteet ovat mahdollisen alueen ulkopuolella."]
    v = copy.deepcopy(r); v["kennot"]["ero_mv"] = 2500
    assert analysis.uskottavuus(v) == ["Kennoryhmien jännite-ero on mahdottoman suuri."]
    assert analysis.uskottavuus({"yhteenveto": {"kunto_pct": None}}) == []     # tarkkuusvaatimus ei täyttynyt: ok


class Palvelin:
    """Vale-akveri.fi: peru onnistuu perumisaikana, sen jälkeen 409; hyvityspyyntö hyväksytään."""
    def __init__(self, perumisaika_kulunut=False, verkko=True):
        self.kulunut, self.verkko, self.kutsut = perumisaika_kulunut, verkko, []

    def __call__(self, method, url, headers, body, aikaraja):
        polku = url.split("akveri.fi", 1)[-1]
        self.kutsut.append(polku)
        if not self.verkko:
            raise urllib.error.URLError("ei verkkoa")
        if polku == "/api/v1/testi/peru":
            return (409, {"virhe": "Luvan voi perua 15 minuutin kuluessa."}) if self.kulunut else (200, {"ok": True})
        if polku == "/api/v1/testi/hyvityspyynto":
            return 200, {"ok": True}
        return 200, {}


def _testi(st, tulos):
    st.save_settings({"tili": "T000000000001", "tili_avain": "x" * 40})
    vid = st.add_vehicle({"nimi": "Testiauto", "malli_id": "kona-64"}) if hasattr(st, "add_vehicle") else None
    tid = st.add_test(vid, "pikatarkastus")
    st.update_test(tid, tila="valmis", lupa="AKTESTI0001", lupa_tila="varattu", lupa_varattu=time.time(),
                   lupa_peruttavissa=time.time() + 600, tulos=tulos)
    return tid


def test_epauskottava_tulos_palauttaa_krediitit():
    huono = {"yhteenveto": {"kunto_pct": 163.0, "kapasiteetti_kwh": 63.9}, "viite": {"kwh": 39.2}}
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d))
        # Perumisaikana: lupa perutaan, krediitit palautuvat heti, tulosta ei näytetä
        p = Palvelin()
        k = kr.Krediitit(st, http=p)
        tid = _testi(st, huono)
        assert k.hylkaa_epauskottava(tid, analysis.uskottavuus(huono)) == "peruttu"
        t = st.test(tid)
        assert t["lupa_tila"] == "peruttu" and not kr.tulos_naytettavissa(t)
        assert "/api/v1/testi/raportti" not in p.kutsut and "/api/v1/testi/peru" in p.kutsut
        # Perumisajan jälkeen: hyvityspyyntö lähtee automaattisesti
        p = Palvelin(perumisaika_kulunut=True)
        k = kr.Krediitit(st, http=p)
        tid = _testi(st, huono)
        assert k.hylkaa_epauskottava(tid, analysis.uskottavuus(huono)) == "tarkistettava"
        assert p.kutsut[-1] == "/api/v1/testi/hyvityspyynto" and not kr.tulos_naytettavissa(st.test(tid))
        # Ilman verkkoa: odottaa ja lähetetään, kun yhteys palaa (ei rekisteröidä raporttina)
        p = Palvelin(verkko=False)
        k = kr.Krediitit(st, http=p)
        tid = _testi(st, huono)
        assert k.hylkaa_epauskottava(tid, analysis.uskottavuus(huono)) == "tarkistus_odottaa"
        assert st.test(tid)["lupa_tila"] == "tarkistus_odottaa" and not kr.tulos_naytettavissa(st.test(tid))
        assert any(t["id"] == tid for t in k.odottavat())
        p.verkko = True
        kr.kasittele_odottavat(k, "2.0.3")
        assert st.test(tid)["lupa_tila"] == "peruttu"
        assert "/api/v1/testi/raportti" not in p.kutsut


if __name__ == "__main__":
    test_esimerkit_ovat_uskottavia()
    test_mahdottomat_arvot_tunnistetaan()
    test_epauskottava_tulos_palauttaa_krediitit()
    print("ok")
