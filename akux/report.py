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


_BRAND = {"gen": "Teslan"}       # raportin auton merkki genetiivissä (asetetaan raporttia muodostettaessa)


def P(text, style="body"):
    if _BRAND["gen"] != "Teslan" and isinstance(text, str):
        text = text.replace("Teslan ", _BRAND["gen"] + " ")
    return Paragraph(text, ST[style] if isinstance(style, str) else style)


GRADE_LEVEL = {"Erinomainen": 5, "Kunnossa": 5, "Hyvä": 4, "Tyydyttävä": 3, "Huomioitava": 3,
               "Heikentynyt": 2, "Poikkeava": 1, "Takuurajan alittava": 1}
GRADE_TONE = {5: "#1F4E79", 4: "#1F4E79", 3: "#B7791F", 2: "#B42318", 1: "#B42318"}


def _star(c, cx, cy, r, filled):
    import math
    pts = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    p = c.beginPath()
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    p.close()
    c.drawPath(p, stroke=0, fill=1)


class Pill(Flowable):
    """Luokan merkintä: viisi tähteä ja luokan nimi."""

    def __init__(self, text):
        super().__init__()
        self.text = text or ""
        self.level = GRADE_LEVEL.get(self.text, 0)
        self.w = 31 + pdfmetrics.stringWidth(self.text, "Inter-Medium", 7.6)
        self.h = 10

    def wrap(self, aw, ah):
        return (self.w, self.h) if self.text else (0, 0)

    def draw(self):
        if not self.text:
            return
        c = self.canv
        tone = colors.HexColor(GRADE_TONE.get(self.level, "#6B7480"))
        for k in range(5):
            c.setFillColor(tone if k < self.level else LINE)
            _star(c, 2.6 + k * 5.4, 4.6, 2.7, k < self.level)
        c.setFillColor(INK)
        c.setFont("Inter-Medium", 7.6)
        c.drawString(31, 2, self.text)


class SohHero(Flowable):
    """Etusivun kuntonäyttö: akkukuva, kuntoprosentti ja viisiportainen luokka-asteikko."""
    SEGMENTS = [(0, 70, "Alle 70 %", "Takuurajan alittava"), (70, 80, "70–80 %", "Heikentynyt"),
                (80, 90, "80–90 %", "Hyvä"), (90, 101, "90–100 %", "Erinomainen")]

    def __init__(self, pct, width, caption, note=""):
        super().__init__()
        self.pct, self.width, self.caption, self.note = pct, width, caption, note
        self.height = 38 * mm

    def wrap(self, aw, ah):
        return self.width, self.height

    def _battery(self, c, x, y, bw, bh):
        """Akku, jonka kymmenen lohkoa täyttyvät kunnon mukaan."""
        c.setStrokeColor(INK)
        c.setLineWidth(1.4)
        c.setFillColor(colors.white)
        c.roundRect(x, y, bw, bh, 2.2 * mm, stroke=1, fill=1)
        c.setFillColor(INK)
        c.roundRect(x + bw + 0.8 * mm, y + bh * 0.3, 2.2 * mm, bh * 0.4, 0.8 * mm, stroke=0, fill=1)
        pad, gap, n = 1.6 * mm, 0.9 * mm, 10
        sw = (bw - 2 * pad - (n - 1) * gap) / n
        sh = bh - 2 * pad
        level = 0 if self.pct is None else max(0.0, min(100.0, self.pct)) / 10
        for k in range(n):
            sx = x + pad + k * (sw + gap)
            c.setFillColor(colors.HexColor("#E3E7EC"))
            c.roundRect(sx, y + pad, sw, sh, 0.7 * mm, stroke=0, fill=1)
            fill = max(0.0, min(1.0, level - k))
            if fill > 0:
                c.setFillColor(ACCENT if level >= 7 else colors.HexColor("#B42318"))
                c.roundRect(sx, y + pad, sw * fill, sh, 0.7 * mm, stroke=0, fill=1)

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        c.setFillColor(PANEL)
        c.roundRect(0, 0, w, h, 2.5 * mm, stroke=0, fill=1)
        # vasemmalla akkukuva
        bw, bh = 40 * mm, 17 * mm
        bx, by = 7 * mm, (h - bh) / 2
        self._battery(c, bx, by, bw, bh)
        # oikealla luku ja asteikko
        x0 = bx + bw + 12 * mm
        x1 = w - 7 * mm
        c.setFillColor(MUTED)
        c.setFont("Inter-Medium", 7.4)
        c.drawString(x0, h - 8 * mm, "AKUN KUNTO (SOH)")
        if self.pct is None:
            c.setFont("Inter-SemiBold", 24)
            c.setFillColor(INK)
            c.drawString(x0, h - 18 * mm, "–")
            return
        val = fmt(self.pct)
        c.setFillColor(INK)
        c.setFont("Inter-SemiBold", 28)
        c.drawString(x0, h - 18.5 * mm, val)
        vw = pdfmetrics.stringWidth(val, "Inter-SemiBold", 28)
        c.setFont("Inter-SemiBold", 15)
        c.setFillColor(MUTED)
        c.drawString(x0 + vw + 1.2 * mm, h - 18.5 * mm, "%")
        c.setFont("Inter", 7.2)
        c.drawString(x0 + vw + 8 * mm, h - 15.2 * mm, self.caption)
        # asteikko
        sx, sw = x0, x1 - x0
        sy = 10 * mm
        seg_w = sw / len(self.SEGMENTS)
        gap = 1.0
        active = next(k for k, (lo, hi, _, _) in enumerate(self.SEGMENTS) if lo <= self.pct < hi or
                      (k == len(self.SEGMENTS) - 1 and self.pct >= lo))
        for k, (lo, hi, rng, name) in enumerate(self.SEGMENTS):
            x = sx + k * seg_w
            on = k == active
            c.setFillColor(ACCENT if on else colors.HexColor("#DDE2E8"))
            c.rect(x + gap / 2, sy, seg_w - gap, 2.0 * mm, stroke=0, fill=1)
            c.setFont("Inter-SemiBold" if on else "Inter", 6.8)
            c.setFillColor(INK if on else MUTED)
            c.drawCentredString(x + seg_w / 2, sy - 3.8 * mm, name)
            c.setFont("Inter", 6.2)
            c.setFillColor(MUTED)
            c.drawCentredString(x + seg_w / 2, sy - 6.6 * mm, rng)
        lo, hi = self.SEGMENTS[active][0], min(self.SEGMENTS[active][1], 100)
        frac = 0.5 if hi <= lo else (min(max(self.pct, lo), hi) - lo) / (hi - lo)
        mx = sx + active * seg_w + gap / 2 + frac * (seg_w - gap)
        c.setFillColor(INK)
        pth = c.beginPath()
        pth.moveTo(mx - 1.4 * mm, sy + 3.7 * mm)
        pth.lineTo(mx + 1.4 * mm, sy + 3.7 * mm)
        pth.lineTo(mx, sy + 2.2 * mm)
        pth.close()
        c.drawPath(pth, stroke=0, fill=1)


class SohGauge(Flowable):
    """Vaihtoehto B: kaarimittari, jonka keskellä kuntoprosentti."""
    BANDS = [(60, 70, "#C8CED6"), (70, 80, "#AAB4C0"), (80, 90, "#6F8399"), (90, 100, "#1F4E79")]

    def __init__(self, pct, width, caption, luokka):
        super().__init__()
        self.pct, self.width, self.caption, self.luokka = pct, width, caption, luokka
        self.height = 52 * mm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        import math
        c = self.canv
        w, h = self.width, self.height
        cx, cy, r = w / 2, 14 * mm, 30 * mm
        lo, hi = 60.0, 100.0

        def ang(p):
            return 180 - (min(hi, max(lo, p)) - lo) / (hi - lo) * 180
        c.setLineCap(0)
        for a_, b_, col in self.BANDS:
            c.setStrokeColor(colors.HexColor(col))
            c.setLineWidth(4.2 * mm)
            c.arc(cx - r, cy - r, cx + r, cy + r, startAng=ang(b_) + 0.6, extent=ang(a_) - ang(b_) - 1.2)
        c.setFont("Inter", 6.4)
        c.setFillColor(MUTED)
        for p_ in (60, 70, 80, 90, 100):
            t = math.radians(ang(p_))
            c.drawCentredString(cx + (r + 5.5 * mm) * math.cos(t), cy + (r + 5.5 * mm) * math.sin(t) - 1, f"{p_}")
        if self.pct is not None:
            t = math.radians(ang(self.pct))
            c.setStrokeColor(INK)
            c.setLineWidth(1.6)
            c.line(cx + (r - 3.6 * mm) * math.cos(t), cy + (r - 3.6 * mm) * math.sin(t),
                   cx + (r + 2.6 * mm) * math.cos(t), cy + (r + 2.6 * mm) * math.sin(t))
        c.setFillColor(MUTED)
        c.setFont("Inter-Medium", 7.4)
        c.drawCentredString(cx, cy + 15 * mm, "AKUN KUNTO (SOH)")
        c.setFillColor(INK)
        c.setFont("Inter-SemiBold", 30)
        val = fmt(self.pct) + " %" if self.pct is not None else "–"
        c.drawCentredString(cx, cy + 2.5 * mm, val)
        c.setFont("Inter-SemiBold", 9.5)
        c.drawCentredString(cx, cy - 3.8 * mm, self.luokka or "")
        c.setFont("Inter", 7.2)
        c.setFillColor(MUTED)
        c.drawCentredString(cx, cy - 8.6 * mm, self.caption)


