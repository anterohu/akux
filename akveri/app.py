"""Sovelluksen ydin: yhdistää tietolähteen, purkajan, tallennuksen ja mittaukset."""
from __future__ import annotations

import sys
import threading

import time

from .decoder import TeslaDecoder
from .notify import Notifier
from .recorder import Recorder
from . import profiles
from .sources import ObdLinkSource, PolledSource
from .simulator import BatterySimulator
from .storage import Storage
from . import krediitit as krediittimoduuli


def _keep_awake(on: bool):
    """Estää Windowsin lepotilan mittauksen aikana."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except Exception:  # noqa: BLE001
        pass


class App:
    def __init__(self, data_dir=None):
        try:
            from . import mittaustiedosto
            mittaustiedosto.default_folder()   # siirtää aiemman nimen mittauskansion ennen polkujen tarkistusta
        except Exception:  # noqa: BLE001
            pass
        self.storage = Storage(data_dir)
        self.krediitit = krediittimoduuli.Krediitit(self.storage)
        self._seuraava_rekisterointi = 0.0
        self.decoder = TeslaDecoder()
        self.recorder = Recorder(self)
        self.source = None
        self.lock = threading.RLock()
        self.notifier = Notifier(lambda: self.storage.settings())
        from . import kielet
        kielet.aseta(self.storage.settings().get("kieli"))
        self.last_frame_wall = 0.0
        self._outage_notified = False
        self._mark_interrupted()

    @property
    def settings(self) -> dict:
        return self.storage.settings()

    def _mark_interrupted(self):
        from .recorder import JATKETTAVAT, JATKETTAVAT_VAIHEET
        for t in self.storage.tests():
            state = (t.get("tulos") or {}).get("keskeneräinen") or {}
            if t["tila"] == "käynnissä" and t["tyyppi"] in JATKETTAVAT and state.get("vaihe") in JATKETTAVAT_VAIHEET:
                self.storage.update_test(t["id"], tila="kesken")
                self.storage.add_event(t["id"], time.time(),
                                       "Ohjelma suljettiin kesken mittauksen. Mittausta voi jatkaa.")
                continue
            if t["tila"] == "käynnissä":
                self.storage.update_test(t["id"], tila="keskeytynyt")
                self.storage.add_event(t["id"], t["aloitettu"],
                                       "Ohjelma suljettiin kesken mittauksen. Mittaus merkittiin keskeytyneeksi.")

    # ------------------------------------------------------------------
    def notify(self, laji, title, message):
        name = None
        try:
            if self.recorder.active:
                v = self.storage.vehicle(self.recorder.vehicle_id) or {}
                name = v.get("rekisteri") or v.get("nimi")
        except Exception:  # noqa: BLE001
            pass
        self.notifier.send(laji, f"{title} – {name}" if name else title, message)

    def _on_frame(self, t, cid, data):
        self.last_frame_wall = time.time()
        self._outage_notified = False
        self.decoder.feed(t, cid, data)
        if self.recorder.active:
            self.recorder.on_frame(t, cid, data)

    def connect(self, kind: str, port: str | None = None, baud: int | None = None, **opts):
        with self.lock:
            self.disconnect()
            self.decoder.reset()
            if kind == "demo" and opts.get("sim") is not None:
                src = opts.pop("sim")          # testit: sama simuloitu auto uudelleen
            elif kind == "demo":
                from .simulator import ESITTELYAUTOT
                from . import polled
                car = ESITTELYAUTOT.get(opts.pop("auto", None) or "m3-lr", ESITTELYAUTOT["m3-lr"])
                model = profiles.get(car.get("malli_id"))
                pm = polled.for_model(model)
                if pm:
                    src = pm.simulator(model, **{**car["opts"], **opts})
                else:
                    src = BatterySimulator(**{**car["opts"], **opts})
                src.car_name = car["nimi"]
                src.malli_id = car.get("malli_id")
            else:
                if not port:
                    raise ValueError("Valitse sovittimen portti.")
                from . import polled
                model = profiles.get(opts.get("malli_id"))
                pm = polled.for_model(model)
                if pm:
                    loop, rare = pm.requests_for(model)
                    vaihto = pm.vaihtoehto_for(model) if hasattr(pm, "vaihtoehto_for") else None
                    src = PolledSource(port, baud or None, loop=loop, rare=rare, rx=pm.RX,
                                       protocol=getattr(pm, "PROTOKOLLA", "6"), fc=getattr(pm, "FC", None),
                                       vaihtoehto=vaihto)
                else:
                    src = ObdLinkSource(port, baud or None)
                src.malli_id = opts.get("malli_id")
            self._configure_platform(getattr(src, "malli_id", None))
            self.source = src
            src.start(self._on_frame)
            return src

    def _configure_platform(self, malli_id):
        """Kyselyihin perustuvan auton (Hyundai, Kia) tiedot asetetaan tulkitsijalle yhdistettäessä."""
        from . import polled
        model = profiles.get(malli_id)
        pm = polled.for_model(model)
        if pm:
            self.decoder.configure(pm.PLATFORM, **pm.decoder_opts(model))

    def disconnect(self):
        with self.lock:
            if self.recorder.active:
                if self.recorder.can_pause():
                    self.recorder.pause("Yhteys autoon katkaistiin")
                else:
                    self.recorder.cancel()
            if self.source:
                self.source.stop()
            self.source = None
            _keep_awake(False)

    def start_test(self, **kw):
        """Aloittaa mittauksen. Oikeasta autosta mittaus vaatii testiluvan (mittaustyypin hinta krediitteinä), esittelytilassa ei."""
        if self.source and self.source.simulated:
            tid = self.recorder.start(**kw)
            self.storage.update_test(tid, demo=1)
            _keep_awake(True)
            return tid
        from . import VERSIO
        from .server import platform_name
        try:
            lupa = self.krediitit.varaa(VERSIO, platform_name(), str(kw.get("tyyppi") or ""))
        except krediittimoduuli.PalveluVirhe as e:
            raise RuntimeError(str(e)) from None
        try:
            tid = self.recorder.start(**kw)
        except Exception:
            # Mittaus ei alkanut: lupa perutaan heti, jolloin krediitti palautuu.
            try:
                self.krediitit.peru(lupa["tunnus"], "Mittaus ei alkanut")
            except krediittimoduuli.PalveluVirhe:
                pass
            raise
        self.krediitit.kiinnita(tid, lupa)
        self.storage.add_event(tid, time.time(), f"Testilupa {lupa.get('tunnusNaytto') or lupa['tunnus']}" + (
            " (testitili: ei kuluta krediittiä, raportti merkitään testimittaukseksi)" if lupa.get("testi") else f" (krediittejä jäljellä {lupa.get('saldo')})"))
        _keep_awake(True)
        return tid

    def live_kunto_sallittu(self) -> bool:
        src = self.source
        t = self.storage.test(self.recorder.test_id) if self.recorder.active and self.recorder.test_id else None
        return krediittimoduuli.live_kunto_sallittu(t, bool(src and src.simulated))

    def peru_lupa(self, tid: int, syy: str) -> str:
        """Keskeytetyn mittauksen lupa perutaan, jos se on vielä mahdollista (krediitti palautuu)."""
        try:
            tila = self.krediitit.peru_mittauksen_lupa(tid, syy)
        except Exception:  # noqa: BLE001
            return ""
        if tila == "peruttu":
            self.storage.add_event(tid, time.time(), "Testilupa peruttiin, krediitit palautuivat tilille.")
        elif tila == "peru_odottaa":
            self.storage.add_event(tid, time.time(), "Testiluvan peruminen lähetetään, kun verkkoyhteys palaa.")
        elif tila == "hyvitettavissa":
            self.storage.add_event(tid, time.time(), "Perumisaika on kulunut. Jos mittaus keskeytyi AKVERIsta johtuvasta syystä, lähetä hyvityspyyntö.")
        return tila

    def mittaus_valmis(self, tid: int, result: dict):
        """Kutsutaan, kun mittaus on valmis ja analysoitu. Luvallisen mittauksen rekisteröinti vaatii verkkoa, joten se
        tehdään taustalla. Esittelytilan mittaus käsitellään heti."""
        if krediittimoduuli.luvan_tila(self.storage.test(tid) or {}) == "varattu":
            threading.Thread(target=self._jalkikasittely, args=(tid, result), name="akveri-valmis", daemon=True).start()
        else:
            self._jalkikasittely(tid, result)

    def _jalkikasittely(self, tid: int, result: dict):
        from . import VERSIO
        y = (result or {}).get("yhteenveto") or {}
        if y.get("kunto_pct") is not None:
            kwh = y.get("kapasiteetti_kwh")
            txt = f"Akun kunto {y['kunto_pct']:.1f} %".replace(".", ",") + \
                  (f", kapasiteetti {kwh:.1f} kWh".replace(".", ",") if kwh else "") + ". Raportti on valmis."
        else:
            txt = "Mittaus on valmis. Avaa tulos ohjelmasta."
        t = self.storage.test(tid) or {}
        if krediittimoduuli.luvan_tila(t) == "varattu":
            from .analysis import uskottavuus  # noqa: PLC0415
            syyt = uskottavuus(result or t.get("tulos"))
            if syyt:
                tila = self.krediitit.hylkaa_epauskottava(tid, syyt)
                self.notify("ongelmat", "Tulosta ei voitu varmistaa",
                            " ".join(syyt) + (" Krediitit palautuivat tilille." if tila == "peruttu" else
                                              " Krediitit palautetaan, kun hyvitys on käsitelty."))
                return
            try:
                self.krediitit.rekisteroi(tid, VERSIO)
                self.storage.add_event(tid, time.time(), "Raportti rekisteröity akveri.fi-palveluun.")
            except krediittimoduuli.PalveluVirhe as e:
                self.storage.add_event(tid, time.time(), f"Raportin rekisteröinti odottaa: {e}")
                txt += " Raportti rekisteröidään tarkistettavaksi, kun verkkoyhteys on käytettävissä."
        if not krediittimoduuli.tulos_naytettavissa(self.storage.test(tid) or {}):
            # Perumisaikana tulosta ei näytetä eikä tallenneta: ilmoitus ja tiedostot tehdään rekisteröinnin jälkeen.
            self.notify("valmis", "Mittaus valmis", "Mittaus on valmis. Tulos näytetään, kun raportti on rekisteröity "
                        "akveri.fi-palveluun. Tarkista verkkoyhteys.")
            return
        self._valmis_ilmoitus_ja_tallennus(tid, txt)

    def _valmis_ilmoitus_ja_tallennus(self, tid: int, txt: str):
        self.notify("valmis", "Mittaus valmis", txt)
        if self.settings.get("mittaus_tallennus", True):
            try:
                from . import mittaustiedosto
                paths = mittaustiedosto.save_to_folder(self.storage, tid)
                if paths:
                    self.storage.add_event(tid, time.time(), f"Mittaustiedosto ja raportti tallennettu: {paths[0].parent}")
            except Exception as e:  # noqa: BLE001
                self.storage.add_event(tid, time.time(), f"Mittaustiedoston tallennus epäonnistui: {e}")

    def _myohassa_rekisteroity(self, tid: int):
        """Verkkoyhteyden palattua rekisteröity raportti: nyt tulos ilmoitetaan ja tiedostot tallennetaan."""
        self.storage.add_event(tid, time.time(), "Raportti rekisteröity akveri.fi-palveluun.")
        t = self.storage.test(tid) or {}
        y = (t.get("tulos") or {}).get("yhteenveto") or {}
        if y.get("kunto_pct") is not None:
            kwh = y.get("kapasiteetti_kwh")
            txt = f"Akun kunto {y['kunto_pct']:.1f} %".replace(".", ",") + \
                (f", kapasiteetti {kwh:.1f} kWh".replace(".", ",") if kwh else "") + ". Raportti on valmis."
        else:
            txt = "Mittaus on valmis. Avaa tulos ohjelmasta."
        self._valmis_ilmoitus_ja_tallennus(tid, txt)

    def _rekisteroi_odottavat(self):
        from . import VERSIO
        try:
            krediittimoduuli.kasittele_odottavat(self.krediitit, VERSIO, self._myohassa_rekisteroity)
        except Exception:  # noqa: BLE001
            pass

    def resume_test(self, tid: int):
        t = self.storage.test(tid) or {}
        v = self.storage.vehicle(t.get("vehicle_id")) or {}
        live = self.decoder.state.vin
        if v.get("vin") and live and v["vin"] != live:
            raise ValueError("Kytketty auto ei ole sama kuin mittauksen auto.")
        self.recorder.resume(tid)
        _keep_awake(True)
        return tid

    def tick(self):
        """Kutsutaan säännöllisesti: tallentaa puskurit, vapauttaa lepotilan eston ja rekisteröi odottavat raportit."""
        if time.time() >= self._seuraava_rekisterointi:
            self._seuraava_rekisterointi = time.time() + 120
            if self.krediitit.odottavat():
                threading.Thread(target=self._rekisteroi_odottavat, name="akveri-rekisterointi", daemon=True).start()
        if self.recorder.active:
            self.recorder.flush()
            if (self.source and not self.source.simulated and self.last_frame_wall
                    and time.time() - self.last_frame_wall > 300 and not self._outage_notified):
                self._outage_notified = True
                self.notify("ongelmat", "Yhteys autoon katkesi",
                            "Autosta ei ole saatu tietoja viiteen minuuttiin. Tarkista sovitin ja että auto on hereillä.")
        else:
            _keep_awake(False)
