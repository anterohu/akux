"""Uusien merkkien valmistellut kyselyalustat (akveri/data/uudet/alustat.json, akveri/uudet).

Alustoja ei ole liitetty ohjelmaan. Testit varmistavat, että tiedot ovat täydelliset, vastausten purku ja tuottaminen
toimivat kaikilla kentillä ja reunoilla, roskadata ei kaada mitään, ja aiempien merkkien opit pysyvät voimassa.
"""
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akveri.uudet import alustat, hae  # noqa: E402
from akveri.uudet.moottori import MUUT_KENTAT, TIEDOSTO, TILAKENTAT  # noqa: E402

D = json.loads(TIEDOSTO.read_text(encoding="utf-8"))
A = alustat()


def _arvot(f, rng):
    """Satunnainen arvo kentän sallitulta alueelta, pyöristettynä kentän tarkkuuteen."""
    lo, hi = f.alue
    v = rng.uniform(lo, hi)
    return round(v / f.kerroin) * f.kerroin


# ---------------------------------------------------------------- rakenne
def test_tiedot_ovat_taydelliset():
    ids = set()
    for a in D["alustat"]:
        assert a["id"] not in ids
        ids.add(a["id"])
        for k in ("nimi", "merkit", "mallit", "kemia", "vayla", "ohjainlaitteet", "kyselyt", "puuttuu", "ehdotus"):
            assert k in a, (a["id"], k)
        for q in a["kyselyt"]:
            for k in ("nimi", "ecu", "kysely", "kentta", "tyyppi", "varmuus", "lahde"):
                assert q.get(k) not in (None, ""), (a["id"], q.get("nimi"), k)
            assert q["ecu"] in a["ohjainlaitteet"] or q["ecu"] == "obd", (a["id"], q["nimi"])
            assert q["varmuus"] in ("lahde", "arvio")
            assert q["kentta"] in TILAKENTAT | MUUT_KENTAT, (a["id"], q["kentta"])
            for s in q["lahde"].split(","):
                assert s.strip() in D["_lahteet"], (a["id"], s)
            if q["tyyppi"] != "vin":
                assert q["alue"] and q["alue"][0] < q["alue"][1], (a["id"], q["nimi"])
                assert q["kerroin"] != 0


def test_osoitteet_vastaavat_vaylaa():
    """11-bittinen tunniste on 3 heksamerkkiä, 29-bittinen 8 (opittu Volkswagenista: väylä vaihtelee)."""
    for a in D["alustat"]:
        t = a["vayla"]["tunniste"]
        for nimi, o in a["ohjainlaitteet"].items():
            for k in ("tx", "rx"):
                if k in o:
                    assert len(o[k]) == {"11-bit": 3, "29-bit": 8}[t], (a["id"], nimi, o[k])
                    assert re.fullmatch(r"[0-9A-F]+", o[k])
            if t == "DoIP":
                assert re.fullmatch(r"[0-9A-F]{4}", o["doip_osoite"])


def test_kyselyt_ovat_kelvollisia():
    for a in A:
        loop, rare = a.requests_for()
        assert loop or rare
        nahty = set()
        for tx, cmd, _cid in loop + rare:
            assert re.fullmatch(r"(22[0-9A-F]{4}|21[0-9A-F]{2}|0902)", cmd), (a.id, cmd)
            assert (tx, cmd) not in nahty, (a.id, cmd)       # sama kysely ei toistu kierroksella
            nahty.add((tx, cmd))


# ---------------------------------------------------------------- purku ja tuottaminen
def test_jokainen_kentta_purkautuu_takaisin():
    rng = random.Random(1)
    for a in A:
        for cid, k in a.kyselyt.items():
            for f in k["kentat"]:
                if f.tyyppi == "vin":
                    vin = "VR3UHZKXZNT080667"
                    assert a.pura(cid, a.encode(cid, vin=vin)) == [(f.kentta, vin, None)]
                    continue
                if f.tyyppi in ("kennot", "lista"):
                    continue
                kokeilut = [f.alue[0], f.alue[1]] + [_arvot(f, rng) for _ in range(25)]
                for v in kokeilut:
                    try:
                        d = a.encode(cid, **{f.nimi: v}, _pituus=12 if f.tavu < 0 else 0)
                    except ValueError:
                        continue                              # alueen reuna ei mahdu tavuihin: ei voi esiintyä
                    saatu = [x for x in a.pura(cid, d) if x[0] == f.kentta]
                    assert saatu, (a.id, f.nimi, v)
                    assert abs(saatu[0][1] - v) <= f.resoluutio() / 2 + 1e-9, (a.id, f.nimi, v, saatu)


