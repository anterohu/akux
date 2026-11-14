"""Hyundain ja Kian kyselyihin perustuvan lukijan testi ilman laitetta.

Keinotekoinen sarjaportti vastaa kuten OBDLink-sovitin, jonka takana on Hyundai Kona Electric 64 kWh:
akunhallinta (7E4) vastaa palvelun 22 kyselyihin monikehyksisinä ISO-TP-vastauksina, mittaristo (7C6)
mittarilukemaan ja yleiskysely (7DF) valmistenumeroon.
"""
import os
import sys
import tempfile as _tf
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AKVERI_MITTAUSKANSIO", _tf.mkdtemp(prefix="akveri-testi-"))

from akveri import hkmc  # noqa: E402
from akveri.decoder import TeslaDecoder  # noqa: E402
from akveri.sources import parse_isotp  # noqa: E402

VIN = "KMHK581GFLU123456"
CELLS = [3.80 + 0.02 * (k % 3) for k in range(98)]
CELLS[40] = 3.72                       # yksi matalampi kenno


def isotp_text(data: bytes) -> str:
    """Tavut ELM-sovittimen muotoilemaksi vastaukseksi (otsikot pois, automaattinen muotoilu)."""
    if len(data) <= 7:
        return data.hex().upper()
    lines = [f"{len(data):03X}", "0:" + data[:6].hex().upper()]
    rest, k = data[6:], 1
    while rest:
        lines.append(f"{k % 16:X}:" + rest[:7].hex().upper().ljust(14, "A"))
        rest, k = rest[7:], k + 1
    return "\r".join(lines)


def payload(header: str, cmd: str) -> bytes | None:
    if header == "7DF" and cmd == "0902":
        return bytes([0x49, 0x02, 0x01]) + VIN.encode()
    if header == "7C6" and cmd == "22B002":
        return bytes([0x62, 0xB0, 0x02]) + hkmc.encode_odo(48_250)
    if header != "7E4" or not cmd.startswith("22"):
        return None
    pid = int(cmd[2:], 16)
    echo = bytes([0x62]) + bytes.fromhex(cmd[2:])
    if pid == 0x0101:
        body = hkmc.encode_main(soc=55.0, v=3.81 * 98, i=-0.4, t_max=18, t_min=17, c_max=3.84, c_max_no=3,
                                c_min=3.72, c_min_no=41, cec=21_500.0, ced=20_100.0, charging=False)
    elif pid == 0x0105:
        body = hkmc.encode_status(soh=94.0, soc_disp=57.0, extra=CELLS[96:98])
    elif 0x220000 | pid in hkmc.P_CELLS[:3]:
        page = hkmc.P_CELLS.index(0x220000 | pid)
        body = hkmc.encode_cells(CELLS[page * 32:page * 32 + 32])
    else:
        return None
    return echo + body


class FakeHk:
    commands: list = []

    def __init__(self, port, baud, timeout=0.2):
        self.buf = b""
        self.cmd = b""
        self.hdr = "7DF"
        self.lock = threading.Lock()

    @property
    def in_waiting(self):
        return len(self.buf)

    def reset_input_buffer(self):
        with self.lock:
            self.buf = b""

    def write(self, data):
        self.cmd += data
        while b"\r" in self.cmd:
            c, self.cmd = self.cmd.split(b"\r", 1)
            c = c.decode().strip()
            if not c:
                continue
            FakeHk.commands.append(c)
            if c.startswith("ATSH"):
                self.hdr, resp = c[4:], "OK"
            elif c.startswith(("AT", "ST")):
                resp = {"ATI": "ELM327 v1.4b", "STI": "STN2255 v5.10.3", "ATZ": "\r\rELM327 v1.4b"}.get(c, "OK")
            else:
                p = payload(self.hdr, c)
                resp = isotp_text(p) if p else "NO DATA"
            with self.lock:
                self.buf += (resp + "\r\r>").encode()

    def read(self, n=1):
        with self.lock:
            out, self.buf = self.buf[:max(1, n)], self.buf[max(1, n):]
        if not out:
            time.sleep(0.005)
        return out

    def close(self):
        pass


