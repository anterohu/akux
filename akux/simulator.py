"""Esittelytila: Teslan ajoakun fysikaalinen malli.

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
                      ID_PACKCFG, ID_SOC, ID_TAXI, ID_VIN, MILE_KM, SX_BATT_ODO, SX_BRICKS,
                      SX_ENERGY, SX_HV, SX_ODO, SX_SOC, SX_VIN)
from .sources import Source


def _vin_with_check(base: str) -> str:
    for c in "0123456789X":
        v = base[:8] + c + base[9:]
        if vinmod.check_digit_ok(v):
            return v
    return base


ESITTELYAUTOT = {
    "m3-lr": {"nimi": "Model 3 Long Range 2020 (NCA)", "opts": {}},
    "m3-lfp": {"nimi": "Model 3 Standard Range Plus 2020, Shanghai (LFP)",
               "opts": {"chem": "LFP", "cells": 106, "nfp_kwh": 52.0, "bol_kwh": 55.0, "weak_cell": 61,
                        "vin": "LRW3E7FA0LC123456"}},
    "my-lr": {"nimi": "Model Y Long Range 2022, Berliini (NMC)",
              "opts": {"chem": "NMC", "nfp_kwh": 75.1, "bol_kwh": 78.8, "vin": "XP7YGCEK0NB123456"}},
    "ms-85": {"nimi": "Model S 85 2015 (NCA, vanha viestiarkkitehtuuri)",
              "opts": {"platform": "sx", "nfp_kwh": 74.2, "bol_kwh": 81.5, "energy_format": "sx10",
                       "vin": "5YJSA1E20FF123456"}},
}


class BatterySimulator(Source):
    name = "Esittelytila"
    simulated = True

    def __init__(self, *, soc: float = 0.12, nfp_kwh: float = 75.6, bol_kwh: float = 80.5,
                 cells: int = 96, accel: float = 1.0, temp_c: float = 21.0,
                 weak_cell: int | None = 47, energy_format: str = "uusi", seed: int = 7,
                 chem: str = "NCA", vin: str | None = None, platform: str = "m3", bol_broadcast: bool = True,
                 sx_counter_swap: bool = False, sx_current_sign: int = 1,
                 leak_cell: int | None = None, leak_pct_day: float = 0.0, dc_kw: float = 110.0):
        super().__init__()
        self.leak_cell, self.leak_pct_day, self.dc_kw = leak_cell, leak_pct_day, dc_kw
        self.platform = platform
        self.sx_counter_swap = sx_counter_swap
        self.sx_current_sign = sx_current_sign
        self.rng = random.Random(seed)
        self.n = cells
        self.chem = chem
        self.curve = profiles.chemistry(self.chem)["ocv"]
        self.bol = bol_kwh
        self.bol_broadcast = bol_broadcast
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
        self.vin = _vin_with_check(vin or ("5YJSA7E26HF654321" if platform == "sx" else "5YJ3E7EB0LF654321"))
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

    def _leak(self, dt):
        """Itsepurkautuva kennoryhmä (vika): menettää varausta myös levossa."""
        if self.leak_cell and self.leak_pct_day:
            k = self.leak_cell - 1
            self.rest[k] = max(0.0, self.rest[k] - self.q[k] * self.leak_pct_day / 100 * dt / 86400)

    def _step(self, dt):
        socs = self._cell_socs()
        v_est = self._pack_voltage(self.current)
        if self.mode == "drive":
            p = self.drive_kw * (1 + 0.6 * self.rng.uniform(-1, 1))
            if self.rng.random() < 0.12:                    # jarrutusenergian palautus
                p = -0.5 * self.drive_kw
            self.current = p * 1000 / v_est
        elif self.mode == "kiihdytys":
            ph = (self.sim_t % 8.0)
            p = 140.0 if ph < 1.6 else (-25.0 if 5.5 <= ph < 6.5 else 10.0)
            self.current = p * 1000 / v_est
        elif self.mode == "pikalataus":
            smax = max(socs)
            if smax >= 0.95:
                self.current = 0.0
            else:
                soc = sum(socs) / self.n
                p = self.dc_kw if soc < 0.5 else max(20.0, self.dc_kw * (1 - (soc - 0.5) / 0.5 * 0.8))
                self.current = -p * 1000 / v_est
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
        elif self.mode == "kiihdytys":
            self.odo += dt * 50 / 3600
        self._leak(dt)
        heat = (self.current ** 2) * self.r_pack * dt / 400_000
        self.temp += heat - (self.temp - self.ambient) * dt / 7200

    # -- kehysten koodaus -----------------------------------------------
    def _hv_frame(self, pack_v, cur):
        if self.platform == "sx":
            b = bytearray(8)
            encode(b, 0, 16, pack_v, 0.01)
            put_bits(b, 16, 16, int(round(cur * self.sx_current_sign / -0.1)))
            return SX_HV, bytes(b)
        b = bytearray(8)
        encode(b, 0, 16, pack_v, 0.01)
        put_bits(b, 16, 16, int(round(cur / -0.1)))
        put_bits(b, 32, 16, int(round((cur - 822) / -0.05)))
        return ID_HV, bytes(b)

    def _sx_frames(self, t):
        """Model S 2012–2021 / Model X 2015–2021: voimalinjan väylän viestit."""
        out = []
        cur = self.current
        socs = self._cell_socs()
        volts = [self._ocv(x) - cur * r for x, r in zip(socs, self.r_cell)]
        out.append(self._hv_frame(sum(volts), cur))
        soc_avg = sum(socs) / self.n * 100
        ui = (soc_avg / 100 * self.nfp - self.buffer) / (self.nfp - self.buffer) * 100
        b = bytearray(8)
        encode(b, 0, 10, soc_avg, 0.1)
        encode(b, 10, 10, max(0.0, ui), 0.1)
        out.append((SX_SOC, bytes(b)))
        ner = soc_avg / 100 * self.nfp
        bits = 11 if self.energy_format == "sx11" else 10
        b = bytearray(8)
        for k, val in enumerate((self.nfp, ner, max(0.0, ner - self.buffer), ner * 1.01, self.nfp - ner)):
            encode(b, k * bits, bits, val, 0.1)
        encode(b, 5 * bits, 8, self.buffer, 0.1)
        if bits == 11:
            put_bits(b, 63, 1, 1 if self.full_complete else 0)
        out.append((SX_ENERGY, bytes(b)))
        pages = (self.n + 3) // 4
        for _ in range(8):
            m = self._mux401
            self._mux401 = (m + 1) % (pages + 8)
            b = bytearray(8)
            if m < pages:
                b[0] = m
                for k, v in enumerate(volts[m * 4: m * 4 + 4]):
                    put_bits(b, 8 + 14 * k, 14, int(round((v + self.rng.gauss(0, 0.0003)) / 0.000305)))
            else:
                b[0] = 24 + (m - pages)
                for k in range(4):
                    tc = self.temp + self.rng.uniform(-0.8, 0.8)
                    put_bits(b, 8 + 14 * k, 14, int(round(tc / 0.0122)) & 0x3FFF)
            out.append((SX_BRICKS, bytes(b)))
        dis, chg = int(self.total_dis * 1000), int(self.total_chg * 1000)
        if self.sx_counter_swap:
            dis, chg = chg, dis
        b = bytearray(8)
        put_bits(b, 0, 32, dis)
        put_bits(b, 32, 32, chg)
        out.append((ID_LIFETIME, bytes(b)))
        vin_b = self.vin.encode("ascii")
        for page, part in enumerate((vin_b[:7], vin_b[7:14], vin_b[14:17])):
            out.append((SX_VIN, bytes([page]) + part))
        b = bytearray(4)
        put_bits(b, 0, 32, int(self.odo / MILE_KM * 1000))
        out.append((SX_ODO, bytes(b)))
        out.append((SX_BATT_ODO, bytes(b)))
        return out

    def _frames(self, t):
        if self.platform == "sx":
            return self._sx_frames(t)
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
        # Osa ohjelmistoversioista ei täytä alkuperäisen energian kenttää (raaka-arvo 1 = 0,1 kWh)
        encode(b, 40, 10, self.bol if self.bol_broadcast else 0.1, 0.1)
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
        b[2] = int(round((self.temp + 0.6 + 40) / 0.5))
        b[3] = int(round((self.temp - 0.6 + 40) / 0.5))
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
        self.info = {"sovitin": "Simuloitu " + getattr(self, "car_name", "Model 3 Long Range 2020"),
                     "portti": "-", "suodatus": True}
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
                    cb = self._cb          # testit voivat katkaista syötön kesken kierroksen
                    if sub == 0 and cb:
                        cid, data = self._hv_frame(self._pack_voltage(self.current), self.current)
                        cb(self.sim_t, cid, data)
                cb = self._cb
                if cb:
                    for cid, data in self._frames(self.sim_t):
                        cb(self.sim_t, cid, data)
            else:
                self._leak(dt)
                self.sim_t += dt
            spent = time.time() - t0
            self._stop.wait(max(0.0, tick - spent))
        self.status = "Ei yhteyttä"
