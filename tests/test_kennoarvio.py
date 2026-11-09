"""Kennoryhmien jännite-eron arvio akkukemian ja varaustilan mukaan.

LFP-akun kennojännitteet eroavat täyteen ladattuna ja tyhjän lähellä luonnostaan enemmän kuin
keskivarauksella. Se ei saa näkyä vikana, mutta todellinen epätasapaino pitää yhä havaita.
Raja-arvot: normaali alue 15/30/50 mV, jyrkkä alue 50/100 mV (Generational, akkujärjestelmien ohjearvot).
Ajo: python tests/test_kennoarvio.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux.analysis import cell_stats, classify_cells, delta_class  # noqa: E402


def _pack(base, n=106, spread_mv=0.0, outlier=None):
    vs = [base + spread_mv / 1000 * ((i % 7) / 6 - 0.5) for i in range(n)]
    if outlier:
        k, mv = outlier
        vs[k] += mv / 1000
    return vs


def _arvio(vs, soc, chem):
    cs = cell_stats(vs, soc, 0.0)
    classify_cells(cs, chem)
    return cs


def test_lfp_taysi():
    # Täysi LFP-akku: 45 mV:n ero on tavanomainen, NCA-akulla sama ero on tyydyttävä
    cs = _arvio(_pack(3.38, spread_mv=45), 99, "LFP")
    assert cs["luokka"] == "Hyvä" and cs["alue"] == "lfp_taysi" and not cs["poikkeavat"], cs["luokka"]
    assert "ominaisuus eikä vika" in cs["selite"]
    assert _arvio(_pack(4.15, spread_mv=45), 99, "NCA")["luokka"] == "Tyydyttävä"
    assert _arvio(_pack(3.38, spread_mv=80), 99, "LFP")["luokka"] == "Tyydyttävä"
    # Todellinen epätasapaino näkyy yhä: yli 100 mV täydessä LFP-akussa on poikkeava
    assert _arvio(_pack(3.38, spread_mv=130), 99, "LFP")["luokka"] == "Poikkeava"
    # Yksittäinen ryhmä 20 mV muita korkeammalla täydessä LFP-akussa ei ole poikkeava, 40 mV on
    assert not _arvio(_pack(3.38, outlier=(10, 20)), 99, "LFP")["poikkeavat"]
    assert [p["nro"] for p in _arvio(_pack(3.38, outlier=(10, 40)), 99, "LFP")["poikkeavat"]] == [11]


def test_matala():
    cs = _arvio(_pack(3.10, spread_mv=45), 8, "LFP")
    assert cs["luokka"] == "Hyvä" and cs["alue"] == "lfp_matala"
    assert _arvio(_pack(3.10, spread_mv=200), 8, "LFP")["luokka"] == "Poikkeava"
    assert _arvio(_pack(3.40, spread_mv=70), 10, "NCA")["luokka"] == "Tyydyttävä"


def test_lfp_tasainen():
    # Keskivarauksella pieni ero ei todista tasapainoa: enintään "Hyvä"
    cs = _arvio(_pack(3.29, spread_mv=6), 55, "LFP")
    assert cs["luokka"] == "Hyvä" and cs["alue"] == "lfp_tasainen"
    assert "ei siksi yksin" in cs["selite"]
    # Tasaisella alueella 20 mV:n poikkeama on merkittävä ja havaitaan
    assert [p["nro"] for p in _arvio(_pack(3.29, outlier=(5, 20)), 55, "LFP")["poikkeavat"]] == [6]
    assert _arvio(_pack(3.29, spread_mv=40), 55, "LFP")["luokka"] == "Tyydyttävä"


def test_nca_ennallaan():
    assert delta_class(12, 60, "NCA") == "Erinomainen"
    assert delta_class(25, 60, "NMC") == "Hyvä"
    assert delta_class(60, 99, "NCA") == "Poikkeava"
    assert _arvio(_pack(3.90, spread_mv=10), 60, "NCA")["alue"] == "normaali"


if __name__ == "__main__":
    for fn in (test_lfp_taysi, test_matala, test_lfp_tasainen, test_nca_ennallaan):
        fn()
        print("OK", fn.__name__)
