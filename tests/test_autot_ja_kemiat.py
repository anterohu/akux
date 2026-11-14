"""Kaikki esittelyautot ja akkukemiat: datan luku bitintarkasti ja jokainen testityyppi.

Osa A: simulaattorin lähettämät viestit puretaan ja verrataan arvoihin, joista viestit tehtiin.
Osa B: jokainen testityyppi jokaisella autolla. Tuloksen on osuttava todelliseen kapasiteettiin
ilmoitetun epävarmuuden sisällä, ja raportissa ei saa olla puuttuvia tai virheellisiä arvoja.

Ajo: python tests/test_autot_ja_kemiat.py [auto ...]
"""
import os
import re
import sys
import tempfile as _tf
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AKUX_MITTAUSKANSIO", _tf.mkdtemp(prefix="akux-testi-"))

from akux.decoder import TeslaDecoder  # noqa: E402
from akux.simulator import ESITTELYAUTOT, BatterySimulator, MILE_KM  # noqa: E402
from test_testityypit import _app, _done, _phase, wait_until  # noqa: E402

HERE = Path(__file__).resolve().parent


def _hk(car):
    from akux import profiles
    m = profiles.get(ESITTELYAUTOT[car].get("malli_id"))
    from akux import polled
    return m if polled.for_model(m) else None


def _sim(car, **kw):
    m = _hk(car)
    if m:
        from akux import polled
        s = polled.for_model(m).simulator(m, **{**ESITTELYAUTOT[car]["opts"], **kw})
        s.malli_id = m["id"]
        return s
    return BatterySimulator(**{**ESITTELYAUTOT[car]["opts"], **kw})


def check_hk_decoding(car):
    """Hyundai/Kia: akunhallinnan vastauksista luetut arvot vastaavat simuloidun auton todellisia arvoja."""
    from akux.app import App
    with _tf.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        app = App(tmp)
        src = _sim(car, soc=0.55, accel=1)
        src.set_mode("park")
        app.connect("demo", sim=src)
        # MG ilmoittaa kennojännitteet lohkoittain: lohkon matalin ja korkein kenno (kaksi arvoa lohkoa kohden)
        mg = src.platform == "mg"
        n_arvot = 2 * src.g["lohkot"] if mg else src.n
        assert wait_until(lambda: app.decoder.state.brick_count == n_arvot and
                          len(app.decoder.state.bricks) == n_arvot and app.decoder.state.odometer_km, 20)
        st = app.decoder.state
        with app.decoder.lock:
            soc_true = sum(src._cell_socs()) / src.n * 100
            vs = src._volts(src.current)
            if mg:
                L = src.g["lohkot"]
                osat = [vs[round(k * src.n / L):round((k + 1) * src.n / L)] for k in range(L)]
                odotetut = [x for o in osat for x in (min(o), max(o))]
            else:
                odotetut = vs
            w = {"jännite (V)": abs(st.pack_v - src._pack_voltage(src.current)),
                 "virta (A)": abs(st.pack_i - src.current),
                 "varaustila (%)": abs(st.soc_avg - soc_true),
                 "kunto (%)": abs(st.nfp_kwh / (st.bol_kwh or src.bol) * 100 - src.nfp / src.bol * 100),
                 "latauslaskuri (kWh)": abs(st.total_charge_kwh - src.total_chg) if st.total_charge_kwh is not None else 0.0,
                 "lämpötila (°C)": abs((st.temp_max + st.temp_min) / 2 - src.temp),
                 "kennojännite (V)": max(abs(st.bricks[k + 1] - odotetut[k]) for k in range(n_arvot))}
        app.disconnect()
    lim = {"jännite (V)": 1.5, "virta (A)": 1.0, "varaustila (%)": 0.6, "kunto (%)": 0.06,
           "latauslaskuri (kWh)": 0.06, "kennojännite (V)": 0.03, "lämpötila (°C)": 1.0}
    for k, v in w.items():
        assert v <= lim[k], f"{car}: {k} poikkeaa {v}"
    return w


