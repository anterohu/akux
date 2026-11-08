"""Nimenvaihto Akux → AKVERI: vanhat kansiot siirtyvät ja tallennetut polut korjautuvat, mitään ei katoa.

Ajo: python tests/test_nimenvaihto.py
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux import mittaustiedosto  # noqa: E402
from akux.storage import Storage, siirra_kansio, uusi_polku  # noqa: E402


def _vanha_asennus(root: Path):
    old = root / "Akux"
    st = Storage(old)
    vid = st.add_vehicle({"vin": "5YJ3E7EB1LF654321", "rekisteri": "ABC-123"})
    tid = st.add_test(vid, "kapasiteetti", None, "Testi")
    raw = old / "raakadata" / f"mittaus_{tid:05d}.csv.gz"
    raw.write_bytes(b"raakadata")
    st.update_test(tid, raakadata=str(raw), tila="valmis")
    (old / "logo.png").write_bytes(b"png")
    docs = root / "Docs"
    (docs / "Akux" / "Mittaukset").mkdir(parents=True)
    (docs / "Akux" / "Mittaukset" / "AKUX_ABC-123.akux").write_bytes(b"x")
    st.save_settings({"logo": str(old / "logo.png"), "yritys_nimi": "Testi Oy",
                      "mittaus_kansio": str(docs / "Akux" / "Mittaukset")})
    st.close()
    return tid


def test_siirto():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        tid = _vanha_asennus(root)
        uusi = siirra_kansio(root / "Akux", root / "AKVERI", "akux.db")
        assert uusi == root / "AKVERI" and not (root / "Akux").exists()
        siirra_kansio(root / "Docs" / "Akux", root / "Docs" / "AKVERI", "Mittaukset")
        assert (root / "Docs" / "AKVERI" / "Mittaukset" / "AKUX_ABC-123.akux").exists()
        st = Storage(uusi)
        t = st.test(tid)
        assert Path(t["raakadata"]).read_bytes() == b"raakadata", t["raakadata"]
        s = st.settings()
        assert s["yritys_nimi"] == "Testi Oy"
        assert Path(s["logo"]) == uusi / "logo.png"
        assert Path(s["mittaus_kansio"]) == root / "Docs" / "AKVERI" / "Mittaukset"
        assert st.vehicles()[0]["rekisteri"] == "ABC-123"
        st.close()
        # Toinen käynnistys: ei tee mitään
        assert siirra_kansio(root / "Akux", root / "AKVERI", "akux.db") == uusi


def test_uusi_kansio_jo_olemassa():
    """Uusi kansio on syntynyt tyhjänä ennen siirtoa: vanhat tiedot siirretään sinne."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        tid = _vanha_asennus(root)
        (root / "AKVERI").mkdir()
        (root / "AKVERI" / "loki.txt").write_text("uusi")
        uusi = siirra_kansio(root / "Akux", root / "AKVERI", "akux.db")
        assert uusi == root / "AKVERI" and (uusi / "akux.db").exists()
        st = Storage(uusi)
        assert Path(st.test(tid)["raakadata"]).exists()
        st.close()


def test_siirto_ei_onnistu():
    """Jos siirto ei onnistu, käytetään vanhaa kansiota sellaisenaan."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _vanha_asennus(root)
        orig = Path.rename
        Path.rename = lambda self, target: (_ for _ in ()).throw(PermissionError("käytössä"))
        try:
            assert siirra_kansio(root / "Akux", root / "AKVERI", "akux.db") == root / "Akux"
        finally:
            Path.rename = orig
        assert (root / "Akux" / "akux.db").exists() and not (root / "AKVERI").exists()


def test_paate():
    assert mittaustiedosto.PAATE == ".akveri" and ".akux" in mittaustiedosto.LUETTAVAT_PAATTEET
    assert uusi_polku(None) is None and uusi_polku("/ei/ole") is None


if __name__ == "__main__":
    for fn in (test_siirto, test_uusi_kansio_jo_olemassa, test_siirto_ei_onnistu, test_paate):
        fn()
        print("OK", fn.__name__)
