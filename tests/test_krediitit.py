"""Krediitit, testiluvat ja raportin tarkistus päästä päähän: AKVERI-sovellus ja oikea AKVERI-palvelin (Node).

Tarkistaa koko tiedon kulun sovelluksesta hallintaan:
  - ilman krediittiä oikeasta autosta ei voi aloittaa mittausta, eikä reaaliaikaista kuntoa näytetä
  - omistaja lisää krediitit hallinnassa (kaksivaiheinen kirjautuminen), mittaus veloittaa yhden
  - valmis raportti rekisteröityy ja näkyy tarkistussivun rajapinnassa samoilla luvuilla kuin sovelluksessa
  - palvelimelle lähtee vain yhteenveto (ei rekisterikilpeä, mittaajan nimeä, lisätietoja eikä koko valmistenumeroa)
  - keskeytys perumisajan sisällä palauttaa krediitin, eikä perutusta mittauksesta tehdä raporttia
  - perumisajan jälkeen hyvityspyyntö menee hallintaan tapahtumalokin kanssa
  - tilin avainta ei näytetä käyttöliittymälle eikä palvelun osoitetta voi vaihtaa sieltä
  - ilman verkkoa rekisteröinti jää jonoon ja tehdään, kun yhteys palaa
  - mittaustiedosto kuljettaa luvan toiselle laitteelle, mutta toinen laite ei rekisteröi sitä
Vaatii Noden (22 tai uudempi).
"""
import base64
import hashlib
import hmac
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
JUURI = Path(__file__).resolve().parents[1]
ALKUTUNNUS = "k" * 48


