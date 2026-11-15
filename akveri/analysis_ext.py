"""Ajo-, kuormitus-, pikalataus- ja itsepurkaustestien laskenta.

Kaikki lähtötiedot ovat auton akunhallinnan luovuttamia: varaustila, akun jännite ja virta,
kennoryhmien jännitteet ja Teslan elinkaaren energialaskurit.
"""
from __future__ import annotations

import math
import statistics

from . import profiles

DEFAULT_R_OHM = {"NCA": 0.075, "NMC": 0.075, "LFP": 0.085}


def fmt(x, d=1):
    from .analysis import fmt as _f
    return _f(x, d)


def _counter_delta(c0, c1):
    """Elinkaarilaskurien muutos: (suurempi muutos, pienempi muutos). Ajossa purku > lataus."""
    if not c0 or not c1:
        return None
    da, db = c1[0] - c0[0], c1[1] - c0[1]
    if da < -0.01 or db < -0.01:
        return None
    return max(da, db), min(da, db)


# ----------------------------------------------------------------------
# Kennoryhmien käytös kuormassa
# ----------------------------------------------------------------------
def _slope(acc):
    """Keskistettyjen summien [n, Sii, Siv, Svv] kulmakerroin ja sen keskivirhe (resistanssi = −kulmakerroin)."""
    if not acc or len(acc) < 4:
        return None
    n, sii, siv, svv = acc
    if n < 20 or sii <= 0 or sii / n < 400:        # virran hajonnan pitää olla vähintään 20 A
        return None
    b = siv / sii
    resid = max(svv - siv * siv / sii, 0.0) / max(n - 2, 1)
    return -b, math.sqrt(resid / sii)


def analyze_load(meta: dict, brick_count: int | None) -> dict | None:
    k = meta.get("kuorma") or {}
    regs = {int(a): b for a, b in (k.get("kennot") or {}).items()}
    rs, ses = {}, {}
    for nro, acc in regs.items():
        res_ = _slope(acc)
        if res_ is None:
            continue
        r, se = res_
        if -0.002 < r < 0.02:      # yhden kennoryhmän resistanssi on alle 20 milliohmia
            rs[nro], ses[nro] = r, se
    total = brick_count or (max(regs) if regs else 0)
    if not rs or len(rs) < 0.9 * max(1, total):
        return None
    pack = _slope(k.get("pakka"))
    vals = list(rs.values())
    med = statistics.median(vals)
    if med <= 0:
        return None
    worst = max(rs, key=rs.get)
    dev = {nro: (r / med - 1) * 100 for nro, r in rs.items()}
    # Poikkeava vain, jos ero mediaaniin on vähintään 20 % ja selvästi mittauksen epävarmuutta suurempi
    outliers = sorted(((nro, d) for nro, d in dev.items()
                       if d >= 20 and rs[nro] - med > 4 * ses[nro]), key=lambda x: -x[1])
    spread = (rs[worst] / med - 1) * 100
    luokka = "Erinomainen" if spread <= 10 else "Hyvä" if spread <= 20 else "Tyydyttävä" if spread <= 35 else "Poikkeava"
    r_sum = sum(vals) * (total / len(rs)) if total else sum(vals)
    # Akun kokonaisresistanssi akun jännitteen ja virran riippuvuudesta (sisältää myös liitokset);
    # jos sitä ei saatu, käytetään kennoryhmien summaa.
    r_pack = pack[0] if (pack and 0.01 < pack[0] < 0.5) else r_sum
    vmin = k.get("v_min")
    return {
        "r_akku_mohm": r_pack * 1000, "r_kennot_mohm": r_sum * 1000, "r_mediaani_mohm": med * 1000, "r_max_mohm": rs[worst] * 1000,
        "r_max_nro": worst, "hajonta_pct": spread, "luokka": luokka,
        "poikkeavat": [{"nro": a, "poikkeama_pct": b} for a, b in outliers[:10]],
        "ryhmat_mohm": [rs.get(i) * 1000 if rs.get(i) else None for i in range(1, total + 1)],
        "jannitteen_lasku_100a_mv": rs[worst] * 100 * 1000,
        "teho_max_kw": k.get("p_max_kw"), "talteenotto_max_kw": -(k.get("p_min_kw") or 0),
        "kuormitustapahtumat": k.get("tapahtumat"),
        "pienin_jannite_kuormassa": ({"v": vmin[0], "nro": vmin[1], "virta_a": vmin[2]} if vmin else None),
    }


