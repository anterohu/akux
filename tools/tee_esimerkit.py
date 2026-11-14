"""Tekee ohjelman mukana tulevat esimerkkimittaukset (akveri/data/esimerkit/*.akveri).

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
os.environ["AKVERI_MITTAUSKANSIO"] = tempfile.mkdtemp(prefix="akveri-esim-")

from akveri import mittaustiedosto  # noqa: E402
from akveri.app import App  # noqa: E402

OUT = ROOT / "akveri" / "data" / "esimerkit"

AUTOT = [
    # auto, nimi, rekisteri, käyttöönotto, mittarilukema, lisämittaukset, lähtövaraus
    ("m3-lfp", "Tesla Model 3 SR+ LFP", "ESIM-301", "15.12.2020", 98500, ["taysi", "pikalataus"], 0.96),
    ("my-lr", "Tesla Model Y Long Range", "ESIM-302", "3.6.2022", 64200, ["ajotesti", "kuormitus"], 0.95),
    ("ms-85", "Tesla Model S 85", "ESIM-303", "20.4.2015", 187000, ["kapasiteetti", "itsepurkaus"], 0.11),
    # Yksi auto kustakin muusta tuetusta merkistä
    ("kona-64", "Hyundai Kona Electric 64 kWh", "ESIM-304", "12.3.2020", 121400, ["kapasiteetti"], 0.11),
    ("ev6-77", "Kia EV6 77,4 kWh", "ESIM-305", "8.9.2022", 58300, ["ajotesti"], 0.95),
    ("leaf-40", "Nissan Leaf 40 kWh", "ESIM-306", "22.5.2019", 93700, ["kapasiteetti"], 0.11),
    ("id3-58", "Volkswagen ID.3 Pro 58 kWh", "ESIM-307", "17.6.2021", 76800, ["taysi"], 0.96),
    ("enyaq-77", "Škoda Enyaq 80 77 kWh", "ESIM-308", "2.2.2022", 69100, ["kapasiteetti"], 0.11),
    ("q4-77", "Audi Q4 40 e-tron 77 kWh", "ESIM-309", "30.11.2022", 44200, ["ajotesti"], 0.95),
    ("born-58", "Cupra Born 58 kWh", "ESIM-310", "14.4.2022", 51600, ["kapasiteetti"], 0.11),
    ("mg4-64", "MG4 Electric 64 kWh", "ESIM-311", "21.3.2023", 38900, ["kapasiteetti"], 0.11),
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


def main(vain=None):
    """vain: lista esittelyautoja (esim. mg4-64), jolloin vain niiden esimerkit tehdään uudelleen."""
    OUT.mkdir(parents=True, exist_ok=True)
    for auto, nimi, reg, kayttoon, km, extra, soc in AUTOT:
        if vain and auto not in vain:
            continue
        for f in OUT.glob(f"{reg}_*.ak*"):
            f.unlink()
    for auto, nimi, reg, kayttoon, km, extra, soc in AUTOT:
        if vain and auto not in vain:
            continue
        tmp = tempfile.mkdtemp()
        app = App(tmp)
        app.storage.save_settings(SETTINGS)
        src = app.connect("demo", auto=auto, soc=soc, accel=300)
        wait(lambda: app.decoder.state.vin and app.decoder.state.nfp_kwh and app.decoder.state.brick_count, 60)
        from akveri.simulator import ESITTELYAUTOT
        vid = app.storage.add_vehicle({"vin": app.decoder.state.vin, "nimi": nimi, "rekisteri": reg,
                                       "malli_id": ESITTELYAUTOT[auto].get("malli_id"),
                                       "kayttoonotto": kayttoon, "omistaja": "Esimerkkiasiakas",
                                       "lisatiedot": "Esimerkkiauto. Mittaukset on tehty AKVERIn esittelytilassa."})
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
                src.set_soc(0.6)                  # lähtöehto: varaus 40–80 %
                wait(lambda: 40 <= (app.decoder.state.soc_ui or app.decoder.state.soc_avg or 0) <= 80, 60)
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
            (OUT / f"{reg}_{app.storage.test(t)['tyyppi']}.akveri").write_bytes(data)
            print(name, len(data) // 1024, "kt")
        app.storage.close()


if __name__ == "__main__":
    main(sys.argv[1:] or None)
