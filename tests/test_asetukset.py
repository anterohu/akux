"""Asetukset: asiakas muuttaa vain kielen, käyttötavan ja raportin tiedot. Raporttien ulkoasu ja mittaustapa ovat
kaikille samat. Yksityisessä käytössä raportissa ei ole yrityksen tietoja. Logon tyhjät reunat rajataan.

Ajo: python tests/test_asetukset.py
"""
import io
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akveri import analysis, mittaustiedosto, report, server  # noqa: E402
from akveri.storage import OLETUSASETUKSET, Storage  # noqa: E402

ESIM = Path(__file__).resolve().parents[1] / "akveri" / "data" / "esimerkit" / "ESIM-301_taysi.akveri"


def _api(st, kehittaja=False):
    app = SimpleNamespace(storage=st, krediitit=SimpleNamespace(esittely_sallittu=lambda tarkista=False: kehittaja))
    api = server.Api.__new__(server.Api)
    api.app = app
    return api


def _text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout


def test_asiakas_muuttaa_vain_omat_tietonsa():
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d))
        api = _api(st)
        s = api.tallenna_asetukset({}, {"kaytto": "henkilo", "mittaaja": "  Matti Meikäläinen ", "vesileima": "ei",
                                        "lepo_alku_min": 1, "tekninen_liite": "0", "puhelin_kaytossa": True,
                                        "ilmoitukset_kaytossa": True, "logo_koko": "pieni", "raportin_ulkoasu": "c",
                                        "mittaus_kansio": "/tmp/x", "tili": "T1", "esittely": True})
        assert s["kaytto"] == "henkilo" and s["mittaaja"] == "Matti Meikäläinen"
        for k in ("vesileima", "lepo_alku_min", "tekninen_liite", "puhelin_kaytossa", "ilmoitukset_kaytossa",
                  "logo_koko", "raportin_ulkoasu", "mittaus_kansio", "tili", "esittely"):
            assert s[k] == OLETUSASETUKSET[k], k
        assert api.tallenna_asetukset({}, {"kaytto": "jotain"})["kaytto"] == "henkilo"
        # Raja-arvot ja ulkoasu ovat kiinteät myös testitilillä, eivätkä aiemmin tallennetut arvot jää voimaan
        k = _api(st, kehittaja=True).tallenna_asetukset({}, {"vesileima": "ei", "lepo_alku_min": 45})
        assert k["vesileima"] == OLETUSASETUKSET["vesileima"] and k["lepo_alku_min"] == OLETUSASETUKSET["lepo_alku_min"]
        import json as _j
        st.settings_path.write_text(_j.dumps({"lepo_alku_min": 3, "vesileima": "ei"}), encoding="utf-8")
        assert Storage(Path(d)).settings()["lepo_alku_min"] == OLETUSASETUKSET["lepo_alku_min"]
        # Testi-ilmoitus ei ole asiakkaan käytössä
        try:
            api.testi_ilmoitus({}, {"osoite": "https://ntfy.sh/x"})
            raise AssertionError("testi-ilmoitus sallittiin")
        except server.ApiError as e:
            assert e.code == 403
        assert st.settings()["ilmoitus_osoite"] == ""


def test_yksityinen_kaytto_ei_nayta_yritysta_raportissa():
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d))
        tid = mittaustiedosto.import_file(st, ESIM.read_bytes())["id"]
        analysis.reanalyze(st, tid)
        st.save_settings({"kaytto": "yritys", "yritys_nimi": "Autoliike Testi Oy", "yritys_osoite": "Testitie 1",
                          "vesileima": "ei"})  # ilman vesileimaa teksti on luettavissa
        teksti = _text(report.build(st, tid, Path(d) / "y.pdf", kieli="fi"))
        assert "Autoliike Testi Oy" in teksti and "Testitie 1" in teksti
        st.save_settings({"kaytto": "henkilo"})
        teksti = _text(report.build(st, tid, Path(d) / "h.pdf", kieli="fi"))
        assert "Autoliike Testi Oy" not in teksti and "Testitie 1" not in teksti
        # Aiemmat asennukset ilman valintaa: yrityksen tiedot näkyvät edelleen
        st.save_settings({"kaytto": ""})
        assert "Autoliike Testi Oy" in _text(report.build(st, tid, Path(d) / "v.pdf", kieli="fi"))


