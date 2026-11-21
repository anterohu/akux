"""Mittarilukema kysytään mittauksen lopussa, jos auto ei ilmoittanut sitä, ja autokohtainen kokemus tallennetaan."""
import json
import os
import sys
import tempfile as _tf
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AKVERI_MITTAUSKANSIO", _tf.mkdtemp(prefix="akveri-testi-"))

from test_autot_ja_kemiat import _connect, _sim, _vid  # noqa: E402
from test_testityypit import _done, wait_until  # noqa: E402


def test_mittarilukema_kysytaan_lopussa():
    from akveri.app import App
    with _tf.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        app = App(tmp)
        src = _sim("m3-lr", soc=0.6, accel=20)
        _connect(app, src)
        tid = app.start_test(vehicle_id=_vid(app), tyyppi="pikatarkastus", mittarilukema=None, mittaaja="Testi")
        rec = app.recorder
        rec._mittarilukema_puuttuu = lambda: not rec.odo_kysytty   # oikea auto, joka ei ilmoita mittarilukemaa
        assert wait_until(lambda: rec.vaihe == "mittarilukema", 120), rec.vaihe
        time.sleep(1.5)
        assert rec.vaihe == "mittarilukema" and (app.storage.test(tid) or {}).get("tila") != "valmis"
        rec.anna_mittarilukema(123456)
        t = _done(app, tid, 60)
        assert t["mittarilukema"] == 123456
        assert t["tulos"]["ajoneuvo"]["mittarilukema_km"] == 123456
        app.disconnect()


def test_kokemus_ei_sisalla_tunnisteita():
    """Kokemuksesta lähtee vain valmistenumeron alku, sovitin ja kyselyjen tilanne."""
    from akveri import kokemukset
    from test_kyselylukija import _meb_auto
    src, dec = _meb_auto(soh_vastaa=False, energia_vastaa=False)
    dec.state.vin = "WVGZZZE2ZMP032376"
    src.start(dec.feed)
    end = time.time() + 20
    while time.time() < end and not (len(dec.state.bricks) >= 96 and sum(src.kyselytilasto.get(0x7B50CE, [0, 0])[:2]) >= 2):
        time.sleep(0.1)
    src.stop()
    src.info = {"sovitin": "OBDLink EX"}
    app = types.SimpleNamespace(source=src, decoder=dec, storage=None)
    k = kokemukset.kokoa(app, "estetty", "pikatarkastus")
    assert k["vin_alku"] == "WVGZZZE2" and "WVGZZZE2ZMP032376" not in json.dumps(k)
    assert k["kyselyt"]["BMS 2250CE"]["kielto"] == 0x31 and k["kyselyt"]["BMS 2250CE"]["vastauksia"] == 0
    assert k["kyselyt"]["BMS 221E3B"]["vastauksia"] > 0
    assert k["kunto_saatu"] is False and k["sovitin"] == "OBDLink EX" and k["alusta"] == "meb"
