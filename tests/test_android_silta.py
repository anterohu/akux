"""Android-sovelluksen Python-puoli: USB-silta, palvelimen käynnistys ja sovittimen kautta mittaus.

Testi korvaa Androidin UsbBridge-luokan keinotekoisella sillalla, joka käyttäytyy kuten
OBDLink EX Androidin USB-rajapinnan takana.
"""
import json
import socket
import os
import sys
import tempfile as _tf
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AKUX_MITTAUSKANSIO", _tf.mkdtemp(prefix="akux-testi-"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_obdlink import FakeSerial  # noqa: E402


class FakeBridge:
    """Sama rajapinta kuin Android-sovelluksen UsbBridge.kt."""

    def __init__(self):
        self.dev = None
        self.stopped = False
        self.asked_at = None

    def listDevices(self):
        return ["FT231X USB UART 0403:6015"]

    def open(self, name, baud):
        # Android kysyy luvan, ja käyttäjä hyväksyy sen parin sekunnin kuluttua
        if self.asked_at is None:
            self.asked_at = time.time()
        if time.time() - self.asked_at < 2.5:
            raise IOError("java.io.IOException: Salli Akuxille pääsy sovittimeen puhelimen kysymässä ikkunassa.")
        self.dev = FakeSerial(name, baud)

    def write(self, data):
        self.dev.write(bytes(data))

    def read(self, max_len, timeout_ms):
        if self.dev is None:
            raise IOError("Sovitin ei ole yhteydessä.")
        self.dev._pump()
        out = self.dev.read(max_len)
        if not out:
            time.sleep(timeout_ms / 1000)
        return out

    def close(self):
        self.dev = None

    def onStopped(self):
        self.stopped = True


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def call(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def test_android_silta():
    from akux import android
    with tempfile.TemporaryDirectory() as tmp:
        bridge = FakeBridge()
        port = free_port()
        android.start(tmp, bridge, port=port)
        base = f"http://127.0.0.1:{port}"
        end = time.time() + 20
        while time.time() < end:
            try:
                t = call(base, "/api/tietoja")
                break
            except OSError:
                time.sleep(0.2)
        assert t["alusta"] == "android"
        assert t["datakansio"].startswith(tmp)
        ports = call(base, "/api/portit")
        assert ports["pyserial"] and ports["portit"][0]["laite"].endswith("0403:6015")
        call(base, "/api/yhdista", {"tyyppi": "obdlink", "portti": ports["portit"][0]["laite"]})
        # ensin lupapyyntö näkyy käyttäjälle, sitten yhteys muodostuu uudelleenyrityksellä
        saw_permission_msg = False
        end = time.time() + 30
        while time.time() < end:
            s = call(base, "/api/tila")
            if s["yhteys"]["virhe"] and s["yhteys"]["virhe"].startswith("Salli"):
                saw_permission_msg = True
            if s["vaylatesti"] and s["vaylatesti"]["kunnossa"] and s["live"]["vin"]:
                break
            time.sleep(0.3)
        assert saw_permission_msg, "lupaviesti ei näkynyt"
        assert s["vaylatesti"]["kunnossa"], s["vaylatesti"]
        assert s["live"]["brick_count"] == 96
        q = call(base, "/api/yllapito/tarkistus?laaja=0")
        sov = [c for c in q["tarkistukset"] if c["nimi"] == "Sovittimen yhteys"][0]
        assert sov["tila"] == "ok", sov
        call(base, "/api/sulje", {})
        end = time.time() + 10
        while time.time() < end and not bridge.stopped:
            time.sleep(0.2)
        assert bridge.stopped, "sovellukselle ei ilmoitettu sulkemisesta"
        print("OK android-silta")


def test_android_bluetooth_lista():
    """Puhelimen paritetuista Bluetooth-laitteista näytetään vain OBDLink-sovittimet."""
    from akux import android

    class B:
        def listDevices(self):
            return ["FT231X USB UART 0403:6015", "Bluetooth: OBDLink MX+ 00:04:3E:9A:1B:2C",
                    "Bluetooth: Galaxy Buds 11:22:33:44:55:66", "Bluetooth: Tesla Model 3 AA:BB:CC:DD:EE:FF"]
    old = android._bridge
    android._bridge = B()
    try:
        ports = android.list_ports()
    finally:
        android._bridge = old
    names = [p["laite"] for p in ports]
    assert names == ["FT231X USB UART 0403:6015", "Bluetooth: OBDLink MX+ 00:04:3E:9A:1B:2C"], names
    print("OK Android Bluetooth-lista")


if __name__ == "__main__":
    test_android_silta()
    test_android_bluetooth_lista()