# ----------------------------------------------------------------------
# Purkumittaus (ajotesti, pika-ajotesti, täyden testin ajo-osuus)
# ----------------------------------------------------------------------
def analyze_discharge(res: dict, meta: dict, chem: str, n_bricks: int, ref_kwh, nfp, tyyppi: str,
                      load: dict | None) -> dict:
    m = meta.get("merkinnat", {})
    A, L = m.get("ajo_alku"), m.get("ajo_loppu")
    out: dict = {"valmis": False}
    if not A or not L:
        out["syy"] = "Ajon alku- tai loppuarvoja ei saatu."
        return out
    soc0, soc1 = A.get("soc_avg"), L.get("soc_avg")
    if soc0 is None or soc1 is None:
        out["syy"] = "Varaustilaa ei saatu luettua."
        return out
    dsoc = soc0 - soc1
    out.update(soc_alku=soc0, soc_loppu=soc1, soc_muutos=dsoc)
    min_dsoc = 10 if tyyppi == "pika_ajo" else 20
    if dsoc < min_dsoc:
        out["syy"] = f"Varaustila laski vain {fmt(dsoc)} %-yksikköä. Laskentaan tarvitaan vähintään {min_dsoc}."
        return out

    cd = _counter_delta(A.get("laskurit"), L.get("laskurit"))
    integ = (L.get("e_out", 0) - A.get("e_out", 0)) - (L.get("e_in", 0) - A.get("e_in", 0))
    if cd:
        net = cd[0] - cd[1]
        out.update(purku_kwh=cd[0], palautus_kwh=cd[1], lahde="Teslan elinkaaren energialaskurit")
    else:
        net = integ
        out.update(purku_kwh=None, palautus_kwh=None, lahde="Akunhallinnan jännite ja virta")
    if net <= 0.5:
        out["syy"] = "Akusta otettua energiaa ei saatu mitattua."
        return out
    coverage = integ / net if net else 0
    gap_frac = 0.0
    if not cd:
        # Ilman energialaskureita energia saadaan vain jännitteestä ja virrasta. Katkojen ajalta energiaa
        # ei arvioida; katkojen osuus otetaan huomioon epävarmuudessa, ja liian katkonainen ajo hylätään.
        kesto = (L.get("t") or 0) - (A.get("t") or 0)
        aukot = max(0.0, (L.get("aukot_s") or 0) - (A.get("aukot_s") or 0))
        gap_frac = aukot / kesto if kesto > 0 else 0.0
        if gap_frac > 0.05:
            out["kattavuus_pct"] = (1.0 - gap_frac) * 100
            out["syy"] = (f"Yhteys autoon katkesi ajon aikana yhteensä {fmt(aukot / 60)} minuutiksi "
                          f"({fmt(gap_frac * 100)} % ajasta). Tulosta ei laskettu, koska akusta otettua "
                          "energiaa ei saatu mitattua katkojen ajalta. Tarkista lukulaitteen kiinnitys ja toista testi.")
            return out
    out["kattavuus_pct"] = max(0.0, min(100.0, (coverage if cd else 1.0 - gap_frac) * 100))

    # Akun sisäiset häviöt: R · ∫I²dt (R kennoryhmien mittauksesta tai kemian tyypillinen arvo)
    r_ohm = (load or {}).get("r_akku_mohm", 0) / 1000
    if not (0.3 * DEFAULT_R_OHM.get(chem, 0.08) < r_ohm < 3 * DEFAULT_R_OHM.get(chem, 0.08)):
        r_ohm = DEFAULT_R_OHM.get(chem, 0.08)
    i2 = L.get("i2_out", 0) - A.get("i2_out", 0)
    if i2 > 0 and coverage > 0.2:
        loss = r_ohm * i2 / 3.6e6 / min(1.0, coverage)
        u_loss = 0.4 * loss
    else:
        loss = 0.015 * net
        u_loss = loss
    e_chem = net + loss

    v_win = profiles.mean_ocv(chem, soc1, soc0)
    ah_win = e_chem * 1000 / (n_bricks * v_win)
    ah_full = ah_win / (dsoc / 100)
    e_full = ah_full * n_bricks * profiles.mean_ocv(chem, 0, 100) / 1000
    e_low = ah_full * soc1 / 100 * n_bricks * profiles.mean_ocv(chem, 0, soc1) / 1000 if soc1 > 0 else 0.0
    e_high = ah_full * (100 - soc0) / 100 * n_bricks * profiles.mean_ocv(chem, soc0, 100) / 1000 if soc0 < 100 else 0.0

    # LFP-akun varaustila on tarkimmillaan lähellä täyttä akkua, jossa akunhallinta kalibroituu
    su = 1.0 if (chem != "LFP" or soc0 >= 90) else 2.0
    u_cnt = 0.01 * net
    u_soc = e_full * math.sqrt(2) * su / dsoc
    u_ext = 0.03 * (e_low + e_high)
    u_ocv = 0.01 * e_full
    u_gap = gap_frac * e_full
    u = math.sqrt(u_cnt ** 2 + (u_loss * e_full / e_chem) ** 2 + u_soc ** 2 + u_ext ** 2 + u_ocv ** 2 + u_gap ** 2)
    km = (L.get("km") or 0) - (A.get("km") or 0) if (L.get("km") and A.get("km")) else None
    out.update(valmis=True, netto_kwh=net, haviot_kwh=loss, kemiallinen_kwh=e_chem, ah_ikkuna=ah_win,
               ah_taysi=ah_full, e_alapuoli_kwh=e_low, e_ylapuoli_kwh=e_high, taysi_kwh=e_full,
               epavarmuus_kwh=u, r_kaytetty_mohm=r_ohm * 1000,
               epavarmuus_osat={"laskurit": u_cnt, "varaustila": u_soc, "haviot": u_loss,
                                "ekstrapolointi": u_ext, "jannitekayra": u_ocv, "katkot": u_gap},
               matka_km=km, kulutus_wh_km=(net * 1000 / km) if km and km > 5 else None,
               osat=meta.get("osat", 1), kesto_h=(L["t"] - A["t"]) / 3600)
    if ref_kwh:
        out["soh_pct"] = e_full / ref_kwh * 100
        out["soh_epavarmuus_pct"] = u / ref_kwh * 100
    if nfp:
        out["ero_bms_pct"] = (e_full - nfp) / nfp * 100

    q = []
    need = 15 if tyyppi == "pika_ajo" else 50
    q.append(("Varaustilan muutos", dsoc >= need, f"{fmt(dsoc)} %-yks."))
    q.append(("Lepo ennen ajoa", (A.get("lepo_min") or 0) >= 10, f"{fmt(A.get('lepo_min'), 0)} min"))
    q.append(("Lepo ajon jälkeen", (L.get("lepo_min") or 0) >= 10, f"{fmt(L.get('lepo_min'), 0)} min"))
    q.append(("Ei latausta ajon aikana", "ladattu_ajossa" not in m, "kyllä" if "ladattu_ajossa" not in m else "ladattiin"))
    q.append(("Teslan energialaskurit käytössä", bool(cd), "kyllä" if cd else "ei"))
    tl = [x for x in (A.get("t_min"), A.get("t_max"), L.get("t_min"), L.get("t_max")) if x is not None]
    if tl:
        q.append(("Akun lämpötila", 10 <= min(tl) and max(tl) <= 40, f"{fmt(min(tl))}–{fmt(max(tl))} °C"))
    fails = sum(1 for _, ok, _ in q if not ok)
    out["laatu"] = [{"nimi": a, "ok": b, "arvo": c} for a, b, c in q]
    out["laatu_luokka"] = "Hyvä" if fails == 0 else ("Kohtalainen" if fails <= 2 else "Heikko")
    if tyyppi == "pika_ajo" and out["laatu_luokka"] == "Hyvä" and dsoc < 40:
        out["laatu_luokka"] = "Kohtalainen"
    return out


