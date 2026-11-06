"""Mittausten ohjaus: tallennus, vaiheet ja energian integrointi."""
from __future__ import annotations

import gzip
import hashlib
import threading
import time
from pathlib import Path

from . import analysis, profiles
from .analysis import fmt

PIKA = "pikatarkastus"
KAPASITEETTI = "kapasiteetti"

VAIHEET = {
    PIKA: [("keruu", "Tietojen keruu"), ("valmis", "Valmis")],
    KAPASITEETTI: [
        ("lepo_alku", "Lepo ennen latausta"),
        ("odota_lataus", "Latauksen aloitus"),
        ("lataus", "Lataus täyteen"),
        ("lepo_loppu", "Lepo latauksen jälkeen"),
        ("valmis", "Valmis"),
    ],
}

LEPO_VIRTA_A = 3.0        # tätä pienempi virta = auto levossa
LATAUS_VIRTA_A = 2.0      # latausvirran tunnistusraja
SAMPLE_INTERVAL = 5.0     # näytteenottoväli (s, mittausaikaa)
SNAPSHOT_INTERVAL = 600.0


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
        self.quick_started = None
        self.notes: list[str] = []
        self.finishing = False

    @property
    def active(self) -> bool:
        return self.test_id is not None

    # ------------------------------------------------------------------
    def start(self, vehicle_id: int, tyyppi: str, mittarilukema=None, mittaaja="", lisatiedot="") -> int:
        with self.lock:
            if self.active:
                raise RuntimeError("Mittaus on jo käynnissä.")
            if not self.app.source or not self.app.source.running:
                raise RuntimeError("Yhdistä ensin sovittimeen tai esittelytilaan.")
            st = self.app.storage
            self._reset_counters()
            tid = st.add_test(vehicle_id, tyyppi, mittarilukema, mittaaja, lisatiedot)
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
            self._event(now, "Mittaus aloitettu (" + ("pikatarkastus" if tyyppi == PIKA else "kapasiteettimittaus") + ")")
            self._set_phase("keruu" if tyyppi == PIKA else "lepo_alku", now)
            if tyyppi == PIKA:
                self.quick_started = now
                self.brick_acc = {}
            self.app.decoder.add_hv_listener(self._on_hv)
            self._snapshot(now, "alku")
            return tid

    def on_frame(self, t, cid, data):
        """Kutsutaan jokaisesta kehyksestä (raakadatan tallennus)."""
        if self.raw is not None:
            line = f"{t:.3f};{cid:03X};{data.hex().upper()}\n"
            try:
                self.raw.write(line)
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
                   "lepo_loppu": "Akku on täynnä. Mittaus jatkuu lepojaksolla."}.get(vaihe)
            if msg:
                self.app.notify("vaiheet", names[vaihe], msg)
        self._persist_state()

    def _event(self, t, txt):
        if self.test_id:
            self.app.storage.add_event(self.test_id, t, txt)

    def _persist_state(self):
        if not self.test_id:
            return
        state = {"vaihe": self.vaihe, "merkinnat": self.marks, "aukot": self.gaps,
                 "huomiot": self.notes, "t_alku": self.t_start}
        self.app.storage.update_test(self.test_id, tulos={"keskeneräinen": state})

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
            st = self.app.decoder.state
            for g in self.gaps:
                seen = self.app.decoder.seen.get(self.app.decoder.energy_id()) or {}
                if g.get("ner_loppu") is None and "_e_mark" in g and seen.get("last", 0) > g["loppu"] \
                        and st.nominal_remaining_kwh is not None:
                    since = (self.e_in - self.e_out) - g.pop("_e_mark")
                    g["ner_loppu"] = st.nominal_remaining_kwh - since
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

    def flush(self):
        if self.test_id and self.pending_samples:
            self.app.storage.add_samples(self.test_id, self.pending_samples)
            self.pending_samples = []
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
        for k, val in d.state.bricks.items():
            acc = self.brick_acc.setdefault(k, [0.0, 0])
            acc[0] += val
            acc[1] += 1
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

    # ------------------------------------------------------------------
    def _end_start_rest(self, t, skipped: bool):
        st = self.app.decoder.state
        snap = self._snapshot(t, "lepo_alku")
        rest_min = ((t - self.rest_since) / 60) if self.rest_since else 0.0
        self.marks["lepo_alku"] = {"t": t, "kesto_min": rest_min, "ohitettu": skipped,
                                   "soc_avg": st.soc_avg, "soc_ui": st.soc_ui, "v": st.pack_v,
                                   "kennot_ka": snap.get("brick_avg"),
                                   "t_min": st.temp_min, "t_max": st.temp_max}
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
            "taysi": bool(st.full_charge_complete), "t_min": st.temp_min, "t_max": st.temp_max,
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

    def cancel(self):
        with self.lock:
            if not self.active:
                return
            t = self.last_hv[0] if self.last_hv else time.time()
            self._event(t, "Mittaus keskeytettiin")
            self.flush()
            self._close_raw()
            self.app.storage.update_test(self.test_id, tila="keskeytetty", paattynyt=t,
                                         tarkiste=self.raw_hash.hexdigest() if self.raw_hash else None)
            self.app.decoder.remove_hv_listener(self._on_hv)
            self.test_id = None
            self.vaihe = None

    def _close_raw(self):
        if self.raw:
            try:
                self.raw.close()
            except (ValueError, OSError):
                pass
            self.raw = None

    def _finish(self, t):
        self.finishing = True
        snap_name = "lepo_loppu" if self.tyyppi == KAPASITEETTI else "pikatarkastus"
        snap = self._snapshot(t, snap_name)
        if self.tyyppi == PIKA and self.brick_acc:
            n = self.app.decoder.state.brick_count or max(self.brick_acc)
            snap["kennot"] = [(self.brick_acc[k][0] / self.brick_acc[k][1]) if k in self.brick_acc else None
                              for k in range(1, n + 1)]
            snap["kennot_naytteita"] = min(v[1] for v in self.brick_acc.values())
            self.app.storage.add_snapshot(self.test_id, t, "pikatarkastus_ka", snap)
        if self.tyyppi == KAPASITEETTI:
            st = self.app.decoder.state
            rest_min = ((t - self.rest_since) / 60) if self.rest_since else 0.0
            self.marks["lepo_loppu"] = {"t": t, "kesto_min": rest_min, "soc_avg": st.soc_avg,
                                        "kennot_ka": snap.get("brick_avg"), "v": st.pack_v}
        self.flush()
        self._event(t, "Mittaus valmis")
        self._close_raw()
        tid = self.test_id
        self.app.decoder.remove_hv_listener(self._on_hv)
        self.vaihe = "valmis"
        self.app.storage.update_test(tid, tila="valmis", paattynyt=t,
                                     tarkiste=self.raw_hash.hexdigest() if self.raw_hash else None)
        meta = {"merkinnat": self.marks, "aukot": self.gaps, "huomiot": self.notes,
                "t_alku": self.t_start, "t_loppu": t, "lahde": self.app.source.name if self.app.source else None,
                "sovitin": (self.app.source.info if self.app.source else {})}
        try:
            result = analysis.analyze_test(self.app.storage, tid, meta)
            self.app.storage.update_test(tid, tulos=result)
            y = result.get("yhteenveto") or {}
            if y.get("kunto_pct") is not None:
                kwh = y.get("kapasiteetti_kwh")
                txt = f"Akun kunto {y['kunto_pct']:.1f} %".replace(".", ",") + \
                      (f", kapasiteetti {kwh:.1f} kWh".replace(".", ",") if kwh else "") + ". Raportti on valmis."
            else:
                txt = "Mittaus on valmis. Avaa tulos ohjelmasta."
            self.app.notify("valmis", "Mittaus valmis", txt)
            analysis.learn_vehicle(self.app.storage, tid, result)
            if self.app.settings.get("mittaus_tallennus", True):
                try:
                    from . import mittaustiedosto
                    paths = mittaustiedosto.save_to_folder(self.app.storage, tid)
                    if paths:
                        self.app.storage.add_event(tid, t, f"Mittaustiedosto ja raportti tallennettu: {paths[0].parent}")
                except Exception as e:  # noqa: BLE001
                    self.app.storage.add_event(tid, t, f"Mittaustiedoston tallennus epäonnistui: {e}")
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
            if self.tyyppi == PIKA:
                n = st.brick_count or 0
                got = sum(1 for k in range(1, n + 1) if self.brick_acc.get(k, [0, 0])[1] >= 10) if n else 0
                out["kennot_luettu"] = got
                out["kennot_yht"] = n
            out["tarkistukset"] = self.checks()
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
            ok = s["lampotila_min"] <= tmin and tmax <= s["lampotila_max"]
            add("Akun lämpötila", ok, f"{fmt(tmin)}–{fmt(tmax)} °C",
                "" if ok else f"Vertailukelpoinen tulos saadaan, kun akku on {s['lampotila_min']}–{s['lampotila_max']} °C.")
        else:
            add("Akun lämpötila", None, "ei tietoa")
        if self.tyyppi == KAPASITEETTI and self.vaihe in ("lepo_alku", "odota_lataus"):
            soc = st.soc_ui
            lim = s["kapasiteetti_lahto_soc_max"]
            if soc is not None:
                ok = soc <= lim
                add("Lähtövaraus", ok, f"{fmt(soc)} %",
                    "" if ok else f"Tarkin tulos saadaan, kun latauksen alussa varaus on enintään {lim} %.")
        if st.pack_i is not None:
            add("Akun virta", abs(st.pack_i) < LEPO_VIRTA_A if self.vaihe in ("lepo_alku", "lepo_loppu", "keruu") else None,
                f"{fmt(st.pack_i)} A")
        return out