def wait(cond, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def vapaa_portti():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def totp(salaisuus, t=None):
    avain = base64.b32decode(salaisuus + "=" * (-len(salaisuus) % 8))
    laskuri = int((t or time.time()) // 30)
    h = hmac.new(avain, struct.pack(">Q", laskuri), hashlib.sha1).digest()
    o = h[-1] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)


class Palvelin:
    def __init__(self, kansio):
        self.portti = vapaa_portti()
        self.osoite = f"http://127.0.0.1:{self.portti}"
        env = {**os.environ, "PORT": str(self.portti), "BIND_HOST": "127.0.0.1", "DB_DIR": str(Path(kansio) / "palvelin"),
               "AKVERI_ALKUTUNNUS": ALKUTUNNUS, "JULKINEN_OSOITE": "https://akveri.fi"}
        self.p = subprocess.Popen(["node", str(JUURI / "palvelin" / "server.js")], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert wait(lambda: self._ok(), 20), "AKVERI-palvelin ei käynnistynyt"
        self.evaste = None

    def _ok(self):
        try:
            return self.get("/api/v1/tila")["ok"]
        except Exception:  # noqa: BLE001
            return False

    def pyynto(self, method, polku, body=None, hallinta=False):
        h = {"Content-Type": "application/json"}
        if hallinta:
            h["X-AKVERI-Hallinta"] = "1"
            if self.evaste:
                h["Cookie"] = self.evaste
        req = urllib.request.Request(self.osoite + polku, method=method, headers=h,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.headers.get("Set-Cookie"):
                    self.evaste = r.headers["Set-Cookie"].split(";")[0]
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise AssertionError(f"{polku}: {e.code} {e.read().decode()}") from None

    def get(self, polku, hallinta=False):
        return self.pyynto("GET", polku, hallinta=hallinta)

    def kirjaudu(self):
        a = self.pyynto("POST", "/api/hallinta/alusta", {"alkutunnus": ALKUTUNNUS, "nimi": "Testi Omistaja", "sahkoposti": "omistaja@akveri.fi", "salasana": "testisalasana-123"}, True)
        self.pyynto("POST", "/api/hallinta/alusta/vahvista", {"alkutunnus": ALKUTUNNUS, "koodi": totp(a["salaisuus"])}, True)
        # Sama koodi ei kelpaa toiseen kertaan: kirjautumiseen käytetään seuraavaa aika-askelta
        nyt = time.time()
        time.sleep(30 - nyt % 30 + 0.5)
        self.pyynto("POST", "/api/hallinta/kirjaudu", {"sahkoposti": "omistaja@akveri.fi", "salasana": "testisalasana-123", "koodi": totp(a["salaisuus"])}, True)

    def sulje(self):
        self.p.terminate()
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()


def oikea_auto(app, **opts):
    """Esittelytilan simulaattori, joka esittää oikeaa autoa (ohjelma käsittelee sen kuin sovittimen)."""
    src = app.connect("demo", soc=0.6, accel=40, **opts)
    src.simulated = False
    assert wait(lambda: app.decoder.state.brick_count and app.decoder.state.nfp_kwh, 30)
    return src


def test_krediitit():
    if not shutil.which("node"):
        raise SystemExit("Node puuttuu: asenna Node 22, jotta krediittien päästä päähän -testi voidaan ajaa.")
    with tempfile.TemporaryDirectory() as kansio:
        palvelin = Palvelin(kansio)
        os.environ["AKVERI_PALVELU"] = palvelin.osoite
        try:
            from akux.app import App
            from akux.server import Api, ApiError
            from akux import report, mittaustiedosto, krediitit as kr

            app = App(Path(kansio) / "a")
            api = Api(app)
            src = oikea_auto(app)
            vid = app.storage.add_vehicle({"vin": app.decoder.state.vin, "rekisteri": "XYZ-999"})

            # 1. Ilman mittausta reaaliaikaista kuntoa ei näytetä oikeasta autosta
            live = api.tila({}, {})["live"]
            assert live.get("kunto_piilotettu") and "nfp_kwh" not in live and "bms_soh_pct" not in live, live.keys()
            assert live.get("soc_ui") is not None and live.get("pack_v") is not None, "jännite ja varaus näkyvät"

            # 2. Uudella tilillä ei ole krediittejä
            try:
                app.start_test(vehicle_id=vid, tyyppi="pikatarkastus", mittarilukema=50000)
                raise AssertionError("mittaus alkoi ilman krediittiä")
            except RuntimeError as e:
                assert "Krediitit eivät riitä" in str(e), e
            tili = app.storage.settings()["tili"]
            assert "tili_avain" not in api.asetukset({}, {}), "tilin avainta ei näytetä käyttöliittymälle"
            api.tallenna_asetukset({}, {"palvelu_osoite": "https://huijaus.example", "tili": "T000000000000"})
            assert app.storage.settings()["tili"] == tili and "palvelu_osoite" not in app.storage.settings()

            # 3. Omistaja lisää krediitit hallinnassa
            palvelin.kirjaudu()
            palvelin.pyynto("POST", f"/api/hallinta/tilit/{tili}/krediitit", {"muutos": 3, "selite": "Testi"}, True)
            assert api.krediitit({}, {})["saldo"] == 3
            v = api.krediitit({}, {})["versiot"]
            assert v["vahimmaisversio"] == "2.0.0" and not v["paivitys_pakollinen"] and not v["paivitys_saatavilla"], v
            # Vähimmäisversion nosto: tämä versio ei saa enää krediittitoimintoja ja ohjelma kertoo päivityksestä
            palvelin.pyynto("PUT", "/api/hallinta/asetukset", {"vahimmaisversio": "9.0.0", "uusinVersio": "9.0.0"}, True)
            try:
                app.start_test(vehicle_id=vid, tyyppi="pikatarkastus")
                raise AssertionError("vanha versio aloitti mittauksen")
            except RuntimeError as e:
                assert "liian vanha" in str(e), e
            palvelin.pyynto("PUT", "/api/hallinta/asetukset", {"vahimmaisversio": "2.0.0", "uusinVersio": "9.0.0"}, True)
            assert api.krediitit({}, {})["versiot"]["paivitys_saatavilla"] is True
            palvelin.pyynto("PUT", "/api/hallinta/asetukset", {"uusinVersio": ""}, True)

            # 3a. Esittelytila ja esimerkkiautot eivät ole asiakkaiden käytössä (vain testitileillä)
            vanha_esittely = os.environ.pop("AKVERI_ESITTELY", None)
            try:
                assert api.tietoja({}, {})["esittely"] is False
                for kutsu in (lambda: api.yhdista({}, {"tyyppi": "demo"}), lambda: api.esimerkit({}, {})):
                    try:
                        kutsu()
                        raise AssertionError("esittelytila avautui asiakkaalle")
                    except ApiError as e:
                        assert e.code == 403 and "testitileillä" in str(e), e
                api.tallenna_asetukset({}, {"esittely": True})
                assert app.storage.settings()["esittely"] is False, "esittelytilaa ei voi avata asetuksista"
                assert not [v for v in app.storage.vehicles() if (v.get("opitut") or {}).get("esimerkki")]

                # 3b. Testitili: mittaus ei kuluta krediittiä ja lupa merkitään testiksi. Esittelytila avautuu.
                palvelin.pyynto("POST", f"/api/hallinta/tilit/{tili}/tila", {"testitili": True}, True)
                assert api.krediitit({}, {})["testitili"] is True
                assert api.tietoja({}, {})["esittely"] is True
                assert api.esimerkit({}, {})["ok"] and api.esimerkit({}, {"poista": True})["poistettu"] > 0
            finally:
                if vanha_esittely is not None:
                    os.environ["AKVERI_ESITTELY"] = vanha_esittely
            tidt = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti", mittarilukema=49990)
            assert app.storage.test(tidt)["lupa_testi"] == 1 and api.krediitit({}, {})["saldo"] == 3
            assert api.mittaus({}, {}, tidt)["lupa"]["testi"] is True
            api.keskeyta({}, {})
            assert api.krediitit({}, {})["saldo"] == 3, "testiluvan peruminen ei lisää krediittejä"
            palvelin.pyynto("POST", f"/api/hallinta/tilit/{tili}/tila", {"testitili": False}, True)
            vanha_esittely = os.environ.pop("AKVERI_ESITTELY", None)
            assert api.krediitit({}, {})["testitili"] is False and api.tietoja({}, {})["esittely"] is False, \
                "testitilan poisto sulkee esittelytilan"
            if vanha_esittely is not None:
                os.environ["AKVERI_ESITTELY"] = vanha_esittely

            # 4. Mittaus veloittaa yhden krediitin ja saa luvan
            tid = app.start_test(vehicle_id=vid, tyyppi="pikatarkastus", mittarilukema=50000, mittaaja="Matti Mittaaja",
                                 lisatiedot="Salainen lisätieto")
            t = app.storage.test(tid)
            assert t["lupa"] and t["lupa_tila"] == "varattu"
            assert api.krediitit({}, {})["saldo"] == 2
            # Perumisaikana reaaliaikainen kunto on piilossa myös mittauksen aikana
            assert api.tila({}, {})["live"].get("kunto_piilotettu")
            assert wait(lambda: not app.recorder.active, 180), "pikatarkastus ei valmistunut"
            assert wait(lambda: app.storage.test(tid)["lupa_tila"] == "rekisteroity", 30), "raportti ei rekisteröitynyt"
            t = app.storage.test(tid)
            y = t["tulos"]["yhteenveto"]
            v = palvelin.get("/api/v1/vahvistus/" + t["lupa"])
            assert v["tila"] == "valmis" and abs(v["kuntoPct"] - round(y["kunto_pct"], 2)) < 0.01, (v, y)
            assert v["tarkiste"] == t["tarkiste"][:16] and v["mittarilukema"] == 50000
            vin = app.decoder.state.vin
            assert v["vin"].startswith(vin[:3]) and v["vin"].endswith(vin[-6:]) and vin not in json.dumps(v)
            assert palvelin.get(f"/api/v1/vahvistus/{t['lupa']}?vin={vin}")["vinTasmaa"] is True
            # Palvelimelle lähtee vain yhteenveto: ei rekisterikilpeä, lisätietoja eikä koko valmistenumeroa.
            # Mittauksen suorittaja näkyy tarkistussivulla (tietosuojaselosteen mukaisesti).
            assert v["suorittaja"] == "Matti Mittaaja", v
            testit = palvelin.get("/api/hallinta/testit?haku=" + t["lupa"], True)["testit"]
            tallennettu = json.dumps(testit)
            for salainen in ("XYZ-999", "Salainen lisätieto", vin):
                assert salainen not in tallennettu, salainen

            # 5. Raportissa on tunnus ja QR-koodi tarkistussivulle
            pdf = report.build(app.storage, tid)
            from pypdf import PdfReader
            teksti = PdfReader(str(pdf)).pages[0].extract_text()
            tunnus = kr.muotoile_tunnus(t["lupa"])
            assert tunnus in teksti and "akveri.fi/v/" in teksti, teksti[:400]

            # 6. Uudelleenlaskenta päivittää rekisteröidyn tuloksen, lupa ei kulu
            api.laske_uudelleen({}, {}, tid)
            assert wait(lambda: palvelin.get("/api/v1/vahvistus/" + t["lupa"]).get("paivitetty"), 20)
            assert api.krediitit({}, {})["saldo"] == 2

            # 7. Keskeytys perumisajan sisällä palauttaa krediitin, eikä raporttia tehdä
            tid2 = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti", mittarilukema=50010)
            assert api.krediitit({}, {})["saldo"] == 1
            r = api.keskeyta({}, {})
            assert r["lupa"] == "peruttu", r
            assert api.krediitit({}, {})["saldo"] == 2
            assert palvelin.get("/api/v1/vahvistus/" + app.storage.test(tid2)["lupa"])["tila"] == "peruttu"
            try:
                report.build(app.storage, tid2)
                raise AssertionError("perutusta mittauksesta tehtiin raportti")
            except ValueError:
                pass

            # 8. Perumisajan jälkeen keskeytys: krediitti ei palaudu automaattisesti, hyvityspyyntö menee hallintaan
            tid3 = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti", mittarilukema=50020)
            app.storage.update_test(tid3, lupa_peruttavissa=time.time() - 1)
            assert not api.tila({}, {})["live"].get("kunto_piilotettu"), "perumisajan jälkeen kunto näkyy mittauksessa"
            r = api.keskeyta({}, {})
            assert r["lupa"] == "hyvitettavissa", r
            assert api.mittaus({}, {}, tid3)["lupa"]["hyvitettavissa"] is True
            api.hyvityspyynto({}, {"syy": "Ohjelma pysähtyi kesken latauksen"}, tid3)
            pyynnot = palvelin.get("/api/hallinta/testit?suodatin=hyvityspyynnot", True)["testit"]
            assert len(pyynnot) == 1 and "Ohjelma pysähtyi" in pyynnot[0]["hyvityspyynto"]["syy"]
            assert "Mittaus keskeytettiin" in pyynnot[0]["hyvityspyynto"]["tiedot"], "tapahtumaloki mukana"
            palvelin.pyynto("POST", f"/api/hallinta/testit/{pyynnot[0]['tunnus']}/hyvita", {"selite": "Hyväksytty"}, True)
            assert api.krediitit({}, {})["saldo"] == 2

            # 9. Ilman verkkoa: mittausta ei voi aloittaa, mutta valmis raportti jää jonoon
            tid4 = app.start_test(vehicle_id=vid, tyyppi="pikatarkastus", mittarilukema=50030)
            os.environ["AKVERI_PALVELU"] = "http://127.0.0.1:9"
            assert wait(lambda: not app.recorder.active, 180)
            assert wait(lambda: any("odottaa" in e["teksti"] for e in app.storage.events(tid4)), 30)
            assert app.storage.test(tid4)["lupa_tila"] == "varattu"
            try:
                app.start_test(vehicle_id=vid, tyyppi="pikatarkastus")
                raise AssertionError("mittaus alkoi ilman yhteyttä palveluun")
            except RuntimeError as e:
                assert "yhteyttä" in str(e), e
            os.environ["AKVERI_PALVELU"] = palvelin.osoite
            assert kr.kasittele_odottavat(app.krediitit, "2.0.0") == 1
            assert app.storage.test(tid4)["lupa_tila"] == "rekisteroity"

            # 10. Mittaustiedosto toiselle laitteelle: lupa ja QR säilyvät, toinen laite ei rekisteröi
            _, data = mittaustiedosto.export(app.storage, tid)
            app.disconnect()
            b = App(Path(kansio) / "b")
            r = mittaustiedosto.import_file(b.storage, data)
            tb = b.storage.test(r["id"])
            assert tb["lupa"] == t["lupa"] and tb["lupa_tila"] == "rekisteroity"
            assert not b.krediitit.odottavat()
            print("OK krediitit ja testiluvat päästä päähän")
        finally:
            os.environ.pop("AKVERI_PALVELU", None)
            palvelin.sulje()


def test_esittelytila_ilman_krediittia():
    """Esittelytila (testitili tai testiversio) ei tarvitse krediittiä. Raporttiin tulee ESIMERKKI-leima."""
    os.environ["AKVERI_PALVELU"] = "http://127.0.0.1:9"
    os.environ["AKVERI_ESITTELY"] = "1"
    try:
        with tempfile.TemporaryDirectory() as kansio:
            from akux.app import App
            from akux.server import Api
            from akux import report
            app = App(kansio)
            app.connect("demo", soc=0.6, accel=40)
            assert wait(lambda: app.decoder.state.brick_count and app.decoder.state.nfp_kwh, 30)
            assert not Api(app).tila({}, {})["live"].get("kunto_piilotettu")
            vid = app.storage.add_vehicle({"vin": app.decoder.state.vin})
            tid = app.start_test(vehicle_id=vid, tyyppi="pikatarkastus")
            assert wait(lambda: not app.recorder.active, 180)
            t = app.storage.test(tid)
            assert t["demo"] == 1 and not t["lupa"]
            from pypdf import PdfReader
            teksti = "".join(p.extract_text() for p in PdfReader(str(report.build(app.storage, tid))).pages[:1])
            assert "Esimerkkiraportti" in teksti, teksti[:300]
            app.disconnect()
            print("OK esittelytila ilman krediittiä")
    finally:
        os.environ.pop("AKVERI_PALVELU", None)


if __name__ == "__main__":
    test_esittelytila_ilman_krediittia()
    test_krediitit()