def combine(charge: dict, discharge: dict, ref_kwh) -> dict | None:
    """Täysi akkutesti: lataus- ja purkumittauksen tulokset yhdistetään epävarmuuksilla painottaen."""
    if not (charge.get("valmis") and discharge.get("valmis")):
        return None
    cc, uc = charge["taysi_kwh"], charge["epavarmuus_kwh"]
    cd, ud = discharge["taysi_kwh"], discharge["epavarmuus_kwh"]
    diff = cd - cc
    limit = 2 * math.sqrt(uc ** 2 + ud ** 2)
    agree = abs(diff) <= limit
    if agree:
        w1, w2 = 1 / uc ** 2, 1 / ud ** 2
        val = (cc * w1 + cd * w2) / (w1 + w2)
        u = 1 / math.sqrt(w1 + w2)
    else:
        val, u = cc, uc            # ristiriidassa käytetään tarkempaa latausmittausta
    out = {"valmis": True, "taysi_kwh": val, "epavarmuus_kwh": u, "lataus_kwh": cc, "purku_kwh": cd,
           "ero_kwh": diff, "ero_pct": diff / cc * 100, "raja_kwh": limit, "yhtapitavat": agree,
           "laatu_luokka": "Hyvä" if agree and charge.get("laatu_luokka") == "Hyvä" else
           (charge.get("laatu_luokka") or "Kohtalainen")}
    if ref_kwh:
        out["soh_pct"] = val / ref_kwh * 100
        out["soh_epavarmuus_pct"] = u / ref_kwh * 100
    return out


