"""Sovelluksen käynnistin (Akux.exe).

- Avaa käyttöliittymän omaan sovellusikkunaansa (Microsoft Edge tai Chrome sovellustilassa).
- Jos ohjelma on jo käynnissä, avaa vain uuden ikkunan.
- Sulkeutuu itsestään, kun ikkuna on suljettu eikä mittausta ole käynnissä.
  Käynnissä oleva mittaus jatkuu, vaikka ikkunan sulkee.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
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
    if _running(PORT):
        open_window(f"http://127.0.0.1:{PORT}")
        return
    from .server import serve
    no_window = "--ei-ikkunaa" in sys.argv
    action = serve(port=PORT, open_window=None if no_window else open_window, open_browser=False,
                   idle_exit=IDLE_EXIT_S)
    if action == "uudelleen":
        # Avoin ikkuna yhdistää uuteen käynnistykseen itsestään
        args = [sys.executable] + ([] if getattr(sys, "frozen", False) else ["-m", "akux.launcher"])
        subprocess.Popen(args + ["--ei-ikkunaa"], close_fds=True)


if __name__ == "__main__":
    main()
