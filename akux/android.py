"""Android-käynnistys. Sovellus kutsuu start()-funktiota taustapalvelusta.

USB-yhteys OBDLink-sovittimeen kulkee Androidin USB-rajapinnan kautta
(UsbBridge-luokka sovelluksessa). Tämä moduuli tarjoaa sille saman rajapinnan
kuin pyserial-kirjasto, joten mittauskoodi on sama kuin tietokoneella.
"""
from __future__ import annotations

import os
import threading
import time
import traceback

_bridge = None
PLATFORM = "android"


class AndroidSerial:
    def __init__(self, port, baud, timeout=0.2):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._buf = bytearray()
        try:
            _bridge.open(port, int(baud))
        except Exception as e:  # noqa: BLE001
            from .sources import AdapterUnavailable
            # Java-poikkeuksen viestistä poistetaan luokan nimi
            msg = str(e).split("IOException: ", 1)[-1]
            raise AdapterUnavailable(msg) from None

    def _pull(self, ms):
        data = _bridge.read(4096, int(ms))
        if data is not None and len(data):
            self._buf += bytes(data)

    @property
    def in_waiting(self):
        if not self._buf:
            self._pull(5)
        return len(self._buf)

    def read(self, n=1):
        if not self._buf:
            self._pull(max(1, int(self.timeout * 1000)))
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def write(self, data):
        _bridge.write(bytes(data))

    def reset_input_buffer(self):
        self._buf.clear()
        try:
            for _ in range(5):
                if not len(_bridge.read(4096, 1)):
                    break
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        try:
            _bridge.close()
        except Exception:  # noqa: BLE001
            pass


def list_ports():
    try:
        devs = list(_bridge.listDevices())
    except Exception:  # noqa: BLE001
        return []
    out = []
    for d in map(str, devs):
        if d.startswith("Bluetooth: "):
            out.append({"laite": d, "kuvaus": "Bluetooth", "todennakoinen": "OBDLINK" in d.upper()})
        else:
            out.append({"laite": d, "kuvaus": "USB-sovitin", "todennakoinen": True})
    out.sort(key=lambda x: not x["todennakoinen"])
    return out


def _run(port):
    from .server import serve
    try:
        while True:
            action = serve(host=None, port=port, open_browser=False)
            if action != "uudelleen":
                break
            time.sleep(0.5)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    finally:
        try:
            _bridge.onStopped()
        except Exception:  # noqa: BLE001
            pass


def start(data_dir: str, bridge, port: int = 8765):
    global _bridge
    _bridge = bridge
    os.environ["AKUX_DATA"] = os.path.join(data_dir, "akux")
    os.environ["AKUX_ALUSTA"] = PLATFORM
    os.environ.setdefault("MPLCONFIGDIR", os.path.join(data_dir, "matplotlib"))
    os.environ.setdefault("HOME", data_dir)
    from . import sources
    sources.SERIAL_FACTORY = AndroidSerial
    sources.PORT_LISTER = list_ports
    from . import mittaustiedosto

    def save(name, mime, data):
        return _bridge.saveToDownloads(name, mime, bytes(data))
    mittaustiedosto.SAVE_HOOK = save
    t = threading.Thread(target=_run, args=(port,), daemon=True, name="akux-palvelin")
    t.start()
    return True
