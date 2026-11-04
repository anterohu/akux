"""Sovelluksen ydin: yhdistää tietolähteen, purkajan, tallennuksen ja mittaukset."""
from __future__ import annotations

import sys
import threading

import time

from .decoder import TeslaDecoder
from .notify import Notifier
from .recorder import Recorder
from .sources import ObdLinkSource, ReplaySource
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
        for t in self.storage.tests():
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
            if kind == "demo":
                src = BatterySimulator(**opts)
            elif kind == "tallenne":
                src = ReplaySource(port, speed=opts.get("speed", 0))
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
                self.recorder.cancel()
            if self.source:
                self.source.stop()
            self.source = None
            _keep_awake(False)

    def start_test(self, **kw):
        tid = self.recorder.start(**kw)
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
