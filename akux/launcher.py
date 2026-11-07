"""Sovelluksen käynnistin (Akux.exe).

- Avaa käyttöliittymän omaan sovellusikkunaansa. Windowsissa ikkuna käyttää Windowsin
  WebView2-näyttökomponenttia (pywebview), joten selainta ei avata. Jos komponentti
  puuttuu, käyttöliittymä avataan Edgen tai Chromen sovellustilaan.
- Jos ohjelma on jo käynnissä, avaa vain uuden ikkunan.
- Sulkeutuu itsestään, kun ikkuna on suljettu eikä mittausta ole käynnissä.
  Käynnissä oleva mittaus jatkuu, vaikka ikkunan sulkee.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

PORT = 8765
IDLE_EXIT_S = 90


def _running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tila", timeout=1.5) as r:
            return json.load(r).get("nimi") == "Akux"
    except Exception:  # noqa: BLE001
        return False


def _browser() -> str | None:
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe",
                      Path(base) / "Google/Chrome/Application/chrome.exe"]
    for c in cands:
        if c.exists():
            return str(c)
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def open_window(url: str):
    exe = _browser()
    if exe:
        profile = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Akux" / "ikkuna"
        profile.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1320,880",
                              f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check"],
                             close_fds=True)
            return
        except OSError:
            pass
    import webbrowser
    webbrowser.open(url)


LATAUS_HTML = """<!doctype html><html lang="fi"><head><meta charset="utf-8"><title>Akux</title>
<style>html,body{height:100%;margin:0;font-family:Segoe UI,system-ui,sans-serif;background:#F5F6F8;color:#1B2430}
body{display:flex;align-items:center;justify-content:center}div{text-align:center}b{font-size:20px}
p{color:#6B7480;font-size:13px}@media(prefers-color-scheme:dark){html,body{background:#12171E;color:#E6E9EE}}</style>
</head><body><div><b>Akux</b><p>Käynnistetään…</p></div></body></html>"""


def _webview():
    """pywebview, jos Windowsin WebView2-ikkuna on käytettävissä."""
    if os.environ.get("AKUX_SELAINIKKUNA") == "1":
        return None
    if not sys.platform.startswith("win") and os.environ.get("AKUX_WEBVIEW") != "1":
        return None
    try:
        import webview  # noqa: PLC0415
        return webview
    except Exception:  # noqa: BLE001
        return None


class IkkunaApi:
    """Käyttöliittymän kutsut sovellusikkunasta: tiedostojen avaus ja tallennus sekä sulkeminen."""

    def __init__(self, base: str):
        self._base = base
        self._window = None

    def _fetch(self, path: str):
        if not path.startswith("/api/"):
            raise ValueError("Virheellinen osoite")
        with urllib.request.urlopen(self._base + path, timeout=300) as r:
            cd = r.headers.get("Content-Disposition") or ""
            m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
            name = urllib.parse.unquote(m.group(1)) if m else Path(urllib.parse.urlparse(path).path).name
            return name, r.read()

    def avaa(self, path: str) -> dict:
        """Avaa tiedoston (esimerkiksi raportin) tietokoneen oletusohjelmassa."""
        try:
            name, data = self._fetch(path)
            d = Path(tempfile.gettempdir()) / "Akux"
            d.mkdir(exist_ok=True)
            out = d / name
            out.write_bytes(data)
            os.startfile(str(out))  # type: ignore[attr-defined]  # noqa: S606
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "virhe": str(e)}

    def tallenna(self, path: str) -> dict:
        """Kysyy tallennuspaikan ja tallentaa tiedoston."""
        try:
            name, data = self._fetch(path)
            import webview  # noqa: PLC0415
            mode = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or webview.SAVE_DIALOG
            res = self._window.create_file_dialog(mode, save_filename=name)
            if not res:
                return {"ok": False, "peruttu": True}
            target = Path(res[0] if isinstance(res, (list, tuple)) else res)
            target.write_bytes(data)
            return {"ok": True, "polku": str(target)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "virhe": str(e)}

    def sulje(self) -> None:
        if self._window:
            close_window(self._window)


def close_window(win, code: int = 0, grace: float = 8.0):
    """Sulkee sovellusikkunan. Jos WebView2 ei vapaudu ajoissa, ohjelma päätetään hallitusti."""
    def force():
        time.sleep(grace)
        try:
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass
        os._exit(code)
    threading.Thread(target=force, daemon=True).start()
    try:
        win.destroy()
    except Exception:  # noqa: BLE001
        pass


def _storage_dir(second: bool = False) -> str:
    d = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Akux" / ("ikkuna-2" if second else "ikkuna")
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def run_window(wv, url: str | None, test: bool = False, on_start=None, watch: bool = False) -> int:
    """Avaa sovellusikkunan ja odottaa sen sulkemista. url=None näyttää latausnäkymän,
    kunnes on_start(window) lataa käyttöliittymän."""
    api = IkkunaApi(f"http://127.0.0.1:{PORT}")
    win = wv.create_window("Akux", url=url, html=None if url else LATAUS_HTML, js_api=api,
                           width=1320, height=880, min_size=(380, 560), background_color="#F5F6F8",
                           text_select=True)
    api._window = win
    result = {"koodi": 0}
    if test:
        print("Ikkunatesti: ikkuna luotu", flush=True)

    def watcher():
        # Kun ohjelma suljetaan (myös asennusohjelman päivittäessä), ikkuna sulkeutuu perässä.
        # Uudelleenkäynnistys kestää muutaman sekunnin, joten katko sallitaan 20 sekuntia.
        from .storage import default_data_dir
        marker = default_data_dir() / ".uudelleenkaynnistys"
        seen, down_since = False, None
        while True:
            time.sleep(1)
            if _running(PORT):
                seen, down_since = True, None
                continue
            if not seen:
                continue
            down_since = down_since or time.time()
            try:
                restarting = time.time() - float(marker.read_text()) < 60
            except (OSError, ValueError):
                restarting = False
            if time.time() - down_since > (30 if restarting else 2):
                close_window(win, grace=4)
                return

    def started():
        if test:
            print("Ikkunatesti: ikkuna auki", flush=True)
        if watch and not test:
            threading.Thread(target=watcher, name="akux-ikkunavahti", daemon=True).start()
        if on_start:
            on_start(win)
        if test:
            # Ikkunatesti: käyttöliittymän pitää latautua ja vastata
            ok = False
            end = time.time() + 40
            while time.time() < end and not ok:
                time.sleep(0.5)
                box = {}

                def probe():
                    try:
                        box["v"] = win.evaluate_js("document.querySelector('#view') ? 'ok' : ''")
                    except Exception:  # noqa: BLE001
                        box["v"] = None
                t = threading.Thread(target=probe, daemon=True)
                t.start()
                t.join(5)
                ok = box.get("v") == "ok"
            result["koodi"] = 0 if ok else 4
            print("Ikkunatesti:", "ok" if ok else "käyttöliittymä ei latautunut", flush=True)
            close_window(win, result["koodi"])

    try:
        wv.settings["ALLOW_DOWNLOADS"] = True
        wv.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    except Exception:  # noqa: BLE001
        pass
    # Toisella samanaikaisella ikkunalla on oma tallennuskansio: kaksi WebView2-prosessia ei voi
    # käyttää samaa kansiota eri asetuksin
    wv.start(started, private_mode=False, storage_path=_storage_dir(second=bool(url)))
    return result["koodi"]


def _log_to_file():
    """Ikkunattomassa sovelluksessa tulosteet ohjataan lokitiedostoon."""
    from .storage import default_data_dir
    d = default_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    f = open(d / "loki.txt", "a", encoding="utf-8", buffering=1)
    f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    if sys.stdout is None or not sys.stdout.isatty():
        sys.stdout = f
        sys.stderr = f


def _spawn(args: list[str], low_priority: bool = False):
    """Käynnistää Akuxin erillisen prosessin (palvelin tai esilataus) ilman konsoli-ikkunaa."""
    base = [sys.executable] + ([] if getattr(sys, "frozen", False) else ["-m", "akux.launcher"])
    kw = {"close_fds": True}
    if sys.platform.startswith("win"):
        flags = 0x08000000 | 0x00000200          # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        if low_priority:
            flags |= 0x00004000                  # BELOW_NORMAL_PRIORITY_CLASS
        kw["creationflags"] = flags
    return subprocess.Popen(base + args, **kw)


def _warm_up():
    """Rakentaa kaaviokirjaston fonttivälimuistin. Ajetaan omana matalan prioriteetin prosessinaan."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot  # noqa: F401
        from . import charts  # noqa: F401
    except Exception:  # noqa: BLE001
        pass


def main():
    if "--esilataus" in sys.argv:
        _warm_up()
        return
    if getattr(sys, "frozen", False):
        _log_to_file()
    url = f"http://127.0.0.1:{PORT}"
    test = "--ikkunatesti" in sys.argv
    if test:
        print("Ikkunatesti: käynnistys", flush=True)
        # Ikkunatesti ei saa koskaan jäädä odottamaan
        threading.Thread(target=lambda: (time.sleep(100), print("Ikkunatesti: aikaraja", flush=True), os._exit(6)),
                         daemon=True).start()
    no_window = "--ei-ikkunaa" in sys.argv
    wv = None if no_window else _webview()
    if test:
        print("Ikkunatesti: näyttökomponentti", "löytyi" if wv else "puuttuu", flush=True)
    if _running(PORT):
        if no_window:
            return
        if wv:
            sys.exit(run_window(wv, url, test=test, watch=True))
        if test:
            print("Ikkunatesti: WebView2-ikkuna ei ole käytettävissä")
            sys.exit(3)
        open_window(url)
        return
    if wv:
        # Palvelin omaan prosessiinsa: ikkuna ei voi hidastaa mittausta eikä palvelinta, ja
        # mittaus jatkuu, vaikka ikkuna suljetaan.
        _spawn(["--ei-ikkunaa"])

        def on_start(win):
            for _ in range(240):              # odotetaan, että palvelin vastaa (enintään 2 min)
                if _running(PORT):
                    win.load_url(url)
                    return
                time.sleep(0.5)
            print("Palvelin ei käynnistynyt", flush=True)

        run_window(wv, None, on_start=on_start, watch=True)
        return
    from .server import serve
    try:
        _spawn(["--esilataus"], low_priority=True)
    except Exception:  # noqa: BLE001
        pass
    action = serve(port=PORT, open_window=None if no_window else open_window, open_browser=False,
                   idle_exit=IDLE_EXIT_S)
    if action == "uudelleen":
        _restart(with_window=False)


def _restart(with_window: bool):
    args = [sys.executable] + ([] if getattr(sys, "frozen", False) else ["-m", "akux.launcher"])
    subprocess.Popen(args + ([] if with_window else ["--ei-ikkunaa"]), close_fds=True)


if __name__ == "__main__":
    main()
