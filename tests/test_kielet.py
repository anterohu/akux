"""Kielet: sanastojen eheys, käännösmoottori ja PDF-raportti englanniksi ja ruotsiksi.

Ajo: python tests/test_kielet.py
"""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from akux import kielet, mittaustiedosto, report  # noqa: E402
from akux.storage import Storage  # noqa: E402

SUOMI = re.compile(r"[äöÄÖ]|\b(ja|tai|ei|kun|jos|sekä|mittaus\w*|akun|auton|kennoryhm\w*|varaus\w*|lataus\w*|alkuperäi\w*|uutena|vrk)\b", re.I)


def test_sanastot():
    en, sv = kielet.sanasto("en"), kielet.sanasto("sv")
    assert len(en) > 1000 and set(en) == set(sv), "englannin ja ruotsin sanastoissa samat tekstit"
    for k in en:
        assert k.count("{}") == en[k].count("{}") == sv[k].count("{}"), k
        assert not SUOMI.search(re.sub(r"\{\}", "", en[k])) or "SK On" in en[k] or "On " in en[k], ("suomea englannissa", en[k])
    assert kielet.sanasto("fi") == {} and kielet.sanasto("xx") == {}


def test_kaannos():
    assert kielet.t("Aloita mittaus", "fi") == "Aloita mittaus"
    assert kielet.t("Aloita mittaus", "en") == "Start test"
    assert kielet.t("Aloita mittaus", "sv") == "Starta testet"
    assert kielet.t("  Aloita mittaus ", "en") == "  Start test ", "välilyönnit säilyvät"
    assert kielet.t("Akun varaus on 42 %.", "en") == "The battery charge level is 42 %."
    # Lause kerrallaan, jos koko tekstiä ei ole sanastossa
    assert kielet.t("Akun varaus on 42 %. Voit silti aloittaa mittauksen.", "en") == \
        "The battery charge level is 42 %. You can still start the test."
    # Merkin genetiivi: sanaston muoto on Teslan, käännökseen tulee oikea merkki
    assert kielet.t("Kian akunhallinta", "en") == "Kia's battery management system"
    # Lyhyt kuvio ei saa niellä useaa lausetta
    s = kielet.t("AKVERI lukee sähköauton ajoakun kunnon ja kapasiteetin suoraan auton akunhallinnasta ja kokoaa tiedot "
                 "raportiksi, jonka voi antaa ostajalle, asiakkaalle tai pitää itsellä. Tuntematon lause.", "en")
    assert s.startswith("AKVERI reads the health") and s.endswith("Tuntematon lause."), s
    assert kielet.t("Tuntematon teksti", "en") == "Tuntematon teksti"
    with kielet.kaytossa("sv"):
        assert kielet.t("Asetukset") == "Inställningar"
    assert kielet.nykyinen() in kielet.KIELET


def test_raportti_kielilla():
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d))
        f = sorted((Path(kielet.__file__).parent / "data" / "esimerkit").glob("*_taysi.akveri"))[0]
        r = mittaustiedosto.import_file(st, f.read_bytes(), merkitse=False)
        st.update_test(r["id"], demo=1, lupa=None, lupa_tila=None, lupa_testi=None)
        from pypdf import PdfReader  # noqa: PLC0415
        tekstit = {}
        for k in ("fi", "en", "sv"):
            p = report.build(st, r["id"], Path(d) / f"r-{k}.pdf", kieli=k)
            tekstit[k] = "\n".join(page.extract_text() or "" for page in PdfReader(str(p)).pages[:3])
        assert "Täysi akkutesti" in tekstit["fi"] and "Akun kunto" in tekstit["fi"]
        assert "Full battery test" in tekstit["en"] and "Battery health" in tekstit["en"]
        assert "Fullständigt batteritest" in tekstit["sv"] and "Batterihälsa" in tekstit["sv"]
        for k in ("en", "sv"):
            assert "Täysi akkutesti" not in tekstit[k] and "Kennoryhmien" not in tekstit[k] and "akunhallinta" not in tekstit[k].lower(), k
        assert kielet.nykyinen() == kielet.OLETUS, "raportin kieli ei jää päälle"


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
            print("OK", n)