def test_isotp_jasennys():
    data = bytes(range(0x40, 0x40 + 62))
    assert parse_isotp(isotp_text(data)) == data
    assert parse_isotp("7F2231") == bytes.fromhex("7F2231")
    assert parse_isotp("NO DATA") is None
    assert parse_isotp("SEARCHING...\r03E\r0:620101FFF7E7") is not None
    print("OK ISO-TP")


def test_kona_kyselyt():
    fake = types.ModuleType("serial")
    fake.Serial = FakeHk
    sys.modules["serial"] = fake
    from akveri.sources import PolledSource
    dec = TeslaDecoder()
    dec.configure("hkmc", cells=98, ref_kwh=64.0, lisakennot=2, malli_id="hy-kona-64")
    loop, rare = hkmc.requests("kona", 98)
    src = PolledSource("COM5", loop=loop, rare=rare)
    src.start(dec.feed)
    st = dec.state
    end = time.time() + 20
    while time.time() < end and not (st.vin and st.odometer_km and len(st.bricks) >= 98 and st.bms_soh_pct):
        time.sleep(0.1)
    src.stop()
    cmds = FakeHk.commands
    for c in ("ATSP6", "ATCAF1", "ATH0", "ATSH7E4", "ATSH7C6", "ATSH7DF", "220101", "220105", "220102", "0902"):
        assert c in cmds, (c, cmds[:40])
    assert not any(c.startswith(("STMA", "ATMA", "2E", "2F", "31", "10", "11", "14")) for c in cmds), \
        "lukijan pitää lähettää vain lukukyselyitä"
    assert st.vin == VIN
    assert st.odometer_km == 48_250
    assert abs(st.pack_v - 3.81 * 98) < 0.11 and abs(st.pack_i + 0.4) < 0.01
    assert st.soc_avg == 55.0 and st.soc_ui == 57.0
    assert st.bms_soh_pct == 94.0 and abs(st.nfp_kwh - 60.16) < 0.01
    assert st.total_charge_kwh == 21_500.0 and st.total_discharge_kwh == 20_100.0
    assert st.brick_count == 98 and len(st.bricks) == 98
    assert abs(st.bricks[41] - 3.72) < 0.011 and abs(st.bricks[97] - CELLS[96]) < 0.011
    assert src.info.get("lukutapa") == "kyselyt"
    print("väyläraportti:", dec.bus_report())
    print("OK Kona-kyselyt:", round(st.nfp_kwh, 2), "kWh,", len(st.bricks), "kennoa")


class Asleep(FakeHk):
    def write(self, data):
        if b"22" in data or b"0902" in data:
            self.cmd += b""
            with self.lock:
                self.buf += b"NO DATA\r\r>"
            return
        super().write(data)


def test_auto_ei_vastaa():
    fake = types.ModuleType("serial")
    fake.Serial = Asleep
    sys.modules["serial"] = fake
    from akveri.sources import PolledSource
    loop, rare = hkmc.requests("kona", 98)
    src = PolledSource("COM5", loop=loop, rare=rare)
    src.start(lambda *a: None)
    end = time.time() + 15
    while time.time() < end and "ei vastaa" not in src.status:
        time.sleep(0.1)
    st = src.status
    src.stop()
    assert "onko auto päällä" in st, st
    print("OK nukkuva auto:", st)


