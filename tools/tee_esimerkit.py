"""Tekee ohjelman mukana tulevat esimerkkimittaukset (akux/data/esimerkit/*.akux).

Mittaukset tehdään esittelytilan simulaattorilla. Aja uudelleen, jos mittaustiedoston
muoto tai analyysi muuttuu:  python tools/tee_esimerkit.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["AKUX_MITTAUSKANSIO"] = tempfile.mkdtemp(prefix="akux-esim-")

from akux import mittaustiedosto  # noqa: E402
from akux.app import App  # noqa: E402

OUT = ROOT / "akux" / "data" / "esimerkit"

AUTOT = [
    # auto, nimi, rekisteri, käyttöönotto, mittarilukema, lisämittaukset, lähtövaraus
    ("m3-lfp", "Model 3 SR+ LFP", "ESIM-301", "15.12.2020", 98500, ["taysi", "pikalataus"], 0.96),
    ("my-lr", "Model Y Long Range", "ESIM-302", "3.6.2022", 64200, ["ajotesti", "kuormitus"], 0.95),
    ("ms-85", "Model S 85", "ESIM-303", "20.4.2015", 187000, ["kapasiteetti", "itsepurkaus"], 0.11),
]
SETTINGS = {"lepo_alku_min": 30, "lepo_loppu_min": 30, "ajo_lepo_min": 15, "itsepurkaus_lepo_min": 30,
            "itsepurkaus_tunnit": 9, "kuormitus_tapahtumat": 6, "mittaus_tallennus": False,
            "ilmoitukset_kaytossa": False}


def wait(cond, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    raise TimeoutError


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.akux"):
        f.unlink()
    for auto, nimi, reg, kayttoon, km, extra, soc in AUTOT:
        tmp = tempfile.mkdtemp()
        app = App(tmp)
        app.storage.save_settings(SETTINGS)
        src = app.connect("demo", auto=auto, soc=soc, accel=300)
        wait(lambda: app.decoder.state.vin and app.decoder.state.nfp_kwh and app.decoder.state.brick_count, 60)
        vid = app.storage.add_vehicle({"vin": app.decoder.state.vin, "nimi": nimi, "rekisteri": reg,
                                       "kayttoonotto": kayttoon, "omistaja": "Esimerkkiasiakas",
                                       "lisatiedot": "Esimerkkiauto. Mittaukset on tehty Akuxin esittelytilassa."})
        app.storage.learn(vid, {"esimerkki": True})
        tids = []

        def run(tyyppi, steps):
            tid = app.start_test(vehicle_id=vid, tyyppi=tyyppi, mittarilukema=km, mittaaja="Esimerkki")
            for fn in steps:
                fn()
            wait(lambda: not app.recorder.active, 900)
            tids.append(tid)

        phase = lambda v, t=900: (lambda: wait(lambda: app.recorder.vaihe == v, t))  # noqa: E731
        mode = lambda m, p=None: (lambda: src.set_mode(m, p))  # noqa: E731
        accel = lambda a: (lambda: src.set_accel(a))  # noqa: E731
        reached = lambda: wait(lambda: (app.recorder.progress() or {}).get("tavoite_saavutettu"), 900)  # noqa: E731
        src.set_accel(20)
        run("pikatarkastus", [])
        src.set_accel(300)
        for tyyppi in extra:
            if tyyppi == "kapasiteetti":
                src.set_soc(soc)
                run(tyyppi, [phase("odota_lataus"), mode("charge", 9.0), phase("lepo_loppu"), mode("park")])
            elif tyyppi in ("taysi", "ajotesti"):
                src.set_soc(soc)
                run(tyyppi, [phase("ajo"), mode("drive", 22.0), reached, mode("park")] + (
                    [phase("odota_lataus"), mode("charge", 9.0), phase("lepo_loppu"), mode("park")]
                    if tyyppi == "taysi" else []))
            elif tyyppi == "kuormitus":
                run(tyyppi, [accel(4), phase("kuormitus"), mode("kiihdytys"),
                             lambda: wait(lambda: app.recorder.load_events >= 6, 300), mode("park")])
                src.set_accel(300)
            elif tyyppi == "pikalataus":
                src.set_soc(0.12)
                run(tyyppi, [accel(60), phase("odota_pikalataus"), mode("pikalataus"), phase("pikalataus"),
                             lambda: wait(lambda: (app.decoder.state.soc_avg or 0) > 82, 600), mode("park")])
                src.set_accel(300)
            elif tyyppi == "itsepurkaus":
                src.set_soc(0.7)
                run(tyyppi, [accel(20), phase("odotus"), accel(600), phase("itse_loppu"), accel(20)])
                src.set_accel(300)
        app.disconnect()
        for t in tids:
            assert app.storage.test(t)["tila"] == "valmis", (auto, t)
            name, data = mittaustiedosto.export(app.storage, t, with_report=False)
            (OUT / f"{reg}_{app.storage.test(t)['tyyppi']}.akux").write_bytes(data)
            print(name, len(data) // 1024, "kt")
        app.storage.close()


if __name__ == "__main__":
    main()