def test_logon_reunat_rajataan():
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (1000, 800), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((300, 300, 700, 400), fill=(20, 60, 120, 255))
    b = io.BytesIO()
    im.save(b, "PNG")
    out = Image.open(io.BytesIO(server.rajaa_logo(b.getvalue())))
    assert out.format == "PNG" and 400 <= out.width <= 420 and 100 <= out.height <= 110, out.size
    # Valkoinen tausta rajataan samoin
    im = Image.new("RGB", (800, 800), (255, 255, 255))
    ImageDraw.Draw(im).ellipse((350, 350, 450, 450), fill=(200, 0, 0))
    b = io.BytesIO()
    im.save(b, "JPEG")
    out = Image.open(io.BytesIO(server.rajaa_logo(b.getvalue())))
    assert out.width < 120 and out.height < 120, out.size
    for huono in (b"ei kuva", Image.new("RGB", (50, 50), (255, 255, 255))):
        if not isinstance(huono, bytes):
            x = io.BytesIO()
            huono.save(x, "PNG")
            huono = x.getvalue()
        try:
            server.rajaa_logo(huono)
            raise AssertionError("kelvoton logo hyväksyttiin")
        except ValueError:
            pass


if __name__ == "__main__":
    test_asiakas_muuttaa_vain_omat_tietonsa()
    test_yksityinen_kaytto_ei_nayta_yritysta_raportissa()
    test_logon_reunat_rajataan()
    print("ok")


def test_esittelytila_sulkeutuu_kun_testitili_poistuu():
    """Kun testitili poistetaan palvelussa, käynnissä oleva esittelytila suljetaan eikä sitä voi käynnistää uudelleen."""
    import os
    from akveri.app import App
    vanha = os.environ.pop("AKVERI_ESITTELY", None)
    try:
        with tempfile.TemporaryDirectory() as d:
            a = App(Path(d))
            api = server.Api(a)
            a.storage.save_settings({"esittely": True})
            a.krediitit._kutsu = lambda *x, **k: {"testitili": True}
            a.connect("demo", soc=0.6, accel=30)
            assert a.source and a.source.simulated
            assert api.tila({}, {})["yhteys"]["simuloitu"]
            # Testitili poistettiin palvelussa
            a.krediitit._kutsu = lambda *x, **k: {"testitili": False}
            server.Api._esittely_tarkistettu = 0.0
            for _ in range(50):
                api.tila({}, {})
                if not a.source:
                    break
                time.sleep(0.1)
            assert a.source is None, "esittelytila jäi päälle"
            assert not api.tila({}, {})["yhteys"]["simuloitu"]
            try:
                api.yhdista({}, {"tyyppi": "demo"})
                raise AssertionError("esittelytila käynnistyi ilman testitiliä")
            except server.ApiError:
                pass
    finally:
        if vanha is not None:
            os.environ["AKVERI_ESITTELY"] = vanha


def test_valmistenumeron_merkki_ja_malli():
    from akveri.server import Api
    assert "Tesla" in Api._merkki_ristiriita("5YJ3E7EB1LF654321", "hy-ioniq-38")
    assert Api._merkki_ristiriita("KMHC851JFLU012345", "hy-ioniq-38") is None
    assert Api._merkki_ristiriita("KNACC81GFL5012345", "hy-kona-64") is None  # Kia ja Hyundai samaa konsernia


def test_kennotiedot_piilossa_ilman_mittausta():
    """Ilman mittausta näkyy vain luettujen kennoryhmien määrä, ei jännitteitä eikä jännite-eroa."""
    from akveri.app import App
    from akveri import krediitit as k
    with tempfile.TemporaryDirectory() as d:
        a = App(Path(d))
        api = server.Api(a)
        for i in range(1, 5):
            a.decoder.state.bricks[i] = 3.70 + i * 0.001
        a.decoder.state.brick_count = 4
        a.live_kunto_sallittu = lambda: False
        r = api.kennot({}, {})
        assert r == {"kennot": [], "piilotettu": True, "luettu": 4}
        assert "brick_delta_mv" not in k.suodata_live(a.decoder.snapshot(), False)
        a.live_kunto_sallittu = lambda: True
        assert len(api.kennot({}, {})["kennot"]) == 4
        assert k.suodata_live(a.decoder.snapshot(), True)["brick_delta_mv"] > 0


