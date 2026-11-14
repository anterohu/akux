"""Tietolähteet: OBDLink-sovitin (STN-piiri) ja esittelytilan simulaattori."""
from __future__ import annotations

import re
import threading
import time
from typing import Callable

from .decoder import KAYTETYT_TUNNISTEET

FrameCallback = Callable[[float, int, bytes], None]

# Android-sovellus korvaa sarjaportin omalla USB-toteutuksellaan (ks. android.py)
SERIAL_FACTORY = None
PORT_LISTER = None


class UnsupportedAdapter(Exception):
    """Sovitin vastaa, mutta se ei ole OBDLink (STN-piiri)."""


class AdapterUnavailable(Exception):
    """Sovitin ei ole käytettävissä (puuttuu tai käyttölupa odottaa). Viesti näytetään käyttäjälle sellaisenaan."""


class Source:
    name = "lähde"
    max_gap = 5.0         # suurin hyväksytty aukko virtamittauksessa (s)
    simulated = False
    scan_supported = True

    def __init__(self):
        self.status = "Ei yhteyttä"
        self.error: str | None = None
        self.info: dict = {}
        self._cb: FrameCallback | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._scan_req = None
        self.scanning_until = None

    def request_scan(self, seconds: float):
        """Väylän kartoitus: kuunnellaan hetki ilman suodatusta, jotta nähdään kaikki viestit."""
        self._scan_req = seconds

    @property
    def scanning(self) -> bool:
        return bool(self._scan_req or (self.scanning_until and self.now() < self.scanning_until))

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
BT_NAME_LOOKUP = None   # testit voivat korvata nimen haun


def bt_device_name(mac: str) -> str | None:
    """Paritetun Bluetooth-laitteen nimi Windowsin rekisteristä. None, jos nimeä ei saada."""
    if BT_NAME_LOOKUP:
        return BT_NAME_LOOKUP(mac)
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             rf"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices\{mac.lower()}")
        raw, _ = winreg.QueryValueEx(key, "Name")
        winreg.CloseKey(key)
        if isinstance(raw, bytes):
            raw = raw.split(b"\x00", 1)[0].decode("utf-8", "ignore")
        return str(raw).strip() or None
    except Exception:  # noqa: BLE001
        return None


def list_ports() -> list[dict]:
    if PORT_LISTER:
        return PORT_LISTER()
    try:
        from serial.tools import list_ports as lp
    except ImportError:
        return []
    out = []
    for p in lp.comports():
        desc = p.description or ""
        hwid = (p.hwid or "").upper()
        if "BTHENUM" in hwid:
            # Windows luo paritetulle Bluetooth-laitteelle kaksi porttia. Lähtevän portin tunnisteessa on
            # laitteen osoite, saapuvan portin tunnisteessa nollat; vain lähtevä toimii. Listalle otetaan
            # vain OBDLink-sovittimet; laitteen nimi luetaan Windowsin Bluetooth-rekisteristä.
            m = re.search(r"&([0-9A-F]{12})_", hwid)
            if not (m and m.group(1) != "0" * 12):
                continue
            name = bt_device_name(m.group(1))
            if name is not None and "OBDLINK" not in name.upper():
                continue
            out.append({"laite": p.device, "todennakoinen": True,
                        "kuvaus": f"Bluetooth: {name}" if name else "Bluetooth"})
            continue
        likely = (p.vid == 0x0403) or "OBDLink" in desc or "FTDI" in (p.manufacturer or "") \
            or "ScanTool" in (p.manufacturer or "")
        out.append({"laite": p.device, "kuvaus": desc, "todennakoinen": likely})
    out.sort(key=lambda x: not x["todennakoinen"])
    return out


