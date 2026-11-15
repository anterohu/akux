"""Krediitit ja testiluvat (akveri.fi).

Mittauksen hinta krediitteinä riippuu mittaustyypistä (asetetaan akveri.fi:n hallinnassa). Oikeasta autosta tehtävä mittaus alkaa vasta, kun palvelin on antanut testiluvan
(krediitti veloitetaan). Lupa on raportin tunnus, ja raportin QR-koodi avaa sen tarkistussivun.

Peruminen: lupa on perumisajan (oletus 60 min) sisällä peruttavissa, jos mittaus keskeytetään, ja krediitti
palautuu. Jotta keskeyttäminen ei antaisi akun kuntoa ilmaiseksi, reaaliaikainen kunto- ja kapasiteettiarvio
näytetään vain käynnissä olevassa mittauksessa ja vasta perumisajan jälkeen. Valmista mittausta ei voi perua.
Perutun luvan mittauksesta ei tehdä raporttia, ja tarkistussivu näyttää luvan perutuksi.

Esittelytilan (simuloitu auto) mittaukset eivät tarvitse lupaa. Niiden raportteihin tulee ESIMERKKI-leima.
Ennen versiota 2.0 tehdyillä mittauksilla ei ole lupaa: niiden raportissa kerrotaan, ettei raporttia voi tarkistaa.
"""
from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.error
import urllib.request

OLETUSOSOITE = "https://akveri.fi"
OLETUS_PERUMISAIKA_MIN = 60

# Live-tiedot, joista akun kunnon tai kapasiteetin voi päätellä. Näytetään vain, kun mittaukseen on oikeus.
KUNTOKENTAT = ("bol_kwh", "nfp_kwh", "nominal_remaining_kwh", "expected_remaining_kwh", "ideal_remaining_kwh",
               "to_charge_complete_kwh", "buffer_kwh", "bms_soh_pct", "viite_kwh", "viite_lahde", "full_charge_complete",
               "brick_delta_mv")   # kennoryhmien jännite-ero ja yksittäiset jännitteet näkyvät vain mittauksessa


class PalveluVirhe(Exception):
    def __init__(self, viesti: str, status: int = 0):
        super().__init__(viesti)
        self.status = status


def _ssl_konteksti():
    try:
        import certifi  # noqa: PLC0415
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def _http(method: str, url: str, headers: dict, body: bytes | None, aikaraja: float):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=aikaraja, context=_ssl_konteksti()) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            return e.code, {}


# ---------------------------------------------------------------- luvan tila
def luvan_tila(t: dict) -> str:
    """esimerkki | vanha | osa | tuotu | varattu | rekisteroity | ei_rekisteroitavissa | peruttu | peru_odottaa |
    tarkistus_odottaa | tarkistettava (tulos ei läpäissyt järkevyystarkistusta: krediitit palautetaan)"""
    if t.get("demo"):
        return "esimerkki"
    if not t.get("lupa"):
        return "vanha"
    if t.get("lupa_tila") == "osa":
        return "osa"
    return t.get("lupa_tila") or "varattu"


def tulos_odottaa(t: dict, nyt: float | None = None) -> bool:
    """Valmiin mittauksen tulos odottaa rekisteröintiä: luvan voi vielä perua (krediitit palautuisivat), joten tulosta ei
    näytetä ennen kuin raportti on rekisteröity tai perumisaika on varmasti kulunut myös palvelimen kellolla."""
    if luvan_tila(t) != "varattu" or t.get("tila") != "valmis" or t.get("lupa_testi"):
        return False
    return (nyt or time.time()) <= float(t.get("lupa_peruttavissa") or 0) + 240


def tulos_naytettavissa(t: dict, nyt: float | None = None) -> bool:
    """Perutun luvan mittauksen tulosta ja raporttia ei näytetä, eikä rekisteröintiä odottavan mittauksen tulosta
    perumisaikana (muuten lyhyen mittauksen tuloksen voisi katsoa ja perua luvan)."""
    return luvan_tila(t) not in ("peruttu", "peru_odottaa", "tarkistus_odottaa", "tarkistettava") and not tulos_odottaa(t, nyt)


