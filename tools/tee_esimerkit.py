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
    # auto, nimi, rekisteri, käyttöönotto, mittarilukema, kapasiteetti?, lähtövaraus
    ("m3-lfp", "Model 3 SR+ LFP", "ESIM-301", "15.12.2020", 98500, True, 0.09),
    ("my-lr", "Model Y Long Range", "ESIM-302", "3.6.2022", 64200, False, 0.62),
    ("ms-85", "Model S 85", "ESIM-303", "20.4.2015", 187000, True, 0.11),
]


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
    for auto, nimi, reg, kayttoon, km, cap, soc in AUTOT:
        tmp = tempfile.mkdtemp()
        app = App(tmp)
        app.storage.save_settings({"lepo_alku_min": 30, "lepo_loppu_min": 30, "mittaus_tallennus": False,
                                   "ilmoitukset_kaytossa": False})
        src = app.connect("demo", auto=auto, soc=soc, accel=300)
        src.set_mode("drive", 25.0)
        wait(lambda: app.decoder.state.vin and app.decoder.state.nfp_kwh and app.decoder.state.brick_count, 60)
        src.set_mode("park")
        vid = app.storage.add_vehicle({"vin": app.decoder.state.vin, "nimi": nimi, "rekisteri": reg,
                                       "kayttoonotto": kayttoon, "omistaja": "Esimerkkiasiakas",
                                       "lisatiedot": "Esimerkkiauto. Mittaukset on tehty Akuxin esittelytilassa."})
        app.storage.learn(vid, {"esimerkki": True})
        tids = []
        tid = app.start_test(vehicle_id=vid, tyyppi="pikatarkastus", mittarilukema=km, mittaaja="Esimerkki")
        wait(lambda: not app.recorder.active, 300)
        tids.append(tid)
        if cap:
            tid = app.start_test(vehicle_id=vid, tyyppi="kapasiteetti", mittarilukema=km, mittaaja="Esimerkki")
            wait(lambda: app.recorder.vaihe == "odota_lataus", 300)
            src.set_mode("charge", 9.0)
            wait(lambda: app.recorder.vaihe == "lepo_loppu", 900)
            src.set_mode("park")
            wait(lambda: not app.recorder.active, 300)
            tids.append(tid)
        app.disconnect()
        for t in tids:
            assert app.storage.test(t)["tila"] == "valmis", (auto, t)
            name, data = mittaustiedosto.export(app.storage, t, with_report=False)
            (OUT / f"{reg}_{app.storage.test(t)['tyyppi']}.akux").write_bytes(data)
            print(name, len(data) // 1024, "kt")
        app.storage.close()


if __name__ == "__main__":
    main()
