"""Tietojen tallennus (SQLite) ja asetukset."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path


def default_data_dir() -> Path:
    env = os.environ.get("AKUX_DATA")
    if env:
        return Path(env)
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "Akux"
    return Path.home() / ".akux"


OLETUSASETUKSET = {
    "yritys_nimi": "",
    "yritys_osoite": "",
    "yritys_ytunnus": "",
    "yritys_puhelin": "",
    "yritys_sahkoposti": "",
    "yritys_www": "",
    "mittaaja": "",
    "logo": "",
    "portti": "",
    "baud": 0,
    "lepo_alku_min": 30,
    "lepo_loppu_min": 30,
    "kapasiteetti_lahto_soc_max": 15,
    "lampotila_min": 15,
    "lampotila_max": 35,
    "raportin_alatunniste": "",
    "puhelin_avain": "",
    "puhelin_kaytossa": False,
    "ilmoitukset_kaytossa": False,
    "ilmoitus_osoite": "",
    "ilmoitus_vaiheet": True,
    "ilmoitus_valmis": True,
    "ilmoitus_ongelmat": True,
    "mittaus_tallennus": True,
    "mittaus_kansio": "",
    "qr_osoite": "",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vin TEXT,
    nimi TEXT,
    rekisteri TEXT,
    omistaja TEXT,
    malli_id TEXT,
    vuosimalli INTEGER,
    vari TEXT,
    lisatiedot TEXT,
    opitut TEXT,
    luotu REAL,
    paivitetty REAL
);
CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
    tyyppi TEXT,
    tila TEXT,
    aloitettu REAL,
    paattynyt REAL,
    mittarilukema REAL,
    mittaaja TEXT,
    lisatiedot TEXT,
    tulos TEXT,
    raakadata TEXT,
    tarkiste TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    test_id INTEGER REFERENCES tests(id) ON DELETE CASCADE,
    t REAL, vaihe TEXT, v REAL, i REAL, soc_ui REAL, soc_avg REAL,
    nfp REAL, ner REAL, t_min REAL, t_max REAL, c_min REAL, c_max REAL,
    e_in REAL, e_out REAL, ah_in REAL
);
CREATE INDEX IF NOT EXISTS idx_samples ON samples(test_id, t);
CREATE TABLE IF NOT EXISTS snapshots (
    test_id INTEGER REFERENCES tests(id) ON DELETE CASCADE,
    t REAL, nimi TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS events (
    test_id INTEGER REFERENCES tests(id) ON DELETE CASCADE,
    t REAL, teksti TEXT
);
"""


