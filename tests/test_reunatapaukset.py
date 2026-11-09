"""Reunatapaukset: vanha energiaviesti, lataustauko, datakatko, ohitukset ja keskeytys."""
import faulthandler
import os
import sys
import tempfile as _tf
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AKUX_MITTAUSKANSIO", _tf.mkdtemp(prefix="akux-testi-"))

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


def test_lfp_akku():
    """Model 3 SR+ LFP (Shanghai, 12/2020): 106 kennoryhmää ja tasainen jännitekäyrä."""
    with tempfile.TemporaryDirectory() as tmp:
        app, src, vid = setup(tmp, soc=0.08, accel=300, chem="LFP", cells=106, nfp_kwh=52.0, bol_kwh=55.0,
                              vin="LRW3E7FA0MC123456", weak_cell=60)
        st = app.decoder.state
        assert st.brick_count == 106, st.brick_count
        tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti", mittarilukema=95000)
        assert wait(lambda: app.recorder.vaihe == "odota_lataus", 60)
        src.set_mode("charge", 7.0)
        assert wait(lambda: app.recorder.vaihe == "lepo_loppu", 300)
        src.set_mode("park")
        assert wait(lambda: not app.recorder.active, 120)
        r = app.storage.test(tid)["tulos"]
        cap = r["kapasiteetti"]
        print("LFP:", r["ajoneuvo"]["malli_id"], round(cap["taysi_kwh"], 2), "±", round(cap["epavarmuus_kwh"], 2),
              "oikea", src.nfp, "R", cap["r_ohm"], "ero", round(r["kennot"]["ero_mv"], 1), r["kennot"]["luokka"],
              "matala", round(r["kennot_matala"]["ero_mv"], 1), r["huomiot"])
        assert r["ajoneuvo"]["kemia"] == "LFP" and r["ajoneuvo"]["kennoryhmat"] == 106
        assert r["ajoneuvo"]["malli_id"].endswith("lfp")
        assert r["viite"]["kwh"] == 55.0
        assert cap["valmis"] and abs(cap["taysi_kwh"] - src.nfp) < max(1.5, cap["epavarmuus_kwh"])
        assert "ocv_kwh" not in cap           # lepojänniterinnakkaisarvio ei sovellu LFP-akulle
        assert r["kennot"]["lkm"] == 106
        assert report.build(app.storage, tid).exists()

        src2 = app.connect("demo", soc=0.55, accel=20, chem="LFP", cells=106, nfp_kwh=52.0, bol_kwh=55.0,
                           vin="LRW3E7FA0MC123456")
        assert wait(lambda: app.decoder.state.brick_count == 106, 20)
        tid2 = app.start_test(vehicle_id=vid, tyyppi="pikatarkastus")
        assert wait(lambda: not app.recorder.active, 120)
        r2 = app.storage.test(tid2)["tulos"]
        app.disconnect()
        print("LFP pika:", round(r2["bms"]["soh_pct"], 1), r2["huomiot"])
        assert abs(r2["bms"]["soh_pct"] - 52.0 / 55.0 * 100) < 0.3
        assert any("täyteen" in h for h in r2["huomiot"]), "LFP-huomautus puuttuu"
        assert report.build(app.storage, tid2).exists()


def test_keskeytynyt_ohjelma():
    """Ohjelma suljetaan kesken mittauksen: mittaus merkitään keskeytyneeksi seuraavalla käynnistyksellä."""
    with tempfile.TemporaryDirectory() as tmp:
        app, src, vid = setup(tmp, soc=0.1, accel=60)
        tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti")
        time.sleep(1)
        app.recorder.flush()
        src.stop()
        app2 = App(tmp)
        # Kapasiteettimittausta voi jatkaa (versiosta 1.7 alkaen myös latauksen aikana)
        assert app2.storage.test(tid)["tila"] == "kesken"
        app2.recorder.discard(tid)
    with tempfile.TemporaryDirectory() as tmp:
        app, src, vid = setup(tmp, soc=0.7, accel=4)
        tid = app.start_test(vehicle_id=vid, tyyppi="kuormitus")
        time.sleep(1)
        src.stop()
        app2 = App(tmp)
        assert app2.storage.test(tid)["tila"] == "keskeytynyt"


if __name__ == "__main__":
    for f in (test_vanha_muoto_tauko_ja_katko, test_datakatko_latauksen_aikana, test_lataus_heti_ja_ohitukset, test_liian_pieni_lataus_ja_keskeytys,
              test_lfp_akku, test_keskeytynyt_ohjelma):
        # Jos testi jumittuu, kaikkien säikeiden pinot tulostetaan ja ajo päättyy virheeseen
        faulthandler.dump_traceback_later(600, exit=True)
        t0 = time.time()
        f()
        faulthandler.cancel_dump_traceback_later()
        print("OK", f.__name__, f"{time.time() - t0:.0f} s", flush=True)
