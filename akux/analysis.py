"""Mittausten analyysi. Kaikki laskentakaavat on kuvattu raportin menetelmäsivulla."""
from __future__ import annotations

import math
import statistics
import time

from . import VERSIO, profiles
from . import vin as vinmod

TARKKUUSRAJA_PCT = 3.0   # päätuloksen suurin sallittu epävarmuus (kunto, %-yksikköä)
SOH_LUOKAT = [(90, "Erinomainen"), (85, "Hyvä"), (80, "Tyydyttävä"), (70, "Heikentynyt"), (0, "Takuurajan alittava")]
ERO_LUOKAT = [(15, "Erinomainen"), (30, "Hyvä"), (50, "Tyydyttävä"), (1e9, "Poikkeava")]


def soh_class(pct):
    for lim, name in SOH_LUOKAT:
        if pct >= lim:
            return name
    return SOH_LUOKAT[-1][1]


def delta_class(mv, soc=None):
    scale = 1.5 if (soc is not None and soc < 20) else 1.0
    for lim, name in ERO_LUOKAT:
        if mv <= lim * scale:
            return name
    return ERO_LUOKAT[-1][1]


def expected_loss_pct(km: float | None, model_code: str | None = None) -> float | None:
    """Suuntaa antava keskimääräinen kapasiteetin alenema ajomäärän mukaan.

    Käyrä on sovitettu Teslan vaikuttavuusraportin (Impact Report 2023)
    keskiarvoon: Model 3/Y noin 15 % noin 320 000 km:n jälkeen, ja alenema on
    nopeinta ensimmäisten kymmenien tuhansien kilometrien aikana."""
    if km is None or km < 0:
        return None
    loss = 5.0 * (1 - math.exp(-km / 30000)) + 10.0 * km / 320000
    if model_code and model_code in "SX":
        loss *= 12.0 / 15.0       # Model S / X: noin 12 % 320 000 km:n jälkeen
    return loss


def fmt(x, d=1):
    if x is None:
        return "–"
    x = round(float(x), d)
    if x == 0:
        x = 0.0
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",").replace("-", "−")


# ----------------------------------------------------------------------
def cell_stats(volts: list, soc: float | None = None, current: float | None = None) -> dict | None:
    vals = [(k + 1, v) for k, v in enumerate(volts or []) if v]
    if len(vals) < 2:
        return None
    vs = [v for _, v in vals]
    med = statistics.median(vs)
    mad = statistics.median([abs(v - med) for v in vs]) * 1.4826
    limit = max(0.015, 4 * mad)
    out_list = [{"nro": n, "v": v, "poikkeama_mv": (v - med) * 1000}
                for n, v in vals if abs(v - med) > limit]
    vmin = min(vals, key=lambda x: x[1])
    vmax = max(vals, key=lambda x: x[1])
    delta = (vmax[1] - vmin[1]) * 1000
    at_rest = current is None or abs(current) < 3.0
    return {
        "lkm": len(vals),
        "ka_v": statistics.fmean(vs),
        "mediaani_v": med,
        "min_v": vmin[1], "min_nro": vmin[0],
        "max_v": vmax[1], "max_nro": vmax[0],
        "ero_mv": delta,
        "keskihajonta_mv": statistics.pstdev(vs) * 1000,
        "poikkeavat": out_list,
        "jannitteet": [v for v in volts],
        "levossa": at_rest,
        "virta_a": current,
        "soc": soc,
        "luokka": delta_class(delta, soc),
    }


def _snap(snaps, *names):
    for name in names:
        for s in reversed(snaps):
            if s["nimi"] == name:
                return s
    return None


def reference_capacity(vehicle: dict, bms_bol: float | None, model: dict | None) -> tuple[float | None, str]:
    learned = (vehicle or {}).get("opitut", {})
    if bms_bol and 30 <= bms_bol <= 150:
        return bms_bol, "Auton akunhallinta"
    if learned.get("bol_kwh"):
        return learned["bol_kwh"], "Auton akunhallinta (aiempi mittaus)"
    if learned.get("viite_kayttaja"):
        return float(learned["viite_kayttaja"]), "Käyttäjän ilmoittama"
    if model:
        return model["viite_kwh"], "Mallitaulukko (likiarvo)"
    return None, "Ei tiedossa"


def _platform_notes(model, platform, ref_src, last) -> list[str]:
    out = []
    if ref_src.startswith("Mallitaulukko") and (platform == "sx" or (model or {}).get("likiarvo")):
        out.append("Tämän mallin akunhallinta ei ilmoita akun alkuperäistä energiaa. Kunto on laskettu mallitaulukon "
                   "likiarvosta. Tarkempi tulos saadaan, kun auton tietoihin syötetään akun alkuperäinen kapasiteetti.")
    if (model or {}).get("kokeellinen"):
        out.append("Tämän mallin akkuviestejä ei ole julkisesti varmistettu. Tulos on kokeellinen.")
    return out


def parse_date(txt):
    """Hyväksyy muodot 2020-05-14, 14.5.2020 ja 5/2020. Palauttaa (vuosi, kuukausi, päivä)."""
    import re
    if not txt:
        return None
    txt = str(txt).strip()
    for pat, order in ((r"(\d{4})-(\d{1,2})-(\d{1,2})$", "ymd"), (r"(\d{1,2})\.(\d{1,2})\.(\d{4})$", "dmy"),
                       (r"(\d{1,2})[./](\d{4})$", "my")):
        m = re.match(pat, txt)
        if m:
            g = [int(x) for x in m.groups()]
            if order == "ymd":
                return g[0], g[1], g[2]
            if order == "dmy":
                return g[2], g[1], g[0]
            return g[1], g[0], 1
    return None


