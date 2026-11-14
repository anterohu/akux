"""OBDLink-sovittimen keskustelun ja rivien jäsentämisen testi ilman laitetta.

Testi korvaa pyserial-kirjaston keinotekoisella sarjaportilla, joka vastaa kuten
STN-piirillinen OBDLink-sovitin ja syöttää simulaattorin tuottamia kehyksiä.
"""
import os
import sys
import tempfile as _tf
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AKVERI_MITTAUSKANSIO", _tf.mkdtemp(prefix="akveri-testi-"))

from akveri.decoder import TeslaDecoder  # noqa: E402
from akveri.simulator import BatterySimulator  # noqa: E402


class FakeSerial:
    commands: list = []

    def __init__(self, port, baud, timeout=0.2):
        self.buf = b""
        self.lock = threading.Lock()
        self.cmd = b""
        self.monitor = False
        sim = BatterySimulator(soc=0.5, accel=1)
        self.frames = []
        for _ in range(40):
            for cid, data in sim._frames(0):
                self.frames.append(f"{cid:03X}{data.hex().upper()}\r".encode())
        self.idx = 0

    @property
    def in_waiting(self):
        self._pump()
        return len(self.buf)

    def _pump(self):
        if self.monitor:
            with self.lock:
                for _ in range(30):
                    self.buf += self.frames[self.idx % len(self.frames)]
                    self.idx += 1

    def reset_input_buffer(self):
        with self.lock:
            self.buf = b""

    def write(self, data):
        if self.monitor:
            self.monitor = False          # mikä tahansa merkki pysäyttää valvonnan
            with self.lock:
                self.buf += b"STOPPED\r>"
        self.cmd += data
        while b"\r" in self.cmd:
            c, self.cmd = self.cmd.split(b"\r", 1)
            c = c.decode().strip()
            if not c:
                continue
            FakeSerial.commands.append(c)
            if c in ("STMA", "ATMA"):
                self.monitor = True
                continue
            resp = {"ATI": "ELM327 v1.4b", "STI": "STN2120 v5.6.19", "ATZ": "\r\rELM327 v1.4b"}.get(c, "OK")
            with self.lock:
                self.buf += (resp + "\r\r>").encode()

    def read(self, n=1):
        self._pump()
        with self.lock:
            out, self.buf = self.buf[:max(1, n)], self.buf[max(1, n):]
        if not out:
            time.sleep(0.01)
        return out

    def close(self):
        pass


def test_obdlink_session():
    fake = types.ModuleType("serial")
    fake.Serial = FakeSerial
    sys.modules["serial"] = fake
    from akveri.sources import ObdLinkSource
    dec = TeslaDecoder()
    src = ObdLinkSource("COM3")
    src.start(dec.feed)
    end = time.time() + 15
    while time.time() < end and not (dec.state.vin and dec.state.brick_count and dec.state.nfp_kwh):
        time.sleep(0.1)
    src.stop()
    cmds = FakeSerial.commands
    assert "ATSP6" in cmds and "ATCAF0" in cmds and "ATH1" in cmds and "STMA" in cmds, cmds
    assert any(c.startswith("STFAP 132") for c in cmds)
    assert dec.state.vin and dec.state.vin.startswith("5YJ3")
    assert dec.state.brick_count == 96
    assert abs(dec.state.nfp_kwh - 75.6) < 0.05
    assert src.info.get("suodatus") is True
    print("OK", src.info, dec.total_frames, "kehystä")


if __name__ == "__main__":
    test_obdlink_session()


class TaxiOnlySerial(FakeSerial):
    """Jalkatilan kolmannen osapuolen liitäntä: väylällä vain nopeus ja virtatila (0x105)."""

    def __init__(self, port, baud, timeout=0.2):
        super().__init__(port, baud, timeout)
        self.frames = [b"10500400000000000000\r"[:3] + b"0400000000000000\r"] * 50


