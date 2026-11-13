"""Mittausten ohjaus: tallennus, vaiheet ja energian integrointi."""
from __future__ import annotations

import gzip
import hashlib
import math
import threading
import time
from pathlib import Path

from . import analysis, profiles
from .analysis import fmt

PIKA = "pikatarkastus"
KAPASITEETTI = "kapasiteetti"
TAYSI = "taysi"
AJO = "ajotesti"
PIKA_AJO = "pika_ajo"
KUORMITUS = "kuormitus"
# Kuormitustestin lähtöehdot (DEKRAn akkutestin vaatimukset): resistanssi riippuu voimakkaasti
# lämpötilasta ja varaustilasta, joten mittaus tehdään vain vertailukelpoisissa olosuhteissa.
KUORMA_SOC = (40.0, 80.0)
KUORMA_LAMPO = (10.0, 30.0)
KUORMA_LAMPOERO = 2.0
PIKALATAUS = "pikalataus"
ITSEPURKAUS = "itsepurkaus"

TYYPIT = {
    PIKA: "Pikatarkastus",
    KAPASITEETTI: "Kapasiteettimittaus",
    TAYSI: "Täysi akkutesti",
    AJO: "Ajotesti",
    PIKA_AJO: "Pika-ajotesti",
    KUORMITUS: "Kuormitustesti",
    PIKALATAUS: "Pikalataustesti",
    ITSEPURKAUS: "Itsepurkaustesti",
}

_AJO_VAIHEET = [("lepo_ajo_alku", "Lepo ennen ajoa"), ("ajo", "Ajo")]
_LATAUS_VAIHEET = [("lepo_alku", "Lepo ennen latausta"), ("odota_lataus", "Latauksen aloitus"),
                   ("lataus", "Lataus täyteen"), ("lepo_loppu", "Lepo latauksen jälkeen")]
VAIHEET = {
    PIKA: [("keruu", "Tietojen keruu"), ("valmis", "Valmis")],
    KAPASITEETTI: _LATAUS_VAIHEET + [("valmis", "Valmis")],
    TAYSI: _AJO_VAIHEET + _LATAUS_VAIHEET + [("valmis", "Valmis")],
    AJO: _AJO_VAIHEET + [("lepo_ajo_loppu", "Lepo ajon jälkeen"), ("valmis", "Valmis")],
    PIKA_AJO: _AJO_VAIHEET + [("lepo_ajo_loppu", "Lepo ajon jälkeen"), ("valmis", "Valmis")],
    KUORMITUS: [("kuorma_lepo", "Lepoarvot"), ("kuormitus", "Kiihdytykset"), ("valmis", "Valmis")],
    PIKALATAUS: [("odota_pikalataus", "Pikalatauksen aloitus"), ("pikalataus", "Pikalataus"), ("valmis", "Valmis")],
    ITSEPURKAUS: [("lepo_itse_alku", "Lepo ja lähtöarvot"), ("odotus", "Seisonta"),
                  ("itse_loppu", "Loppuarvot"), ("valmis", "Valmis")],
}
# Mittaukset, jotka voi keskeyttää ja jatkaa myöhemmin (myös ohjelman sulkemisen jälkeen)
JATKETTAVAT = {AJO, PIKA_AJO, TAYSI, ITSEPURKAUS, KAPASITEETTI}
JATKETTAVAT_VAIHEET = {"lepo_ajo_alku", "ajo", "lepo_ajo_loppu", "lepo_alku", "odota_lataus",
                       "lataus", "lepo_loppu", "lepo_itse_alku", "odotus", "itse_loppu"}
KUORMA_A = 80.0           # kuormitustapahtuman virtaraja (A)

REG_WINDOW_S = 60.0       # resistanssin laskennan aikaikkuna (s)
LEPO_VIRTA_A = 3.0        # tätä pienempi virta = auto levossa
LATAUS_VIRTA_A = 2.0      # latausvirran tunnistusraja
SAMPLE_INTERVAL = 5.0     # näytteenottoväli (s, mittausaikaa)
SNAPSHOT_INTERVAL = 600.0


def _reg_add(acc: list, win: list):
    """Lisää aikaikkunan keskistetyt summat: Σ(i−ī)², Σ(i−ī)(v−v̄), Σ(v−v̄)²."""
    if len(win) < 3:
        return
    n = len(win)
    mi = sum(x[1] for x in win) / n
    mv = sum(x[2] for x in win) / n
    acc[0] += n - 1
    acc[1] += sum((x[1] - mi) ** 2 for x in win)
    acc[2] += sum((x[1] - mi) * (x[2] - mv) for x in win)
    acc[3] += sum((x[2] - mv) ** 2 for x in win)



def _cnt(st):
    """Elinkaarilaskurit [purku, lataus] kWh, jos auto ilmoittaa ne."""
    if st.total_discharge_kwh is not None and st.total_charge_kwh is not None:
        return [st.total_discharge_kwh, st.total_charge_kwh]
    return None


def _soc_ui(st):
    """Näytön varaustila; jos auto ei ilmoita sitä (Nissan Leaf), akunhallinnan varaustila."""
    return st.soc_ui if st.soc_ui is not None else st.soc_avg