def test_leaf_virran_suunta():
    """Leafin virran etumerkki päätellään varaustilan muutoksesta: kumpikin tulkinta johtaa oikeaan suuntaan."""
    from akveri import profiles
    from akveri.simulator import LeafSimulator
    m = profiles.get("nis-leaf-40")
    for raw_sign in (-1, 1):
        sim = LeafSimulator(ze1=True, ref_ah=115.0, raw_sign=raw_sign, chem="NMC", cells=96, nfp_kwh=36.4,
                            bol_kwh=40.0, soc=0.6, accel=1)
        dec = TeslaDecoder()
        dec.configure("leaf", cells=96, ref_kwh=40.0, ref_ah=115.0, malli_id=m["id"])
        sim.set_mode("drive", 30.0)
        t = 0.0
        for _ in range(4000):
            sim._step(1.0)
            sim.sim_t += 1.0
            t += 1.0
            cid, data = sim._hv_frame(sim._pack_voltage(sim.current), sim.current)
            dec.feed(t, cid, data)
            if dec.hk.get("sign_locked"):
                break
        assert dec.hk.get("sign_locked"), "suuntaa ei päätelty"
        assert dec.hk["sign"] == raw_sign, (dec.hk["sign"], raw_sign)
        assert abs(dec.state.pack_i - sim.current) < 0.05, (dec.state.pack_i, sim.current)
        print(f"OK Leafin virran suunta {raw_sign:+d}: lukittu {t:.0f} s:n ajon jälkeen")


def test_leaf_kyselyt():
    """Nissan Leaf: kyselyt osoitteeseen 79B, vuonohjaus samalle ohjainlaitteelle, vastaus 7BB."""
    from akveri import leaf, profiles
    m = profiles.get("nis-leaf-40")
    cells = [3.95 + 0.001 * (k % 5) for k in range(96)]

    def leaf_payload(header, cmd):
        if header == "79B" and cmd == "2101":
            return bytes([0x61, 0x01]) + leaf.encode_main(soc=72.5, v=380.2, i=-12.0, ah=106.0, ze1=True)
        if header == "79B" and cmd == "2102":
            return bytes([0x61, 0x02]) + leaf.encode_cells(cells, 380.2)
        if header == "79B" and cmd == "2104":
            return bytes([0x61, 0x04]) + leaf.encode_temps([14, 15, None, 14])
        if header == "79B" and cmd == "2161":
            return bytes([0x61, 0x61]) + leaf.encode_soh(91.5)
        if header == "797" and cmd == "2181":
            return bytes([0x61, 0x81]) + leaf.encode_vin("SJNFAAZE1U6012345")
        if header == "743" and cmd == "220E01":
            return bytes([0x62, 0x0E, 0x01]) + leaf.encode_odo(61_200)
        return None

    class FakeLeaf(FakeHk):
        def write(self, data):
            self.cmd += data
            while b"\r" in self.cmd:
                c, self.cmd = self.cmd.split(b"\r", 1)
                c = c.decode().strip()
                if not c:
                    continue
                FakeHk.commands.append(c)
                if c.startswith("ATSH"):
                    self.hdr, resp = c[4:], "OK"
                elif c.startswith(("AT", "ST")):
                    resp = {"ATI": "ELM327 v1.4b", "STI": "STN2255 v5.10.3", "ATZ": "\r\rELM327 v1.4b"}.get(c, "OK")
                else:
                    p = leaf_payload(self.hdr, c)
                    resp = isotp_text(p) if p else "NO DATA"
                with self.lock:
                    self.buf += (resp + "\r\r>").encode()

    fake = types.ModuleType("serial")
    fake.Serial = FakeLeaf
    sys.modules["serial"] = fake
    FakeHk.commands.clear()
    from akveri.sources import PolledSource
    dec = TeslaDecoder()
    dec.configure("leaf", **leaf.decoder_opts(m))
    loop, rare = leaf.requests_for(m)
    src = PolledSource("COM6", loop=loop, rare=rare, rx=leaf.RX)
    src.start(dec.feed)
    st = dec.state
    end = time.time() + 20
    while time.time() < end and not (st.vin and st.odometer_km and len(st.bricks) == 96 and st.bms_soh_pct
                                     and st.temp_max is not None):
        time.sleep(0.1)
    src.stop()
    cmds = FakeHk.commands
    for c in ("ATSH79B", "ATCRA7BB", "ATFCSH79B", "ATFCSD300000", "ATFCSM1", "ATSH797", "ATCRA79A",
              "ATSH743", "ATCRA763", "2101", "2102", "2104", "2161", "2181", "220E01"):
        assert c in cmds, c
    assert st.vin == "SJNFAAZE1U6012345" and st.odometer_km == 61_200
    assert abs(st.pack_v - 380.2) < 0.01 and abs(st.pack_i + 12.0) < 0.01     # lataus 12 A
    assert st.soc_avg == 72.5 and st.bms_soh_pct == 91.5 and abs(st.nfp_kwh - 36.6) < 0.01
    assert st.temp_max == 15 and st.temp_min == 14
    assert len(st.bricks) == 96 and abs(st.bricks[5] - cells[4]) < 0.0005
    print("OK Leaf-kyselyt:", round(st.nfp_kwh, 2), "kWh,", len(st.bricks), "kennoa")