def test_rajattu_liitanta_ja_kartoitus():
    fake = types.ModuleType("serial")
    fake.Serial = TaxiOnlySerial
    sys.modules["serial"] = fake
    import tempfile
    import json
    import urllib.request
    from akveri.app import App
    from akveri.server import Api, bind_server
    FakeSerial.commands.clear()
    with tempfile.TemporaryDirectory() as tmp:
        app = App(tmp)
        api = Api(app)
        httpd = bind_server(api, "127.0.0.1", 0)
        api.httpd = httpd
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json"},
                                         method="POST" if body is not None else "GET")
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())

        app.connect("obdlink", port="COM3")
        end = time.time() + 15
        while time.time() < end and app.decoder.total_frames < 400:
            time.sleep(0.1)
        t = call("/api/tila")
        assert not t["vaylatesti"]["kunnossa"]
        assert [r["tunniste"] for r in t["vaylatesti"]["viestit"] if r["nakyy"]] == ["0x105"]
        call("/api/vaylakartoitus", {})
        time.sleep(1)
        assert app.source.scanning
        end = time.time() + 20
        while time.time() < end:
            r = call("/api/vaylakartoitus")
            if r["tila"] == "valmis":
                break
            time.sleep(0.5)
        assert r["tila"] == "valmis" and r["arvio"] == "rajattu", r
        assert "diagnostiikkaliittimeen" in r["teksti"]
        # kartoituksen ajan suodattimet poistettiin ja sen jälkeen palautettiin
        time.sleep(1.5)
        cmds = FakeSerial.commands
        i = len(cmds) - 1 - cmds[::-1].index("STFAC")
        assert any(c.startswith("STFAP") for c in cmds[i:]), "suodattimia ei palautettu"
        app.disconnect()
        httpd.shutdown()
        print("OK rajattu liitäntä ja kartoitus")


class ElmClone(FakeSerial):
    """Tavallinen ELM327-kopio: ei STN-komentoja."""
    def write(self, data):
        if b"STI" in data:
            self.cmd += data.replace(b"STI\r", b"")
            with self.lock:
                self.buf += b"?\r\r>"
            return
        super().write(data)


def test_elm327_hylataan():
    fake = types.ModuleType("serial")
    fake.Serial = ElmClone
    sys.modules["serial"] = fake
    from akveri.sources import ObdLinkSource
    src = ObdLinkSource("COM7")
    src.start(lambda *a: None)
    end = time.time() + 10
    while time.time() < end and src.status != "Sovitinta ei tueta":
        time.sleep(0.1)
    st, err = src.status, src.error
    src.stop()
    assert st == "Sovitinta ei tueta", st
    assert "ei ole OBDLink" in err and "MX+" in err, err
    print("OK ELM327 hylätään:", err)


def test_bluetooth_portit():
    from akveri import sources
    P = types.SimpleNamespace
    ports = [
        P(device="COM3", description="USB Serial Port", hwid="USB VID:PID=0403:6015 SER=OBDLINKEX", vid=0x0403,
          manufacturer="FTDI"),
        P(device="COM5", description="Standard Serial over Bluetooth link (COM5)",
          hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002\\7&2A0B1C3D&0&00043E9A1B2C_C00000000",
          vid=None, manufacturer="Microsoft"),
        P(device="COM6", description="Standard Serial over Bluetooth link (COM6)",
          hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\7&2A0B1C3D&0&000000000000_00000000",
          vid=None, manufacturer="Microsoft"),
        P(device="COM8", description="Standard Serial over Bluetooth link (COM8)",
          hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002\\7&11AA22BB&0&A0B1C2D3E4F5_C00000000",
          vid=None, manufacturer="Microsoft"),
    ]
    sources.BT_NAME_LOOKUP = lambda mac: {"00043E9A1B2C": "OBDLink MX+ 12345", "A0B1C2D3E4F5": "Puhelin"}.get(mac)
    lp = types.ModuleType("serial.tools.list_ports")
    lp.comports = lambda: ports
    tools = types.ModuleType("serial.tools")
    tools.list_ports = lp
    sys.modules["serial.tools"] = tools
    sys.modules["serial.tools.list_ports"] = lp
    out = {p["laite"]: p for p in sources.list_ports()}
    assert out["COM5"]["todennakoinen"] and out["COM5"]["kuvaus"] == "Bluetooth: OBDLink MX+ 12345", out["COM5"]
    assert "COM6" not in out, "saapuva Bluetooth-portti ei saa näkyä"
    assert "COM8" not in out, "muu Bluetooth-laite kuin OBDLink ei saa näkyä"
    sources.BT_NAME_LOOKUP = None
    assert out["COM3"]["todennakoinen"]
    print("OK Bluetooth-portit")


if __name__ == "__main__":
    test_rajattu_liitanta_ja_kartoitus()
    test_elm327_hylataan()
    test_bluetooth_portit()
