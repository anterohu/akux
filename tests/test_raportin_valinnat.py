"""Raportin valinnat: kennoryhmien kuvaaja, pääsivu, mittauksen suorittaja, aiempien versioiden riippumattomuus,
vastuunrajaus ja sivunumerointi.

Ajo: python tests/test_raportin_valinnat.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akveri import analysis, charts, mittaustiedosto, report  # noqa: E402
from akveri.storage import Storage  # noqa: E402

ESIM = Path(__file__).resolve().parents[1] / "akveri" / "data" / "esimerkit" / "ESIM-301_taysi.akveri"


def _text(pdf: Path) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() for p in PdfReader(str(pdf)).pages)


def test_moduulijako():
    assert charts.module_layout("Model 3 Long Range", 96) == [23, 25, 25, 23]
    assert charts.module_layout("Model 3 Standard Range Plus LFP", 106) == [25, 28, 28, 25]
    assert charts.module_layout("Model S 85", 96) == [6] * 16
    assert charts.module_layout("Model Y Long Range", 96) is None      # ei varmistettua jakoa
    assert charts.module_layout("Model 3", 92) is None


def test_riippumattomuus_ja_sivut():
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d))
        tid = mittaustiedosto.import_file(st, ESIM.read_bytes())["id"]
        analysis.reanalyze(st, tid)
        assert st.test(tid)["riippumaton"] is None
        txt = _text(report.build(st, tid))
        assert "Riippumattomuus" not in txt and "Mittaus on tehty riippumattomasti" not in txt
        assert "ei ole takuu" in txt and "ohjelmiston toimittaja ei vastaa" in txt
        # Pääsivu on itsenäinen raportti: siinä ei ole sivunumeroa eikä lisäsivujen määrää; muissa tavallinen sivunumero
        import re  # noqa: PLC0415
        n = len(re.findall(r"Sivu \d+/\d+", txt)) + 1
        assert n >= 5 and f"Sivu 2/{n}" in txt and f"Sivu {n}/{n}" in txt and "Sivu 1/" not in txt, n
        assert "Pääsivu" not in txt and "Lisätiedot, sivu" not in txt
        assert "AKUN KUNTORAPORTTI" in txt and "MITÄ TULOS TARKOITTAA" not in txt and "RAPORTIN AITOUS" not in txt
        assert "Tulokset on luettu auton akunhallinnasta, ja AKVERI on laskenut ja varmentanut ne." in txt
        assert "Ei tarkistettavissa akveri.fi:ssä" in txt
        st.update_test(tid, riippumaton=1)
        st.save_settings({"kennokuvaaja": "moduulit"})
        txt = _text(report.build(st, tid))
        assert "Riippumaton mittaaja" in txt and "Mittaus on tehty riippumattomasti" in txt
        st.update_test(tid, riippumaton=0)
        txt = _text(report.build(st, tid))
        assert "Mittaaja ei ole riippumaton" in txt
        # Valinta kulkee mittaustiedoston mukana ja täyden testin osiin
        data = mittaustiedosto.export(st, tid, with_report=False)[1]
        osat = analysis.split_full_test(st, tid)
        assert all(st.test(o["id"])["riippumaton"] == 0 for o in osat if o["id"])
        st.close()
        if data:
            with tempfile.TemporaryDirectory() as d2:
                st2 = Storage(Path(d2))
                t2 = mittaustiedosto.import_file(st2, data)["id"]
                assert st2.test(t2)["riippumaton"] == 0
                st2.close()


def test_mittauksen_suorittaja():
    """Suorittaja näkyy raportissa ja lähtee akveri.fi:n tarkistussivulle; rekisteröidyn raportin tiedot lukitaan."""
    from akveri import krediitit, server  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d))
        tid = mittaustiedosto.import_file(st, ESIM.read_bytes())["id"]
        analysis.reanalyze(st, tid)
        st.save_settings({"mittaaja": "Asetusten oletus"})
        st.update_test(tid, mittaaja="Autoliike Esimerkki Oy", lupa="AK7H2QKM4XPC", lupa_tila="rekisteroity")
        txt = _text(report.build(st, tid))
        assert "Mittauksen suorittaja" in txt and "Autoliike Esimerkki Oy" in txt and "Asetusten oletus" not in txt
        assert "akveri.fi/v/AK-7H2QK-M4XPC" in txt and "Tarkista raportin aitous" in txt
        assert "Ei tarkistettavissa" not in txt
        # Yhteenveto palvelimelle sisältää suorittajan
        y = krediitit.Krediitit(st).yhteenveto(st.test(tid))
        assert y["suorittaja"] == "Autoliike Esimerkki Oy"
        # Rekisteröidyn raportin riippumattomuusmerkintää ei voi muuttaa
        class _App:
            storage = st
        h = server.Api.__new__(server.Api)
        h.app = _App()
        try:
            h.aseta_riippumattomuus({}, {"riippumaton": True}, tid)
            raise AssertionError("rekisteröidyn raportin tietoja ei saa muuttaa")
        except server.ApiError as e:
            assert "rekisteröity" in str(e)
        # Rekisteröimättömässä (vanhassa) mittauksessa suorittaja tulee asetuksista kuten ennen
        st.update_test(tid, mittaaja="", lupa=None, lupa_tila=None)
        assert "Asetusten oletus" in _text(report.build(st, tid))
        st.close()


if __name__ == "__main__":
    for fn in (test_moduulijako, test_riippumattomuus_ja_sivut, test_mittauksen_suorittaja):
        fn()
        print("OK", fn.__name__)
