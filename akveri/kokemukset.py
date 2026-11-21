"""Autokohtaiset kokemukset akveri.fi-palveluun: mihin tietoihin auto vastasi ja mihin ei.

Kokemus tallennetaan jokaisesta oikean auton mittauksesta lopputuloksesta riippumatta (valmis, hylätty, keskeytetty)
ja myös silloin, kun mittausta ei voitu aloittaa (estetty). Tiedot lähetetään, kun verkkoyhteys on käytettävissä.
Tunnisteita ei lähetetä: valmistenumerosta vain 8 ensimmäistä merkkiä (valmistaja ja mallikoodi), ei rekisterinumeroa,
mittaajaa, raporttia eikä tarkkaa aikaa.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import VERSIO, polled, profiles
from .decoder import kuvaus


def _kansio(storage) -> Path:
    k = Path(storage.dir) / "kokemukset"
    k.mkdir(parents=True, exist_ok=True)
    return k


def kokoa(app, tila: str, tyyppi: str = "", vehicle_id=None) -> dict | None:
    """Kokoaa kokemuksen nykyisestä yhteydestä. None esittelytilassa tai ilman yhteyttä."""
    src = app.source
    if not src or src.simulated:
        return None
    dec = app.decoder
    st = dec.state
    platform = dec.state.platform
    v = app.storage.vehicle(vehicle_id) if vehicle_id else None
    model = profiles.get((v or {}).get("malli_id")) if v and v.get("malli_id") else None
    vin = (st.vin or (v or {}).get("vin") or "").upper()
    kyselyt = {}
    pm = polled.module(platform)
    tilasto = getattr(src, "kyselytilasto", None)
    if tilasto:
        for cid, ks in tilasto.items():
            nimi = (getattr(pm, "NAYTTO", {}) or {}).get(cid) if pm else None
            kyselyt[(nimi or f"0x{cid:X}")[:40]] = {"vastauksia": ks[0], "ei_vastausta": ks[1],
                                                    "kielto": ks[3] if len(ks) > 3 else None, "pituus": ks[2]}
    else:
        # Tesla: auto lähettää viestit itse. Tallennetaan, mitkä ohjelman käyttämistä viesteistä kulkivat liitännässä.
        maarat = dec.counts()
        from .decoder import M3_TUNNISTEET, SX_TUNNISTEET  # noqa: PLC0415
        tunnisteet = SX_TUNNISTEET if platform == "sx" else M3_TUNNISTEET
        for cid in tunnisteet:
            n = maarat.get(cid, 0)
            kyselyt[f"0x{cid:03X} {kuvaus(cid, platform) or ''}".strip()[:40]] = {
                "vastauksia": n, "ei_vastausta": 0 if n else 1, "kielto": None, "pituus": None}
    vm = (v or {}).get("vuosimalli")
    return {
        "versio": VERSIO, "tila": tila, "mittaustyyppi": tyyppi or "",
        "alusta": platform or "", "malli_id": (model or {}).get("id") or "",
        "merkki": (v or {}).get("merkki") or "", "malli": (v or {}).get("malli") or (model or {}).get("nimi") or "",
        "vuosimalli": int(vm) if str(vm or "").isdigit() else None,
        "vin_alku": vin[:8] if len(vin) == 17 else None,
        "sovitin": str((src.info or {}).get("sovitin") or "")[:60],
        "kunto_saatu": st.nfp_kwh is not None, "mittarilukema_autosta": bool(st.odometer_km), "vin_autosta": bool(st.vin),
        "kennoryhmat_autosta": st.brick_count or len(st.bricks) or 0,
        "kennoryhmat_mallissa": (model or {}).get("sarjakennot"),
        "kyselyt": kyselyt,
    }


def tallenna(app, tila: str, tyyppi: str = "", vehicle_id=None) -> None:
    """Tallentaa kokemuksen lähetettäväksi. Virhe ei koskaan estä mittausta."""
    try:
        k = kokoa(app, tila, tyyppi, vehicle_id)
        if k:
            (_kansio(app.storage) / f"{time.time():.3f}.json").write_text(json.dumps(k, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def odottavia(storage) -> bool:
    try:
        return any(_kansio(storage).glob("*.json"))
    except OSError:
        return False


def laheta(krediitit, storage) -> int:
    """Lähettää odottavat kokemukset. Lähetetty tiedosto poistetaan; epäonnistunut odottaa seuraavaa kertaa."""
    from .krediitit import PalveluVirhe  # noqa: PLC0415
    n = 0
    for p in sorted(_kansio(storage).glob("*.json"))[:50]:
        try:
            body = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            p.unlink(missing_ok=True)
            continue
        try:
            krediitit._kutsu("POST", "/api/v1/kokemus", body)
        except PalveluVirhe as e:
            if e.status in (400, 413):
                p.unlink(missing_ok=True)      # palvelu ei hyväksy tiedostoa: ei yritetä uudelleen
                continue
            break                              # ei yhteyttä: yritetään myöhemmin
        p.unlink(missing_ok=True)
        n += 1
    return n