def test_reunojen_ulkopuoliset_ja_lyhyet_vastaukset_hylataan():
    for a in A:
        for cid, k in a.kyselyt.items():
            assert a.pura(cid, b"") == []
            for f in k["kentat"]:
                if f.tyyppi in ("vin",):
                    continue
                lyhyt = bytes(max(0, f.tavu + f.pituus - 1)) if f.tavu >= 0 else b"\x00"
                for kentta, _v, _ in a.pura(cid, lyhyt):
                    assert kentta != f.kentta or f.tyyppi in ("kennot", "lista"), (a.id, f.nimi)


def test_roskadata_ei_kaada_eika_tuota_mahdottomia_arvoja():
    rng = random.Random(7)
    for a in A:
        for cid, k in a.kyselyt.items():
            alueet = {f.kentta: f.alue for f in k["kentat"] if f.alue}
            for _ in range(60):
                d = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 300)))
                for kentta, v, _ in a.pura(cid, d):
                    if kentta in alueet:
                        lo, hi = alueet[kentta]
                        e = max(abs(f.kerroin) for f in k["kentat"] if f.kentta == kentta) / 2
                        assert lo - e <= v <= hi + e, (a.id, kentta, v)


def test_simuloitu_auto_jokaiselle_alustalle():
    """Koko auto: kaikki vastaukset tuotetaan tunnetuista arvoista ja puretaan takaisin samaan tilaan."""
    rng = random.Random(3)
    for a in A:
        tosi, tila = {}, {}
        for cid, k in a.kyselyt.items():
            arvot = {}
            for f in k["kentat"]:
                if f.tyyppi == "vin":
                    arvot["vin"] = tosi["vin"] = "WVWZZZAUZLW000001"
                elif f.tyyppi in ("kennot", "lista"):
                    lista = {f.kenno_alku + j: _arvot(f, rng) for j in range(f.maara)}
                    arvot.setdefault(f.kentta, {}).update(lista)
                    tosi.setdefault(f.kentta, {}).update(lista)
                else:
                    v = _arvot(f, rng)
                    arvot[f.nimi] = v
                    tosi[(f.kentta, f.nimi)] = v
            if any(f.tavu < 0 for f in k["kentat"]):
                arvot["_pituus"] = 12
            a.kasittele(tila, cid, a.encode(cid, **arvot))
        for avain, v in tosi.items():
            if isinstance(avain, tuple):
                kentta, nimi = avain
                f = next(f for k in a.kyselyt.values() for f in k["kentat"] if f.nimi == nimi)
                if sum(1 for k in a.kyselyt.values() for g in k["kentat"] if g.kentta == kentta) > 1:
                    continue                                  # sama kenttä useasta kyselystä (esim. kaksi vuosimallia)
                assert abs(tila[kentta] - v) <= f.resoluutio() / 2 + 1e-9, (a.id, nimi)
            elif avain == "vin":
                assert tila["vin"] == v
            else:
                assert set(tila[avain]) == set(v), (a.id, avain)
                for nro, x in v.items():
                    assert abs(tila[avain][nro] - x) < 1e-6, (a.id, avain, nro)


# ---------------------------------------------------------------- alustakohtaiset erityispiirteet
def test_eup_kennojarjestys_kattaa_kaikki_kennot_kerran():
    a = hae("eup")
    kennot = {}
    for _cid, k in a.kyselyt.items():
        for f in k["kentat"]:
            if f.kentta == "kennot":
                assert f.kenno_alku not in kennot, f.kenno_alku
                kennot[f.kenno_alku] = int(k["kysely"][2:], 16)
    assert sorted(kennot) == list(range(1, 85))
    assert min(kennot.values()) == 0x1E40 and max(kennot.values()) == 0x1E93
    assert kennot[1] == 0x1E40 and kennot[7] == 0x1E41       # (i % 14) × 6 + i // 14 + 1


def test_ecmp_kaikki_kennot_ja_lampotilat_yhdesta_vastauksesta():
    a = hae("ecmp")
    cid_k = next(c for c, k in a.kyselyt.items() if k["kysely"] == "22D440")
    cid_t = next(c for c, k in a.kyselyt.items() if k["kysely"] == "22D442")
    kennot = {i: 3.6 + i / 10000 for i in range(1, 109)}
    lampo = {i: 10.0 + (i % 5) for i in range(1, 55)}
    tila = {}
    a.kasittele(tila, cid_k, a.encode(cid_k, kennot=kennot))
    a.kasittele(tila, cid_t, a.encode(cid_t, lampotilat=lampo))
    assert len(tila["kennot"]) == 108 and len(tila["lampotilat"]) == 54
    assert abs(tila["cell_v_max_laskettu"] - 3.6108) <= 0.0005
    assert tila["temp_min"] == 10.0 and tila["temp_max"] == 14.0