class Storage:
    def __init__(self, data_dir: Path | None = None):
        self.dir = Path(data_dir or default_data_dir())
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "raakadata").mkdir(exist_ok=True)
        (self.dir / "raportit").mkdir(exist_ok=True)
        self.path = self.dir / "akux.db"
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._migrate()
        self.db.commit()
        self.settings_path = self.dir / "asetukset.json"

    def _migrate(self):
        """Lisää uudempien versioiden sarakkeet vanhaan tietokantaan tietoja menettämättä."""
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(vehicles)")}
        if "kayttoonotto" not in cols:
            self.db.execute("ALTER TABLE vehicles ADD COLUMN kayttoonotto TEXT")

    def close(self):
        with self.lock:
            try:
                self.db.close()
            except sqlite3.Error:
                pass

    # -- asetukset ------------------------------------------------------
    def settings(self) -> dict:
        s = dict(OLETUSASETUKSET)
        if self.settings_path.exists():
            try:
                s.update(json.loads(self.settings_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        return s

    def save_settings(self, values: dict) -> dict:
        s = self.settings()
        for k, v in values.items():
            if k in OLETUSASETUKSET:
                s[k] = v
        tmp = self.settings_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.settings_path)
        return s

    # -- yleiset --------------------------------------------------------
    def _exec(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    # -- ajoneuvot ------------------------------------------------------
    VEHICLE_FIELDS = ("vin", "nimi", "rekisteri", "omistaja", "malli_id", "vuosimalli", "vari", "lisatiedot",
                      "kayttoonotto")

    def add_vehicle(self, data: dict) -> int:
        now = time.time()
        vals = [data.get(k) for k in self.VEHICLE_FIELDS]
        cur = self._exec(
            f"INSERT INTO vehicles ({','.join(self.VEHICLE_FIELDS)}, opitut, luotu, paivitetty) "
            f"VALUES ({','.join('?' * len(self.VEHICLE_FIELDS))}, ?, ?, ?)",
            (*vals, json.dumps(data.get("opitut") or {}), now, now))
        return cur.lastrowid

    def update_vehicle(self, vid: int, data: dict):
        sets, args = [], []
        for k in self.VEHICLE_FIELDS:
            if k in data:
                sets.append(f"{k}=?")
                args.append(data[k])
        if "opitut" in data:
            sets.append("opitut=?")
            args.append(json.dumps(data["opitut"]))
        if not sets:
            return
        sets.append("paivitetty=?")
        args.append(time.time())
        self._exec(f"UPDATE vehicles SET {','.join(sets)} WHERE id=?", (*args, vid))

    def learn(self, vid: int, values: dict):
        v = self.vehicle(vid)
        if not v:
            return
        learned = v["opitut"]
        learned.update({k: val for k, val in values.items() if val is not None})
        self.update_vehicle(vid, {"opitut": learned})

    def vehicle(self, vid: int) -> dict | None:
        rows = self._rows("SELECT * FROM vehicles WHERE id=?", (vid,))
        if not rows:
            return None
        r = rows[0]
        r["opitut"] = json.loads(r["opitut"] or "{}")
        return r

    def vehicles(self) -> list[dict]:
        rows = self._rows("""SELECT v.*, (SELECT COUNT(*) FROM tests t WHERE t.vehicle_id=v.id) AS mittauksia,
                             (SELECT MAX(aloitettu) FROM tests t WHERE t.vehicle_id=v.id) AS viimeisin
                             FROM vehicles v ORDER BY v.paivitetty DESC""")
        for r in rows:
            r["opitut"] = json.loads(r["opitut"] or "{}")
        return rows

    def find_vehicle_by_vin(self, vin: str) -> dict | None:
        rows = self._rows("SELECT id FROM vehicles WHERE vin=?", (vin,))
        return self.vehicle(rows[0]["id"]) if rows else None

    def vehicle_photo(self, vid: int) -> Path:
        """Auton valokuvan polku (kuvaa ei välttämättä ole)."""
        return self.dir / "autot" / f"auto_{int(vid):05d}.jpg"

    def save_vehicle_photo(self, vid: int, data: bytes) -> Path:
        """Tallentaa auton kuvan: oikea asento puhelimen kuvatiedoista, enintään 1600 px, JPEG."""
        import io as _io
        from PIL import Image, ImageOps
        try:
            im = Image.open(_io.BytesIO(data))
            im = ImageOps.exif_transpose(im)
        except Exception as e:  # noqa: BLE001
            raise ValueError("Kuvaa ei voitu lukea. Käytä JPEG- tai PNG-kuvaa.") from e
        im = im.convert("RGB")
        im.thumbnail((1600, 1600))
        out = self.vehicle_photo(vid)
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, "JPEG", quality=86, optimize=True)
        return out

    def delete_vehicle(self, vid: int):
        for t in self.tests(vid):
            self.delete_test(t["id"])
        try:
            self.vehicle_photo(vid).unlink()
        except OSError:
            pass
        self._exec("DELETE FROM vehicles WHERE id=?", (vid,))

    # -- mittaukset -----------------------------------------------------
    def add_test(self, vehicle_id: int, tyyppi: str, mittarilukema=None, mittaaja="", lisatiedot="") -> int:
        cur = self._exec(
            "INSERT INTO tests (vehicle_id, tyyppi, tila, aloitettu, mittarilukema, mittaaja, lisatiedot) "
            "VALUES (?,?,?,?,?,?,?)",
            (vehicle_id, tyyppi, "käynnissä", time.time(), mittarilukema, mittaaja, lisatiedot))
        return cur.lastrowid

    def update_test(self, tid: int, **fields):
        if "tulos" in fields and not isinstance(fields["tulos"], str):
            fields["tulos"] = json.dumps(fields["tulos"], ensure_ascii=False)
        sets = ",".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE tests SET {sets} WHERE id=?", (*fields.values(), tid))

    def test(self, tid: int) -> dict | None:
        rows = self._rows("SELECT * FROM tests WHERE id=?", (tid,))
        if not rows:
            return None
        r = rows[0]
        r["tulos"] = json.loads(r["tulos"]) if r["tulos"] else None
        return r

    def tests(self, vehicle_id: int | None = None) -> list[dict]:
        if vehicle_id:
            rows = self._rows("SELECT * FROM tests WHERE vehicle_id=? ORDER BY aloitettu DESC", (vehicle_id,))
        else:
            rows = self._rows("SELECT * FROM tests ORDER BY aloitettu DESC")
        for r in rows:
            r["tulos"] = json.loads(r["tulos"]) if r["tulos"] else None
        return rows

    def delete_test(self, tid: int):
        t = self.test(tid)
        if t and t.get("raakadata"):
            try:
                Path(t["raakadata"]).unlink(missing_ok=True)
            except OSError:
                pass
        self._exec("DELETE FROM samples WHERE test_id=?", (tid,))
        self._exec("DELETE FROM snapshots WHERE test_id=?", (tid,))
        self._exec("DELETE FROM events WHERE test_id=?", (tid,))
        self._exec("DELETE FROM tests WHERE id=?", (tid,))

    def add_samples(self, tid: int, rows: list[tuple]):
        if not rows:
            return
        with self.lock:
            self.db.executemany(
                "INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(tid, *r) for r in rows])
            self.db.commit()

    def samples(self, tid: int) -> list[dict]:
        return self._rows("SELECT * FROM samples WHERE test_id=? ORDER BY t", (tid,))

    def add_snapshot(self, tid: int, t: float, nimi: str, data: dict):
        self._exec("INSERT INTO snapshots VALUES (?,?,?,?)", (tid, t, nimi, json.dumps(data)))

    def snapshots(self, tid: int) -> list[dict]:
        rows = self._rows("SELECT * FROM snapshots WHERE test_id=? ORDER BY t", (tid,))
        for r in rows:
            r["data"] = json.loads(r["data"])
        return rows

    def add_event(self, tid: int, t: float, teksti: str):
        self._exec("INSERT INTO events VALUES (?,?,?)", (tid, t, teksti))

    def events(self, tid: int) -> list[dict]:
        return self._rows("SELECT * FROM events WHERE test_id=? ORDER BY t", (tid,))
