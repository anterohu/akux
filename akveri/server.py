"""Paikallinen verkkopalvelin: käyttöliittymä selaimessa osoitteessa http://127.0.0.1:8765"""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import json
import mimetypes
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import NIMI, VERSIO, analysis, docs, kielet, maintenance, mittaustiedosto, profiles, report
from . import krediitit as krediittimoduuli
from . import vin as vinmod
from .app import App
from .decoder import KAIKKI_PAKOLLISET
from .sources import list_ports

WEB = Path(__file__).parent / "web"
FONTS = Path(__file__).parent / "data" / "fonts"


def platform_name() -> str:
    import os
    import sys
    if os.environ.get("AKVERI_ALUSTA"):
        return os.environ["AKVERI_ALUSTA"]
    if sys.platform.startswith("win"):
        return "windows"
    return "mac" if sys.platform == "darwin" else "linux"


def _backups(d):
    """Automaattiset varmuuskopiot vanhimmasta uusimpaan (myös vanhalla nimellä tehdyt)."""
    found = {p.resolve(): p for pat in ("AKVERI-varmuuskopio_*.zip",) for p in d.glob(pat)}
    return sorted(found.values(), key=lambda p: p.stat().st_mtime)


# Asetukset, joita vain kehittäjä muuttaa (testitili tai kehitysversio). Asiakkaalla ovat käytössä oletusarvot.
# AKVERI on kaikkien käytössä samanlainen: raporttien ulkoasu ja mittaustapa ovat kaikille samat.
KEHITTAJAN_ASETUKSET = ("lepo_alku_min", "lepo_loppu_min", "kapasiteetti_lahto_soc_max", "lampotila_min", "lampotila_max",
                        "ajo_lepo_min", "ajo_loppu_soc", "pika_ajo_soc", "kuormitus_tapahtumat", "itsepurkaus_lepo_min",
                        "itsepurkaus_tunnit", "raportin_ulkoasu", "vesileima", "kennokuvaaja", "tekninen_liite",
                        "logo_koko", "raportin_alatunniste", "mittaus_tallennus", "mittaus_kansio", "puhelin_kaytossa",
                        "ilmoitukset_kaytossa", "ilmoitus_osoite", "ilmoitus_vaiheet", "ilmoitus_valmis", "ilmoitus_ongelmat")
# Asiakkaan muutettavat asetukset (Asetukset-sivu). Muut avaimet hylätään.
ASIAKKAAN_ASETUKSET = ("kieli", "kaytto", "mittaaja", "yritys_nimi", "yritys_ytunnus", "yritys_osoite", "yritys_puhelin",
                       "yritys_sahkoposti", "yritys_www", "portti", "yhteys_malli")


def rajaa_logo(data: bytes) -> bytes:
    """Logo raporttia varten: tyhjät (läpinäkyvät tai valkoiset) reunat rajataan pois, jotta logo näkyy raportissa
    mahdollisimman suurena, ja kuva pienennetään enintään 1200 pikseliin. Tallennetaan PNG-muodossa."""
    import io  # noqa: PLC0415
    from PIL import Image, ImageChops  # noqa: PLC0415
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ValueError("Kuvaa ei voitu lukea. Käytä PNG- tai JPEG-kuvaa.") from e
    im = im.convert("RGBA")
    # Näkyvä alue: ei läpinäkyvä eikä lähes valkoinen
    tausta = Image.new("RGBA", im.size, (255, 255, 255, 255))
    yhdistetty = Image.alpha_composite(tausta, im).convert("RGB")
    ero = ImageChops.difference(yhdistetty, Image.new("RGB", im.size, (255, 255, 255))).convert("L")
    ala = ero.point(lambda v: 255 if v > 12 else 0).getbbox()
    if not ala:
        raise ValueError("Kuvassa ei ole näkyvää logoa.")
    reuna = max(2, round(min(ala[2] - ala[0], ala[3] - ala[1]) * 0.02))
    ala = (max(0, ala[0] - reuna), max(0, ala[1] - reuna), min(im.width, ala[2] + reuna), min(im.height, ala[3] + reuna))
    im = im.crop(ala)
    im.thumbnail((1200, 1200))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def _riippumaton(v):
    """Mittaajan riippumattomuus: True, False tai None (ei valittu)."""
    if v is None or v == "":
        return None
    return str(v).lower() in ("1", "true", "kyllä", "kylla", "on")


def _num(x):
    if x in (None, ""):
        return None
    try:
        return float(str(x).replace(",", ".").replace(" ", ""))
    except ValueError:
        raise ApiError(f"Virheellinen luku: {x}")


def lan_addresses() -> list[str]:
    """Tietokoneen lähiverkko-osoitteet (myös Tailscale 100.x), joilla puhelin saa yhteyden."""
    import socket
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 80))          # ei lähetä mitään, valitsee vain oletusliitännän
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            ips.add(ip)
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254."))