def warranty_status(vehicle, model, km, at_ts) -> dict:
    w = profiles.warranty(model)
    out = {"vuotta": w["vuotta"], "km": w["km"], "sailyvyys_pct": w["sailyvyys_pct"], "voimassa": None}
    d = parse_date((vehicle or {}).get("kayttoonotto"))
    if d:
        y, mth, day = d
        out["kayttoonotto"] = f"{day}.{mth}.{y}"
        out["paattyy"] = f"{day}.{mth}.{y + w['vuotta']}"
        end_ts = time.mktime((y + w["vuotta"], mth, day, 0, 0, 0, 0, 0, -1))
        at = at_ts or time.time()
        out["aika_jaljella_v"] = max(0.0, (end_ts - at) / (365.25 * 86400))
        time_ok = at < end_ts
    else:
        time_ok = None
    if km is not None:
        out["km_jaljella"] = max(0.0, w["km"] - km)
        km_ok = km < w["km"]
    else:
        km_ok = None
    if time_ok is False or km_ok is False:
        out["voimassa"] = False
    elif time_ok and km_ok:
        out["voimassa"] = True
    return out


# ----------------------------------------------------------------------
def analyze_test(storage, tid: int, meta: dict) -> dict:
    test = storage.test(tid)
    vehicle = storage.vehicle(test["vehicle_id"])
    snaps = storage.snapshots(tid)
    samples = storage.samples(tid)
    last = snaps[-1]["data"] if snaps else {}

    # -- ajoneuvon tunnistus --------------------------------------------
    vin_txt = (vehicle or {}).get("vin") or last.get("vin")
    vin_info = vinmod.decode(vin_txt) if vin_txt else None
    bol = None
    for s in reversed(snaps):
        if s["data"].get("bol_kwh"):
            bol = s["data"]["bol_kwh"]
            break
    brick_count = last.get("brick_count")
    model = profiles.get((vehicle or {}).get("malli_id"))
    reasons = ["valittu käsin"] if model else []
    platform = last.get("platform")
    nfp_now = last.get("nfp_kwh")
    if model and platform and model.get("alusta", "m3") != platform:
        model = None          # väylä kertoo toisesta alustasta kuin valittu pohja
    if model and model.get("likiarvo") and nfp_now and nfp_now > model["viite_kwh"] * 1.02:
        model = None          # akku on suurempi kuin valittu pohja
    if not model:
        model, reasons = profiles.identify(vin_info, bol_kwh=bol, brick_count=brick_count,
                                           cell_v_max=last.get("cell_v_max"), soc=last.get("soc_avg"),
                                           platform=platform, nfp_kwh=nfp_now)
    chem_key = (model or {}).get("kemia", "NCA")
    ref_kwh, ref_src = reference_capacity(vehicle, bol, model)
    odo = test.get("mittarilukema") or last.get("odometer_km")

    res: dict = {
        "tyyppi": test["tyyppi"],
        "versio": VERSIO,
        "analysoitu": time.time(),
        "ajoneuvo": {
            "vin": vin_txt,
            "vin_tiedot": vin_info,
            "malli_id": (model or {}).get("id"),
            "malli": (model or {}).get("nimi"),
            "kemia": chem_key,
            "kemia_nimi": profiles.chemistry(chem_key)["nimi"],
            "kennovalmistaja": (model or {}).get("kennovalmistaja"),
            "kennotyyppi": (model or {}).get("kennotyyppi"),
            "kennoryhmat": brick_count,
            "tunnistus": reasons,
            "mittarilukema_km": odo,
            "mittarilukema_lahde": "Käyttäjän ilmoittama" if test.get("mittarilukema") else (
                "Auton väylä" if last.get("odometer_km") else None),
            "akun_massa_kg": last.get("pack_mass_kg"),
            "alusta": platform,
            "alusta_nimi": last.get("platform_name"),
            "akun_matkamittari_km": last.get("battery_odometer_km"),
            "kokeellinen": bool((model or {}).get("kokeellinen")),
        },
        "viite": {"kwh": ref_kwh, "lahde": ref_src},
        "huomiot": list(meta.get("huomiot", [])) + _platform_notes(model, platform, ref_src, last),
        "meta": meta,
        "arviot": [],
    }

    # -- akunhallinnan tiedot -------------------------------------------
    nfp = last.get("nfp_kwh")
    buffer = last.get("buffer_kwh")
    bms = {
        "nfp_kwh": nfp, "ner_kwh": last.get("nominal_remaining_kwh"), "puskuri_kwh": buffer,
        "soc_ui": last.get("soc_ui"), "soc_avg": last.get("soc_avg"),
        "soc_min": last.get("soc_min"), "soc_max": last.get("soc_max"),
        "kaytettava_kwh": (nfp - buffer) if (nfp and buffer is not None) else None,
        "energiamuoto": last.get("energy_format"),
        "virtatarkistus": last.get("current_check"),
        "max_lataus_v": last.get("max_charge_v"),
    }
    if nfp and ref_kwh:
        bms["soh_pct"] = nfp / ref_kwh * 100
    res["bms"] = bms

    # -- elinkaari ------------------------------------------------------
    dis = last.get("total_discharge_kwh")
    chg = last.get("total_charge_kwh")
    res["elinkaari"] = {
        "purku_kwh": dis, "lataus_kwh": chg,
        "syklit": (dis / ref_kwh) if (dis and ref_kwh) else None,
        "kulutus_wh_km": (dis * 1000 / odo) if (dis and odo and odo > 1000) else None,
    }

    # -- lämpötilat -----------------------------------------------------
    tmins = [s["t_min"] for s in samples if s["t_min"] is not None]
    tmaxs = [s["t_max"] for s in samples if s["t_max"] is not None]
    res["lampotilat"] = {
        "min": min(tmins) if tmins else last.get("temp_min"),
        "max": max(tmaxs) if tmaxs else last.get("temp_max"),
        "alku_min": tmins[0] if tmins else None, "alku_max": tmaxs[0] if tmaxs else None,
        "loppu_min": tmins[-1] if tmins else None, "loppu_max": tmaxs[-1] if tmaxs else None,
    }

    res["takuu"] = warranty_status(vehicle, model, odo, test.get("aloitettu"))

    from . import analysis_ext as ext
    tyyppi = test["tyyppi"]
    n_bricks = brick_count or (model or {}).get("sarjakennot") or 96
    if isinstance(n_bricks, list):
        n_bricks = n_bricks[-1]
    if tyyppi == "pikatarkastus":
        _analyze_quick(res, snaps, samples)
    elif tyyppi in ("kapasiteetti", "taysi"):
        _analyze_capacity(res, snaps, samples, meta, chem_key, ref_kwh, nfp, buffer)
    else:
        _analyze_cells_other(res, snaps, meta, tyyppi)

    load = ext.analyze_load(meta, brick_count)
    if load:
        res["kuorma"] = load
    if tyyppi in ("ajotesti", "pika_ajo", "taysi"):
        res["purku"] = ext.analyze_discharge(res, meta, chem_key, n_bricks, ref_kwh, nfp, tyyppi, load)
        if not res["purku"].get("valmis") and res["purku"].get("syy"):
            res["huomiot"].append("Purkumittausta ei voitu laskea: " + res["purku"]["syy"])
    if tyyppi == "taysi":
        res["yhdistetty"] = ext.combine(res.get("kapasiteetti") or {}, res.get("purku") or {}, ref_kwh)
    if tyyppi == "pikalataus":
        res["pikalataus"] = ext.analyze_dc(meta)
    if tyyppi == "itsepurkaus":
        res["itsepurkaus"] = ext.analyze_self_discharge(meta, chem_key)

    # Raportin päätulos: täydessä testissä yhdistetty, ajotestissä purkumittaus
    cands = {"taysi": [(res.get("yhdistetty"), "Täysi akkutesti"), (res.get("kapasiteetti"), "Kapasiteettimittaus"),
                       (res.get("purku"), "Ajotesti")],
             "ajotesti": [(res.get("purku"), "Ajotesti")],
             "kapasiteetti": [(res.get("kapasiteetti"), "Kapasiteettimittaus")]}.get(tyyppi, [])
    # Pika-ajotesti ei anna kuntoprosenttia: lyhyen ajon varaustilan muutos ei riitä tarkkaan tulokseen.
    # Se tarkistaa, vastaako akunhallinnan oma arvio ajossa mitattua.
    pk = res.get("purku") or {}
    if tyyppi == "pika_ajo" and pk.get("valmis") and nfp:
        diff = pk["taysi_kwh"] - nfp
        pk["vahvistaa_bms"] = abs(diff) <= max(2 * pk["epavarmuus_kwh"], 0.02 * nfp)
    # Laatuportti: päätulokseksi kelpaa vain riittävän tarkka ja hyvälaatuinen mittaus
    primary = None
    rejected = []
    for c in cands:
        p0 = c[0]
        if not (p0 and p0.get("valmis")):
            continue
        u_pct = p0.get("soh_epavarmuus_pct")
        if u_pct is None and ref_kwh and p0.get("epavarmuus_kwh"):
            u_pct = p0["epavarmuus_kwh"] / ref_kwh * 100
        if p0.get("laatu_luokka") == "Heikko" or (u_pct is not None and u_pct > TARKKUUSRAJA_PCT):
            p0["hylatty"] = True
            rejected.append(f"{c[1]} ei täyttänyt raportin tarkkuusvaatimusta (epävarmuus ±{fmt(u_pct)} "
                            f"%-yksikköä, vaatimus enintään ±{fmt(TARKKUUSRAJA_PCT, 0)}"
                            + (", mittauksen laatu heikko" if p0.get("laatu_luokka") == "Heikko" else "") + ").")
            continue
        primary = c
        break
    if rejected:
        res["huomiot"].extend(rejected)
        if not primary:
            res["huomiot"].append("Akun kuntona näytetään Teslan akunhallinnan oma arvio.")
    if primary and primary[0] and primary[0].get("valmis"):
        res["paatulos"] = {**{k: primary[0].get(k) for k in ("taysi_kwh", "epavarmuus_kwh", "soh_pct",
                                                              "soh_epavarmuus_pct", "laatu_luokka")},
                           "valmis": True, "lahde": primary[1],
                           "ero_bms_pct": ((primary[0]["taysi_kwh"] - nfp) / nfp * 100) if nfp else None}

    _summarize(res)
    ext.assessments(res)
    res["kapasiteetit"] = _gross_net(res, ref_kwh, buffer)
    res["tarkiste"] = test.get("tarkiste")
    return res


