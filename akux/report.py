"""PDF-raportin muodostus."""
from __future__ import annotations

import io
import time
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, Image, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from . import NIMI, VERSIO, charts, profiles
from .analysis import fmt

FONT_DIR = Path(__file__).parent / "data" / "fonts"
for name, file in (("Inter", "Inter-Regular.ttf"), ("Inter-Medium", "Inter-Medium.ttf"),
                   ("Inter-SemiBold", "Inter-SemiBold.ttf"), ("Inter-Bold", "Inter-Bold.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
pdfmetrics.registerFontFamily("Inter", normal="Inter", bold="Inter-SemiBold", italic="Inter", boldItalic="Inter-Bold")

INK = colors.HexColor("#1B2430")
MUTED = colors.HexColor("#6B7480")
LINE = colors.HexColor("#E3E6EA")
PANEL = colors.HexColor("#F5F6F8")
ACCENT = colors.HexColor("#1F4E79")
CLASS_COLORS = {
    "Erinomainen": ("#E6F2EA", "#2F7D4F"),
    "Hyvä": ("#E8F0F8", "#1F4E79"),
    "Tyydyttävä": ("#FBF1DE", "#8A5A12"),
    "Heikentynyt": ("#FBE7E5", "#B42318"),
    "Poikkeava": ("#FBE7E5", "#B42318"),
    "Takuurajan alittava": ("#FBE7E5", "#B42318"),
    "Kunnossa": ("#E6F2EA", "#2F7D4F"),
    "Huomioitava": ("#FBF1DE", "#8A5A12"),
}

W, H = A4
M = 18 * mm
CW = W - 2 * M

ST = {
    "body": ParagraphStyle("body", fontName="Inter", fontSize=9, leading=13.2, textColor=INK),
    "small": ParagraphStyle("small", fontName="Inter", fontSize=7.6, leading=10.4, textColor=MUTED),
    "smallink": ParagraphStyle("smallink", fontName="Inter", fontSize=7.8, leading=10.6, textColor=INK),
    "h1": ParagraphStyle("h1", fontName="Inter-SemiBold", fontSize=19, leading=23, textColor=INK, spaceAfter=2),
    "h2": ParagraphStyle("h2", fontName="Inter-SemiBold", fontSize=12.5, leading=16, textColor=INK,
                         spaceBefore=4, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName="Inter-SemiBold", fontSize=9.5, leading=13, textColor=INK,
                         spaceBefore=8, spaceAfter=3),
    "sub": ParagraphStyle("sub", fontName="Inter", fontSize=10.5, leading=14, textColor=MUTED),
    "label": ParagraphStyle("label", fontName="Inter-Medium", fontSize=7.2, leading=9, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName="Inter", fontSize=8.4, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Inter-Medium", fontSize=8.4, leading=11, textColor=INK),
    "cellr": ParagraphStyle("cellr", fontName="Inter", fontSize=8.4, leading=11, textColor=INK, alignment=TA_RIGHT),
    "kpi_val": ParagraphStyle("kpi_val", fontName="Inter-SemiBold", fontSize=17, leading=21, textColor=INK),
    "kpi_unit": ParagraphStyle("kpi_unit", fontName="Inter", fontSize=8, leading=11, textColor=MUTED),
    "mono": ParagraphStyle("mono", fontName="Inter", fontSize=7, leading=9.5, textColor=MUTED),
}


def P(text, style="body"):
    return Paragraph(text, ST[style] if isinstance(style, str) else style)


GRADE_LEVEL = {"Erinomainen": 4, "Kunnossa": 4, "Hyvä": 3, "Tyydyttävä": 2, "Huomioitava": 2,
               "Heikentynyt": 1, "Poikkeava": 1, "Takuurajan alittava": 1}
GRADE_TONE = {4: "#1F4E79", 3: "#1F4E79", 2: "#B7791F", 1: "#B42318"}


class Pill(Flowable):
    """Luokan merkintä: neliportainen tasomittari ja luokan nimi."""

    def __init__(self, text):
        super().__init__()
        self.text = text or ""
        self.level = GRADE_LEVEL.get(self.text, 0)
        self.w = 13 + pdfmetrics.stringWidth(self.text, "Inter-Medium", 7.6)
        self.h = 10

    def wrap(self, aw, ah):
        return (self.w, self.h) if self.text else (0, 0)

    def draw(self):
        if not self.text:
            return
        c = self.canv
        tone = colors.HexColor(GRADE_TONE.get(self.level, "#6B7480"))
        for k in range(4):
            hh = 3 + k * 1.7
            c.setFillColor(tone if k < self.level else LINE)
            c.rect(k * 2.4, 1.2, 1.6, hh, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Inter-Medium", 7.6)
        c.drawString(13, 2, self.text)


class SohHero(Flowable):
    """Etusivun kuntonäyttö: suuri prosenttiluku ja viisiportainen luokka-asteikko."""
    SEGMENTS = [(0, 70, "Alle 70 %", "Takuurajan alittava"), (70, 80, "70–80 %", "Heikentynyt"),
                (80, 85, "80–85 %", "Tyydyttävä"), (85, 90, "85–90 %", "Hyvä"), (90, 101, "90–100 %", "Erinomainen")]

    def __init__(self, pct, width, caption, note=""):
        super().__init__()
        self.pct, self.width, self.caption, self.note = pct, width, caption, note
        self.height = 43 * mm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        c.setFillColor(PANEL)
        c.roundRect(0, 0, w, h, 2.5 * mm, stroke=0, fill=1)
        cx = w / 2
        c.setFillColor(MUTED)
        c.setFont("Inter-Medium", 7.4)
        c.drawCentredString(cx, h - 6.5 * mm, "AKUN KUNTO (SOH)")
        if self.pct is None:
            c.setFont("Inter-SemiBold", 30)
            c.setFillColor(INK)
            c.drawCentredString(cx, h - 21 * mm, "–")
            return
        val = fmt(self.pct)
        c.setFillColor(INK)
        c.setFont("Inter-SemiBold", 40)
        vw = pdfmetrics.stringWidth(val, "Inter-SemiBold", 40)
        uw = pdfmetrics.stringWidth(" %", "Inter-SemiBold", 22)
        x0 = cx - (vw + uw) / 2
        c.drawString(x0, h - 20.5 * mm, val)
        c.setFont("Inter-SemiBold", 22)
        c.setFillColor(MUTED)
        c.drawString(x0 + vw, h - 20.5 * mm, " %")
        # asteikko
        sw = min(w - 24 * mm, 150 * mm)
        sx = cx - sw / 2
        sy = 11 * mm
        seg_w = sw / len(self.SEGMENTS)
        gap = 1.2
        active = next(k for k, (lo, hi, _, _) in enumerate(self.SEGMENTS) if lo <= self.pct < hi or
                      (k == len(self.SEGMENTS) - 1 and self.pct >= lo))
        for k, (lo, hi, rng, name) in enumerate(self.SEGMENTS):
            x = sx + k * seg_w
            on = k == active
            c.setFillColor(ACCENT if on else colors.HexColor("#DDE2E8"))
            c.rect(x + gap / 2, sy, seg_w - gap, 2.4 * mm, stroke=0, fill=1)
            c.setFont("Inter-SemiBold" if on else "Inter", 7.0)
            c.setFillColor(INK if on else MUTED)
            c.drawCentredString(x + seg_w / 2, sy - 4.2 * mm, name)
            c.setFont("Inter", 6.4)
            c.setFillColor(MUTED)
            c.drawCentredString(x + seg_w / 2, sy - 7.4 * mm, rng)
        # merkki aktiivisen lohkon kohdalle
        lo, hi = self.SEGMENTS[active][0], min(self.SEGMENTS[active][1], 100)
        frac = 0.5 if hi <= lo else (min(max(self.pct, lo), hi) - lo) / (hi - lo)
        mx = sx + active * seg_w + gap / 2 + frac * (seg_w - gap)
        c.setFillColor(INK)
        pth = c.beginPath()
        pth.moveTo(mx - 1.6 * mm, sy + 4.4 * mm)
        pth.lineTo(mx + 1.6 * mm, sy + 4.4 * mm)
        pth.lineTo(mx, sy + 2.7 * mm)
        pth.close()
        c.drawPath(pth, stroke=0, fill=1)
        c.setFont("Inter", 7.2)
        c.setFillColor(MUTED)
        c.drawCentredString(cx, 18 * mm, self.caption)


def _table(rows, widths, header=True, zebra=False, valign="MIDDLE", pad=4):
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), valign),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
    ]
    if header:
        style += [("LINEBELOW", (0, 0), (-1, 0), 0.8, INK)]
    if zebra:
        for r in range(1 if header else 0, len(rows)):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), PANEL))
    t.setStyle(TableStyle(style))
    return t