def live_kunto_sallittu(t: dict | None, simuloitu: bool, nyt: float | None = None) -> bool:
    """Reaaliaikainen kuntoarvio: esittelytilassa aina, oikeassa autossa vain käynnissä olevassa luvallisessa mittauksessa
    perumisajan jälkeen."""
    if simuloitu:
        return True
    if not t or luvan_tila(t) != "varattu":
        return bool(t) and luvan_tila(t) == "rekisteroity"
    return (nyt or time.time()) > float(t.get("lupa_peruttavissa") or 0)


def peruttavissa(t: dict, nyt: float | None = None) -> bool:
    return luvan_tila(t) == "varattu" and (nyt or time.time()) <= float(t.get("lupa_peruttavissa") or 0)


def _versio(v: str) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return (0, 0, 0)


def muotoile_tunnus(t: str | None) -> str:
    return f"{t[:2]}-{t[2:7]}-{t[7:]}" if t and len(t) == 12 else (t or "")


def anonyymi_tiedot(r: dict) -> dict:
    """Mittauksen anonyymit lisätiedot akveri.fi:n tilastoaineistoon (ei tunnisteita: ei valmistenumeroa, rekisterinumeroa,
    nimiä eikä tarkkaa aikaa). Palvelin tallentaa ne erilliseen aineistoon, jota ei voi yhdistää raporttiin."""
    a = r.get("ajoneuvo") or {}
    k = r.get("kennot") or {}
    lt = r.get("lampotilat") or {}
    kk = r.get("kapasiteetit") or {}
    y = r.get("yhteenveto") or {}
    pt = next((x for x in (r.get("paatulos"), r.get("yhdistetty"), r.get("kapasiteetti"), r.get("purku"))
               if x and x.get("ero_bms_pct") is not None), {}) or {}
    out = {"alusta": a.get("alusta"), "kemia": a.get("kemia"), "kennotyyppi": a.get("kennotyyppi"),
           "vuosimalli": a.get("vuosimalli") or (a.get("vin_tiedot") or {}).get("vuosimalli"),
           "kennoryhmat": a.get("kennoryhmat"), "uutena_kwh": (r.get("viite") or {}).get("kwh"),
           "jannite_ero_mv": k.get("ero_mv"), "ero_bms_pct": pt.get("ero_bms_pct"),
           "epavarmuus_kwh": y.get("epavarmuus_kwh"), "lampo_min_c": lt.get("min"), "lampo_max_c": lt.get("max"),
           "suojavara_kwh": kk.get("puskuri_kwh")}
    return {k_: v for k_, v in out.items() if v not in (None, "")}


