"""Versio 1.4: kaikki testityypit simulaattorilla, myös keskeytys ja jatkaminen.

Ajo: python tests/test_testityypit.py
"""
import os
import sys
import tempfile as _tf
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AKVERI_MITTAUSKANSIO", _tf.mkdtemp(prefix="akveri-testi-"))

from akveri.app import App  # noqa: E402
from akveri.simulator import BatterySimulator  # noqa: E402

LYHYT = {"lepo_alku_min": 10, "lepo_loppu_min": 10, "ajo_lepo_min": 10, "itsepurkaus_lepo_min": 10,
         "itsepurkaus_tunnit": 6, "kuormitus_tapahtumat": 6, "mittaus_tallennus": False}


def wait_until(cond, timeout=240, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


def _app(tmp):
    app = App(tmp)
    app.storage.save_settings(LYHYT)
    return app


def _start(app, src, tyyppi):
    app.connect("demo", sim=src)
    assert wait_until(lambda: app.decoder.state.vin and app.decoder.state.brick_count and
                      app.decoder.state.soc_avg is not None, 30)
    st = app.decoder.state
    v = app.storage.find_vehicle_by_vin(st.vin)
    vid = v["id"] if v else app.storage.add_vehicle({"vin": st.vin, "nimi": "Testiauto"})
    return app.start_test(vehicle_id=vid, tyyppi=tyyppi, mittarilukema=None, mittaaja="Testi")


def _phase(app, name, timeout=120):
    ok = wait_until(lambda: app.recorder.vaihe == name, timeout)
    assert ok, f"vaihe {app.recorder.vaihe} ≠ {name}"


def _done(app, tid, timeout=180):
    assert wait_until(lambda: not app.recorder.active, timeout), app.recorder.vaihe
    t = app.storage.test(tid)
    assert t["tila"] == "valmis", t["tila"]
    assert "virhe" not in (t["tulos"] or {}), t["tulos"].get("virhe")
    return t


def _report(app, tid):
    from akveri import report
    p = report.build(app.storage, tid)
    assert p.exists() and p.stat().st_size > 20000
    return p


def test_ajotesti_kahdessa_osassa(tmp):
    app = _app(tmp)
    src = BatterySimulator(soc=0.92, accel=400, weak_cell=None)
    tid = _start(app, src, "ajotesti")
    _phase(app, "lepo_ajo_alku")
    p = app.recorder.progress()
    assert p["voi_tauottaa"] and p.get("lepo_tavoite_s") == 600
    _phase(app, "ajo", 60)
    src.set_mode("drive", 18.0)
    assert wait_until(lambda: (app.decoder.state.soc_avg or 100) < 55, 120)
    # Ensimmäinen ajo päättyy: yhteys katkaistaan, mittaus jää kesken
    src.set_mode("park")
    app.disconnect()
    t = app.storage.test(tid)
    assert t["tila"] == "kesken", t["tila"]
    # Ohjelma käynnistetään uudelleen ja mittausta jatketaan
    app2 = _app(tmp)
    app2.connect("demo", sim=src)
    assert wait_until(lambda: app2.decoder.state.vin, 20)
    app2.resume_test(tid)
    assert app2.recorder.vaihe == "ajo" and app2.recorder.osat == 2
    src.set_mode("drive", 18.0)
    assert wait_until(lambda: (app2.recorder.progress() or {}).get("tavoite_saavutettu"), 200)
    src.set_mode("park")
    t = _done(app2, tid, 200)
    r = t["tulos"]
    pu = r["purku"]
    assert pu["valmis"], pu
    assert pu["osat"] == 2
    err = pu["taysi_kwh"] - src.nfp
    print(f"Ajotesti {pu['taysi_kwh']:.2f} kWh, todellinen {src.nfp}, ±{pu['epavarmuus_kwh']:.2f}, "
          f"laatu {pu['laatu_luokka']}, matka {pu.get('matka_km')}",
          [q for q in pu["laatu"] if not q["ok"]])
    assert abs(err) < max(2.0, 1.5 * pu["epavarmuus_kwh"]), err
    assert r["paatulos"]["lahde"] == "Ajotesti"
    assert r["yhteenveto"]["kunto_lahde"] == "Ajotesti"
    _report(app2, tid)
    app2.disconnect()
    return app2


def test_pika_ajotesti(tmp):
    app = _app(tmp)
    src = BatterySimulator(soc=0.7, accel=400, weak_cell=None)
    tid = _start(app, src, "pika_ajo")
    _phase(app, "lepo_ajo_alku")
    app.recorder.skip_phase()
    _phase(app, "ajo", 10)
    src.set_mode("drive", 18.0)
    assert wait_until(lambda: (app.recorder.progress() or {}).get("tavoite_saavutettu"), 120)
    src.set_mode("park")
    t = _done(app, tid)
    pu = t["tulos"]["purku"]
    assert pu["valmis"], pu
    print(f"Pika-ajotesti {pu['taysi_kwh']:.2f} kWh ±{pu['epavarmuus_kwh']:.2f}, laatu {pu['laatu_luokka']}",
          [q for q in pu["laatu"] if not q["ok"]])
    assert abs(pu["taysi_kwh"] - src.nfp) < max(3.0, 1.5 * pu["epavarmuus_kwh"])
    assert pu["laatu_luokka"] != "Hyvä"           # lyhyt ajo ja ohitettu lepo
    r = t["tulos"]
    assert "paatulos" not in r                    # pika-ajotesti ei anna kuntoprosenttia
    assert r["yhteenveto"]["kunto_lahde"] == "Akunhallinnan arvio"
    assert pu["vahvistaa_bms"] is True
    _report(app, tid)
    app.disconnect()


def test_taysi_akkutesti(tmp):
    app = _app(tmp)
    src = BatterySimulator(soc=0.95, accel=400)
    tid = _start(app, src, "taysi")
    _phase(app, "lepo_ajo_alku")
    _phase(app, "ajo", 60)
    src.set_mode("drive", 20.0)
    assert wait_until(lambda: (app.recorder.progress() or {}).get("tavoite_saavutettu"), 240)
    src.set_mode("park")
    _phase(app, "lepo_alku", 60)
    _phase(app, "odota_lataus", 60)
    src.set_mode("charge", 11.0)
    _phase(app, "lataus", 30)
    _phase(app, "lepo_loppu", 400)
    src.set_mode("park")
    t = _done(app, tid)
    r = t["tulos"]
    y = r["yhdistetty"]
    assert y and y["valmis"], (r.get("purku"), r.get("kapasiteetti", {}).get("valmis"))
    print(f"Täysi akkutesti {y['taysi_kwh']:.2f} ±{y['epavarmuus_kwh']:.2f} (lataus {y['lataus_kwh']:.2f}, "
          f"purku {y['purku_kwh']:.2f}), todellinen {src.nfp}")
    assert y["yhtapitavat"]
    assert abs(y["taysi_kwh"] - src.nfp) < max(1.5, 1.5 * y["epavarmuus_kwh"])
    assert y["epavarmuus_kwh"] <= min(r["kapasiteetti"]["epavarmuus_kwh"], r["purku"]["epavarmuus_kwh"]) + 1e-9
    assert r["yhteenveto"]["kunto_lahde"] == "Täysi akkutesti"
    _report(app, tid)
    app.disconnect()


def test_kuormitustesti_lahtoehdot(tmp):
    """Kuormitustesti aloitetaan vain DEKRAn ehdoilla: varaus 40–80 %, akku 10–30 °C, lämpötilaero alle 2 °C."""
    for kw, sana in ((dict(soc=0.92), "varaus"), (dict(soc=0.6, temp_c=4.0), "lämpötila")):
        app = _app(tmp)
        src = BatterySimulator(accel=4, weak_cell=None, **kw)
        app.connect("demo", sim=src)
        assert wait_until(lambda: app.decoder.state.vin and app.decoder.state.temp_min is not None, 20)
        vid = app.storage.add_vehicle({"vin": app.decoder.state.vin})
        try:
            app.start_test(vehicle_id=vid, tyyppi="kuormitus")
            raise AssertionError("kuormitustesti käynnistyi, vaikka ehdot eivät täyty")
        except RuntimeError as e:
            msg = str(e)
        assert "Kuormitustestiä ei voi aloittaa" in msg and sana in msg, msg
        assert not app.recorder.active and not app.storage.tests()
        app.disconnect()
        print("  estetty:", msg)


def test_kuormitustesti(tmp):
    app = _app(tmp)
    src = BatterySimulator(soc=0.7, accel=4, weak_cell=None)
    src.r_cell[30] *= 1.6                         # yksi kennoryhmä selvästi muita suurempi resistanssi
    tid = _start(app, src, "kuormitus")
    _phase(app, "kuormitus", 60)
    src.set_mode("kiihdytys")
    assert wait_until(lambda: app.recorder.load_events >= 6, 120)
    src.set_mode("park")
    t = _done(app, tid, 60)
    k = t["tulos"]["kuorma"]
    print(f"Kuormitus R {k['r_akku_mohm']:.1f} mΩ (todellinen {sum(src.r_cell) * 1000:.1f}), hajonta "
          f"{k['hajonta_pct']:.1f} %, suurin ryhmä {k['r_max_nro']}, huippu {k['teho_max_kw']:.0f} kW")
    assert k["r_max_nro"] == 31, k["r_max_nro"]
    assert any(p["nro"] == 31 for p in k["poikkeavat"])
    assert abs(k["r_akku_mohm"] - sum(src.r_cell) * 1000) / (sum(src.r_cell) * 1000) < 0.15
    _report(app, tid)
    app.disconnect()


def test_pikalataustesti(tmp):
    app = _app(tmp)
    src = BatterySimulator(soc=0.15, accel=60, dc_kw=150.0)
    tid = _start(app, src, "pikalataus")
    _phase(app, "odota_pikalataus", 20)
    src.set_mode("pikalataus")
    _phase(app, "pikalataus", 30)
    assert wait_until(lambda: (app.decoder.state.soc_avg or 0) > 80, 200)
    src.set_mode("park")
    t = _done(app, tid, 60)
    dc = t["tulos"]["pikalataus"]
    print(f"Pikalataus huippu {dc['huipputeho_kw']:.0f} kW, {dc['energia_kwh']:.1f} kWh, "
          f"20→80 % {dc.get('aika_20_80_min')} min, ero {dc['jannite_ero_max_mv']} mV")
    assert 140 <= dc["huipputeho_kw"] <= 160
    assert dc["aika_20_80_min"] and 15 < dc["aika_20_80_min"] < 60
    assert dc["jannite_ero_max_mv"] < 120
    _report(app, tid)
    app.disconnect()


def test_itsepurkaustesti_ja_tauko(tmp):
    app = _app(tmp)
    src = BatterySimulator(soc=0.6, accel=20, weak_cell=None, leak_cell=12, leak_pct_day=0.6)
    tid = _start(app, src, "itsepurkaus")
    _phase(app, "odotus", 120)
    src.set_accel(600)
    app.disconnect()                       # yö: ohjelma suljetaan välillä
    assert app.storage.test(tid)["tila"] == "kesken"
    time.sleep(2)
    app2 = _app(tmp)
    app2.connect("demo", sim=src)
    assert wait_until(lambda: app2.decoder.state.vin, 20)
    app2.resume_test(tid)
    _phase(app2, "itse_loppu", 120)
    src.set_accel(20)
    t = _done(app2, tid, 200)
    sd = t["tulos"]["itsepurkaus"]
    print(f"Itsepurkaus {sd['tunnit']:.1f} h, heikoin {sd['heikoin_nro']} {sd['heikoin_mv_vrk']:.2f} mV/vrk, "
          f"luokka {sd['luokka']}")
    assert sd["heikoin_nro"] == 12
    assert sd["luokka"] in ("Tyydyttävä", "Poikkeava")
    assert sd["riittava"] and len(sd["poikkeavat"]) == 1, sd["poikkeavat"]
    _report(app2, tid)
    app2.disconnect()


def test_hylkays(tmp):
    app = _app(tmp)
    src = BatterySimulator(soc=0.9, accel=200)
    tid = _start(app, src, "ajotesti")
    _phase(app, "lepo_ajo_alku")
    app.recorder.pause()
    assert app.storage.test(tid)["tila"] == "kesken"
    app.recorder.discard(tid)
    assert app.storage.test(tid)["tila"] == "keskeytetty"
    app.disconnect()


def test_lataus_tauon_aikana(tmp):
    app = _app(tmp)
    src = BatterySimulator(soc=0.9, accel=400, weak_cell=None)
    tid = _start(app, src, "ajotesti")
    _phase(app, "ajo", 60)
    src.set_mode("drive", 18.0)
    assert wait_until(lambda: (app.decoder.state.soc_avg or 100) < 60, 120)
    src.set_mode("park")
    app.disconnect()
    # Tauon aikana autoa ladataan (ohjelma ei ole yhteydessä)
    src.set_mode("charge", 11.0)
    for _ in range(600):
        src._step(5.0)
        src.sim_t += 5.0
    src.set_mode("park")
    app2 = _app(tmp)
    app2.connect("demo", sim=src)
    assert wait_until(lambda: app2.decoder.state.vin and app2.decoder.state.total_charge_kwh, 20)
    app2.resume_test(tid)
    assert wait_until(lambda: "jatkotauko" not in app2.recorder.marks, 20)
    assert "ladattu_ajossa" in app2.recorder.marks
    assert any("tauon aikana" in n for n in app2.recorder.notes)
    app2.recorder.cancel()
    app2.disconnect()


def _offline(src, minutes, step=5.0):
    """Simuloitu auto jatkaa toimintaansa, kun ohjelma ei ole yhteydessä."""
    for _ in range(int(minutes * 60 / step)):
        src._step(step)
        src.sim_t += step


def test_yotauko_latauksessa_lammitys(tmp):
    """Mittaus jätetään yöksi tauolle kesken latauksen. Lataus on pysäytetty ja auto kuluttaa yön aikana
    energiaa (lämmitys, valvontatila). Aamulla lataus jatkuu. Yön kulutus pitää vähentää tuloksesta."""
    app = _app(tmp)
    src = BatterySimulator(soc=0.12, accel=300, weak_cell=None)
    tid = _start(app, src, "kapasiteetti")
    src.set_mode("charge", 11.0)
    _phase(app, "lataus", 60)
    assert wait_until(lambda: (app.decoder.state.soc_avg or 0) > 40, 120)
    app.recorder.pause()                   # Jatka myöhemmin
    app.disconnect()
    src.set_mode("drive", 0.4)             # lataus pysäytetty, auto kuluttaa 0,4 kW koko yön
    c0 = src.total_dis - src.total_chg
    _offline(src, 8 * 60, step=30.0)
    kulutus = (src.total_dis - src.total_chg) - c0      # yön todellinen nettokulutus (noin 2,6 kWh)
    app2 = _app(tmp)
    app2.connect("demo", sim=src)
    assert wait_until(lambda: app2.decoder.state.vin and app2.decoder.state.nominal_remaining_kwh, 20)
    src.set_mode("park")
    app2.resume_test(tid)
    src.set_mode("charge", 11.0)
    _phase(app2, "lepo_loppu", 400)
    src.set_mode("park")
    t = _done(app2, tid, 300)
    cap = t["tulos"]["kapasiteetti"]
    print(f"Yötauko: kapasiteetti {cap['taysi_kwh']:.2f} ±{cap['epavarmuus_kwh']:.2f}, tauon nettoenergia "
          f"{cap['katkot_kwh']:.2f} kWh (yön kulutus {kulutus:.2f} kWh), todellinen {src.nfp}")
    assert cap["valmis"]
    assert kulutus > 2.0
    assert abs(cap["katkot_kwh"] + kulutus) < 0.15, (cap["katkot_kwh"], kulutus)
    assert abs(cap["taysi_kwh"] - src.nfp) < max(1.5, 1.5 * cap["epavarmuus_kwh"])
    assert any("kulutus" in h for h in t["tulos"]["huomiot"]), t["tulos"]["huomiot"]
    app2.disconnect()


def test_virheellinen_alkuperainen_energia(tmp):
    """LFP-auto (Model 3 SR+ LFP, 106 kennoryhmää), jonka akunhallinta ilmoittaa alkuperäiseksi energiaksi
    76,9 kWh (mittaus 2026-00009). Arvo ei sovi 55 kWh:n LFP-akkuun, joten sitä ei käytetä, ja kunto lasketaan
    mallin kapasiteetista. Väärä arvo ei myöskään saa jäädä autolle opituksi."""
    from akveri import analysis
    app = _app(tmp)
    src = BatterySimulator(chem="LFP", cells=106, nfp_kwh=51.4, bol_kwh=76.9, soc=0.15, accel=300,
                           weak_cell=None, vin="LRW3E7FA4LC110444")
    tid = _start(app, src, "kapasiteetti")
    assert abs(app.decoder.state.bol_kwh - 76.9) < 0.05
    src.set_mode("charge", 11.0)
    _phase(app, "lepo_loppu", 400)
    src.set_mode("park")
    t = _done(app, tid, 300)
    r = t["tulos"]
    assert r["ajoneuvo"]["malli_id"] == "m3-srplus-2021-lfp", r["ajoneuvo"]["malli_id"]
    assert r["viite"]["kwh"] == 55.0 and r["viite"]["hylatty_bol_kwh"] == 76.9, r["viite"]
    assert any("76,9 kWh" in h and "ei sovi" in h for h in r["huomiot"]), r["huomiot"]
    soh = r["kapasiteetti"]["soh_pct"]
    assert 90 < soh < 97, soh                       # 51,4 / 55,0 ≈ 93 %, ei 67 %
    v = app.storage.vehicle(t["vehicle_id"])
    assert (v.get("opitut") or {}).get("bol_kwh") != 76.9, v.get("opitut")
    # Vanhalla versiolla tehty mittaus: väärä arvo on jo opittu autolle. Uudelleenlaskenta korjaa tuloksen.
    app.storage.update_vehicle(v["id"], {"opitut": {**(v.get("opitut") or {}), "bol_kwh": 76.9}})
    r2 = analysis.reanalyze(app.storage, tid)
    assert r2["viite"]["kwh"] == 55.0 and 90 < r2["kapasiteetti"]["soh_pct"] < 97, r2["viite"]
    _report(app, tid)
    print(f"Väärä alkuperäinen energia hylätty: kunto {soh:.1f} %")
    app.disconnect()


def test_kapasiteetti_katkot_latauksessa(tmp):
    """Ohjelma suljetaan kesken latauksen ja kone sammuu kesken latauksen: mittaus jatkuu ja tulos pitää."""
    app = _app(tmp)
    src = BatterySimulator(soc=0.12, accel=300, weak_cell=None)
    tid = _start(app, src, "kapasiteetti")
    src.set_mode("charge", 11.0)
    _phase(app, "lataus", 60)
    assert app.recorder.progress()["voi_tauottaa"]
    assert wait_until(lambda: (app.decoder.state.soc_avg or 0) > 40, 120)
    # 1) Ohjelma suljetaan tavallisesti latauksen aikana; auto latautuu 20 min ilman yhteyttä
    app.disconnect()
    assert app.storage.test(tid)["tila"] == "kesken"
    _offline(src, 20)
    app2 = _app(tmp)
    app2.connect("demo", sim=src)
    assert wait_until(lambda: app2.decoder.state.vin and app2.decoder.state.nominal_remaining_kwh, 20)
    app2.resume_test(tid)
    assert app2.recorder.vaihe == "lataus" and app2.recorder.osat == 2
    soc_resume = app2.decoder.state.soc_avg
    assert wait_until(lambda: (app2.decoder.state.soc_avg or 0) > soc_resume + 15, 120)
    # 2) Tietokone sammuu yllättäen (akku loppuu): tila on tallentunut vain viimeisimpään tallennukseen asti
    rec = app2.recorder
    with rec.lock:
        rec.flush()
        app2.decoder.remove_hv_listener(rec._on_hv)
        app2.decoder.remove_brick_listener(rec._on_brick)
        rec._close_raw()
        rec.test_id = None
    app2.source.stop()
    assert app2.storage.test(tid)["tila"] == "käynnissä"
    _offline(src, 15)
    app3 = _app(tmp)                       # käynnistys merkitsee mittauksen jatkettavaksi
    assert app3.storage.test(tid)["tila"] == "kesken"
    app3.connect("demo", sim=src)
    assert wait_until(lambda: app3.decoder.state.vin and app3.decoder.state.nominal_remaining_kwh, 20)
    app3.resume_test(tid)
    assert app3.recorder.vaihe == "lataus" and app3.recorder.osat == 3
    _phase(app3, "lepo_loppu", 400)
    src.set_mode("park")
    t = _done(app3, tid, 300)
    cap = t["tulos"]["kapasiteetti"]
    print(f"Kapasiteetti kahden katkon jälkeen {cap['taysi_kwh']:.2f} ±{cap['epavarmuus_kwh']:.2f}, "
          f"katkot {cap['katkot_kwh']:.2f} kWh, todellinen {src.nfp}")
    assert cap["valmis"]
    assert cap["katkot_kwh"] > 4.0, cap["katkot_kwh"]
    assert abs(cap["taysi_kwh"] - src.nfp) < max(1.5, 1.5 * cap["epavarmuus_kwh"])
    _report(app3, tid)
    app3.disconnect()


ALL = [test_kuormitustesti_lahtoehdot, test_kapasiteetti_katkot_latauksessa, test_lataus_tauon_aikana, test_ajotesti_kahdessa_osassa, test_pika_ajotesti, test_taysi_akkutesti, test_kuormitustesti,
       test_pikalataustesti, test_itsepurkaustesti_ja_tauko, test_hylkays, test_yotauko_latauksessa_lammitys, test_virheellinen_alkuperainen_energia]

if __name__ == "__main__":
    only = sys.argv[1:]
    for fn in ALL:
        if only and fn.__name__ not in only:
            continue
        t0 = time.time()
        with _tf.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            fn(tmp)
        print(f"OK {fn.__name__} ({time.time() - t0:.0f} s)")
