"""Mittaustiedosto (.akux).

Jokainen mittaus tallennetaan omaksi tiedostokseen, joka sisältää kaiken: auton
tiedot, mittausnäytteet, kennoryhmien jännitteet, tapahtumat, tuloksen,
muuttamattoman raakadatan ja PDF-raportin. Tiedoston voi säilyttää missä
kansiossa tahansa, ja sen voi avata missä tahansa AKUX-versiossa.

Tiedosto on zip-paketti, jonka sisältö on kuvattu tiedostossa mittaus.json.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

from . import NIMI, VERSIO

MUOTO = "akux-mittaus"
MUOTO_VERSIO = 1
PAATE = ".akux"

# Android-sovellus tallentaa tiedostot puhelimen Lataukset-kansioon (ks. android.py)
SAVE_HOOK = None


def default_folder() -> Path:
    env = os.environ.get("AKUX_MITTAUSKANSIO")
    if env:
        return Path(env)
    home = Path.home()
    if sys.platform.startswith("win"):
        docs = Path(os.environ.get("USERPROFILE", home)) / "Documents"
        return docs / "Akux" / "Mittaukset"
    return home / "Akux" / "Mittaukset"


def _safe(txt: str) -> str:
    return re.sub(r"[^A-Za-z0-9ÅÄÖåäö_-]+", "-", txt or "").strip("-") or "auto"


def file_name(test: dict, vehicle: dict | None) -> str:
    v = vehicle or {}
    who = v.get("rekisteri") or v.get("nimi") or (v.get("vin") or "")[-6:] or "auto"
    day = time.strftime("%Y-%m-%d", time.localtime(test["aloitettu"]))
    kind = re.sub(r"[^a-z_]", "", str(test.get("tyyppi") or "mittaus")) or "mittaus"
    return f"AKUX_{_safe(who)}_{day}_{kind}_{test['id']:05d}"


def export(storage, tid: int, with_report: bool = True) -> tuple[str, bytes]:
    """Palauttaa (tiedostonimi, sisältö)."""
    test = storage.test(tid)
    if not test:
        raise ValueError("Mittausta ei löydy.")
    vehicle = storage.vehicle(test["vehicle_id"])
    name = file_name(test, vehicle)
    manifest = {
        "muoto": MUOTO, "muoto_versio": MUOTO_VERSIO, "ohjelma": NIMI, "ohjelman_versio": VERSIO,
        "tallennettu": time.time(),
        "mittaus": {k: v for k, v in test.items() if k not in ("raakadata",)},
        "ajoneuvo": vehicle,
        "tiedostot": {},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def put(path, data: bytes, compress=True):
            z.writestr(zipfile.ZipInfo(path, time.localtime()[:6]), data,
                       compress_type=zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED)
            manifest["tiedostot"][path] = hashlib.sha256(data).hexdigest()

        put("naytteet.json", json.dumps(storage.samples(tid), ensure_ascii=False).encode("utf-8"))
        put("kennot.json", json.dumps(storage.snapshots(tid), ensure_ascii=False).encode("utf-8"))
        put("tapahtumat.json", json.dumps(storage.events(tid), ensure_ascii=False).encode("utf-8"))
        photo = storage.vehicle_photo(test["vehicle_id"])
        if photo.exists():
            put("auton_kuva.jpg", photo.read_bytes(), compress=False)
        raw = test.get("raakadata")
        if raw and Path(raw).exists():
            put("raakadata.csv.gz", Path(raw).read_bytes(), compress=False)
        if with_report and test["tila"] == "valmis" and (test.get("tulos") or {}).get("yhteenveto"):
            try:
                from . import report
                pdf = report.build(storage, tid)
                put("raportti.pdf", pdf.read_bytes(), compress=False)
            except Exception:  # noqa: BLE001
                pass
        z.writestr("mittaus.json", json.dumps(manifest, ensure_ascii=False, indent=1, default=str))
    return name + PAATE, buf.getvalue()


def save_to_folder(storage, tid: int, folder: Path | None = None) -> list[Path]:
    """Tallentaa mittaustiedoston ja raportin kansioon. Palauttaa tallennetut polut."""
    name, data = export(storage, tid)
    if SAVE_HOOK:
        saved = [SAVE_HOOK(name, "application/octet-stream", data)]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if "raportti.pdf" in z.namelist():
                saved.append(SAVE_HOOK(name[: -len(PAATE)] + ".pdf", "application/pdf", z.read("raportti.pdf")))
        return [Path(str(p)) for p in saved if p]
    folder = Path(folder or storage.settings().get("mittaus_kansio") or default_folder())
    folder.mkdir(parents=True, exist_ok=True)
    out = [folder / name]
    out[0].write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if "raportti.pdf" in z.namelist():
            pdf = folder / (name[: -len(PAATE)] + ".pdf")
            pdf.write_bytes(z.read("raportti.pdf"))
            out.append(pdf)
    return out


def inspect(data: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        m = json.loads(z.read("mittaus.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
        raise ValueError("Tiedosto ei ole AKUXin mittaustiedosto.")
    if m.get("muoto") != MUOTO:
        raise ValueError("Tiedosto ei ole AKUXin mittaustiedosto.")
    if m.get("muoto_versio", 1) > MUOTO_VERSIO:
        raise ValueError("Mittaustiedosto on tehty uudemmalla AKUX-versiolla. Päivitä AKUX ja avaa tiedosto uudelleen.")
    for path, digest in (m.get("tiedostot") or {}).items():
        if hashlib.sha256(z.read(path)).hexdigest() != digest:
            raise ValueError("Mittaustiedosto on vioittunut tai sitä on muutettu.")
    return m


def import_file(storage, data: bytes, merkitse: bool = True) -> dict:
    """Avaa mittaustiedoston ohjelmaan. Auto yhdistetään valmistenumeron perusteella.
    Jos sama mittaus on jo ohjelmassa, sitä ei tuoda uudelleen."""
    m = inspect(data)
    z = zipfile.ZipFile(io.BytesIO(data))
    t = m["mittaus"]
    v = m.get("ajoneuvo") or {}

    # Sama mittaus on jo ohjelmassa, jos raakadatan tarkiste täsmää
    if t.get("tarkiste"):
        for old in storage.tests():
            if old.get("tarkiste") == t["tarkiste"]:
                return {"id": old["id"], "uusi": False, "ajoneuvo_id": old["vehicle_id"]}

    existing = storage.find_vehicle_by_vin(v["vin"]) if v.get("vin") else None
    if existing:
        vid = existing["id"]
        new_vehicle = False
    else:
        vid = storage.add_vehicle({k: v.get(k) for k in storage.VEHICLE_FIELDS} | {"opitut": v.get("opitut") or {}})
        new_vehicle = True

    if "auton_kuva.jpg" in z.namelist() and not storage.vehicle_photo(vid).exists():
        try:
            storage.save_vehicle_photo(vid, z.read("auton_kuva.jpg"))
        except ValueError:
            pass
    tid = storage.add_test(vid, t["tyyppi"], t.get("mittarilukema"), t.get("mittaaja") or "", t.get("lisatiedot") or "")
    raw_path = None
    if "raakadata.csv.gz" in z.namelist():
        raw_path = storage.dir / "raakadata" / f"mittaus_{tid:05d}.csv.gz"
        raw_path.write_bytes(z.read("raakadata.csv.gz"))
    storage.update_test(tid, tila=t.get("tila") or "valmis", aloitettu=t.get("aloitettu"),
                        paattynyt=t.get("paattynyt"), tulos=t.get("tulos") or {},
                        raakadata=str(raw_path) if raw_path else None, tarkiste=t.get("tarkiste"))
    cols = ["t", "vaihe", "v", "i", "soc_ui", "soc_avg", "nfp", "ner", "t_min", "t_max",
            "c_min", "c_max", "e_in", "e_out", "ah_in"]
    samples = json.loads(z.read("naytteet.json"))
    storage.add_samples(tid, [tuple(s.get(c) for c in cols) for s in samples])
    for s in json.loads(z.read("kennot.json")):
        storage.add_snapshot(tid, s["t"], s["nimi"], s["data"])
    for e in json.loads(z.read("tapahtumat.json")):
        storage.add_event(tid, e["t"], e["teksti"])
    if merkitse:
        storage.add_event(tid, time.time(), f"Mittaus avattiin tiedostosta (tallennettu versiolla {m.get('ohjelman_versio')})")
    return {"id": tid, "uusi": True, "ajoneuvo_id": vid, "uusi_ajoneuvo": new_vehicle}
