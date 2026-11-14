"""Yhteensopivuus kehittäjän omien, ennen nimenvaihtoa tehtyjen tietojen kanssa.

Ohjelman aiempi työnimi näkyy vain tässä tiedostossa: vanha tietokantatiedosto nimetään uudelleen, ja vanhat
varmuuskopiot ja mittaustiedostot avautuvat. Kun kaikki omat laitteet on päivitetty, tämän tiedoston voi poistaa.
"""
from __future__ import annotations

from pathlib import Path

_VANHA = "ak" + "ux"
VANHA_TIETOKANTA = f"{_VANHA}.db"
VANHA_VARMUUSKOPIOTIEDOT = f"{_VANHA.upper()}-VARMUUSKOPIO.json"
VANHA_MUOTO = f"{_VANHA}-mittaus"


def siirra_tietokanta(kansio: Path, uusi: str) -> None:
    """Nimeää vanhan tietokantatiedoston uudelleen, jos uutta ei vielä ole."""
    vanha = kansio / VANHA_TIETOKANTA
    if vanha.exists() and not (kansio / uusi).exists():
        try:
            vanha.rename(kansio / uusi)
            for liite in ("-wal", "-shm"):
                v = kansio / (VANHA_TIETOKANTA + liite)
                if v.exists():
                    v.rename(kansio / (uusi + liite))
        except OSError:
            pass
