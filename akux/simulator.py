"""Esittelytila: Model 3 Long Range 2020 -akun fysikaalinen malli.

Simulaattori tuottaa samat CAN-kehykset kuin auto, joten koko ohjelmaa voi
kokeilla ja esitellä ilman autoa. Aikaa voi nopeuttaa, jolloin
kapasiteettimittaus valmistuu minuuteissa.
"""
from __future__ import annotations

import random
import time

from . import profiles, vin as vinmod
from .bits import encode, put_bits
from .decoder import (ID_BRICKS, ID_ENERGY, ID_HV, ID_LIFETIME, ID_MINMAX, ID_ODO,
                      ID_PACKCFG, ID_SOC, ID_TAXI, ID_VIN)
from .sources import Source


def _vin_with_check(base: str) -> str:
    for c in "0123456789X":
        v = base[:8] + c + base[9:]
        if vinmod.check_digit_ok(v):
            return v
    return base


class BatterySimulator(Source):
    name = "Esittelytila"
    simulated = True

    def __init__(self, *, soc: float = 0.12, nfp_kwh: float = 75.6, bol_kwh: float = 80.5,
                 cells: int = 96, accel: float = 1.0, temp_c: float = 21.0,
                 weak_cell: int | None = 47, energy_format: str = "uusi", seed: int = 7):
        super().__init__()
        self.rng = random.Random(seed)
        self.n = cells
        self.chem = "NCA"
        self.curve = profiles.chemistry(self.chem)["ocv"]
        self.bol = bol_kwh
        self.nfp = nfp_kwh
        self.buffer = round(nfp_kwh * 0.045, 2)
        self.accel = accel
        self.energy_format = energy_format
        self.r_pack = 0.072                      # ohmia
        self.temp = temp_c
        self.ambient = temp_c
        # kennoryhmien kapasiteetit (Ah) ja pieni hajonta
        avg_v = profiles.mean_ocv(self.chem, 0, 100)
        self.q_nom = nfp_kwh * 1000 / (cells * avg_v)
        self.q = [self.q_nom * (1 + self.rng.gauss(0, 0.004)) for _ in range(cells)]
        if weak_cell:
            self.q[weak_cell - 1] *= 0.975
        self.rest = []
        self.set_soc(soc)
        self.r_cell = [self.r_pack / cells * (1 + self.rng.gauss(0, 0.05)) for _ in range(cells)]
        self.mode = "park"               # park | drive | charge | sleep
        self.charge_kw = 7.0
        self.drive_kw = 15.0
        self.current = 0.0
        self.total_dis = 41250.0
        self.total_chg = 44410.0
        self.odo = 112_345.0
        self.vin = _vin_with_check("5YJ3E7EB0LF654321")
        self.full_complete = False
        self.sim_t = time.time()
        self._mux401 = 0
        self.max_gap = max(5.0, 0.25 * accel)

    # -- ohjaus ---------------------------------------------------------
    def set_mode(self, mode: str, power_kw: float | None = None):
        self.mode = mode
        if power_kw is not None:
            if mode == "charge":
                self.charge_kw = power_kw
            elif mode == "drive":
                self.drive_kw = power_kw
        if mode != "charge":
            self.full_complete = False

    def set_accel(self, accel: float):
        self.accel = max(1.0, min(600.0, accel))
        self.max_gap = max(5.0, 0.25 * self.accel)

    def set_soc(self, soc: float):
        # Kennot ovat tasapainossa täyden akun päässä, kuten Teslan akuissa
        self.rest = [max(0.0, q - self.q_nom * (1 - soc)) for q in self.q]

    def now(self) -> float:
        return self.sim_t

    # -- fysiikka -------------------------------------------------------
    def _ocv(self, soc):
        s = min(100.0, max(0.0, soc * 100))
        i = min(9, int(s // 10))
        c = self.curve
        return c[i] + (c[i + 1] - c[i]) * (s - 10 * i) / 10

    def _cell_socs(self):
        return [r / q for r, q in zip(self.rest, self.q)]

    def _pack_voltage(self, current):
        return sum(self._ocv(s) - current * r for s, r in zip(self._cell_socs(), self.r_cell))

    def _step(self, dt):
        socs = self._cell_socs()
        v_est = self._pack_voltage(self.current)
        if self.mode == "drive":
            p = self.drive_kw * (1 + 0.6 * self.rng.uniform(-1, 1))
            self.current = p * 1000 / v_est
        elif self.mode == "charge":
            smax = max(socs)
            if smax >= 0.999 or self.full_complete:
                self.current = 0.0
                self.full_complete = True
            else:
                p = self.charge_kw
                if smax > 0.93:                       # vakiojännitevaihe
                    p *= max(0.15, (0.999 - smax) / 0.069)
                self.current = -p * 1000 / v_est
        elif self.mode == "park":
            self.current = 0.35 + self.rng.uniform(-0.05, 0.05)
        else:
            self.current = 0.0
        # tasapainotus lähellä täyttä akkua
        dq = self.current * dt / 3600
        for k in range(self.n):
            self.rest[k] = min(self.q[k], max(0.0, self.rest[k] - dq))
        if self.mode == "charge" and max(socs) > 0.95:
            avg = sum(socs) / self.n
            for k in range(self.n):
                if socs[k] > avg:
                    self.rest[k] -= min(0.0004 * dt, (socs[k] - avg) * self.q[k] * 0.5)
        e = abs(self.current) * v_est * dt / 3.6e6
        if self.current > 0:
            self.total_dis += e
        else:
            self.total_chg += e
        if self.mode == "drive":
            self.odo += dt * 90 / 3600
        heat = (self.current ** 2) * self.r_pack * dt / 400_000
        self.temp += heat - (self.temp - self.ambient) * dt / 7200

    # -- kehysten koodaus -----------------------------------------------
    def _hv_frame(self, pack_v, cur):
        b = bytearray(8)
        encode(b, 0, 16, pack_v, 0.01)
        put_bits(b, 16, 16, int(round(cur / -0.1)))
        put_bits(b, 32, 16, int(round((cur - 822) / -0.05)))
        return ID_HV, bytes(b)

    def _frames(self, t):
        out = []
        cur = self.current
        socs = self._cell_socs()
        volts = [self._ocv(s) - cur * r for s, r in zip(socs, self.r_cell)]
        pack_v = sum(volts)
        out.append(self._hv_frame(pack_v, cur))

        soc_avg = sum(socs) / self.n * 100
        b = bytearray(8)
        encode(b, 0, 10, min(socs) * 100, 0.1)
        ui = (soc_avg / 100 * self.nfp - self.buffer) / (self.nfp - self.buffer) * 100
        encode(b, 10, 10, max(0.0, ui), 0.1)
        encode(b, 20, 10, max(socs) * 100, 0.1)
        encode(b, 30, 10, soc_avg, 0.1)
        encode(b, 40, 10, self.bol, 0.1)
        out.append((ID_SOC, bytes(b)))

        ner = soc_avg / 100 * self.nfp
        to_full = self.nfp - ner
        if self.energy_format == "uusi":
            b = bytearray(8)
            b[0] = 0
            encode(b, 16, 16, self.nfp, 0.02)
            encode(b, 32, 16, ner, 0.02)
            encode(b, 48, 16, ner * 1.01, 0.02)
            out.append((ID_ENERGY, bytes(b)))
            b = bytearray(8)
            b[0] = 1
            put_bits(b, 15, 1, 1 if self.full_complete else 0)
            encode(b, 16, 16, self.buffer, 0.01)
            encode(b, 32, 16, max(0.0, ner - self.buffer), 0.02)
            encode(b, 48, 16, to_full, 0.02)
            out.append((ID_ENERGY, bytes(b)))
            out.append((ID_ENERGY, bytes([2, 0x26, 2, 0x20, 2, 0x80, 0, 0])))
        else:
            b = bytearray(8)
            encode(b, 0, 11, self.nfp, 0.1)
            encode(b, 11, 11, ner, 0.1)
            encode(b, 22, 11, max(0.0, ner - self.buffer), 0.1)
            encode(b, 33, 11, ner * 1.01, 0.1)
            encode(b, 44, 11, to_full, 0.1)
            encode(b, 55, 8, self.buffer, 0.1)
            put_bits(b, 63, 1, 1 if self.full_complete else 0)
            out.append((ID_ENERGY, bytes(b)))

        b = bytearray(6)
        b[0] = 0
        b[2] = int(round((self.temp + 0.8 + 40) / 0.5))
        b[3] = int(round((self.temp - 0.9 + 40) / 0.5))
        out.append((ID_MINMAX, bytes(b)))
        b = bytearray(6)
        put_bits(b, 0, 2, 1)
        vmax, vmin = max(volts), min(volts)
        encode(b, 2, 12, vmax, 0.002)
        encode(b, 16, 12, vmin, 0.002)
        b[4] = volts.index(vmax)
        b[5] = volts.index(vmin)
        out.append((ID_MINMAX, bytes(b)))

        groups = (self.n + 2) // 3
        per_tick = 8
        for _ in range(per_tick):
            m = self._mux401
            self._mux401 = (m + 1) % groups
            b = bytearray(8)
            b[0] = m
            vals = volts[m * 3: m * 3 + 3]
            b[1] = 0x2A if len(vals) == 3 else 0x02
            for k, v in enumerate(vals):
                raw = int(round((v + self.rng.gauss(0, 0.0003)) / 0.0001))
                b[2 + 2 * k] = raw & 0xFF
                b[3 + 2 * k] = raw >> 8
            out.append((ID_BRICKS, bytes(b)))

        b = bytearray(8)
        put_bits(b, 0, 32, int(self.total_dis * 1000))
        put_bits(b, 32, 32, int(self.total_chg * 1000))
        out.append((ID_LIFETIME, bytes(b)))

        vin_b = self.vin.encode("ascii")
        parts = [b"\x00\x00\x00\x00" + vin_b[:3], vin_b[3:10], vin_b[10:17]]
        for mux, p in zip((0x10, 0x11, 0x12), parts):
            out.append((ID_VIN, bytes([mux]) + p))

        b = bytearray(4)
        put_bits(b, 0, 32, int(self.odo * 1000))
        out.append((ID_ODO, bytes(b)))
        out.append((ID_PACKCFG, bytes([1, 1, 178, 0, 0, 0, 0, 0])))

        b = bytearray(8)
        ps = {"drive": 3, "charge": 1, "park": 2}.get(self.mode, 0)
        put_bits(b, 1, 2, ps)
        encode(b, 3, 12, 90.0 if self.mode == "drive" else 0.0, 0.08, -40)
        out.append((ID_TAXI, bytes(b)))
        return out

    # -- ajosilmukka ----------------------------------------------------
    def _run(self):
        self.status = "Esittelytila käynnissä"
        self.info = {"sovitin": "Simuloitu Model 3 Long Range 2020", "portti": "-", "suodatus": True}
        tick = 0.1
        while not self._stop.is_set():
            if self._scan_req:
                secs, self._scan_req = self._scan_req, None
                self.scanning_until = self.sim_t + secs * self.accel
            t0 = time.time()
            dt = tick * self.accel
            if self.mode != "sleep":
                half = dt / 2
                for sub in range(2):
                    self._step(half)
                    self.sim_t += half
                    if sub == 0 and self._cb:
                        cid, data = self._hv_frame(self._pack_voltage(self.current), self.current)
                        self._cb(self.sim_t, cid, data)
                if self._cb:
                    for cid, data in self._frames(self.sim_t):
                        self._cb(self.sim_t, cid, data)
            else:
                self.sim_t += dt
            spent = time.time() - t0
            self._stop.wait(max(0.0, tick - spent))
        self.status = "Ei yhteyttä"