# ----------------------------------------------------------------------
# Osa A: datan luku
# ----------------------------------------------------------------------
def check_decoding(car, **kw):
    src = _sim(car, soc=0.55, accel=1, **kw)
    d = TeslaDecoder()
    t = 1000.0
    worst = {}

    def cmp(name, got, want, tol):
        assert got is not None, f"{car}: {name} puuttuu"
        e = abs(got - want)
        worst[name] = max(worst.get(name, 0), e)
        assert e <= tol, f"{car}: {name} {got} ≠ {want} (sallittu ±{tol})"

    n_step = 0
    fresh = []
    d.add_brick_listener(lambda t_, k, v, i: fresh.append((k, v)))
    seq = [("park", None, 40), ("drive", 25.0, 120), ("charge", 11.0, 120), ("kiihdytys", None, 40), ("park", None, 40)]
    for mode, pw, steps in seq:
        src.set_mode(mode, pw)
        for _ in range(steps):
            src._step(0.5)
            src.sim_t += 0.5
            t += 0.5
            fresh.clear()
            for cid, data in src._frames(src.sim_t):
                d.feed(t, cid, data)
            st = d.state
            n_step += 1
            if n_step < 30 or (src.platform == "sx" and not d._sx_sign_ok):
                continue
            socs = src._cell_socs()
            cur = src.current
            volts = [src._ocv(x) - cur * r for x, r in zip(socs, src.r_cell)]
            cmp("akun jännite (V)", st.pack_v, sum(volts), 0.006)
            cmp("akun virta (A)", st.pack_i, cur, 0.051)
            cmp("varaustila (%)", st.soc_avg, sum(socs) / src.n * 100, 0.051)
            cmp("täyden akun energia (kWh)", st.nfp_kwh, src.nfp, 0.051 if src.platform == "sx" else 0.011)
            cmp("suojavara (kWh)", st.buffer_kwh, src.buffer, 0.051 if src.platform == "sx" else 0.0051)
            dis = st.total_discharge_kwh
            chg = st.total_charge_kwh
            if dis is not None and chg is not None:
                cmp("purkulaskuri (kWh)", dis, src.total_dis, 0.0011)
                cmp("latauslaskuri (kWh)", chg, src.total_chg, 0.0011)
            cmp("mittarilukema (km)", st.odometer_km, src.odo, 0.002 * MILE_KM if src.platform == "sx" else 0.0011)
            lsb = 0.000305 if src.platform == "sx" else 0.0001
            for k, v in fresh:
                # Juuri purettu kennoryhmän jännite; simulaattorin mittauskohina 0,3 mV (5 σ)
                cmp("kennoryhmän jännite (V)", v, volts[k - 1], 0.0015 + lsb)
    st = d.state
    for need in ("akun jännite (V)", "akun virta (A)", "varaustila (%)", "täyden akun energia (kWh)",
                 "purkulaskuri (kWh)", "mittarilukema (km)", "kennoryhmän jännite (V)"):
        assert need in worst, f"{car}: {need} ei tarkistettu"
    assert st.vin == src.vin, (st.vin, src.vin)
    assert st.brick_count == src.n, (st.brick_count, src.n)
    assert st.platform == src.platform
    assert len(st.bricks) == src.n
    return worst


# ----------------------------------------------------------------------
# Osa B: testityypit
# ----------------------------------------------------------------------
def _vid(app):
    st = app.decoder.state
    v = app.storage.find_vehicle_by_vin(st.vin)
    return v["id"] if v else app.storage.add_vehicle({"vin": st.vin, "nimi": "Testiauto", "rekisteri": "ABC-123"})


def _n_arvot(src):
    """Kennojännitearvojen määrä: MG ilmoittaa lohkon matalimman ja korkeimman kennon (kaksi arvoa lohkoa kohden)."""
    return 2 * src.g["lohkot"] if getattr(src, "platform", "") == "mg" else src.n


def _connect(app, src):
    app.connect("demo", sim=src)
    n = _n_arvot(src)
    assert wait_until(lambda: app.decoder.state.vin and app.decoder.state.brick_count == n and
                      app.decoder.state.soc_avg is not None and app.decoder.state.nfp_kwh, 40), "yhteys"
    if src.platform == "sx":
        # vanhan arkkitehtuurin virran suunta varmistuu vasta kun virta vaihtelee
        pass


def _start(app, src, tyyppi):
    _connect(app, src)
    return app.start_test(vehicle_id=_vid(app), tyyppi=tyyppi, mittarilukema=None, mittaaja="Testi")


