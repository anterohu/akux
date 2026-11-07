"""Sovelluksen ydin: yhdistää tietolähteen, purkajan, tallennuksen ja mittaukset."""
from __future__ import annotations

import sys
import threading

import time

from .decoder import TeslaDecoder
from .notify import Notifier
from .recorder import Recorder
from .sources import ObdLinkSource
from .simulator import BatterySimulator
from .storage import Storage


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
        self.storage = Storage(data_dir)
        self.decoder = TeslaDecoder()
        self.recorder = Recorder(self)
        self.source = None
        self.lock = threading.RLock()
        self.notifier = Notifier(lambda: self.storage.settings())
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
                car = ESITTELYAUTOT.get(opts.pop("auto", None) or "m3-lr", ESITTELYAUTOT["m3-lr"])
                src = BatterySimulator(**{**car["opts"], **opts})
                src.car_name = car["nimi"]
            else:
                if not port:
                    raise ValueError("Valitse sovittimen portti.")
                src = ObdLinkSource(port, baud or None)
            self.source = src
            src.start(self._on_frame)
            return src

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
        tid = self.recorder.start(**kw)
        _keep_awake(True)
        return tid

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
        """Kutsutaan säännöllisesti: tallentaa puskurit ja vapauttaa lepotilan eston."""
        if self.recorder.active:
            self.recorder.flush()
            if (self.source and not self.source.simulated and self.last_frame_wall
                    and time.time() - self.last_frame_wall > 300 and not self._outage_notified):
                self._outage_notified = True
                self.notify("ongelmat", "Yhteys autoon katkesi",
                            "Autosta ei ole saatu tietoja viiteen minuuttiin. Tarkista sovitin ja että auto on hereillä.")
        else:
            _keep_awake(False)
