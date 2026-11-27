"""Uusien merkkien valmistellut tiedot (akveri/data/uudet/alustat.json): rakenne ja aiempien merkkien opit."""
import json
import re
from pathlib import Path

D = json.loads((Path(__file__).resolve().parents[1] / "akveri" / "data" / "uudet" / "alustat.json").read_text(encoding="utf-8"))


def test_jokainen_alusta_on_taydellinen():
    ids = set()
    for a in D["alustat"]:
        assert a["id"] not in ids
        ids.add(a["id"])
        for k in ("nimi", "mallit", "kemia", "vayla", "ohjainlaitteet", "kyselyt", "puuttuu", "ehdotus"):
            assert k in a, (a["id"], k)
        assert a["vayla"]["tunniste"] in ("11-bit", "29-bit"), a["id"]
        for q in a["kyselyt"]:
            for k in ("nimi", "ecu", "kysely", "kaava", "varmuus", "lahde"):
                assert q.get(k), (a["id"], q.get("nimi"), k)
            assert q["ecu"] in a["ohjainlaitteet"] or q["ecu"] == "obd", (a["id"], q["nimi"])
            assert q["varmuus"] in ("lahde", "arvio")
            assert all(s.strip().split(" ")[0] in D["_lahteet"] for s in q["lahde"].split(",")), q["lahde"]


def test_kuntotiedot_on_kysytty():
    """Pikatarkastus voidaan estää ennen ostoa vain, jos kuntotiedon kysely on tiedossa (opittu Volkswagenista)."""
    for a in D["alustat"]:
        kyselyt = {q["kysely"] for q in a["kyselyt"]}
        for k in a["ehdotus"]["kunto_tunnisteet"]:
            assert k in kyselyt, (a["id"], k)


def test_kennottomilla_alustoilla_kennotestit_estetty():
    """Ilman yksittäisiä kennojännitteitä itsepurkausta ei voi mitata (opittu MG:stä)."""
    for a in D["alustat"]:
        tapa = a["ehdotus"]["kennolukutapa"]
        if tapa.startswith("ei kenno") or tapa.startswith("vain"):
            assert "itsepurkaus" in a["ehdotus"]["ei_testit"], a["id"]


def test_yli_sadan_kunto_ei_ole_jumissa():
    """e-CMP:n kunto voi olla yli 100 %: jumissa olevan kunnon sääntöä ei saa soveltaa (opittu Hyundaista)."""
    e = next(a for a in D["alustat"] if a["id"] == "ecmp")
    assert e["ehdotus"]["soh_jumissa_yli"] is None


def test_ei_kilpailijoiden_nimia():
    teksti = json.dumps(D, ensure_ascii=False)
    assert not re.search("AVILOO|Aviloo|Generational|DEKRA", teksti)
