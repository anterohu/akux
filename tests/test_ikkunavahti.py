"""Ikkunavahti: kiireinen palvelin ei saa sulkea ikkunaa, sammunut palvelin sulkee sen.

Ajo: python tests/test_ikkunavahti.py
"""
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akveri.launcher import watch_server  # noqa: E402


def test_kiireinen_ja_sammunut():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(50)                       # hyväksyy yhteydet, mutta ei koskaan vastaa (kiireinen palvelin)
    port = srv.getsockname()[1]
    closed = []
    t = threading.Thread(target=watch_server, args=(lambda: closed.append(time.time()), port),
                         kwargs={"poll": 0.1, "down_limit": 1.0, "ping": False}, daemon=True)
    t.start()
    time.sleep(3)
    assert not closed, "kiireinen palvelin sulki ikkunan"
    srv.close()                          # palvelin sammuu
    t0 = time.time()
    t.join(10)
    assert closed, "ikkuna ei sulkeutunut, vaikka palvelin sammui"
    assert 0.9 <= closed[0] - t0 < 5, closed[0] - t0


if __name__ == "__main__":
    test_kiireinen_ja_sammunut()
    print("OK test_kiireinen_ja_sammunut")