def _gross_net(res, ref_kwh, buffer) -> dict:
    """Brutto = akun koko energia, netto = käytettävissä oleva energia (brutto miinus akunhallinnan suojavara)."""
    y = res.get("yhteenveto") or {}
    now = y.get("kapasiteetti_kwh")
    b = buffer if (buffer is not None and 0 <= buffer < 15) else None
    out = {"puskuri_kwh": b,
           "brutto_uutena": ref_kwh, "netto_uutena": (ref_kwh - b) if (ref_kwh and b is not None) else None,
           "brutto_nyt": now, "netto_nyt": (now - b) if (now and b is not None) else None,
           "uutena_lahde": res["viite"]["lahde"], "nyt_lahde": y.get("kunto_lahde")}
    return out


def _analyze_quick(res, snaps, samples):
    s = _snap(snaps, "pikatarkastus_ka", "pikatarkastus")
    d = s["data"] if s else {}
    cs = cell_stats(d.get("kennot"), d.get("soc_avg"), d.get("pack_i"))
    res["kennot"] = cs
    res["kennot_otsikko"] = "Kennoryhmien jännitteet mittaushetkellä"
    if cs and not cs["levossa"]:
        res["huomiot"].append("Akun virta oli mittaushetkellä yli 3 A. Kennojännitteiden ero on luotettavin levossa mitattuna.")
    if d.get("kennot_naytteita") and res["kennot"]:
        res["kennot"]["naytteita"] = d["kennot_naytteita"]
    if res["ajoneuvo"].get("kemia") == "LFP":
        res["huomiot"].append("LFP-akun akunhallinta arvioi kapasiteetin luotettavimmin, kun akku on ladattu täyteen "
                              "viime päivinä. Tesla suosittelee LFP-akun lataamista täyteen vähintään kerran viikossa. "
                              "Tarkin tulos saadaan kapasiteettimittauksella.")