def test_meb_kyselyt():
    """MEB: 29-bittiset tunnisteet (protokolla 7), kenno kerrallaan; kennomäärä selviää puuttuvasta kennosta."""
    from akveri import meb, profiles
    m = profiles.get("vw-meb-77")
    cells = [3.70 + 0.002 * (k % 4) for k in range(96)]

    def meb_payload(header, cmd):
        pid = int(cmd[2:], 16)
        echo = bytes([0x62]) + bytes.fromhex(cmd[2:])
        if header == "17FC007B":
            if 0x1E40 <= pid <= 0x1EAB:
                k = pid - 0x1E40
                return echo + meb.encode(meb.M_CELL0 + k, v=cells[k] if k < 96 else None)
            vals = {0x1E3B: (meb.M_V, {"v": 355.5}), 0x1E3D: (meb.M_I, {"i": 25.3}),
                    0x028C: (meb.M_SOC, {"soc": 64.0}), 0x1E0E: (meb.M_TMAX, {"c": 21.0}),
                    0x1E0F: (meb.M_TMIN, {"c": 19.5}), 0x1E32: (meb.M_LIFE, {"chg": 9_800.0, "dis": 9_300.0}),
                    0x50CE: (meb.M_SOH, {"soh": 93.2})}
            if pid in vals:
                cid, kw = vals[pid]
                return echo + meb.encode(cid, **kw)
        if header == "17FC0076" and pid == 0xF802:
            return echo + meb.encode(meb.M_VIN, vin="WVGZZZE2ZMP012345")
        if header == "17FC0076" and pid == 0x295A:
            return echo + meb.encode(meb.M_ODO, km=33_100)
        return None

    class FakeMeb(FakeHk):
        def write(self, data):
            self.cmd += data
            while b"\r" in self.cmd:
                c, self.cmd = self.cmd.split(b"\r", 1)
                c = c.decode().strip()
                if not c:
                    continue
                FakeHk.commands.append(c)
                if c.startswith("ATSH"):
                    self.hdr, resp = c[4:], "OK"
                elif c.startswith(("AT", "ST")):
                    resp = {"ATI": "ELM327 v1.4b", "STI": "STN2255 v5.10.3", "ATZ": "\r\rELM327 v1.4b"}.get(c, "OK")
                else:
                    p = meb_payload(self.hdr, c)
                    resp = isotp_text(p) if p else "NO DATA"
                with self.lock:
                    self.buf += (resp + "\r\r>").encode()

    fake = types.ModuleType("serial")
    fake.Serial = FakeMeb
    sys.modules["serial"] = fake
    FakeHk.commands.clear()
    from akveri.sources import PolledSource
    dec = TeslaDecoder()
    opts = meb.decoder_opts(m)
    opts["cells"] = None                          # kennomäärä päätellään autosta
    dec.configure("meb", **opts)
    loop, rare = meb.requests_for({**m, "sarjakennot": None})
    src = PolledSource("COM7", loop=loop, rare=rare, rx=meb.RX, protocol=meb.PROTOKOLLA)
    src.start(dec.feed)
    st = dec.state
    end = time.time() + 30
    while time.time() < end and not (st.vin and st.odometer_km and st.brick_count == 96 and len(st.bricks) == 96
                                     and st.bms_soh_pct and st.total_charge_kwh):
        time.sleep(0.1)
    src.stop()
    cmds = FakeHk.commands
    for c in ("ATSP7", "ATSH17FC007B", "ATCRA17FE007B", "ATFCSH17FC007B", "ATSH17FC0076", "ATCRA17FE0076",
              "221E3B", "221E3D", "22028C", "221E40", "221EAB", "2250CE", "22F802", "22295A"):
        assert c in cmds, c
    assert st.vin == "WVGZZZE2ZMP012345" and st.odometer_km == 33_100
    assert abs(st.pack_v - 355.5) < 0.01 and abs(st.pack_i - 25.3) < 0.01
    assert abs(st.soc_avg - 64.0) < 0.21 and st.bms_soh_pct == 93.2 and abs(st.nfp_kwh - 82.0 * 0.932) < 0.01
    assert abs(st.temp_max - 21.0) < 0.02 and abs(st.temp_min - 19.5) < 0.02
    assert abs(st.total_charge_kwh - 9_800.0) < 0.01 and abs(st.total_discharge_kwh - 9_300.0) < 0.01
    assert st.brick_count == 96 and abs(st.bricks[96] - cells[95]) < 0.0005
    print("OK MEB-kyselyt:", round(st.nfp_kwh, 2), "kWh,", st.brick_count, "kennoa")



