"""Tietolähteet: OBDLink-sovitin (STN-piiri) ja esittelytilan simulaattori."""
from __future__ import annotations

import threading
import time
from typing import Callable

from .decoder import KAYTETYT_TUNNISTEET

FrameCallback = Callable[[float, int, bytes], None]


class Source:
    name = "lähde"
    max_gap = 5.0         # suurin hyväksytty aukko virtamittauksessa (s)
    simulated = False

    def __init__(self):
        self.status = "Ei yhteyttä"
        self.error: str | None = None
        self.info: dict = {}
        self._cb: FrameCallback | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, cb: FrameCallback):
        self._cb = cb
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=self.name)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def now(self) -> float:
        return time.time()

    def _run(self):  # pragma: no cover - toteutetaan aliluokissa
        raise NotImplementedError


# ----------------------------------------------------------------------
def list_ports() -> list[dict]:
    try:
        from serial.tools import list_ports as lp
    except ImportError:
        return []
    out = []
    for p in lp.comports():
        desc = p.description or ""
        likely = (p.vid == 0x0403) or "OBDLink" in desc or "FTDI" in (p.manufacturer or "") \
            or "ScanTool" in (p.manufacturer or "")
        out.append({"laite": p.device, "kuvaus": desc, "todennakoinen": likely})
    out.sort(key=lambda x: not x["todennakoinen"])
    return out


class ObdLinkSource(Source):
    """OBDLink EX / SX / MX (STN11xx/STN21xx) USB- tai sarjaliitännällä.

    Sovitin asetetaan kuuntelemaan 11-bittistä CAN-väylää (500 kbit/s)
    ilman automaattista muotoilua. Sovitin ei lähetä autolle mitään.
    """
    name = "OBDLink"
    BAUDS = (115200, 2000000, 500000, 230400, 38400)

    def __init__(self, port: str, baud: int | None = None):
        super().__init__()
        self.port = port
        self.baud = baud
        self.ser = None
        self.stn = False

    # -- matalan tason apufunktiot --------------------------------------
    def _cmd(self, cmd: str, timeout: float = 1.5) -> str:
        ser = self.ser
        ser.reset_input_buffer()
        ser.write((cmd + "\r").encode("ascii"))
        buf = b""
        end = time.time() + timeout
        while time.time() < end:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if b">" in buf:
                    break
        return buf.decode("ascii", "ignore").replace(">", "").strip()

    def _open(self):
        import serial  # pyserial
        bauds = [self.baud] if self.baud else list(self.BAUDS)
        last = None
        for b in bauds:
            try:
                self.ser = serial.Serial(self.port, b, timeout=0.2)
                self.ser.write(b"\r")
                time.sleep(0.1)
                resp = self._cmd("ATI", 1.0)
                if "ELM" in resp or "STN" in resp or "OBD" in resp:
                    self.baud = b
                    return
                self.ser.close()
            except Exception as e:  # noqa: BLE001
                last = e
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:  # noqa: BLE001
                    pass
        raise RuntimeError(f"Sovitin ei vastaa portissa {self.port}" + (f" ({last})" if last else ""))

    def _init_adapter(self):
        self._cmd("ATZ", 3.0)
        for c in ("ATE0", "ATL0", "ATS0", "ATH1", "ATD0", "ATSP6", "ATCAF0", "ATAL"):
            self._cmd(c)
        ident = self._cmd("STI")
        self.stn = "STN" in ident or "OBDLink" in ident
        self.info = {"sovitin": ident or self._cmd("ATI"), "portti": self.port, "nopeus": self.baud,
                     "suodatus": self.stn}
        if self.stn:
            self._cmd("STFAC")
            for cid in KAYTETYT_TUNNISTEET:
                self._cmd(f"STFAP {cid:03X},7FF")

    def _start_monitor(self):
        self.ser.reset_input_buffer()
        self.ser.write(b"STMA\r" if self.stn else b"ATMA\r")

    def _parse(self, line: str):
        line = line.strip().replace(" ", "")
        if len(line) < 5 or len(line) > 3 + 16 or len(line) % 2 == 0:
            return None
        try:
            cid = int(line[:3], 16)
            data = bytes.fromhex(line[3:])
        except ValueError:
            return None
        return cid, data

    def _run(self):
        while not self._stop.is_set():
            try:
                self.status = "Yhdistetään sovittimeen"
                self._open()
                self._init_adapter()
                self.status = "Kuunnellaan väylää"
                self.error = None
                self._start_monitor()
                buf = b""
                last_frame = time.time()
                while not self._stop.is_set():
                    chunk = self.ser.read(self.ser.in_waiting or 1)
                    now = time.time()
                    if chunk:
                        buf += chunk
                        *lines, buf = buf.split(b"\r")
                        for raw in lines:
                            txt = raw.decode("ascii", "ignore").strip().lstrip(">")
                            if not txt:
                                continue
                            if "BUFFER FULL" in txt or "STOPPED" in txt:
                                self._start_monitor()
                                continue
                            if "NO DATA" in txt or "CAN ERROR" in txt or "?" == txt:
                                self.status = "Väylä hiljaa – onko auto hereillä?"
                                self._start_monitor()
                                continue
                            fr = self._parse(txt)
                            if fr and self._cb:
                                last_frame = now
                                self.status = "Kuunnellaan väylää"
                                self._cb(now, fr[0], fr[1])
                    if now - last_frame > 5:
                        self.status = "Väylä hiljaa – onko auto hereillä?"
                        last_frame = now
                        self._start_monitor()
            except Exception as e:  # noqa: BLE001
                self.error = str(e)
                self.status = "Yhteys katkesi, yritetään uudelleen"
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:  # noqa: BLE001
                    pass
                self._stop.wait(3)
        try:
            if self.ser:
                self.ser.write(b"\r")
                self.ser.close()
        except Exception:  # noqa: BLE001
            pass
        self.status = "Ei yhteyttä"


class ReplaySource(Source):
    """Toistaa tallennetun raakadatan (tiedosto: aika;tunniste;data)."""
    name = "Tallenne"
    max_gap = 30.0

    def __init__(self, path: str, speed: float = 0.0):
        super().__init__()
        self.path = path
        self.speed = speed

    def _run(self):
        import gzip
        opener = gzip.open if str(self.path).endswith(".gz") else open
        self.status = "Toistetaan tallennetta"
        first = None
        start = time.time()
        with opener(self.path, "rt", encoding="ascii") as f:
            for line in f:
                if self._stop.is_set():
                    break
                try:
                    t_s, cid_s, data_s = line.strip().split(";")
                    t = float(t_s)
                    cid = int(cid_s, 16)
                    data = bytes.fromhex(data_s)
                except ValueError:
                    continue
                if first is None:
                    first = t
                if self.speed > 0:
                    target = start + (t - first) / self.speed
                    delay = target - time.time()
                    if delay > 0:
                        time.sleep(delay)
                if self._cb:
                    self._cb(t, cid, data)
        self.status = "Tallenne toistettu"