def _analyze_cells_other(res, snaps, meta, tyyppi):
    """Kennoryhmien jännitteet ajo-, kuormitus-, pikalataus- ja itsepurkaustesteissä."""
    m = meta.get("merkinnat", {})
    if tyyppi in ("ajotesti", "pika_ajo"):
        s_hi = _snap(snaps, "ajo_alku")
        s_lo = _snap(snaps, "loppu")
        if s_hi:
            res["kennot"] = cell_stats(s_hi["data"].get("kennot"), s_hi["data"].get("soc_avg"), s_hi["data"].get("pack_i"))
            res["kennot_otsikko"] = "Kennoryhmien jännitteet levossa ennen ajoa"
        if s_lo:
            res["kennot_matala"] = cell_stats(s_lo["data"].get("kennot"), s_lo["data"].get("soc_avg"),
                                              s_lo["data"].get("pack_i"))
        return
    src = {"kuormitus": (m.get("kuorma_lepo") or {}), "itsepurkaus": (m.get("itse_loppu") or {})}.get(tyyppi)
    if src and src.get("kennot"):
        res["kennot"] = cell_stats(src["kennot"], src.get("soc_avg"), 0.0)
        res["kennot_otsikko"] = {"kuormitus": "Kennoryhmien jännitteet levossa ennen kuormitusta",
                                 "itsepurkaus": "Kennoryhmien jännitteet seisonnan jälkeen"}[tyyppi]
        return
    s_end = _snap(snaps, "loppu")
    if s_end:
        res["kennot"] = cell_stats(s_end["data"].get("kennot"), s_end["data"].get("soc_avg"), s_end["data"].get("pack_i"))
        res["kennot_otsikko"] = "Kennoryhmien jännitteet mittauksen lopussa"


