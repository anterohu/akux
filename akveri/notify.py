"""Puhelinilmoitukset ntfy-palvelun kautta (oma palvelin tai ntfy.sh).

Ilmoitus lähetetään HTTP POST -pyyntönä aiheen osoitteeseen, esimerkiksi
https://ntfy.sh/akveri-oma-aihe tai http://100.64.0.5:8080/akveri. Puhelimeen asennetaan
ntfy-sovellus ja tilataan sama aihe.
"""
from __future__ import annotations

import threading
import urllib.request

LAJIT = {
    "vaiheet": "ilmoitus_vaiheet",
    "valmis": "ilmoitus_valmis",
    "ongelmat": "ilmoitus_ongelmat",
}


def _post(url: str, title: str, message: str, priority: str, tags: str) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST")
        # Otsikko koodataan RFC 2047 -muotoon, jotta ääkköset säilyvät
        import base64
        req.add_header("Title", "=?UTF-8?B?" + base64.b64encode(title.encode("utf-8")).decode() + "?=")
        req.add_header("Priority", priority)
        req.add_header("Tags", tags)
        with urllib.request.urlopen(req, timeout=8) as r:
            return 200 <= r.status < 300, f"Palvelin vastasi {r.status}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


class Notifier:
    def __init__(self, settings_fn):
        self.settings_fn = settings_fn
        self.last_result = None

    def send(self, laji: str, title: str, message: str, *, force=False, wait=False):
        s = self.settings_fn()
        url = (s.get("ilmoitus_osoite") or "").strip()
        if not url:
            return False, "Ilmoitusten osoitetta ei ole asetettu."
        if not force:
            if not s.get("ilmoitukset_kaytossa"):
                return False, "Ilmoitukset eivät ole käytössä."
            key = LAJIT.get(laji)
            if key and not s.get(key, True):
                return False, "Tämä ilmoituslaji ei ole käytössä."
        priority = {"ongelmat": "high", "valmis": "default"}.get(laji, "low")
        tags = {"ongelmat": "warning", "valmis": "white_check_mark"}.get(laji, "battery")

        from . import kielet  # noqa: PLC0415  ilmoitus ohjelman kielellä
        title, message = kielet.t(title), kielet.t(message)

        def run():
            self.last_result = _post(url, title, message, priority, tags)

        if wait:
            run()
            return self.last_result
        threading.Thread(target=run, daemon=True).start()
        return True, "Lähetetty"