class Api:
    def __init__(self, app: App):
        self.app = app
        self.network = False
        self.port = 8765
        self.key = None
        self.last_seen = time.time()
        self.httpd = None
        self.exit_action = None      # "sulje" tai "uudelleen"

    def phone_info(self):
        if not self.network:
            return {"kaytossa": False, "osoitteet": []}
        return {"kaytossa": True, "avain": self.key,
                "osoitteet": [f"http://{ip}:{self.port}/?avain={self.key}" for ip in lan_addresses()]}

    # -- tila -----------------------------------------------------------
    def sulje(self, q, body):
        if self.app.recorder.active and not body.get("vahvistettu"):
            raise ApiError("Mittaus on käynnissä. Ohjelman sulkeminen keskeyttää sen.", 409)
        self._stop("sulje")
        return {"ok": True}

    def uudelleen(self, q, body):
        if self.app.recorder.active:
            raise ApiError("Mittaus on käynnissä. Käynnistä ohjelma uudelleen mittauksen jälkeen.", 409)
        self._stop("uudelleen")
        return {"ok": True}

    def _stop(self, action):
        self.exit_action = action
        try:
            # Sovellusikkuna tunnistaa tästä, että ohjelma käynnistyy uudelleen eikä sulkeudu
            marker = self.app.storage.dir / ".uudelleenkaynnistys"
            if action == "uudelleen":
                marker.write_text(str(time.time()))
            elif marker.exists():
                marker.unlink()
        except OSError:
            pass
        if self.httpd:
            threading.Timer(0.4, self.httpd.shutdown).start()

    # -- ylläpito -------------------------------------------------------
    def tarkistus(self, q, body):
        return maintenance.selftest(self.app, full=q.get("laaja", ["1"])[0] != "0")

    def loki(self, q, body):
        return {"loki": maintenance.read_log(self.app.storage)}

    def varmuuskopiot(self, q, body):
        d = self.app.storage.dir / "varmuuskopiot"
        items = []
        if d.exists():
            for p in sorted(d.glob("*.zip"), reverse=True):
                items.append({"nimi": p.name, "koko": p.stat().st_size, "aika": p.stat().st_mtime})
        return {"varmuuskopiot": items, "kansio": str(d)}

    def tarkista_palautus(self, q, body):
        try:
            return maintenance.inspect_backup(body.get("_raw") or b"")
        except ValueError as e:
            raise ApiError(str(e))

    def palauta(self, q, body):
        if self.app.recorder.active:
            raise ApiError("Mittaus on käynnissä. Palauta varmuuskopio mittauksen jälkeen.")
        self.app.disconnect()
        try:
            meta = maintenance.restore(self.app.storage, body.get("_raw") or b"")
        except ValueError as e:
            raise ApiError(str(e))
        self._stop("uudelleen")
        return meta

    def testi_ilmoitus(self, q, body):
        if not self.app.krediitit.esittely_sallittu():
            raise ApiError("Puhelinilmoitukset eivät ole käytössä.", 403)
        if body.get("osoite") is not None:
            self.app.storage.save_settings({"ilmoitus_osoite": body["osoite"].strip()})
        ok, msg = self.app.notifier.send("valmis", "AKVERI – testi-ilmoitus",
                                         "Ilmoitukset toimivat. Saat tällaisen ilmoituksen, kun mittaus etenee.",
                                         force=True, wait=True)
        if not ok:
            raise ApiError(f"Ilmoituksen lähetys epäonnistui: {msg}")
        return {"ok": True}

    def ohjeet(self, q, body):
        return {"osiot": docs.as_html(platform_name())}

    def tietoja(self, q, body):
        import platform
        return {"nimi": NIMI, "versio": VERSIO, "datakansio": str(self.app.storage.dir), "alusta": platform_name(),
                "esittely": self.app.krediitit.esittely_sallittu(),
                "python": platform.python_version(), "jarjestelma": f"{platform.system()} {platform.release()}"}

    _esittely_tarkistettu = 0.0

    def _sulje_esittely_tarvittaessa(self):
        """Kun testitili poistetaan, esittelytila suljetaan: lupa tarkistetaan palvelusta minuutin välein."""
        a = self.app
        if not (a.source and a.source.simulated):
            return
        if time.monotonic() - Api._esittely_tarkistettu > 60:
            Api._esittely_tarkistettu = time.monotonic()
            threading.Thread(target=lambda: a.krediitit.esittely_sallittu(tarkista=True), daemon=True).start()
        if not a.krediitit.esittely_sallittu():
            if a.recorder.active:
                a.recorder.cancel()
            a.disconnect()

    def tila(self, q, body):
        self.last_seen = time.time()
        a = self.app
        self._sulje_esittely_tarvittaessa()
        src = a.source
        snap = a.decoder.snapshot()
        known = None
        v = None
        if snap.get("vin"):
            v = a.storage.find_vehicle_by_vin(snap["vin"])
            known = {"id": v["id"], "nimi": v["nimi"]} if v else None
        snap["viite_kwh"], snap["viite_lahde"] = self._live_reference(snap, v)
        return {
            "nimi": NIMI, "versio": VERSIO, "alusta": platform_name(),
            "yhteys": {
                "kaynnissa": bool(src and src.running), "lahde": src.name if src else None,
                "tila": src.status if src else "Ei yhteyttä", "virhe": src.error if src else None,
                "tiedot": src.info if src else {}, "simuloitu": bool(src and src.simulated),
                "demo": {"tila": src.mode, "nopeutus": src.accel} if (src and src.simulated) else None,
            },
            # Akun kunto ja kapasiteetti näkyvät vain luvallisessa mittauksessa (ks. krediitit.py).
            "live": krediittimoduuli.suodata_live(snap, a.live_kunto_sallittu()),
            "auto_tunnettu": known,
            "mittaus": a.recorder.progress(),
            "vaylatesti": self._bus_verdict(),
        }

    def _live_reference(self, snap, vehicle):
        """Alkuperäinen kapasiteetti reaaliaikaisen kunnon laskemiseen. Sama järjestys ja samat tarkistukset
        kuin raportissa: akunhallinta (jos arvo sopii akkuun), aiempi mittaus tai ilmoitettu arvo, mallitaulukko."""
        from .analysis import reference_capacity, bol_sopii
        key = (snap.get("vin"), (vehicle or {}).get("malli_id"), snap.get("brick_count"), snap.get("platform"))
        cache = getattr(self, "_model_cache", None)
        if cache and cache[0] == key:
            model = cache[1]
        else:
            model = profiles.get((vehicle or {}).get("malli_id")) or profiles.get(snap.get("malli_id"))
            if not model and snap.get("vin"):
                info = vinmod.decode(snap["vin"])
                if info.get("kelvollinen"):
                    model, _ = profiles.identify(info, brick_count=snap.get("brick_count"),
                                                 platform=snap.get("platform"), nfp_kwh=snap.get("nfp_kwh"))
            self._model_cache = (key, model)
        bol = snap.get("bol_kwh")
        if bol and bol_sopii(bol, model, snap.get("nfp_kwh"), snap.get("brick_count")):
            if snap.get("platform") not in (None, "m3", "sx"):
                return bol, "mallin alkuperäinen kapasiteetti"
            return bol, "Teslan akunhallinta"
        kwh, src = reference_capacity(vehicle or {}, None, model, snap.get("nfp_kwh"), snap.get("brick_count"))
        label = ("mallin alkuperäinen kapasiteetti (likiarvo)" if src.startswith("Mallitaulukko") else
                 "ilmoitettu" if src.startswith("Käyttäjän") else "akunhallinta, aiempi mittaus")
        return kwh, (label if kwh else None)

    def _bus_verdict(self):
        d = self.app.decoder
        if not d.total_frames:
            return None
        rep = d.bus_report(self.app.source.now() if self.app.source else None)
        missing = [r for r in rep if r["pakollinen"] and not r["nakyy"]]
        return {"viestit": rep, "puuttuvat": [r["kuvaus"] for r in missing], "kunnossa": not missing,
                "kehyksia": d.total_frames}

    # -- väylän kartoitus ------------------------------------------------
    def aloita_kartoitus(self, q, body):
        src = self.app.source
        if not src or not src.running:
            raise ApiError("Yhdistä ensin sovittimeen.")
        if self.app.recorder.active:
            raise ApiError("Kartoitusta ei voi tehdä mittauksen aikana.")
        secs = 10.0
        self.scan = {"perus": self.app.decoder.counts(), "alku": src.now(), "kesto": secs,
                     "seinakello": time.time()}
        src.request_scan(secs)
        return {"ok": True, "kesto_s": secs}

    def kartoitus(self, q, body):
        sc = getattr(self, "scan", None)
        src = self.app.source
        if not sc or not src:
            return {"tila": "ei"}
        from .decoder import KAIKKI_PAKOLLISET, kuvaus
        running = src.scanning
        now = src.now()
        dur = max(0.5, (min(now, sc["alku"] + sc["kesto"] * (src.accel if src.simulated else 1))) - sc["alku"])
        cur = self.app.decoder.counts()
        rows = []
        for cid, n in sorted(cur.items()):
            d = n - sc["perus"].get(cid, 0)
            if d > 0:
                rows.append({"tunniste": f"0x{cid:03X}", "kpl": d, "taajuus_hz": round(d / dur, 1),
                             "kuvaus": kuvaus(cid, self.app.decoder.platform), "akku": cid in KAIKKI_PAKOLLISET})
        ids = {int(r["tunniste"], 16) for r in rows}
        if any(cid in ids for cid in KAIKKI_PAKOLLISET):
            verdict = ("ok", "Liitäntä välittää akun tiedot. Mittaukset voidaan tehdä tämän liitännän kautta.")
        elif not rows:
            verdict = ("ei", "Väylällä ei liikkunut viestejä. Herätä auto avaamalla ovi tai käynnistämällä ilmastointi ja kartoita uudelleen.")
        else:
            verdict = ("rajattu", "Liitäntä välittää vain muutaman tiedon, kuten nopeuden ja virtatilan, mutta ei akun tietoja. "
                       "Kytke sovitin auton diagnostiikkaliittimeen mallille sopivalla välikaapelilla. "
                       + self._guide_text())
        return {"tila": "kaynnissa" if running else "valmis", "jaljella_s": max(0, round(sc["kesto"] - (time.time() - sc["seinakello"]))),
                "viestit": rows, "lajeja": len(rows), "arvio": verdict[0], "teksti": verdict[1]}

    def kennot(self, q, body):
        kennot = self.app.decoder.bricks_list()
        if not self.app.live_kunto_sallittu():
            # Yksittäiset kennojännitteet näkyvät mittauksen aikana ja raportissa; ilman mittausta vain luettujen määrä.
            return {"kennot": [], "piilotettu": True, "luettu": sum(1 for v in kennot if v)}
        return {"kennot": kennot}

    def portit(self, q, body):
        from . import sources
        try:
            if not sources.SERIAL_FACTORY:
                import serial  # noqa: F401
            ok = True
        except ImportError:
            ok = False
        return {"portit": list_ports(), "pyserial": ok, "windows": platform_name() == "windows",
                "alusta": platform_name()}

    def yhdista(self, q, body):
        kind = body.get("tyyppi", "obdlink")
        if kind == "demo":
            if not self.app.krediitit.esittely_sallittu(tarkista=True):
                raise ApiError("Esittelytila on käytössä vain testitileillä.", 403)
            self.app.connect("demo", soc=(_num(body.get("soc")) or 12) / 100, accel=_num(body.get("nopeutus")) or 60,
                             auto=body.get("auto"))
        else:
            port = body.get("portti") or self.app.settings.get("portti")
            baud = int(body.get("baud") or 0) or None
            from . import sources
            if not sources.SERIAL_FACTORY:
                try:
                    import serial  # noqa: F401
                except ImportError:
                    raise ApiError("Sovittimen yhteysosa puuttuu ohjelmasta. Asenna ohjelma uudelleen.")
            malli = body.get("malli_id") or None
            if malli == "tesla":       # Tesla: malli tunnistetaan valmistenumerosta
                malli = None
            self.app.connect("obdlink", port=port, baud=baud, malli_id=malli)
            self.app.storage.save_settings({"portti": port, "yhteys_malli": malli or "tesla"})
        return {"ok": True}

    def katkaise(self, q, body):
        self.app.disconnect()
        return {"ok": True}

    def demo(self, q, body):
        src = self.app.source
        if not (src and src.simulated):
            raise ApiError("Esittelytila ei ole käytössä.")
        if "tila" in body:
            src.set_mode(body["tila"], _num(body.get("teho")))
        if "nopeutus" in body:
            src.set_accel(_num(body["nopeutus"]))
        if "soc" in body:
            src.set_soc(_num(body["soc"]) / 100)
        return {"ok": True}

    # -- ajoneuvot ------------------------------------------------------
    def ajoneuvot(self, q, body):
        out = []
        for v in self.app.storage.vehicles():
            v["malli"] = (profiles.get(v["malli_id"]) or {}).get("nimi")
            out.append(v)
        return {"ajoneuvot": out}

    # Saman konsernin merkit tulkitaan yhteensopiviksi (esim. MEB-alustan autot, Hyundai ja Kia).
    _MERKKIRYHMAT = ({"volkswagen", "škoda", "skoda", "audi", "cupra", "seat"}, {"hyundai", "kia"})

    @classmethod
    def _merkkiero(cls, vin: str | None, malli_id: str | None) -> tuple[str, str] | None:
        """(valmistenumeron merkki, valitun mallin nimi), jos ne eivät sovi yhteen; muuten None."""
        if not vin or not malli_id:
            return None
        m = profiles.get(malli_id)
        info = vinmod.decode(vin)
        merkki = (info.get("merkki") or (info.get("valmistaja") or "").split(",")[0]).strip()
        vm, mm = merkki.lower(), ((m or {}).get("merkki") or "").strip().lower()
        if not vm or not mm or vm == mm or any(vm in r and mm in r for r in cls._MERKKIRYHMAT):
            return None
        return merkki, m["nimi"]

    @classmethod
    def _merkki_ristiriita(cls, vin: str | None, malli_id: str | None) -> str | None:
        """Virheilmoitus, jos auton tietoihin syötetty valmistenumero ei sovi valittuun malliin."""
        ero = cls._merkkiero(vin, malli_id)
        if not ero:
            return None
        return f"Valmistenumero {vin} on {ero[0]}-auton, mutta malliksi on valittu {ero[1]}. Tarkista valmistenumero ja malli."

    def _vehicle_payload(self, body):
        data = {k: body.get(k) for k in ("vin", "nimi", "rekisteri", "omistaja", "malli_id", "vari", "lisatiedot", "kayttoonotto")
                if k in body}
        if "vin" in data and data["vin"]:
            data["vin"] = vinmod.normalize(data["vin"])
            info = vinmod.decode(data["vin"])
            if not info["kelvollinen"]:
                raise ApiError(" ".join(info["virheet"]))
        if "vuosimalli" in body:
            data["vuosimalli"] = int(body["vuosimalli"]) if body["vuosimalli"] else None
        dec = self.app.decoder
        if not data.get("malli_id") and data.get("vin") and data["vin"] == dec.state.vin and dec.hk.get("malli_id"):
            data["malli_id"] = dec.hk["malli_id"]     # kyselyihin vastaava auto: malli valittiin yhdistettäessä
        if not data.get("malli_id") and data.get("vin"):
            _vi = vinmod.decode(data["vin"])
            m, _ = profiles.identify(_vi, platform=_vi.get("alusta_arvio"))
            data["malli_id"] = m["id"] if m else None
            if not data.get("vuosimalli"):
                data["vuosimalli"] = vinmod.decode(data["vin"]).get("vuosimalli")
        virhe = self._merkki_ristiriita(data.get("vin"), data.get("malli_id"))
        if virhe:
            raise ApiError(virhe)
        return data

    def lisaa_ajoneuvo(self, q, body):
        data = self._vehicle_payload(body)
        if data.get("vin") and self.app.storage.find_vehicle_by_vin(data["vin"]):
            raise ApiError("Ajoneuvo tällä valmistenumerolla on jo tallennettu.")
        if not data.get("nimi"):
            m = profiles.get(data.get("malli_id"))
            data["nimi"] = (body.get("rekisteri") or "") or (m["nimi"] if m else (vinmod.decode(data["vin"]).get("merkki") if data.get("vin") else None) or "Auto")
        opitut = {}
        if body.get("viite_kayttaja"):
            opitut["viite_kayttaja"] = _num(body["viite_kayttaja"])
        data["opitut"] = opitut
        vid = self.app.storage.add_vehicle(data)
        return {"id": vid}

    def ajoneuvo(self, q, body, vid):
        v = self.app.storage.vehicle(vid)
        if not v:
            raise ApiError("Ajoneuvoa ei löydy.", 404)
        v["malli"] = profiles.get(v["malli_id"])
        v["vin_tiedot"] = vinmod.decode(v["vin"]) if v.get("vin") else None
        vi = v["vin_tiedot"] or {}
        v["liitanta"] = profiles.connection_guide(vi.get("malli_koodi") or ((v["malli"] or {}).get("malli_koodi") or "")[:1],
                                                  vi.get("vuosimalli") or v.get("vuosimalli"),
                                                  (v.get("opitut") or {}).get("alusta") or (v["malli"] or {}).get("alusta"))
        v["mittaukset"] = [self._test_row(t) for t in self.app.storage.tests(vid)]
        return v

    def muokkaa_ajoneuvo(self, q, body, vid):
        data = self._vehicle_payload(body)
        self.app.storage.update_vehicle(vid, data)
        if "viite_kayttaja" in body:
            self.app.storage.learn(vid, {"viite_kayttaja": _num(body["viite_kayttaja"])})
        return {"ok": True}

    def poista_ajoneuvo(self, q, body, vid):
        if self.app.recorder.active and self.app.recorder.vehicle_id == vid:
            raise ApiError("Ajoneuvolla on käynnissä oleva mittaus.")
        self.app.storage.delete_vehicle(vid)
        return {"ok": True}

    def vin(self, q, body):
        info = vinmod.decode(body.get("vin", ""))
        model, reasons = profiles.identify(info, platform=info.get("alusta_arvio")) if info["kelvollinen"] else (None, [])
        from . import polled
        _pb = polled.for_brand(info.get("merkki"))
        plat = (model or {}).get("alusta") or (_pb.PLATFORM if _pb else None)
        guide = profiles.connection_guide(info.get("malli_koodi"), info.get("vuosimalli"), plat) if info["kelvollinen"] else None
        return {"tiedot": info, "malli": model, "perusteet": reasons, "liitanta": guide}

    def _guide_text(self) -> str:
        """Liitäntäohje valitun tai viimeksi kytketyn auton mukaan, muuten Model 3 / Y -ohje."""
        v = None
        vin_txt = self.app.decoder.state.vin
        if vin_txt:
            v = self.app.storage.find_vehicle_by_vin(vin_txt)
        if not v:
            vs = self.app.storage.vehicles()
            v = vs[0] if len(vs) == 1 else None
        info = vinmod.decode(v["vin"]) if v and v.get("vin") else {}
        m = profiles.get((v or {}).get("malli_id"))
        g = profiles.connection_guide(info.get("malli_koodi") or "3", info.get("vuosimalli") or (v or {}).get("vuosimalli"),
                                      (m or {}).get("alusta"))
        return g["ohje"]

    def mallit(self, q, body):
        return {"mallit": profiles.models()}

    # -- mittaukset -----------------------------------------------------
    def _test_row(self, t):
        r = t.get("tulos") or {}
        y = r.get("yhteenveto") or {}
        return {"id": t["id"], "ajoneuvo_id": t["vehicle_id"], "tyyppi": t["tyyppi"], "tila": t["tila"],
                "aloitettu": t["aloitettu"], "paattynyt": t["paattynyt"], "mittarilukema": t["mittarilukema"],
                "kunto_pct": y.get("kunto_pct"), "kunto_luokka": y.get("kunto_luokka"),
                "kapasiteetti_kwh": y.get("kapasiteetti_kwh"), "epavarmuus_kwh": y.get("epavarmuus_kwh"),
                "ero_mv": (r.get("kennot") or {}).get("ero_mv"), "virhe": r.get("virhe"),
                "osat": (r.get("purku") or {}).get("osat"), **self._lupa(t)}

    @staticmethod
    def _lupa(t):
        tila = krediittimoduuli.luvan_tila(t)
        return {"lupa": {"tunnus": krediittimoduuli.muotoile_tunnus(t.get("lupa")), "tila": tila, "testi": bool(t.get("lupa_testi")),
                         "peruttavissa": krediittimoduuli.peruttavissa(t),
                         "hyvitettavissa": tila == "varattu" and t.get("tila") in ("keskeytetty", "keskeytynyt")
                         and not krediittimoduuli.peruttavissa(t)}}

    def aloita(self, q, body):
        vid = int(body.get("ajoneuvo_id") or 0)
        veh = self.app.storage.vehicle(vid)
        if not veh:
            raise ApiError("Valitse auto.")
        bus_vin = self.app.decoder.state.vin
        if bus_vin and veh.get("vin") and bus_vin != veh["vin"]:
            other = self.app.storage.find_vehicle_by_vin(bus_vin)
            hint = f" Autosta luettu numero kuuluu autoon {other['nimi']}." if other else \
                " Lisää tämä auto ensin Autot-sivulla."
            raise ApiError(f"Kytketyn auton valmistenumero {bus_vin} ei vastaa valittua autoa ({veh['vin']})." + hint)
        if veh.get("vin"):
            virhe = self._merkki_ristiriita(veh["vin"], veh.get("malli_id"))
            if virhe:
                raise ApiError(virhe + " Korjaa auton tiedot Autot-sivulla.")
        elif bus_vin:
            ero = self._merkkiero(bus_vin, veh.get("malli_id"))
            if ero:
                raise ApiError(f"Kytketty auto on {ero[0]}, mutta valittu auto on {ero[1]}. Valmistenumerot eivät täsmää. "
                               "Valitse oikea auto tai kytke sovitin valittuun autoon.")
        tyyppi = body.get("tyyppi")
        from .recorder import TYYPIT
        if tyyppi not in TYYPIT:
            raise ApiError("Valitse mittauksen tyyppi.")
        verdict = self._bus_verdict()
        if not verdict or not verdict["kunnossa"]:
            missing = ", ".join(verdict["puuttuvat"]) if verdict else "kaikki"
            raise ApiError(f"Akun tietoja ei vielä vastaanoteta ({missing.lower()}). Tarkista, että auto on "
                           "hereillä ja sovitin on kytketty.")
        mittaaja = str(body.get("mittaaja") or self.app.settings.get("mittaaja", "") or "").strip()[:80]
        if not mittaaja and not (self.app.source and self.app.source.simulated):
            raise ApiError("Kirjoita mittauksen suorittaja (nimi tai yritys). Se näkyy raportissa ja tarkistussivulla.")
        try:
            tid = self.app.start_test(vehicle_id=vid, tyyppi=tyyppi, mittarilukema=_num(body.get("mittarilukema")),
                                      mittaaja=mittaaja,
                                      lisatiedot=body.get("lisatiedot", ""),
                                      riippumaton=_riippumaton(body.get("riippumaton")))
            if body.get("riippumaton") is not None:
                self.app.storage.save_settings({"riippumaton_viimeksi": _riippumaton(body.get("riippumaton"))})
        except RuntimeError as e:
            raise ApiError(str(e))
        return {"id": tid}

    def ohita(self, q, body):
        self.app.recorder.skip_phase()
        return {"ok": True}

    def keskeyta(self, q, body):
        tid = self.app.recorder.test_id
        self.app.recorder.cancel()
        tila = self.app.peru_lupa(tid, "Mittaus keskeytettiin") if tid else ""
        return {"ok": True, "lupa": tila}

    def tauko(self, q, body):
        r = self.app.recorder
        if not r.can_pause():
            raise ApiError("Tätä mittausta ei voi jatkaa myöhemmin tässä vaiheessa.")
        r.pause("Mittaus jätettiin jatkettavaksi myöhemmin")
        return {"ok": True}

    def jatka(self, q, body, tid):
        t = self.app.storage.test(tid)
        if not t or t["tila"] != "kesken":
            raise ApiError("Mittausta ei voi jatkaa.")
        if self.app.recorder.active:
            raise ApiError("Toinen mittaus on käynnissä.")
        verdict = self._bus_verdict()
        if not verdict or not verdict["kunnossa"]:
            raise ApiError("Akun tietoja ei vielä vastaanoteta. Kytke sovitin ja herätä auto ennen jatkamista.")
        try:
            self.app.resume_test(tid)
        except (RuntimeError, ValueError) as e:
            raise ApiError(str(e))
        return {"id": tid}

    def hylkaa(self, q, body, tid):
        t = self.app.storage.test(tid)
        if not t or t["tila"] != "kesken":
            raise ApiError("Mittausta ei löydy.")
        self.app.recorder.discard(tid)
        return {"ok": True, "lupa": self.app.peru_lupa(tid, "Kesken jäänyt mittaus hylättiin")}

    # -- krediitit ------------------------------------------------------
    def krediitit(self, q, body):
        try:
            d = self.app.krediitit.tilanne()
        except krediittimoduuli.PalveluVirhe as e:
            raise ApiError(str(e), 503)
        return {**d, "alusta": platform_name(), "tili_naytto": d.get("tili")}

    # ---- Tietosuoja (tietosuojaseloste): raportin poisto palvelusta ja tilin poisto. Tilin tiedot ladataan
    # tiedostona osoitteesta /api/tietosuoja/akveri-tietoni.zip (ks. _files).
    def poista_raportti_palvelusta(self, q, body, tid):
        try:
            self.app.krediitit.poista_raportti(tid)
        except krediittimoduuli.PalveluVirhe as e:
            raise ApiError(str(e), 409 if e.args and "rekisteröity" in str(e) else 503)
        self.app.storage.add_event(tid, time.time(), "Raportin tiedot poistettiin akveri.fi-palvelusta. Raporttia ei voi enää tarkistaa.")
        return {"ok": True}

    def poista_tili(self, q, body):
        if body.get("vahvista") is not True:
            raise ApiError("Vahvista tilin poisto.")
        try:
            d = self.app.krediitit.poista_tili(bool(body.get("raportit")))
        except krediittimoduuli.PalveluVirhe as e:
            raise ApiError(str(e), 503)
        return {"ok": True, "raportteja": d.get("raportteja", 0)}

    def krediitit_osto(self, q, body):
        tuote = str(body.get("tuote") or "")
        token = str(body.get("ostotunnus") or "")
        if not tuote or not token:
            raise ApiError("Oston tiedot puuttuvat.")
        try:
            return self.app.krediitit.osto(tuote, token)
        except krediittimoduuli.PalveluVirhe as e:
            raise ApiError(str(e), 409 if e.status == 409 else 400)

    def hyvityspyynto(self, q, body, tid):
        t = self.app.storage.test(tid)
        if not t or krediittimoduuli.luvan_tila(t) != "varattu" or t.get("tila") not in ("keskeytetty", "keskeytynyt"):
            raise ApiError("Hyvitystä voi pyytää vain keskeytyneestä mittauksesta.")
        syy = str(body.get("syy") or "").strip()
        if len(syy) < 10:
            raise ApiError("Kerro lyhyesti, mitä tapahtui (vähintään 10 merkkiä).")
        tapahtumat = "\n".join(f"{time.strftime('%d.%m. %H.%M', time.localtime(e['t']))} {e['teksti']}"
                               for e in (self.app.storage.events(tid) or [])[-25:])
        try:
            self.app.krediitit.hyvityspyynto(t["lupa"], syy, f"AKVERI {VERSIO} ({platform_name()})\n{tapahtumat}")
        except krediittimoduuli.PalveluVirhe as e:
            raise ApiError(str(e))
        self.app.storage.add_event(tid, time.time(), "Hyvityspyyntö lähetetty: " + syy[:200])
        return {"ok": True}

    def mittaukset(self, q, body):
        vid = int(q.get("ajoneuvo", ["0"])[0] or 0) or None
        rows = [self._test_row(t) for t in self.app.storage.tests(vid)]
        names = {v["id"]: v for v in self.app.storage.vehicles()}
        for r in rows:
            v = names.get(r["ajoneuvo_id"]) or {}
            r["ajoneuvo"] = v.get("nimi")
            r["rekisteri"] = v.get("rekisteri")
            r["vin"] = v.get("vin")
        return {"mittaukset": rows}

    def mittaus(self, q, body, tid):
        t = self.app.storage.test(tid)
        if not t:
            raise ApiError("Mittausta ei löydy.", 404)
        samples = self.app.storage.samples(tid)
        step = max(1, len(samples) // 600)
        t["naytteet"] = samples[::step]
        t["tapahtumat"] = self.app.storage.events(tid)
        t["ajoneuvo"] = self.app.storage.vehicle(t["vehicle_id"])
        if not krediittimoduuli.tulos_naytettavissa(t):
            t["tulos_odottaa"] = krediittimoduuli.tulos_odottaa(t)
            t["tulos"] = None
        t.update(self._lupa(t))
        return t

    def avaa_mittaus(self, q, body):
        try:
            r = mittaustiedosto.import_file(self.app.storage, body.get("_raw") or b"")
        except (ValueError, KeyError) as e:
            raise ApiError(str(e) if isinstance(e, ValueError) else
                           "Tiedosto ei ole AKVERIn mittaustiedosto tai se on vaurioitunut.")
        # Vanhemmalla versiolla laskettu tulos lasketaan avattaessa uudelleen tämän version laskennalla
        # samasta tallennetusta mittausdatasta. Aiemman laskennan versio ja kunto jäävät raporttiin.
        t = self.app.storage.test(r["id"]) or {}
        if t.get("tila") == "valmis" and (t.get("tulos") or {}).get("versio") != VERSIO:
            try:
                analysis.reanalyze(self.app.storage, r["id"])
                r["laskettu_uudelleen"] = VERSIO
            except Exception:
                pass
        return r

    def tallenna_kansioon(self, q, body, tid):
        try:
            paths = mittaustiedosto.save_to_folder(self.app.storage, tid)
        except (ValueError, OSError) as e:
            raise ApiError(f"Tallennus epäonnistui: {e}")
        return {"tiedostot": [str(p) for p in paths]}

    def poista_mittaus(self, q, body, tid):
        if self.app.recorder.test_id == tid:
            raise ApiError("Mittaus on käynnissä. Keskeytä se ensin.")
        self.app.storage.delete_test(tid)
        return {"ok": True}

    def aseta_riippumattomuus(self, q, body, tid):
        # Aiempien versioiden mittauksille. Rekisteröidyn raportin tietoja ei voi muuttaa: raportti ja akveri.fi:n
        # tarkistussivu pysyvät aina yhtäpitävinä.
        t = self.app.storage.test(tid)
        if not t:
            raise ApiError("Mittausta ei löydy.", 404)
        from . import krediitit  # noqa: PLC0415
        if krediitit.luvan_tila(t) == "rekisteroity":
            raise ApiError("Raportti on rekisteröity akveri.fi-palveluun, eikä sen tietoja voi enää muuttaa.", 409)
        self.app.storage.update_test(tid, riippumaton=_riippumaton(body.get("riippumaton")))
        return {"ok": True}

    def laske_uudelleen(self, q, body, tid):
        rec = self.app.recorder
        if rec.active and rec.test_id == tid:
            raise ApiError("Mittaus on käynnissä.", 409)
        try:
            res = analysis.reanalyze(self.app.storage, tid)
        except ValueError as e:
            raise ApiError(str(e)) from e
        y = res.get("yhteenveto") or {}
        if krediittimoduuli.luvan_tila(self.app.storage.test(tid) or {}) == "rekisteroity":
            threading.Thread(target=self._paivita_rekisterointi, args=(tid,), daemon=True).start()
        return {"ok": True, "versio": VERSIO, "kunto_pct": y.get("kunto_pct"),
                "aiempi": res.get("aiempi_laskenta")}

    def _paivita_rekisterointi(self, tid):
        """Uudelleen lasketun mittauksen tulos päivitetään tarkistussivulle (sama raakadata, sama lupa)."""
        try:
            self.app.krediitit.rekisteroi(tid, VERSIO)
            self.app.storage.add_event(tid, time.time(), f"Uudelleen laskettu tulos päivitetty tarkistussivulle (versio {VERSIO}).")
        except krediittimoduuli.PalveluVirhe:
            pass

    def jaa_osiin(self, q, body, tid):
        try:
            return {"ok": True, "osat": analysis.split_full_test(self.app.storage, tid)}
        except ValueError as e:
            raise ApiError(str(e)) from e

    def tarkista(self, q, body, tid):
        t = self.app.storage.test(tid)
        if not t or not t.get("raakadata"):
            raise ApiError("Raakadataa ei löydy.", 404)
        path = Path(t["raakadata"])
        if not path.exists():
            return {"ok": False, "viesti": "Raakadatatiedostoa ei löydy."}
        h = hashlib.sha256()
        n = 0
        with gzip.open(path, "rt", encoding="ascii") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                h.update(line.encode("ascii"))
                n += 1
        ok = h.hexdigest() == t.get("tarkiste")
        return {"ok": ok, "rivit": n, "tarkiste": h.hexdigest(), "tallennettu": t.get("tarkiste"),
                "viesti": "Raakadata on muuttumaton." if ok else "Raakadatan tarkiste ei täsmää."}

    # -- kieli -----------------------------------------------------------
    # Kieli valitaan ensimmäisellä käynnistyksellä ja sitä voi vaihtaa asetuksista. Sama kieli koskee raportteja.
    def kieli(self, q, body):
        k = self.app.settings.get("kieli")
        return {"kieli": k if k in kielet.KIELET else None, "kielet": kielet.KIELET}

    def aseta_kieli(self, q, body):
        k = str(body.get("kieli") or "")
        if k not in kielet.KIELET:
            raise ApiError("Tuntematon kieli.")
        self.app.storage.save_settings({"kieli": k})
        kielet.aseta(k)
        return {"ok": True, "kieli": k}

    def kielen_sanasto(self, q, body):
        k = (q.get("kieli") or [""])[0]
        if k not in kielet.KIELET:
            raise ApiError("Tuntematon kieli.")
        return kielet.sanasto(k)

    # -- asetukset ------------------------------------------------------
    def asetukset(self, q, body):
        s = self.app.settings
        s["datakansio"] = str(self.app.storage.dir)
        s["puhelin"] = self.phone_info()
        s["mittaus_kansio_oletus"] = "Lataukset/AKVERI" if platform_name() == "android" else str(mittaustiedosto.default_folder())
        s.pop("puhelin_avain", None)
        for k in ("tili_avain", "palvelu_osoite"):
            s.pop(k, None)
        return s

    def tallenna_asetukset(self, q, body):  # noqa: C901
        for k in ("puhelin_avain", "tili", "tili_avain", "palvelu_osoite", "esittely"):
            body.pop(k, None)
        if "kaytto" in body and body["kaytto"] not in ("henkilo", "yritys"):
            body.pop("kaytto")
        # Mittaustavan raja-arvot ja raportin ulkoasu ovat kehittäjän päätettäviä: asiakas ei voi muuttaa niitä.
        # Testitileillä (akveri.fi:n hallinta) ja kehitysversiossa ne näkyvät Asetuksissa kohdassa Kehittäjän asetukset.
        if not self.app.krediitit.esittely_sallittu():
            for k in [k for k in body if k not in ASIAKKAAN_ASETUKSET]:
                body.pop(k, None)
        for k in ("mittaaja", "yritys_nimi", "yritys_ytunnus", "yritys_osoite", "yritys_puhelin", "yritys_sahkoposti", "yritys_www"):
            if k in body:
                body[k] = str(body[k] or "").strip()[:120]
        if "kieli" in body:
            if body["kieli"] not in kielet.KIELET:
                body.pop("kieli")
            else:
                kielet.aseta(body["kieli"])
        # Mittausten raja-arvot: virheellinen tai tyhjä arvo jätetään pois, muut rajataan järkevälle välille
        limits = {"lepo_alku_min": (0, 240), "lepo_loppu_min": (0, 240), "kapasiteetti_lahto_soc_max": (5, 60),
                  "lampotila_min": (-20, 40), "lampotila_max": (0, 60), "ajo_lepo_min": (0, 240),
                  "ajo_loppu_soc": (3, 50), "pika_ajo_soc": (10, 60), "kuormitus_tapahtumat": (3, 30),
                  "itsepurkaus_lepo_min": (5, 240), "itsepurkaus_tunnit": (2, 72)}
        for k, (lo, hi) in limits.items():
            if k in body:
                v = _num(body[k])
                if v is None:
                    body.pop(k)
                else:
                    body[k] = max(lo, min(hi, int(round(v)) if k != "lampotila_min" and k != "lampotila_max" else v))
        if "tekninen_liite" in body:
            body["tekninen_liite"] = str(body["tekninen_liite"]).lower() not in ("0", "false", "ei", "")
        return self.app.storage.save_settings(body)

    def esimerkit(self, q, body):
        """Lisää ohjelmaan esimerkkiautot valmiine mittauksineen tai poistaa ne."""
        st = self.app.storage
        ex = [v for v in st.vehicles() if (v.get("opitut") or {}).get("esimerkki")]
        if body.get("poista"):
            if self.app.recorder.active and self.app.recorder.vehicle_id in {v["id"] for v in ex}:
                raise ApiError("Esimerkkiautolla on käynnissä oleva mittaus.")
            for v in ex:
                st.delete_vehicle(v["id"])
            return {"ok": True, "poistettu": len(ex)}
        if ex:
            return {"ok": True, "lisatty": 0, "autoja": len(ex)}
        if not self.app.krediitit.esittely_sallittu(tarkista=True):
            raise ApiError("Esimerkkiautot ovat käytössä vain testitileillä.", 403)
        folder = Path(__file__).parent / "data" / "esimerkit"
        n = 0
        for f in sorted(folder.glob("*.akveri")):
            r = mittaustiedosto.import_file(st, f.read_bytes(), merkitse=False)
            # Esimerkit ovat esittelytilan mittauksia: raporttiin ESIMERKKI-leima, ei testilupaa eikä tarkistusta
            st.update_test(r["id"], demo=1, lupa=None, lupa_tila=None, lupa_testi=None)
            st.learn(r["ajoneuvo_id"], {"esimerkki": True})
            v = st.vehicle(r["ajoneuvo_id"]) or {}
            if (v.get("nimi") or "").startswith("Esimerkki: "):
                st.update_vehicle(r["ajoneuvo_id"], {"nimi": v["nimi"][len("Esimerkki: "):]})
            t = st.test(r["id"])
            meta = (t.get("tulos") or {}).get("meta")
            if meta:
                # Tulos lasketaan tämän version laskennalla, jotta esimerkit vastaavat ohjelmaa
                try:
                    res = analysis.analyze_test(st, r["id"], meta)
                    st.update_test(r["id"], tulos=res)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
            n += 1
        return {"ok": True, "lisatty": n,
                "autoja": len([v for v in st.vehicles() if (v.get("opitut") or {}).get("esimerkki")])}

    def logo(self, q, body):
        data = body.get("data", "")
        m = re.match(r"data:image/(png|jpeg);base64,(.*)", data)
        if not m:
            if body.get("poista"):
                self.app.storage.save_settings({"logo": ""})
                return {"ok": True}
            raise ApiError("Logon on oltava PNG- tai JPEG-kuva.")
        try:
            data = rajaa_logo(base64.b64decode(m.group(2)))
        except ValueError as e:
            raise ApiError(str(e))
        for vanha in self.app.storage.dir.glob("logo.*"):
            try:
                vanha.unlink()
            except OSError:
                pass
        path = self.app.storage.dir / "logo.png"
        path.write_bytes(data)
        self.app.storage.save_settings({"logo": str(path)})
        return {"ok": True}


ROUTES = [
    ("GET", r"/api/tila", "tila"), ("GET", r"/api/kennot", "kennot"), ("GET", r"/api/portit", "portit"),
    ("POST", r"/api/yhdista", "yhdista"), ("POST", r"/api/katkaise", "katkaise"), ("POST", r"/api/demo", "demo"),
    ("GET", r"/api/ajoneuvot", "ajoneuvot"), ("POST", r"/api/ajoneuvot", "lisaa_ajoneuvo"),
    ("GET", r"/api/ajoneuvot/(\d+)", "ajoneuvo"), ("PUT", r"/api/ajoneuvot/(\d+)", "muokkaa_ajoneuvo"),
    ("DELETE", r"/api/ajoneuvot/(\d+)", "poista_ajoneuvo"),
    ("POST", r"/api/vin", "vin"), ("GET", r"/api/mallit", "mallit"),
    ("POST", r"/api/mittaukset", "aloita"), ("POST", r"/api/mittaukset/aktiivinen/ohita", "ohita"),
    ("POST", r"/api/mittaukset/aktiivinen/keskeyta", "keskeyta"),
    ("POST", r"/api/mittaukset/aktiivinen/tauko", "tauko"),
    ("POST", r"/api/mittaukset/(\d+)/jatka", "jatka"), ("POST", r"/api/mittaukset/(\d+)/hylkaa", "hylkaa"),
    ("GET", r"/api/mittaukset", "mittaukset"), ("GET", r"/api/mittaukset/(\d+)", "mittaus"),
    ("DELETE", r"/api/mittaukset/(\d+)", "poista_mittaus"), ("POST", r"/api/mittaukset/avaa", "avaa_mittaus"),
    ("POST", r"/api/mittaukset/(\d+)/tallenna", "tallenna_kansioon"), ("GET", r"/api/mittaukset/(\d+)/tarkista", "tarkista"),
    ("POST", r"/api/mittaukset/(\d+)/laske-uudelleen", "laske_uudelleen"),
    ("POST", r"/api/mittaukset/(\d+)/riippumattomuus", "aseta_riippumattomuus"), ("POST", r"/api/mittaukset/(\d+)/jaa", "jaa_osiin"),
    ("GET", r"/api/kieli", "kieli"), ("POST", r"/api/kieli", "aseta_kieli"), ("GET", r"/api/kieli/sanasto", "kielen_sanasto"),
    ("GET", r"/api/asetukset", "asetukset"), ("POST", r"/api/asetukset", "tallenna_asetukset"),
    ("POST", r"/api/vaylakartoitus", "aloita_kartoitus"), ("GET", r"/api/vaylakartoitus", "kartoitus"),
    ("POST", r"/api/esimerkit", "esimerkit"),
    ("POST", r"/api/logo", "logo"), ("POST", r"/api/sulje", "sulje"), ("POST", r"/api/uudelleen", "uudelleen"),
    ("GET", r"/api/yllapito/tarkistus", "tarkistus"), ("GET", r"/api/yllapito/loki", "loki"),
    ("GET", r"/api/yllapito/varmuuskopiot", "varmuuskopiot"),
    ("POST", r"/api/yllapito/palauta/tarkista", "tarkista_palautus"), ("POST", r"/api/yllapito/palauta", "palauta"),

    ("POST", r"/api/ilmoitus/testi", "testi_ilmoitus"), ("GET", r"/api/ohjeet", "ohjeet"),
    ("GET", r"/api/tietoja", "tietoja"),
    ("GET", r"/api/krediitit", "krediitit"), ("POST", r"/api/krediitit/osto", "krediitit_osto"),
    ("POST", r"/api/mittaukset/(\d+)/poista-palvelusta", "poista_raportti_palvelusta"), ("POST", r"/api/tietosuoja/poista-tili", "poista_tili"),
    ("POST", r"/api/mittaukset/(\d+)/hyvityspyynto", "hyvityspyynto"),
]


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"{NIMI}/{VERSIO}"

        def log_message(self, fmt, *args):  # hiljainen loki
            pass

        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

        def _authorized(self, q) -> bool:
            if not api.key or self.client_address[0] in ("127.0.0.1", "::1"):
                return True
            cookie = self.headers.get("Cookie") or ""
            if f"avain={api.key}" in cookie.replace(" ", "").split(";"):
                return True
            return False

        def _dispatch(self, method):
            url = urlparse(self.path)
            path = url.path
            q = parse_qs(url.query)
            if not self._authorized(q):
                if q.get("avain", [""])[0] == api.key:
                    self._send(302, b"", "text/plain", {
                        "Location": "/", "Set-Cookie": f"avain={api.key}; Max-Age=31536000; SameSite=Strict; Path=/"})
                    return
                if path.startswith("/fonts/") or path in ("/style.css",):
                    pass
                else:
                    html = ("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                            "<title>AKVERI</title><body style='font-family:system-ui;padding:24px;max-width:480px'>"
                            "<h2>AKVERI</h2><p>Avaa ohjelma puhelimella osoitteesta, jonka ohjelma näyttää "
                            "tietokoneen ikkunassa ja Asetukset-sivulla, tai syötä suojakoodi.</p>"
                            "<form><input name='avain' inputmode='numeric' placeholder='Suojakoodi' "
                            "style='font-size:18px;padding:8px;width:100%'><button style='margin-top:10px;font-size:16px;"
                            "padding:8px 16px'>Avaa</button></form></body>")
                    self._send(403, html.encode("utf-8"), "text/html; charset=utf-8")
                    return
            try:
                if method == "GET" and self._files(path):
                    return
                body = {}
                if method in ("POST", "PUT"):
                    n = int(self.headers.get("Content-Length") or 0)
                    raw = self.rfile.read(n) if n else b""
                    if (self.headers.get("Content-Type") or "").startswith("application/octet-stream"):
                        body = {"_raw": raw}
                    elif raw:
                        body = json.loads(raw.decode("utf-8") or "{}")
                for m, pattern, name in ROUTES:
                    if m != method:
                        continue
                    mm = re.fullmatch(pattern, path)
                    if mm:
                        args = [int(g) for g in mm.groups()]
                        self._json(200, getattr(api, name)(q, body, *args))
                        return
                self._json(404, {"virhe": "Tuntematon osoite"})
            except ApiError as e:
                self._json(e.code, {"virhe": str(e)})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._json(500, {"virhe": f"Odottamaton virhe: {e}"})

        def _files(self, path) -> bool:
            st = api.app.storage
            if path == "/api/tietosuoja/akveri-tietoni.zip":
                # Oikeus saada pääsy tietoihin: akveri.fi-palvelun tiedot tästä tilistä yhtenä tiedostona
                import io as _io, json as _json, zipfile as _zip  # noqa: PLC0415,E401
                try:
                    tiedot = api.app.krediitit.tilin_tiedot()
                except krediittimoduuli.PalveluVirhe as e:
                    raise ApiError(str(e), 503)
                buf = _io.BytesIO()
                with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as z:
                    z.writestr("akveri-tietoni.json", _json.dumps(tiedot, ensure_ascii=False, indent=2))
                    z.writestr("LUEMINUT.txt", kielet.t(
                        "Tiedosto sisältää kaikki akveri.fi-palvelussa tähän sovelluksen tiliin liittyvät tiedot: tili, "
                        "krediittien kirjanpito, ostot ja rekisteröityjen raporttien tiedot. Mittaukset ja autot ovat vain "
                        "tällä laitteella.") + "\n")
                self._send(200, buf.getvalue(), "application/zip",
                           {"Content-Disposition": 'attachment; filename="akveri-tietoni.zip"'})
                return True
            m0 = re.fullmatch(r"/api/mittaukset/(\d+)/(?:tiedosto\.akveri|data\.csv|raakadata\.csv\.gz)", path)
            if m0 and krediittimoduuli.tulos_odottaa(st.test(int(m0.group(1))) or {}):
                # Perumisaikana mittauksen tiedostoja ei anneta: tulos näytetään vasta rekisteröinnin jälkeen
                raise ApiError("Mittauksen tiedostot ovat saatavilla, kun raportti on rekisteröity akveri.fi-palveluun. "
                               "Tarkista verkkoyhteys.", 409)
            m3 = re.fullmatch(r"/api/mittaukset/(\d+)/tiedosto\.akveri", path)
            if m3:
                try:
                    name, data = mittaustiedosto.export(st, int(m3.group(1)))
                except ValueError as e:
                    raise ApiError(str(e), 404)
                self._send(200, data, "application/octet-stream",
                           {"Content-Disposition": f'attachment; filename="{name}"'})
                return True
            m = re.fullmatch(r"/api/mittaukset/(\d+)/(raportti\.pdf|data\.csv|raakadata\.csv\.gz)", path)
            if m:
                tid = int(m.group(1))
                kind = m.group(2)
                t = st.test(tid)
                if not t:
                    raise ApiError("Mittausta ei löydy.", 404)
                if kind == "raportti.pdf":
                    try:
                        p = report.build(st, tid)
                    except ValueError as e:
                        raise ApiError(str(e))
                    self._send(200, p.read_bytes(), "application/pdf",
                               {"Content-Disposition": f'inline; filename="{p.name}"'})
                elif kind == "data.csv":
                    buf = io.StringIO()
                    w = csv.writer(buf, delimiter=";")
                    cols = ["t", "vaihe", "v", "i", "soc_ui", "soc_avg", "nfp", "ner", "t_min", "t_max",
                            "c_min", "c_max", "e_in", "e_out", "ah_in"]
                    w.writerow(["aika", "vaihe", "jannite_V", "virta_A", "varaus_naytto_pct", "varaus_ka_pct",
                                "taysi_energia_kWh", "jaljella_kWh", "lampo_min_C", "lampo_max_C",
                                "kenno_min_V", "kenno_max_V", "energia_sisaan_kWh", "energia_ulos_kWh", "Ah_sisaan"])
                    for s in st.samples(tid):
                        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["t"]))] +
                                   [("" if s[c] is None else (f"{s[c]:.4f}".replace(".", ",")
                                                              if isinstance(s[c], float) else s[c])) for c in cols[1:]])
                    self._send(200, ("﻿" + buf.getvalue()).encode("utf-8"), "text/csv; charset=utf-8",
                               {"Content-Disposition": f'attachment; filename="mittaus_{tid:05d}.csv"'})
                else:
                    p = Path(t.get("raakadata") or "")
                    if not p.exists():
                        raise ApiError("Raakadataa ei löydy.", 404)
                    self._send(200, p.read_bytes(), "application/gzip",
                               {"Content-Disposition": f'attachment; filename="{p.name}"'})
                return True
            if path == "/api/yllapito/varmuuskopio":
                p = maintenance.backup(st)
                self._send(200, p.read_bytes(), "application/zip",
                           {"Content-Disposition": f'attachment; filename="{p.name}"'})
                return True
            m2 = re.fullmatch(r"/api/yllapito/varmuuskopiot/([\w.-]+\.zip)", path)
            if m2:
                p = st.dir / "varmuuskopiot" / m2.group(1)
                if not p.exists():
                    raise ApiError("Varmuuskopiota ei löydy.", 404)
                self._send(200, p.read_bytes(), "application/zip",
                           {"Content-Disposition": f'attachment; filename="{p.name}"'})
                return True
            if path == "/api/ohjeet.pdf":
                p = st.dir / "AKVERI-kayttoohje.pdf"
                docs.build_pdf(p, alusta=platform_name())
                self._send(200, p.read_bytes(), "application/pdf",
                           {"Content-Disposition": 'inline; filename="AKVERI-kayttoohje.pdf"'})
                return True
            if path.startswith("/api/"):
                return False
            if path.startswith("/fonts/"):
                f = FONTS / Path(path).name
            else:
                f = WEB / (path.lstrip("/") or "index.html")
                if not f.exists() or f.is_dir():
                    f = WEB / "index.html"
            if not f.exists():
                return False
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)
            return True

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

    return Handler


