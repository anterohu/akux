"""Kaikki Tesla-mallit: valmistenumeron purku, mallipohjan valinta, kytkentäohjeet ja
Model S 2012–2021 / Model X 2015–2021 -viestiarkkitehtuurin koko mittausketju."""
import os
import sys
import tempfile as _tf
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AKVERI_MITTAUSKANSIO", _tf.mkdtemp(prefix="akveri-testi-"))

from akveri import profiles, report, vin as vinmod  # noqa: E402
from akveri.app import App  # noqa: E402
from akveri.decoder import TeslaDecoder  # noqa: E402
from akveri.simulator import ESITTELYAUTOT, BatterySimulator  # noqa: E402


def wait(cond, timeout=300, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


def test_valmistenumerot_ja_mallipohjat():
    cases = [
        # VIN, malli, odotettu pohja
        ("5YJ3E7EB0LF654321", "Model 3", "m3-lr-2019-2020-nca"),
        ("LRW3E7FA0MC123456", "Model 3", "m3-srplus-2021-lfp"),
        ("XP7YGCEK0NB123456", "Model Y", "my-lr-nmc"),
        ("5YJSA1E20FF123456", "Model S", None),            # vanha S: pohja tarkentuu mittauksessa
        ("5YJXCBE20HF123456", "Model X", None),
        ("5YJSA1E50NF123456", "Model S", None),
        ("7G2CEHED0RA123456", "Cybertruck", "ct-awd"),
    ]
    for v, malli, pohja in cases:
        info = vinmod.decode(v)
        assert info["kelvollinen"], (v, info)
        assert info["malli"] == malli, (v, info["malli"])
        m, why = profiles.identify(info, platform=info.get("alusta_arvio"))
        assert m, v
        if pohja:
            assert m["id"] == pohja, (v, m["id"], why)
        if malli in ("Model S", "Model X"):
            assert "S" in m["malli_koodi"] or "X" in m["malli_koodi"], m
            exp_platform = "sx" if info["vuosimalli"] <= 2020 else "m3"
            assert m["alusta"] == exp_platform, (v, m)
        g = profiles.connection_guide(info["malli_koodi"], info["vuosimalli"], m.get("alusta"))
        assert g["ohje"] and g["liitin"], v
    assert "Roadster" in vinmod.decode("5YJRE1A19A1000123")["malli"]
    assert vinmod.decode("5YJRE1A19A1000123").get("huomautus")
    # Vanhan S/X:n akku valitaan akunhallinnan täyden akun energian perusteella
    info = vinmod.decode("5YJSA1E20FF123456")
    m, _ = profiles.identify(info, platform="sx", brick_count=96, nfp_kwh=74.2)
    assert m["id"] == "sx-85", m["id"]
    m, _ = profiles.identify(vinmod.decode("5YJSA1E26HF123456"), platform="sx", brick_count=96, nfp_kwh=94.0)
    assert m["id"] == "sx-100", m["id"]
    # Model 3:n ja Model Y:n kytkentäohje
    assert "26-pinninen" in profiles.connection_guide("3", 2022)["liitin"]
    assert "20-pinninen" in profiles.connection_guide("3", 2020)["liitin"]
    assert not profiles.connection_guide("Y", 2025)["varmistettu"]
    print("OK valmistenumerot ja mallipohjat")


def test_alustan_tunnistus():
    """Model 3 -väylää ei tulkita koskaan vanhaksi Model S:ksi eikä päinvastoin."""
    for key, plat in (("m3-lr", "m3"), ("m3-lfp", "m3"), ("my-lr", "m3"), ("ms-85", "sx")):
        sim = BatterySimulator(soc=0.5, **ESITTELYAUTOT[key]["opts"])
        d = TeslaDecoder()
        for k in range(300):
            sim._step(0.1)
            sim.sim_t += 0.1
            for cid, data in sim._frames(sim.sim_t):
                d.feed(sim.sim_t, cid, data)
        s = d.snapshot()
        assert s["platform"] == plat, (key, s["platform"])
        assert s["vin"] == sim.vin and s["brick_count"] == sim.n, (key, s["vin"], s["brick_count"])
        assert abs(s["nfp_kwh"] - sim.nfp) < 0.15, (key, s["nfp_kwh"])
        assert s["temp_min"] is not None and s["odometer_km"]
        assert all(r["nakyy"] for r in d.bus_report() if r["pakollinen"]), key
    print("OK alustan tunnistus")


def _capacity(tmp, **sim):
    app = App(tmp)
    app.storage.save_settings({"lepo_alku_min": 20, "lepo_loppu_min": 20})
    src = app.connect("demo", **sim)
    src.set_mode("drive", 25.0)                 # lyhyt ajo: virran merkki varmistuu kuormituksesta
    assert wait(lambda: app.decoder.state.vin and app.decoder.state.nfp_kwh and app.decoder.state.brick_count, 30)
    src.set_mode("park")
    vid = app.storage.add_vehicle({"vin": app.decoder.state.vin, "nimi": "Testi"})
    tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti", mittarilukema=180000)
    assert wait(lambda: app.recorder.vaihe == "odota_lataus", 90)
    src.set_mode("charge", 9.0)
    assert wait(lambda: app.recorder.vaihe == "lepo_loppu", 400)
    src.set_mode("park")
    assert wait(lambda: not app.recorder.active, 150)
    r = app.storage.test(tid)["tulos"]
    app.disconnect()
    return app, src, tid, r


def test_model_s_kapasiteettimittaus():
    """Model S 85 (2015): vanha viestiarkkitehtuuri, 10-bittinen energiaviesti."""
    with tempfile.TemporaryDirectory() as tmp:
        app, src, tid, r = _capacity(tmp, auto="ms-85", soc=0.10, accel=300)
        cap = r["kapasiteetti"]
        print("Model S:", r["ajoneuvo"]["malli_id"], round(cap["taysi_kwh"], 2), "±", round(cap["epavarmuus_kwh"], 2),
              "oikea", src.nfp, "laskuri", cap.get("laskuri_ero_pct"), r["bms"].get("virtatarkistus"), r["huomiot"])
        assert r["ajoneuvo"]["alusta"] == "sx"
        assert r["ajoneuvo"]["malli_id"] == "sx-85", r["ajoneuvo"]["malli_id"]
        assert r["viite"]["lahde"].startswith("Mallitaulukko")
        assert any("alkuperäistä energiaa" in h for h in r["huomiot"])
        assert cap["valmis"] and abs(cap["taysi_kwh"] - src.nfp) < max(1.5, cap["epavarmuus_kwh"])
        assert cap.get("laskuri_ero_pct") is not None and abs(cap["laskuri_ero_pct"]) < 3
        assert r["kennot"]["lkm"] == 96
        pdf = report.build(app.storage, tid)
        assert pdf.exists() and pdf.stat().st_size > 50000


def test_model_s_kaanteinen_virta_ja_laskurit():
    """Virran merkki ja elinkaarilaskurien järjestys poikkeavat: ohjelma korjaa ne itse."""
    with tempfile.TemporaryDirectory() as tmp:
        app, src, tid, r = _capacity(tmp, auto="ms-85", soc=0.12, accel=300, sx_current_sign=-1,
                                     sx_counter_swap=True, energy_format="sx11")
        cap = r["kapasiteetti"]
        print("Model S käänteinen:", round(cap["taysi_kwh"], 2), "oikea", src.nfp, r["bms"].get("virtatarkistus"),
              r["bms"]["energiamuoto"])
        assert r["bms"]["energiamuoto"] == "sx11"
        assert cap["valmis"] and abs(cap["taysi_kwh"] - src.nfp) < max(1.5, cap["epavarmuus_kwh"])
        assert r["elinkaari"]["lataus_kwh"] > r["elinkaari"]["purku_kwh"]


def test_alkuperainen_energia_puuttuu():
    """Oikea Model 3 LFP 12/2020: akunhallinta lähettää alkuperäisen energian kentässä 0,1 kWh.
    Arvo on hylättävä, ja kunto lasketaan mallin alkuperäisestä kapasiteetista sekä näkymässä että raportissa."""
    import time as _t
    from akveri.app import App
    from akveri.server import Api
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        app = App(tmp)
        app.storage.save_settings({"mittaus_tallennus": False})
        api = Api(app)
        app.connect("demo", auto="m3-lfp", soc=0.5, accel=20, bol_broadcast=False)
        end = _t.time() + 30
        while _t.time() < end and not (app.decoder.state.nfp_kwh and app.decoder.state.brick_count):
            _t.sleep(0.2)
        live = api.tila({}, {})["live"]
        assert live["bol_kwh"] is None, live["bol_kwh"]
        assert live["viite_kwh"] == 55.0 and "mallin" in live["viite_lahde"], (live["viite_kwh"], live["viite_lahde"])
        soh = live["nfp_kwh"] / live["viite_kwh"] * 100
        assert 90 < soh < 100, soh
        vid = app.storage.add_vehicle({"vin": app.decoder.state.vin, "nimi": "LFP"})
        tid = app.start_test(vehicle_id=vid, tyyppi="pikatarkastus", mittarilukema=None, mittaaja="Testi")
        end = _t.time() + 120
        while _t.time() < end and app.recorder.active:
            _t.sleep(0.2)
        r = app.storage.test(tid)["tulos"]
        print("Alkuperäinen energia puuttuu: kunto", round(r["yhteenveto"]["kunto_pct"], 1), r["viite"])
        assert abs(r["yhteenveto"]["kunto_pct"] - 52.0 / 55.0 * 100) < 0.3
        assert r["viite"]["kwh"] == 55.0 and r["viite"]["lahde"] != "Auton akunhallinta"
        app.disconnect()


if __name__ == "__main__":
    for f in (test_valmistenumerot_ja_mallipohjat, test_alustan_tunnistus, test_model_s_kapasiteettimittaus,
              test_model_s_kaanteinen_virta_ja_laskurit, test_alkuperainen_energia_puuttuu):
        f()
        print("OK", f.__name__)