def _pdf_check(app, tid, must):
    from akux import report
    from pypdf import PdfReader
    p = report.build(app.storage, tid)
    txt = "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
    bad = [m.group(0) + " … " + txt[max(0, m.start() - 40):m.end() + 20].replace("\n", " ")
           for m in re.finditer(r"\b(None|nan|NaN|inf|Traceback|null)\b|[{}]|–\s*%|\?\?", txt)]
    assert not bad, f"raportissa virheellisiä merkkijonoja: {bad}"
    for m in must:
        assert m in txt, f"raportista puuttuu: {m}"
    merkki = ((app.storage.test(tid) or {}).get("tulos") or {}).get("ajoneuvo", {}).get("merkki") or "Tesla"
    if merkki != "Tesla":
        # muiden merkkien raportissa ei saa mainita Teslaa
        hits = [txt[max(0, m.start() - 40):m.end() + 30].replace("\n", " ") for m in re.finditer("Tesla", txt)]
        assert not hits, f"{merkki}-raportissa mainitaan Tesla: {hits}"
    return p, txt


def _within(name, got, u, true, abs_lim):
    err = got - true
    print(f"   {name}: {got:.2f} ± {u:.2f} kWh, todellinen {true:.2f}, ero {err:+.2f} kWh ({err / true * 100:+.1f} %)")
    assert abs(err) <= max(u * 1.5, 0.5), f"{name}: ero {err:.2f} yli epävarmuuden {u:.2f}"
    assert abs(err) <= abs_lim, f"{name}: ero {err:.2f} yli rajan {abs_lim}"


def check_self_discharge(app, car):
    src = _sim(car)
    # Itsepurkaustesti: terve akku ei saa näyttää vikaa, vuotava ryhmä on löydettävä.
    # LFP-kennon käyrä on keskialueella vaakasuora: testi tehdään täydestä akusta, ja keskialueella
    # tuloksen on oltava "ei luotettava" eikä virheellinen arvio.
    lfp = src.chem == "LFP"
    cases = [(None, 0.95 if lfp else 0.6), (src.n - 5, 0.95 if lfp else 0.6)] + ([(src.n - 5, 0.6)] if lfp else [])
    for leak, soc0 in cases:
        src = _sim(car, soc=soc0, accel=20, weak_cell=None, leak_cell=leak, leak_pct_day=0.8 if leak else 0.0)
        tid = _start(app, src, "itsepurkaus")
        _phase(app, "odotus", 150)
        src.set_accel(600)
        _phase(app, "itse_loppu", 120)
        src.set_accel(20)
        t = _done(app, tid, 200)
        sd = t["tulos"]["itsepurkaus"]
        print(f"   itsepurkaus {soc0 * 100:.0f} % ({'vuoto ryhmässä ' + str(leak) if leak else 'terve'}): "
              f"heikoin {sd['heikoin_nro']} {sd['heikoin_pct_vrk']:.2f} %/vrk, havaitsemisraja "
              f"{sd['havaitsemisraja_pct_vrk']:.2f} %/vrk, {sd['luokka']}")
        if lfp and soc0 < 0.9:
            assert not sd["riittava"] and sd["luokka"] is None, sd["luokka"]
            assert any("LFP-kennon lepojännite" in h for h in t["tulos"]["huomiot"])
        else:
            assert sd["riittava"], sd["havaitsemisraja_pct_vrk"]
            if leak:
                assert [p["nro"] for p in sd["poikkeavat"]] == [leak], sd["poikkeavat"]
                assert 0.4 < -sd["heikoin_pct_vrk"] < 1.3, sd["heikoin_pct_vrk"]
            else:
                assert not sd["poikkeavat"] and sd["luokka"] in ("Erinomainen", "Hyvä"), sd["poikkeavat"]
        _pdf_check(app, tid, ["Itsepurkaustesti", "Itsepurkautuminen"])
        app.disconnect()