# ----------------------------------------------------------------------
# Pikalataus
# ----------------------------------------------------------------------
def analyze_dc(meta: dict, chem_key: str | None = None) -> dict | None:
    m = meta.get("merkinnat", {})
    A, L = m.get("pikalataus_alku"), m.get("pikalataus_loppu")
    curve = [c for c in (meta.get("kayra") or []) if c[1] is not None and c[2] is not None]
    if not A or not L or len(curve) < 3:
        return None
    peak = max(curve, key=lambda c: c[2])
    cd = _counter_delta(A.get("laskurit"), L.get("laskurit"))
    e = (cd[0] - cd[1]) if cd else (L.get("e_in", 0) - A.get("e_in", 0))
    dur = (L["t"] - A["t"]) / 3600

    def t_at(soc):
        for a, b in zip(curve, curve[1:]):
            if a[1] <= soc <= b[1] and b[1] > a[1]:
                return a[0] + (soc - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
        return None
    t20, t80 = t_at(20), t_at(80)
    # Jännite-ero vain tasaisen tehon kohdista: tehon muuttuessa kennoryhmien arvot eivät ole samanhetkisiä
    # LFP-akulla jännitekäyrä on jyrkkä tyhjän ja täyden lähellä, jolloin kennoryhmien jännitteet
    # eroavat luonnostaan. Jännite-ero arvioidaan siksi vain tasaiselta alueelta 20–90 %.
    lfp = chem_key == "LFP"
    deltas = []
    for a, b, c in zip(curve, curve[1:], curve[2:]):
        if b[4] is None or b[0] - curve[0][0] < 60 or b[2] <= 0:
            continue
        if lfp and not (20 <= b[1] <= 90):
            continue
        if abs(a[2] - b[2]) <= 0.15 * b[2] and abs(c[2] - b[2]) <= 0.15 * b[2]:
            deltas.append(b[4])
    temps = [c[3] for c in curve if c[3] is not None]
    out = {
        "huipputeho_kw": peak[2], "huippu_soc": peak[1], "energia_kwh": e,
        "energia_lahde": "Teslan elinkaaren energialaskurit" if cd else "Akunhallinnan jännite ja virta",
        "kesto_min": dur * 60, "keskiteho_kw": e / dur if dur > 0 else None,
        "soc_alku": A.get("soc_avg"), "soc_loppu": L.get("soc_avg"),
        "aika_20_80_min": (t80 - t20) / 60 if (t20 and t80) else None,
        "jannite_ero_max_mv": max(deltas) if deltas else None,
        "jannite_ero_alue": "20–90 %:n varauksessa" if lfp else None,
        "lampotila_alku": temps[0] if temps else None, "lampotila_max": max(temps) if temps else None,
        "kayra": [[c[1], c[2]] for c in curve if c[2] >= 3],
    }
    d = out["jannite_ero_max_mv"] or 0
    out["luokka"] = "Erinomainen" if d <= 50 else "Hyvä" if d <= 80 else "Tyydyttävä" if d <= 120 else "Poikkeava"
    return out


# ----------------------------------------------------------------------
# Itsepurkautuminen
# ----------------------------------------------------------------------
def analyze_self_discharge(meta: dict, chem: str) -> dict | None:
    m = meta.get("merkinnat", {})
    A, L = m.get("itse_alku"), m.get("itse_loppu")
    if not A or not L or not A.get("kennot") or not L.get("kennot"):
        return None
    h = (L["t"] - A["t"]) / 3600
    if h <= 0.5:
        return None
    k0, k1 = A["kennot"], L["kennot"]
    dv = [((b - a) * 1000) if (a and b) else None for a, b in zip(k0, k1)]
    vals = [x for x in dv if x is not None]
    if len(vals) < 10:
        return None
    med = statistics.median(vals)
    rel24 = [((x - med) * 24 / h) if x is not None else None for x in dv]
    worst_i = min((i for i, x in enumerate(rel24) if x is not None), key=lambda i: rel24[i])
    worst = rel24[worst_i]
    # Jännitteen muutos muunnetaan varauksen muutokseksi lepojännitekäyrän jyrkkyydellä. LFP-kennon käyrä on
    # keskialueella lähes vaakasuora, jolloin pienikin jännite-ero vastaa suurta varauksen muutosta.
    soc_mid = ((A.get("soc_avg") or 50) + (L.get("soc_avg") or A.get("soc_avg") or 50)) / 2
    slope = max(0.2, profiles.ocv_slope(chem, soc_mid))          # mV / %-yks.
    lim_pct = 0.3                                                # %-yks. vuorokaudessa
    lim = lim_pct * slope                                        # sama raja millivoltteina
    # Havaitsemisraja: kennoryhmän jännitteen keskiarvon epävarmuus (4 keskivirhettä) muunnettuna mV/vrk.
    # Kaikki kennoryhmät mitataan samalla anturipiirillä: kohina arvioidaan kaikkien ryhmien mediaanina,
    # ja kunkin ryhmän keskiarvon epävarmuus saadaan sen näytteiden määrästä. Kohinaa ei tulkita vuodoksi.
    def pooled(mark):
        sds = [x for x in (mark.get("kennot_sd") or []) if x is not None]
        return statistics.median(sds) if sds else None
    sd0, sd1 = pooled(A), pooled(L)
    n0, n1 = A.get("kennot_n") or [], L.get("kennot_n") or []
    thr = []
    for k in range(len(dv)):
        if sd0 is None or sd1 is None or k >= len(n0) or k >= len(n1) or not n0[k] or not n1[k]:
            thr.append(lim)
            continue
        se = math.sqrt(sd0 ** 2 / n0[k] + sd1 ** 2 / n1[k]) * 1000
        thr.append(max(lim, 4 * se * 24 / h))
    det = statistics.median(thr)
    sig = [i for i, x in enumerate(rel24) if x is not None and x <= -thr[i]]
    out_list = sorted(({"nro": i + 1, "mv_vrk": rel24[i], "pct_vrk": rel24[i] / slope} for i in sig),
                      key=lambda d: d["mv_vrk"])
    mild = [i for i, x in enumerate(rel24) if x is not None and x <= -max(lim / 2, thr[i] * 0.75)]
    if not mild:
        luokka = "Erinomainen"
    elif not sig:
        luokka = "Hyvä"
    else:
        luokka = "Tyydyttävä" if min(rel24[i] for i in sig) > -2 * max(lim, det) else "Poikkeava"
    riittava = det <= 1.5 * lim
    cd = _counter_delta(A.get("laskurit"), L.get("laskurit"))
    charged = bool(cd and cd[1] > 0.05)
    used = (cd[0] - cd[1]) if cd else None
    return {
        "tunnit": h, "muutos_mediaani_mv": med, "suhteellinen_mv_vrk": rel24,
        "heikoin_nro": worst_i + 1, "heikoin_mv_vrk": worst, "poikkeavat": out_list[:10], "luokka": luokka,
        "raja_mv_vrk": lim, "havaitsemisraja_mv_vrk": det, "riittava": riittava,
        "jyrkkyys_mv_pct": slope, "raja_pct_vrk": lim_pct, "havaitsemisraja_pct_vrk": det / slope,
        "heikoin_pct_vrk": worst / slope, "soc_keski": soc_mid, "seisonta_kwh": used, "seisonta_w": (used * 1000 / h) if used is not None else None,
        "soc_alku": A.get("soc_avg"), "soc_loppu": L.get("soc_avg"), "ladattu": charged,
        "lfp": chem == "LFP",
    }


# ----------------------------------------------------------------------
def assessments(res: dict):
    """Lisää uusien mittausten arviot, huomiot ja yhteenvetotekstin."""
    ar = res["arviot"]
    y = res.setdefault("yhteenveto", {})
    parts = []
    k = res.get("kuorma")
    if k:
        ar.append({"nimi": "Kennoryhmät kuormassa", "arvo": f"hajonta {fmt(k['hajonta_pct'], 0)} %",
                   "luokka": k["luokka"],
                   "kuvaus": f"Sisäisen resistanssin mediaani {fmt(k['r_mediaani_mohm'], 2)} mΩ, suurin "
                             f"{fmt(k['r_max_mohm'], 2)} mΩ (ryhmä {k['r_max_nro']}). Akun resistanssi "
                             f"{fmt(k['r_akku_mohm'], 0)} mΩ."})
        if k["poikkeavat"]:
            parts.append("Kuormassa muita heikommin käyttäytyviä kennoryhmiä: " +
                         ", ".join(f"ryhmä {p['nro']}" for p in k["poikkeavat"][:5]) + ".")
        else:
            parts.append("Kuormassa kaikki kennoryhmät käyttäytyivät tasaisesti.")
    elif res["tyyppi"] == "kuormitus":
        res["huomiot"].append("Kuormitusta ei saatu riittävästi kennoryhmien vertailuun. Tee testissä useampi "
                              "reipas kiihdytys.")
    p = res.get("purku")
    if p and p.get("valmis") and res["tyyppi"] == "pika_ajo" and "vahvistaa_bms" in p:
        ok = p["vahvistaa_bms"]
        ar.append({"nimi": "Akunhallinnan kapasiteetti ajossa", "arvo": "Vahvistettu" if ok else "Poikkeaa",
                   "luokka": "Erinomainen" if ok else "Tyydyttävä",
                   "kuvaus": f"Ajossa mitattu {fmt(p['taysi_kwh'])} ± {fmt(p['epavarmuus_kwh'])} kWh, "
                             f"Teslan akunhallinnan ilmoittama {fmt((res.get('bms') or {}).get('nfp_kwh'))} kWh."})
        parts.append("Ajossa mitattu purku vastaa akunhallinnan ilmoittamaa kapasiteettia." if ok else
                     "Ajossa mitattu purku poikkeaa akunhallinnan ilmoittamasta kapasiteetista. Tarkka tulos saadaan "
                     "kapasiteettimittauksella tai täydellä akkutestillä.")
    yh = res.get("yhdistetty")
    if yh:
        ar.append({"nimi": "Lataus- ja purkumittauksen vertailu",
                   "arvo": "Yhtäpitävät" if yh["yhtapitavat"] else "Ristiriitaiset",
                   "luokka": "Erinomainen" if yh["yhtapitavat"] else "Tyydyttävä",
                   "kuvaus": f"Lataus {fmt(yh['lataus_kwh'])} kWh, purku ajossa {fmt(yh['purku_kwh'])} kWh. "
                             f"Ero {fmt(yh['ero_kwh'], 2)} kWh ({fmt(yh['ero_pct'])} %)."})
        parts.append("Lataus- ja purkumittauksen tulokset ovat yhtäpitävät." if yh["yhtapitavat"] else
                     "Lataus- ja purkumittauksen tulokset poikkeavat toisistaan; tulos perustuu latausmittaukseen.")
    dc = res.get("pikalataus")
    if dc:
        ar.append({"nimi": "Pikalatauksen huipputeho", "arvo": f"{fmt(dc['huipputeho_kw'], 0)} kW", "luokka": None,
                   "kuvaus": f"Varaustilassa {fmt(dc['huippu_soc'], 0)} %. Ladattu {fmt(dc['energia_kwh'])} kWh "
                             f"{fmt(dc['kesto_min'], 0)} minuutissa."})
        ar.append({"nimi": "Jännite-ero pikalatauksessa", "arvo": f"{fmt(dc['jannite_ero_max_mv'], 0)} mV",
                   "luokka": dc["luokka"], "kuvaus": "Suurin kennoryhmien välinen jännite-ero latauksen aikana."})
        parts.append(f"Pikalatauksen huipputeho oli {fmt(dc['huipputeho_kw'], 0)} kW.")
    elif res["tyyppi"] == "pikalataus":
        res["huomiot"].append("Pikalatausta ei saatu mitattua.")
    sd = res.get("itsepurkaus")
    if sd:
        reliable = sd.get("riittava", True) and not sd["ladattu"]
        if not reliable:
            sd["luokka"] = None
        ar.append({"nimi": "Kennoryhmien itsepurkautuminen", "arvo": f"{fmt(sd['heikoin_pct_vrk'], 2)} %/vrk",
                   "luokka": sd["luokka"],
                   "kuvaus": f"Eniten muista poikkeava ryhmä {sd['heikoin_nro']} ({fmt(sd['heikoin_mv_vrk'], 1)} mV/vrk). "
                             f"Seisonta {fmt(sd['tunnit'], 1)} h."})
        if sd.get("seisonta_w") is not None:
            ar.append({"nimi": "Seisonnan energiankulutus", "arvo": f"{fmt(sd['seisonta_w'], 0)} W", "luokka": None,
                       "kuvaus": f"Auto käytti akusta {fmt(sd['seisonta_kwh'], 2)} kWh seisonnan aikana."})
        if not sd.get("riittava", True):
            if sd["lfp"] and 20 < sd["soc_keski"] < 85:
                res["huomiot"].append(
                    f"LFP-kennon lepojännite muuttuu {fmt(sd['soc_keski'], 0)} %:n varauksessa niin vähän, ettei "
                    f"itsepurkautumista voi mitata luotettavasti (havaitsemisraja {fmt(sd['havaitsemisraja_pct_vrk'], 1)} "
                    "%/vrk). Tee LFP-akun itsepurkaustesti heti täyteen latauksen jälkeen, yli 90 %:n varauksessa.")
            else:
                res["huomiot"].append(
                    f"Mittaus ei ollut riittävän tarkka luotettavaan tulokseen (havaitsemisraja "
                    f"{fmt(sd['havaitsemisraja_pct_vrk'], 1)} %/vrk). Toista testi pidemmällä seisonnalla, "
                    "esimerkiksi yön yli.")
        if reliable and not sd["poikkeavat"]:
            parts.append("Itsepurkautuvia kennoryhmiä ei havaittu.")
        elif reliable:
            parts.append("Muita nopeammin purkautuvia kennoryhmiä: " +
                         ", ".join(f"ryhmä {x['nro']}" for x in sd["poikkeavat"][:5]) + ".")
        if sd["ladattu"]:
            res["huomiot"].append("Autoa ladattiin seisonnan aikana. Itsepurkaustesti on tällöin epäluotettava.")
    elif res["tyyppi"] == "itsepurkaus":
        res["huomiot"].append("Itsepurkaustestin alku- tai loppuarvoja ei saatu.")
    if parts:
        y["teksti"] = (y.get("teksti", "") + " " + " ".join(parts)).strip()
