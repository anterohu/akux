"""Kyselyalusta JSON-kuvauksesta: kyselyt, vastausten purku ja tuottaminen.

Arvo = (raaka + lisays) × kerroin. Raaka luetaan vastauksen tavusta 'tavu' (DID-tunnisteen jälkeen; negatiivinen
lasketaan lopusta) 'pituus' tavun mittaisena, suurin tavu ensin (tai pienin, jos alustalla tavujarjestys = little).
"""
from __future__ import annotations

import json
import re
import zlib
from functools import lru_cache
from pathlib import Path

TIEDOSTO = Path(__file__).resolve().parents[1] / "data" / "uudet" / "alustat.json"

# Kentät, jotka vastaavat dekooderin tilaa (akveri.decoder.State)
TILAKENTAT = {"pack_v", "pack_i", "soc_avg", "soc_ui", "bms_soh_pct", "nfp_kwh", "nominal_remaining_kwh", "temp_min",
              "temp_max", "odometer_km", "vin", "total_charge_kwh", "total_discharge_kwh", "cell_v_min", "cell_v_max"}
# Kentät, jotka tallennetaan alustakohtaisesti (dec.hk) tai lasketaan muista
MUUT_KENTAT = {"kennot", "lampotilat", "temp_avg", "eristys_kohm", "teho_kw"}


def _eup_jarjestys(i: int) -> int:
    """VW e-up!: kennojen kyselyjärjestys poikkeaa numeroinnista (evDash)."""
    return (i % 14) * 6 + i // 14 + 1


JARJESTYKSET = {"eup": _eup_jarjestys}


def _cid(alusta: str, ecu: str, kysely: str) -> int:
    return zlib.crc32(f"{alusta}:{ecu}:{kysely}".encode()) & 0x7FFFFFFF


class Kentta:
    def __init__(self, q: dict, little: bool):
        self.q = q
        self.nimi, self.kentta, self.tyyppi = q["nimi"], q["kentta"], q["tyyppi"]
        self.tavu, self.pituus = int(q.get("tavu", 0)), int(q.get("pituus", 2))
        self.kerroin, self.lisays = float(q.get("kerroin", 1.0)), float(q.get("lisays", 0))
        self.etumerkki, self.alue = bool(q.get("etumerkki")), q.get("alue")
        self.little = little
        self.maara = int(q.get("maara", 1))
        self.kenno_alku = int(q.get("kenno_alku", 1))

    # ---- raaka <-> arvo
    def _lue(self, d: bytes, i: int):
        if i < 0:
            i = len(d) + i
        if i < 0 or i + self.pituus > len(d):
            return None
        raw = int.from_bytes(d[i:i + self.pituus], "little" if self.little else "big", signed=self.etumerkki)
        return (raw + self.lisays) * self.kerroin

    def _sallittu(self, v) -> bool:
        # Puolen tarkkuusaskeleen sallittu ylitys: alueen reuna-arvo voi pyöristyä hieman alueen ulkopuolelle.
        e = abs(self.kerroin) / 2
        return v is not None and (not self.alue or self.alue[0] - e <= v <= self.alue[1] + e)

    def raaka(self, arvo: float) -> bytes:
        raw = round(arvo / self.kerroin - self.lisays)
        bits = 8 * self.pituus
        if self.etumerkki:
            if not -(1 << (bits - 1)) <= raw < (1 << (bits - 1)):
                raise ValueError(f"{self.nimi}: arvo {arvo} ei mahdu {self.pituus} tavuun")
            raw &= (1 << bits) - 1
        if not 0 <= raw < (1 << bits):
            raise ValueError(f"{self.nimi}: arvo {arvo} ei mahdu {self.pituus} tavuun")
        return raw.to_bytes(self.pituus, "little" if self.little else "big")

    def resoluutio(self) -> float:
        return abs(self.kerroin)

    def pura(self, d: bytes) -> list:
        """[(kenttä, arvo, indeksi)] kelvollisista arvoista."""
        if self.tyyppi == "vin":
            txt = bytes(b if 0x30 <= b <= 0x5A else 0x20 for b in d).decode("ascii", "ignore")
            m = re.search(r"[A-HJ-NPR-Z0-9]{17}", txt)
            return [(self.kentta, m.group(0), None)] if m else []
        if self.tyyppi in ("kennot", "lista"):
            out = []
            for k in range(self.maara):
                v = self._lue(d, self.tavu + k * self.pituus)
                if self._sallittu(v):
                    out.append((self.kentta, v, self.kenno_alku + k))
            return out
        v = self._lue(d, self.tavu)
        return [(self.kentta, v, None)] if self._sallittu(v) else []