def run_types(car, tmp):
    app = _app(tmp)
    name = ESITTELYAUTOT[car]["nimi"]
    print(f"== {name}")
    true_soh = None

    # Pikatarkastus
    src = _sim(car, soc=0.6, accel=20)
    tid = _start(app, src, "pikatarkastus")
    t = _done(app, tid, 120)
    r = t["tulos"]
    true_soh = src.nfp / src.bol * 100
    assert abs(r["yhteenveto"]["kunto_pct"] - true_soh) < 0.2, (r["yhteenveto"]["kunto_pct"], true_soh)
    assert r["kennot"]["lkm"] == _n_arvot(src), (r["kennot"]["lkm"], _n_arvot(src))
    _pdf_check(app, tid, ["Pikatarkastus", src.vin, "ABC-123"])
    print(f"   pikatarkastus: kunto {r['yhteenveto']['kunto_pct']:.1f} %, todellinen {true_soh:.1f} %")
    app.disconnect()

    # Kapasiteettimittaus
    src = _sim(car, soc=0.1, accel=300)
    tid = _start(app, src, "kapasiteetti")
    _phase(app, "odota_lataus", 90)
    src.set_mode("charge", 11.0)
    _phase(app, "lepo_loppu", 400)
    src.set_mode("park")
    t = _done(app, tid, 120)
    r = t["tulos"]
    c = r["kapasiteetti"]
    assert c["valmis"], r["huomiot"]
    _within("kapasiteettimittaus", c["taysi_kwh"], c["epavarmuus_kwh"], src.nfp, 0.025 * src.nfp)
    assert r["paatulos"]["lahde"] == "Kapasiteettimittaus"
    _pdf_check(app, tid, ["Kapasiteettimittaus", src.vin])
    app.disconnect()

    # Ajotesti. Simuloitu aika kulkee nopeutettuna. Jos autossa ei ole elinkaaren energialaskureita (Nissan
    # Leaf), energia lasketaan jännitteestä ja virrasta; silloin nopeutus pidetään pienenä, jotta näytteitä
    # tulee tiheästi myös kuormitetulla testikoneella (oikeassa autossa useita kertoja sekunnissa).
    from akux import polled
    _pm = polled.for_model(_hk(car))
    src = _sim(car, soc=0.95, accel=60 if _pm and not _pm.ELINKAARILASKURIT else 500)
    tid = _start(app, src, "ajotesti")
    _phase(app, "ajo", 90)
    src.set_mode("drive", 20.0)
    assert wait_until(lambda: (app.recorder.progress() or {}).get("tavoite_saavutettu"), 300)
    src.set_mode("park")
    t = _done(app, tid, 120)
    r = t["tulos"]
    pu = r["purku"]
    assert pu["valmis"], r["huomiot"]
    _within("ajotesti", pu["taysi_kwh"], pu["epavarmuus_kwh"], src.nfp, 0.03 * src.nfp)
    assert r["paatulos"]["lahde"] == "Ajotesti", r["huomiot"]
    _pdf_check(app, tid, ["Ajotesti", "Purkumittaus ajossa"])
    app.disconnect()

    # Kuormitustesti
    src = _sim(car, soc=0.7, accel=4, weak_cell=None)
    bad = src.n // 3
    src.r_cell[bad - 1] *= 1.6
    tid = _start(app, src, "kuormitus")
    _phase(app, "kuormitus", 60)
    src.set_mode("kiihdytys")
    assert wait_until(lambda: app.recorder.load_events >= 6, 120)
    src.set_mode("park")
    t = _done(app, tid, 60)
    k = t["tulos"]["kuorma"]
    true_r = sum(src.r_cell) * 1000
    print(f"   kuormitus: resistanssi {k['r_akku_mohm']:.1f} mΩ, todellinen {true_r:.1f} mΩ, "
          f"poikkeava ryhmä {k['r_max_nro']} (asetettu {bad})")
    odotettu = bad
    if getattr(src, "platform", "") == "mg":
        # MG: suurimman resistanssin kenno näkyy lohkonsa matalimpana kennona (arvo 2 × lohko − 1)
        L, i = src.g["lohkot"], bad - 1
        lohko = next(j for j in range(L) if round(j * src.n / L) <= i < round((j + 1) * src.n / L)) + 1
        odotettu = 2 * lohko - 1
    assert k["r_max_nro"] == odotettu, (k["r_max_nro"], odotettu)
    assert abs(k["r_akku_mohm"] - true_r) / true_r < 0.1
    assert "paatulos" not in t["tulos"]
    _pdf_check(app, tid, ["Kuormitustesti", "Kennoryhmät kuormassa"])
    app.disconnect()

    # Pikalataustesti
    src = _sim(car, soc=0.12, accel=60, dc_kw=120.0)
    tid = _start(app, src, "pikalataus")
    _phase(app, "odota_pikalataus", 30)
    src.set_mode("pikalataus")
    _phase(app, "pikalataus", 30)
    assert wait_until(lambda: (app.decoder.state.soc_avg or 0) > 85, 300)
    src.set_mode("park")
    t = _done(app, tid, 120)
    dc = t["tulos"]["pikalataus"]
    print(f"   pikalataus: huippu {dc['huipputeho_kw']:.0f} kW, {dc['energia_kwh']:.1f} kWh, "
          f"jännite-ero {dc['jannite_ero_max_mv']:.0f} mV")
    assert 110 <= dc["huipputeho_kw"] <= 130
    _pdf_check(app, tid, ["Pikalataustesti", "Latausteho"])
    app.disconnect()

    from akux import polled
    if not _hk(car) or polled.for_model(_hk(car)).ITSEPURKAUS_OK:
        check_self_discharge(app, car)

    # Täysi akkutesti
    src = _sim(car, soc=0.95, accel=500)
    tid = _start(app, src, "taysi")
    _phase(app, "ajo", 90)
    src.set_mode("drive", 20.0)
    assert wait_until(lambda: (app.recorder.progress() or {}).get("tavoite_saavutettu"), 300)
    src.set_mode("park")
    _phase(app, "odota_lataus", 90)
    src.set_mode("charge", 11.0)
    _phase(app, "lepo_loppu", 400)
    src.set_mode("park")
    t = _done(app, tid, 120)
    r = t["tulos"]
    y = r["yhdistetty"]
    assert y and y["valmis"], r["huomiot"]
    _within("täysi akkutesti", y["taysi_kwh"], y["epavarmuus_kwh"], src.nfp, 0.02 * src.nfp)
    assert y["yhtapitavat"]
    assert r["yhteenveto"]["kunto_lahde"] == "Täysi akkutesti"
    soh = r["yhteenveto"]["kunto_pct"]
    print(f"   kunto {soh:.1f} %, todellinen {true_soh:.1f} %")
    _pdf_check(app, tid, ["Täysi akkutesti", "Lataus- ja purkumittauksen vertailu"])
    app.disconnect()


