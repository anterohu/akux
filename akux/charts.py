"""Raporttien kuvaajat (matplotlib)."""
from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

FONT_DIR = Path(__file__).parent / "data" / "fonts"
for f in FONT_DIR.glob("Inter-*.ttf"):
    font_manager.fontManager.addfont(str(f))

INK = "#1B2430"
MUTED = "#6B7480"
GRID = "#E3E6EA"
ACCENT = "#1F4E79"
ACCENT_2 = "#C2410C"
GOOD = "#2F7D4F"
WARN = "#B7791F"
BAD = "#B42318"

plt.rcParams.update({
    "font.family": "Inter",
    "font.size": 8,
    "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED,
    "axes.titlecolor": INK,
    "axes.titlesize": 9,
    "axes.titleweight": "semibold",
    "axes.titlelocation": "left",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
    "legend.fontsize": 7.5,
    "figure.dpi": 100,
})


def _fi(d=0):
    return FuncFormatter(lambda x, _: f"{x:,.{d}f}".replace(",", " ").replace(".", ","))


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return buf.getvalue()


def cell_chart(volts: list, title: str, width_mm=174, height_mm=62, poikkeavat=()) -> bytes:
    vals = [v for v in volts if v]
    mean = sum(vals) / len(vals)
    dev = [((v - mean) * 1000) if v else 0 for v in volts]
    out = {p["nro"] for p in poikkeavat}
    colors = [BAD if (k + 1) in out else ACCENT for k in range(len(volts))]
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax.bar(range(1, len(volts) + 1), dev, color=colors, width=0.72, zorder=3)
    ax.axhline(0, color=INK, linewidth=0.7, zorder=4)
    ax.set_xlim(0.3, len(volts) + 0.7)
    lim = max(5.0, max(abs(x) for x in dev) * 1.25)
    ax.set_ylim(-lim, lim)
    ax.set_ylabel("Poikkeama keskiarvosta (mV)")
    ax.set_xlabel("Kennoryhmä")
    step = 8 if len(volts) > 60 else 4
    ax.set_xticks([1] + list(range(step, len(volts) + 1, step)))
    ax.yaxis.set_major_formatter(_fi(0))
    ax.grid(axis="x", visible=False)
    ax.set_title(title + f"  ·  keskiarvo {mean:.4f} V".replace(".", ","))
    return _png(fig)


def capacity_chart(samples: list[dict], t0: float, width_mm=174, height_mm=70) -> bytes:
    s = [x for x in samples if x["soc_avg"] is not None]
    hours = [(x["t"] - t0) / 3600 for x in s]
    soc = [x["soc_avg"] for x in s]
    power = [-(x["v"] * x["i"]) / 1000 if x["v"] and x["i"] is not None else 0 for x in s]
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax.plot(hours, soc, color=ACCENT, linewidth=1.6, label="Varaustila (%)", zorder=3)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Varaustila (%)")
    ax.set_xlabel("Aika mittauksen alusta (h)")
    ax.xaxis.set_major_formatter(_fi(1))
    ax2 = ax.twinx()
    ax2.fill_between(hours, 0, power, color=ACCENT_2, alpha=0.18, linewidth=0, zorder=2)
    ax2.plot(hours, power, color=ACCENT_2, linewidth=0.9, label="Latausteho akkuun (kW)", zorder=2)
    ax2.set_ylabel("Teho (kW)")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    pmax = max(power) if power else 1
    ax2.set_ylim(0, max(1.0, pmax * 1.6))
    ax2.yaxis.set_major_formatter(_fi(1))
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left")
    ax.set_title("Varaustila ja latausteho")
    return _png(fig)


def voltage_spread_chart(samples: list[dict], t0: float, width_mm=174, height_mm=52) -> bytes:
    s = [x for x in samples if x["c_min"] and x["c_max"]]
    hours = [(x["t"] - t0) / 3600 for x in s]
    spread = [(x["c_max"] - x["c_min"]) * 1000 for x in s]
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax.plot(hours, spread, color=ACCENT, linewidth=1.2)
    ax.set_ylabel("Ero (mV)")
    ax.set_xlabel("Aika mittauksen alusta (h)")
    ax.set_ylim(0, max(10, max(spread) * 1.2) if spread else 10)
    ax.xaxis.set_major_formatter(_fi(1))
    ax.set_title("Kennoryhmien suurimman ja pienimmän jännitteen ero")
    return _png(fig)


def trend_chart(points: list[tuple], width_mm=174, height_mm=55) -> bytes:
    """points: (kilometrit, kunto %)"""
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ax.plot(xs, ys, color=ACCENT, marker="o", markersize=4, linewidth=1.4)
    ax.set_ylabel("Kunto (%)")
    ax.set_xlabel("Mittarilukema (km)")
    ax.xaxis.set_major_formatter(_fi(0))
    ax.set_ylim(min(70, min(ys) - 3), 101)
    ax.set_title("Akun kunnon kehitys")
    return _png(fig)
