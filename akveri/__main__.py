"""Käynnistys: python -m akveri [--portti 8765] [--ei-selainta] [--verkko]"""
import argparse

from .server import serve


def main():
    p = argparse.ArgumentParser(prog="akveri", description="Ajoakun kunnon ja kapasiteetin mittaus")
    p.add_argument("--portti", type=int, default=8765, help="käyttöliittymän verkkoportti (oletus 8765)")
    p.add_argument("--data", default=None, help="tietojen tallennuskansio")
    p.add_argument("--ei-selainta", action="store_true", help="älä avaa selainta automaattisesti")
    p.add_argument("--verkko", action="store_true",
                   help="salli käyttö muilta lähiverkon laitteilta (esim. puhelimella)")
    a = p.parse_args()
    first = True
    while True:
        action = serve(host="0.0.0.0" if a.verkko else None, port=a.portti, data_dir=a.data,
                       open_browser=(not a.ei_selainta) and first)
        first = False
        if action != "uudelleen":
            break


if __name__ == "__main__":
    main()