def _median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _analyze_capacity(res, snaps, samples, meta, chem_key, ref_kwh, nfp, buffer):
    m = meta.get("merkinnat", {})
    A = m.get("lataus_alku")
    L = m.get("lataus_loppu")
    rest0 = m.get("lepo_alku", {})
    rest1 = m.get("lepo_loppu", {})
    s_low = _snap(snaps, "lepo_alku")
    s_high = _snap(snaps, "lepo_loppu", "lataus_loppu")
    cs_high = cell_stats(s_high["data"].get("kennot"), s_high["data"].get("soc_avg"),
                         s_high["data"].get("pack_i")) if s_high else None
    cs_low = cell_stats(s_low["data"].get("kennot"), s_low["data"].get("soc_avg"),
                        s_low["data"].get("pack_i")) if s_low else None
    res["kennot"] = cs_high
    res["kennot_otsikko"] = "Kennoryhmien jännitteet täyden latauksen jälkeen levossa"
    res["kennot_matala"] = cs_low

    cap: dict = {"valmis": False}
    res["kapasiteetti"] = cap
    if not A or not L:
        res["huomiot"].append("Latausta ei saatu mitattua, joten kapasiteettia ei voitu laskea.")
        return

    soc0, soc1 = A.get("soc_avg"), L.get("soc_avg")
    e_in, e_out = L.get("e_in_kokonais", 0.0), L.get("e_out_kokonais", 0.0)
    ah_in, ah_out = L.get("ah_in_kokonais", 0.0), L.get("ah_out_kokonais", 0.0)
    flipped = False
    if soc0 is not None and soc1 is not None and soc1 > soc0 and e_out > e_in:
        e_in, e_out, ah_in, ah_out = e_out, e_in, ah_out, ah_in
        flipped = True
        res["huomiot"].append("Virran etumerkki tulkittiin käänteisesti, koska varaustila nousi.")
    e_term = e_in - e_out
    ah_net = ah_in - ah_out

    # Vertailu akunhallinnan elinkaarilaskureihin (1 Wh:n tarkkuus)
    cnt_kwh = None
    c0, c1 = A.get("laskurit"), L.get("laskurit")
    if c0 and c1:
        # Latauksessa latauslaskuri kasvaa ja purkulaskuri pysyy lähes paikallaan. Erotus on
        # akkuun mennyt nettoenergia kenttien järjestyksestä riippumatta.
        cnt_kwh = abs((c1[0] - c0[0]) - (c1[1] - c0[1]))
        if cnt_kwh <= 0.5:
            cnt_kwh = None
    cnt_diff = (e_term - cnt_kwh) / cnt_kwh * 100 if (cnt_kwh and e_term > 0) else None
    cnt_used = False
    if cnt_kwh and res["ajoneuvo"].get("alusta") == "sx" and (cnt_diff is None or abs(cnt_diff) > 8):
        # Model S/X 2012–2021: virran mittakaava ei ole julkisesti varmistettu. Jos integroitu
        # energia poikkeaa laskurista, käytetään laskuria ja skaalataan varaus samassa suhteessa.
        k = cnt_kwh / e_term if e_term > 0 else 1.0
        e_term, ah_net = cnt_kwh, ah_net * k
        cnt_used = True
        res["huomiot"].append("Latausenergia on laskettu akunhallinnan latauslaskurista, koska virran "
                              "mittakaava ei vastannut laskuria.")

    # Sisäinen resistanssi latauksen alun jännitehypystä. Lepojännitteen nousu
    # latauksen alussa vähennetään kemian lepojännitekäyrän kulmakertoimella.
    r_est = None
    v_rest = A.get("v_lepo")
    win = m.get("r_ikkuna") or []
    n_cells = res["ajoneuvo"]["kennoryhmat"] or 96
    if v_rest and win and soc0 is not None and A.get("nfp"):
        ah_full_est = A["nfp"] * 1000 / (n_cells * profiles.mean_ocv(chem_key, 0, 100))
        slope = (profiles.mean_ocv(chem_key, soc0 + 1.0, soc0 + 1.0) -
                 profiles.mean_ocv(chem_key, soc0, soc0)) * n_cells          # V / %-yks.
        rs = []
        for row in win:
            v, i = row[0], row[1]
            ah = row[2] if len(row) > 2 else 0.0
            if i < -2:
                ocv_rise = slope * ah / ah_full_est * 100
                rs.append((v - v_rest - ocv_rise) / (-i))
        r_est = _median(rs)
        if r_est is not None and not (0.02 <= r_est <= 0.30):
            r_est = None
    i2 = L.get("i2_kokonais", 0.0)
    e_loss = (r_est * i2 / 3.6e6) if r_est else 0.0
    e_chem = e_term - e_loss

    gap_kwh = 0.0
    for g in meta.get("aukot", []):
        g.pop("_e_mark", None)
        if cnt_used:
            continue          # laskuri sisältää myös katkojen aikana ladatun energian
        if g.get("ner_alku") is not None and g.get("ner_loppu") is not None:
            gap_kwh += max(0.0, g["ner_loppu"] - g["ner_alku"])
    if gap_kwh:
        res["huomiot"].append(f"Mittausdatan katkojen aikana akkuun mennyt energia ({fmt(gap_kwh, 2)} kWh) "
                              "on täydennetty akunhallinnan energialaskennasta.")
    e_chem += gap_kwh

    dsoc = (soc1 - soc0) if (soc0 is not None and soc1 is not None) else None
    cap.update({
        "soc_alku": soc0, "soc_loppu": soc1, "dsoc": dsoc,
        "soc_ui_alku": A.get("soc_ui"), "soc_ui_loppu": L.get("soc_ui"),
        "taysi": L.get("taysi"), "lataus_kesto_s": L["t"] - A["t"],
        "e_napa_kwh": e_term, "ah": ah_net, "r_ohm": r_est, "e_haviot_kwh": e_loss,
        "e_kemia_kwh": e_chem, "katkot_kwh": gap_kwh, "etumerkki_kaannetty": flipped,
        "lepo_alku_min": rest0.get("kesto_min"), "lepo_loppu_min": rest1.get("kesto_min"),
        "lepo_alku_ohitettu": rest0.get("ohitettu"),
        "t_alku": [A.get("t_min"), A.get("t_max")], "t_loppu": [L.get("t_min"), L.get("t_max")],
        "nfp_alku": A.get("nfp"), "nfp_loppu": L.get("nfp"),
        "ner_alku": A.get("ner"), "ner_loppu": L.get("ner"),
        "keskiteho_kw": (e_term / ((L["t"] - A["t"]) / 3600)) if L["t"] > A["t"] else None,
        "laskuri_kwh": cnt_kwh, "laskuri_ero_pct": cnt_diff, "laskuri_kaytetty": cnt_used,
    })
    if not dsoc or dsoc < 20:
        res["huomiot"].append("Varaustila muuttui latauksen aikana alle 20 %-yksikköä, joten kapasiteettia ei voida "
                              "laskea luotettavasti. Aloita lataus mahdollisimman tyhjästä akusta.")
        return

    n = res["ajoneuvo"]["kennoryhmat"] or 96
    ah_full = ah_net / dsoc * 100
    v_low = profiles.mean_ocv(chem_key, 0, soc0) * n
    v_high = profiles.mean_ocv(chem_key, soc1, 100) * n
    e_below = ah_full * soc0 / 100 * v_low / 1000
    e_above = ah_full * max(0.0, 100 - soc1) / 100 * v_high / 1000
    e_full = e_chem + e_below + e_above
    cap.update({"ah_taysi": ah_full, "e_alapuoli_kwh": e_below, "e_ylapuoli_kwh": e_above,
                "taysi_kwh": e_full, "suora_kwh": e_chem / dsoc * 100, "valmis": True})

    # Rinnakkaisarvio lepojännitteistä (ei LFP)
    chem = profiles.chemistry(chem_key)
    if chem.get("ocv_soc_arvio") and cs_low and cs_high and \
            (rest0.get("kesto_min") or 0) >= 20 and (rest1.get("kesto_min") or 0) >= 20:
        so0 = profiles.ocv_to_soc(cs_low["ka_v"], chem_key)
        so1 = profiles.ocv_to_soc(cs_high["ka_v"], chem_key)
        if so0 is not None and so1 is not None and so1 - so0 > 20:
            cap["ocv_soc_alku"], cap["ocv_soc_loppu"] = so0, so1
            cap["ocv_kwh"] = e_chem / (so1 - so0) * 100

    # Epävarmuusarvio
    u_meas = 0.010 * e_full
    end_err = 0.3 if L.get("taysi") else 1.0
    u_soc = e_full * math.sqrt(1.0 ** 2 + end_err ** 2) / dsoc
    u_ext = 0.03 * (e_below + e_above)
    u_loss = 0.5 * e_loss if r_est else 0.01 * e_term
    u_gap = 0.10 * gap_kwh
    u = math.sqrt(u_meas ** 2 + u_soc ** 2 + u_ext ** 2 + u_loss ** 2 + u_gap ** 2)
    cap["epavarmuus_kwh"] = u
    cap["epavarmuus_osat"] = {"mittaus": u_meas, "varaustila": u_soc, "ekstrapolointi": u_ext,
                              "haviot": u_loss, "katkot": u_gap}
    if ref_kwh:
        cap["soh_pct"] = e_full / ref_kwh * 100
        cap["soh_epavarmuus_pct"] = u / ref_kwh * 100
    if buffer is not None:
        cap["kaytettava_kwh"] = e_full - buffer
    if nfp:
        cap["ero_bms_pct"] = (e_full - nfp) / nfp * 100

    # Mittauksen laatu
    q_points = []
    if dsoc >= 75:
        q_points.append(("Varaustilan muutos", True, f"{fmt(dsoc)} %-yks."))
    else:
        q_points.append(("Varaustilan muutos", dsoc >= 50, f"{fmt(dsoc)} %-yks."))
    q_points.append(("Lepo ennen latausta", (rest0.get("kesto_min") or 0) >= 20, f"{fmt(rest0.get('kesto_min'), 0)} min"))
    q_points.append(("Lepo latauksen jälkeen", (rest1.get("kesto_min") or 0) >= 20, f"{fmt(rest1.get('kesto_min'), 0)} min"))
    q_points.append(("Lataus täyteen", bool(L.get("taysi")), "kyllä" if L.get("taysi") else "ei"))
    if cnt_diff is not None:
        q_points.append(("Vastaa akunhallinnan latauslaskuria", abs(cnt_diff) <= 5 or cnt_used,
                         f"ero {fmt(cnt_diff)} %" + (", laskuri käytössä" if cnt_used else "")))
    q_points.append(("Katkoton mittausdata", not meta.get("aukot"), "kyllä" if not meta.get("aukot") else
                     f"{len(meta['aukot'])} katkoa"))
    tl = [x for x in (A.get("t_min"), A.get("t_max"), L.get("t_min"), L.get("t_max")) if x is not None]
    if tl:
        q_points.append(("Akun lämpötila", 15 <= min(tl) and max(tl) <= 35, f"{fmt(min(tl))}–{fmt(max(tl))} °C"))
    fails = sum(1 for _, ok, _ in q_points if not ok)
    cap["laatu"] = [{"nimi": a, "ok": b, "arvo": c} for a, b, c in q_points]
    cap["laatu_luokka"] = "Hyvä" if fails == 0 else ("Kohtalainen" if fails <= 2 else "Heikko")

    # Heikoin kennoryhmä matalassa varauksessa
    if cs_low and cs_low["lkm"] > 3:
        vs = [v for v in cs_low["jannitteet"] if v]
        med = statistics.median(vs)
        dev = (cs_low["min_v"] - med) * 1000
        cap["heikoin_ryhma"] = {"nro": cs_low["min_nro"], "poikkeama_mv": dev}