class ObdLinkSource(Source):
    """OBDLink EX / SX (USB) tai MX+ / LX (Bluetooth), STN11xx/STN21xx-piiri.

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
        if SERIAL_FACTORY:
            factory = SERIAL_FACTORY
        else:
            import serial  # pyserial
            factory = serial.Serial
        bauds = [self.baud] if self.baud else list(self.BAUDS)
        last = None
        for b in bauds:
            try:
                self.ser = factory(self.port, b, timeout=0.2)
                self.ser.write(b"\r")
                time.sleep(0.1)
                resp = self._cmd("ATI", 1.0)
                if "ELM" in resp or "STN" in resp or "OBD" in resp:
                    self.baud = b
                    return
                self.ser.close()
            except AdapterUnavailable:
                raise
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
        if not self.stn:
            # Teslan väylällä kulkee tuhansia viestejä sekunnissa. Ilman OBDLinkin suodatusta tavallinen
            # ELM327-sovitin ei pysy perässä, ja mittaus olisi epäluotettava.
            raise UnsupportedAdapter(
                f"Sovitin ({self._cmd('ATI') or 'tuntematon'}) ei ole OBDLink. AKVERI toimii OBDLink-sovittimilla: "
                "EX ja SX (USB) sekä MX+ ja LX (Bluetooth).")
        self.info = {"sovitin": ident or self._cmd("ATI"), "portti": self.port, "nopeus": self.baud,
                     "suodatus": self.stn}
        self._apply_filters(True)

    def _apply_filters(self, on: bool):
        if not self.stn:
            return
        self._cmd("STFAC")
        if on:
            for cid in KAYTETYT_TUNNISTEET:
                self._cmd(f"STFAP {cid:03X},7FF")

    def _stop_monitor(self):
        self.ser.write(b"\r")
        time.sleep(0.3)
        self.ser.reset_input_buffer()

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
                    if self._scan_req:
                        secs, self._scan_req = self._scan_req, None
                        self._stop_monitor()
                        self._apply_filters(False)
                        self.scanning_until = time.time() + secs
                        self._start_monitor()
                    elif self.scanning_until and time.time() > self.scanning_until:
                        self.scanning_until = None
                        self._stop_monitor()
                        self._apply_filters(True)
                        self._start_monitor()
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
            except UnsupportedAdapter as e:
                self.error = str(e)
                self.status = "Sovitinta ei tueta"
                try:
                    self.ser.close()
                except Exception:  # noqa: BLE001
                    pass
                self._stop.wait(3600)
                continue
            except AdapterUnavailable as e:
                self.error = str(e)
                self.status = "Odotetaan sovitinta"
                self._stop.wait(2)
                continue
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


# ----------------------------------------------------------------------
_ISOTP_LINE = re.compile(r"^([0-9A-F]):")


def parse_isotp(text: str) -> bytes | None:
    """ELM/STN-sovittimen vastaus (otsikot pois, automaattinen muotoilu päällä) tavuiksi.

    Monikehyksinen vastaus tulee muodossa "03E" + "0:..." + "1:...", yksikehyksinen yhtenä rivinä.
    """
    total = None
    parts = []
    for raw in text.replace("\n", "\r").split("\r"):
        line = raw.strip().replace(" ", "").upper()
        if not line or line.startswith("SEARCHING") or line == "OK":
            continue
        if any(x in line for x in ("NODATA", "ERROR", "STOPPED", "UNABLE", "?")):
            return None
        m = _ISOTP_LINE.match(line)
        if m:
            parts.append(line[2:])
        elif len(line) == 3 and total is None and not parts and re.fullmatch(r"[0-9A-F]{3}", line):
            total = int(line, 16)
        elif re.fullmatch(r"[0-9A-F]+", line):
            parts.append(line)
    hexs = "".join(parts)
    if not hexs or len(hexs) % 2:
        return None
    data = bytes.fromhex(hexs)
    return data[:total] if total else data


class PolledSource(ObdLinkSource):
    """Kyselyihin perustuva lukutapa (Hyundai, Kia): sovitin kysyy tiedot akunhallinnalta vuorotellen.

    Vastaukset välitetään tulkitsijalle virtuaalitunnisteella. Kyselyt ovat lukukyselyitä (palvelut 21, 22 ja
    OBD-standardin 01 ja 09), jotka eivät muuta auton asetuksia.
    """
    name = "OBDLink"
    scan_supported = False

    def __init__(self, port: str, baud: int | None = None, *, loop: list, rare: list, rare_every: float = 60.0,
                 rx: dict | None = None, protocol: str = "6", fc: dict | None = None):
        super().__init__(port, baud)
        self.loop, self.rare, self.rare_every = loop, rare, rare_every
        self.rx = rx or {}                  # kyselyosoite -> vastausosoite (oletus: osoite + 8, None: mikä tahansa)
        self.protocol = protocol            # 6 = 11-bittiset tunnisteet, 7 = 29-bittiset (MEB)
        self.fc = fc or {}                  # yleiskysely, jonka vastauksen vuonohjaus menee tietylle laitteelle (MG4)
        self.max_gap = 8.0
        self._hdr = None

    def _init_adapter(self):
        self._cmd("ATZ", 3.0)
        for c in ("ATE0", "ATL0", "ATS0", "ATH0", "ATD0", f"ATSP{self.protocol}", "ATCAF1", "ATAL", "ATST32"):
            self._cmd(c)
        ident = self._cmd("STI")
        self.stn = "STN" in ident or "OBDLink" in ident
        if not self.stn:
            raise UnsupportedAdapter(
                f"Sovitin ({self._cmd('ATI') or 'tuntematon'}) ei ole OBDLink. AKVERI toimii OBDLink-sovittimilla: "
                "EX ja SX (USB) sekä MX+ ja LX (Bluetooth).")
        self.info = {"sovitin": ident or self._cmd("ATI"), "portti": self.port, "nopeus": self.baud,
                     "lukutapa": "kyselyt"}
        self._hdr = None

    def request(self, header: str, cmd: str) -> bytes | None:
        if header != self._hdr:
            self._cmd(f"ATSH{header}")
            if (header == "7DF" and header not in self.rx) or (header in self.rx and self.rx[header] is None):
                self._cmd("ATAR")           # yleiskysely: vastaus mistä tahansa ohjainlaitteesta
                self._cmd("ATFCSM0")        # sovittimen oma vuonohjaus
            else:
                rx = self.rx.get(header) or f"{int(header, 16) + 8:03X}"
                self._cmd(f"ATCRA{rx}")
                # Monikehyksisen vastauksen vuonohjaus lähetetään samalle ohjainlaitteelle (Nissan: 79B -> 7BB)
                self._cmd(f"ATFCSH{self.fc.get(header, header)}")
                self._cmd("ATFCSD300000")
                self._cmd("ATFCSM1")
            self._hdr = header
        data = parse_isotp(self._cmd(cmd, 2.0))
        if not data:
            return None
        sid = int(cmd[:2], 16)
        if data[0] != sid + 0x40:
            return None
        echo = 2 if sid in (0x01, 0x21, 0x09) else 3
        if bytes.fromhex(cmd[2:]) != data[1:1 + len(cmd[2:]) // 2]:
            return None
        return data[echo:]

    def _run(self):
        while not self._stop.is_set():
            try:
                self.status = "Yhdistetään sovittimeen"
                self._open()
                self._init_adapter()
                self.error = None
                last_ok = time.time()
                next_rare = 0.0
                while not self._stop.is_set():
                    jobs = list(self.loop)
                    if time.time() >= next_rare:
                        jobs = list(self.rare) + jobs
                        next_rare = time.time() + self.rare_every
                    for header, cmd, cid in jobs:
                        if self._stop.is_set():
                            break
                        data = self.request(header, cmd)
                        now = time.time()
                        if data is not None and self._cb:
                            last_ok = now
                            self.status = "Luetaan akunhallintaa"
                            self._cb(now, cid, data)
                    if time.time() - last_ok > 5:
                        self.status = "Auto ei vastaa – onko auto päällä tai latauksessa?"
                        self._stop.wait(2)
            except UnsupportedAdapter as e:
                self.error = str(e)
                self.status = "Sovitinta ei tueta"
                try:
                    self.ser.close()
                except Exception:  # noqa: BLE001
                    pass
                self._stop.wait(3600)
            except AdapterUnavailable as e:
                self.error = str(e)
                self.status = "Odotetaan sovitinta"
                self._stop.wait(2)
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
                self.ser.close()
        except Exception:  # noqa: BLE001
            pass
        self.status = "Ei yhteyttä"
