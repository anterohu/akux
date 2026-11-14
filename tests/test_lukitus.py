"""Lukitustesti: kehysten käsittely ja käyttäjän toiminnot rinnakkain eivät saa lukita ohjelmaa.

Tilanne vastaa sitä, että käyttäjä ohittaa vaiheen samalla hetkellä, kun autosta saapuu dataa:
mittaus pitää omaa lukkoaan ja lukee dekooderin tilan, ja dekooderi kutsuu mittauksen kuuntelijaa.
"""
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akveri.decoder import TeslaDecoder, ID_HV  # noqa: E402


def test_ei_lukitu():
    dec = TeslaDecoder()
    toinen = threading.RLock()          # mittauksen lukko
    kutsuja = [0]

    def kuuntelija(t, v, i):
        with toinen:
            kutsuja[0] += 1

    dec.add_hv_listener(kuuntelija)
    loppu = time.time() + 3
    data = struct.pack("<HhH", 35000, -100, 0) + b"\0\0"

    def syotto():
        k = 0
        while time.time() < loppu:
            k += 1
            dec.feed(k * 0.01, ID_HV, data)

    def kayttaja():
        while time.time() < loppu:
            with toinen:
                dec.snapshot()

    saikeet = [threading.Thread(target=syotto, daemon=True), threading.Thread(target=kayttaja, daemon=True)]
    for s in saikeet:
        s.start()
    for s in saikeet:
        s.join(15)
        assert not s.is_alive(), "ohjelma lukittui (deadlock)"
    assert kutsuja[0] > 100, kutsuja[0]
    assert abs(dec.state.pack_v - 350.0) < 0.01


if __name__ == "__main__":
    test_ei_lukitu()
    print("OK test_ei_lukitu")
