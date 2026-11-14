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
    from . import kielet
    return FuncFormatter(lambda x, _: kielet.desimaalit(f"{x:,.{d}f}".replace(",", " ").replace(".", ",")))


def _png(fig) -> bytes:
    from . import kielet
    if kielet.nykyinen() != "fi":
        from matplotlib.text import Text
        for teksti in fig.findobj(Text):
            s = teksti.get_text()
            if s:
                teksti.set_text(kielet.t(s))
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


def module_layout(model_name: str | None, n: int) -> list[int] | None:
    """Kennoryhmien jako moduuleihin, kun se on varmistettu lähteistä.
    Model 3: neljä moduulia, 23 + 25 + 25 + 23 ryhmää (Electrek 2017) tai LFP-akussa 25 + 28 + 28 + 25 kennoa
    (Battery Design). Model S ja X: 16 moduulia, kussakin 6 ryhmää. Muille malleille jakoa ei käytetä."""
    name = (model_name or "").lower()
    if "model 3" in name:
        return {96: [23, 25, 25, 23], 106: [25, 28, 28, 25]}.get(n)
    if ("model s" in name or "model x" in name) and n == 96:
        return [6] * 16
    return None


def module_chart(volts: list, layout: list[int], title: str, poikkeavat=(), width_mm=174) -> bytes:
    """Kennoryhmät moduuleittain värikarttana; ruudun luku on poikkeama mediaanista (mV)."""
    from matplotlib.colors import LinearSegmentedColormap
    vals = sorted(v for v in volts if v)
    med = vals[len(vals) // 2]
    dev = [((v - med) * 1000) if v else 0.0 for v in volts]
    lim = max(30.0, max(abs(d) for d in dev))
    cm = LinearSegmentedColormap.from_list("ero", [BAD, "#F3D9C7", "#FFFFFF", "#C9D7E6", ACCENT])
    out = {p["nro"] for p in poikkeavat}
    ncols = 1 if len(layout) <= 4 else 4
    nrows = -(-len(layout) // ncols)
    height_mm = 15 * nrows + 14 if ncols == 1 else 12 * nrows + 14
    fig, axs = plt.subplots(nrows, ncols, figsize=(width_mm / 25.4, height_mm / 25.4), squeeze=False)
    start = 0
    for m, n in enumerate(layout):
        ax = axs[m // ncols][m % ncols]
        row = dev[start:start + n]
        ax.imshow([row], aspect="auto", cmap=cm, vmin=-lim, vmax=lim, extent=(start + 0.5, start + n + 0.5, 0, 1))
        for j, d in enumerate(row):
            nro = start + j + 1
            dr = round(d)
            ax.text(nro, 0.5, ("0" if dr == 0 else f"{dr:+d}").replace("-", "−"), ha="center", va="center",
                    fontsize=7.2 if n > 10 else 8, fontweight="bold" if nro in out else "normal",
                    color="white" if abs(d) > lim * 0.6 else INK)
        ax.set_yticks([0.5])
        ax.set_yticklabels([f"Moduuli {m + 1}"], fontsize=7.5)
        ax.set_xticks([start + 1, start + n])
        ax.tick_params(axis="x", labelsize=6.5, length=0, pad=1)
        ax.tick_params(axis="y", length=0)
        ax.grid(False)
        for sp in ax.spines.values():
            sp.set_visible(False)
        start += n
    for k in range(len(layout), nrows * ncols):
        axs[k // ncols][k % ncols].axis("off")
    fig.suptitle(title + f"  ·  poikkeama mediaanista {med:.3f} V (mV)".replace(".", ","),
                 fontsize=9, color=INK, x=0.01, ha="left")
    fig.tight_layout()
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


def spread_soc_chart(data: dict, width_mm=174, height_mm=64) -> bytes:
    """Kennoryhmien jännite-ero varaustilan mukaan latauksessa ja purussa; jyrkät alueet varjostettuina."""
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4))
    for lo, hi in data.get("jyrkat", []):
        ax.axvspan(lo, hi, color=WARN, alpha=0.09, linewidth=0, zorder=0)
    style = {"lataus": (ACCENT, "Latauksessa"), "purku": (ACCENT_2, "Ajossa")}
    ymax = 10.0
    for suunta, pts in data["sarjat"].items():
        col, lab = style[suunta]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        ax.plot(xs, ys, color=col, linewidth=1.3, label=lab, zorder=3)
        ymax = max(ymax, max(ys))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, ymax * 1.25)
    ax.set_xlabel("Varaustila (%)")
    ax.set_ylabel("Ero (mV)")
    ax.yaxis.set_major_formatter(_fi(0))
    if data.get("jyrkat"):
        ax.plot([], [], color=WARN, alpha=0.3, linewidth=6, label="Jännitekäyrän jyrkkä alue")
    ax.legend(loc="upper center", ncol=3)
    ax.set_title("Kennoryhmien jännite-ero varaustilan mukaan")
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


def group_bar_chart(values: list, title: str, ylabel: str, highlight=(), ref=None, center=False,
                    width_mm=174, height_mm=58, decimals=1, min_lim=1.0) -> bytes:
    """Kennoryhmäkohtainen pylväskaavio (resistanssi, itsepurkautuminen)."""
    vals = [v if v is not None else 0 for v in values]
    hl = set(highlight)
    colors = [BAD if (k + 1) in hl else ACCENT for k in range(len(vals))]
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax.bar(range(1, len(vals) + 1), vals, color=colors, width=0.72, zorder=3)
    if ref is not None:
        ax.axhline(ref, color=INK, linewidth=0.7, zorder=4, linestyle="--")
    if center:
        lim = max(min_lim, max(abs(x) for x in vals) * 1.25)
        ax.set_ylim(-lim, lim)
        ax.axhline(0, color=INK, linewidth=0.7, zorder=4)
    else:
        nz = [v for v in vals if v]
        if nz:
            lo, hi = min(nz), max(nz)
            pad = max((hi - lo) * 0.3, hi * 0.05)
            ax.set_ylim(max(0, lo - pad), hi + pad)
    ax.set_xlim(0.3, len(vals) + 0.7)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Kennoryhmä")
    step = 8 if len(vals) > 60 else 4
    ax.set_xticks([1] + list(range(step, len(vals) + 1, step)))
    ax.yaxis.set_major_formatter(_fi(decimals))
    ax.grid(axis="x", visible=False)
    ax.set_title(title)
    return _png(fig)


def dc_chart(curve: list, width_mm=174, height_mm=64) -> bytes:
    """Pikalatauksen teho varaustilan funktiona."""
    xs = [c[0] for c in curve]
    ys = [c[1] for c in curve]
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax.plot(xs, ys, color=ACCENT, linewidth=1.6, zorder=3)
    ax.fill_between(xs, ys, color=ACCENT, alpha=0.08, zorder=2)
    ax.set_xlabel("Varaustila (%)")
    ax.set_ylabel("Latausteho (kW)")
    ax.set_ylim(0, max(ys) * 1.15 if ys else 1)
    ax.xaxis.set_major_formatter(_fi(0))
    ax.yaxis.set_major_formatter(_fi(0))
    ax.set_title("Latausteho pikalatauksessa")
    return _png(fig)


def drive_chart(samples: list[dict], width_mm=174, height_mm=66) -> bytes:
    """Ajotestin varaustila ja akusta otettu teho. Teho on keskiarvo kahden minuutin jaksoilta."""
    s = [x for x in samples if x["soc_avg"] is not None and x["v"] and x["i"] is not None]
    t0 = s[0]["t"] if s else 0
    bins: dict = {}
    for x in s:
        b = int((x["t"] - t0) // 120)
        acc = bins.setdefault(b, [0.0, 0, x["soc_avg"]])
        acc[0] += x["v"] * x["i"] / 1000
        acc[1] += 1
        acc[2] = x["soc_avg"]
    keys = sorted(bins)
    hours = [(k * 120 + 60) / 3600 for k in keys]
    power = [bins[k][0] / bins[k][1] for k in keys]
    soc = [bins[k][2] for k in keys]
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax.plot(hours, soc, color=ACCENT, linewidth=1.6, label="Varaustila (%)", zorder=3)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Varaustila (%)")
    ax.set_xlabel("Aika mittauksen alusta (h)")
    ax.xaxis.set_major_formatter(_fi(1))
    ax2 = ax.twinx()
    ax2.fill_between(hours, 0, power, color=ACCENT_2, alpha=0.18, linewidth=0, zorder=2, step="mid")
    ax2.step(hours, power, where="mid", color=ACCENT_2, linewidth=0.9, label="Teho akusta (kW, 2 min keskiarvo)",
             zorder=2)
    ax2.set_ylabel("Teho (kW)")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    pmax = max(power) if power else 1
    ax2.set_ylim(min(0.0, min(power, default=0)) * 1.2, max(1.0, pmax * 1.6))
    ax2.yaxis.set_major_formatter(_fi(0))
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right")
    ax.set_title("Varaustila ja teho ajon aikana")
    return _png(fig)
