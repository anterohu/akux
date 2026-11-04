"""Mittaustiedosto (.akux): automaattinen tallennus kansioon, avaus toisessa asennuksessa,
eheyden tarkistus ja raportin muodostus avatusta tiedostosta."""
import io
import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akux.app import App  # noqa: E402
from akux import mittaustiedosto, report  # noqa: E402
from akux.server import Api  # noqa: E402


def wait(cond, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_mittaustiedosto():
    with tempfile.TemporaryDirectory() as a_dir, tempfile.TemporaryDirectory() as b_dir, \
            tempfile.TemporaryDirectory() as folder:
        # Ensimmäinen asennus: mittaus tallentuu automaattisesti valittuun kansioon
        a = App(a_dir)
        a.storage.save_settings({"mittaus_kansio": folder})
        a.connect("demo", soc=0.6, accel=30)
        assert wait(lambda: a.decoder.state.brick_count and a.decoder.state.nfp_kwh, 20)
        vid = a.storage.add_vehicle({"vin": a.decoder.state.vin, "rekisteri": "ABC-123", "kayttoonotto": "14.5.2020"})
        tid = a.start_test(vehicle_id=vid, tyyppi="pikatarkastus", mittarilukema=112000)
        assert wait(lambda: not a.recorder.active, 120)
        a.disconnect()
        files = sorted(os.listdir(folder))
        print("Tallennetut:", files)
        akux_files = [f for f in files if f.endswith(".akux")]
        pdf_files = [f for f in files if f.endswith(".pdf")]
        assert len(akux_files) == 1 and len(pdf_files) == 1
        assert akux_files[0].startswith("Akux_ABC-123_") and "pikatarkastus" in akux_files[0]
        data = (Path(folder) / akux_files[0]).read_bytes()
        original = a.storage.test(tid)

        # Toinen asennus (esimerkiksi uusi tietokone tai uusi versio): tiedosto avautuu oikein
        b = App(b_dir)
        r = mittaustiedosto.import_file(b.storage, data)
        assert r["uusi"] and r["uusi_ajoneuvo"]
        t = b.storage.test(r["id"])
        v = b.storage.vehicle(r["ajoneuvo_id"])
        assert v["rekisteri"] == "ABC-123" and v["kayttoonotto"] == "14.5.2020"
        assert t["tila"] == "valmis" and t["tarkiste"] == original["tarkiste"]
        assert t["tulos"]["yhteenveto"]["kunto_pct"] == original["tulos"]["yhteenveto"]["kunto_pct"]
        assert len(b.storage.samples(r["id"])) == len(a.storage.samples(tid))
        assert len(b.storage.snapshots(r["id"])) == len(a.storage.snapshots(tid))
        api = Api(b)
        assert api.tarkista({}, {}, r["id"])["ok"], "raakadata ei täsmää avauksen jälkeen"
        pdf = report.build(b.storage, r["id"])
        assert pdf.stat().st_size > 50000

        # Sama tiedosto uudelleen: ei tuoda kahdesti
        r2 = mittaustiedosto.import_file(b.storage, data)
        assert not r2["uusi"] and r2["id"] == r["id"]

        # Muutettu tiedosto hylätään
        zin = zipfile.ZipFile(io.BytesIO(data))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zout:
            for n in zin.namelist():
                b_ = zin.read(n)
                if n == "naytteet.json":
                    b_ = b_.replace(b'"v": 3', b'"v": 4', 1) + b" "
                zout.writestr(n, b_)
        try:
            mittaustiedosto.import_file(b.storage, buf.getvalue())
            raise AssertionError("muutettu tiedosto hyväksyttiin")
        except ValueError as e:
            assert "muutettu" in str(e)

        # Uudemman version tiedosto: selkeä ilmoitus
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zout:
            m = json.loads(zin.read("mittaus.json"))
            m["muoto_versio"] = 99
            zout.writestr("mittaus.json", json.dumps(m))
        try:
            mittaustiedosto.import_file(b.storage, buf.getvalue())
            raise AssertionError("uudemman muodon tiedosto hyväksyttiin")
        except ValueError as e:
            assert "Päivitä Akux" in str(e)

        # Väärä tiedosto
        try:
            mittaustiedosto.import_file(b.storage, b"ei zip")
            raise AssertionError("väärä tiedosto hyväksyttiin")
        except ValueError:
            pass
        a.storage.close()
        b.storage.close()
        print("OK mittaustiedosto")


if __name__ == "__main__":
    test_mittaustiedosto()
