"""Tesla Model 3 / Model Y -ajoakun CAN-viestien purku.

Viestimäärittelyt perustuvat avoimeen, yhteisön ylläpitämään DBC-tiedostoon
(github.com/joshwardell/model3dbc) sekä Battery-Emulator-projektin
(github.com/dalathegreat/Battery-Emulator) havaintoihin uudemmista
ohjelmistoversioista. Ohjelma vain kuuntelee väylää eikä lähetä autolle viestejä.
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

KAYTETYT_TUNNISTEET = [ID_HV, ID_SOC, ID_ENERGY, ID_MINMAX, ID_BRICKS, ID_LIFETIME,
                       ID_VIN, ID_ODO, ID_PACKCFG, ID_LIMITS, ID_TAXI]

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

# Mittauksen kannalta välttämättömät viestit
PAKOLLISET = [ID_HV, ID_SOC, ID_ENERGY, ID_BRICKS]

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

    # ------------------------------------------------------------------
    def add_hv_listener(self, fn):
        """fn(t, volts, amps) kutsutaan jokaisesta jännite/virta-kehyksestä."""
        self._hv_listeners.append(fn)

    def remove_hv_listener(self, fn):
        if fn in self._hv_listeners:
            self._hv_listeners.remove(fn)

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
                self.state.bricks[mux * 3 + k + 1] = v
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
            for cid in KAYTETYT_TUNNISTEET:
                s = self.seen.get(cid)
                rate = None
                if s and s["count"] > 1 and s["last"] > s["first"]:
                    rate = (s["count"] - 1) / (s["last"] - s["first"])
                out.append({
                    "tunniste": f"0x{cid:03X}",
                    "kuvaus": TUNNISTE_KUVAUS[cid],
                    "pakollinen": cid in PAKOLLISET,
                    "nakyy": bool(s),
                    "kpl": s["count"] if s else 0,
                    "taajuus_hz": round(rate, 1) if rate else None,
                })
        return out

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
            return d