# ----------------------------------------------------------------------
def _summarize(res):
    ar = res["arviot"]
    cap = res.get("kapasiteetti") or {}
    bms = res.get("bms") or {}
    ref = res["viite"]["kwh"]
    km = res["ajoneuvo"].get("mittarilukema_km")
    summary = {}

    pt = res.get("paatulos") or {}
    if pt.get("valmis") and pt.get("soh_pct"):
        soh = pt["soh_pct"]
        summary.update(kunto_pct=soh, kunto_lahde=pt["lahde"], kapasiteetti_kwh=pt["taysi_kwh"],
                       epavarmuus_kwh=pt.get("epavarmuus_kwh"), epavarmuus_pct=pt.get("soh_epavarmuus_pct"))
    elif bms.get("soh_pct"):
        soh = bms["soh_pct"]
        summary.update(kunto_pct=soh, kunto_lahde="Akunhallinnan arvio", kapasiteetti_kwh=bms.get("nfp_kwh"))
    else:
        soh = None

    if soh is not None:
        luokka = soh_class(soh)
        summary["kunto_luokka"] = luokka
        ar.append({"nimi": "Akun kunto (SOH)", "arvo": f"{fmt(soh)} %", "luokka": luokka,
                   "kuvaus": f"Nykyinen kapasiteetti suhteessa alkuperäiseen ({fmt(ref)} kWh)."})
        exp = expected_loss_pct(km, ((res["ajoneuvo"].get("vin_tiedot") or {}).get("malli_koodi")))
        if exp is not None and km and km > 5000:
            actual_loss = 100 - soh
            diff = actual_loss - exp
            if diff < -3:
                verdict = "Parempi kuin keskimäärin"
            elif diff > 3:
                verdict = "Heikompi kuin keskimäärin"
            else:
                verdict = "Tavanomainen"
            summary["vertailu"] = {"odotettu_alenema_pct": exp, "toteutunut_alenema_pct": actual_loss,
                                   "arvio": verdict}
            ar.append({"nimi": "Ajomäärään suhteutettuna", "arvo": verdict,
                       "luokka": {"Parempi kuin keskimäärin": "Erinomainen", "Tavanomainen": "Hyvä",
                                  "Heikompi kuin keskimäärin": "Tyydyttävä"}[verdict],
                       "kuvaus": f"Kapasiteetin alenema {fmt(actual_loss)} %, keskimäärin noin {fmt(exp)} % "
                                 f"{fmt(km, 0)} km:n kohdalla."})

    if pt.get("valmis"):
        ar.append({"nimi": "Mitattu kapasiteetti", "arvo": f"{fmt(pt['taysi_kwh'])} kWh",
                   "luokka": None, "kuvaus": f"{pt['lahde']}. Epävarmuus noin ±{fmt(pt['epavarmuus_kwh'])} kWh. "
                                             f"Mittauksen luotettavuus: {(pt.get('laatu_luokka') or '–').lower()}."})
        if bms.get("nfp_kwh"):
            ar.append({"nimi": "Akunhallinnan arvio", "arvo": f"{fmt(bms['nfp_kwh'])} kWh", "luokka": None,
                       "kuvaus": f"Ero mitattuun {fmt(pt.get('ero_bms_pct'))} %."})

    cs = res.get("kennot")
    if cs:
        ar.append({"nimi": "Kennoryhmien jännite-ero", "arvo": f"{fmt(cs['ero_mv'], 0)} mV", "luokka": cs["luokka"],
                   "kuvaus": f"Suurin {fmt(cs['max_v'], 3)} V (ryhmä {cs['max_nro']}), "
                             f"pienin {fmt(cs['min_v'], 3)} V (ryhmä {cs['min_nro']})."})
        n_out = len(cs["poikkeavat"])
        ar.append({"nimi": "Poikkeavat kennoryhmät", "arvo": "Ei havaittu" if n_out == 0 else f"{n_out} kpl",
                   "luokka": "Erinomainen" if n_out == 0 else ("Tyydyttävä" if n_out == 1 else "Poikkeava"),
                   "kuvaus": "Yksikään kennoryhmä ei poikkea muista selvästi."
                             if n_out == 0 else ", ".join(f"ryhmä {p['nro']} ({fmt(p['poikkeama_mv'], 0)} mV)"
                                                         for p in cs["poikkeavat"][:6])})

    tk = res.get("takuu") or {}
    if tk:
        if tk.get("voimassa") is True:
            arvo, luokka = "Voimassa", "Hyvä"
            kuv = (f"Päättyy {tk['paattyy']} tai {fmt(tk['km'], 0)} km:n kohdalla, kumpi täyttyy ensin "
                   f"(jäljellä {fmt(tk['km_jaljella'], 0)} km). Takuu kattaa kapasiteetin laskun alle "
                   f"{tk['sailyvyys_pct']} %:n.")
        elif tk.get("voimassa") is False:
            arvo, luokka = "Päättynyt", None
            kuv = f"Takuu on {tk['vuotta']} vuotta tai {fmt(tk['km'], 0)} km, kumpi täyttyy ensin."
        else:
            arvo, luokka = "Ei arvioitu", None
            kuv = (f"Takuu on {tk['vuotta']} vuotta tai {fmt(tk['km'], 0)} km, kumpi täyttyy ensin. "
                   "Voimassaolo lasketaan, kun autolle syötetään käyttöönottopäivä.")
        ar.append({"nimi": "Akkutakuu", "arvo": arvo, "luokka": luokka, "kuvaus": kuv})

    low = res.get("kennot_matala")
    if low:
        lcls = delta_class(low["ero_mv"], low.get("soc"))
        hr = cap.get("heikoin_ryhma") or {}
        desc = f"Mitattu levossa {fmt(low.get('soc'))} %:n varauksessa ennen latausta."
        if hr.get("poikkeama_mv", 0) < -15:
            desc += f" Pienin jännite ryhmässä {hr['nro']} ({fmt(hr['poikkeama_mv'], 0)} mV mediaanista)."
        ar.append({"nimi": "Jännite-ero matalassa varauksessa", "arvo": f"{fmt(low['ero_mv'], 0)} mV",
                   "luokka": lcls, "kuvaus": desc})

    t = res.get("lampotilat") or {}
    if t.get("min") is not None:
        ok = 15 <= t["min"] and t["max"] <= 35
        ar.append({"nimi": "Akun lämpötila mittauksessa", "arvo": f"{fmt(t['min'])}–{fmt(t['max'])} °C",
                   "luokka": "Hyvä" if ok else "Tyydyttävä",
                   "kuvaus": "Vertailukelpoisella alueella." if ok else
                   "Lämpötila oli suositellun alueen (15–35 °C) ulkopuolella, mikä voi vaikuttaa tulokseen."})

    # Sanallinen yhteenveto
    parts = []
    if soh is not None:
        kwh = summary.get("kapasiteetti_kwh")
        src = "akunhallinnan arvio" if summary.get("kunto_lahde") == "Akunhallinnan arvio" else "mitattu"
        parts.append(f"Akun kapasiteetti on {fmt(soh, 1)} % alkuperäisestä ({src} {fmt(kwh)} kWh, "
                     f"uutena {fmt(ref)} kWh).")
        v = summary.get("vertailu")
        if v:
            parts.append({"Parempi kuin keskimäärin": "Tulos on ajomäärään nähden keskimääräistä parempi.",
                          "Tavanomainen": "Tulos on ajomäärään nähden tavanomainen.",
                          "Heikompi kuin keskimäärin": "Tulos on ajomäärään nähden keskimääräistä heikompi."}[v["arvio"]])
    if cs:
        txt = {"Erinomainen": "osoittaa akun olevan erinomaisessa tasapainossa",
               "Hyvä": "on tavanomaisella tasolla",
               "Tyydyttävä": "on hieman tavanomaista suurempi",
               "Poikkeava": "on selvästi tavanomaista suurempi ja kannattaa tarkistaa"}[cs["luokka"]]
        parts.append(f"Kennoryhmien jännite-ero levossa on {fmt(cs['ero_mv'], 0)} mV, mikä {txt}.")
        if cs["poikkeavat"]:
            parts.append("Poikkeavia kennoryhmiä havaittiin: " +
                         ", ".join(f"ryhmä {p['nro']}" for p in cs["poikkeavat"][:6]) + ".")
        else:
            parts.append("Täydessä akussa poikkeavia kennoryhmiä ei havaittu." if res.get("kennot_matala")
                         else "Poikkeavia kennoryhmiä ei havaittu.")
    hr = cap.get("heikoin_ryhma")
    if hr and hr["poikkeama_mv"] < -15:
        parts.append(f"Kennoryhmä {hr['nro']} on matalassa varauksessa {fmt(abs(hr['poikkeama_mv']), 0)} mV muita "
                     "alempana, mikä viittaa muita pienempään kapasiteettiin.")
    summary["teksti"] = " ".join(parts) if parts else "Mittauksesta ei saatu riittävästi tietoa arvion tekemiseen."
    if soh is not None:
        summary["tulkinta"] = interpretation(soh, cs, cap)
    res["yhteenveto"] = summary