class Krediitit:
    """akveri.fi-palvelun asiakas. Tilin tunnus ja avain tallennetaan ohjelman asetuksiin."""

    def __init__(self, storage, http=_http):
        self.storage = storage
        self.http = http
        self.lock = threading.Lock()
        self._rekisteroinnit: set[int] = set()

    @property
    def osoite(self) -> str:
        # Palvelun osoitetta ei voi vaihtaa käyttöliittymästä. Kehityksessä sen voi ohittaa ympäristömuuttujalla.
        import os  # noqa: PLC0415
        return (os.environ.get("AKVERI_PALVELU") or OLETUSOSOITE).rstrip("/")

    def _kutsu(self, method: str, polku: str, body: dict | None = None, tunnistus=True, aikaraja=20.0) -> dict:
        from . import VERSIO  # noqa: PLC0415
        headers = {"Accept": "application/json", "User-Agent": f"AKVERI/{VERSIO}", "X-AKVERI-Versio": VERSIO}
        if tunnistus:
            s = self.varmista_tili()
            headers["Authorization"] = f"AKVERI {s['tili']}.{s['avain']}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            status, d = self.http(method, self.osoite + polku, headers, data, aikaraja)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise PalveluVirhe("AKVERI-palveluun ei saatu yhteyttä. Tarkista verkkoyhteys ja yritä uudelleen.") from e
        if status >= 400:
            raise PalveluVirhe(d.get("virhe") or f"AKVERI-palvelu vastasi virheellä ({status}).", status)
        return d

    def varmista_tili(self) -> dict:
        with self.lock:
            s = self.storage.settings()
            if s.get("tili") and s.get("tili_avain"):
                return {"tili": s["tili"], "avain": s["tili_avain"]}
            d = self._kutsu("POST", "/api/v1/tili", {}, tunnistus=False)
            self.storage.save_settings({"tili": d["tili"], "tili_avain": d["avain"]})
            return {"tili": d["tili"], "avain": d["avain"]}

    def tilanne(self) -> dict:
        d = self._kutsu("GET", "/api/v1/saldo")
        self._muista_esittely(d)
        d["tuotteet"] = self._kutsu("GET", "/api/v1/tuotteet", tunnistus=False).get("tuotteet", [])
        d["versiot"] = self.versiot()
        return d

    # ------------------------------------------------------------ esittelytila
    # Esittelytila ja esimerkkiautot eivät näy asiakkaille. Ne ovat käytössä vain tileillä, jotka on merkitty
    # testitileiksi akveri.fi:n hallinnassa, sekä kehitys- ja testiversioissa (AKVERI_ESITTELY=1).
    def _muista_esittely(self, d: dict):
        sallittu = bool(d.get("testitili"))
        if bool(self.storage.settings().get("esittely")) != sallittu:
            self.storage.save_settings({"esittely": sallittu})

    def esittely_sallittu(self, tarkista: bool = False) -> bool:
        import os  # noqa: PLC0415
        if os.environ.get("AKVERI_ESITTELY") == "1":
            return True
        if tarkista:
            try:
                self._muista_esittely(self._kutsu("GET", "/api/v1/saldo", aikaraja=10.0))
            except PalveluVirhe:
                pass
        return bool(self.storage.settings().get("esittely"))

    def versiot(self) -> dict:
        """Palvelimen ilmoittama vähimmäis- ja uusin versio verrattuna tähän versioon."""
        from . import VERSIO  # noqa: PLC0415
        t = self._kutsu("GET", "/api/v1/tila", tunnistus=False, aikaraja=10.0)
        nyt = _versio(VERSIO)
        return {"nykyinen": VERSIO, "vahimmaisversio": t.get("vahimmaisversio"), "uusin": t.get("uusinVersio") or "",
                "paivitys_pakollinen": bool(t.get("vahimmaisversio")) and nyt < _versio(t["vahimmaisversio"]),
                "paivitys_saatavilla": bool(t.get("uusinVersio")) and nyt < _versio(t["uusinVersio"])}

    def osto(self, tuote: str, ostotunnus: str) -> dict:
        return self._kutsu("POST", "/api/v1/osto", {"tuote": tuote, "ostotunnus": ostotunnus}, aikaraja=40.0)

    def varaa(self, versio: str, alusta: str, tyyppi: str = "") -> dict:
        body = {"versio": versio, "alusta": alusta}
        if tyyppi:
            body["tyyppi"] = tyyppi  # palvelin veloittaa mittaustyypin hinnan (hallinnassa asetettu)
        return self._kutsu("POST", "/api/v1/testi/varaa", body)

    def peru(self, tunnus: str, syy: str) -> dict:
        return self._kutsu("POST", "/api/v1/testi/peru", {"tunnus": tunnus, "syy": syy})

    def hyvityspyynto(self, tunnus: str, syy: str, tiedot: str) -> dict:
        return self._kutsu("POST", "/api/v1/testi/hyvityspyynto", {"tunnus": tunnus, "syy": syy, "tiedot": tiedot})

    # ------------------------------------------------------------ mittauksen elinkaari
    def kiinnita(self, tid: int, lupa: dict):
        """Tallentaa saadun luvan mittaukselle."""
        perumisaika = float(lupa.get("hyvitysaikaMin") or OLETUS_PERUMISAIKA_MIN) * 60
        self.storage.update_test(tid, lupa=lupa["tunnus"], lupa_tila="varattu", lupa_varattu=time.time(),
                                 lupa_testi=1 if lupa.get("testi") else None,
                                 lupa_peruttavissa=time.time() + perumisaika - 120)  # pieni varmuusmarginaali kellolle

    def peru_mittauksen_lupa(self, tid: int, syy: str) -> str:
        """Perii keskeytyneen mittauksen luvan, jos se on vielä mahdollista. Palauttaa tilan selitteen."""
        t = self.storage.test(tid) or {}
        if luvan_tila(t) != "varattu" or t.get("tila") == "valmis":
            return ""          # valmista mittausta ei peruta: raportti rekisteröidään, kun verkkoyhteys palaa
        if not peruttavissa(t):
            return "hyvitettavissa"
        try:
            self.peru(t["lupa"], syy)
        except PalveluVirhe as e:
            if e.status == 409:
                return "hyvitettavissa"
            self.storage.update_test(tid, lupa_tila="peru_odottaa")
            return "peru_odottaa"
        self.storage.update_test(tid, lupa_tila="peruttu")
        return "peruttu"

    def hylkaa_epauskottava(self, tid: int, syyt: list[str]) -> str:
        """Tulos ei läpäissyt järkevyystarkistusta: raporttia ei rekisteröidä, ja krediitit palautetaan. Lupa perutaan,
        jos se on vielä mahdollista; muuten lähetetään hyvityspyyntö automaattisesti."""
        self.storage.update_test(tid, lupa_tila="tarkistus_odottaa")
        self.storage.add_event(tid, time.time(), "Tulosta ei voitu varmistaa: " + " ".join(syyt))
        return self.laheta_hylkays(tid)

    def laheta_hylkays(self, tid: int) -> str:
        from .analysis import uskottavuus  # noqa: PLC0415
        from . import VERSIO  # noqa: PLC0415
        t = self.storage.test(tid) or {}
        syyt = uskottavuus(t.get("tulos")) or ["Tulos ei läpäissyt järkevyystarkistusta."]
        syy = "Tulos ei läpäissyt järkevyystarkistusta: " + " ".join(syyt)
        y = self.yhteenveto(t)
        tiedot = (f"Automaattinen hyvityspyyntö. Auto: {y.get('merkki')} {y.get('malli')}, malli "
                  f"{(self.storage.vehicle(t.get('vehicle_id')) or {}).get('malli_id') or '-'}, mittaus {y.get('tyyppi')}, "
                  f"AKVERI {VERSIO}. {syy}")
        try:
            self.peru(t["lupa"], syy[:300])
        except PalveluVirhe as e:
            if e.status != 409:
                return "tarkistus_odottaa"             # ei yhteyttä: lähetetään myöhemmin uudelleen
            try:
                self.hyvityspyynto(t["lupa"], syy, tiedot)
            except PalveluVirhe as e2:
                if e2.status != 409:
                    return "tarkistus_odottaa"
            self.storage.update_test(tid, lupa_tila="tarkistettava")
            self.storage.add_event(tid, time.time(), "Hyvityspyyntö lähetettiin automaattisesti. Krediitit palautetaan, kun ylläpito on käsitellyt sen.")
            return "tarkistettava"
        self.storage.update_test(tid, lupa_tila="peruttu")
        self.storage.add_event(tid, time.time(), "Testilupa peruttiin, krediitit palautuivat tilille.")
        return "peruttu"

    def yhteenveto(self, t: dict) -> dict:
        r = t.get("tulos") or {}
        y = r.get("yhteenveto") or {}
        v = self.storage.vehicle(t.get("vehicle_id")) or {}
        ajo = r.get("ajoneuvo") or {}
        from .recorder import TYYPIT  # noqa: PLC0415
        aloitettu = t.get("aloitettu") or time.time()
        return {
            "tyyppi": TYYPIT.get(t.get("tyyppi"), t.get("tyyppi") or ""),
            "merkki": v.get("merkki") or ajo.get("merkki") or "", "malli": v.get("malli") or ajo.get("malli") or "",
            "vin": (ajo.get("vin") or v.get("vin") or "").upper(),
            "mittarilukema": t.get("mittarilukema"), "kunto_pct": y.get("kunto_pct"), "kapasiteetti_kwh": y.get("kapasiteetti_kwh"),
            "mitattu": aloitettu, "paattynyt": t.get("paattynyt"),
            "raporttinumero": f"{time.strftime('%Y', time.localtime(aloitettu))}-{int(t['id']):05d}",
            "mittaustyyppi": t.get("tyyppi") or "",
            "suorittaja": (t.get("mittaaja") or "").strip()[:80],
            "anonyymi": anonyymi_tiedot(r),
            "riippumaton": None if t.get("riippumaton") is None else bool(t["riippumaton"]),
        }

    # ---- Tietosuoja: tilin tiedot, raportin poisto palvelusta ja tilin poisto (tietosuojaseloste)
    def tilin_tiedot(self) -> dict:
        return self._kutsu("POST", "/api/v1/tili/tiedot", {})

    def poista_raportti(self, tid: int) -> None:
        t = self.storage.test(tid) or {}
        if not t.get("lupa") or luvan_tila(t) != "rekisteroity":
            raise PalveluVirhe("Mittauksen raporttia ei ole rekisteröity akveri.fi-palveluun.")
        self._kutsu("POST", "/api/v1/testi/poista-tiedot", {"tunnus": t["lupa"]})
        self.storage.update_test(tid, lupa_tila="poistettu")

    def poista_tili(self, raportit: bool) -> dict:
        d = self._kutsu("POST", "/api/v1/tili/poista", {"vahvista": True, "raportit": bool(raportit)})
        # Paikallinen tilitieto pois: seuraava krediittitoiminto luo uuden tilin.
        self.storage.save_settings({"tili": None, "tili_avain": None})
        if raportit:
            for t in self.storage.tests():
                if luvan_tila(t) == "rekisteroity":
                    self.storage.update_test(t["id"], lupa_tila="poistettu")
        return d

    def rekisteroi(self, tid: int, versio: str) -> bool:
        """Rekisteröi valmiin mittauksen raportin. Palauttaa True, kun raportti on rekisteröity (myös aiemmin)."""
        t = self.storage.test(tid) or {}
        if luvan_tila(t) not in ("varattu", "rekisteroity") or t.get("tila") != "valmis" or not t.get("tarkiste"):
            return luvan_tila(t) == "rekisteroity"
        with self.lock:
            if tid in self._rekisteroinnit:
                return False
            self._rekisteroinnit.add(tid)
        try:
            self._kutsu("POST", "/api/v1/testi/raportti", {"tunnus": t["lupa"], "tarkiste": t["tarkiste"],
                                                            "yhteenveto": self.yhteenveto(t), "versio": versio})
            self.storage.update_test(tid, lupa_tila="rekisteroity")
            return True
        finally:
            with self.lock:
                self._rekisteroinnit.discard(tid)

    def odottavat(self) -> list[dict]:
        """Valmiit mittaukset, joiden raportti odottaa rekisteröintiä, ja perumiset, jotka odottavat yhteyttä."""
        return [t for t in self.storage.tests()
                if t.get("lupa") and ((t.get("lupa_tila") == "varattu" and t.get("tila") == "valmis")
                                      or t.get("lupa_tila") in ("peru_odottaa", "tarkistus_odottaa"))]