class Recorder:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.test_id: int | None = None
        self.tyyppi: str | None = None
        self.vaihe: str | None = None
        self.raw = None
        self.raw_hash = None
        self.raw_path: Path | None = None
        self._reset_counters()

    # ------------------------------------------------------------------
    def _reset_counters(self):
        self.t_start = None
        self.t_phase = None
        self.last_hv = None          # (t, v, i)
        self.last_sample_t = 0.0
        self.last_snapshot_t = 0.0
        self.pending_samples: list[tuple] = []
        self.e_in = 0.0              # kWh akkuun (lataus)
        self.e_out = 0.0             # kWh akusta (purku)
        self.ah_in = 0.0
        self.ah_out = 0.0
        self.i2_in = 0.0             # ∫ I² dt latauksessa (A²s)
        self.ch_e_neg = self.ch_e_pos = 0.0   # latausvaiheen energiat merkin mukaan
        self.ch_ah_neg = self.ch_ah_pos = 0.0
        self.ch_i2 = 0.0
        self.ch_seconds = 0.0
        self.rest_since = None
        self.charge_since = None
        self.idle_since = None
        self.last_rest = None        # (t, v, i) viimeisin lepotilan lukema
        self.r_window: list[tuple] = []
        self.marks: dict = {}
        self.gaps: list[dict] = []
        self.brick_seen_at_start: set = set()
        self.brick_acc: dict = {}
        self.collect_bricks = False  # kerätäänkö tuoreita kennoryhmäjännitteitä keskiarvoon
        self.quick_started = None
        self.notes: list[str] = []
        self.finishing = False
        self.i2_out = 0.0            # ∫ I² dt purussa (A²s)
        # Resistanssi lasketaan lyhyistä aikaikkunoista, joissa varaustila ei ehdi muuttua: kunkin ikkunan
        # arvot keskistetään ikkunan keskiarvoon, jolloin lepojännitteen hidas muutos ei vääristä tulosta.
        self.bricks_reg: dict = {}   # kennoryhmä -> [n, Sii, Siv, Svv] (keskistetyt summat)
        self.pack_reg = [0, 0.0, 0.0, 0.0]
        self._brick_win: dict = {}   # kennoryhmä -> [(t, i, v), ...]
        self._pack_win: list = []
        self.p_max_kw = 0.0
        self.p_min_kw = 0.0
        self.v_min_load = None       # (V, numero, A) pienin kennoryhmän jännite kuormassa
        self.load_events = 0
        self._in_load = False
        self.curve: list = []        # pikalatauksen käyrä
        self.last_curve_t = 0.0
        self.osat = 1                # mittauksen osat (jatketut istunnot)

    @property
    def active(self) -> bool:
        return self.test_id is not None

    # ------------------------------------------------------------------
    def start(self, vehicle_id: int, tyyppi: str, mittarilukema=None, mittaaja="", lisatiedot="",
              riippumaton=None) -> int:
        with self.lock:
            if self.active:
                raise RuntimeError("Mittaus on jo käynnissä.")
            if not self.app.source or not self.app.source.running:
                raise RuntimeError("Yhdistä ensin sovittimeen tai esittelytilaan.")
            st = self.app.storage
            from . import polled
            _pm = polled.module(self.app.decoder.platform)
            if tyyppi == ITSEPURKAUS and _pm and not _pm.ITSEPURKAUS_OK:
                raise RuntimeError("Itsepurkaustestiä ei voi tehdä tälle autolle: akunhallinta ilmoittaa "
                                   f"kennojännitteet {_pm.RESOLUUTIO_MV:.0f} mV:n tarkkuudella, mutta "
                                   "itsepurkautumisen havaitseminen vaatii alle 1 mV:n tarkkuuden.")
            if tyyppi == KUORMITUS:
                virheet = self.kuormitus_ehdot()
                if virheet:
                    raise RuntimeError("Kuormitustestiä ei voi aloittaa: " + "; ".join(virheet) + ".")
            self._reset_counters()
            tid = st.add_test(vehicle_id, tyyppi, mittarilukema, mittaaja, lisatiedot, riippumaton)
            self.test_id = tid
            self.tyyppi = tyyppi
            self.vehicle_id = vehicle_id
            self.raw_path = st.dir / "raakadata" / f"mittaus_{tid:05d}.csv.gz"
            self.raw = gzip.open(self.raw_path, "at", encoding="ascii")
            self.raw.write("# aika;tunniste;data\n")
            self.raw_hash = hashlib.sha256()
            st.update_test(tid, raakadata=str(self.raw_path))
            now = self.app.source.now()
            self.t_start = now
            self._event(now, f"Mittaus aloitettu ({TYYPIT.get(tyyppi, tyyppi).lower()})")
            self._set_phase(VAIHEET[tyyppi][0][0], now)
            if tyyppi in (PIKA, KUORMITUS, ITSEPURKAUS):
                self.quick_started = now
                self.brick_acc = {}
            if tyyppi == KUORMITUS:
                d = self.app.decoder.state
                self.marks["lahtoehdot"] = {"soc": _soc_ui(d), "t_min": d.temp_min, "t_max": d.temp_max}
            self.app.decoder.add_hv_listener(self._on_hv)
            self.app.decoder.add_brick_listener(self._on_brick)
            self._snapshot(now, "alku")
            return tid

    # -- tauko ja jatkaminen -------------------------------------------
    def can_pause(self) -> bool:
        return self.active and self.tyyppi in JATKETTAVAT and self.vaihe in JATKETTAVAT_VAIHEET

    def pause(self, reason: str = "Mittaus keskeytettiin tauolle"):
        """Tallentaa jatkettavan mittauksen tilan ja vapauttaa yhteyden. Jatketaan myöhemmin."""
        with self.lock:
            if not self.active:
                return
            t = self.last_hv[0] if self.last_hv else time.time()
            self._event(t, f"{reason}. Mittausta voi jatkaa myöhemmin.")
            st = self.app.decoder.state
            self._flush_reg()
            self.marks["jatkotauko"] = {"t": t, "lataus_kwh": st.total_charge_kwh, "soc_avg": st.soc_avg,
                                   "vaihe": self.vaihe,
                                   "laskurit": _cnt(st)}
            self.flush()
            self._close_raw()
            self._persist_state(tila="kesken")
            self.app.decoder.remove_hv_listener(self._on_hv)
            self.app.decoder.remove_brick_listener(self._on_brick)
            self.test_id = None
            self.vaihe = None

    def resume(self, tid: int):
        """Jatkaa tauolla olevaa mittausta. Autoon pitää olla yhteys."""
        with self.lock:
            if self.active:
                raise RuntimeError("Mittaus on jo käynnissä.")
            if not self.app.source or not self.app.source.running:
                raise RuntimeError("Yhdistä ensin autoon.")
            st = self.app.storage
            t = st.test(tid)
            if not t or t["tila"] != "kesken":
                raise RuntimeError("Mittausta ei voi jatkaa.")
            state = (t.get("tulos") or {}).get("keskeneräinen") or {}
            self._reset_counters()
            self.test_id, self.tyyppi, self.vehicle_id = tid, t["tyyppi"], t["vehicle_id"]
            self._load_state(state)
            self.raw_path = Path(t["raakadata"])
            self.raw = gzip.open(self.raw_path, "at", encoding="ascii")
            self.raw_hash = None              # lasketaan tiedostosta mittauksen lopussa
            self.osat += 1
            now = self.app.source.now()
            st.update_test(tid, tila="käynnissä")
            self._event(now, f"Mittaus jatkuu (osa {self.osat})")
            if self.vaihe == "lataus":
                # Tauon aikana akkuun mennyt energia täydennetään akunhallinnan energialaskennasta
                # samalla tavalla kuin lyhyissä datakatkoissa.
                # Elinkaarilaskureista saadaan tauon aikana akkuun mennyt nettoenergia tarkasti, myös
                # tauon aikainen kulutus (lämmitys, valvontatila) vähennettynä.
                tk = self.marks.get("jatkotauko") or {}
                t0 = tk.get("t") or state.get("t_viim") or now
                self.gaps.append({"alku": t0, "loppu": now, "kesto_s": max(0.0, now - t0),
                                  "ner_alku": self.marks.get("_ner_last"), "ner_loppu": None,
                                  "laskurit_alku": tk.get("laskurit"), "laskurit_loppu": None,
                                  "_e_mark": self.e_in - self.e_out, "tauko": True})
                self.marks.pop("jatkotauko", None)
            else:
                self._check_pause_charging(now)
            if self.vaihe in ("lepo_ajo_alku", "lepo_ajo_loppu", "lepo_alku", "lepo_itse_alku", "lepo_loppu"):
                self.rest_since = None
            self.t_phase = now
            self._persist_state()
            self.app.decoder.add_hv_listener(self._on_hv)
            self.app.decoder.add_brick_listener(self._on_brick)
            self._snapshot(now, f"jatko_{self.osat}")
            return tid

    def _check_pause_charging(self, now):
        """Ladattiinko akkua mittauksen tauon aikana? Teslan latauslaskuri kertoo sen luotettavasti."""
        st = self.app.decoder.state
        if st.total_charge_kwh is None and self.marks.get("jatkotauko", {}).get("lataus_kwh") is not None:
            return                       # laskuri ei vielä luettu: tarkistetaan seuraavasta viestistä
        tk = self.marks.pop("jatkotauko", None) or {}
        c0, c1 = tk.get("lataus_kwh"), st.total_charge_kwh
        if c0 is None or c1 is None or c1 - c0 < 0.3:
            return
        txt = f"Akkua ladattiin mittauksen tauon aikana ({c1 - c0:.1f} kWh)".replace(".", ",")
        self._event(now, txt)
        if self.tyyppi in (AJO, PIKA_AJO) or (self.tyyppi == TAYSI and tk.get("vaihe") in ("lepo_ajo_alku", "ajo")):
            self.marks.setdefault("ladattu_ajossa", now)
            self.notes.append(txt + ". Purkumittauksen tulos on tavallista epävarmempi.")
        elif self.tyyppi == ITSEPURKAUS:
            self.notes.append(txt + ". Itsepurkaustestin tulos ei ole luotettava.")

    def discard(self, tid: int):
        st = self.app.storage
        t = st.test(tid)
        if t and t["tila"] == "kesken":
            st.update_test(tid, tila="keskeytetty")
            st.add_event(tid, time.time(), "Kesken jäänyt mittaus hylättiin")

    _STATE_KEYS = ("vaihe", "marks", "gaps", "notes", "t_start", "e_in", "e_out", "ah_in", "ah_out", "i2_in",
                   "i2_out", "bricks_reg", "pack_reg", "p_max_kw", "p_min_kw", "v_min_load", "load_events", "curve", "osat",
                   "brick_acc", "quick_started", "ch_e_neg", "ch_e_pos", "ch_ah_neg", "ch_ah_pos", "ch_i2",
                   "ch_seconds", "r_window")

    def _state_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self._STATE_KEYS}
        d["merkinnat"], d["aukot"], d["huomiot"], d["t_alku"] = self.marks, self.gaps, self.notes, self.t_start
        d["brick_acc"] = {str(k): v for k, v in (self.brick_acc or {}).items()}
        d["bricks_reg"] = {str(k): v for k, v in self.bricks_reg.items()}
        d["t_viim"] = self.last_hv[0] if self.last_hv else None
        return d

    def _load_state(self, d: dict):
        for k in self._STATE_KEYS:
            if k in d and k not in ("brick_acc", "bricks_reg"):
                setattr(self, k, d[k])
        self.marks = d.get("merkinnat", d.get("marks", {})) or {}
        self.gaps = d.get("aukot", d.get("gaps", [])) or []
        self.notes = d.get("huomiot", d.get("notes", [])) or []
        self.t_start = d.get("t_alku", d.get("t_start"))
        self.brick_acc = {int(k): v for k, v in (d.get("brick_acc") or {}).items()}
        self.bricks_reg = {int(k): v for k, v in (d.get("bricks_reg") or {}).items()}

    def on_frame(self, t, cid, data):
        """Kutsutaan jokaisesta kehyksestä (raakadatan tallennus)."""
        if self.raw is not None:
            line = f"{t:.3f};{cid:03X};{data.hex().upper()}\n"
            try:
                self.raw.write(line)
                if self.raw_hash is not None:
                    self.raw_hash.update(line.encode("ascii"))
            except (ValueError, OSError):
                pass

    # ------------------------------------------------------------------
    def _set_phase(self, vaihe, t):
        self.vaihe = vaihe
        self.t_phase = t
        names = dict(VAIHEET[self.tyyppi])
        if self.test_id and vaihe in names:
            self._event(t, f"Vaihe: {names[vaihe]}")
            msg = {"odota_lataus": "Lepojakso on valmis. Aseta latausraja 100 %:iin ja aloita lataus.",
                   "lataus": "Lataus on alkanut. Mittaus jatkuu itsestään.",
                   "lepo_loppu": "Akku on täynnä. Mittaus jatkuu lepojaksolla.",
                   "ajo": "Lähtöarvot on tallennettu. Voit aloittaa ajon.",
                   "lepo_ajo_loppu": "Ajo on päättynyt. Pidä auto paikallaan lepojakson ajan.",
                   "odotus": "Lähtöarvot on tallennettu. Jätä auto seisomaan ilman latausta.",
                   "pikalataus": "Pikalataus on alkanut. Mittaus jatkuu itsestään."}.get(vaihe)
            if msg:
                self.app.notify("vaiheet", names[vaihe], msg)
        self._persist_state()

    def _event(self, t, txt):
        if self.test_id:
            self.app.storage.add_event(self.test_id, t, txt)

    def _persist_state(self, tila: str | None = None):
        if not self.test_id:
            return
        fields = {"tulos": {"keskeneräinen": self._state_dict()}}
        if tila:
            fields["tila"] = tila
        self.app.storage.update_test(self.test_id, **fields)

    def _snapshot(self, t, nimi):
        d = self.app.decoder
        snap = d.snapshot()
        snap["kennot"] = d.bricks_list()
        self.app.storage.add_snapshot(self.test_id, t, nimi, snap)
        self.last_snapshot_t = t
        return snap

    # ------------------------------------------------------------------
    def _on_hv(self, t, v, i):
        with self.lock:
            if not self.active or self.finishing:
                return
            if "jatkotauko" in self.marks:
                self._check_pause_charging(t)
            src = self.app.source
            max_gap = src.max_gap if src else 5.0
            if self.last_hv:
                lt, lv, li = self.last_hv
                dt = t - lt
                if 0 < dt <= max_gap:
                    p = (v * i + lv * li) / 2          # W, + = purku
                    ia = (i + li) / 2
                    if p < 0:
                        self.e_in += -p * dt / 3.6e6
                        self.ah_in += -ia * dt / 3600
                        self.i2_in += ia * ia * dt
                    else:
                        self.e_out += p * dt / 3.6e6
                        self.ah_out += ia * dt / 3600
                        self.i2_out += ia * ia * dt
                    if self.vaihe == "lataus":
                        if p < 0:
                            self.ch_e_neg += -p * dt / 3.6e6
                            self.ch_ah_neg += -ia * dt / 3600
                        else:
                            self.ch_e_pos += p * dt / 3.6e6
                            self.ch_ah_pos += ia * dt / 3600
                        self.ch_i2 += ia * ia * dt
                        self.ch_seconds += dt
                elif dt > max_gap and self.vaihe == "lataus":
                    # Katkon jälkeinen energialukema otetaan vasta, kun akunhallinnan
                    # energiaviesti on ehditty vastaanottaa uudelleen.
                    self.gaps.append({"alku": lt, "loppu": t, "kesto_s": dt,
                                      "ner_alku": self.marks.get("_ner_last"), "ner_loppu": None,
                                      "_e_mark": self.e_in - self.e_out})
                    self._event(t, f"Mittausdatassa {dt:.0f} s:n katko latauksen aikana")
                    self.app.notify("ongelmat", "Katko mittausdatassa",
                                    f"Autosta ei saatu tietoja {dt / 60:.0f} minuuttiin. Mittaus jatkuu.")
            self.last_hv = (t, v, i)
            if self.vaihe in ("ajo", "kuormitus", "pikalataus"):
                self._pack_win.append((t, i, v))
                if t - self._pack_win[0][0] >= REG_WINDOW_S / 2:
                    _reg_add(self.pack_reg, self._pack_win)
                    self._pack_win = []
            elif self._pack_win:
                _reg_add(self.pack_reg, self._pack_win)
                self._pack_win = []
            pk = v * i / 1000
            self.p_max_kw = max(self.p_max_kw, pk)
            self.p_min_kw = min(self.p_min_kw, pk)
            if abs(i) >= KUORMA_A and not self._in_load:
                self._in_load = True
                self.load_events += 1
            elif abs(i) < KUORMA_A * 0.5:
                self._in_load = False
            st = self.app.decoder.state
            for g in self.gaps:
                seen = self.app.decoder.seen.get(self.app.decoder.energy_id()) or {}
                if g.get("ner_loppu") is None and "_e_mark" in g and seen.get("last", 0) > g["loppu"] \
                        and st.nominal_remaining_kwh is not None:
                    since = (self.e_in - self.e_out) - g.pop("_e_mark")
                    g["ner_loppu"] = st.nominal_remaining_kwh - since
                    if g.get("laskurit_alku") and _cnt(st):
                        # laskurit luettu tauon jälkeen: jatkon jälkeen jo mitattu energia vähennetään
                        g["laskurit_loppu"] = _cnt(st)
                        g["e_jatkon_jalkeen"] = since
            if self.vaihe == "lataus":
                self.marks["_ner_last"] = st.nominal_remaining_kwh
            if abs(i) < 1.0:
                self.last_rest = (t, v, i)

            self._phase_logic(t, v, i)

            if t - self.last_sample_t >= SAMPLE_INTERVAL:
                self.last_sample_t = t
                self.pending_samples.append((
                    t, self.vaihe, v, i, st.soc_ui, st.soc_avg, st.nfp_kwh, st.nominal_remaining_kwh,
                    st.temp_min, st.temp_max, st.cell_v_min, st.cell_v_max,
                    self.e_in, self.e_out, self.ah_in))
                if len(self.pending_samples) >= 12:
                    self.flush()
            if self.vaihe not in ("valmis",) and t - self.last_snapshot_t >= SNAPSHOT_INTERVAL:
                self._snapshot(t, f"seuranta_{self.vaihe}")

    def _on_brick(self, t, k, v, i):
        """Juuri luettu kennoryhmän jännite ja samanhetkinen virta.

        Levossa jännitteet keskiarvoistetaan (jokainen viesti kerran). Kuormassa niistä määritetään
        kennoryhmäkohtainen sisäinen resistanssi.
        """
        if not self.active or self.finishing:
            return
        if self.collect_bricks:
            acc = self.brick_acc.setdefault(k, [0.0, 0, 0.0])
            if len(acc) < 3:
                acc.append(0.0)
            acc[0] += v
            acc[1] += 1
            acc[2] += v * v
        if self.vaihe not in ("ajo", "kuormitus", "pikalataus"):
            if self._brick_win:
                self._flush_reg()
            return
        w = self._brick_win.setdefault(k, [])
        w.append((t, i, v))
        if t - w[0][0] >= REG_WINDOW_S:
            _reg_add(self.bricks_reg.setdefault(k, [0, 0.0, 0.0, 0.0]), w)
            self._brick_win[k] = []
        if i >= KUORMA_A and (self.v_min_load is None or v < self.v_min_load[0]):
            self.v_min_load = (v, k, i)

    def _flush_reg(self):
        for k, w in self._brick_win.items():
            if w:
                _reg_add(self.bricks_reg.setdefault(k, [0, 0.0, 0.0, 0.0]), w)
        self._brick_win = {}
        if self._pack_win:
            _reg_add(self.pack_reg, self._pack_win)
            self._pack_win = []

    def flush(self):
        if self.test_id and self.pending_samples:
            self.app.storage.add_samples(self.test_id, self.pending_samples)
            self.pending_samples = []
            if self.tyyppi in JATKETTAVAT and not self.finishing:
                self._persist_state()
        if self.raw:
            try:
                self.raw.flush()
            except (ValueError, OSError):
                pass

    # ------------------------------------------------------------------
    def _phase_logic(self, t, v, i):
        s = self.app.settings
        st = self.app.decoder.state
        if self.tyyppi == PIKA:
            self._quick_logic(t, i)
            return
        if self.vaihe in ("lepo_ajo_alku", "ajo", "lepo_ajo_loppu"):
            self._drive_logic(t, v, i)
            return
        if self.tyyppi == KUORMITUS:
            self._load_logic(t, i)
            return
        if self.tyyppi == PIKALATAUS:
            self._dc_logic(t, v, i)
            return
        if self.tyyppi == ITSEPURKAUS:
            self._self_discharge_logic(t, i)
            return

        charging = i < -LATAUS_VIRTA_A
        resting = abs(i) < LEPO_VIRTA_A

        if charging:
            if self.charge_since is None:
                self.charge_since = t
                self._charge_mark = (self.e_in, self.ah_in, self.i2_in, self.e_out, self.ah_out)
                self._charge_mark_cnt = st.counters_raw
        else:
            self.charge_since = None

        if self.vaihe == "lepo_alku":
            if resting:
                self.rest_since = self.rest_since or t
                if t - self.rest_since >= s["lepo_alku_min"] * 60:
                    self._end_start_rest(t, skipped=False)
            else:
                if self.rest_since and not charging:
                    self._event(t, "Virta kasvoi lepojakson aikana, lepojakso alkaa alusta")
                self.rest_since = None
            if self.charge_since and t - self.charge_since >= 10:
                self._end_start_rest(t, skipped=True)
                self._begin_charge(t)

        elif self.vaihe == "odota_lataus":
            if self.charge_since and t - self.charge_since >= 10:
                self._begin_charge(t)

        elif self.vaihe == "lataus":
            ch_t = t - self.marks["lataus_alku_t"]
            if 5 <= ch_t <= 90 and charging:
                self.r_window.append((v, i, self.ah_in - self.marks.get("ah_in_ennen", self.ah_in)))
            if i > -0.5:
                self.idle_since = self.idle_since or t
            else:
                self.idle_since = None
            done = bool(st.full_charge_complete) and ch_t > 120
            soc = st.soc_avg or 0
            if st.platform not in (None, "m3", "sx"):
                # Kyselyihin vastaavien autojen akunhallinnan varaustila voi jäädä täydessä akussa alle 100 %;
                # näytön arvo on 100 %
                soc = max(soc, st.soc_ui or 0)
            if self.idle_since and t - self.idle_since >= 300 and soc >= 97.0:
                done = True
            if self.idle_since and t - self.idle_since >= 600 and soc < 97.0 and "tauko" not in self.marks:
                self.marks["tauko"] = t
                self._event(t, "Lataus on keskeytynyt ennen täyttä akkua. Mittaus odottaa latauksen jatkumista.")
                self.app.notify("ongelmat", "Lataus keskeytyi",
                                "Lataus pysähtyi ennen täyttä akkua. Tarkista latauskaapeli ja latausraja.")
            if self.idle_since is None and "tauko" in self.marks:
                self._event(t, "Lataus jatkuu")
                self.marks.pop("tauko")
            if done:
                self._end_charge(t)

        elif self.vaihe == "lepo_loppu":
            if resting:
                self.rest_since = self.rest_since or t
                if t - self.rest_since >= s["lepo_loppu_min"] * 60:
                    self._finish(t)
            else:
                self.rest_since = None

    def _quick_logic(self, t, i):
        d = self.app.decoder
        self.collect_bricks = True
        elapsed = t - self.quick_started
        st = d.state
        n = st.brick_count or 0
        counts = [self.brick_acc.get(k, [0, 0])[1] for k in range(1, n + 1)] if n else []
        enough_cells = n > 0 and counts and min(counts) >= 10
        enough_energy = st.nfp_kwh is not None and st.soc_avg is not None
        if (elapsed >= 60 and enough_cells and enough_energy) or elapsed >= 300:
            if not enough_cells:
                self.notes.append("Kaikkien kennoryhmien jännitteitä ei saatu luettua mittausaikana.")
            if not enough_energy:
                self.notes.append("Akunhallinnan energiatietoja ei saatu luettua mittausaikana.")
            self._finish(t)

    # -- ajotestit -------------------------------------------------------
    def _state_mark(self, t, extra=None) -> dict:
        st = self.app.decoder.state
        m = {"t": t, "soc_avg": st.soc_avg, "soc_ui": st.soc_ui, "soc_min": st.soc_min, "soc_max": st.soc_max,
             "ner": st.nominal_remaining_kwh, "nfp": st.nfp_kwh, "laskurit": st.counters_raw,
             "km": st.odometer_km, "v": st.pack_v, "t_min": st.temp_min, "t_max": st.temp_max,
             "e_in": self.e_in, "e_out": self.e_out, "i2_out": self.i2_out, "i2_in": self.i2_in,
             "ah_in": self.ah_in, "ah_out": self.ah_out}
        if extra:
            m.update(extra)
        return m

    def _drive_target_reached(self) -> bool:
        st = self.app.decoder.state
        s = self.app.settings
        a = self.marks.get("ajo_alku") or {}
        # Tavoitteet ilmaistaan auton näytön varauksena, jotta ne vastaavat sitä, mitä kuljettaja näkee
        soc = st.soc_ui if st.soc_ui is not None else st.soc_avg
        soc0 = a.get("soc_ui") if a.get("soc_ui") is not None else a.get("soc_avg")
        if soc is None or soc0 is None:
            return False
        if self.tyyppi == PIKA_AJO:
            return soc0 - soc >= s["pika_ajo_soc"]
        if self.tyyppi == TAYSI:
            return soc <= s["kapasiteetti_lahto_soc_max"]
        return soc <= s["ajo_loppu_soc"]

    def _drive_logic(self, t, v, i):
        s = self.app.settings
        resting = abs(i) < LEPO_VIRTA_A
        if self.vaihe == "lepo_ajo_alku":
            if resting:
                self.rest_since = self.rest_since or t
                if t - self.rest_since >= s["ajo_lepo_min"] * 60:
                    self._begin_drive(t, skipped=False)
            else:
                if self.rest_since:
                    self._event(t, "Auto lähti liikkeelle ennen lepojakson loppua")
                    self._begin_drive(t, skipped=True)
                self.rest_since = None
            return
        if self.vaihe == "ajo":
            charging = i < -LATAUS_VIRTA_A
            if charging:
                self.charge_since = self.charge_since or t
            else:
                self.charge_since = None
            if self.charge_since and t - self.charge_since >= 60 and "ladattu_ajossa" not in self.marks:
                if self.tyyppi == TAYSI and self._drive_target_reached():
                    # Latauskaapeli kytkettiin heti ajon jälkeen: purkuosuus päättyy tähän
                    self._end_drive(t, skipped=True)
                    return
                self.marks["ladattu_ajossa"] = t
                self.notes.append("Akkua ladattiin ajotestin aikana. Tulos on tavallista epävarmempi.")
                self._event(t, "Akkua ladattiin ajotestin aikana")
            if self._drive_target_reached():
                if "tavoite" not in self.marks:
                    self.marks["tavoite"] = t
                    self._event(t, "Ajon tavoite saavutettu")
                    self.app.notify("vaiheet", "Ajo riittää", "Ajon tavoite on saavutettu. Pysäköi auto.")
                if resting:
                    self.rest_since = self.rest_since or t
                    if t - self.rest_since >= 60:
                        self._end_drive(t, skipped=False)
                else:
                    self.rest_since = None
            return
        if self.vaihe == "lepo_ajo_loppu":
            if resting:
                self.rest_since = self.rest_since or t
                if t - self.rest_since >= s["ajo_lepo_min"] * 60:
                    self._finish(t)
            else:
                self.rest_since = None

    def _begin_drive(self, t, skipped: bool):
        rest_min = ((t - self.rest_since) / 60) if self.rest_since else 0.0
        self._snapshot(t, "ajo_alku")
        self.marks["ajo_alku"] = self._state_mark(t, {"lepo_min": rest_min, "ohitettu": skipped,
                                                      "vaadittu_min": self.app.settings.get("ajo_lepo_min")})
        if skipped:
            self.notes.append(f"Lepojakso ennen ajoa jäi {rest_min:.0f} minuuttiin.")
        self.rest_since = None
        self._set_phase("ajo", t)

    def _end_drive(self, t, skipped: bool):
        """Ajo-osuus päättyy. Ajotesteissä seuraa lepo, täydessä testissä lepo ennen latausta."""
        self.marks["ajo_paattyi"] = t
        self.rest_since = None
        if self.tyyppi == TAYSI:
            if skipped:
                # Lataus alkoi suoraan: purkuosuuden loppu on latauksen alku
                self.marks["ajo_loppu"] = self._state_mark(t, {"lepo_min": 0.0, "ohitettu": True})
                self.notes.append("Lataus aloitettiin heti ajon jälkeen ilman lepojaksoa.")
            self._set_phase("lepo_alku", t)
        else:
            self._set_phase("lepo_ajo_loppu", t)

    # -- kuormitustesti ----------------------------------------------------
    def _load_logic(self, t, i):
        s = self.app.settings
        if self.vaihe == "kuorma_lepo":
            d = self.app.decoder
            self.collect_bricks = True
            n = d.state.brick_count or 0
            ready = n and min((self.brick_acc.get(k, [0, 0])[1] for k in range(1, n + 1)), default=0) >= 5
            if (ready and t - self.quick_started >= 30) or t - self.quick_started >= 180:
                self.marks["kuorma_lepo"] = self._state_mark(t, {"kennot": [
                    (self.brick_acc[k][0] / self.brick_acc[k][1]) if k in self.brick_acc else None
                    for k in range(1, (n or max(self.brick_acc or {0: 0})) + 1)]})
                self.collect_bricks = False
                self._set_phase("kuormitus", t)
            return
        if self.vaihe == "kuormitus":
            if self.load_events >= s["kuormitus_tapahtumat"] and abs(i) < LEPO_VIRTA_A:
                self.rest_since = self.rest_since or t
                if t - self.rest_since >= 20:
                    self._finish(t)
            else:
                self.rest_since = None

    # -- pikalataustesti -------------------------------------------------
    def _dc_logic(self, t, v, i):
        st = self.app.decoder.state
        p_kw = -v * i / 1000
        if self.vaihe == "odota_pikalataus":
            if p_kw > 20:
                self.charge_since = self.charge_since or t
                if t - self.charge_since >= 5:
                    self.marks["pikalataus_alku"] = self._state_mark(t)
                    self._set_phase("pikalataus", t)
            else:
                self.charge_since = None
            return
        if self.vaihe == "pikalataus":
            if t - self.last_curve_t >= 10:
                self.last_curve_t = t
                bricks = [x for x in st.bricks.values() if x]
                self.curve.append([t, st.soc_avg, round(max(p_kw, 0.0), 2), st.temp_max,
                                   round((max(bricks) - min(bricks)) * 1000, 1) if bricks else None])
            if p_kw < 3:
                self.idle_since = self.idle_since or t
                if t - self.idle_since >= 60:
                    self._finish(t)
            else:
                self.idle_since = None

    # -- itsepurkaustesti ------------------------------------------------
    def _avg_bricks(self) -> list:
        n = self.app.decoder.state.brick_count or (max(self.brick_acc) if self.brick_acc else 0)
        return [(self.brick_acc[k][0] / self.brick_acc[k][1]) if k in self.brick_acc else None
                for k in range(1, n + 1)]

    def _noise_bricks(self) -> tuple[list, list]:
        """Kennoryhmien jännitelukemien keskihajonta (V) ja näytteiden määrä."""
        n = self.app.decoder.state.brick_count or (max(self.brick_acc) if self.brick_acc else 0)
        sd, cnt = [], []
        for k in range(1, n + 1):
            a = self.brick_acc.get(k)
            if not a or len(a) < 3 or a[1] < 2:
                sd.append(None)
                cnt.append(a[1] if a else 0)
                continue
            sd.append(math.sqrt(max(a[2] / a[1] - (a[0] / a[1]) ** 2, 0.0) * a[1] / (a[1] - 1)))
            cnt.append(a[1])
        return sd, cnt

    def _brick_mark(self) -> dict:
        sd, cnt = self._noise_bricks()
        return {"kennot": self._avg_bricks(), "kennot_sd": sd, "kennot_n": cnt}

    def _min_brick_samples(self) -> int:
        n = self.app.decoder.state.brick_count or 0
        return min((self.brick_acc.get(k, [0, 0])[1] for k in range(1, n + 1)), default=0) if n else 0

    def _self_discharge_logic(self, t, i):
        s = self.app.settings
        resting = abs(i) < LEPO_VIRTA_A
        if self.vaihe == "lepo_itse_alku":
            if resting:
                self.rest_since = self.rest_since or t
                target = s["itsepurkaus_lepo_min"] * 60
                el = t - self.rest_since
                self.collect_bricks = el >= max(0, target - 120)
                if el >= target and (self._min_brick_samples() >= 50 or el >= target + 900) and self.brick_acc:
                    self.marks["itse_alku"] = self._state_mark(t, self._brick_mark())
                    self.brick_acc = {}
                    self.collect_bricks = False
                    self.rest_since = None
                    self._set_phase("odotus", t)
            else:
                self.rest_since = None
                self.collect_bricks = False
                self.brick_acc = {}
            return
        if self.vaihe == "odotus":
            self.collect_bricks = False
            a = self.marks.get("itse_alku") or {}
            if t - a.get("t", t) >= s["itsepurkaus_tunnit"] * 3600 and resting:
                self.brick_acc = {}
                self.marks["itse_loppu_alku"] = t
                self._set_phase("itse_loppu", t)
            return
        if self.vaihe == "itse_loppu":
            if not resting:
                return                     # odotetaan, että akku on taas levossa
            self.collect_bricks = True
            el = t - self.marks["itse_loppu_alku"]
            if (self._min_brick_samples() >= 50 and el >= 60) or el >= 900:
                self.marks["itse_loppu"] = self._state_mark(t, self._brick_mark())
                self.collect_bricks = False
                self._finish(t)

    # ------------------------------------------------------------------
    def _end_start_rest(self, t, skipped: bool):
        st = self.app.decoder.state
        snap = self._snapshot(t, "lepo_alku")
        rest_min = ((t - self.rest_since) / 60) if self.rest_since else 0.0
        self.marks["lepo_alku"] = {"t": t, "kesto_min": rest_min, "ohitettu": skipped,
                                   "vaadittu_min": self.app.settings.get("lepo_alku_min"),
                                   "soc_avg": st.soc_avg, "soc_ui": st.soc_ui, "v": st.pack_v,
                                   "kennot_ka": snap.get("brick_avg"),
                                   "t_min": st.temp_min, "t_max": st.temp_max}
        if self.tyyppi == TAYSI and "ajo_loppu" not in self.marks:
            self.marks["ajo_loppu"] = self._state_mark(t, {"lepo_min": rest_min, "ohitettu": skipped})
        if skipped:
            self.notes.append(f"Lepojakso ennen latausta jäi {rest_min:.0f} minuuttiin.")
        self.rest_since = None
        self._set_phase("odota_lataus", t)

    def _begin_charge(self, t):
        st = self.app.decoder.state
        lr = self.last_rest
        t0 = self.charge_since or t
        self.marks["lataus_alku_t"] = t0
        self.marks["lataus_alku"] = {"t": t0, "soc_avg": st.soc_avg, "soc_ui": st.soc_ui,
                                     "soc_min": st.soc_min, "soc_max": st.soc_max,
                                     "ner": st.nominal_remaining_kwh, "nfp": st.nfp_kwh,
                                     "v_lepo": lr[1] if lr else None,
                                     "t_min": st.temp_min, "t_max": st.temp_max}
        self.marks["lataus_alku"]["laskurit"] = getattr(self, "_charge_mark_cnt", None) or st.counters_raw
        # Lataus tunnistetaan 10 s viiveellä: energia lasketaan latauksen alusta
        self.ch_e_neg = self.ch_ah_neg = self.ch_i2 = 0.0
        self.ch_e_pos = self.ch_ah_pos = self.ch_seconds = 0.0
        self.idle_since = None
        mark = getattr(self, "_charge_mark", (self.e_in, self.ah_in, self.i2_in, self.e_out, self.ah_out))
        (self.marks["e_in_ennen"], self.marks["ah_in_ennen"], self.marks["i2_ennen"],
         self.marks["e_out_ennen"], self.marks["ah_out_ennen"]) = mark
        self._set_phase("lataus", t)

    def _end_charge(self, t):
        st = self.app.decoder.state
        # Lisätään latauksen tunnistusviiveen aikana kertynyt energia
        pre_e = self.e_in - self.marks.get("e_in_ennen", self.e_in)
        self.marks["lataus_loppu"] = {
            "t": t, "soc_avg": st.soc_avg, "soc_ui": st.soc_ui, "soc_min": st.soc_min,
            "soc_max": st.soc_max, "ner": st.nominal_remaining_kwh, "nfp": st.nfp_kwh,
            # Täysi: akunhallinta ilmoitti latauksen valmiiksi, tai (viestissä ei ole valmis-tietoa, kuten
            # Model S/X:n 10-bittisessä muodossa) lataus loppui itsestään yli 97 %:n varauksessa
            "taysi": bool(st.full_charge_complete) or bool(
                max(st.soc_avg or 0, (st.soc_ui or 0) if st.platform not in (None, "m3", "sx") else 0) >= 97.0
                and self.idle_since and t - self.idle_since >= 300),
            "t_min": st.temp_min, "t_max": st.temp_max,
            "laskurit": st.counters_raw,
            "e_neg": self.ch_e_neg, "e_pos": self.ch_e_pos, "ah_neg": self.ch_ah_neg,
            "ah_pos": self.ch_ah_pos, "i2": self.ch_i2, "kesto_s": self.ch_seconds,
            "e_in_kokonais": pre_e, "ah_in_kokonais": self.ah_in - self.marks.get("ah_in_ennen", self.ah_in),
            "i2_kokonais": self.i2_in - self.marks.get("i2_ennen", self.i2_in),
            "e_out_kokonais": self.e_out - self.marks.get("e_out_ennen", self.e_out),
            "ah_out_kokonais": self.ah_out - self.marks.get("ah_out_ennen", self.ah_out),
        }
        if self.r_window:
            self.marks["r_ikkuna"] = self.r_window[:]
        self._snapshot(t, "lataus_loppu")
        self.rest_since = None
        self._set_phase("lepo_loppu", t)

    # -- käyttäjän toiminnot -------------------------------------------
    def skip_phase(self):
        with self.lock:
            if not self.active or not self.last_hv:
                return
            t = self.last_hv[0]
            if self.vaihe == "lepo_alku":
                self._end_start_rest(t, skipped=True)
            elif self.vaihe == "lataus":
                self.notes.append("Lataus lopetettiin käyttäjän toimesta ennen täyttä akkua.")
                self._end_charge(t)
            elif self.vaihe == "lepo_loppu":
                rest_min = ((t - self.rest_since) / 60) if self.rest_since else 0
                self.notes.append(f"Lepojakso latauksen jälkeen jäi {rest_min:.0f} minuuttiin.")
                self._finish(t)
            elif self.vaihe == "keruu":
                self._finish(t)
            elif self.vaihe == "lepo_ajo_alku":
                self._begin_drive(t, skipped=True)
            elif self.vaihe == "ajo":
                self._end_drive(t, skipped=False)
            elif self.vaihe == "lepo_ajo_loppu":
                rest_min = ((t - self.rest_since) / 60) if self.rest_since else 0
                self.notes.append(f"Lepojakso ajon jälkeen jäi {rest_min:.0f} minuuttiin.")
                self._finish(t)
            elif self.vaihe in ("kuormitus", "pikalataus"):
                self._finish(t)
            elif self.vaihe == "kuorma_lepo":
                self._load_logic(t + 999, 0.0)
            elif self.vaihe == "lepo_itse_alku":
                # Lepo lyhennetään: lähtöarvot kerätään heti (vähintään 50 näytettä kennoryhmää kohden)
                self.notes.append("Lepojakso ennen itsepurkaustestiä lyhennettiin.")
                self.rest_since = t - self.app.settings["itsepurkaus_lepo_min"] * 60

    def cancel(self):
        with self.lock:
            if not self.active:
                return
            t = self.last_hv[0] if self.last_hv else time.time()
            self._event(t, "Mittaus keskeytettiin")
            self.flush()
            self._close_raw()
            self.app.storage.update_test(self.test_id, tila="keskeytetty", paattynyt=t,
                                         tarkiste=self._raw_digest())
            self.app.decoder.remove_hv_listener(self._on_hv)
            self.app.decoder.remove_brick_listener(self._on_brick)
            self.test_id = None
            self.vaihe = None

    def _raw_digest(self) -> str | None:
        """Raakadatan tarkiste. Jatketussa mittauksessa lasketaan koko tiedostosta."""
        if self.raw_hash is not None and self.osat == 1:
            return self.raw_hash.hexdigest()
        if not self.raw_path or not self.raw_path.exists():
            return None
        h = hashlib.sha256()
        with gzip.open(self.raw_path, "rt", encoding="ascii") as f:
            for line in f:
                if not line.startswith("#"):
                    h.update(line.encode("ascii"))
        return h.hexdigest()

    def _close_raw(self):
        if self.raw:
            try:
                self.raw.close()
            except (ValueError, OSError):
                pass
            self.raw = None

    def _finish(self, t):
        self.finishing = True
        self._flush_reg()
        snap_name = {KAPASITEETTI: "lepo_loppu", TAYSI: "lepo_loppu", PIKA: "pikatarkastus"}.get(self.tyyppi, "loppu")
        snap = self._snapshot(t, snap_name)
        if self.tyyppi in (AJO, PIKA_AJO):
            rest_min = ((t - self.rest_since) / 60) if self.rest_since else 0.0
            self.marks["ajo_loppu"] = self._state_mark(t, {"lepo_min": rest_min})
        if self.tyyppi == PIKALATAUS:
            self.marks["pikalataus_loppu"] = self._state_mark(t)
        if self.tyyppi == PIKA and self.brick_acc:
            n = self.app.decoder.state.brick_count or max(self.brick_acc)
            snap["kennot"] = [(self.brick_acc[k][0] / self.brick_acc[k][1]) if k in self.brick_acc else None
                              for k in range(1, n + 1)]
            snap["kennot_naytteita"] = min(v[1] for v in self.brick_acc.values())
            self.app.storage.add_snapshot(self.test_id, t, "pikatarkastus_ka", snap)
        if self.tyyppi in (KAPASITEETTI, TAYSI):
            st = self.app.decoder.state
            rest_min = ((t - self.rest_since) / 60) if self.rest_since else 0.0
            self.marks["lepo_loppu"] = {"t": t, "kesto_min": rest_min, "soc_avg": st.soc_avg,
                                        "vaadittu_min": self.app.settings.get("lepo_loppu_min"),
                                        "kennot_ka": snap.get("brick_avg"), "v": st.pack_v}
        self.flush()
        self._event(t, "Mittaus valmis")
        self._close_raw()
        tid = self.test_id
        self.app.decoder.remove_hv_listener(self._on_hv)
        self.app.decoder.remove_brick_listener(self._on_brick)
        self.vaihe = "valmis"
        self.app.storage.update_test(tid, tila="valmis", paattynyt=t, tarkiste=self._raw_digest())
        meta = {"merkinnat": self.marks, "aukot": self.gaps, "huomiot": self.notes,
                "t_alku": self.t_start, "t_loppu": t, "lahde": self.app.source.name if self.app.source else None,
                "sovitin": (self.app.source.info if self.app.source else {}),
                "kuorma": {"kennot": {str(k): v for k, v in self.bricks_reg.items()}, "pakka": self.pack_reg,
                           "p_max_kw": self.p_max_kw,
                           "p_min_kw": self.p_min_kw, "v_min": self.v_min_load, "tapahtumat": self.load_events,
                           "i2_out": self.i2_out, "e_out": self.e_out, "e_in": self.e_in},
                "kayra": self.curve, "osat": self.osat}
        try:
            result = analysis.analyze_test(self.app.storage, tid, meta)
            self.app.storage.update_test(tid, tulos=result)
            analysis.learn_vehicle(self.app.storage, tid, result)
            # Ilmoitus, raportin rekisteröinti akveri.fi:hin ja tallennus kansioon (App.mittaus_valmis)
            if hasattr(self.app, "mittaus_valmis"):
                self.app.mittaus_valmis(tid, result)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.app.storage.update_test(tid, tulos={"virhe": f"Analyysi epäonnistui: {e}", "meta": meta})
        self.test_id = None
        self.finishing = False

    # ------------------------------------------------------------------
    def progress(self) -> dict | None:
        with self.lock:
            if not self.active:
                return None
            t = self.last_hv[0] if self.last_hv else (self.t_start or 0)
            st = self.app.decoder.state
            s = self.app.settings
            out = {
                "test_id": self.test_id, "tyyppi": self.tyyppi, "vaihe": self.vaihe,
                "vaiheet": [{"id": k, "nimi": n} for k, n in VAIHEET[self.tyyppi]],
                "kesto_s": t - (self.t_start or t), "vaihe_kesto_s": t - (self.t_phase or t),
                "e_in_kwh": self.e_in, "e_out_kwh": self.e_out, "ah_in": self.ah_in,
                "huomiot": self.notes,
            }
            if self.vaihe in ("lepo_alku", "lepo_loppu"):
                target = s["lepo_alku_min" if self.vaihe == "lepo_alku" else "lepo_loppu_min"] * 60
                out["lepo_s"] = (t - self.rest_since) if self.rest_since else 0
                out["lepo_tavoite_s"] = target
            if self.vaihe == "lataus":
                start = self.marks.get("lataus_alku", {})
                out["lataus_kwh"] = self.e_in - self.marks.get("e_in_ennen", self.e_in) + 0.0
                out["lataus_alku_soc"] = start.get("soc_avg")
                out["tauko"] = "tauko" in self.marks
                if st.soc_avg and start.get("soc_avg") is not None and st.soc_avg - start["soc_avg"] > 5:
                    # Alustava arvio ampeeritunneista ja kemian keskimääräisestä lepojännitteestä
                    ah = self.ah_in - self.marks.get("ah_in_ennen", self.ah_in)
                    v = self.app.storage.vehicle(self.vehicle_id) or {}
                    chem = (profiles.get(v.get("malli_id")) or {}).get("kemia", "NCA")
                    n = st.brick_count or 96
                    ah_full = ah / ((st.soc_avg - start["soc_avg"]) / 100)
                    out["arvio_taysi_kwh"] = ah_full * n * profiles.mean_ocv(chem, 0, 100) / 1000
            out["voi_tauottaa"] = self.can_pause()
            out["osat"] = self.osat
            if self.vaihe in ("lepo_ajo_alku", "lepo_ajo_loppu", "lepo_itse_alku"):
                key = "itsepurkaus_lepo_min" if self.vaihe == "lepo_itse_alku" else "ajo_lepo_min"
                out["lepo_s"] = (t - self.rest_since) if self.rest_since else 0
                out["lepo_tavoite_s"] = s[key] * 60
            if self.vaihe == "ajo":
                a = self.marks.get("ajo_alku") or {}
                a_soc = a.get("soc_ui") if a.get("soc_ui") is not None else a.get("soc_avg")
                out["ajo_alku_soc"] = a_soc
                out["soc_nyt"] = st.soc_ui if st.soc_ui is not None else st.soc_avg
                if self.tyyppi == PIKA_AJO:
                    out["ajo_tavoite"] = f"varaus laskee {s['pika_ajo_soc']} %-yksikköä"
                    out["ajo_tavoite_soc"] = (a_soc - s["pika_ajo_soc"]) if a_soc is not None else None
                else:
                    lim = s["kapasiteetti_lahto_soc_max"] if self.tyyppi == TAYSI else s["ajo_loppu_soc"]
                    out["ajo_tavoite"] = f"varaus enintään {lim} %"
                    out["ajo_tavoite_soc"] = lim
                if a.get("km") and st.odometer_km:
                    out["ajo_km"] = st.odometer_km - a["km"]
                out["ajo_kwh"] = self.e_out - a.get("e_out", self.e_out)
                out["tavoite_saavutettu"] = "tavoite" in self.marks
            if self.tyyppi == KUORMITUS:
                out["kuorma_tapahtumat"] = self.load_events
                out["kuorma_tavoite"] = s["kuormitus_tapahtumat"]
                out["teho_max_kw"] = self.p_max_kw
            if self.tyyppi == PIKALATAUS:
                p = (-(st.pack_v or 0) * (st.pack_i or 0) / 1000) if st.pack_v and st.pack_i is not None else None
                out["teho_kw"] = p
                out["soc_nyt"] = st.soc_ui if st.soc_ui is not None else st.soc_avg
                out["huipputeho_kw"] = max((c[2] for c in self.curve), default=None)
                a = self.marks.get("pikalataus_alku") or {}
                out["lataus_kwh"] = self.e_in - a.get("e_in", self.e_in) if a else 0.0
            if self.vaihe == "odotus":
                a = self.marks.get("itse_alku") or {}
                total = s["itsepurkaus_tunnit"] * 3600
                out["odotus_s"] = t - a.get("t", t)
                out["odotus_tavoite_s"] = total
            if self.tyyppi == PIKA:
                n = st.brick_count or 0
                got = sum(1 for k in range(1, n + 1) if self.brick_acc.get(k, [0, 0])[1] >= 10) if n else 0
                out["kennot_luettu"] = got
                out["kennot_yht"] = n
            out["tarkistukset"] = self.checks()
            return out

    def kuormitus_ehdot(self) -> list[str]:
        """Kuormitustestin lähtöehdot. Palauttaa täyttymättömät ehdot; tyhjä lista, kun testin voi aloittaa."""
        st = self.app.decoder.state
        out = []
        soc, tmin, tmax = _soc_ui(st), st.temp_min, st.temp_max
        if soc is None:
            out.append("varaustilaa ei ole vielä saatu autosta")
        elif not KUORMA_SOC[0] <= soc <= KUORMA_SOC[1]:
            out.append(f"varaus on {fmt(soc)} %, vaaditaan {KUORMA_SOC[0]:.0f}–{KUORMA_SOC[1]:.0f} %")
        if tmin is None or tmax is None:
            out.append("akun lämpötilaa ei ole vielä saatu autosta")
        else:
            if tmin < KUORMA_LAMPO[0] or tmax > KUORMA_LAMPO[1]:
                out.append(f"akun lämpötila on {fmt(tmin)}–{fmt(tmax)} °C, vaaditaan "
                           f"{KUORMA_LAMPO[0]:.0f}–{KUORMA_LAMPO[1]:.0f} °C")
            if tmax - tmin >= KUORMA_LAMPOERO:
                out.append(f"akun lämpötilaero on {fmt(tmax - tmin)} °C, vaaditaan alle {fmt(KUORMA_LAMPOERO, 0)} °C")
        return out

    def checks(self) -> list[dict]:
        """Mittausolosuhteiden tarkistukset käyttöliittymää varten."""
        st = self.app.decoder.state
        s = self.app.settings
        out = []

        def add(nimi, ok, arvo, ohje=""):
            out.append({"nimi": nimi, "ok": ok, "arvo": arvo, "ohje": ohje})

        tmin, tmax = st.temp_min, st.temp_max
        if tmin is not None and tmax is not None:
            lo, hi = KUORMA_LAMPO if self.tyyppi == KUORMITUS else (s["lampotila_min"], s["lampotila_max"])
            ok = lo <= tmin and tmax <= hi
            add("Akun lämpötila", ok, f"{fmt(tmin)}–{fmt(tmax)} °C",
                "" if ok else f"Vertailukelpoinen tulos saadaan, kun akku on {fmt(lo, 0)}–{fmt(hi, 0)} °C.")
        else:
            add("Akun lämpötila", None, "ei tietoa")
        if self.tyyppi == KAPASITEETTI and self.vaihe in ("lepo_alku", "odota_lataus"):
            soc = _soc_ui(st)
            lim = s["kapasiteetti_lahto_soc_max"]
            if soc is not None:
                ok = soc <= lim
                add("Lähtövaraus", ok, f"{fmt(soc)} %",
                    "" if ok else f"Tarkin tulos saadaan, kun latauksen alussa varaus on enintään {lim} %.")
        if self.tyyppi in (AJO, TAYSI) and self.vaihe == "lepo_ajo_alku" and _soc_ui(st) is not None:
            ok = _soc_ui(st) >= 80
            add("Lähtövaraus", ok, f"{fmt(_soc_ui(st))} %",
                "" if ok else "Tarkin tulos saadaan, kun ajo aloitetaan vähintään 80 %:n varauksesta.")
        if self.tyyppi == ITSEPURKAUS and self.vaihe == "lepo_itse_alku" and _soc_ui(st) is not None:
            v = self.app.storage.vehicle(self.vehicle_id) or {}
            if (profiles.get(v.get("malli_id")) or {}).get("kemia") == "LFP" or \
                    (v.get("opitut") or {}).get("kemia") == "LFP":
                ok = _soc_ui(st) >= 90
                add("Lähtövaraus", ok, f"{fmt(_soc_ui(st))} %",
                    "" if ok else "LFP-akun itsepurkautuminen voidaan mitata luotettavasti vain yli 90 %:n "
                                  "varauksessa. Lataa akku täyteen ennen testiä.")
        if self.tyyppi == KUORMITUS and _soc_ui(st) is not None:
            ok = KUORMA_SOC[0] <= _soc_ui(st) <= KUORMA_SOC[1]
            add("Varaus", ok, f"{fmt(_soc_ui(st))} %", "" if ok else "Kuormitustesti tehdään 40–80 %:n varauksessa.")
        if self.tyyppi == KUORMITUS and tmin is not None and tmax is not None:
            ok = tmax - tmin < KUORMA_LAMPOERO
            add("Akun lämpötilaero", ok, f"{fmt(tmax - tmin)} °C", "" if ok else "Lämpötilaeron pitää olla alle 2 °C.")
        if self.tyyppi == PIKALATAUS and self.vaihe == "odota_pikalataus" and _soc_ui(st) is not None:
            ok = _soc_ui(st) <= 30
            add("Lähtövaraus", ok, f"{fmt(_soc_ui(st))} %",
                "" if ok else "Latauskäyrä saadaan kattavimmin, kun lataus aloitetaan alle 30 %:n varauksesta.")
        if st.pack_i is not None:
            add("Akun virta", abs(st.pack_i) < LEPO_VIRTA_A if self.vaihe in (
                "lepo_alku", "lepo_loppu", "keruu", "lepo_ajo_alku", "lepo_ajo_loppu", "lepo_itse_alku") else None,
                f"{fmt(st.pack_i)} A")
        return out
