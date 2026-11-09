"""Valmiin mittauksen uudelleenlaskenta ja täyden akkutestin jakaminen osiin.

Käyttää esimerkkimittausta (Model 3 LFP, täysi akkutesti), joka on tallennettu aiemmalla versiolla.
Ajo: python tests/test_uudelleenlaskenta.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux import VERSIO, analysis, maintenance, mittaustiedosto, report  # noqa: E402
from akux.storage import Storage  # noqa: E402

ESIM = Path(__file__).resolve().parents[1] / "akux" / "data" / "esimerkit" / "ESIM-301_taysi.akveri"


def test_uudelleenlaskenta_ja_jako():
    with tempfile.TemporaryDirectory() as d:
        st = Storage(Path(d))
        tid = mittaustiedosto.import_file(st, ESIM.read_bytes())["id"]
        t = st.test(tid)
        assert t["tyyppi"] == "taysi" and t["tila"] == "valmis"
        old = t["tulos"]
        old_ver = old.get("versio")
        # Uudelleenlaskenta: sama data, nykyinen laskenta
        res = analysis.reanalyze(st, tid)
        assert res["versio"] == VERSIO
        assert res["mittausversio"] == (old.get("mittausversio") or old_ver)
        if old_ver != VERSIO:
            assert res["aiempi_laskenta"]["versio"] == old_ver
        assert res["kennot"]["alue"] == "lfp_taysi", res["kennot"].get("alue")
        assert abs(res["yhteenveto"]["kunto_pct"] - old["yhteenveto"]["kunto_pct"]) < 0.05
        st.update_test(tid, tarkiste=t["tarkiste"])
        # Jako osiin
        osat = {o["tyyppi"]: o for o in analysis.split_full_test(st, tid)}
        cap, ajo = st.test(osat["kapasiteetti"]["id"]), st.test(osat["ajotesti"]["id"])
        assert cap["tyyppi"] == "kapasiteetti" and ajo["tyyppi"] == "ajotesti"
        rc, ra = cap["tulos"], ajo["tulos"]
        assert rc["paatulos"]["valmis"] and ra["paatulos"]["valmis"]
        assert abs(rc["kapasiteetti"]["taysi_kwh"] - res["kapasiteetti"]["taysi_kwh"]) < 1e-6
        assert abs(ra["purku"]["taysi_kwh"] - res["purku"]["taysi_kwh"]) < 1e-6
        assert rc["osa_testista"] == tid and ra["osa_testista"] == tid
        assert "osa täyttä akkutestiä nro" in cap["lisatiedot"]
        # Ajotestin matalan varauksen kennot ovat ajon jälkeiseltä levolta, eivät täydestä akusta
        assert ra["kennot_matala"]["soc"] < 40, ra["kennot_matala"]["soc"]
        # Raakadata on kopioitu: osat ovat eheitä ja niiden poisto ei koske alkuperäiseen
        for x in (cap, ajo):
            assert Path(x["raakadata"]).exists() and x["raakadata"] != t["raakadata"]
        st.delete_test(cap["id"])
        assert Path(t["raakadata"]).exists()
        for x in (tid, ajo["id"]):
            pdf = report.build(st, x)
            assert Path(pdf).stat().st_size > 20000
        print(f"Täysi {res['yhteenveto']['kunto_pct']:.1f} %, kapasiteettimittaus {rc['yhteenveto']['kunto_pct']:.1f} %, "
              f"ajotesti {ra['yhteenveto']['kunto_pct']:.1f} %; kennot {res['kennot']['ero_mv']:.0f} mV "
              f"{res['kennot']['soc']:.0f} %:ssa: {res['kennot']['luokka']}")
        st.close()


if __name__ == "__main__":
    test_uudelleenlaskenta_ja_jako()
    print("OK test_uudelleenlaskenta_ja_jako")