def suodata_live(snap: dict, sallittu: bool) -> dict:
    """Poistaa kunnon ja kapasiteetin paljastavat arvot, kun mittaukseen ei ole oikeutta."""
    if sallittu:
        return snap
    out = {k: v for k, v in snap.items() if k not in KUNTOKENTAT}
    out["kunto_piilotettu"] = True
    return out


def kasittele_odottavat(krediitit: "Krediitit", versio: str, valmis=None) -> int:
    """Rekisteröi odottavat raportit ja lähettää odottavat perumiset. valmis(tid) kutsutaan rekisteröinnin jälkeen."""
    tehty = 0
    for t in krediitit.odottavat():
        try:
            if t.get("lupa_tila") == "tarkistus_odottaa":
                krediitit.laheta_hylkays(t["id"])
            elif t.get("lupa_tila") == "peru_odottaa":
                try:
                    krediitit.peru(t["lupa"], "Mittaus keskeytettiin (lähetetty, kun yhteys palasi)")
                    krediitit.storage.update_test(t["id"], lupa_tila="peruttu")
                except PalveluVirhe as e:
                    if e.status != 409:
                        raise
                    krediitit.storage.update_test(t["id"], lupa_tila="varattu")
            elif krediitit.rekisteroi(t["id"], versio):
                if valmis:
                    valmis(t["id"])
            tehty += 1
        except PalveluVirhe as e:
            if e.status in (403, 404, 409):
                # Palvelin hylkäsi rekisteröinnin (esim. lupa peruttu tai kuuluu toiselle tilille): ei yritetä uudelleen.
                krediitit.storage.update_test(t["id"], lupa_tila="ei_rekisteroitavissa")
                krediitit.storage.add_event(t["id"], time.time(), f"Raporttia ei voitu rekisteröidä: {e}")
                continue
            break          # ei yhteyttä: yritetään myöhemmin uudelleen
    return tehty
