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

from . import NIMI, VERSIO, docs, maintenance, mittaustiedosto, profiles, report
from . import vin as vinmod
from .app import App
from .decoder import PAKOLLISET
from .sources import list_ports

WEB = Path(__file__).parent / "web"
FONTS = Path(__file__).parent / "data" / "fonts"


def platform_name() -> str:
    import os
    import sys
    if os.environ.get("AKUX_ALUSTA"):
        return os.environ["AKUX_ALUSTA"]
    if sys.platform.startswith("win"):
        return "windows"
    return "mac" if sys.platform == "darwin" else "linux"


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


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

    def tarkista_paivitys(self, q, body):
        try:
            return maintenance.inspect_update(body.get("_raw") or b"")
        except ValueError as e:
            raise ApiError(str(e))

    def paivita(self, q, body):
        if self.app.recorder.active:
            raise ApiError("Mittaus on käynnissä. Päivitä ohjelma mittauksen jälkeen.")
        try:
            info = maintenance.start_update(body.get("_raw") or b"")
        except ValueError as e:
            raise ApiError(str(e))
        self._stop("sulje")
        return info

    def testi_ilmoitus(self, q, body):
        if body.get("osoite") is not None:
            self.app.storage.save_settings({"ilmoitus_osoite": body["osoite"].strip()})
        ok, msg = self.app.notifier.send("valmis", "Akux – testi-ilmoitus",
                                         "Ilmoitukset toimivat. Saat tällaisen ilmoituksen, kun mittaus etenee.",
                                         force=True, wait=True)
        if not ok:
            raise ApiError(f"Ilmoituksen lähetys epäonnistui: {msg}")
        return {"ok": True}

    def ohjeet(self, q, body):
        return {"osiot": docs.as_html()}

    def tietoja(self, q, body):
        import platform
        return {"nimi": NIMI, "versio": VERSIO, "datakansio": str(self.app.storage.dir), "alusta": platform_name(),
                "python": platform.python_version(), "jarjestelma": f"{platform.system()} {platform.release()}"}

    def tila(self, q, body):
        self.last_seen = time.time()
        a = self.app
        src = a.source
        snap = a.decoder.snapshot()
        known = None
        if snap.get("vin"):
            v = a.storage.find_vehicle_by_vin(snap["vin"])
            known = {"id": v["id"], "nimi": v["nimi"]} if v else None
        return {
            "nimi": NIMI, "versio": VERSIO, "alusta": platform_name(),
            "yhteys": {
                "kaynnissa": bool(src and src.running), "lahde": src.name if src else None,
                "tila": src.status if src else "Ei yhteyttä", "virhe": src.error if src else None,
                "tiedot": src.info if src else {}, "simuloitu": bool(src and src.simulated),
                "demo": {"tila": src.mode, "nopeutus": src.accel} if (src and src.simulated) else None,
            },
            "live": snap,
            "auto_tunnettu": known,
            "mittaus": a.recorder.progress(),
            "vaylatesti": self._bus_verdict(),
        }

    def _bus_verdict(self):
        d = self.app.decoder
        if not d.total_frames:
            return None
        rep = d.bus_report(self.app.source.now() if self.app.source else None)
        missing = [r for r in rep if r["pakollinen"] and not r["nakyy"]]
        return {"viestit": rep, "puuttuvat": [r["kuvaus"] for r in missing], "kunnossa": not missing,
                "kehyksia": d.total_frames}

    def kennot(self, q, body):
        return {"kennot": self.app.decoder.bricks_list()}

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
            self.app.connect("demo", soc=(_num(body.get("soc")) or 12) / 100, accel=_num(body.get("nopeutus")) or 60)
        else:
            port = body.get("portti") or self.app.settings.get("portti")
            baud = int(body.get("baud") or 0) or None
            from . import sources
            if not sources.SERIAL_FACTORY:
                try:
                    import serial  # noqa: F401
                except ImportError:
                    raise ApiError("Sovittimen yhteysosa puuttuu ohjelmasta. Asenna ohjelma uudelleen.")
            self.app.connect("obdlink", port=port, baud=baud)
            self.app.storage.save_settings({"portti": port})
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
        if not data.get("malli_id") and data.get("vin"):
            m, _ = profiles.identify(vinmod.decode(data["vin"]))
            data["malli_id"] = m["id"] if m else None
            if not data.get("vuosimalli"):
                data["vuosimalli"] = vinmod.decode(data["vin"]).get("vuosimalli")
        return data

    def lisaa_ajoneuvo(self, q, body):
        data = self._vehicle_payload(body)
        if data.get("vin") and self.app.storage.find_vehicle_by_vin(data["vin"]):
            raise ApiError("Ajoneuvo tällä valmistenumerolla on jo tallennettu.")
        if not data.get("nimi"):
            m = profiles.get(data.get("malli_id"))
            data["nimi"] = (body.get("rekisteri") or "") or (m["nimi"] if m else "Tesla")
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
        model, reasons = profiles.identify(info) if info["kelvollinen"] else (None, [])
        return {"tiedot": info, "malli": model, "perusteet": reasons}

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
                "ero_mv": (r.get("kennot") or {}).get("ero_mv"), "virhe": r.get("virhe")}

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
        tyyppi = body.get("tyyppi")
        if tyyppi not in ("pikatarkastus", "kapasiteetti"):
            raise ApiError("Valitse mittauksen tyyppi.")
        verdict = self._bus_verdict()
        if not verdict or not verdict["kunnossa"]:
            missing = ", ".join(verdict["puuttuvat"]) if verdict else "kaikki"
            raise ApiError(f"Akun tietoja ei vielä vastaanoteta ({missing.lower()}). Tarkista, että auto on "
                           "hereillä ja sovitin on kytketty.")
        try:
            tid = self.app.start_test(vehicle_id=vid, tyyppi=tyyppi, mittarilukema=_num(body.get("mittarilukema")),
                                      mittaaja=body.get("mittaaja") or self.app.settings.get("mittaaja", ""),
                                      lisatiedot=body.get("lisatiedot", ""))
        except RuntimeError as e:
            raise ApiError(str(e))
        return {"id": tid}

    def ohita(self, q, body):
        self.app.recorder.skip_phase()
        return {"ok": True}

    def keskeyta(self, q, body):
        self.app.recorder.cancel()
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
        return t

    def avaa_mittaus(self, q, body):
        try:
            return mittaustiedosto.import_file(self.app.storage, body.get("_raw") or b"")
        except ValueError as e:
            raise ApiError(str(e))

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

    # -- asetukset ------------------------------------------------------
    def asetukset(self, q, body):
        s = self.app.settings
        s["datakansio"] = str(self.app.storage.dir)
        s["puhelin"] = self.phone_info()
        s["mittaus_kansio_oletus"] = "Lataukset/Akux" if platform_name() == "android" else str(mittaustiedosto.default_folder())
        s.pop("puhelin_avain", None)
        return s

    def tallenna_asetukset(self, q, body):
        body.pop("puhelin_avain", None)
        for k in ("lepo_alku_min", "lepo_loppu_min", "kapasiteetti_lahto_soc_max", "lampotila_min", "lampotila_max"):
            if k in body:
                body[k] = _num(body[k])
        return self.app.storage.save_settings(body)

    def logo(self, q, body):
        data = body.get("data", "")
        m = re.match(r"data:image/(png|jpeg);base64,(.*)", data)
        if not m:
            if body.get("poista"):
                self.app.storage.save_settings({"logo": ""})
                return {"ok": True}
            raise ApiError("Logon on oltava PNG- tai JPEG-kuva.")
        ext = "png" if m.group(1) == "png" else "jpg"
        path = self.app.storage.dir / f"logo.{ext}"
        path.write_bytes(base64.b64decode(m.group(2)))
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
    ("GET", r"/api/mittaukset", "mittaukset"), ("GET", r"/api/mittaukset/(\d+)", "mittaus"),
    ("DELETE", r"/api/mittaukset/(\d+)", "poista_mittaus"), ("POST", r"/api/mittaukset/avaa", "avaa_mittaus"),
    ("POST", r"/api/mittaukset/(\d+)/tallenna", "tallenna_kansioon"), ("GET", r"/api/mittaukset/(\d+)/tarkista", "tarkista"),
    ("GET", r"/api/asetukset", "asetukset"), ("POST", r"/api/asetukset", "tallenna_asetukset"),
    ("POST", r"/api/logo", "logo"), ("POST", r"/api/sulje", "sulje"), ("POST", r"/api/uudelleen", "uudelleen"),
    ("GET", r"/api/yllapito/tarkistus", "tarkistus"), ("GET", r"/api/yllapito/loki", "loki"),
    ("GET", r"/api/yllapito/varmuuskopiot", "varmuuskopiot"),
    ("POST", r"/api/yllapito/palauta/tarkista", "tarkista_palautus"), ("POST", r"/api/yllapito/palauta", "palauta"),
    ("POST", r"/api/yllapito/paivitys/tarkista", "tarkista_paivitys"), ("POST", r"/api/yllapito/paivitys", "paivita"),
    ("POST", r"/api/ilmoitus/testi", "testi_ilmoitus"), ("GET", r"/api/ohjeet", "ohjeet"),
    ("GET", r"/api/tietoja", "tietoja"),
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
                            "<title>Akux</title><body style='font-family:system-ui;padding:24px;max-width:480px'>"
                            "<h2>Akux</h2><p>Avaa ohjelma puhelimella osoitteesta, jonka ohjelma näyttää "
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
            m3 = re.fullmatch(r"/api/mittaukset/(\d+)/tiedosto\.akux", path)
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
                p = st.dir / "Akux-kayttoohje.pdf"
                docs.build_pdf(p)
                self._send(200, p.read_bytes(), "application/pdf",
                           {"Content-Disposition": 'inline; filename="Akux-kayttoohje.pdf"'})
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
        old = sorted(d.glob("Akux-varmuuskopio_*.zip")) if d.exists() else []
        if not app.storage.tests() and not app.storage.vehicles():
            return
        if old and time.time() - old[-1].stat().st_mtime < every_days * 86400:
            return
        time.sleep(20)
        maintenance.backup(app.storage)
        old = sorted(d.glob("Akux-varmuuskopio_*.zip"))
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