def interpretation(soh, cs, cap) -> str:
    """Selkokielinen tulkinta ostajalle tai omistajalle."""
    if soh >= 90:
        t = "Akku on hyvässä kunnossa. Kapasiteettia on jäljellä lähes yhtä paljon kuin uutena."
    elif soh >= 85:
        t = "Akku on hyvässä kunnossa. Kapasiteetti on alentunut tavanomaisesti käytön myötä."
    elif soh >= 80:
        t = "Akku on käyttökunnossa, mutta kapasiteetti on alentunut selvästi uudesta."
    elif soh >= 70:
        t = "Akun kapasiteetti on alentunut huomattavasti. Toimintamatka on selvästi uutta lyhyempi."
    else:
        t = "Akun kapasiteetti on alle akkutakuun rajan. Akun kunto kannattaa selvittää valtuutetussa huollossa."
    t += f" Toimintamatka on noin {fmt(soh, 0)} % uuden auton toimintamatkasta samoissa olosuhteissa."
    if cs and cs["luokka"] in ("Tyydyttävä", "Poikkeava"):
        t += " Kennoryhmien jännite-ero on tavanomaista suurempi, joten akku kannattaa tarkistaa uudelleen täyden latauksen ja levon jälkeen."
    hr = (cap or {}).get("heikoin_ryhma")
    if hr and hr.get("poikkeama_mv", 0) < -50:
        t += f" Kennoryhmä {hr['nro']} poikkeaa muista matalassa varauksessa, ja sen kehitystä kannattaa seurata seuraavissa mittauksissa."
    return t