def _auto_backup(app, keep=5, every_days=7):
    """Automaattinen varmuuskopio kerran viikossa, viisi uusinta säilytetään."""
    try:
        d = app.storage.dir / "varmuuskopiot"
        old = _backups(d) if d.exists() else []
        if not app.storage.tests() and not app.storage.vehicles():
            return
        if old and time.time() - old[-1].stat().st_mtime < every_days * 86400:
            return
        time.sleep(20)
        maintenance.backup(app.storage)
        old = _backups(d)
        for p in old[:-keep]:
            p.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        traceback.print_exc()


def bind_server(api, host, port, attempts=20):
    last = None
    for _ in range(attempts):
        try:
            return ThreadingHTTPServer((host, port), make_handler(api))
        except OSError as e:          # portti vielä edellisen käynnistyksen varaama
            last = e
            time.sleep(0.5)
    raise last


def serve(host=None, port=8765, data_dir=None, open_browser=True, open_window=None, idle_exit=None):
    """Käynnistää palvelimen. Palauttaa "sulje", "uudelleen" tai None (Ctrl+C / joutokäynti)."""
    app = App(data_dir)
    api = Api(app)
    api.port = port
    if host is None:
        host = "0.0.0.0" if app.settings.get("puhelin_kaytossa") else "127.0.0.1"
    if host in ("0.0.0.0", ""):
        import secrets
        key = app.settings.get("puhelin_avain")
        if not key:
            key = "".join(secrets.choice("0123456789") for _ in range(8))
            app.storage.save_settings({"puhelin_avain": key})
        api.network, api.key = True, key
    httpd = bind_server(api, host, port)
    httpd.daemon_threads = True
    api.httpd = httpd


    def ticker():
        while True:
            time.sleep(15)
            try:
                app.tick()
                # Ilman avointa ikkunaa ja käynnissä olevaa mittausta ohjelma sulkeutuu itsestään
                if idle_exit and not app.recorder.active and time.time() - api.last_seen > idle_exit:
                    api._stop(None)
                    return
            except Exception:  # noqa: BLE001
                traceback.print_exc()

    threading.Thread(target=ticker, daemon=True).start()
    threading.Thread(target=_auto_backup, args=(app,), daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    print(f"{NIMI} {VERSIO} käynnissä: {url}")
    print(f"Tiedot tallennetaan kansioon: {app.storage.dir}")
    if api.network:
        print("")
        print("Käyttö puhelimella: liitä puhelin samaan Wi-Fi-verkkoon ja avaa jokin näistä osoitteista:")
        for u in api.phone_info()["osoitteet"]:
            print(f"    {u}")
        print(f"Suojakoodi: {api.key}")
        print("Jos Windows kysyy palomuurin lupaa, salli yhteys yksityisissä verkoissa.")
        print("")
    print("Sulje ohjelma painamalla Ctrl+C.")
    if open_window:
        threading.Timer(0.3, lambda: open_window(url)).start()
    elif open_browser:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.disconnect()
        httpd.server_close()
    return api.exit_action
