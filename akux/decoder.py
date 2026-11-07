"""Teslan ajoakun CAN-viestien purku.

Kaksi viestiarkkitehtuuria:
- "m3": Model 3, Model Y sekä vuodesta 2021 valmistetut Model S ja Model X.
  Määrittelyt: avoin DBC-tiedosto (github.com/joshwardell/model3dbc) ja
  Battery-Emulator-projektin havainnot uudemmista ohjelmistoversioista.
- "sx": Model S 2012–2021 ja Model X 2015–2021 (voimalinjan CAN-väylä).
  Määrittelyt: Open Vehicle Monitoring System (MIT), Battery-Emulator
  (TESLA-LEGACY-BATTERY) ja wk057:n julkaisemat havainnot.

Alusta tunnistetaan automaattisesti väylällä näkyvistä viesteistä.
Ohjelma vain kuuntelee väylää eikä lähetä autolle viestejä.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from .bits import get_bits, signal

# Viestitunnisteet, joita ohjelma käyttää
ID_HV = 0x132          # akun jännite ja virta
ID_SOC = 0x292         # varaustilat ja alkuperäinen energia
ID_ENERGY = 0x352      # akunhallinnan energialaskenta
ID_MINMAX = 0x332      # kennojen min/max-jännite ja lämpötila
ID_BRICKS = 0x401      # kennoryhmien jännitteet
ID_LIFETIME = 0x3D2    # elinkaaren lataus- ja purkuenergia
ID_VIN = 0x405         # valmistenumero
ID_ODO = 0x3B6         # matkamittari
ID_PACKCFG = 0x392     # akun kokoonpano
ID_LIMITS = 0x2D2      # jännite- ja virtarajat
ID_TAXI = 0x105        # Teslan dokumentoima kolmannen osapuolen viesti (nopeus, virtatila)

# Model S 2012–2021 / Model X 2015–2021
SX_HV = 0x102          # akun jännite ja virta
SX_SOC = 0x302         # varaustila
SX_ENERGY = 0x382      # akunhallinnan energialaskenta
SX_BRICKS = 0x6F2      # kennoryhmien jännitteet ja moduulien lämpötilat
SX_VIN = 0x508         # valmistenumero
SX_ODO = 0x5D8         # matkamittari (mailia)
SX_BATT_ODO = 0x562    # akun oma matkamittari (mailia)
SX_LIMITS = 0x202      # jännite- ja virtarajat

M3_TUNNISTEET = [ID_HV, ID_SOC, ID_ENERGY, ID_MINMAX, ID_BRICKS, ID_LIFETIME,
                 ID_VIN, ID_ODO, ID_PACKCFG, ID_LIMITS, ID_TAXI]
SX_TUNNISTEET = [SX_HV, SX_SOC, SX_ENERGY, SX_BRICKS, ID_LIFETIME, SX_VIN, SX_ODO,
                 SX_BATT_ODO, SX_LIMITS]
KAYTETYT_TUNNISTEET = list(dict.fromkeys(M3_TUNNISTEET + SX_TUNNISTEET))

ALUSTAT = {
    "m3": "Model 3 / Model Y / Model S ja X 2021–",
    "sx": "Model S 2012–2021 / Model X 2015–2021",
}

TUNNISTE_KUVAUS = {
    ID_HV: "Akun jännite ja virta",
    ID_SOC: "Varaustila ja alkuperäinen energia",
    ID_ENERGY: "Akunhallinnan energialaskenta",
    ID_MINMAX: "Kennojen ääriarvot ja lämpötilat",
    ID_BRICKS: "Kennoryhmien jännitteet",
    ID_LIFETIME: "Elinkaaren energialaskurit",
    ID_VIN: "Valmistenumero (VIN)",
    ID_ODO: "Matkamittari",
    ID_PACKCFG: "Akun kokoonpano",
    ID_LIMITS: "Jännite- ja virtarajat",
    ID_TAXI: "Nopeus ja virtatila",
}
SX_KUVAUS = {
    SX_HV: "Akun jännite ja virta",
    SX_SOC: "Varaustila",
    SX_ENERGY: "Akunhallinnan energialaskenta",
    SX_BRICKS: "Kennoryhmien jännitteet ja lämpötilat",
    ID_LIFETIME: "Elinkaaren energialaskurit",
    SX_VIN: "Valmistenumero (VIN)",
    SX_ODO: "Matkamittari",
    SX_BATT_ODO: "Akun matkamittari",
    SX_LIMITS: "Jännite- ja virtarajat",
}

# Mittauksen kannalta välttämättömät viestit
PAKOLLISET = [ID_HV, ID_SOC, ID_ENERGY, ID_BRICKS]
SX_PAKOLLISET = [SX_HV, SX_SOC, SX_ENERGY, SX_BRICKS]
KAIKKI_PAKOLLISET = PAKOLLISET + SX_PAKOLLISET

# Alustan tunnistus: viestit, joita toinen alusta ei käytä akun tietoihin
M3_TUNNUS = {ID_HV, ID_SOC, ID_ENERGY, ID_BRICKS}
SX_TUNNUS = {SX_ENERGY, SX_BRICKS, SX_SOC}
MILE_KM = 1.609344


def kuvaus(cid: int, platform: str | None = None) -> str | None:
    if platform == "sx":
        return SX_KUVAUS.get(cid) or TUNNISTE_KUVAUS.get(cid)
    return TUNNISTE_KUVAUS.get(cid) or SX_KUVAUS.get(cid)

VIN_RE = re.compile(r"[A-HJ-NPR-Z0-9]{17}")

VIRTATILAT = {0: "Pois", 1: "Ilmastointi", 2: "Lisävirta", 3: "Ajo"}


@dataclass
class BatteryState:
    pack_v: float | None = None
    pack_i: float | None = None            # A, positiivinen = purku, negatiivinen = lataus
    soc_ui: float | None = None
    soc_min: float | None = None
    soc_max: float | None = None
    soc_avg: float | None = None
    bol_kwh: float | None = None           # akunhallinnan tallentama alkuperäinen energia
    nfp_kwh: float | None = None           # nykyinen täyden akun energia (nominal full pack)
    nominal_remaining_kwh: float | None = None
    expected_remaining_kwh: float | None = None
    ideal_remaining_kwh: float | None = None
    to_charge_complete_kwh: float | None = None
    buffer_kwh: float | None = None
    full_charge_complete: bool | None = None
    energy_format: str | None = None       # "vanha" tai "uusi"
    cell_v_max: float | None = None
    cell_v_min: float | None = None
    cell_v_max_num: int | None = None
    cell_v_min_num: int | None = None
    temp_max: float | None = None
    temp_min: float | None = None
    total_charge_kwh: float | None = None
    total_discharge_kwh: float | None = None
    vin: str | None = None
    odometer_km: float | None = None
    pack_mass_kg: float | None = None
    max_charge_v: float | None = None
    min_discharge_v: float | None = None
    power_state: str | None = None
    speed_kmh: float | None = None
    bricks: dict = field(default_factory=dict)   # numero (1..N) -> jännite
    brick_count: int | None = None
    platform: str | None = None            # "m3" tai "sx"
    battery_odometer_km: float | None = None
    current_check: str | None = None       # virran merkin ja mittakaavan tarkistuksen tila (sx)
    counters_raw: tuple | None = None      # elinkaarilaskurit viestin kenttäjärjestyksessä (kWh)
    last_update: float = 0.0


class TeslaDecoder:
    """Purkaa kehyksiä ja ylläpitää akun viimeisintä tilaa."""

    def __init__(self):
        self.state = BatteryState()
        self.lock = threading.RLock()
        self.seen: dict[int, dict] = {}       # tunniste -> {"count", "first", "last"}
        self.total_frames = 0
        self._vin_parts: dict[int, bytes] = {}
        self._energy_votes = {"vanha": 0, "uusi": 0}
        self._old_nfp_history: list[float] = []
        self._brick_max_mux = -1
        self._brick_seen_mux: set[int] = set()
        self._hv_listeners = []
        self._brick_listeners = []
        self._sx_reset()

    def _sx_reset(self):
        self._sx_votes = {"10": 0, "11": 0}
        self._sx_energy_hist: list[bytes] = []
        self._sx_i_scale = -0.1              # + = purku; tarkistetaan väylän tiedoista
        self._sx_vi: list[tuple] = []         # (v, i) virran merkin tarkistukseen
        self._sx_sign_ok = False
        self._sx_counter_swap = None          # None = ei tiedossa, False = Model 3 -järjestys
        self._sx_cnt_prev = None
        self._sx_cal = None                   # [laskurin alku, integroitu kWh, edellinen t]
        self._sx_brick_pages: set[int] = set()
        self._sx_temps: dict[int, float] = {}
        self._sx_vin_parts: dict[int, bytes] = {}

    # ------------------------------------------------------------------
    def add_hv_listener(self, fn):
        """fn(t, volts, amps) kutsutaan jokaisesta jännite/virta-kehyksestä."""
        self._hv_listeners.append(fn)

    def remove_hv_listener(self, fn):
        if fn in self._hv_listeners:
            self._hv_listeners.remove(fn)

    def add_brick_listener(self, fn):
        """fn(t, numero, volts, amps) kutsutaan jokaisesta kennoryhmän jännitelukemasta."""
        self._brick_listeners.append(fn)

    def remove_brick_listener(self, fn):
        if fn in self._brick_listeners:
            self._brick_listeners.remove(fn)

    def _brick_value(self, t, k, v):
        self.state.bricks[k] = v
        if self._brick_listeners and self.state.pack_i is not None:
            for fn in list(self._brick_listeners):
                fn(t, k, v, self.state.pack_i)

    def reset(self):
        with self.lock:
            self.state = BatteryState()
            self.seen.clear()
            self.total_frames = 0
            self._vin_parts.clear()
            self._energy_votes = {"vanha": 0, "uusi": 0}
            self._old_nfp_history.clear()
            self._brick_max_mux = -1
            self._brick_seen_mux.clear()
            self._sx_reset()

    @property
    def platform(self) -> str | None:
        return self.state.platform

    def required_ids(self) -> list[int]:
        return SX_PAKOLLISET if self.state.platform == "sx" else PAKOLLISET

    def energy_id(self) -> int:
        return SX_ENERGY if self.state.platform == "sx" else ID_ENERGY

    def _detect_platform(self):
        """Alusta päätellään, kun jommankumman tunnusviestejä on näkynyt riittävästi."""
        def strong(ids):
            return sum(1 for c in ids if self.seen.get(c, {}).get("count", 0) >= 3)
        m3, sx = strong(M3_TUNNUS), strong(SX_TUNNUS)
        if m3 >= 2 and m3 >= sx:
            self.state.platform = "m3"
        elif sx >= 2 and m3 == 0:
            self.state.platform = "sx"

    # ------------------------------------------------------------------
    def feed(self, t: float, can_id: int, data: bytes) -> None:
        with self.lock:
            self.total_frames += 1
            s = self.seen.get(can_id)
            if s is None:
                self.seen[can_id] = {"count": 1, "first": t, "last": t}
            else:
                s["count"] += 1
                s["last"] = t
            if self.state.platform is None and self.total_frames % 20 == 0:
                self._detect_platform()
            if self.state.platform == "sx":
                handler = self._sx_handlers.get(can_id)
            else:
                handler = self._handlers.get(can_id)
            if handler is None:
                return
            try:
                handler(self, t, data)
                self.state.last_update = t
            except Exception:
                # Viallinen tai lyhyt kehys ohitetaan
                pass

    # ------------------------------------------------------------------
    def _hv(self, t, d):
        if len(d) < 4:
            return
        v = signal(d, 0, 16, 0.01)
        i = signal(d, 16, 16, -0.1, signed=True)
        if not (100.0 < v < 600.0):
            return
        self.state.pack_v = v
        self.state.pack_i = i
        for fn in list(self._hv_listeners):
            fn(t, v, i)

    def _soc(self, t, d):
        if len(d) < 7:
            return
        st = self.state

        def pct(start):
            raw = get_bits(d, start, 10)
            return None if raw == 1023 else raw * 0.1

        st.soc_min = pct(0)
        st.soc_ui = pct(10)
        st.soc_max = pct(20)
        st.soc_avg = pct(30)
        bol_raw = get_bits(d, 40, 10)
        if bol_raw not in (0, 1023):
            st.bol_kwh = bol_raw * 0.1

    def _energy(self, t, d):
        if len(d) < 8:
            return
        st = self.state
        mux = d[0] & 0x03
        # Uudempi muoto (n. 2021 alkaen): kanavoitu, 16-bittiset kentät
        new_nfp = get_bits(d, 16, 16) * 0.02 if mux == 0 else None
        # Vanha muoto: 11-bittiset kentät 0,1 kWh:n tarkkuudella
        old_nfp = get_bits(d, 0, 11) * 0.1
        old_ner = get_bits(d, 11, 11) * 0.1

        # Muodon tunnistus: vanhassa muodossa täyden akun energia pysyy vakaana
        # ja jäljellä oleva energia on sitä pienempi.
        if st.energy_format is None:
            self._old_nfp_history.append(old_nfp)
            if len(self._old_nfp_history) > 12:
                self._old_nfp_history.pop(0)
            hist = self._old_nfp_history
            if len(hist) >= 6:
                spread = max(hist) - min(hist)
                plausible_old = 38 <= old_nfp <= 150 and old_ner <= old_nfp + 0.5
                if spread < 0.6 and plausible_old:
                    self._energy_votes["vanha"] += 1
                elif new_nfp is not None and 38 <= new_nfp <= 150:
                    self._energy_votes["uusi"] += 1
                if self._energy_votes["vanha"] >= 5:
                    st.energy_format = "vanha"
                elif self._energy_votes["uusi"] >= 3:
                    st.energy_format = "uusi"
            if st.energy_format is None:
                return

        if st.energy_format == "vanha":
            st.nfp_kwh = old_nfp
            st.nominal_remaining_kwh = old_ner
            st.expected_remaining_kwh = get_bits(d, 22, 11) * 0.1
            st.ideal_remaining_kwh = get_bits(d, 33, 11) * 0.1
            st.to_charge_complete_kwh = get_bits(d, 44, 11) * 0.1
            st.buffer_kwh = get_bits(d, 55, 8) * 0.1
            st.full_charge_complete = bool(get_bits(d, 63, 1))
        else:
            if mux == 0:
                st.nfp_kwh = get_bits(d, 16, 16) * 0.02
                st.nominal_remaining_kwh = get_bits(d, 32, 16) * 0.02
                st.ideal_remaining_kwh = get_bits(d, 48, 16) * 0.02
            elif mux == 1:
                st.full_charge_complete = bool(get_bits(d, 15, 1))
                st.buffer_kwh = get_bits(d, 16, 16) * 0.01
                st.expected_remaining_kwh = get_bits(d, 32, 16) * 0.02
                st.to_charge_complete_kwh = get_bits(d, 48, 16) * 0.02

    def _minmax(self, t, d):
        if len(d) < 4:
            return
        st = self.state
        mux = d[0] & 0x03
        if mux == 0:
            st.temp_max = d[2] * 0.5 - 40
            st.temp_min = d[3] * 0.5 - 40
        elif mux == 1 and len(d) >= 6:
            st.cell_v_max = get_bits(d, 2, 12) * 0.002
            st.cell_v_min = get_bits(d, 16, 12) * 0.002
            st.cell_v_max_num = (d[4] & 0x7F) + 1
            st.cell_v_min_num = (d[5] & 0x7F) + 1

    def _bricks(self, t, d):
        if len(d) < 4:
            return
        mux = d[0]
        status = d[1]
        if mux >= 64:
            return
        count = 3 if (status == 0x2A and len(d) >= 8) else (1 if status == 0x02 else 3)
        for k in range(count):
            off = 2 + 2 * k
            if off + 1 >= len(d):
                break
            v = (d[off] | (d[off + 1] << 8)) * 0.0001
            if 1.5 <= v <= 4.6:
                self._brick_value(t, mux * 3 + k + 1, v)
        if status == 0x02:
            self.state.brick_count = mux * 3 + 1
        else:
            self._brick_seen_mux.add(mux)
            self._brick_max_mux = max(self._brick_max_mux, mux)
            if self.state.brick_count is None or self.state.brick_count < 3 * (self._brick_max_mux + 1):
                if len(self._brick_seen_mux) >= self._brick_max_mux + 1:
                    self.state.brick_count = 3 * (self._brick_max_mux + 1)

    def _lifetime(self, t, d):
        if len(d) < 8:
            return
        dis = get_bits(d, 0, 32) * 0.001
        chg = get_bits(d, 32, 32) * 0.001
        if 0 < dis < 4_000_000 and 0 < chg < 4_000_000:
            self.state.counters_raw = (dis, chg)
        if 0 < dis < 4_000_000:
            self.state.total_discharge_kwh = dis
        if 0 < chg < 4_000_000:
            self.state.total_charge_kwh = chg

    def _vin(self, t, d):
        if len(d) < 8:
            return
        mux = d[0]
        if mux in (0x10, 0x11, 0x12):
            self._vin_parts[mux] = bytes(d[1:8])
            if len(self._vin_parts) == 3:
                raw = b"".join(self._vin_parts[k] for k in (0x10, 0x11, 0x12))
                txt = "".join(chr(c) for c in raw if 48 <= c <= 90)
                m = VIN_RE.search(txt)
                if m:
                    self.state.vin = m.group(0)

    def _odo(self, t, d):
        if len(d) < 4:
            return
        km = get_bits(d, 0, 32) * 0.001
        if 0 < km < 2_000_000:
            self.state.odometer_km = km

    def _packcfg(self, t, d):
        if len(d) >= 3 and d[0] == 1:
            self.state.pack_mass_kg = d[2] + 300

    def _limits(self, t, d):
        if len(d) < 4:
            return
        lo = signal(d, 0, 16, 0.01)
        hi = signal(d, 16, 16, 0.01)
        if 150 < lo < 450:
            self.state.min_discharge_v = lo
        if 200 < hi < 500:
            self.state.max_charge_v = hi

    def _taxi(self, t, d):
        if len(d) < 2:
            return
        self.state.power_state = VIRTATILAT.get(get_bits(d, 1, 2))
        self.state.speed_kmh = max(0.0, signal(d, 3, 12, 0.08, -40))

    _handlers = {
        ID_HV: _hv, ID_SOC: _soc, ID_ENERGY: _energy, ID_MINMAX: _minmax,
        ID_BRICKS: _bricks, ID_LIFETIME: _lifetime, ID_VIN: _vin, ID_ODO: _odo,
        ID_PACKCFG: _packcfg, ID_LIMITS: _limits, ID_TAXI: _taxi,
    }

    # -- Model S 2012–2021 / Model X 2015–2021 ---------------------------
    def _sx_hv(self, t, d):
        if len(d) < 4:
            return
        v = signal(d, 0, 16, 0.01)
        raw_i = get_bits(d, 16, 16, signed=True)
        if not (100.0 < v < 600.0):
            return
        i = raw_i * self._sx_i_scale
        st = self.state
        # Virran merkki tarkistetaan sisäisen resistanssin avulla: kuormitettuna
        # jännite laskee purkaessa ja nousee ladatessa.
        if not self._sx_sign_ok:
            self._sx_vi.append((v, i))
            if len(self._sx_vi) > 400:
                self._sx_vi.pop(0)
            if len(self._sx_vi) >= 40:
                vs = [a for a, _ in self._sx_vi]
                is_ = [b for _, b in self._sx_vi]
                n = len(vs)
                mv, mi = sum(vs) / n, sum(is_) / n
                cov = sum((a - mv) * (b - mi) for a, b in self._sx_vi) / n
                sv = (sum((a - mv) ** 2 for a in vs) / n) ** 0.5
                si = (sum((b - mi) ** 2 for b in is_) / n) ** 0.5
                if si > 3.0 and sv > 0.2:
                    corr = cov / (sv * si)
                    if corr > 0.5:
                        self._sx_i_scale = -self._sx_i_scale
                        i = -i
                        self._sx_vi.clear()
                        st.current_check = "merkki korjattu"
                    elif corr < -0.5:
                        self._sx_sign_ok = True
                        st.current_check = st.current_check or "merkki vahvistettu"
        if self._sx_cal is not None:
            last_t = self._sx_cal[2]
            if last_t is not None and 0 < t - last_t < 120 and st.pack_v is not None and st.pack_i is not None:
                self._sx_cal[1] += -(v * i + st.pack_v * st.pack_i) / 2 * (t - last_t) / 3.6e6
            self._sx_cal[2] = t
        st.pack_v = v
        st.pack_i = i
        for fn in list(self._hv_listeners):
            fn(t, v, i)

    def _sx_soc(self, t, d):
        if len(d) < 3:
            return
        st = self.state
        lo = get_bits(d, 0, 10)
        ui = get_bits(d, 10, 10)
        if lo <= 1000:
            st.soc_min = lo * 0.1
            st.soc_avg = st.soc_min
        if ui <= 1000:
            st.soc_ui = ui * 0.1

    @staticmethod
    def _sx_energy_fields(d, bits: int) -> list[float]:
        """Täysi, nimellinen jäljellä, odotettu jäljellä, ideaali jäljellä, latausta jäljellä, puskuri."""
        if bits == 11:
            return [get_bits(d, k * 11, 11) * 0.1 for k in range(5)] + [get_bits(d, 55, 8) * 0.1]
        return [get_bits(d, k * 10, 10) * 0.1 for k in range(5)] + [get_bits(d, 50, 8) * 0.1]

    def _sx_energy(self, t, d):
        if len(d) < 8:
            return
        st = self.state
        if st.energy_format is None:
            # Viestin rakenne on vaihdellut ohjelmistoversioittain (10- tai 11-bittiset kentät).
            # Oikea rakenne antaa vakaan täyden akun energian ja varaustilaa vastaavan jäljellä olevan energian.
            self._sx_energy_hist.append(bytes(d))
            if len(self._sx_energy_hist) > 10:
                self._sx_energy_hist.pop(0)
            if len(self._sx_energy_hist) >= 5:
                for bits in (10, 11):
                    rows = [self._sx_energy_fields(raw, bits) for raw in self._sx_energy_hist]
                    nfps = [r[0] for r in rows]
                    ok = all(30 <= r[0] <= 110 and r[1] <= r[0] * 1.03 and r[5] <= 10 for r in rows) \
                        and max(nfps) - min(nfps) <= 0.5
                    if ok and st.soc_ui is not None:
                        r = rows[-1]
                        if r[0] - r[5] > 5:
                            pred = (r[1] - r[5]) / (r[0] - r[5]) * 100
                            ok = abs(pred - st.soc_ui) <= max(6, st.soc_ui * 0.25)
                    if ok:
                        self._sx_votes[str(bits)] += 1
                v10, v11 = self._sx_votes["10"], self._sx_votes["11"]
                if v11 >= 3 and v10 == 0:
                    st.energy_format = "sx11"
                elif v10 >= 3 and v11 == 0:
                    st.energy_format = "sx10"
                elif min(v10, v11) >= 6:
                    st.energy_format = "sx10" if v10 >= v11 else "sx11"
            if st.energy_format is None:
                return
        bits = 11 if st.energy_format == "sx11" else 10
        (st.nfp_kwh, st.nominal_remaining_kwh, st.expected_remaining_kwh, st.ideal_remaining_kwh,
         st.to_charge_complete_kwh, st.buffer_kwh) = self._sx_energy_fields(d, bits)
        if bits == 11:
            st.full_charge_complete = bool(get_bits(d, 63, 1))

    def _sx_bricks(self, t, d):
        if len(d) < 8:
            return
        page = d[0]
        vals = [get_bits(d, 8 + 14 * k, 14) for k in range(4)]
        st = self.state
        if page < 24:
            self._sx_brick_pages.add(page)
            for k, raw in enumerate(vals):
                if raw in (0, 0x3FFF):
                    continue
                v = raw * 0.000305
                if 1.5 <= v <= 4.5:
                    self._brick_value(t, page * 4 + k + 1, v)
            if len(self._sx_brick_pages) >= 24 or (page == 0 and len(self._sx_brick_pages) > 10):
                if st.bricks:
                    st.brick_count = max(st.bricks)
        elif page < 32:
            for k, raw in enumerate(vals):
                if raw in (0, 0x3FFF):
                    continue
                if raw & 0x2000:
                    raw -= 0x4000
                c = raw * 0.0122
                if -40 <= c <= 90:
                    self._sx_temps[(page - 24) * 4 + k] = c
            if self._sx_temps:
                st.temp_min = min(self._sx_temps.values())
                st.temp_max = max(self._sx_temps.values())
        if st.bricks:
            vs = st.bricks
            kmax = max(vs, key=vs.get)
            kmin = min(vs, key=vs.get)
            st.cell_v_max, st.cell_v_max_num = vs[kmax], kmax
            st.cell_v_min, st.cell_v_min_num = vs[kmin], kmin

    def _sx_lifetime(self, t, d):
        if len(d) < 8:
            return
        a = get_bits(d, 0, 32) * 0.001
        b = get_bits(d, 32, 32) * 0.001
        if not (0 < a < 4_000_000 and 0 < b < 4_000_000):
            return
        st = self.state
        st.counters_raw = (a, b)
        prev = self._sx_cnt_prev
        self._sx_cnt_prev = (a, b)
        # Lähteet eroavat kenttien järjestyksestä: latauslaskuri on se, joka kasvaa latauksen aikana
        if prev and self._sx_counter_swap is None and self._sx_sign_ok and st.pack_i is not None:
            da, db = a - prev[0], b - prev[1]
            if st.pack_i < -2.0 and max(da, db) > 0:
                self._sx_counter_swap = da > db
            elif st.pack_i > 2.0 and max(da, db) > 0:
                self._sx_counter_swap = db > da
        swap = bool(self._sx_counter_swap)
        dis, chg = (b, a) if swap else (a, b)
        st.total_discharge_kwh, st.total_charge_kwh = dis, chg
        # Virran mittakaavan tarkistus: integroitu energia verrattuna akunhallinnan laskureihin
        if self._sx_sign_ok and self._sx_counter_swap is not None:
            net = chg - dis
            if self._sx_cal is None:
                self._sx_cal = [net, 0.0, None]
            else:
                dc = net - self._sx_cal[0]
                acc = self._sx_cal[1]
                if abs(dc) >= 0.5 and abs(acc) >= 0.2:
                    ratio = dc / acc
                    if 1.6 < ratio < 2.5 or 0.35 < ratio < 0.65:
                        self._sx_i_scale *= ratio
                        st.current_check = "mittakaava korjattu"
                    elif 0.8 <= ratio <= 1.25:
                        st.current_check = "vahvistettu energialaskurista"
                    self._sx_cal = [net, 0.0, None]

    def _sx_vin(self, t, d):
        if len(d) < 2:
            return
        page = d[0]
        if page in (0, 1, 2):
            self._sx_vin_parts[page] = bytes(d[1:8])
            if len(self._sx_vin_parts) == 3:
                raw = b"".join(self._sx_vin_parts[k] for k in (0, 1, 2))
                txt = "".join(chr(c) for c in raw if 48 <= c <= 90)
                m = VIN_RE.search(txt)
                if m:
                    self.state.vin = m.group(0)

    def _sx_odo(self, t, d):
        if len(d) < 4:
            return
        km = get_bits(d, 0, 32) * 0.001 * MILE_KM
        if 0 < km < 2_000_000:
            self.state.odometer_km = km

    def _sx_batt_odo(self, t, d):
        if len(d) < 4:
            return
        km = get_bits(d, 0, 32) * 0.001 * MILE_KM
        if 0 < km < 2_000_000:
            self.state.battery_odometer_km = km

    def _sx_limits(self, t, d):
        if len(d) < 4:
            return
        lo = signal(d, 0, 16, 0.01)
        hi = signal(d, 16, 16, 0.01)
        if 150 < lo < 450:
            self.state.min_discharge_v = lo
        if 200 < hi < 500:
            self.state.max_charge_v = hi

    _sx_handlers = {
        SX_HV: _sx_hv, SX_SOC: _sx_soc, SX_ENERGY: _sx_energy, SX_BRICKS: _sx_bricks,
        ID_LIFETIME: _sx_lifetime, SX_VIN: _sx_vin, SX_ODO: _sx_odo, SX_BATT_ODO: _sx_batt_odo,
        SX_LIMITS: _sx_limits,
    }

    # ------------------------------------------------------------------
    def bricks_list(self) -> list[float | None]:
        with self.lock:
            n = self.state.brick_count or (max(self.state.bricks) if self.state.bricks else 0)
            return [self.state.bricks.get(k) for k in range(1, n + 1)]

    def bus_report(self, now: float | None = None) -> list[dict]:
        """Yhteystestin tulos: mitkä tarvittavat viestit näkyvät ja millä taajuudella."""
        now = now if now is not None else time.time()
        out = []
        with self.lock:
            plat = self.state.platform
            ids = SX_TUNNISTEET if plat == "sx" else M3_TUNNISTEET
            req = self.required_ids()
            for cid in ids:
                s = self.seen.get(cid)
                rate = None
                if s and s["count"] > 1 and s["last"] > s["first"]:
                    rate = (s["count"] - 1) / (s["last"] - s["first"])
                out.append({
                    "tunniste": f"0x{cid:03X}",
                    "kuvaus": kuvaus(cid, plat),
                    "pakollinen": cid in req,
                    "nakyy": bool(s),
                    "kpl": s["count"] if s else 0,
                    "taajuus_hz": round(rate, 1) if rate else None,
                })
        return out

    def counts(self) -> dict:
        with self.lock:
            return {cid: v["count"] for cid, v in self.seen.items()}

    def snapshot(self) -> dict:
        with self.lock:
            st = self.state
            d = {k: getattr(st, k) for k in st.__dataclass_fields__ if k != "bricks"}
            vals = [v for v in st.bricks.values() if v]
            d["bricks_seen"] = len(vals)
            if vals:
                d["brick_avg"] = sum(vals) / len(vals)
                d["brick_delta_mv"] = (max(vals) - min(vals)) * 1000
            d["power_kw"] = (st.pack_v * st.pack_i / 1000) if st.pack_v is not None and st.pack_i is not None else None
            d["frames"] = self.total_frames
            d["platform_name"] = ALUSTAT.get(st.platform)
            return d