def _kv(rows, widths=(48 * mm, None)):
    data = [[P(k, "label"), P(v if v not in (None, "") else "–", "cell")] for k, v in rows]
    w2 = widths[1] or (CW / 2 - widths[0] - 4 * mm)
    t = Table(data, colWidths=[widths[0], w2], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
    ]))
    return t


def _img(png: bytes, width):
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(io.BytesIO(png))
    iw, ih = ir.getSize()
    return Image(io.BytesIO(png), width=width, height=width * ih / iw)


def _photo(path, width, height):
    """Auton kuva rajattuna annettuun kokoon, pyöristetyin kulmin."""
    from PIL import Image as PILImage, ImageDraw
    im = PILImage.open(path).convert("RGB")
    target = width / height
    w, h = im.size
    if w / h > target:
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / target)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize((int(width / mm * 12), int(height / mm * 12)), PILImage.LANCZOS)   # noin 300 dpi
    mask = PILImage.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.size[0] - 1, im.size[1] - 1), radius=int(im.size[0] * 0.03), fill=255)
    bg = PILImage.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, (0, 0), mask)
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=88)
    buf.seek(0)
    return Image(buf, width=width, height=height)


def _bn(brutto, netto):
    if not brutto:
        return None
    return f"{fmt(brutto)} kWh / {fmt(netto)} kWh" if netto else f"{fmt(brutto)} kWh / –"


def _date(ts, with_time=True):
    if not ts:
        return "–"
    lt = time.localtime(ts)
    return time.strftime("%d.%m.%Y klo %H.%M" if with_time else "%d.%m.%Y", lt)


def _signed(x):
    if abs(x) < 0.05:
        return "0,0"
    return f"{x:+.1f}".replace(".", ",").replace("-", "−")


def _dur(s):
    if s is None:
        return "–"
    h, m = int(s // 3600), int((s % 3600) // 60)
    return f"{h} h {m} min" if h else f"{m} min"


BRAND_GREEN = colors.HexColor("#6CC193")


def draw_logo(c, x, y, h, wordmark=True, ink=None):
    """Akux-merkki (sama kuin ohjelman kuvake) ja nimi. (x, y) = vasen alakulma, h = merkin korkeus."""
    c.saveState()
    c.setFillColor(ACCENT)
    c.roundRect(x, y, h, h, h * 0.22, stroke=0, fill=1)
    bw, bh = h * 0.62, h * 0.36
    bx, by = x + h * 0.15, y + (h - bh) / 2
    c.setStrokeColor(colors.white)
    c.setLineWidth(max(0.6, h * 0.065))
    c.roundRect(bx, by, bw, bh, h * 0.06, stroke=1, fill=0)
    c.setFillColor(colors.white)
    c.roundRect(bx + bw + h * 0.035, y + h * 0.43, h * 0.07, h * 0.14, h * 0.02, stroke=0, fill=1)
    c.setFillColor(BRAND_GREEN)
    pad = h * 0.07
    c.roundRect(bx + pad, by + pad, bw * 0.5, bh - 2 * pad, h * 0.03, stroke=0, fill=1)
    w = h
    if wordmark:
        c.setFillColor(ink or INK)
        c.setFont("Inter-SemiBold", h * 0.78)
        c.drawString(x + h * 1.28, y + h * 0.2, NIMI)
        w = h * 1.28 + pdfmetrics.stringWidth(NIMI, "Inter-SemiBold", h * 0.78)
    c.restoreState()
    return w


# ----------------------------------------------------------------------
class ReportDoc(BaseDocTemplate):
    def __init__(self, path, ctx):
        super().__init__(str(path), pagesize=A4, leftMargin=M, rightMargin=M, topMargin=26 * mm,
                         bottomMargin=20 * mm, title=ctx["title"], author=ctx["company"] or NIMI,
                         subject="Ajoakun kuntoraportti", creator=f"{NIMI} {VERSIO}")
        self.ctx = ctx
        frame = Frame(M, 20 * mm, CW, H - 46 * mm, id="f", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        first = Frame(M, 44 * mm, CW, H - 70 * mm, id="f1", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="first", frames=[first], onPage=self._first),
                               PageTemplate(id="page", frames=[frame], onPage=self._decorate)])

    def _first(self, c, doc):
        self._decorate(c, doc)
        qr = self.ctx.get("qr")
        if qr:
            from reportlab.graphics import renderPDF
            from reportlab.graphics.barcode.qr import QrCodeWidget
            from reportlab.graphics.shapes import Drawing
            size = 19 * mm
            w = QrCodeWidget(qr, barLevel="M")
            x1, y1, x2, y2 = w.getBounds()
            d = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
            d.add(w)
            renderPDF.draw(d, c, W - M - size + 1.5 * mm, H - 23 * mm - size)
            c.saveState()
            c.setFont("Inter", 5.6)
            c.setFillColor(MUTED)
            c.drawRightString(W - M, H - 23 * mm - size - 2.6 * mm, "Raportin tunnistetiedot")
            c.restoreState()
        c.saveState()
        y = 22 * mm
        half = CW / 2 - 5 * mm
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.6)
        c.line(M, y, M + half, y)
        c.line(W - M - half, y, W - M, y)
        c.setFont("Inter-Medium", 7.2)
        c.setFillColor(MUTED)
        c.drawString(M, y + 13 * mm, "Paikka ja päiväys")
        c.drawString(W - M - half, y + 13 * mm, "Mittaajan allekirjoitus ja nimenselvennys")
        c.restoreState()

    def _decorate(self, c, doc):
        ctx = self.ctx
        c.saveState()
        y = H - 14 * mm
        logo = ctx.get("logo")
        x0 = M
        if not ctx["company"] and not (logo and Path(logo).exists()):
            # Ilman yrityksen tietoja otsikkona on Akux-logo
            draw_logo(c, M, y - 7.2 * mm, 8.5 * mm)
            x0 = None
        elif logo and Path(logo).exists():
            try:
                from reportlab.lib.utils import ImageReader
                ir = ImageReader(logo)
                iw, ih = ir.getSize()
                hgt = 9 * mm
                wid = min(40 * mm, hgt * iw / ih)
                c.drawImage(ir, M, y - 6.5 * mm, width=wid, height=wid * ih / iw, mask="auto")
                x0 = M + wid + 4 * mm
            except Exception:  # noqa: BLE001
                pass
        if x0 is not None:
            c.setFont("Inter-SemiBold", 10)
            c.setFillColor(INK)
            c.drawString(x0, y - 1, ctx["company"] or NIMI)
            c.setFont("Inter", 7.4)
            c.setFillColor(MUTED)
            if ctx.get("company_line"):
                c.drawString(x0, y - 11, ctx["company_line"])
        c.setFont("Inter-Medium", 8)
        c.setFillColor(INK)
        c.drawRightString(W - M, y - 1, ctx["title"])
        c.setFont("Inter", 7.4)
        c.setFillColor(MUTED)
        c.drawRightString(W - M, y - 11, f"Raportti {ctx['report_no']}  ·  {ctx['date']}")
        c.setStrokeColor(LINE)
        c.setLineWidth(0.8)
        c.line(M, H - 21 * mm, W - M, H - 21 * mm)
        # alatunniste
        c.line(M, 14 * mm, W - M, 14 * mm)
        lw = draw_logo(c, M, 8.9 * mm, 3.6 * mm, ink=MUTED)
        c.setFont("Inter", 6.8)
        c.setFillColor(MUTED)
        c.drawString(M + lw + 3 * mm, 10 * mm, ctx["footer"])
        c.drawRightString(W - M, 10 * mm, f"Sivu {doc.page}")
        c.restoreState()


