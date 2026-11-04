"""Koko ketjun testi simulaattorilla: pikatarkastus ja kapasiteettimittaus.

Ajo: python -m pytest tests  (tai python tests/test_kokonaisuus.py)
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux.app import App  # noqa: E402
from akux.bits import encode, get_bits, put_bits  # noqa: E402
from akux.decoder import TeslaDecoder  # noqa: E402
from akux import vin  # noqa: E402


def wait_until(cond, timeout=240, step=0.2):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


def test_bits_roundtrip():
    b = bytearray(8)
    encode(b, 11, 11, 75.3, 0.1)
    assert abs(get_bits(b, 11, 11) * 0.1 - 75.3) < 1e-9
    put_bits(b, 16, 16, -123 & 0xFFFF)
    assert get_bits(b, 16, 16, signed=True) == -123


def test_vin():
    info = vin.decode("5YJ3E7EB0LF654321")
    assert info["kelvollinen"]
    assert info["malli"] == "Model 3"
    assert info["vuosimalli"] == 2020
    assert info["tehdas"] == "Fremont"
    assert info["veto"] == "AWD"
    assert not vin.decode("ABC")["kelvollinen"]


def test_old_energy_format():
    d = TeslaDecoder()
    b = bytearray(8)
    encode(b, 0, 11, 76.4, 0.1)
    encode(b, 11, 11, 40.2, 0.1)
    encode(b, 55, 8, 3.4, 0.1)
    for k in range(10):
        d.feed(k * 0.1, 0x352, bytes(b))
    assert d.state.energy_format == "vanha"
    assert abs(d.state.nfp_kwh - 76.4) < 0.01
    assert abs(d.state.buffer_kwh - 3.4) < 0.01


def _run_capacity(tmp):
    app = App(tmp)
    app.storage.save_settings({"lepo_alku_min": 30, "lepo_loppu_min": 30})
    src = app.connect("demo", soc=0.08, accel=300)
    assert wait_until(lambda: app.decoder.state.vin and app.decoder.state.nfp_kwh and
                      app.decoder.state.brick_count, 30)
    st = app.decoder.state
    vid = app.storage.add_vehicle({"vin": st.vin, "nimi": "Testiauto"})
    tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti", mittarilukema=112345, mittaaja="Testi")
    assert wait_until(lambda: app.recorder.vaihe == "odota_lataus", 60)
    src.set_mode("charge", 7.0)
    assert wait_until(lambda: app.recorder.vaihe == "lataus", 30)
    assert wait_until(lambda: app.recorder.vaihe == "lepo_loppu", 400)
    src.set_mode("park")
    assert wait_until(lambda: not app.recorder.active, 120)
    t = app.storage.test(tid)
    app.disconnect()
    return app, t, src


def test_capacity_and_quick():
    with tempfile.TemporaryDirectory() as tmp:
        app, t, src = _run_capacity(tmp)
        r = t["tulos"]
        assert t["tila"] == "valmis", t
        cap = r["kapasiteetti"]
        assert cap["valmis"], r["huomiot"]
        true_kwh = src.nfp
        print("Mitattu", round(cap["taysi_kwh"], 2), "todellinen", true_kwh,
              "±", round(cap["epavarmuus_kwh"], 2), "R", cap["r_ohm"])
        assert abs(cap["taysi_kwh"] - true_kwh) < max(1.5, cap["epavarmuus_kwh"])
        assert r["ajoneuvo"]["malli_id"] == "m3-lr-2019-2020-nca"
        assert r["viite"]["lahde"] == "Auton akunhallinta"
        assert r["kennot"]["lkm"] == 96
        assert r["kapasiteetti"]["heikoin_ryhma"]["nro"] == 47

        # pikatarkastus samalle autolle
        src2 = app.connect("demo", soc=0.6, accel=20)
        assert wait_until(lambda: app.decoder.state.brick_count, 20)
        vid = t["vehicle_id"]
        tid2 = app.start_test(vehicle_id=vid, tyyppi="pikatarkastus")
        assert wait_until(lambda: not app.recorder.active, 120)
        t2 = app.storage.test(tid2)
        app.disconnect()
        assert t2["tila"] == "valmis"
        r2 = t2["tulos"]
        assert abs(r2["bms"]["soh_pct"] - src2.nfp / src2.bol * 100) < 0.2
        assert r2["kennot"]["lkm"] == 96
        v = app.storage.vehicle(vid)
        assert v["opitut"]["bol_kwh"] == r2["viite"]["kwh"]

        from akux import report
        for tt in (t, t2):
            path = report.build(app.storage, tt["id"])
            assert path.exists() and path.stat().st_size > 20000
            print("Raportti", path)


if __name__ == "__main__":
    test_bits_roundtrip()
    test_vin()
    test_old_energy_format()
    test_capacity_and_quick()
    print("OK")
