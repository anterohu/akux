"""Kyselyihin perustuvat alustat (Hyundai ja Kia, Nissan Leaf, Volkswagen-konsernin MEB, MG).

Teslan akunhallinta lähettää tietonsa väylälle jatkuvasti, ja AKVERI vain kuuntelee. Muiden merkkien
akunhallinta vastaa vain kyselyihin, joten sovitin kysyy tiedot vuorotellen. Jokainen alusta on oma
moduulinsa, jolla on sama rajapinta:

    PLATFORM, NIMI, MERKIT, KUVAUS, TUNNISTEET, PAKOLLISET, HANDLERS,
    RESOLUUTIO_MV, ITSEPURKAUS_OK, LAHDE, OHJE, RX,
    requests_for(model) -> (toistuvat, harvat), decoder_opts(model) -> dict,
    simulator(model, **opts) -> esittelytilan simuloitu auto.
"""
from __future__ import annotations

_MODULES = ("hkmc", "leaf", "meb", "mg")


def module(platform: str | None):
    # Moduulit tuodaan suoraan nimeltä, jotta Windows- ja Android-paketointi löytää ne
    if platform == "hkmc":
        from . import hkmc
        return hkmc
    if platform == "leaf":
        from . import leaf
        return leaf
    if platform == "meb":
        from . import meb
        return meb
    if platform == "mg":
        from . import mg
        return mg
    return None


def is_polled(platform: str | None) -> bool:
    return module(platform) is not None


def platforms() -> list[str]:
    return [p for p in _MODULES if module(p)]


def for_model(model: dict | None):
    return module((model or {}).get("alusta")) if model else None


def for_brand(brand: str | None):
    for p in platforms():
        if brand in module(p).MERKIT:
            return module(p)
    return None