class SohBand(Flowable):
    """Vaihtoehto C: tumma tunnusluku-kaista koko leveydeltä."""

    def __init__(self, pct, width, caption, luokka, items):
        super().__init__()
        self.pct, self.width, self.caption, self.luokka, self.items = pct, width, caption, luokka, items
        self.height = 34 * mm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        c.setFillColor(ACCENT)
        c.roundRect(0, 0, w, h, 2.5 * mm, stroke=0, fill=1)
        light = colors.HexColor("#C9D7E6")
        c.setFillColor(light)
        c.setFont("Inter-Medium", 7.4)
        c.drawString(7 * mm, h - 8 * mm, "AKUN KUNTO (SOH)")
        c.setFillColor(colors.white)
        c.setFont("Inter-SemiBold", 32)
        val = fmt(self.pct) if self.pct is not None else "–"
        c.drawString(7 * mm, h - 19 * mm, val)
        vw = pdfmetrics.stringWidth(val, "Inter-SemiBold", 32)
        c.setFont("Inter-SemiBold", 16)
        c.drawString(7 * mm + vw + 1.5 * mm, h - 19 * mm, "%")
        c.setFont("Inter-SemiBold", 9)
        c.drawString(7 * mm, 4.5 * mm, self.luokka or "")
        c.setFillColor(light)
        c.setFont("Inter", 7.2)
        c.drawString(7 * mm + pdfmetrics.stringWidth((self.luokka or "") + "  ", "Inter-SemiBold", 9), 4.5 * mm,
                     self.caption)
        # palkki kunnosta 0–100 %
        bx, by, bw = 7 * mm, 10.5 * mm, 62 * mm
        c.setFillColor(colors.HexColor("#3D6890"))
        c.roundRect(bx, by, bw, 1.6 * mm, 0.8 * mm, stroke=0, fill=1)
        if self.pct is not None:
            c.setFillColor(colors.white)
            c.roundRect(bx, by, bw * max(0, min(100, self.pct)) / 100, 1.6 * mm, 0.8 * mm, stroke=0, fill=1)
        # oikealla kolme tunnuslukua
        x = 82 * mm
        cw = (w - x - 4 * mm) / len(self.items)
        for k, (lab, v, sub_) in enumerate(self.items):
            xx = x + k * cw
            if k:
                c.setStrokeColor(colors.HexColor("#3D6890"))
                c.setLineWidth(0.6)
                c.line(xx - 3 * mm, 6 * mm, xx - 3 * mm, h - 6 * mm)
            c.setFillColor(light)
            c.setFont("Inter-Medium", 6.8)
            c.drawString(xx, h - 8 * mm, lab)
            c.setFillColor(colors.white)
            c.setFont("Inter-SemiBold", 15)
            c.drawString(xx, h - 17 * mm, v)
            c.setFillColor(light)
            c.setFont("Inter", 6.8)
            c.drawString(xx, h - 22.5 * mm, sub_)


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


def draw_mark(c, cx, cy, r, dots=True, ring=True):
    """AKVERI-merkki: valkoinen ympyrä, tummansininen reunus, pisteviivarengas ja A-kirjain."""
    k = r / 50.0                                  # merkki on piirretty 100 × 100 -ruudukkoon
    c.saveState()
    if ring:
        c.setFillColor(colors.white)
        c.setStrokeColor(ACCENT)
        c.setLineWidth(6 * k)
        c.circle(cx, cy, r - 3.5 * k, stroke=1, fill=1)
    if dots and r >= 3 * mm:
        c.setStrokeColor(colors.Color(ACCENT.red, ACCENT.green, ACCENT.blue, alpha=0.38))
        c.setLineWidth(1.8 * k)
        c.setDash(2 * k, 4 * k)
        c.circle(cx, cy, 37 * k, stroke=1, fill=0)
        c.setDash()

    def pt(x, y):                                 # merkin koordinaatit (y alaspäin) sivulle
        return cx + (x - 50) * k, cy - (y - 50) * k
    c.setStrokeColor(ACCENT)
    c.setLineWidth(9 * k)
    c.setLineJoin(1)
    c.setLineCap(1)
    pth = c.beginPath()
    pth.moveTo(*pt(33, 71))
    pth.lineTo(*pt(50, 28))
    pth.lineTo(*pt(67, 71))
    c.drawPath(pth, stroke=1, fill=0)
    c.setStrokeColor(BRAND_GREEN)
    c.setLineWidth(7.5 * k)
    c.line(*pt(40.5, 57), *pt(59.5, 57))
    c.restoreState()


def draw_logo(c, x, y, h, wordmark=True, ink=None, watermark=False):
    """AKVERI-merkki (sama kuin ohjelman kuvake) ja nimi. (x, y) = vasen alakulma, h = merkin korkeus."""
    c.saveState()
    draw_mark(c, x + h / 2, y + h / 2, h / 2, dots=h >= 6 * mm)
    w = h
    if wordmark:
        c.setFillColor(ink or INK)
        size = h * 0.72
        c.setFont("Inter-SemiBold", size)
        c.drawString(x + h * 1.3, y + h * 0.24, NIMI, charSpace=size * 0.06)
        w = h * 1.3 + pdfmetrics.stringWidth(NIMI, "Inter-SemiBold", size) + size * 0.06 * (len(NIMI) - 1)
    c.restoreState()
    return w


def _arc_text(c, text, cx, cy, r, font, size, top=True, spacing=0.0):
    """Kaareva teksti: top=True yläkaarelle myötäpäivään, muuten alakaarelle vasemmalta oikealle."""
    import math
    widths = [pdfmetrics.stringWidth(ch, font, size) + spacing for ch in text]
    total = sum(widths) - spacing
    ang = math.pi / 2 + total / r / 2 if top else 3 * math.pi / 2 - total / r / 2
    c.setFont(font, size)
    for ch, w in zip(text, widths):
        half = (w - spacing) / 2 / r
        a = ang - half if top else ang + half
        c.saveState()
        c.translate(cx + r * math.cos(a), cy + r * math.sin(a))
        c.rotate(math.degrees(a) - 90 if top else math.degrees(a) + 90)
        c.drawCentredString(0, 0, ch)
        c.restoreState()
        ang = ang - w / r if top else ang + w / r
    return total


def draw_seal(c, cx, cy, r, bottom_text):
    """AKVERI-leima: kehällä AKVERI-TESTI ja alhaalla mittauksen tiedot, keskellä merkki."""
    k = r / 100.0                                 # leima on suunniteltu 200 × 200 -ruudukkoon
    c.saveState()
    c.setFillColor(colors.white)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(4 * k)
    c.circle(cx, cy, 96 * k, stroke=1, fill=1)
    c.setStrokeColor(colors.Color(ACCENT.red, ACCENT.green, ACCENT.blue, alpha=0.55))
    c.setLineWidth(1.3 * k)
    c.circle(cx, cy, 88 * k, stroke=1, fill=0)
    c.circle(cx, cy, 62 * k, stroke=1, fill=0)
    c.setFillColor(ACCENT)
    # Tekstit keskitetään renkaiden väliin (säde 62–88): isojen kirjainten korkeus on noin 0,72 × koko
    top_size, bot_size = 17 * k, 14 * k
    _arc_text(c, "AKVERI-TESTI", cx, cy, 75 * k - 0.36 * top_size, "Inter-Bold", top_size, top=True,
              spacing=4 * k)
    _arc_text(c, bottom_text.upper(), cx, cy, 75 * k + 0.36 * bot_size, "Inter-SemiBold", bot_size, top=False,
              spacing=3 * k)
    c.setFillColor(BRAND_GREEN)
    c.circle(cx - 75 * k, cy, 2.6 * k, stroke=0, fill=1)
    c.circle(cx + 75 * k, cy, 2.6 * k, stroke=0, fill=1)
    c.restoreState()
    draw_mark(c, cx, cy, 50 * k, ring=False)


def draw_watermark(c, style):
    """Vino, läpikuultava AKVERI-vesileima sivun päälle. style: iso, toisto, rivit tai ei."""
    if style not in ("iso", "toisto", "rivit"):
        return
    c.saveState()
    c.setFillColor(colors.Color(0x1F / 255, 0x4E / 255, 0x79 / 255, alpha={"iso": 0.055, "toisto": 0.042}.get(style, 0.06)))
    c.translate(W / 2, H / 2)
    c.rotate(35)
    if style == "iso":
        size = 150
        c.setFont("Inter-SemiBold", size)
        c.drawCentredString(0, -size * 0.35, NIMI)
    elif style == "toisto":
        size = 22
        c.setFont("Inter-SemiBold", size)
        step_x, step_y = 62 * mm, 30 * mm
        for row in range(-9, 10):
            off = (row % 2) * step_x / 2
            for col in range(-6, 7):
                c.drawCentredString(col * step_x + off, row * step_y, NIMI)
    else:
        size = 34
        c.setFont("Inter-SemiBold", size)
        for row in range(-4, 5):
            c.drawCentredString(0, row * 70 * mm, "   ·   ".join([NIMI] * 6))
    c.restoreState()


# ----------------------------------------------------------------------
HDR_TOP = H - 8 * mm
LOGO_KOOT = {"pieni": (9 * mm, 40 * mm, 7.5 * mm), "normaali": (11 * mm, 55 * mm, 9 * mm),
             "suuri": (14 * mm, 70 * mm, 11.5 * mm)}      # yrityksen logo: korkeus, enimmäisleveys; AKVERI-logo


def header_line(ctx) -> float:
    """Ylätunnisteen viivan korkeus: logo on sivun yläreunassa, ja sisältö alkaa logon koon mukaan."""
    hgt, _, akv = LOGO_KOOT.get(ctx.get("logo_koko"), LOGO_KOOT["normaali"])
    logo = ctx.get("logo")
    if logo and Path(logo).exists():
        h = hgt
    elif not ctx.get("company"):
        h = akv
    else:
        h = 9 * mm
    return HDR_TOP - h - 2.5 * mm