def test_ajotesti_katkot_ilman_energialaskureita():
    """Ilman energialaskureita (esim. Nissan Leaf) katkojen ajalta ei arvioida energiaa: pienet katkot kasvattavat
    epävarmuutta, ja yli 5 %:n katkot hylkäävät tuloksen selkeällä syyllä."""
    from akveri.analysis_ext import analyze_discharge

    def mittaa(aukot_s):
        A = {"t": 0, "soc_avg": 90.0, "e_in": 0.0, "e_out": 0.0, "i2_out": 0.0, "aukot_s": 0.0}
        L = {"t": 3600, "soc_avg": 30.0, "e_in": 0.5, "e_out": 12.0, "i2_out": 1.0e7, "aukot_s": aukot_s}
        return analyze_discharge({}, {"merkinnat": {"ajo_alku": A, "ajo_loppu": L}}, "NMC", 96, None, None, "ajo", None)

    ehja, pieni, suuri = mittaa(0), mittaa(90), mittaa(400)
    assert ehja["valmis"] and pieni["valmis"]
    assert ehja["epavarmuus_osat"]["katkot"] == 0
    assert pieni["epavarmuus_kwh"] > ehja["epavarmuus_kwh"]
    assert abs(pieni["taysi_kwh"] - ehja["taysi_kwh"]) < 1e-9, "katkojen energiaa ei arvioida tulokseen"
    assert not suuri["valmis"] and "katkesi" in suuri["syy"] and suuri["kattavuus_pct"] < 95


def test_perutun_mittauksen_kuntoa_ei_nayteta_missaan():
    """Akun kuntoa, kapasiteettia tai kennoeroa ei saa ilman maksua: perutun mittauksen tulos on piilossa listassa,
    mittausnäkymässä, näytteissä, tallennuksessa, uudelleenlaskennassa ja jaossa."""
    from akveri.app import App
    with tempfile.TemporaryDirectory() as d:
        a = App(Path(d))
        api = server.Api(a)
        vid = a.storage.add_vehicle({"nimi": "Testiauto", "malli_id": "hy-kona-64", "vin": "KMHK581GFLU123456"})
        tid = a.storage.add_test(vid, "pikatarkastus")
        tulos = {"yhteenveto": {"kunto_pct": 91.2, "kunto_luokka": "Erinomainen", "kapasiteetti_kwh": 58.4, "epavarmuus_kwh": 0.6},
                 "kennot": {"ero_mv": 12}}
        a.storage.update_test(tid, tila="valmis", tulos=tulos, lupa="ABCD1234", lupa_tila="peruttu")
        a.storage.add_samples(tid, [(1.0, "lepo", 358.0, 0.1, 60.0, 60.0, 58.4, 35.0, 20.0, 21.0, 3.70, 3.71, 0, 0, 0)])
        rivi = api.mittaukset({}, {})["mittaukset"][0]
        assert rivi["kunto_pct"] is None and rivi["kapasiteetti_kwh"] is None and rivi["ero_mv"] is None
        assert api.ajoneuvo({}, {}, vid)["mittaukset"][0]["kunto_pct"] is None
        m = api.mittaus({}, {}, tid)
        assert m["tulos"] is None
        assert all(n["nfp"] is None and n["c_max"] is None for n in m["naytteet"])
        assert "91.2" not in json.dumps(m) and "58.4" not in json.dumps(m)
        for kutsu in (api.tallenna_kansioon, api.laske_uudelleen, api.jaa_osiin):
            try:
                kutsu({}, {}, tid)
            except server.ApiError as e:
                assert e.code == 409
            else:
                raise AssertionError(kutsu.__name__)
        # Rekisteröidyn (maksetun) mittauksen tulos näkyy
        a.storage.update_test(tid, lupa_tila="rekisteroity")
        assert api.mittaukset({}, {})["mittaukset"][0]["kunto_pct"] == 91.2
        assert api.mittaus({}, {}, tid)["naytteet"][0]["nfp"] == 58.4
