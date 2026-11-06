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
        self.window = None

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
            res = self.window.create_file_dialog(mode, save_filename=name)
            if not res:
                return {"ok": False, "peruttu": True}
            target = Path(res[0] if isinstance(res, (list, tuple)) else res)
            target.write_bytes(data)
            return {"ok": True, "polku": str(target)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "virhe": str(e)}

    def sulje(self) -> None:
        if self.window:
            close_window(self.window)


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


def _storage_dir() -> str:
    d = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Akux" / "ikkuna"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def run_window(wv, url: str | None, test: bool = False, on_start=None) -> int:
    """Avaa sovellusikkunan ja odottaa sen sulkemista. url=None näyttää latausnäkymän,
    kunnes on_start(window) lataa käyttöliittymän."""
    api = IkkunaApi(f"http://127.0.0.1:{PORT}")
    win = wv.create_window("Akux", url=url, html=None if url else LATAUS_HTML, js_api=api,
                           width=1320, height=880, min_size=(380, 560), background_color="#F5F6F8",
                           text_select=True)
    api.window = win
    result = {"koodi": 0}

    def started():
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
    if test:
        # Ikkunatesti ei saa jäädä odottamaan, vaikka ikkuna ei koskaan aukeaisi
        threading.Thread(target=lambda: (time.sleep(90), print("Ikkunatesti: aikaraja", flush=True), os._exit(6)),
                         daemon=True).start()
    wv.start(started, private_mode=False, storage_path=_storage_dir())
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


def main():
    if getattr(sys, "frozen", False):
        _log_to_file()
    url = f"http://127.0.0.1:{PORT}"
    test = "--ikkunatesti" in sys.argv
    wv = _webview()
    if _running(PORT):
        if wv:
            sys.exit(run_window(wv, url, test=test))
        if test:
            print("Ikkunatesti: WebView2-ikkuna ei ole käytettävissä")
            sys.exit(3)
        open_window(url)
        return
    from .server import serve
    no_window = "--ei-ikkunaa" in sys.argv
    if wv and not no_window:
        # Palvelin taustasäikeessä, sovellusikkuna pääsäikeessä
        state = {"ikkuna": None, "toiminto": None}

        def server_thread():
            action_ = serve(port=PORT, open_window=None, open_browser=False, idle_exit=IDLE_EXIT_S)
            state["toiminto"] = action_
            if action_ == "uudelleen":
                _restart(with_window=True)
            if state["ikkuna"]:
                close_window(state["ikkuna"])

        th = threading.Thread(target=server_thread, name="akux-palvelin")

        def on_start(win):
            state["ikkuna"] = win
            for _ in range(240):              # odotetaan, että palvelin vastaa (enintään 2 min)
                if _running(PORT):
                    win.load_url(url)
                    return
                if not th.is_alive():
                    return
                time.sleep(0.5)

        th.start()
        run_window(wv, None, on_start=on_start)
        th.join()            # käynnissä oleva mittaus jatkuu, vaikka ikkuna suljetaan
        return
    action = serve(port=PORT, open_window=None if no_window else open_window, open_browser=False,
                   idle_exit=IDLE_EXIT_S)
    if action == "uudelleen":
        _restart(with_window=False)


def _restart(with_window: bool):
    args = [sys.executable] + ([] if getattr(sys, "frozen", False) else ["-m", "akux.launcher"])
    subprocess.Popen(args + ([] if with_window else ["--ei-ikkunaa"]), close_fds=True)


if __name__ == "__main__":
    main()
