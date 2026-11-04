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
os.environ.setdefault("AKUX_MITTAUSKANSIO", _tf.mkdtemp(prefix="akux-testi-"))

from akux.decoder import TeslaDecoder  # noqa: E402
from akux.simulator import BatterySimulator  # noqa: E402


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
    from akux.sources import ObdLinkSource
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
    from akux.app import App
    from akux.server import Api, bind_server
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


if __name__ == "__main__":
    test_rajattu_liitanta_ja_kartoitus()
