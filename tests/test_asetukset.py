"""Asetukset: asiakas muuttaa vain kielen, käyttötavan ja raportin tiedot. Raporttien ulkoasu ja mittaustapa ovat
kaikille samat. Yksityisessä käytössä raportissa ei ole yrityksen tietoja. Logon tyhjät reunat rajataan.

Ajo: python tests/test_asetukset.py
"""
import io
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux import analysis, mittaustiedosto, report, server  # noqa: E402
from akux.storage import OLETUSASETUKSET, Storage  # noqa: E402

ESIM = Path(__file__).resolve().parents[1] / "akux" / "data" / "esimerkit" / "ESIM-301_taysi.akveri"


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
        # Kehittäjä (testitili) voi muuttaa raja-arvot ja ulkoasun
        k = _api(st, kehittaja=True).tallenna_asetukset({}, {"vesileima": "ei", "lepo_alku_min": 45})
        assert k["vesileima"] == "ei" and k["lepo_alku_min"] == 45
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