def test_ecmp_yli_sadan_kunto_sailyy_mutta_raportissa_enintaan_sata():
    """Uuden akun kunto voi olla yli 100 %. Sitä ei tulkita jumissa olevaksi (opittu Hyundaista)."""
    a = hae("ecmp")
    cid = next(c for c, k in a.kyselyt.items() if k["kysely"] == "22D860")
    tila = a.kasittele({}, cid, a.encode(cid, kunto=103.0))
    assert tila["bms_soh_pct"] == 103.0 and tila["soh_raportille"] == 100.0
    e = next(x for x in D["alustat"] if x["id"] == "ecmp")["ehdotus"]
    assert e["soh_jumissa_yli"] is None and e["soh_yli_100"] is True


def test_sama_tunniste_eri_merkeissa_tarkoittaa_eri_asiaa():
    """22490C on Fordissa kunto ja Jaguarissa virta: kyselyt on sidottu alustaan."""
    f, j = hae("mache"), hae("ipace")
    cf = next(c for c, k in f.kyselyt.items() if k["kysely"] == "22490C")
    cj = next(c for c, k in j.kyselyt.items() if k["kysely"] == "22490C")
    assert cf != cj
    d = bytes([0xB4, 0x00])
    assert [x[0] for x in f.pura(cf, d)] == ["bms_soh_pct"]
    assert [x[0] for x in j.pura(cj, d)] == ["pack_i"]


def test_bmw_kentat_vastauksen_lopusta():
    """BMW:n energialaskurit luetaan vastauksen lopusta, koska alun pituus vaihtelee."""
    a = hae("bmw")
    cid = next(c for c, k in a.kyselyt.items() if k["kysely"] == "22DD7C")
    for alku in (0, 3, 7):
        d = bytes(alku) + (123456789).to_bytes(4, "big") + (98765432).to_bytes(4, "big")
        t = dict((k, v) for k, v, _ in a.pura(cid, d))
        assert abs(t["total_charge_kwh"] - 1234.56789) < 1e-6
        assert abs(t["total_discharge_kwh"] - 987.65432) < 1e-6


def test_byd_pienin_tavu_ensin():
    a = hae("byd")
    cid = next(c for c, k in a.kyselyt.items() if k["kysely"] == "221FFC")
    assert dict((k, v) for k, v, _ in a.pura(cid, bytes([0, 0x10, 0x27])))["soc_avg"] == 100.0


def test_virran_etumerkki_on_kirjattu():
    """Purku on AKVERIssa positiivinen. Lähteiden käytännöt vaihtelevat, joten jokaiseen virtaan on merkintä."""
    for a in D["alustat"]:
        for q in a["kyselyt"]:
            if q["kentta"] == "pack_i":
                assert "purku positiivinen" in q.get("huom", ""), (a["id"], q["nimi"])


# ---------------------------------------------------------------- aiempien merkkien opit
def test_pikatarkastus_vain_kun_kunto_tunnetaan():
    """Pikatarkastusta ei voi myydä ilman kuntotietoa (opittu Volkswagenista)."""
    for a in A:
        if not a.kunto_tunnisteet:
            assert "pikatarkastus" in a.ei_testit, a.id


def test_kennottomilla_kennotestit_estetty():
    """Ilman yksittäisiä kennojännitteitä itsepurkausta ei voi mitata (opittu MG:stä)."""
    for a in D["alustat"]:
        tapa = a["ehdotus"]["kennolukutapa"]
        if tapa.startswith("ei kenno") or tapa.startswith("vain"):
            assert "itsepurkaus" in a["ehdotus"]["ei_testit"], a["id"]


def test_kunto_tunnisteet_kuuluvat_kyselyihin():
    for a in D["alustat"]:
        kyselyt = {q["kysely"] for q in a["kyselyt"]}
        for k in a["ehdotus"]["kunto_tunnisteet"]:
            assert k in kyselyt, (a["id"], k)


def test_puuttuvat_tiedot_on_kirjattu():
    """Mittarilukeman ja valmistenumeron puute kirjataan (opittu Teslasta ja Ioniqista)."""
    for a in D["alustat"]:
        kentat = {q["kentta"] for q in a["kyselyt"]}
        if "odometer_km" not in kentat:
            assert any("mittarilukema" in p for p in a["puuttuu"]) or a["id"] == "polestar", a["id"]


def test_ei_kilpailijoiden_nimia():
    assert not re.search("AVILOO|Aviloo|Generational|DEKRA", json.dumps(D, ensure_ascii=False))


def test_sallittu_alue_mahtuu_tavuihin():
    """Kentän koko alueen on oltava esitettävissä sen tavuilla; muuten laskuri tai arvo pyörähtää huomaamatta."""
    for a in A:
        for k in a.kyselyt.values():
            for f in k["kentat"]:
                if f.tyyppi == "vin":
                    continue
                for v in f.alue:
                    try:
                        f.raaka(v)
                    except ValueError:
                        # reuna saa olla puolen askeleen päässä esitettävästä arvosta
                        assert any(_mahtuu(f, v + s * abs(f.kerroin)) for s in (-1, 1)), (a.id, f.nimi, v)


def _mahtuu(f, v):
    try:
        f.raaka(v)
        return True
    except ValueError:
        return False
