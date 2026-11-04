"""Reunatapaukset: vanha energiaviesti, lataustauko, datakatko, ohitukset ja keskeytys."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux.app import App  # noqa: E402
from akux import report  # noqa: E402


def wait(cond, timeout=300, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


def setup(tmp, **sim):
    app = App(tmp)
    app.storage.save_settings({"lepo_alku_min": 20, "lepo_loppu_min": 20})
    src = app.connect("demo", **sim)
    assert wait(lambda: app.decoder.state.vin and app.decoder.state.nfp_kwh and app.decoder.state.brick_count, 30)
    vid = app.storage.add_vehicle({"vin": app.decoder.state.vin, "nimi": "Testi"})
    return app, src, vid


def test_vanha_muoto_tauko_ja_katko():
    """Vanha energiaviesti, lataus katkeaa välillä ja auto nukahtaa kesken latauksen."""
    with tempfile.TemporaryDirectory() as tmp:
        app, src, vid = setup(tmp, soc=0.10, accel=300, energy_format="vanha")
        assert app.decoder.state.energy_format == "vanha"
        tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti")
        assert wait(lambda: app.recorder.vaihe == "odota_lataus", 60)
        src.set_mode("charge", 7.0)
        assert wait(lambda: app.recorder.vaihe == "lataus", 30)
        assert wait(lambda: (app.decoder.state.soc_avg or 0) > 40, 120)
        src.set_mode("park")                         # lataus keskeytyy
        time.sleep(4)                                # ~20 min mittausaikaa
        assert wait(lambda: "tauko" in app.recorder.marks, 30)
        src.set_mode("sleep")                        # auto nukahtaa: väylä hiljaa
        time.sleep(1.5)
        src.set_mode("charge", 7.0)                  # lataus jatkuu
        assert wait(lambda: app.recorder.vaihe == "lepo_loppu", 300)
        src.set_mode("park")
        assert wait(lambda: not app.recorder.active, 120)
        t = app.storage.test(tid)
        app.disconnect()
        cap = t["tulos"]["kapasiteetti"]
        print("vanha muoto:", round(cap["taysi_kwh"], 2), "±", round(cap["epavarmuus_kwh"], 2),
              "katkot", cap["katkot_kwh"], t["tulos"]["huomiot"])
        assert t["tila"] == "valmis" and cap["valmis"]
        assert abs(cap["taysi_kwh"] - src.nfp) < max(1.5, cap["epavarmuus_kwh"])
        events = " ".join(e["teksti"] for e in app.storage.events(tid))
        assert "keskeytynyt" in events and "Lataus jatkuu" in events
        assert report.build(app.storage, tid).exists()


def test_datakatko_latauksen_aikana():
    """Sovitin ei välitä tietoja 20 minuuttiin latauksen aikana: energia täydennetään akunhallinnasta."""
    with tempfile.TemporaryDirectory() as tmp:
        app, src, vid = setup(tmp, soc=0.10, accel=300)
        tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti")
        src.set_mode("charge", 7.0)
        assert wait(lambda: app.recorder.vaihe == "lataus", 30)
        assert wait(lambda: (app.decoder.state.soc_avg or 0) > 50, 120)
        cb, src._cb = src._cb, None
        time.sleep(4)
        src._cb = cb
        assert wait(lambda: app.recorder.vaihe == "lepo_loppu", 300)
        src.set_mode("park")
        app.recorder.skip_phase()
        assert wait(lambda: not app.recorder.active, 30)
        cap = app.storage.test(tid)["tulos"]["kapasiteetti"]
        app.disconnect()
        print("katko:", round(cap["katkot_kwh"], 2), "kWh, tulos", round(cap["taysi_kwh"], 2), "±",
              round(cap["epavarmuus_kwh"], 2))
        assert cap["katkot_kwh"] > 1.5
        assert abs(cap["taysi_kwh"] - src.nfp) < max(1.5, cap["epavarmuus_kwh"])


def test_lataus_heti_ja_ohitukset():
    """Lataus aloitetaan heti (lepo jää lyhyeksi) ja loppulepo ohitetaan käsin."""
    with tempfile.TemporaryDirectory() as tmp:
        app, src, vid = setup(tmp, soc=0.12, accel=300)
        tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti")
        src.set_mode("charge", 11.0)
        assert wait(lambda: app.recorder.vaihe == "lataus", 30)
        assert wait(lambda: app.recorder.vaihe == "lepo_loppu", 300)
        src.set_mode("park")
        app.recorder.skip_phase()
        assert wait(lambda: not app.recorder.active, 30)
        t = app.storage.test(tid)
        app.disconnect()
        r = t["tulos"]
        assert r["kapasiteetti"]["valmis"]
        assert r["kapasiteetti"]["laatu_luokka"] in ("Kohtalainen", "Heikko")
        assert any("Lepojakso ennen latausta" in h for h in r["huomiot"])
        assert report.build(app.storage, tid).exists()


def test_liian_pieni_lataus_ja_keskeytys():
    with tempfile.TemporaryDirectory() as tmp:
        app, src, vid = setup(tmp, soc=0.85, accel=300)
        tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti")
        src.set_mode("charge", 7.0)
        assert wait(lambda: app.recorder.vaihe == "lepo_loppu", 120)
        app.recorder.skip_phase()
        assert wait(lambda: not app.recorder.active, 30)
        r = app.storage.test(tid)["tulos"]
        assert not r["kapasiteetti"]["valmis"]
        assert any("alle 20 %-yksikköä" in h for h in r["huomiot"])
        # keskeytys
        tid2 = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti")
        time.sleep(1)
        app.recorder.cancel()
        assert app.storage.test(tid2)["tila"] == "keskeytetty"
        try:
            report.build(app.storage, tid2)
            raise AssertionError("keskeytetystä mittauksesta ei saa tehdä raporttia")
        except ValueError:
            pass
        app.disconnect()


def test_keskeytynyt_ohjelma():
    """Ohjelma suljetaan kesken mittauksen: mittaus merkitään keskeytyneeksi seuraavalla käynnistyksellä."""
    with tempfile.TemporaryDirectory() as tmp:
        app, src, vid = setup(tmp, soc=0.1, accel=60)
        tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti")
        time.sleep(1)
        src.stop()
        app2 = App(tmp)
        assert app2.storage.test(tid)["tila"] == "keskeytynyt"


if __name__ == "__main__":
    for f in (test_vanha_muoto_tauko_ja_katko, test_datakatko_latauksen_aikana, test_lataus_heti_ja_ohitukset, test_liian_pieni_lataus_ja_keskeytys,
              test_keskeytynyt_ohjelma):
        f()
        print("OK", f.__name__)
