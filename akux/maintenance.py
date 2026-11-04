"""Ylläpito: varmuuskopiot, palautus, päivitys zip-paketista ja laaduntarkistus."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from . import NIMI, VERSIO

PKG = Path(__file__).parent


# ----------------------------------------------------------------------
# Varmuuskopio ja palautus
# ----------------------------------------------------------------------
def backup(storage) -> Path:
    """Tekee koko tietokansiosta zip-varmuuskopion. Tietokanta kopioidaan SQLiten
    omalla varmuuskopiotoiminnolla, joten kopio on eheä myös mittauksen aikana."""
    out_dir = storage.dir / "varmuuskopiot"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    out = out_dir / f"Akux-varmuuskopio_{stamp}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / "akux.db"
        with storage.lock:
            dst = sqlite3.connect(db_copy)
            storage.db.backup(dst)
            dst.close()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("AKUX-VARMUUSKOPIO.json", json.dumps(
                {"ohjelma": NIMI, "versio": VERSIO, "aika": time.time()}, ensure_ascii=False))
            z.write(db_copy, "akux.db")
            for name in ("asetukset.json",):
                p = storage.dir / name
                if p.exists():
                    z.write(p, name)
            for p in storage.dir.glob("logo.*"):
                z.write(p, p.name)
            for sub in ("raakadata", "raportit"):
                for p in (storage.dir / sub).glob("*"):
                    if p.is_file():
                        z.write(p, f"{sub}/{p.name}", compress_type=zipfile.ZIP_STORED
                                if p.suffix in (".gz", ".pdf") else zipfile.ZIP_DEFLATED)
    return out


def inspect_backup(data: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("Tiedosto ei ole Akuxin varmuuskopio.")
    names = set(z.namelist())
    if "AKUX-VARMUUSKOPIO.json" not in names or "akux.db" not in names:
        raise ValueError("Tiedosto ei ole Akuxin varmuuskopio.")
    meta = json.loads(z.read("AKUX-VARMUUSKOPIO.json"))
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "akux.db"
        p.write_bytes(z.read("akux.db"))
        con = sqlite3.connect(p)
        ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        n_v = con.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
        n_t = con.execute("SELECT COUNT(*) FROM tests").fetchone()[0]
        con.close()
    if not ok:
        raise ValueError("Varmuuskopion tietokanta on vioittunut.")
    meta.update(autoja=n_v, mittauksia=n_t)
    return meta


def restore(storage, data: bytes) -> dict:
    """Palauttaa varmuuskopion. Nykyiset tiedot siirretään ensin talteen kansioon
    'ennen_palautusta_<aika>', joten mitään ei menetetä."""
    meta = inspect_backup(data)
    z = zipfile.ZipFile(io.BytesIO(data))
    keep = storage.dir / f"ennen_palautusta_{time.strftime('%Y-%m-%d_%H%M%S')}"
    keep.mkdir()
    storage.close()
    for name in ("akux.db", "asetukset.json"):
        p = storage.dir / name
        if p.exists():
            shutil.move(str(p), keep / name)
    for p in storage.dir.glob("logo.*"):
        shutil.move(str(p), keep / p.name)
    for sub in ("raakadata", "raportit"):
        if (storage.dir / sub).exists():
            shutil.move(str(storage.dir / sub), keep / sub)
        (storage.dir / sub).mkdir(exist_ok=True)
    for info in z.infolist():
        name = info.filename
        if name.endswith("/") or name == "AKUX-VARMUUSKOPIO.json" or ".." in name or name.startswith("/"):
            continue
        target = storage.dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(info))
    # Raakadatan polut osoittamaan tähän kansioon
    con = sqlite3.connect(storage.dir / "akux.db")
    for tid, path in con.execute("SELECT id, raakadata FROM tests").fetchall():
        if path:
            con.execute("UPDATE tests SET raakadata=? WHERE id=?",
                        (str(storage.dir / "raakadata" / Path(path).name), tid))
    s_path = storage.dir / "asetukset.json"
    if s_path.exists():
        try:
            s = json.loads(s_path.read_text(encoding="utf-8"))
            for lg in storage.dir.glob("logo.*"):
                s["logo"] = str(lg)
            s_path.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass
    con.commit()
    con.close()
    meta["talteen"] = str(keep)
    return meta


# ----------------------------------------------------------------------
# Päivitys
# ----------------------------------------------------------------------
def inspect_update(data: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("Tiedosto ei ole Akuxin päivityspaketti.")
    init = [n for n in z.namelist() if n.endswith("akux/__init__.py")]
    bat = [n for n in z.namelist() if n.endswith("Asenna.bat")]
    if not init or not bat:
        raise ValueError("Tiedosto ei ole Akuxin päivityspaketti.")
    m = re.search(r'VERSIO\s*=\s*"([^"]+)"', z.read(init[0]).decode("utf-8", "ignore"))
    new = m.group(1) if m else "?"

    def key(v):
        return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))
    root = bat[0][: -len("Asenna.bat")]
    return {"versio": new, "nykyinen": VERSIO, "uudempi": key(new) > key(VERSIO), "juuri": root}


def start_update(data: bytes) -> dict:
    """Purkaa päivityspaketin ja käynnistää sen asennuksen. Asennus sulkee
    ohjelman, asentaa uuden version ja avaa sen. Tiedot säilyvät."""
    info = inspect_update(data)
    if not sys.platform.startswith("win"):
        raise ValueError("Päivitys ohjelmasta toimii Windowsissa. Pura paketti ja aja asennus käsin.")
    base = Path(tempfile.gettempdir()) / f"akux-paivitys-{info['versio']}"
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    zipfile.ZipFile(io.BytesIO(data)).extractall(base)
    bat = base / info["juuri"] / "Asenna.bat"
    subprocess.Popen(["cmd", "/c", "start", "Akux - päivitys", "/D", str(bat.parent), str(bat)],
                     close_fds=True, creationflags=0x00000008)  # DETACHED_PROCESS
    return info


# ----------------------------------------------------------------------
# Laaduntarkistus
# ----------------------------------------------------------------------
def _check(name, fn):
    t0 = time.time()
    try:
        status, detail = fn()
    except Exception as e:  # noqa: BLE001
        status, detail = "virhe", f"{type(e).__name__}: {e}"
    return {"nimi": name, "tila": status, "tieto": detail, "kesto_s": round(time.time() - t0, 2)}


def selftest(app, full: bool = True) -> dict:
    st = app.storage
    out = []

    def files():
        need = [PKG / "web" / "index.html", PKG / "web" / "app.js", PKG / "web" / "style.css",
                PKG / "data" / "profiles.json"] + [PKG / "data" / "fonts" / f"Inter-{w}.ttf"
                                                    for w in ("Regular", "Medium", "SemiBold", "Bold")]
        missing = [p.name for p in need if not p.exists()]
        return ("ok", "Kaikki ohjelmatiedostot löytyvät.") if not missing else ("virhe", "Puuttuu: " + ", ".join(missing))
    out.append(_check("Ohjelmatiedostot", files))

    def db():
        with st.lock:
            r = st.db.execute("PRAGMA integrity_check").fetchone()[0]
            nv = st.db.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            nt = st.db.execute("SELECT COUNT(*) FROM tests").fetchone()[0]
        return ("ok", f"Tietokanta on eheä. Autoja {nv}, mittauksia {nt}.") if r == "ok" else ("virhe", r)
    out.append(_check("Tietokanta", db))

    def disk():
        free = shutil.disk_usage(st.dir).free / 1e9
        if free < 1:
            return "varoitus", f"Levytilaa on vähän: {free:.1f} Gt. Kapasiteettimittaus vie noin 20–60 Mt."
        return "ok", f"Vapaata levytilaa {free:.0f} Gt."
    out.append(_check("Levytila", disk))

    def serial_ok():
        try:
            import serial  # noqa: F401
            from .sources import list_ports
        except ImportError:
            return "virhe", "Sarjaporttiosa puuttuu. Asenna ohjelma uudelleen."
        ports = list_ports()
        if not ports:
            return "varoitus", "Sarjaporttiosa toimii, mutta sovitinta ei ole kytketty."
        likely = [p for p in ports if p["todennakoinen"]]
        return "ok", f"Sovitin löytyy: {likely[0]['laite']}." if likely else f"Portteja {len(ports)}, OBDLinkiä ei tunnistettu."
    out.append(_check("Sovittimen yhteys", serial_ok))

    def decode():
        from .decoder import TeslaDecoder
        from .simulator import BatterySimulator
        sim = BatterySimulator(soc=0.5, accel=1)
        dec = TeslaDecoder()
        for k in range(40):
            for cid, data in sim._frames(k * 0.1):
                dec.feed(k * 0.1, cid, data)
        s = dec.state
        errs = []
        if not s.vin or not s.vin.startswith("5YJ3"):
            errs.append("valmistenumero")
        if s.brick_count != 96:
            errs.append("kennoryhmien määrä")
        if not s.nfp_kwh or abs(s.nfp_kwh - sim.nfp) > 0.05:
            errs.append("akun energia")
        if not s.soc_avg or abs(s.soc_avg - 50) > 1:
            errs.append("varaustila")
        return ("ok", "Viestien purku tuottaa oikeat arvot.") if not errs else ("virhe", "Väärin: " + ", ".join(errs))
    out.append(_check("Viestien purku", decode))

    def integrity():
        bad, n = [], 0
        for t in st.tests():
            if not t.get("tarkiste") or not t.get("raakadata"):
                continue
            p = Path(t["raakadata"])
            if not p.exists():
                bad.append(f"{t['id']} (tiedosto puuttuu)")
                continue
            h = hashlib.sha256()
            with gzip.open(p, "rt", encoding="ascii") as f:
                for line in f:
                    if not line.startswith("#"):
                        h.update(line.encode("ascii"))
            n += 1
            if h.hexdigest() != t["tarkiste"]:
                bad.append(str(t["id"]))
        if bad:
            return "virhe", "Raakadata ei täsmää mittauksissa: " + ", ".join(bad)
        return "ok", f"{n} mittauksen raakadata tarkistettu, kaikki muuttumattomia." if n else "Ei tarkistettavia mittauksia."
    out.append(_check("Raakadatan eheys", integrity))

    if full:
        def chain():
            from .app import App
            from . import report
            with tempfile.TemporaryDirectory() as tmp:
                a = App(tmp)
                src = a.connect("demo", soc=0.6, accel=60)
                end = time.time() + 20
                while time.time() < end and not (a.decoder.state.brick_count and a.decoder.state.nfp_kwh):
                    time.sleep(0.1)
                vid = a.storage.add_vehicle({"vin": a.decoder.state.vin, "nimi": "Laaduntarkistus"})
                tid = a.start_test(vehicle_id=vid, tyyppi="pikatarkastus")
                end = time.time() + 60
                while time.time() < end and a.recorder.active:
                    time.sleep(0.1)
                a.disconnect()
                t = a.storage.test(tid)
                r = t["tulos"] or {}
                soh = (r.get("bms") or {}).get("soh_pct")
                if t["tila"] != "valmis" or not soh or abs(soh - src.nfp / src.bol * 100) > 0.3:
                    return "virhe", "Mittauksen laskenta ei tuottanut odotettua tulosta."
                pdf = report.build(a.storage, tid)
                size = pdf.stat().st_size
                a.storage.close()
                return "ok", f"Simuloitu pikatarkastus ja raportti onnistuivat ({size // 1024} kt)."
        out.append(_check("Mittaus ja raportti", chain))

    def notif():
        s = app.settings
        if not s.get("ilmoitukset_kaytossa"):
            return "info", "Ilmoitukset eivät ole käytössä."
        res = app.notifier.last_result
        if res and not res[0]:
            return "varoitus", f"Viimeisin ilmoitus epäonnistui: {res[1]}"
        return "ok", "Ilmoitukset on otettu käyttöön."
    out.append(_check("Puhelinilmoitukset", notif))

    worst = "ok"
    for c in out:
        if c["tila"] == "virhe":
            worst = "virhe"
        elif c["tila"] == "varoitus" and worst == "ok":
            worst = "varoitus"
    return {"tulos": worst, "tarkistukset": out, "aika": time.time(), "versio": VERSIO}


def read_log(storage, lines=300) -> str:
    p = storage.dir / "loki.txt"
    if not p.exists():
        return ""
    data = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-lines:])