class ReportDoc(BaseDocTemplate):
    def __init__(self, path, ctx):
        ctx["hdr_line"] = header_line(ctx)
        top = ctx["hdr_line"] - 5 * mm
        super().__init__(str(path), pagesize=A4, leftMargin=M, rightMargin=M, topMargin=H - top,
                         bottomMargin=20 * mm, title=ctx["title"].replace("  ·  ", " – "), author=ctx["company"] or NIMI,
                         subject="Ajoakun kuntoraportti", creator=f"{NIMI} {VERSIO}")
        self.ctx = ctx
        frame = Frame(M, 20 * mm, CW, top - 20 * mm, id="f", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        first = Frame(M, 58 * mm, CW, top - 58 * mm, id="f1", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        wm = lambda c, d: draw_watermark(c, ctx.get("vesileima"))  # noqa: E731
        self.addPageTemplates([PageTemplate(id="first", frames=[first], onPage=self._first, onPageEnd=wm),
                               PageTemplate(id="page", frames=[frame], onPage=self._decorate, onPageEnd=wm)])

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
            qy = self.ctx["hdr_line"] - 2 * mm - size
            renderPDF.draw(d, c, W - M - size + 1.5 * mm, qy)
            c.saveState()
            c.setFont("Inter", 5.6)
            c.setFillColor(MUTED)
            c.drawRightString(W - M, qy - 2.6 * mm, self.ctx.get("qr_label") or "Raportin tunnistetiedot")
            c.restoreState()
        c.saveState()
        y = 36 * mm
        # Allekirjoitusten väliin AKVERI-leima, keskitettynä allekirjoitusalueen korkeuteen
        seal_r = 13 * mm
        half = (CW - 2 * seal_r - 10 * mm) / 2
        draw_seal(c, W / 2, y + 6.5 * mm, seal_r, self.ctx["measured"])
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.6)
        c.line(M, y, M + half, y)
        c.line(W - M - half, y, W - M, y)
        c.setFont("Inter-Medium", 7.2)
        c.setFillColor(MUTED)
        c.drawString(M, y + 13 * mm, "Paikka ja päiväys")
        c.drawString(W - M - half, y + 13 * mm, "Mittaajan allekirjoitus ja nimenselvennys")
        # Riippumattomuus ja vastuunrajaus allekirjoitusten alle
        lines = []
        indep = self.ctx.get("riippumaton")
        if indep is True:
            lines.append("Mittaus on tehty riippumattomasti: mittaaja ei ole ajoneuvon kaupan osapuoli eikä sidoksissa siihen.")
        elif indep is False:
            lines.append("Mittaaja ei ole riippumaton: mittaaja on ajoneuvon kaupan osapuoli tai sidoksissa siihen.")
        lines += ["Raportti kuvaa akun tilaa mittaushetkellä. Se ei ole takuu akun tai ajoneuvon kunnosta eikä niiden "
                  "kestosta. Tulokset perustuvat auton akunhallinnan",
                  f"tietoihin, ja niiden tarkkuus on ilmoitettu raportissa. {NIMI}-ohjelmiston toimittaja ei vastaa "
                  "mittauksen suorittamisesta eikä tuloksiin perustuvista päätöksistä."]
        c.setFont("Inter", 5.9)
        yy = y - 11.5 * mm
        for k, ln in enumerate(lines):
            if k == 0 and indep is not None:
                c.setFont("Inter-SemiBold", 6.2)
                c.setFillColor(INK)
            else:
                c.setFont("Inter", 5.9)
                c.setFillColor(MUTED)
            c.drawString(M, yy, ln)
            yy -= 2.5 * mm
        c.restoreState()

    def _decorate(self, c, doc):
        ctx = self.ctx
        # Himmeä AKVERI-vesileima sivun taustalle (piirretään ennen sisältöä)
        c.saveState()
        line_y = ctx["hdr_line"]
        y = line_y + 7 * mm
        logo = ctx.get("logo")
        hgt, maxw, akv = LOGO_KOOT.get(ctx.get("logo_koko"), LOGO_KOOT["normaali"])
        x0 = M
        if not ctx["company"] and not (logo and Path(logo).exists()):
            # Ilman yrityksen tietoja otsikkona on AKVERI-logo; mittaavan yrityksen tiedoilla vain yrityksen omat
            draw_logo(c, M, HDR_TOP - akv, akv)
            x0 = None
        elif logo and Path(logo).exists():
            try:
                from reportlab.lib.utils import ImageReader
                ir = ImageReader(logo)
                iw, ih = ir.getSize()
                # Logon koko asetuksista; logo sivun yläreunassa otsikkoviivan yläpuolella
                wid = min(maxw, hgt * iw / ih)
                h_img = wid * ih / iw
                base = HDR_TOP - hgt
                c.drawImage(ir, M, base + (hgt - h_img) / 2, width=wid, height=h_img, mask="auto")
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
        c.drawRightString(W - M, y - 11, f"Testi nro {ctx['report_no']}  ·  {ctx['date']}")
        c.setStrokeColor(LINE)
        c.setLineWidth(0.8)
        c.line(M, line_y, W - M, line_y)
        # alatunniste
        c.line(M, 14 * mm, W - M, 14 * mm)
        lw = draw_logo(c, M, 8.9 * mm, 3.6 * mm, ink=MUTED)
        c.setFont("Inter", 6.8)
        c.setFillColor(MUTED)
        c.drawString(M + lw + 3 * mm, 10 * mm, ctx["footer"])
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
    from .analysis import MERKKI_GEN
    brand = veh.get("merkki") or "Tesla"
    _BRAND["gen"] = MERKKI_GEN.get(brand, f"{brand}in")
    vi = veh.get("vin_tiedot") or {}
    cap = r.get("kapasiteetti") or {}
    bms = r.get("bms") or {}
    from . import polled as _polled_mod
    _polled = _polled_mod.module(veh.get("alusta"))
    summ = r["yhteenveto"]
    tyyppi = r["tyyppi"]
    is_cap = tyyppi in ("kapasiteetti", "taysi")
    purku = r.get("purku") or {}
    yhd = r.get("yhdistetty") or {}
    kuorma = r.get("kuorma") or {}
    dc = r.get("pikalataus") or {}
    itse = r.get("itsepurkaus") or {}

    company_line = "  ·  ".join(x for x in (s.get("yritys_osoite"), s.get("yritys_puhelin"),
                                            s.get("yritys_sahkoposti"), s.get("yritys_www")) if x)
    report_no = f"{time.strftime('%Y', time.localtime(test['aloitettu']))}-{tid:05d}"
    from .recorder import TYYPIT
    test_kind = TYYPIT.get(tyyppi, "Akun tarkastus")
    title = test_kind
    ctx = {
        "company": s.get("yritys_nimi"), "company_line": company_line, "logo": s.get("logo"),
        "title": test_kind, "report_no": report_no, "vesileima": s.get("vesileima") or "toisto", "date": _date(test.get("paattynyt") or test["aloitettu"], False),
        "measured": _date(test["aloitettu"], False),
        "logo_koko": s.get("logo_koko") or "normaali",
        "riippumaton": None if test.get("riippumaton") is None else bool(test["riippumaton"]),
        "footer": s.get("raportin_alatunniste") or f"{VERSIO}  ·  Tiedot: auton akunhallinta",
    }
    _y = r.get("yhteenveto") or {}
    qr_url = (s.get("qr_osoite") or "").strip()
    if qr_url.startswith(("https://", "http://")):
        from urllib.parse import urlencode
        ctx["qr"] = qr_url + ("&" if "?" in qr_url else "?") + urlencode(
            {"raportti": report_no, "tarkiste": (test.get("tarkiste") or "")[:16]})
        ctx["qr_label"] = "Tarkista raportti"
    else:
        ctx["qr_label"] = "Raportin tunnistetiedot"
    ctx["qr"] = ctx.get("qr") or "\n".join(x for x in (
        f"AKVERI-TESTI {report_no}",
        test_kind,
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
    A = []      # tekninen liite: mittauksen vaiheet, kennoryhmäluettelo, menetelmä ja tietolähteet
    liite = s.get("tekninen_liite", True) is not False

    # ---------------- Sivu 1: yhteenveto -------------------------------
    model_name = veh.get("malli") or (vi.get("malli") and f"Tesla {vi['malli']}") or brand
    import re as _re
    base_name = _re.sub(r"\s*\([^)]*\d{4}[^)]*\)\s*$", "", model_name)     # mallipohjan vuosiväli pois
    sub = base_name if brand != "Tesla" or base_name.startswith("Tesla") else f"Tesla {base_name}"
    _prof = profiles.get(veh.get("malli_id")) or {}
    if _prof.get("akku_lyhyt") and vi.get("malli") and brand == "Tesla" and _prof.get("alusta") == "sx":
        sub = f"Tesla {vi['malli']}  ·  {_prof['akku_lyhyt']}"
    year = vehicle.get("vuosimalli") or vi.get("vuosimalli")
    reg = (vehicle.get("rekisteri") or "").strip()
    head = [P(test_kind, "h1"), P(sub, "sub")]
    meta_line = "  ·  ".join(x for x in ((f"Vuosimalli {year}" if year else None),
                                         (f"Rekisterinumero <b>{reg}</b>" if reg else None)) if x)
    if meta_line:
        head += [Spacer(1, 2), P(meta_line, "sub")]
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
        lahde_txt = {"Akunhallinnan arvio": f"{_BRAND['gen']} akunhallinta"}.get(summ.get("kunto_lahde"),
                                                                    summ.get("kunto_lahde") or "")
        cap_pct = summ.get("epavarmuus_pct") if summ.get("kunto_lahde") != "Akunhallinnan arvio" else None
        caption = lahde_txt + (f"  ·  ±{fmt(cap_pct)} %-yks." if cap_pct else "")
    else:
        caption = "Ei laskettavissa"
    style_ = (s.get("raportin_ulkoasu") or "b").lower()
    _kk0 = r.get("kapasiteetit") or {}
    if style_ == "c":
        items = [("BRUTTO", f"{fmt(kwh)} kWh" if kwh else "–", f"uutena {fmt(r['viite']['kwh'])} kWh"),
                 ("NETTO", f"{fmt(_kk0['netto_nyt'])} kWh" if _kk0.get("netto_nyt") else "–",
                  f"suojavara {fmt(_kk0.get('puskuri_kwh'), 1)} kWh" if _kk0.get("puskuri_kwh") is not None else ""),
                 ("JÄNNITE-ERO", (f"alle {fmt(veh['kenno_resoluutio_mv'], 0)} mV" if cs and (veh.get("kenno_resoluutio_mv") or 0) > 1 and cs["ero_mv"] < veh["kenno_resoluutio_mv"] else f"{fmt(cs['ero_mv'], 0)} mV") if cs else "–",
                  f"{cs['lkm']} kennoryhmää" if cs else "")]
        E.append(SohBand(soh, CW, caption, summ.get("kunto_luokka"), items))
        E.append(Spacer(1, 3 * mm))
    elif style_ == "b":
        E.append(SohGauge(soh, CW, caption, summ.get("kunto_luokka")))
        E.append(Spacer(1, 2 * mm))
    else:
        E.append(SohHero(soh, CW, caption))
        E.append(Spacer(1, 3 * mm))
    _kk = r.get("kapasiteetit") or {}
    kw = CW / 3
    kpis.append(kpi("KAPASITEETTI NYT (BRUTTO)", f"{fmt(kwh)} kWh" if kwh else "–",
                    (f"±{fmt(unc)} kWh  ·  " if unc else "") + f"uutena {fmt(r['viite']['kwh'])} kWh"))
    if not _kk.get("netto_nyt") and _polled and bms.get("nfp_kwh") and r["viite"].get("kwh"):
        # Kyselyihin vastaavat autot eivät ilmoita suojavaraa; näytetään akunhallinnan oma kuntoarvio
        kpis.append(kpi("AKUNHALLINNAN KUNTOARVIO", f"{fmt(bms['nfp_kwh'] / r['viite']['kwh'] * 100)} %",
                        f"{_BRAND['gen']} akunhallinta"))
    else:
        kpis.append(kpi("KÄYTETTÄVÄ ENERGIA (NETTO)", f"{fmt(_kk['netto_nyt'])} kWh" if _kk.get("netto_nyt") else "–",
                        f"Suojavara {fmt(_kk['puskuri_kwh'], 1)} kWh" if _kk.get("puskuri_kwh") is not None else ""))
    _res = veh.get("kenno_resoluutio_mv")
    _ero_txt = (f"alle {fmt(_res, 0)} mV" if cs and (_res or 0) > 1 and cs["ero_mv"] < _res else
                f"{fmt(cs['ero_mv'], 0)} mV" if cs else "–")
    kpis.append(kpi("KENNORYHMIEN JÄNNITE-ERO", _ero_txt,
                    f"{cs['luokka']}  ·  {cs['lkm']} kennoryhmää" if cs else "Ei mitattu"))
    kt = Table([kpis], colWidths=[kw, kw, kw], hAlign="LEFT") if style_ != "c" else Spacer(1, 0)
    if style_ != "c":
        kt.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("LINEAFTER", (0, 0), (1, 0), 0.6, LINE),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, LINE),
    ]))
    E.append(kt)
    E.append(Spacer(1, 2.2 * mm))
    src_line = "Kaikki mittausarvot ovat auton oman akunhallinnan luovuttamia."
    _pt = next((x for x in (r.get("paatulos"), r.get("yhdistetty"), r.get("kapasiteetti"), r.get("purku"))
                if x and x.get("valmis") and x.get("ero_bms_pct") is not None), None)
    if bms.get("nfp_kwh") and _pt:
        from .analysis import bms_vertailu
        _, _lause = bms_vertailu(_pt["ero_bms_pct"], _pt.get("epavarmuus_kwh"), _pt.get("taysi_kwh"))
        src_line = (f"Vertailu: {_BRAND['gen']} akunhallinnan oma arvio täyden akun energiasta "
                    f"<b>{fmt(bms['nfp_kwh'])} kWh</b> {_lause} (ero {fmt(_pt['ero_bms_pct'])} %). " + src_line)
    elif bms.get("nfp_kwh"):
        src_line = (f"{_BRAND['gen']} akunhallinnan oma arvio täyden akun energiasta "
                    f"<b>{fmt(bms['nfp_kwh'])} kWh</b>. " + src_line)
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
        *([("Riippumattomuus", "Riippumaton mittaaja" if test["riippumaton"] else "Mittaaja ei ole riippumaton")]
          if test.get("riippumaton") is not None else []),
    ]
    two = Table([[_kv(left, (32 * mm, CW / 2 - 35 * mm)), _kv(right, (34 * mm, CW / 2 - 34 * mm))]],
                colWidths=[CW / 2, CW / 2], hAlign="LEFT")
    two.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    E.append(P("Ajoneuvo ja mittaus", "h3"))
    E.append(two)
    E.append(Spacer(1, 5 * mm))

    # Arviot
    rows = [[P("Kohde", "label"), P("Tulos", "label"), P("Luokka", "label"), P("Selite", "label")]]
    for a in r.get("arviot", []):
        rows.append([P(a["nimi"], "cellb"), P(a["arvo"], "cell"), Pill(a.get("luokka")), P(a["kuvaus"], "small")])
    E.append(PageBreak())
    E.append(P("Yhteenveto", "h2"))
    E.append(P(summ.get("teksti", ""), "body"))
    E.append(Spacer(1, 5 * mm))
    E.append(P("Tulokset", "h2"))
    E.append(P("Luokat: erinomainen, hyvä, tyydyttävä, heikentynyt ja poikkeava." + (
        " Luokkien rajat on kuvattu teknisessä liitteessä." if liite else ""), "small"))
    E.append(Spacer(1, 3 * mm))
    E.append(_table(rows, [52 * mm, 25 * mm, 29 * mm, CW - 106 * mm]))

    if r.get("huomiot"):
        E.append(Spacer(1, 4 * mm))
        E.append(P("Huomiot", "h3"))
        for h in r["huomiot"]:
            E.append(P("– " + h, "smallink"))

    # Mittausolosuhteet
    E.append(Spacer(1, 6 * mm))
    E.append(P("Mittaus", "h3"))
    tt = r.get("lampotilat") or {}
    meta = r.get("meta") or {}
    rows_c = [[P("Tieto", "label"), P("Arvo", "label"), P("Selite", "label")]]

    def cond(n_, v_, p_=""):
        rows_c.append([P(n_, "cell"), P(v_ if v_ not in (None, "") else "–", "cellb"), P(p_, "small")])
    tapa = {
        "pikatarkastus": ("Pikatarkastus levossa", "Akunhallinnan tiedot ja kennoryhmien jännitteet"),
        "kapasiteetti": ("Kapasiteettimittaus latauksen aikana",
                         "Akkuun mennyt energia mitattu akun omasta jännitteestä ja virrasta"),
        "taysi": ("Purku ajamalla ja lataus täyteen",
                  "Kapasiteetti mitattu sekä ajossa että latauksessa"),
        "ajotesti": ("Purkumittaus ajon aikana", f"Akusta otettu energia {_BRAND['gen']} elinkaaren energialaskureista"),
        "pika_ajo": ("Lyhyt purkumittaus ajon aikana", f"Akusta otettu energia {_BRAND['gen']} elinkaaren energialaskureista"),
        "kuormitus": ("Kuormitus kiihdytyksillä", "Kennoryhmien jännite ja akun virta samanaikaisesti"),
        "pikalataus": ("Pikalataus tasavirtalaturilla", "Latausteho, varaustila ja kennoryhmien jännitteet"),
        "itsepurkaus": ("Seisonta yön yli", "Kennoryhmien lepojännitteet seisonnan alussa ja lopussa"),
    }.get(tyyppi, (test_kind, ""))
    cond("Mittaustapa", tapa[0], tapa[1])
    le = (meta.get("merkinnat") or {}).get("lahtoehdot")
    if tyyppi == "kuormitus" and le:
        ero = (le["t_max"] - le["t_min"]) if le.get("t_max") is not None and le.get("t_min") is not None else None
        cond("Lähtöehdot", f"Varaus {fmt(le.get('soc'))} %, akku {fmt(le.get('t_min'))}–{fmt(le.get('t_max'))} °C, "
             f"lämpötilaero {fmt(ero)} °C", "Vaatimus: varaus 40–80 %, akku 10–30 °C, lämpötilaero alle 2 °C")
    cond("Mittauksen kesto", _dur((meta.get("t_loppu") or 0) - (meta.get("t_alku") or 0)) if meta.get("t_loppu") else None,
         f"{_date(test['aloitettu'])} alkaen")
    if tt.get("alku_min") is not None:
        cond("Akun lämpötila alussa ja lopussa", f"{fmt(tt['alku_min'])}–{fmt(tt['alku_max'])} °C → "
             f"{fmt(tt['loppu_min'])}–{fmt(tt['loppu_max'])} °C", "Suositus 15–35 °C")
    if is_cap and cap.get("soc_alku") is not None:
        cond("Varaustila latauksen alussa ja lopussa", f"{fmt(cap['soc_alku'])} % → {fmt(cap['soc_loppu'])} %",
             f"Muutos {fmt(cap.get('dsoc'))} %-yksikköä")
        if tyyppi == "kapasiteetti":
            cond("Lepo ennen latausta ja sen jälkeen",
                 f"{fmt(cap.get('lepo_alku_min'), 0)} min ja {fmt(cap.get('lepo_loppu_min'), 0)} min", "Suositus 30 min")
    if purku.get("soc_alku") is not None:
        cond("Varaustila ajon alussa ja lopussa", f"{fmt(purku['soc_alku'])} % → {fmt(purku['soc_loppu'])} %",
             f"Muutos {fmt(purku.get('soc_muutos'))} %-yksikköä")
        if purku.get("matka_km"):
            cond("Ajettu matka", f"{fmt(purku['matka_km'], 0)} km",
                 f"{purku['osat']} ajokertaa" if (purku.get("osat") or 1) > 1 else "Yksi ajokerta")
    if tyyppi == "kuormitus" and kuorma.get("kuormitustapahtumat"):
        cond("Kuormitustapahtumia", f"{kuorma['kuormitustapahtumat']} kpl",
             f"Suurin teho {fmt(kuorma.get('teho_max_kw'), 0)} kW")
    if dc.get("soc_alku") is not None:
        cond("Varaustila latauksen alussa ja lopussa", f"{fmt(dc['soc_alku'])} % → {fmt(dc['soc_loppu'])} %",
             f"Kesto {fmt(dc.get('kesto_min'), 0)} min")
    if itse.get("tunnit"):
        cond("Seisonta-aika", f"{fmt(itse['tunnit'], 1)} h", "Suositus vähintään 8 tuntia")
    if tyyppi == "pikatarkastus" and cs:
        cond("Akun virta mittaushetkellä", f"{fmt(cs.get('virta_a'))} A", "Alle 3 A tarkoittaa, että akku on levossa")
        cond("Varaustila", f"{fmt(cs.get('soc'))} %" if cs.get("soc") is not None else None, "Kennoryhmien keskiarvo")
        if cs.get("naytteita"):
            cond("Kennojännitteiden näytteitä", f"{cs['naytteita']} kpl kennoryhmää kohden", "Tulos on näytteiden keskiarvo")
    src_info = meta.get("sovitin") or {}
    cond("Tietolähde", src_info.get("sovitin") or meta.get("lahde"), "Auton akunhallinta diagnostiikkaliitännän kautta")
    # Lyhyt taulukko pidetään otsikkonsa kanssa samalla sivulla, jottei sivulle jää yksittäisiä rivejä
    ct_ = _table(rows_c, [50 * mm, 64 * mm, CW - 114 * mm])
    E.append(KeepTogether([E.pop(), ct_]))

    # Tietojen alkuperä ja vastuu
    E.append(Spacer(1, 6 * mm))
    origin = ("Kaikki raportin mittausarvot on luettu auton omasta akunhallintajärjestelmästä (BMS) "
              "diagnostiikkaliitännän kautta. AKVERI ei käytä omia antureitaan eikä muuta luettuja arvoja, vaan "
              "tallentaa ne muuttamattomina. ")
    if is_cap:
        origin += ("Kapasiteettimittauksen tulos perustuu akunhallinnan jännite- ja virtamittauksiin, ja se on "
                   "tarkistettu akunhallinnan omasta latauslaskurista. ")
    if purku.get("valmis"):
        origin += (f"Purkumittauksen tulos perustuu {_BRAND['gen']} elinkaaren energialaskureihin ja akunhallinnan "
                   "varaustilaan. ")
    if is_cap or purku.get("valmis") or kuorma or dc or itse:
        origin += "Menetelmä on kuvattu menetelmäsivulla. "
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
    origin_box = KeepTogether(ob)

    # ---------------- Sivu 3: kapasiteettimittaus ----------------------
    if is_cap and cap:
        E.append(PageBreak())
        E.append(P("Kapasiteettimittaus", "h2"))
        E.append(P("Akku ladattiin matalasta varaustilasta täyteen. Akkuun mennyt energia on mitattu auton "
                   "akunhallinnan jännitteestä ja virrasta, joten laturin häviöt eivät vaikuta tulokseen.", "body"))
        E.append(Spacer(1, 4 * mm))
        cs_ = samples
        if tyyppi == "taysi":
            # Täydessä testissä latauksen kaavio alkaa lepojaksosta ennen latausta (ajo-osuus omalla sivullaan)
            cs_ = [x for x in samples if x.get("vaihe") in ("lepo_alku", "odota_lataus", "lataus", "lepo_loppu")] \
                or samples
        t0 = cs_[0]["t"] if cs_ else test["aloitettu"]
        if cs_:
            E.append(_img(charts.capacity_chart(cs_, t0), CW))
            E.append(Spacer(1, 3 * mm))
        if cap.get("valmis"):
            rows = [[P("Suure", "label"), P("Arvo", "label"), P("Peruste", "label")]]
            highlight = []

            rows_d = [[P("Vaihe", "label"), P("Arvo", "label"), P("Peruste", "label")]]

            def add(n, v, p="", strong=False):
                if strong:
                    highlight.append(len(rows))
                rows.append([P(n, "cellb" if strong else "cell"), P(v, "cellb"), P(p, "small")])

            def add_d(n, v, p=""):
                rows_d.append([P(n, "cell"), P(v, "cellb"), P(p, "small")])
            add("Varaustila latauksen alussa ja lopussa", f"{fmt(cap['soc_alku'])} % → {fmt(cap['soc_loppu'])} %",
                f"{_BRAND['gen']} akunhallinta" + ("; lataus valmis" if cap.get("taysi") else ""))
            add("Akkuun ladattu energia", f"{fmt(cap['e_napa_kwh'], 1)} kWh",
                f"Latauksen kesto {_dur(cap.get('lataus_kesto_s'))}")
            add("Akun kokonaiskapasiteetti", f"{fmt(cap['taysi_kwh'], 1)} kWh",
                f"Mittaustarkkuus ±{fmt(cap['epavarmuus_kwh'])} kWh", strong=True)
            if cap.get("kaytettava_kwh") is not None:
                add("Käytettävissä oleva energia", f"{fmt(cap['kaytettava_kwh'], 1)} kWh",
                    f"Suojavara {fmt(bms.get('puskuri_kwh'))} kWh vähennetty")
            if bms.get("nfp_kwh"):
                add("Vertailu: akunhallinnan oma arvio", f"{fmt(bms['nfp_kwh'], 1)} kWh",
                    f"Ero mitattuun {fmt(cap.get('ero_bms_pct'))} %; ei vaikuta tulokseen")
            add_d("Akkuun mennyt energia navoilta", f"{fmt(cap['e_napa_kwh'], 2)} kWh",
                  f"{_BRAND['gen']} latauslaskuri" if cap.get("laskuri_kaytetty") else "Akunhallinnan jännite ja virta, ∫ U · I dt")
            if cap.get("laskuri_kwh") and not cap.get("laskuri_kaytetty"):
                add_d(f"{_BRAND['gen']} latauslaskuri samalta ajalta", f"{fmt(cap['laskuri_kwh'], 2)} kWh",
                      f"Vertailu: ero {fmt(cap.get('laskuri_ero_pct'))} %")
            add_d("Latauksen keskiteho akkuun", f"{fmt(cap.get('keskiteho_kw'))} kW", "")
            add_d("Akun sisäinen resistanssi", f"{fmt(cap['r_ohm'] * 1000, 0)} mΩ" if cap.get("r_ohm") else "–",
                  "Jännitteen nousu latauksen alussa")
            add_d("Sisäiset häviöt latauksessa", f"{fmt(cap['e_haviot_kwh'], 2)} kWh", "R · ∫ I² dt")
            if cap.get("katkot_kwh"):
                add_d("Katkojen aikainen energia", f"{fmt(cap['katkot_kwh'], 2)} kWh", "Akunhallinnan energialaskuri")
            add_d("Varastoitunut energia mittausvälillä", f"{fmt(cap['e_kemia_kwh'], 2)} kWh", "")
            add_d("Energia lähtövarauksen alapuolella", f"{fmt(cap['e_alapuoli_kwh'], 2)} kWh",
                  "Mitattu Ah-kapasiteetti ja akkukemian lepojännitekäyrä")
            if cap.get("e_ylapuoli_kwh", 0) > 0.05:
                add_d("Energia loppuvarauksen yläpuolella", f"{fmt(cap['e_ylapuoli_kwh'], 2)} kWh", "Sama menetelmä")
            add_d("Akun kokonaiskapasiteetti", f"{fmt(cap['taysi_kwh'], 2)} kWh",
                  f"Mittaustarkkuus ±{fmt(cap['epavarmuus_kwh'], 2)} kWh")
            if cap.get("ocv_kwh"):
                add_d("Vertailuarvo lepojännitteistä", f"{fmt(cap['ocv_kwh'], 1)} kWh",
                      "Varaustila lepojännitteestä, ei akunhallinnasta. Suuntaa antava.")
            ct = _table(rows, [66 * mm, 30 * mm, CW - 96 * mm])
            for hr in highlight:
                ct.setStyle(TableStyle([("BACKGROUND", (0, hr), (-1, hr), PANEL)]))
            E.append(ct)
            A.append(P("Kapasiteettimittauksen vaiheet", "h2"))
            A.append(_table(rows_d, [66 * mm, 30 * mm, CW - 96 * mm]))

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
            A.append(KeepTogether([Spacer(1, 3 * mm), P("Mittauksen luotettavuus", "h3"), side]))
        if cs_:
            A.append(CondPageBreak(55 * mm))
            A.append(Spacer(1, 4 * mm))
            A.append(_img(charts.voltage_spread_chart(cs_, t0), CW))
            A.append(Spacer(1, 6 * mm))

    # ---------------- Purkumittaus (ajotestit ja täysi akkutesti) ------
    def result_table(rows_, highlight_):
        t_ = _table(rows_, [66 * mm, 30 * mm, CW - 96 * mm])
        for hr_ in highlight_:
            t_.setStyle(TableStyle([("BACKGROUND", (0, hr_), (-1, hr_), PANEL)]))
        return t_

    if purku.get("valmis"):
        E.append(PageBreak())
        E.append(P("Purkumittaus ajossa", "h2"))
        osat = purku.get("osat") or 1
        E.append(P(f"Ajossa akusta otettu energia on luettu {_BRAND['gen']} energialaskureista ja varaustila akunhallinnasta "
                   "levossa ennen ajoa ja sen jälkeen." + (
                       f" Mittaus koottiin {osat} ajokerrasta." if osat > 1 else ""), "body"))
        E.append(Spacer(1, 4 * mm))
        ds_ = [x for x in samples if x.get("vaihe") in ("lepo_ajo_alku", "ajo", "lepo_ajo_loppu")]
        if len(ds_) >= 10:
            E.append(_img(charts.drive_chart(ds_), CW))
            E.append(Spacer(1, 3 * mm))
        rows = [[P("Suure", "label"), P("Arvo", "label"), P("Peruste", "label")]]
        hl = []

        rows_d = [[P("Vaihe", "label"), P("Arvo", "label"), P("Peruste", "label")]]

        def addp(n, v, p="", strong=False):
            if strong:
                hl.append(len(rows))
            rows.append([P(n, "cellb" if strong else "cell"), P(v, "cellb"), P(p, "small")])

        def addp_d(n, v, p=""):
            rows_d.append([P(n, "cell"), P(v, "cellb"), P(p, "small")])
        addp("Varaustila ennen ajoa ja sen jälkeen", f"{fmt(purku['soc_alku'])} % → {fmt(purku['soc_loppu'])} %",
             f"{_BRAND['gen']} akunhallinta, levossa")
        if purku.get("matka_km"):
            addp("Ajettu matka", f"{fmt(purku['matka_km'], 0)} km",
                 f"Keskikulutus {fmt(purku['kulutus_wh_km'], 0)} Wh/km" if purku.get("kulutus_wh_km") else "")
        addp("Akusta otettu energia", f"{fmt(purku['netto_kwh'], 1)} kWh", f"{_BRAND['gen']} energialaskurit")
        pk_ok = not purku.get("hylatty") and tyyppi != "pika_ajo"
        addp("Akun kokonaiskapasiteetti", f"{fmt(purku['taysi_kwh'], 1)} kWh",
             f"Mittaustarkkuus ±{fmt(purku['epavarmuus_kwh'])} kWh", strong=pk_ok)
        if bms.get("nfp_kwh") and purku.get("ero_bms_pct") is not None:
            addp("Vertailu: akunhallinnan oma arvio", f"{fmt(bms['nfp_kwh'], 1)} kWh",
                 f"Ero mitattuun {fmt(purku['ero_bms_pct'])} %; ei vaikuta tulokseen")
        if purku.get("purku_kwh") is not None:
            addp_d("Akusta otettu energia", f"{fmt(purku['purku_kwh'], 2)} kWh", f"{_BRAND['gen']} elinkaaren purkulaskuri")
            addp_d("Jarrutuksissa palautunut energia", f"{fmt(purku['palautus_kwh'], 2)} kWh",
                   f"{_BRAND['gen']} elinkaaren latauslaskuri")
        addp_d("Nettoenergia navoilta", f"{fmt(purku['netto_kwh'], 2)} kWh", purku.get("lahde") or "")
        addp_d("Sisäiset häviöt ajossa", f"{fmt(purku['haviot_kwh'], 2)} kWh",
               f"R · ∫ I² dt, R = {fmt(purku.get('r_kaytetty_mohm'), 0)} mΩ")
        addp_d("Energia mittausvälin ulkopuolella", f"{fmt(purku['e_alapuoli_kwh'] + purku['e_ylapuoli_kwh'], 2)} kWh",
               "Mitattu Ah-kapasiteetti ja akkukemian lepojännitekäyrä")
        addp_d("Akun kokonaiskapasiteetti", f"{fmt(purku['taysi_kwh'], 2)} kWh",
               f"Mittaustarkkuus ±{fmt(purku['epavarmuus_kwh'], 2)} kWh")
        E.append(result_table(rows, hl))
        if tyyppi == "pika_ajo":
            E.append(Spacer(1, 2 * mm))
            E.append(P(f"Pika-ajotesti tarkistaa {_BRAND['gen']} akunhallinnan ilmoittaman kapasiteetin. Lyhyen ajon tulosta "
                       "ei käytetä akun kuntoprosenttina.", "small"))
        A.append(P("Purkumittauksen vaiheet", "h2"))
        A.append(_table(rows_d, [66 * mm, 30 * mm, CW - 96 * mm]))
        qrows = [[P("Tarkistus", "label"), P("Tulos", "label"), P("", "label")]]
        for q in purku.get("laatu", []):
            qrows.append([P(q["nimi"], "cell"), P(q["arvo"], "cell"), Pill("Kunnossa" if q["ok"] else "Huomioitava")])
        qrows.append([P("Kokonaisarvio", "cellb"), P(purku.get("laatu_luokka"), "cellb"), ""])
        uo = purku.get("epavarmuus_osat", {})
        urows = [[P("Epävarmuuden osa", "label"), P("kWh", "label")]]
        for k, label in (("laskurit", "Energialaskurit (1 %)"), ("varaustila", "Varaustilan lukema"),
                         ("haviot", "Häviöiden korjaus"), ("ekstrapolointi", "Mittausvälin ulkopuolinen osuus"),
                         ("jannitekayra", "Lepojännitekäyrä")):
            if uo.get(k) is not None:
                urows.append([P(label, "cell"), P(fmt(uo[k], 2), "cellr")])
        urows.append([P("Yhdistetty epävarmuus", "cellb"), P(fmt(purku["epavarmuus_kwh"], 2), "cellr")])
        side = Table([[_table(qrows, [44 * mm, 24 * mm, 22 * mm]), _table(urows, [CW - 90 * mm - 26 * mm, 18 * mm])]],
                     colWidths=[92 * mm, CW - 92 * mm], hAlign="LEFT")
        side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        A.append(KeepTogether([Spacer(1, 3 * mm), P("Mittauksen luotettavuus", "h3"), side]))
        A.append(Spacer(1, 6 * mm))

    if yhd.get("valmis"):
        E.append(Spacer(1, 6 * mm))
        rows = [[P("Mittaus", "label"), P("Kapasiteetti", "label"), P("Mittaustarkkuus", "label")],
                [P("Lataus täyteen", "cell"), P(f"{fmt(yhd['lataus_kwh'], 1)} kWh", "cellb"),
                 P(f"±{fmt(cap.get('epavarmuus_kwh'))} kWh", "cell")],
                [P("Purku ajossa", "cell"), P(f"{fmt(yhd['purku_kwh'], 1)} kWh", "cellb"),
                 P(f"±{fmt(purku.get('epavarmuus_kwh'))} kWh", "cell")],
                [P("Tulos", "cellb"), P(f"{fmt(yhd['taysi_kwh'], 1)} kWh", "cellb"),
                 P(f"±{fmt(yhd['epavarmuus_kwh'])} kWh", "cellb")]]
        vt = _table(rows, [66 * mm, 40 * mm, CW - 106 * mm])
        vt.setStyle(TableStyle([("BACKGROUND", (0, 3), (-1, 3), PANEL)]))
        txt = (f"Lataus- ja purkumittauksen ero on {fmt(yhd['ero_kwh'], 2)} kWh ({fmt(yhd['ero_pct'])} %). "
               + ("Kaksi toisistaan riippumatonta mittausta vahvistaa tuloksen."
                  if yhd["yhtapitavat"] else
                  "Ero on suurempi kuin mittaustarkkuus selittää, joten tuloksena käytetään latausmittausta."))
        E.append(KeepTogether([P("Lataus- ja purkumittauksen vertailu", "h3"), vt, Spacer(1, 2 * mm),
                               P(txt, "small")]))

    # ---------------- Kuormitus ------------------------------------------
    if kuorma:
        E.append(PageBreak())
        E.append(P("Kennoryhmät kuormassa", "h2"))
        E.append(P("Kun akusta otetaan suuri virta, kunkin kennoryhmän jännite laskee sen sisäisen resistanssin "
                   "mukaan. Resistanssi määritettiin jokaiselle kennoryhmälle sen jännitteen ja samanaikaisen "
                   "akun virran riippuvuudesta. Muita selvästi suurempi resistanssi viittaa heikentyneeseen "
                   "kennoryhmään tai liitokseen.", "body"))
        E.append(Spacer(1, 3 * mm))
        vals = kuorma.get("ryhmat_mohm") or []
        if any(vals):
            med_ = kuorma.get("r_mediaani_mohm") or 1
            devs = [((x / med_ - 1) * 100) if x else None for x in vals]
            E.append(_img(charts.group_bar_chart(
                devs, "Kennoryhmien sisäinen resistanssi suhteessa mediaaniin", "Poikkeama (%)",
                highlight=[p["nro"] for p in kuorma.get("poikkeavat", [])], center=True, decimals=0,
                min_lim=30.0), CW))
            E.append(P(f"Nollataso on kaikkien kennoryhmien mediaani ({fmt(med_, 3)} mΩ). Korostetut ryhmät "
                       "poikkeavat mediaanista vähintään 20 %.", "small"))
            E.append(Spacer(1, 3 * mm))
        rows = [[P("Suure", "label"), P("Arvo", "label"), P("Selite", "label")]]

        def addk(n, v, p=""):
            rows.append([P(n, "cell"), P(v, "cellb"), P(p, "small")])
        addk("Akun sisäinen resistanssi", f"{fmt(kuorma['r_akku_mohm'], 0)} mΩ", "Kennoryhmien resistanssien summa")
        addk("Kennoryhmän resistanssi, mediaani", f"{fmt(kuorma['r_mediaani_mohm'], 3)} mΩ", "")
        addk("Suurin resistanssi", f"{fmt(kuorma['r_max_mohm'], 3)} mΩ",
             f"Ryhmä {kuorma['r_max_nro']}, {fmt(kuorma['hajonta_pct'], 0)} % yli mediaanin")
        addk("Poikkeavat ryhmät", ", ".join(f"{p['nro']} (+{fmt(p['poikkeama_pct'], 0)} %)"
                                            for p in kuorma.get("poikkeavat", [])) or "Ei havaittu",
             "Vähintään 20 % yli mediaanin")
        if kuorma.get("teho_max_kw"):
            addk("Suurin teho akusta", f"{fmt(kuorma['teho_max_kw'], 0)} kW", "Mittauksen aikana")
        if kuorma.get("talteenotto_max_kw"):
            addk("Suurin jarrutusteho akkuun", f"{fmt(kuorma['talteenotto_max_kw'], 0)} kW", "")
        pj = kuorma.get("pienin_jannite_kuormassa")
        if pj:
            addk("Pienin kennoryhmän jännite kuormassa", f"{fmt(pj['v'], 3)} V",
                 f"Ryhmä {pj['nro']}, virta {fmt(pj['virta_a'], 0)} A")
        addk("Luokka", kuorma.get("luokka") or "–", "Suurimman resistanssin poikkeama mediaanista")
        E.append(KeepTogether(_table(rows, [66 * mm, 40 * mm, CW - 106 * mm])))

    # ---------------- Pikalataus -----------------------------------------
    if dc:
        E.append(PageBreak())
        E.append(P("Pikalataus", "h2"))
        E.append(P("Pikalatauksen aikana tallennettiin latausteho, varaustila, akun lämpötila ja kennoryhmien "
                   "välinen jännite-ero. Latausteho laskee varaustilan noustessa akunhallinnan ohjaamana. "
                   "Tehoon vaikuttavat myös akun lämpötila ja laturin oma enimmäisteho.", "body"))
        E.append(Spacer(1, 3 * mm))
        if len(dc.get("kayra") or []) >= 3:
            E.append(_img(charts.dc_chart(dc["kayra"]), CW))
            E.append(Spacer(1, 3 * mm))
        rows = [[P("Suure", "label"), P("Arvo", "label"), P("Selite", "label")]]

        def addd(n, v, p=""):
            rows.append([P(n, "cell"), P(v, "cellb"), P(p, "small")])
        addd("Huipputeho", f"{fmt(dc['huipputeho_kw'], 0)} kW", f"Varaustilassa {fmt(dc['huippu_soc'], 0)} %")
        addd("Varaustila alussa ja lopussa", f"{fmt(dc['soc_alku'])} % → {fmt(dc['soc_loppu'])} %", "")
        addd("Ladattu energia akkuun", f"{fmt(dc['energia_kwh'], 1)} kWh", dc.get("energia_lahde") or "")
        addd("Kesto ja keskiteho", f"{fmt(dc['kesto_min'], 0)} min, {fmt(dc.get('keskiteho_kw'), 0)} kW", "")
        if dc.get("aika_20_80_min"):
            addd("Lataus 20 → 80 %", f"{fmt(dc['aika_20_80_min'], 0)} min", "")
        if dc.get("lampotila_alku") is not None:
            addd("Akun lämpötila", f"{fmt(dc['lampotila_alku'])} → {fmt(dc['lampotila_max'])} °C", "Alussa ja enimmillään")
        if dc.get("jannite_ero_max_mv") is not None:
            addd("Suurin jännite-ero latauksessa", f"{fmt(dc['jannite_ero_max_mv'], 0)} mV",
                 f"Luokka: {(dc.get('luokka') or '–').lower()}"
                 + (f", {dc['jannite_ero_alue']}" if dc.get("jannite_ero_alue") else ""))
        E.append(KeepTogether(_table(rows, [66 * mm, 40 * mm, CW - 106 * mm])))

    # ---------------- Itsepurkautuminen ----------------------------------
    if itse:
        E.append(PageBreak())
        E.append(P("Itsepurkautuminen", "h2"))
        E.append(P(f"Kennoryhmien lepojännitteet luettiin seisonnan alussa ja {fmt(itse['tunnit'], 1)} tunnin "
                   "kuluttua. Sarjaan kytkettyjen ryhmien varaus muuttuu seisonnassa yhtä paljon, joten muita "
                   "nopeammin laskeva jännite viittaa kennoryhmän sisäiseen vuotoon. Jännitteen muutos on muunnettu "
                   "varauksen muutokseksi akkukemian lepojännitekäyrän avulla.", "body"))
        E.append(Spacer(1, 3 * mm))
        slope_ = itse.get("jyrkkyys_mv_pct") or 1.0
        lim_p = itse.get("raja_pct_vrk") or (itse["raja_mv_vrk"] / slope_)
        det_p = itse.get("havaitsemisraja_pct_vrk") or lim_p
        E.append(_img(charts.group_bar_chart(
            [(x / slope_) if x is not None else None for x in itse["suhteellinen_mv_vrk"]],
            "Varauksen muutos suhteessa muihin kennoryhmiin", "%-yks. / vrk",
            highlight=[p["nro"] for p in itse.get("poikkeavat", [])], center=True, decimals=2,
            min_lim=2 * max(lim_p, det_p)), CW))
        E.append(P(f"Korostetut ryhmät purkautuvat muita nopeammin enemmän kuin mittauksen havaitsemisraja "
                   f"({fmt(det_p, 2)} %-yks./vrk).", "small"))
        E.append(Spacer(1, 3 * mm))
        rows = [[P("Suure", "label"), P("Arvo", "label"), P("Selite", "label")]]

        def addi(n, v, p=""):
            rows.append([P(n, "cell"), P(v, "cellb"), P(p, "small")])
        addi("Seisonta-aika", f"{fmt(itse['tunnit'], 1)} h", "")
        addi("Varaustila", f"{fmt(itse.get('soc_alku'))} % → {fmt(itse.get('soc_loppu'))} %", "Akunhallinta")
        addi("Jännitteen muutos, mediaani", f"{_signed(itse['muutos_mediaani_mv'])} mV", "Kaikkien ryhmien yhteinen muutos")
        addi("Eniten poikkeava ryhmä", f"{itse['heikoin_nro']}",
             f"{fmt(itse.get('heikoin_pct_vrk', itse['heikoin_mv_vrk'] / slope_), 2)} %-yks./vrk "
             f"({fmt(itse['heikoin_mv_vrk'], 2)} mV/vrk) suhteessa muihin")
        addi("Havaitsemisraja", f"{fmt(det_p, 2)} %-yks./vrk",
             f"Pienin luotettavasti havaittava poikkeama. Arviointiraja {fmt(lim_p, 1)} %-yks./vrk.")
        addi("Poikkeavat ryhmät", ", ".join(str(p["nro"]) for p in itse.get("poikkeavat", [])) or "Ei havaittu", "")
        if itse.get("seisonta_w") is not None:
            addi("Auton energiankulutus seisonnassa", f"{fmt(itse['seisonta_w'], 0)} W",
                 f"{fmt(itse['seisonta_kwh'], 2)} kWh, {_BRAND['gen']} energialaskurit")
        addi("Luokka", itse.get("luokka") or "Ei arvioitu", "" if itse.get("luokka") else "Mittaus ei ollut riittävän tarkka")
        E.append(KeepTogether(_table(rows, [66 * mm, 40 * mm, CW - 106 * mm])))

    # ---------------- Kennoryhmät --------------------------------------
    if cs:
        E.append(CondPageBreak(150 * mm) if tyyppi in ("ajotesti", "pika_ajo") else PageBreak())
        E.append(Spacer(1, 4 * mm))
        E.append(P("Kennoryhmät", "h2"))
        E.append(P(f"Akussa on {cs['lkm']} sarjaan kytkettyä kennoryhmää. Kunkin ryhmän jännite on luettu "
                   "akunhallinnasta. Levossa mitattu jännite-ero kertoo, kuinka tasaisesti kennoryhmät ovat "
                   "varautuneet. Suuri yksittäinen poikkeama voi viitata heikentyneeseen ryhmään.", "body"))
        E.append(Spacer(1, 3 * mm))
        layout = (charts.module_layout(veh.get("malli"), len(cs["jannitteet"]))
                  if s.get("kennokuvaaja") == "moduulit" else None)

        def main_cell_chart(stats, title):
            if layout and len(stats["jannitteet"]) == sum(layout):
                return charts.module_chart(stats["jannitteet"], layout, title, poikkeavat=stats["poikkeavat"])
            return charts.cell_chart(stats["jannitteet"], title, poikkeavat=stats["poikkeavat"])

        E.append(_img(main_cell_chart(cs, r.get("kennot_otsikko", "Kennoryhmät")), CW))
        low = r.get("kennot_matala")
        if low:
            E.append(Spacer(1, 2 * mm))
            drive = test.get("tyyppi") in ("ajotesti", "pika_ajo")
            E.append(_img(main_cell_chart(low, "Kennoryhmät matalassa varauksessa ajon jälkeen" if drive
                                          else "Kennoryhmät matalassa varauksessa ennen latausta"), CW))
        E.append(Spacer(1, 3 * mm))
        rows = [[P("Tunnusluku", "label"), P(r.get("kennot_otsikko", ""), "label")]]
        drive = test.get("tyyppi") in ("ajotesti", "pika_ajo")
        hdr = [P("Tunnusluku", "label"), P(("Ennen ajoa" if drive else "Täyden latauksen jälkeen") if low
                                         else "Mittaushetkellä", "label")]
        if low:
            hdr.append(P("Ajon jälkeen" if drive else "Matalassa varauksessa", "label"))
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

    # ---------------- Vertailu ajomäärään ja aiemmat mittaukset ------
    hist = [t for t in storage.tests(test["vehicle_id"]) if t["tila"] == "valmis" and t["tulos"]
            and (t["tulos"].get("yhteenveto") or {}).get("kunto_pct") and t["mittarilukema"]]
    pts = sorted({(t["mittarilukema"], t["tulos"]["yhteenveto"]["kunto_pct"]) for t in hist})
    if len({km for km, _ in pts}) >= 2:
        E.append(CondPageBreak(70 * mm))
        E.append(Spacer(1, 4 * mm))
        E.append(_img(charts.trend_chart(pts), CW))

    # ---------------- Jännite-ero varaustilan mukaan --------------------
    from .analysis import spread_by_soc
    sp = spread_by_soc(samples, veh.get("kemia")) if test.get("tyyppi") in (
        "taysi", "kapasiteetti", "ajotesti", "pika_ajo", "pikalataus") else None
    if sp:
        A.append(CondPageBreak(120 * mm))
        A.append(Spacer(1, 6 * mm))
        A.append(P("Kennoryhmien jännite-ero varaustilan mukaan", "h2"))
        lfp = veh.get("kemia") == "LFP"
        A.append(P("Kuvaaja näyttää kennoryhmien suurimman ja pienimmän jännitteen eron koko mittauksen ajalta "
                   "varaustilan mukaan, erikseen latauksessa ja ajossa. Arvot ovat kahden prosenttiyksikön "
                   "välein laskettuja mediaaneja. Jännitekäyrän jyrkällä alueella ero kasvaa luonnostaan, koska pienikin ero "
                   "kennoryhmien varauksessa näkyy siellä suurena jännite-erona. "
                   + ("LFP-akun jännite on keskivarauksella lähes tasainen ja muuttuu jyrkästi sekä tyhjän että "
                      "täyden lähellä, joten ero kasvaa kummassakin päässä. Se on akkukemian ominaisuus eikä vika. "
                      if lfp else "")
                   + "Virran aikana mitattu ero on suurempi kuin levossa, joten akun luokitus tehdään levossa "
                   "mitatuista arvoista. Ajosta on otettu mukaan vain tasainen ajo (akun virta enintään 80 A), "
                   "jotta kiihdytykset ja ajotyyli eivät vaikuta kuvaan.", "body"))
        A.append(Spacer(1, 2 * mm))
        A.append(_img(charts.spread_soc_chart(sp), CW))
        rows_s = [[P("Varausalue", "label"), P("Pienin ero", "label"), P("Keskimäärin", "label"),
                   P("Suurin ero", "label"), P("", "label")]]
        for a_ in sp["alueet"]:
            rows_s.append([P(a_["alue"], "cell"), P(f"{fmt(a_['pienin_mv'], 0)} mV", "cellr"),
                           P(f"{fmt(a_['ka_mv'], 0)} mV", "cellr"), P(f"{fmt(a_['suurin_mv'], 0)} mV", "cellr"),
                           P("Jyrkkä alue" if a_["jyrkka"] else "Tasainen alue" if lfp else "", "cell")])
        A.append(Spacer(1, 2 * mm))
        A.append(_table(rows_s, [40 * mm, 28 * mm, 28 * mm, 28 * mm, CW - 124 * mm]))

    # ---------------- Akunhallinta ja elinkaari -----------------------
    A.append(CondPageBreak(90 * mm))
    A.append(Spacer(1, 6 * mm))
    A.append(P("Akunhallinnan tiedot", "h2"))
    lt = r.get("elinkaari") or {}
    tt = r.get("lampotilat") or {}
    rows = [[P("Tieto", "label"), P("Arvo", "label"), P("Selite", "label")]]

    def add(n, v, p=""):
        rows.append([P(n, "cell"), P(v, "cellb"), P(p, "small")])
    add("Täyden akun energia", f"{fmt(bms.get('nfp_kwh'))} kWh" if bms.get("nfp_kwh") else "–",
        "Akunhallinnan ilmoittama akun nykyinen kokonaisenergia")
    add("Alkuperäinen energia", f"{fmt(r['viite']['kwh'])} kWh" if r["viite"]["kwh"] else "–", r["viite"]["lahde"])
    if bms.get("soh_pct"):
        add("Kunto akunhallinnan mukaan", f"{fmt(bms['soh_pct'])} %", "Täyden akun energia / alkuperäinen energia")
    if _polled:
        add("Suojavara", "Ei ilmoiteta", f"{_BRAND['gen']} akunhallinta ei ilmoita suojavaraa")
    else:
        add("Suojavara", f"{fmt(bms.get('puskuri_kwh'), 2)} kWh" if bms.get("puskuri_kwh") is not None else "–",
            "Energia, jota ei näytetä käyttäjälle")
        add("Käytettävä energia", f"{fmt(bms.get('kaytettava_kwh'))} kWh" if bms.get("kaytettava_kwh") else "–",
            "Täyden akun energia vähennettynä suojavaralla")
    add("Varaustila (näytöllä)", f"{fmt(bms.get('soc_ui'))} %" if bms.get("soc_ui") is not None else "–",
        "Mittauksen lopussa")
    add("Varaustila (kennojen keskiarvo)", f"{fmt(bms.get('soc_avg'))} %" if bms.get("soc_avg") is not None else "–",
        f"Vaihteluväli {fmt(bms.get('soc_min'))}–{fmt(bms.get('soc_max'))} %"
        if (bms.get("soc_min") is not None and bms.get("soc_max") is not None) else "Kennoryhmien keskiarvo")
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
    A.append(_table(rows, [62 * mm, 34 * mm, CW - 96 * mm]))

    # ---------------- Menetelmä ja tietolähteet -----------------------
    A.append(PageBreak())
    A.append(P("Menetelmä ja tietolähteet", "h2"))
    A.append(origin_box)
    A.append(Spacer(1, 5 * mm))
    meth = [
        ("Tiedonkeruu", ("Tiedot luettiin auton akunhallinnalta diagnostiikkaliitännän kautta. Ohjelma lähettää "
         "akunhallinnalle vain lukukyselyjä eikä muuta auton asetuksia. Kyselyt ja vastausten sisältö perustuvat "
         f"{_polled.LAHDE}.") if _polled else (
         "Tiedot luettiin auton CAN-väylältä diagnostiikkaliitännän kautta. Ohjelma ainoastaan kuuntelee "
         "väylää eikä lähetä autolle viestejä tai muuta sen asetuksia. Viestien sisältö puretaan avoimien, "
         "Tesla-omistajien yhteisön ylläpitämien viestimäärittelyjen mukaisesti" + (
             " (Model S 2012–2021 / Model X 2015–2021: Open Vehicle Monitoring System ja Battery-Emulator)."
             if veh.get("alusta") == "sx" else " (Model 3 DBC ja Battery-Emulator)."))),
        ("Alkuperäinen kapasiteetti", "Akun alkuperäinen energia luetaan ensisijaisesti akunhallinnasta, joka "
         "tallentaa sen akun valmistuksen yhteydessä. Jos arvoa ei saada, käytetään käyttäjän ilmoittamaa arvoa "
         "tai mallitaulukon likiarvoa, joka valitaan valmistenumeron (vuosimalli, tehdas, voimalinja) ja "
         "kennoryhmien määrän perusteella. Käytetty lähde näkyy raportissa."),
        ("Akun kunto (SOH)", "Kunto on akun nykyinen kokonaiskapasiteetti jaettuna alkuperäisellä "
         "kapasiteetilla. Pikatarkastuksessa nykyinen kapasiteetti on akunhallinnan oma arvio. "
         "Kapasiteettimittauksessa se on mitattu latauksen aikana, ajotesteissä ajon aikana ja täydessä "
         "akkutestissä molemmilla tavoilla."),
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
    if purku.get("valmis"):
        meth += [
            ("Purkumittaus", f"Ajon aikana akusta otettu energia luetaan {_BRAND['gen']} elinkaaren energialaskureista, "
             "joista vähennetään jarrutuksissa akkuun palautunut energia. Akun sisäiset häviöt (R · ∫ I² dt) "
             "lisätään, jolloin saadaan akusta purkautunut energia. Varaustilan muutos luetaan akunhallinnasta "
             "levossa ennen ajoa ja sen jälkeen. Ampeerituntikapasiteetti ja akkukemian lepojännitekäyrä antavat "
             "koko akun kapasiteetin. Mittaus voidaan koota useasta ajokerrasta."),
        ]
    if yhd.get("valmis"):
        meth += [
            ("Täysi akkutesti", "Kapasiteetti mitataan kahdesti toisistaan riippumattomasti: purkamalla ajossa ja "
             "lataamalla täyteen. Jos tulokset ovat yhtäpitävät kaksinkertaisen yhdistetyn epävarmuuden rajoissa, "
             "tulos on niiden epävarmuuksilla painotettu keskiarvo. Muuten käytetään latausmittausta."),
        ]
    if kuorma:
        meth += [
            ("Kennoryhmien resistanssi", "Jokaisen kennoryhmän jännite ja samanhetkinen akun virta tallennetaan "
             "kuormituksen aikana. Ryhmän sisäinen resistanssi on jännitteen ja virran välisen suoran kulmakerroin "
             "(pienimmän neliösumman menetelmä). Luokat suurimman resistanssin poikkeamalle mediaanista: enintään "
             "10 % erinomainen, 20 % hyvä, 35 % tyydyttävä."),
        ]
    if dc:
        meth += [
            ("Pikalataus", "Latausteho lasketaan akunhallinnan jännitteestä ja virrasta kymmenen sekunnin välein. "
             "Kennoryhmien jännite-ero huomioidaan vain tasaisen tehon kohdista, LFP-akulla vain 20–90 %:n varauksessa. "
             "Jännite-eron luokat: alle 50 mV erinomainen, alle 80 mV hyvä, alle 120 mV tyydyttävä."),
        ]
    if itse:
        meth += [
            ("Itsepurkautuminen", "Kennoryhmien lepojännitteet keskiarvoistetaan seisonnan alussa ja lopussa. "
             "Kunkin ryhmän muutoksesta vähennetään kaikkien ryhmien mediaanimuutos, jolloin auton oma kulutus "
             "ja varaustilan lasku eivät vaikuta tulokseen. Jännitteen muutos muunnetaan varauksen muutokseksi "
             "vuorokaudessa akkukemian lepojännitekäyrän jyrkkyydellä. Poikkeavaksi merkitään ryhmä, jonka muutos "
             "ylittää 0,3 %-yksikköä vuorokaudessa ja mittauksen havaitsemisrajan. Havaitsemisraja lasketaan "
             "jännitelukemien hajonnasta ja näytteiden määrästä, joten mittauskohinaa ei tulkita vuodoksi."),
        ]
    meth += [
        ("Kennoryhmät", f"Kennoryhmien jännitteet luetaan akunhallinnasta {fmt(veh['kenno_resoluutio_mv'], 0) + ' mV' if veh.get('kenno_resoluutio_mv') else '0,1 mV'}:n tarkkuudella. Poikkeavaksi "
         "merkitään ryhmä, jonka jännite eroaa mediaanista yli puolet hyvän rajasta tai yli nelinkertaisesti "
         "tavanomaisen hajonnan verran. Jännite-eron luokat levossa: alle 15 mV erinomainen, alle 30 mV hyvä, "
         "alle 50 mV tyydyttävä. Raja-arvot perustuvat käytettyjen sähköautojen akkutestien aineistoon (Generational, "
         "noin 10 000 testiä: tyypillinen ero noin 8 mV, yli 50 mV vaatii selvittelyä, yli 100 mV viittaa vikaan) "
         "sekä akkujärjestelmien täyden latauksen ohjearvoihin (enintään 30 mV hyväksyttävä, vähintään 50 mV vaatii "
         "tasauslatauksen). Jännitekäyrän jyrkällä alueella kennoryhmien ero on luonnostaan suurempi: alle 20 %:n "
         "varauksessa ja LFP-akulla myös vähintään 95 %:n varauksessa käytetään rajoja alle 50 mV hyvä ja alle "
         "100 mV tyydyttävä. LFP-akun jännite on keskivarauksella lähes tasainen, joten pieni ero ei siellä yksin "
         "todista tasapainoa, ja luokaksi annetaan enintään hyvä."),
        ("Kunnon luokitus", "Vähintään 90 % erinomainen, 80–90 % hyvä, 70–80 % heikentynyt (luokat AVILOOn käytännön "
         "mukaan). "
         + (f"{_BRAND['gen']} akkutakuu kattaa kapasiteetin laskun alle {(r.get('takuu') or {}).get('sailyvyys_pct') or 70} %:n "
            "takuuaikana.")),
        *([("Vertailu ajomäärään", "Vertailukäyrä perustuu Teslan vaikuttavuusraportissa (Impact Report 2023) "
            "julkaistuun keskiarvoon, jonka mukaan Model 3- ja Model Y -akkujen kapasiteetti on alentunut noin "
            "15 % ja Model S- ja Model X -akkujen noin 12 % noin 320 000 km:n jälkeen.")] if brand == "Tesla" else []),
        ("Tietojen eheys", "Kaikki mittauksen aikana vastaanotetut viestit tallennetaan muuttamattomina "
         "raakadatatiedostoon. Tiedoston SHA-256-tarkiste on alla. Tarkisteen avulla voidaan todentaa, että "
         "raportti on laskettu juuri tästä aineistosta."),
    ]
    for head, txt in meth:
        A.append(KeepTogether([P(head, "h3"), P(txt, "body")]))

    A.append(P("Mittauksen tiedot", "h3"))
    info = r.get("meta", {}).get("sovitin") or {}
    A.append(_kv([
        ("Ohjelma", f"{NIMI} {VERSIO}" + (f" (mittaus tallennettu versiolla {r.get('mittausversio') or r['versio']})"
                                      if (r.get("mittausversio") or r.get("versio")) not in (None, VERSIO) else "")),
        *([("Tuloksen laskenta", f"Laskettu uudelleen versiolla {r['versio']} samasta mittausdatasta"
            + (f" (aiempi laskenta versiolla {r['aiempi_laskenta']['versio']})"
               if (r.get("aiempi_laskenta") or {}).get("versio") else ""))]
          if r.get("aiempi_laskenta") else []),
        *([("Mittauksen alkuperä", f"Osa täyttä akkutestiä nro {r['osa_testista']}, sama mittausdata")]
          if r.get("osa_testista") else []),
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
    tail = []
    if events:
        t0 = events[0]["t"]
        rows = [[P("Aika", "label"), P("Tapahtuma", "label")]]
        for ev in events:
            rows.append([P(_dur(ev["t"] - t0) if ev["t"] - t0 >= 60 else "0 min", "small"), P(ev["teksti"], "smallink")])
        tail += [P("Tapahtumat", "h3"), _table(rows, [24 * mm, CW - 24 * mm])]
    tail += [Spacer(1, 5 * mm), P("Raportti perustuu mittaushetken tietoihin. Akun kunto voi muuttua käytön ja ajan "
                                  "myötä. Raportti ei ole valmistajan takuulausunto.", "small")]
    # Lyhyt tapahtumaluettelo pidetään yhtenäisenä; pitkä saa jatkua seuraavalle sivulle
    A.extend([KeepTogether(tail)] if len(events) <= 25 else tail)

    # ---------------- Sanasto ------------------------------------------
    from .docs import SANASTO
    A.append(PageBreak())
    A.append(P("Sanasto", "h2"))
    A.append(_table([[P(a, "cellb"), P(b, "cell")] for a, b in SANASTO], [50 * mm, CW - 50 * mm], header=False,
                    valign="TOP"))

    if liite and A:
        E.append(PageBreak())
        E.append(P("Tekninen liite", "h1"))
        E.append(P("Liitteessä on mittauksen vaiheet ja mittaustarkkuuden erittely, akunhallinnan tiedot sekä "
                   "menetelmän ja tietolähteiden kuvaus.", "sub"))
        E.append(Spacer(1, 6 * mm))
        while A and isinstance(A[0], (PageBreak, CondPageBreak)):
            A.pop(0)
        E.extend(A)
    doc.build(E, canvasmaker=_numbered_canvas(ctx["report_no"]))
    return out_path


def _numbered_canvas(report_no: str):
    """Sivunumero muodossa "Raportti 2026-00001 · Sivu 3/14": irrallinen sivu yhdistyy raporttiin ja
    puuttuva sivu huomataan."""
    from reportlab.pdfgen.canvas import Canvas

    class NumberedCanvas(Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._pages)
            for st in self._pages:
                self.__dict__.update(st)
                self.saveState()
                self.setFont("Inter", 6.8)
                self.setFillColor(MUTED)
                self.drawRightString(W - M, 10 * mm, f"Testi nro {report_no}  ·  Sivu {self._pageNumber}/{n}")
                self.restoreState()
                super().showPage()
            super().save()

    return NumberedCanvas