class Alusta:
    def __init__(self, spec: dict):
        self.spec = spec
        self.id, self.nimi = spec["id"], spec["nimi"]
        self.merkit = tuple(spec.get("merkit") or ())
        self.little = spec.get("tavujarjestys") == "little"
        self.protokolla = spec["vayla"]["protokolla"]
        self.ohjainlaitteet = spec["ohjainlaitteet"]
        ehd = spec["ehdotus"]
        self.ei_testit = list(ehd.get("ei_testit") or [])
        self.resoluutio_mv = ehd.get("resoluutio_mv")
        self.elinkaarilaskurit = bool(ehd.get("elinkaarilaskurit"))
        self.soh_yli_100 = bool(ehd.get("soh_yli_100"))
        # kyselyt ryhmitellään vastauksittain: sama (ohjainlaite, kysely) = yksi tunniste, useita kenttiä
        self.kyselyt: dict[int, dict] = {}
        for q in spec["kyselyt"]:
            if q["tyyppi"] == "kenno_did":
                jarj = JARJESTYKSET.get(q.get("kennojarjestys"), lambda i: i + 1)
                for i in range(q["did_loppu"] - q["did_alku"] + 1):
                    nro = jarj(i)
                    if nro > q["maara"]:
                        continue
                    did = f"22{q['did_alku'] + i:04X}"
                    kq = {**q, "tyyppi": "kennot", "maara": 1, "kenno_alku": nro, "kysely": did}
                    self._lisaa(kq)
            else:
                self._lisaa(q)
        self.kunto_tunnisteet = tuple(c for c, k in self.kyselyt.items() if k["kysely"] in ehd["kunto_tunnisteet"])

    def _lisaa(self, q):
        cid = _cid(self.id, q["ecu"], q["kysely"])
        k = self.kyselyt.setdefault(cid, {"ecu": q["ecu"], "kysely": q["kysely"], "harva": False, "kentat": []})
        k["kentat"].append(Kentta(q, self.little))
        k["harva"] = k["harva"] or bool(q.get("harva"))

    # ---- kyselyt (sama muoto kuin nykyisten alustojen requests_for)
    def tx(self, ecu: str) -> str:
        o = self.ohjainlaitteet.get(ecu) or {}
        return o.get("tx") or o.get("doip_osoite") or "7DF"

    def requests_for(self, model: dict | None = None) -> tuple[list, list]:
        loop, rare = [], []
        for cid, k in self.kyselyt.items():
            (rare if k["harva"] else loop).append((self.tx(k["ecu"]), k["kysely"], cid))
        return loop, rare

    # ---- purku
    def pura(self, cid: int, data: bytes) -> list:
        k = self.kyselyt.get(cid)
        if not k:
            return []
        out = []
        for f in k["kentat"]:
            out += f.pura(bytes(data))
        return out

    def kasittele(self, tila: dict, cid: int, data: bytes) -> dict:
        """Päivittää tilan (sanakirja) vastauksesta: kennot ja lämpötilat listoina, ääriarvot lasketaan."""
        for kentta, arvo, ind in self.pura(cid, data):
            if kentta == "kennot":
                tila.setdefault("kennot", {})[ind] = arvo
            elif kentta == "lampotilat":
                tila.setdefault("lampotilat", {})[ind] = arvo
            elif kentta == "bms_soh_pct":
                tila[kentta] = arvo
                tila["soh_raportille"] = min(arvo, 100.0)
            else:
                tila[kentta] = arvo
        kn = tila.get("kennot")
        if kn:
            tila["cell_v_min_laskettu"], tila["cell_v_max_laskettu"] = min(kn.values()), max(kn.values())
        lt = tila.get("lampotilat")
        if lt:
            tila["temp_min"], tila["temp_max"] = min(lt.values()), max(lt.values())
        if "temp_avg" in tila and "temp_min" not in tila:
            tila["temp_min"] = tila["temp_max"] = tila["temp_avg"]
        return tila

    # ---- vastausten tuottaminen (testit ja tuleva simulaattori)
    def encode(self, cid: int, **arvot) -> bytes:
        k = self.kyselyt[cid]
        if any(f.tyyppi == "vin" for f in k["kentat"]):
            return bytes([1]) + arvot["vin"].encode("ascii")
        loppu = max(abs(f.tavu) + f.pituus * f.maara for f in k["kentat"])
        d = bytearray(max(loppu, arvot.get("_pituus", 0)))
        for f in k["kentat"]:
            if f.tyyppi in ("kennot", "lista"):
                lista = arvot.get(f.kentta) or {}
                for j in range(f.maara):
                    nro = f.kenno_alku + j
                    if nro in lista:
                        i = f.tavu + j * f.pituus
                        d[i:i + f.pituus] = f.raaka(lista[nro])
            elif f.nimi in arvot or f.kentta in arvot:
                v = arvot.get(f.nimi, arvot.get(f.kentta))
                i = f.tavu if f.tavu >= 0 else len(d) + f.tavu
                d[i:i + f.pituus] = f.raaka(v)
        return bytes(d)


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(TIEDOSTO.read_text(encoding="utf-8"))


def alustat() -> list[Alusta]:
    return [Alusta(a) for a in _data()["alustat"]]


def hae(alusta_id: str) -> Alusta:
    for a in _data()["alustat"]:
        if a["id"] == alusta_id:
            return Alusta(a)
    raise KeyError(alusta_id)