# ----------------------------------------------------------------------
def build(storage, tid: int, out_path: Path | None = None) -> Path:
    test = storage.test(tid)
    r = test["tulos"] or {}
    if "virhe" in r or "keskeneräinen" in r or not r.get("yhteenveto"):
        raise ValueError("Mittauksesta ei ole valmista tulosta.")
    vehicle = storage.vehicle(test["vehicle_id"]) or {}
    s = storage.settings()
    samples = storage.samples(tid)
    events = storage.events(tid)
    veh = r["ajoneuvo"]
    vi = veh.get("vin_tiedot") or {}
    cap = r.get("kapasiteetti") or {}
    bms = r.get("bms") or {}
    summ = r["yhteenveto"]
    is_cap = r["tyyppi"] == "kapasiteetti"

    company_line = "  ·  ".join(x for x in (s.get("yritys_osoite"), s.get("yritys_puhelin"),
                                            s.get("yritys_sahkoposti"), s.get("yritys_www")) if x)
    report_no = f"{time.strftime('%Y', time.localtime(test['aloitettu']))}-{tid:05d}"
    title = "Akun kapasiteettimittaus" if is_cap else "Akun kuntotarkastus"
    ctx = {
        "company": s.get("yritys_nimi"), "company_line": company_line, "logo": s.get("logo"),
        "title": title, "report_no": report_no, "date": _date(test.get("paattynyt") or test["aloitettu"], False),
        "footer": s.get("raportin_alatunniste") or (
            f"{VERSIO}  ·  Tiedot: auton akunhallinta  ·  Raakadatan tarkiste {(test.get('tarkiste') or '')[:16]}…"),
    }
    _y = r.get("yhteenveto") or {}
    ctx["qr"] = "\n".join(x for x in (
        f"AKUX-RAPORTTI {report_no}",
        f"VIN {(r.get('ajoneuvo') or {}).get('vin') or '-'}",
        f"Rekisteri {vehicle.get('rekisteri')}" if vehicle.get("rekisteri") else None,
        f"Päiväys {ctx['date']}",
        f"Kunto {fmt(_y.get('kunto_pct'))} %" if _y.get("kunto_pct") is not None else None,
        f"Kapasiteetti {fmt(_y.get('kapasiteetti_kwh'))} kWh" if _y.get("kapasiteetti_kwh") else None,
        f"Tarkiste {(test.get('tarkiste') or '')[:16]}",
    ) if x)
    out_path = out_path or (storage.dir / "raportit" / f"Akkuraportti_{report_no}.pdf")
    doc = ReportDoc(out_path, ctx)
    E = [NextPageTemplate("page")]

    # ---------------- Sivu 1: yhteenveto -------------------------------
    model_name = veh.get("malli") or (vi.get("malli") and f"Tesla {vi['malli']}") or "Tesla"
    import re as _re
    base_name = _re.sub(r"\s*\([^)]*\d{4}[^)]*\)\s*$", "", model_name)     # mallipohjan vuosiväli pois
    sub = f"Tesla {base_name}" if not base_name.startswith("Tesla") else base_name
    _prof = profiles.get(veh.get("malli_id")) or {}
    if _prof.get("akku_lyhyt") and vi.get("malli"):
        sub = f"Tesla {vi['malli']}  ·  {_prof['akku_lyhyt']}"
    year = vehicle.get("vuosimalli") or vi.get("vuosimalli")
    if year:
        sub += f"  ·  vuosimalli {year}"
    reg = (vehicle.get("rekisteri") or "").strip()
    head = [P(title, "h1"), P(sub, "sub")]
    if reg:
        head += [Spacer(1, 2), P(f"Rekisterinumero <b>{reg}</b>", "sub")]
    photo = storage.vehicle_photo(test["vehicle_id"])
    if photo.exists():
        pw, ph = 56 * mm, 32 * mm
        try:
            img = _photo(photo, pw, ph)
        except Exception:  # noqa: BLE001
            img = None
    else:
        img = None
    if img is not None:
        ht = Table([[head, img, ""]], colWidths=[CW - pw - 24 * mm, pw, 24 * mm], hAlign="LEFT")
        ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        E.append(ht)
        E.append(Spacer(1, 5 * mm))
    else:
        E.extend(head)
        E.append(Spacer(1, 7 * mm))

    soh = summ.get("kunto_pct")
    kwh = summ.get("kapasiteetti_kwh")
    unc = summ.get("epavarmuus_kwh")
    cs = r.get("kennot")
    kpis = []

    def kpi(label, value, unit, extra=None):
        cell = [P(label, "label"), Spacer(1, 3), P(value, "kpi_val"), P(unit, "kpi_unit")]
        if extra is not None:
            cell += [Spacer(1, 4), extra]
        return cell

    if soh is not None:
        lahde_txt = {"Kapasiteettimittaus": "Kapasiteettimittaus",
                     "Akunhallinnan arvio": "Teslan akunhallinta"}.get(summ.get("kunto_lahde"),
                                                                       summ.get("kunto_lahde") or "")
        cap_pct = cap.get("soh_epavarmuus_pct") if summ.get("kunto_lahde") == "Kapasiteettimittaus" else None
        caption = lahde_txt + (f"  ·  ±{fmt(cap_pct)} %-yks." if cap_pct else "")
    else:
        caption = "Ei laskettavissa"
    E.append(SohHero(soh, CW, caption))
    E.append(Spacer(1, 3 * mm))
    _kk = r.get("kapasiteetit") or {}
    kw = CW / 3
    kpis.append(kpi("KAPASITEETTI NYT (BRUTTO)", f"{fmt(kwh)} kWh" if kwh else "–",
                    (f"±{fmt(unc)} kWh  ·  " if unc else "") + f"uutena {fmt(r['viite']['kwh'])} kWh"))
    kpis.append(kpi("KÄYTETTÄVÄ ENERGIA (NETTO)", f"{fmt(_kk['netto_nyt'])} kWh" if _kk.get("netto_nyt") else "–",
                    f"Puskuri {fmt(_kk['puskuri_kwh'], 1)} kWh" if _kk.get("puskuri_kwh") is not None else ""))
    kpis.append(kpi("KENNORYHMIEN JÄNNITE-ERO", f"{fmt(cs['ero_mv'], 0)} mV" if cs else "–",
                    f"{cs['luokka']}  ·  {cs['lkm']} kennoryhmää" if cs else "Ei mitattu"))
    kt = Table([kpis], colWidths=[kw, kw, kw], hAlign="LEFT")
    kt.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("LINEAFTER", (0, 0), (1, 0), 0.6, LINE),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, LINE),
    ]))
    E.append(kt)
    E.append(Spacer(1, 2.2 * mm))
    tesla = []
    if bms.get("nfp_kwh"):
        tesla.append(f"täyden akun energia <b>{fmt(bms['nfp_kwh'])} kWh</b>")
    if r["viite"]["lahde"].startswith("Auton akunhallinta") and r["viite"]["kwh"]:
        tesla.append(f"alkuperäinen energia <b>{fmt(r['viite']['kwh'])} kWh</b>")
    if bms.get("soh_pct") and r["viite"]["lahde"].startswith("Auton akunhallinta"):
        tesla.append(f"kunto <b>{fmt(bms['soh_pct'])} %</b>")
    src_line = "Kaikki mittausarvot ovat auton oman akunhallinnan luovuttamia."
    if tesla:
        src_line = "Teslan akunhallinta: " + ", ".join(tesla) + ". " + src_line
    E.append(P(src_line, "small"))
    E.append(Spacer(1, 4 * mm))
    if summ.get("tulkinta"):
        box = Table([[P("MITÄ TULOS TARKOITTAA", "label")], [P(summ["tulkinta"], "smallink")]], colWidths=[CW])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LINEBEFORE", (0, 0), (0, -1), 2.2, ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
            ("TOPPADDING", (0, 0), (-1, 0), 3 * mm), ("BOTTOMPADDING", (0, -1), (-1, -1), 3 * mm),
            ("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ]))
        E.append(box)
    E.append(Spacer(1, 5 * mm))

    # Ajoneuvo ja mittaus
    odo = veh.get("mittarilukema_km")
    left = [
        ("Valmistenumero (VIN)", veh.get("vin")),
        ("Rekisterinumero", vehicle.get("rekisteri")),
        ("Vuosimalli", str(vehicle.get("vuosimalli") or vi.get("vuosimalli") or "–")),
        ("Valmistustehdas", vi.get("tehdas")),
        ("Voimalinja", vi.get("voimalinja")),
        ("Mittarilukema", f"{fmt(odo, 0)} km" if odo else None),
        ("Käyttöönotto", (r.get("takuu") or {}).get("kayttoonotto")),
    ]
    kk = r.get("kapasiteetit") or {}
    right = [
        ("Akkutyyppi", veh.get("kennotyyppi") or veh.get("kemia_nimi")),
        ("Kennoryhmiä sarjassa", str(veh.get("kennoryhmat") or "–")),
        ("Uutena, brutto / netto", (_bn(kk.get("brutto_uutena"), kk.get("netto_uutena")) or "") + (
            "" if r["viite"]["lahde"].startswith("Auton akunhallinta") or not kk.get("brutto_uutena")
            else (" (ilmoitettu)" if r["viite"]["lahde"].startswith("Käyttäjän") else " (likiarvo)")) or None),
        ("Nyt, brutto / netto", _bn(kk.get("brutto_nyt"), kk.get("netto_nyt"))),
        ("Mittauspäivä", _date(test["aloitettu"])),
        ("Mittaaja", test.get("mittaaja") or s.get("mittaaja")),
    ]
    two = Table([[_kv(left, (36 * mm, CW / 2 - 40 * mm)), _kv(right, (40 * mm, CW / 2 - 40 * mm))]],
                colWidths=[CW / 2, CW / 2], hAlign="LEFT")
    two.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    E.append(P("Ajoneuvo ja mittaus", "h3"))
    E.append(two)
    E.append(Spacer(1, 5 * mm))

    # Arviot
    rows = [[P("Arvio", "label"), P("Tulos", "label"), P("Luokka", "label"), P("Selite", "label")]]
    for a in r.get("arviot", []):
        rows.append([P(a["nimi"], "cellb"), P(a["arvo"], "cell"), Pill(a.get("luokka")), P(a["kuvaus"], "small")])
    E.append(PageBreak())
    E.append(P("Yhteenveto", "h2"))
    E.append(P(summ.get("teksti", ""), "body"))
    E.append(Spacer(1, 5 * mm))
    E.append(P("Arviot", "h2"))
    E.append(P("Jokainen arvio on luokiteltu menetelmäsivulla kuvattujen rajojen mukaan. Luokat: erinomainen, "
               "hyvä, tyydyttävä, heikentynyt ja poikkeava.", "small"))
    E.append(Spacer(1, 3 * mm))
    E.append(_table(rows, [44 * mm, 28 * mm, 30 * mm, CW - 102 * mm]))

    if r.get("huomiot"):
        E.append(Spacer(1, 4 * mm))
        E.append(P("Huomiot", "h3"))
        for h in r["huomiot"]:
            E.append(P("– " + h, "smallink"))

    # Mittausolosuhteet
    E.append(Spacer(1, 6 * mm))
    E.append(P("Mittausolosuhteet", "h3"))
    tt = r.get("lampotilat") or {}
    meta = r.get("meta") or {}
    rows_c = [[P("Tieto", "label"), P("Arvo", "label"), P("Selite", "label")]]

    def cond(n_, v_, p_=""):
        rows_c.append([P(n_, "cell"), P(v_ if v_ not in (None, "") else "–", "cellb"), P(p_, "small")])
    cond("Mittaustapa", "Kapasiteettimittaus latauksen aikana" if is_cap else "Pikatarkastus levossa",
         "Akkuun mennyt energia mitattu akun omasta jännitteestä ja virrasta" if is_cap
         else "Akunhallinnan tiedot ja kennoryhmien jännitteet")
    cond("Mittauksen kesto", _dur((meta.get("t_loppu") or 0) - (meta.get("t_alku") or 0)) if meta.get("t_loppu") else None,
         f"{_date(test['aloitettu'])} alkaen")
    if tt.get("alku_min") is not None:
        cond("Akun lämpötila alussa", f"{fmt(tt['alku_min'])}–{fmt(tt['alku_max'])} °C", "Suositus 15–35 °C")
        cond("Akun lämpötila lopussa", f"{fmt(tt['loppu_min'])}–{fmt(tt['loppu_max'])} °C", "")
    if is_cap and cap.get("soc_alku") is not None:
        cond("Varaustila latauksen alussa ja lopussa", f"{fmt(cap['soc_alku'])} % → {fmt(cap['soc_loppu'])} %",
             f"Muutos {fmt(cap.get('dsoc'))} %-yksikköä")
        cond("Lepo ennen latausta ja sen jälkeen",
             f"{fmt(cap.get('lepo_alku_min'), 0)} min ja {fmt(cap.get('lepo_loppu_min'), 0)} min", "Suositus 30 min")
        cond("Latauksen keskiteho akkuun", f"{fmt(cap.get('keskiteho_kw'))} kW", "Vaihtovirtalataus")
    elif cs:
        cond("Akun virta mittaushetkellä", f"{fmt(cs.get('virta_a'))} A", "Alle 3 A tarkoittaa, että akku on levossa")
        cond("Varaustila", f"{fmt(cs.get('soc'))} %" if cs.get("soc") is not None else None, "Kennoryhmien keskiarvo")
        if cs.get("naytteita"):
            cond("Kennojännitteiden näytteitä", f"{cs['naytteita']} kpl kennoryhmää kohden", "Tulos on näytteiden keskiarvo")
    src_info = meta.get("sovitin") or {}
    cond("Tietolähde", src_info.get("sovitin") or meta.get("lahde"), "Auton akunhallinta diagnostiikkaliitännän kautta")
    E.append(_table(rows_c, [62 * mm, 50 * mm, CW - 112 * mm]))

    # Tietojen alkuperä ja vastuu
    E.append(Spacer(1, 6 * mm))
    origin = ("Kaikki raportin mittausarvot on luettu auton omasta akunhallintajärjestelmästä (BMS) "
              "diagnostiikkaliitännän kautta. Akux ei käytä omia antureitaan eikä muuta luettuja arvoja, vaan "
              "tallentaa ne muuttamattomina. ")
    if is_cap:
        origin += ("Kapasiteettimittauksen tulos perustuu akunhallinnan jännite- ja virtamittauksiin, ja se on "
                   "tarkistettu akunhallinnan omasta latauslaskurista. Menetelmä on kuvattu menetelmäsivulla. ")
    if not r["viite"]["lahde"].startswith("Auton akunhallinta"):
        origin += f"Alkuperäisen kapasiteetin lähde: {r['viite']['lahde'].lower()}. "
    origin += ("Tulosten tarkkuus riippuu auton antureiden tarkkuudesta. Raportti kuvaa akun tilaa mittaushetkellä, "
               "eikä se ole valmistajan lausunto eikä takuu akun tulevasta kunnosta.")
    ob = Table([[P("TIETOJEN ALKUPERÄ JA VASTUU", "label")], [P(origin, "smallink")]], colWidths=[CW])
    ob.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LINEBEFORE", (0, 0), (0, -1), 2.2, MUTED),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, 0), 3 * mm), ("BOTTOMPADDING", (0, -1), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
    ]))
    E.append(KeepTogether(ob))

    # ---------------- Sivu 3: kapasiteettimittaus ----------------------
    if is_cap and cap:
        E.append(PageBreak())
        E.append(P("Kapasiteettimittaus", "h2"))
        E.append(P("Akku ladattiin matalasta varaustilasta täyteen, ja akkuun mennyt energia laskettiin "
                   "auton akunhallinnan jännite- ja virtamittauksista koko latauksen ajalta. Laturin häviöt eivät "
                   "siksi vaikuta tulokseen.", "body"))
        E.append(Spacer(1, 4 * mm))
        t0 = samples[0]["t"] if samples else test["aloitettu"]
        if samples:
            E.append(_img(charts.capacity_chart(samples, t0), CW))
            E.append(Spacer(1, 3 * mm))
        if cap.get("valmis"):
            rows = [[P("Suure", "label"), P("Arvo", "label"), P("Peruste", "label")]]
            highlight = []

            def add(n, v, p="", strong=False):
                if strong:
                    highlight.append(len(rows))
                rows.append([P(n, "cellb" if strong else "cell"), P(v, "cellb"), P(p, "small")])
            add("Varaustila latauksen alussa", f"{fmt(cap['soc_alku'])} %", "Teslan akunhallinta")
            add("Varaustila latauksen lopussa", f"{fmt(cap['soc_loppu'])} %",
                "Akunhallinta ilmoitti latauksen valmiiksi" if cap.get("taysi") else "Lataus päättyi")
            add("Latauksen kesto", _dur(cap.get("lataus_kesto_s")),
                f"Keskiteho akkuun {fmt(cap.get('keskiteho_kw'))} kW")
            add("Akkuun mennyt energia (navoilta)", f"{fmt(cap['e_napa_kwh'], 2)} kWh",
                "Teslan latauslaskuri" if cap.get("laskuri_kaytetty") else "Akunhallinnan jännite ja virta, ∫ U · I dt")
            if cap.get("laskuri_kwh") and not cap.get("laskuri_kaytetty"):
                add("Teslan latauslaskuri samalta ajalta", f"{fmt(cap['laskuri_kwh'], 2)} kWh",
                    f"Vertailu: ero {fmt(cap.get('laskuri_ero_pct'))} %")
            add("Akun sisäinen resistanssi", f"{fmt(cap['r_ohm'] * 1000, 0)} mΩ" if cap.get("r_ohm") else "–",
                "Jännitteen nousu latauksen alussa")
            add("Sisäiset häviöt latauksessa", f"{fmt(cap['e_haviot_kwh'], 2)} kWh", "R · ∫ I² dt")
            if cap.get("katkot_kwh"):
                add("Katkojen aikainen energia", f"{fmt(cap['katkot_kwh'], 2)} kWh", "Akunhallinnan energialaskenta")
            add("Varastoitunut energia mittausvälillä", f"{fmt(cap['e_kemia_kwh'], 2)} kWh", "")
            add("Energia lähtövarauksen alapuolella", f"{fmt(cap['e_alapuoli_kwh'], 2)} kWh",
                "Mitattu Ah-kapasiteetti ja akkukemian lepojännitekäyrä")
            if cap.get("e_ylapuoli_kwh", 0) > 0.05:
                add("Energia loppuvarauksen yläpuolella", f"{fmt(cap['e_ylapuoli_kwh'], 2)} kWh", "Sama menetelmä")
            add("Akun kokonaiskapasiteetti", f"{fmt(cap['taysi_kwh'], 1)} kWh",
                f"Epävarmuus noin ±{fmt(cap['epavarmuus_kwh'])} kWh", strong=True)
            if cap.get("kaytettava_kwh") is not None:
                add("Käytettävissä oleva energia", f"{fmt(cap['kaytettava_kwh'], 1)} kWh",
                    f"Kokonaiskapasiteetti vähennettynä akunhallinnan puskurilla ({fmt(bms.get('puskuri_kwh'))} kWh)")
            if bms.get("nfp_kwh"):
                add("Teslan akunhallinnan oma arvio", f"{fmt(bms['nfp_kwh'], 1)} kWh",
                    f"Ero mitattuun {fmt(cap.get('ero_bms_pct'))} %")
            if cap.get("ocv_kwh"):
                add("Rinnakkaisarvio lepojännitteistä", f"{fmt(cap['ocv_kwh'], 1)} kWh",
                    "Varaustila arvioitu lepojännitteestä, ei akunhallinnasta. Suuntaa antava.")
            ct = _table(rows, [66 * mm, 30 * mm, CW - 96 * mm])
            for hr in highlight:
                ct.setStyle(TableStyle([("BACKGROUND", (0, hr), (-1, hr), PANEL)]))
            E.append(ct)

            qrows = [[P("Tarkistus", "label"), P("Tulos", "label"), P("", "label")]]
            for q in cap.get("laatu", []):
                qrows.append([P(q["nimi"], "cell"), P(q["arvo"], "cell"),
                              Pill("Kunnossa" if q["ok"] else "Huomioitava")])
            qrows.append([P("Kokonaisarvio", "cellb"), P(cap.get("laatu_luokka"), "cellb"), ""])
            uo = cap.get("epavarmuus_osat", {})
            urows = [[P("Epävarmuuden osa", "label"), P("kWh", "label")]]
            for k, label in (("mittaus", "Jännite- ja virtamittaus (1 %)"),
                             ("varaustila", "Varaustilan lukema alussa ja lopussa"),
                             ("ekstrapolointi", "Mittausvälin ulkopuolinen osuus"),
                             ("haviot", "Sisäisten häviöiden korjaus"), ("katkot", "Mittausdatan katkot")):
                if uo.get(k) is not None and (uo[k] > 0.005 or k == "mittaus"):
                    urows.append([P(label, "cell"), P(fmt(uo[k], 2), "cellr")])
            urows.append([P("Yhdistetty epävarmuus", "cellb"), P(fmt(cap["epavarmuus_kwh"], 2), "cellr")])
            side = Table([[_table(qrows, [44 * mm, 24 * mm, 22 * mm]),
                           _table(urows, [CW - 90 * mm - 26 * mm, 18 * mm])]],
                         colWidths=[92 * mm, CW - 92 * mm], hAlign="LEFT")
            side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            E.append(KeepTogether([Spacer(1, 3 * mm), P("Mittauksen luotettavuus", "h3"), side]))
        if samples:
            E.append(CondPageBreak(55 * mm))
            E.append(Spacer(1, 4 * mm))
            E.append(_img(charts.voltage_spread_chart(samples, t0), CW))

    # ---------------- Kennoryhmät --------------------------------------
    if cs:
        E.append(PageBreak())
        E.append(P("Kennoryhmät", "h2"))
        E.append(P(f"Akussa on {cs['lkm']} sarjaan kytkettyä kennoryhmää. Kunkin ryhmän jännite on luettu "
                   "akunhallinnasta. Levossa mitattu jännite-ero kertoo, kuinka tasaisesti kennoryhmät ovat "
                   "varautuneet. Suuri yksittäinen poikkeama voi viitata heikentyneeseen ryhmään.", "body"))
        E.append(Spacer(1, 3 * mm))
        E.append(_img(charts.cell_chart(cs["jannitteet"], r.get("kennot_otsikko", "Kennoryhmät"),
                                        poikkeavat=cs["poikkeavat"]), CW))
        low = r.get("kennot_matala")
        if low:
            E.append(Spacer(1, 2 * mm))
            E.append(_img(charts.cell_chart(low["jannitteet"], "Kennoryhmät matalassa varauksessa ennen latausta",
                                            poikkeavat=low["poikkeavat"]), CW))
        E.append(Spacer(1, 3 * mm))
        rows = [[P("Tunnusluku", "label"), P(r.get("kennot_otsikko", ""), "label")]]
        hdr = [P("Tunnusluku", "label"), P("Täyden latauksen jälkeen" if low else "Mittaushetkellä", "label")]
        if low:
            hdr.append(P("Matalassa varauksessa", "label"))
        rows = [hdr]

        def line(n, f):
            row = [P(n, "cell"), P(f(cs), "cell")]
            if low:
                row.append(P(f(low), "cell"))
            rows.append(row)
        line("Varaustila", lambda c: f"{fmt(c['soc'])} %" if c.get("soc") is not None else "–")
        line("Keskiarvo", lambda c: f"{fmt(c['ka_v'], 4)} V")
        line("Suurin", lambda c: f"{fmt(c['max_v'], 4)} V (ryhmä {c['max_nro']})")
        line("Pienin", lambda c: f"{fmt(c['min_v'], 4)} V (ryhmä {c['min_nro']})")
        line("Suurin ero", lambda c: f"{fmt(c['ero_mv'], 1)} mV")
        line("Keskihajonta", lambda c: f"{fmt(c['keskihajonta_mv'], 1)} mV")
        line("Poikkeavat ryhmät", lambda c: ", ".join(str(p["nro"]) for p in c["poikkeavat"]) or "Ei havaittu")
        line("Akun virta", lambda c: f"{fmt(c['virta_a'])} A" if c.get("virta_a") is not None else "–")
        cols = [50 * mm, 60 * mm] + ([CW - 110 * mm] if low else [])
        E.append(_table(rows, cols))

        # kennotaulukot
        def cell_table(stats, title, intro):
            E.append(PageBreak())
            E.append(P(title, "h2"))
            E.append(P(intro + " Poikkeama on ilmoitettu suhteessa kaikkien ryhmien keskiarvoon.", "small"))
            E.append(Spacer(1, 3 * mm))
            vals = stats["jannitteet"]
            mean = stats["ka_v"]
            n = len(vals)
            per_col = (n + 3) // 4
            out_set = {p["nro"] for p in stats["poikkeavat"]}
            hdr = []
            for _ in range(4):
                hdr += [P("Nro", "label"), P("Jännite", "label"), P("Ero", "label"), ""]
            rows = [hdr]
            for i in range(per_col):
                row = []
                for c in range(4):
                    k = c * per_col + i
                    if k < n and vals[k]:
                        stl = "cellb" if (k + 1) in out_set else "cell"
                        row += [P(str(k + 1), "small"), P(f"{fmt(vals[k], 4)}", stl),
                                P(_signed((vals[k] - mean) * 1000), "small"), ""]
                    else:
                        row += ["", "", "", ""]
                rows.append(row)
            cw = CW / 4
            t = Table(rows, colWidths=[8 * mm, 17 * mm, 13 * mm, cw - 38 * mm] * 4, hAlign="LEFT", repeatRows=1)
            t.setStyle(TableStyle([
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
                ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]))
            E.append(t)
            E.append(Spacer(1, 4 * mm))
            summ_rows = [[P(x, "label") for x in ("Keskiarvo", "Suurin", "Pienin", "Suurin ero", "Keskihajonta",
                                                  "Poikkeavat ryhmät")],
                         [P(f"{fmt(stats['ka_v'], 4)} V", "cellb"),
                          P(f"{fmt(stats['max_v'], 4)} V (nro {stats['max_nro']})", "cell"),
                          P(f"{fmt(stats['min_v'], 4)} V (nro {stats['min_nro']})", "cell"),
                          P(f"{fmt(stats['ero_mv'], 1)} mV", "cellb"),
                          P(f"{fmt(stats.get('keskihajonta_mv'), 1)} mV", "cell"),
                          P(", ".join(str(p["nro"]) for p in stats["poikkeavat"]) or "Ei havaittu", "cell")]]
            st_ = Table(summ_rows, colWidths=[24 * mm, 36 * mm, 36 * mm, 24 * mm, 24 * mm, CW - 144 * mm], hAlign="LEFT")
            st_.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                                     ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
            E.append(KeepTogether(st_))
            E.append(Spacer(1, 3 * mm))
            E.append(P(f"{n} kennoryhmää. Jännitteet voltteina (V), ero millivoltteina (mV). Lihavoidut arvot "
                       "poikkeavat muista. Arvot on luettu auton akunhallinnasta.", "small"))

        cell_table(cs, "Kennoryhmien jännitteet", r.get("kennot_otsikko", "") + ".")
        if low and low.get("jannitteet"):
            cell_table(low, "Kennoryhmien jännitteet matalassa varauksessa",
                       f"Kennoryhmien jännitteet levossa ennen latausta, varaustila {fmt(low.get('soc'))} %. "
                       "Matalassa varauksessa heikentyneen ryhmän jännite laskee muita enemmän.")

    # ---------------- Akunhallinta ja elinkaari -----------------------
    E.append(PageBreak())
    E.append(P("Akunhallinnan tiedot", "h2"))
    lt = r.get("elinkaari") or {}
    tt = r.get("lampotilat") or {}
    rows = [[P("Tieto", "label"), P("Arvo", "label"), P("Selite", "label")]]

    def add(n, v, p=""):
        rows.append([P(n, "cell"), P(v, "cellb"), P(p, "small")])
    add("Täyden akun energia", f"{fmt(bms.get('nfp_kwh'))} kWh" if bms.get("nfp_kwh") else "–",
        "Akunhallinnan arvio akun nykyisestä kokonaisenergiasta")
    add("Alkuperäinen energia", f"{fmt(r['viite']['kwh'])} kWh" if r["viite"]["kwh"] else "–", r["viite"]["lahde"])
    if bms.get("soh_pct"):
        add("Kunto akunhallinnan mukaan", f"{fmt(bms['soh_pct'])} %", "Täyden akun energia / alkuperäinen energia")
    add("Puskuri", f"{fmt(bms.get('puskuri_kwh'), 2)} kWh" if bms.get("puskuri_kwh") is not None else "–",
        "Energia, jota ei näytetä käyttäjälle")
    add("Käytettävä energia", f"{fmt(bms.get('kaytettava_kwh'))} kWh" if bms.get("kaytettava_kwh") else "–",
        "Täyden akun energia vähennettynä puskurilla")
    add("Varaustila (näytöllä)", f"{fmt(bms.get('soc_ui'))} %" if bms.get("soc_ui") is not None else "–",
        "Mittauksen lopussa")
    add("Varaustila (kennojen keskiarvo)", f"{fmt(bms.get('soc_avg'))} %" if bms.get("soc_avg") is not None else "–",
        f"Vaihteluväli {fmt(bms.get('soc_min'))}–{fmt(bms.get('soc_max'))} %")
    add("Akun lämpötila mittauksessa", f"{fmt(tt.get('min'))}–{fmt(tt.get('max'))} °C" if tt.get("min") is not None
        else "–", "Akunhallinnan lämpötila-anturit")
    if veh.get("akun_massa_kg"):
        add("Akun massa", f"{fmt(veh['akun_massa_kg'], 0)} kg", "Akunhallinnan kokoonpanotieto")
    if veh.get("akun_matkamittari_km"):
        add("Akun matkamittari", f"{fmt(veh['akun_matkamittari_km'], 0)} km",
            "Akun oma laskuri. Auton mittarilukemaa pienempi arvo viittaa vaihdettuun akkuun.")
    add("Akusta otettu energia yhteensä", f"{fmt(lt.get('purku_kwh'), 0)} kWh" if lt.get("purku_kwh") else "–",
        "Akun elinkaaren laskuri")
    add("Akkuun ladattu energia yhteensä", f"{fmt(lt.get('lataus_kwh'), 0)} kWh" if lt.get("lataus_kwh") else "–",
        "Akun elinkaaren laskuri")
    if lt.get("syklit"):
        add("Täysiä lataussyklejä", f"noin {fmt(lt['syklit'], 0)}", "Otettu energia / alkuperäinen energia")
    if lt.get("kulutus_wh_km"):
        add("Keskikulutus elinkaaren aikana", f"{fmt(lt['kulutus_wh_km'], 0)} Wh/km", "Otettu energia / mittarilukema")
    E.append(_table(rows, [62 * mm, 34 * mm, CW - 96 * mm]))

    v = summ.get("vertailu")
    if v:
        E.append(P("Vertailu ajomäärään", "h3"))
        E.append(P(f"Akun kapasiteetti on alentunut {fmt(v['toteutunut_alenema_pct'])} %. Teslan julkaiseman "
                   f"keskiarvon perusteella alenema on {fmt(odo, 0)} km:n kohdalla tyypillisesti noin "
                   f"{fmt(v['odotettu_alenema_pct'])} %. Arvio: <b>{v['arvio'].lower()}</b>. Vertailu on suuntaa "
                   "antava, koska alenemaan vaikuttavat myös ikä, lataustavat ja ilmasto.", "body"))

    hist = [t for t in storage.tests(test["vehicle_id"]) if t["tila"] == "valmis" and t["tulos"]
            and (t["tulos"].get("yhteenveto") or {}).get("kunto_pct") and t["mittarilukema"]]
    pts = sorted({(t["mittarilukema"], t["tulos"]["yhteenveto"]["kunto_pct"]) for t in hist})
    if len({km for km, _ in pts}) >= 2:
        E.append(Spacer(1, 4 * mm))
        E.append(_img(charts.trend_chart(pts), CW))

    # ---------------- Menetelmä ja tietolähteet -----------------------
    E.append(PageBreak())
    E.append(P("Menetelmä ja tietolähteet", "h2"))
    meth = [
        ("Tiedonkeruu", "Tiedot luettiin auton CAN-väylältä diagnostiikkaliitännän kautta. Ohjelma ainoastaan kuuntelee "
         "väylää eikä lähetä autolle viestejä tai muuta sen asetuksia. Viestien sisältö puretaan avoimien, "
         "Tesla-omistajien yhteisön ylläpitämien viestimäärittelyjen mukaisesti" + (
             " (Model S 2012–2021 / Model X 2015–2021: Open Vehicle Monitoring System ja Battery-Emulator)."
             if veh.get("alusta") == "sx" else " (Model 3 DBC ja Battery-Emulator).")),
        ("Alkuperäinen kapasiteetti", "Akun alkuperäinen energia luetaan ensisijaisesti akunhallinnasta, joka "
         "tallentaa sen akun valmistuksen yhteydessä. Jos arvoa ei saada, käytetään käyttäjän ilmoittamaa arvoa "
         "tai mallitaulukon likiarvoa, joka valitaan valmistenumeron (vuosimalli, tehdas, voimalinja) ja "
         "kennoryhmien määrän perusteella. Käytetty lähde näkyy raportissa."),
        ("Akun kunto (SOH)", "Kunto on akun nykyinen kokonaiskapasiteetti jaettuna alkuperäisellä "
         "kapasiteetilla. Pikatarkastuksessa nykyinen kapasiteetti on akunhallinnan oma arvio. "
         "Kapasiteettimittauksessa se on mitattu latauksen aikana."),
    ]
    if is_cap:
        meth += [
            ("Kapasiteettimittaus", "Akkuun latauksen aikana mennyt energia lasketaan integroimalla akun jännitteen "
             "ja virran tulo ajan yli (E = ∫ U · I dt) useita kertoja sekunnissa. Akun sisäisissä resistansseissa "
             "syntyvä häviö (R · ∫ I² dt) vähennetään, jolloin saadaan akkuun varastoitunut energia. Resistanssi "
             "määritetään jännitteen noususta latauksen alussa."),
            ("Mittausvälin ulkopuolinen osuus", "Akkua ei pureta täysin tyhjäksi. Lähtövarauksen alapuolinen "
             "energia lasketaan mitatusta ampeerituntikapasiteetista ja akkukemian lepojännitekäyrästä. Mitä "
             "matalammasta varauksesta lataus aloitetaan, sitä pienempi tämä osuus ja sen epävarmuus on."),
            ("Epävarmuus", "Epävarmuus yhdistetään neliöllisesti jännite- ja virtamittauksen tarkkuudesta (1 %), "
             "varaustilan lukemasta latauksen alussa ja lopussa, mittausvälin ulkopuolisesta osuudesta, häviöiden "
             "korjauksesta ja mahdollisista mittausdatan katkoista."),
        ]
    meth += [
        ("Kennoryhmät", "Kennoryhmien jännitteet luetaan akunhallinnasta 0,1 mV:n tarkkuudella. Poikkeavaksi "
         "merkitään ryhmä, jonka jännite eroaa mediaanista yli 15 mV tai yli nelinkertaisesti tavanomaisen "
         "hajonnan verran. Jännite-eron luokat levossa: alle 15 mV erinomainen, alle 30 mV hyvä, alle 50 mV "
         "tyydyttävä. Alle 20 %:n varauksessa rajat ovat 1,5-kertaiset, koska kennojännite muuttuu siellä jyrkemmin."),
        ("Kunnon luokitus", "Vähintään 90 % erinomainen, 85–90 % hyvä, 80–85 % tyydyttävä, 70–80 % heikentynyt. "
         "Teslan akkutakuu kattaa kapasiteetin laskun alle 70 %:n takuuaikana."),
        ("Vertailu ajomäärään", "Vertailukäyrä perustuu Teslan vaikuttavuusraportissa (Impact Report 2023) "
         "julkaistuun keskiarvoon, jonka mukaan Model 3- ja Model Y -akkujen kapasiteetti on alentunut noin "
         "15 % ja Model S- ja Model X -akkujen noin 12 % noin 320 000 km:n jälkeen."),
        ("Tietojen eheys", "Kaikki mittauksen aikana vastaanotetut viestit tallennetaan muuttamattomina "
         "raakadatatiedostoon. Tiedoston SHA-256-tarkiste on alla. Tarkisteen avulla voidaan todentaa, että "
         "raportti on laskettu juuri tästä aineistosta."),
    ]
    for head, txt in meth:
        E.append(KeepTogether([P(head, "h3"), P(txt, "body")]))

    E.append(P("Mittauksen tiedot", "h3"))
    info = r.get("meta", {}).get("sovitin") or {}
    E.append(_kv([
        ("Ohjelma", f"{NIMI} {r.get('versio', VERSIO)}"),
        ("Tietolähde", f"{r.get('meta', {}).get('lahde') or '–'}, {info.get('sovitin') or '–'}"),
        ("Viestiarkkitehtuuri", veh.get("alusta_nimi") or "–"),
        ("Akunhallinnan energiaviestin muoto", {"uusi": "Uudempi (kanavoitu)", "vanha": "Vanhempi",
                                                "sx10": "10-bittinen", "sx11": "11-bittinen"}.get(
            bms.get("energiamuoto"), "–")),
        *([("Akun virran tarkistus", bms.get("virtatarkistus").capitalize())] if bms.get("virtatarkistus") else []),
        ("Mittaus alkoi", _date(test["aloitettu"])),
        ("Mittaus päättyi", _date(test.get("paattynyt"))),
        ("Tallennettuja näytteitä", f"{len(samples)} kpl"),
        ("Raakadatan SHA-256", test.get("tarkiste") or "–"),
    ], (52 * mm, CW - 52 * mm)))
    if events:
        E.append(P("Tapahtumat", "h3"))
        t0 = events[0]["t"]
        rows = [[P("Aika", "label"), P("Tapahtuma", "label")]]
        for ev in events:
            rows.append([P(_dur(ev["t"] - t0) if ev["t"] - t0 >= 60 else "0 min", "small"), P(ev["teksti"], "smallink")])
        E.append(_table(rows, [24 * mm, CW - 24 * mm]))
    E.append(Spacer(1, 5 * mm))
    E.append(P("Raportti perustuu mittaushetken tietoihin. Akun kunto voi muuttua käytön ja ajan myötä. "
               "Raportti ei ole valmistajan takuulausunto.", "small"))

    # ---------------- Sanasto ------------------------------------------
    from .docs import SANASTO
    E.append(PageBreak())
    E.append(P("Sanasto", "h2"))
    E.append(_table([[P(a, "cellb"), P(b, "cell")] for a, b in SANASTO], [50 * mm, CW - 50 * mm], header=False,
                    valign="TOP"))

    doc.build(E)
    return out_path
