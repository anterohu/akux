"""Ylläpito- ja palvelintoiminnot HTTP-rajapinnan kautta: asetukset, puhelinkäytön suojaus,
ilmoitukset, laaduntarkistus, varmuuskopio ja palautus, päivityspaketin tarkistus, ohje-PDF."""
import io
import json
import socket
import os
import sys
import tempfile as _tf
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AKUX_MITTAUSKANSIO", _tf.mkdtemp(prefix="akux-testi-"))

from akux import server  # noqa: E402
from akux.server import Api, bind_server  # noqa: E402
from akux.app import App  # noqa: E402

received = []


class Ntfy(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        received.append({"title": self.headers.get("Title"), "body": self.rfile.read(n).decode()})
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def call(base, path, method="GET", body=None, raw=None, ok=True):
    data, headers = None, {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if raw is not None:
        data = raw
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            ct = r.headers.get("Content-Type", "")
            b = r.read()
            return r.status, (json.loads(b) if "json" in ct else b)
    except urllib.error.HTTPError as e:
        if ok:
            raise AssertionError(f"{path}: {e.code} {e.read()[:300]}")
        return e.code, json.loads(e.read() or b"{}")


def test_yllapito():
    with tempfile.TemporaryDirectory() as tmp:
        # ilmoituspalvelin
        np = free_port()
        ns = HTTPServer(("127.0.0.1", np), Ntfy)
        threading.Thread(target=ns.serve_forever, daemon=True).start()

        app = App(tmp)
        api = Api(app)
        port = free_port()
        api.port = port
        httpd = bind_server(api, "127.0.0.1", port)
        api.httpd = httpd
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}"

        # asetukset ja ilmoitukset
        call(base, "/api/asetukset", "POST", {"yritys_nimi": "Testi Oy", "ilmoitukset_kaytossa": True,
                                               "ilmoitus_osoite": f"http://127.0.0.1:{np}/akux"})
        _, s = call(base, "/api/asetukset")
        assert s["yritys_nimi"] == "Testi Oy" and "puhelin_avain" not in s
        call(base, "/api/ilmoitus/testi", "POST", {})
        assert received and "testi" in received[-1]["title"].lower() or received[-1]["title"].startswith("=?UTF-8?B?")

        # mittaus esittelytilassa: vaihe- ja valmisilmoitukset
        call(base, "/api/yhdista", "POST", {"tyyppi": "demo", "soc": 60, "nopeutus": 60})
        end = time.time() + 20
        while time.time() < end:
            _, t = call(base, "/api/tila")
            if t["vaylatesti"] and t["vaylatesti"]["kunnossa"] and t["live"]["vin"]:
                break
            time.sleep(0.3)
        _, r = call(base, "/api/ajoneuvot", "POST", {"vin": t["live"]["vin"], "rekisteri": "ABC-123",
                                                     "kayttoonotto": "14.5.2020"})
        vid = r["id"]
        _, v = call(base, f"/api/ajoneuvot/{vid}")
        assert v["malli_id"] == "m3-lr-2019-2020-nca" and v["kayttoonotto"] == "14.5.2020"
        _, other = call(base, "/api/ajoneuvot", "POST", {"vin": "5YJYGDEE8MF123456", "rekisteri": "XYZ-789"})
        code, err = call(base, "/api/mittaukset", "POST", {"ajoneuvo_id": other["id"], "tyyppi": "pikatarkastus"},
                         ok=False)
        assert code == 400 and "ei vastaa" in err["virhe"], err
        call(base, f"/api/ajoneuvot/{other['id']}", "DELETE")
        code, err = call(base, "/api/ajoneuvot", "POST", {"vin": "ABC"}, ok=False)
        assert code == 400 and "17" in err["virhe"]
        _, r = call(base, "/api/mittaukset", "POST", {"ajoneuvo_id": vid, "tyyppi": "pikatarkastus",
                                                      "mittarilukema": "112 000"})
        tid = r["id"]
        code, err = call(base, "/api/sulje", "POST", {}, ok=False)
        assert code == 409
        end = time.time() + 90
        while time.time() < end:
            _, t = call(base, "/api/tila")
            if not t["mittaus"]:
                break
            time.sleep(0.5)
        _, m = call(base, f"/api/mittaukset/{tid}")
        assert m["tila"] == "valmis", m["tila"]
        tk = m["tulos"]["takuu"]
        assert tk["voimassa"] is True and tk["paattyy"] == "14.5.2028" and tk["km_jaljella"] == 80000
        assert m["tulos"]["yhteenveto"]["tulkinta"]
        time.sleep(1)
        assert any("valmis" in json.dumps(x).lower() or "Akun kunto" in x["body"] for x in received)

        _, pdf = call(base, f"/api/mittaukset/{tid}/raportti.pdf")
        assert pdf[:4] == b"%PDF" and len(pdf) > 50000
        _, csvb = call(base, f"/api/mittaukset/{tid}/data.csv")
        assert b"jannite_V" in csvb
        _, ver = call(base, f"/api/mittaukset/{tid}/tarkista")
        assert ver["ok"]

        # laaduntarkistus
        _, q = call(base, "/api/yllapito/tarkistus")
        try:
            import serial  # noqa: F401
            skip = set()
        except ImportError:          # testiympäristössä ei ole sarjaporttikirjastoa
            skip = {"Sovittimen yhteys"}
        bad = [c for c in q["tarkistukset"] if c["tila"] == "virhe" and c["nimi"] not in skip]
        assert not bad, bad
        print("Laaduntarkistus:", [(c["nimi"], c["tila"]) for c in q["tarkistukset"]])
        folder = Path(os.environ["AKUX_MITTAUSKANSIO"])
        extra = [p.name for p in folder.glob("*Laaduntarkistus*")] if folder.exists() else []
        assert not extra, f"laaduntarkistus tallensi tiedostoja mittauskansioon: {extra}"

        # esimerkkiautot: lisäys, raportit ja poisto
        _, e = call(base, "/api/esimerkit", "POST", {})
        assert e["lisatty"] == 23 and e["autoja"] == 10, e
        _, e2 = call(base, "/api/esimerkit", "POST", {})
        assert e2["lisatty"] == 0, "esimerkit lisättiin kahdesti"
        _, lst = call(base, "/api/mittaukset")
        ex_tests = [t for t in lst["mittaukset"] if t["id"] != tid]
        assert len(ex_tests) == 23
        merkit = set()
        for t in ex_tests:
            assert t["tila"] == "valmis" and t["kunto_pct"], t
            _, pdf_e = call(base, f"/api/mittaukset/{t['id']}/raportti.pdf")
            assert pdf_e[:4] == b"%PDF"
            _, full = call(base, f"/api/mittaukset/{t['id']}")
            kk = full["tulos"]["kapasiteetit"]
            aj = full["tulos"]["ajoneuvo"]
            merkit.add(aj.get("merkki"))
            assert kk["brutto_nyt"], kk
            if aj.get("merkki") == "Tesla":     # muiden merkkien akunhallinta ei ilmoita suojavaraa
                assert kk["netto_nyt"] and kk["netto_nyt"] < kk["brutto_nyt"], kk
            assert aj["kennotyyppi"], aj
            assert full["ajoneuvo"]["nimi"].split()[0] == aj.get("merkki"), (full["ajoneuvo"]["nimi"], aj.get("merkki"))
        assert merkit == {"Tesla", "Hyundai", "Kia", "Nissan", "Volkswagen", "Škoda", "Audi", "Cupra"}, merkit
        _, d = call(base, "/api/esimerkit", "POST", {"poista": True})
        assert d["poistettu"] == 10
        _, vs = call(base, "/api/ajoneuvot")
        assert len(vs["ajoneuvot"]) == 1, "omat autot eivät saa poistua"

        # ohjeet
        _, o = call(base, "/api/ohjeet")
        assert len(o["osiot"]) >= 10
        _, gp = call(base, "/api/ohjeet.pdf")
        assert gp[:4] == b"%PDF"

        # varmuuskopio ja palautuksen tarkistus
        call(base, "/api/katkaise", "POST", {})
        _, zipb = call(base, "/api/yllapito/varmuuskopio")
        _, info = call(base, "/api/yllapito/palauta/tarkista", "POST", raw=zipb)
        assert info["autoja"] == 1 and info["mittauksia"] == 1
        code, err = call(base, "/api/yllapito/palauta/tarkista", "POST", raw=b"roskaa", ok=False)
        assert code == 400
        _, lst = call(base, "/api/yllapito/varmuuskopiot")
        assert len(lst["varmuuskopiot"]) == 1

        # palautus oikeasti: tiedot palautuvat ja vanhat siirtyvät talteen
        call(base, "/api/ajoneuvot", "POST", {"nimi": "Toinen"})
        _, meta = call(base, "/api/yllapito/palauta", "POST", raw=zipb)
        assert Path(meta["talteen"]).exists()
        time.sleep(1)
        app2 = App(tmp)
        assert len(app2.storage.vehicles()) == 1 and len(app2.storage.tests()) == 1
        t2 = app2.storage.tests()[0]
        assert Path(t2["raakadata"]).exists()
        app2.storage.close()
        ns.shutdown()

        # puhelinkäytön suojaus
        app3 = App(tmp)
        api3 = Api(app3)
        api3.network, api3.key, api3.port = True, "12345678", free_port()
        h3 = bind_server(api3, "0.0.0.0", api3.port)
        threading.Thread(target=h3.serve_forever, daemon=True).start()
        lan = server.lan_addresses()
        if lan:
            os.environ["NO_PROXY"] = os.environ["no_proxy"] = ",".join(lan)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            ext = f"http://{lan[0]}:{api3.port}"
            try:
                opener.open(ext + "/api/tila", timeout=5)
                raise AssertionError("suojaamaton")
            except urllib.error.HTTPError as e:
                assert e.code == 403

            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **k):
                    return None
            op2 = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
            try:
                op2.open(ext + "/?avain=12345678", timeout=5)
            except urllib.error.HTTPError as e:
                assert e.code == 302 and "avain=12345678" in e.headers.get("Set-Cookie")
            req = urllib.request.Request(ext + "/api/tila", headers={"Cookie": "avain=12345678"})
            assert opener.open(req, timeout=5).status == 200
        h3.shutdown()
        print("OK ylläpito")


if __name__ == "__main__":
    test_yllapito()