def _mg_testi(malli_id, bms, odo_hdr, odo_pid):
    """MG: kysely akunhallinnalle; lohkot (matalin ja korkein kenno), kuntoarvio, varaustila ja tunnisteet."""
    from akveri import mg, profiles
    m = profiles.get(malli_id)
    g = mg.ryhma(m)
    lohkot = [(3.700 + 0.001 * k, 3.704 + 0.001 * k) for k in range(g["lohkot"])]
    lohkot[4] = (3.652, 3.706)                    # lohkon 5 matalin kenno poikkeaa

    def mg_payload(header, cmd):
        if cmd == "015B":
            return bytes([0x41, 0x5B]) + mg.encode(mg.M_SOC_UI, ui=60.0) if header == bms else None
        pid = int(cmd[2:], 16)
        echo = bytes([0x62]) + bytes.fromhex(cmd[2:])
        if header == bms:
            if pid in mg.LOHKO_PID[:g["lohkot"]]:
                k = mg.LOHKO_PID.index(pid)
                return echo + mg.encode(mg.M_BLK0 + k, vmin=lohkot[k][0], vmax=lohkot[k][1], tmin=18.5, tmax=21.0)
            vals = {0xB042: (mg.M_V, {"v": 398.25}), 0xB043: (mg.M_I, {"i": -31.5}), 0xB046: (mg.M_SOC_RAW, {"raw": 58.4}),
                    0xB056: (mg.M_TEMP, {"c": 20.0}), 0xB058: (mg.M_CMAX, {"v": 3.73}), 0xB059: (mg.M_CMIN, {"v": 3.652}),
                    0xB061: (mg.M_SOH, {"soh": 94.6})}
            if pid in vals:
                cid, kw = vals[pid]
                return echo + mg.encode(cid, **kw)
        if header == odo_hdr and pid == 0xF190:
            return echo + mg.encode(mg.M_VIN, vin="LSJWH4092PN012345")
        if header == odo_hdr and pid == odo_pid:
            return echo + mg.encode(mg.M_ODO, km=42_700)
        return None

    class FakeMg(FakeHk):
        def write(self, data):
            self.cmd += data
            while b"\r" in self.cmd:
                c, self.cmd = self.cmd.split(b"\r", 1)
                c = c.decode().strip()
                if not c:
                    continue
                FakeHk.commands.append(c)
                if c.startswith("ATSH"):
                    self.hdr, resp = c[4:], "OK"
                elif c.startswith(("AT", "ST")):
                    resp = {"ATI": "ELM327 v1.4b", "STI": "STN2255 v5.10.3", "ATZ": "\r\rELM327 v1.4b"}.get(c, "OK")
                else:
                    p = mg_payload(self.hdr, c)
                    resp = isotp_text(p) if p else "NO DATA"
                with self.lock:
                    self.buf += (resp + "\r\r>").encode()

    fake = types.ModuleType("serial")
    fake.Serial = FakeMg
    sys.modules["serial"] = fake
    FakeHk.commands.clear()
    from akveri.sources import PolledSource
    dec = TeslaDecoder()
    dec.configure("mg", **mg.decoder_opts(m))
    loop, rare = mg.requests_for(m)
    src = PolledSource("COM8", loop=loop, rare=rare, rx=mg.RX, protocol=mg.PROTOKOLLA, fc=mg.FC)
    src.start(dec.feed)
    st = dec.state
    end = time.time() + 30
    while time.time() < end and not (st.vin and st.odometer_km and len(st.bricks) == 2 * g["lohkot"]
                                     and st.bms_soh_pct and st.soc_avg is not None and st.pack_i is not None):
        time.sleep(0.1)
    src.stop()
    return m, g, st, FakeHk.commands, lohkot


