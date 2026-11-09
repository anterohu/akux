"""Raportin valinnat: kennoryhmien kuvaaja, mittaajan riippumattomuus, vastuunrajaus ja sivunumerointi.

Ajo: python tests/test_raportin_valinnat.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux import analysis, charts, mittaustiedosto, report  # noqa: E402
from akux.storage import Storage  # noqa: E402

ESIM = Path(__file__).resolve().parents[1] / "akux" / "data" / "esimerkit" / "ESIM-301_taysi.akveri"


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
        n = txt.count("Sivu ")
        assert f"Sivu 1/{n}" in txt and f"Sivu {n}/{n}" in txt, n
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


if __name__ == "__main__":
    for fn in (test_moduulijako, test_riippumattomuus_ja_sivut):
        fn()
        print("OK", fn.__name__)
