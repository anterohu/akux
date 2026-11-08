"""AKVERI-merkin kuvakkeet: Windowsin akux.ico ja Androidin käynnistyskuvakkeet.

Merkki: valkoinen ympyrä, tummansininen reunus, pisteviivarengas sekä A-kirjain vihreällä poikkiviivalla.
Ajo: python tools/tee_kuvakkeet.py   (vaatii Playwrightin ja Pillow'n)
"""
import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
NAVY, GREEN = "#1F4E79", "#6CC193"


def mark_svg(size: int) -> str:
    # Pienissä koossa pisteviiva jätetään pois, jotta merkki pysyy selkeänä
    dots = size >= 48
    ring = 7 if size < 32 else 6
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 100 100">
<circle cx="50" cy="50" r="{50 - ring / 2 - 0.5}" fill="#fff" stroke="{NAVY}" stroke-width="{ring}"/>
{f'<circle cx="50" cy="50" r="37" fill="none" stroke="{NAVY}" stroke-opacity=".38" stroke-width="1.8" stroke-dasharray="2 4"/>' if dots else ''}
<path d="M33 71 L50 28 L67 71" fill="none" stroke="{NAVY}" stroke-width="{10 if size < 32 else 9}" stroke-linejoin="round" stroke-linecap="round"/>
<line x1="40.5" y1="57" x2="59.5" y2="57" stroke="{GREEN}" stroke-width="{9 if size < 32 else 7.5}" stroke-linecap="round"/>
</svg>"""


def render(page, size: int) -> Image.Image:
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(f"<html><body style='margin:0;background:transparent'>{mark_svg(size)}</body></html>")
    png = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": size, "height": size})
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        ico_sizes = [16, 24, 32, 48, 64, 128, 256]
        imgs = {s: render(page, s) for s in ico_sizes}
        imgs[256].save(ROOT / "akux.ico", sizes=[(s, s) for s in ico_sizes],
                       append_images=[imgs[s] for s in ico_sizes if s != 256])
        for d, s in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
            # Androidin käynnistyskuvake: merkki pienellä reunuksella
            canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            inner = render(page, round(s * 0.92))
            canvas.paste(inner, ((s - inner.width) // 2, (s - inner.height) // 2), inner)
            canvas.save(ROOT / f"android/app/src/main/res/mipmap-{d}/ic_launcher.png")
        b.close()
    print("Kuvakkeet päivitetty")


if __name__ == "__main__":
    sys.exit(main())