# ----------------------------------------------------------------------
def learn_vehicle(storage, tid: int, res: dict):
    test = storage.test(tid)
    vid = test["vehicle_id"]
    v = storage.vehicle(vid)
    if not v:
        return
    upd = {}
    veh = res.get("ajoneuvo", {})
    if not v.get("vin") and veh.get("vin"):
        upd["vin"] = veh["vin"]
    if veh.get("malli_id") and v.get("malli_id") != veh["malli_id"] and veh.get("tunnistus") != ["valittu käsin"]:
        upd["malli_id"] = veh["malli_id"]
    if not v.get("vuosimalli") and (veh.get("vin_tiedot") or {}).get("vuosimalli"):
        upd["vuosimalli"] = veh["vin_tiedot"]["vuosimalli"]
    if upd:
        storage.update_vehicle(vid, upd)
    learned = {
        "kennoryhmat": veh.get("kennoryhmat"),
        "energiamuoto": (res.get("bms") or {}).get("energiamuoto"),
        "kemia": veh.get("kemia"),
        "alusta": veh.get("alusta"),
        "viimeisin_kunto_pct": (res.get("yhteenveto") or {}).get("kunto_pct"),
        "viimeisin_mittaus": tid,
    }
    if res["viite"]["lahde"] == "Auton akunhallinta":
        learned["bol_kwh"] = res["viite"]["kwh"]
    storage.learn(vid, learned)