# Jatkuvassa integraatiossa koko testisarja ajetaan näillä autoilla (yksi kustakin alustasta ja kemiasta);
# muilla autoilla tarkistetaan datan luku. Kaikki autot: python tests/test_autot_ja_kemiat.py --kaikki
CI_AUTOT = ["m3-lr", "m3-lfp", "my-lr", "ms-85", "kona-64", "leaf-40", "id3-58"]

if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--ci"]:
        for car in ESITTELYAUTOT:
            if car not in CI_AUTOT and _hk(car):
                w = check_hk_decoding(car)
                print(f"OK datan luku {car}: " + ", ".join(f"{k} ±{v:.4g}" for k, v in w.items()))
        args = CI_AUTOT
    cars = list(ESITTELYAUTOT) if not args or args == ["--kaikki"] else args
    for car in cars:
        t0 = time.time()
        variants = [{}]
        if _hk(car):
            w = check_hk_decoding(car)
            print(f"OK datan luku {car}: " + ", ".join(f"{k} ±{v:.4g}" for k, v in w.items()))
            variants = []
        elif ESITTELYAUTOT[car]["opts"].get("platform") == "sx":
            variants += [{"sx_counter_swap": True}, {"sx_current_sign": -1}, {"energy_format": "sx11"},
                         {"sx_counter_swap": True, "sx_current_sign": -1}]
        elif car == "m3-lr":
            variants += [{"energy_format": "vanha"}]
        for kw in variants:
            w = check_decoding(car, **kw)
            print(f"OK datan luku {car} {kw or ''}: " + ", ".join(f"{k} ±{v:.4g}" for k, v in w.items()))
        with _tf.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            run_types(car, tmp)
        print(f"OK {car} ({time.time() - t0:.0f} s)")