def test_mg4_kyselyt():
    """MG4: yleiskysely 7DF, vastaus 7ED ja vuonohjaus akunhallinnalle 7E5; näytön varaustila palvelulla 01."""
    m, g, st, cmds, lohkot = _mg_testi("mg4-64", "7DF", "710", 0xB921)
    i = cmds.index("ATSH7DF")
    assert cmds[i + 1] == "ATCRA7ED" and cmds[i + 2] == "ATFCSH7E5", cmds[i:i + 4]
    assert "ATAR" not in cmds[i:i + 3]
    for c in ("22B042", "22B043", "015B", "22B001", "22B115", "22B061", "ATSH710", "ATCRA718", "22F190", "22B921"):
        assert c in cmds, c
    assert st.vin == "LSJWH4092PN012345" and st.odometer_km == 42_700
    assert abs(st.pack_v - 398.25) < 0.01 and abs(st.pack_i + 31.5) < 0.03 and st.power_state == "lataus"
    # Näytön 60 % vastaa koko akun aluetta 2,5 + 60 · 0,905 = 56,8 %
    assert abs(st.soc_ui - 60.0) < 0.3 and abs(st.soc_avg - (2.5 + 60.0 * 0.905)) < 0.3
    assert st.bms_soh_pct == 94.6 and abs(st.nfp_kwh - 64.0 * 0.946) < 0.01
    assert st.brick_count == 48 and len(st.bricks) == 48
    assert abs(st.bricks[9] - 3.652) < 0.001 and abs(st.bricks[10] - 3.706) < 0.001     # lohko 5: matalin, korkein
    assert st.cell_v_min_num == 9 and abs(st.cell_v_min - 3.652) < 0.001
    assert st.temp_min == 18.5 and st.temp_max == 21.0
    print("OK MG4-kyselyt:", round(st.nfp_kwh, 2), "kWh,", g["lohkot"], "lohkoa")


def test_mg_zs_kyselyt():
    """MG ZS EV 2019–2021: akunhallinta 781 (vastaus 789), varaustila koko akun alueelta (22 B046)."""
    m, g, st, cmds, lohkot = _mg_testi("mg-zs-44", "781", "7E3", 0xE101)
    for c in ("ATSH781", "ATCRA789", "ATFCSH781", "22B046", "22B0B3", "ATSH7E3", "ATCRA7EB", "22E101"):
        assert c in cmds, c
    assert "22B0BB" not in cmds                    # vain 9 lohkoa
    assert abs(st.soc_avg - 58.4) < 0.01 and abs(st.soc_ui - (584 - 25) * 100 / (940 - 25)) < 0.01
    assert st.brick_count == 18 and abs(st.nfp_kwh - 44.5 * 0.946) < 0.01 and st.bol_kwh is None
    print("OK MG ZS EV -kyselyt:", round(st.nfp_kwh, 2), "kWh,", g["lohkot"], "lohkoa")


if __name__ == "__main__":
    test_mg4_kyselyt()
    test_mg_zs_kyselyt()
    test_meb_kyselyt()
    test_leaf_virran_suunta()
    test_leaf_kyselyt()
    test_isotp_jasennys()
    test_kona_kyselyt()
    test_auto_ei_vastaa()
