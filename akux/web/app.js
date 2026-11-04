"use strict";
/* Akux – käyttöliittymä */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const view = $("#view");
let S = null;            // viimeisin /api/tila
let current = null;      // aktiivinen näkymä
let pollTimer = null;

// ---------- apufunktiot ----------
const ANDROID = !!window.AkuxAndroid;
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function n(x, d = 1) {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return Number(x).toLocaleString("fi-FI", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function date(ts, time = true) {
  if (!ts) return "–";
  const o = { day: "numeric", month: "numeric", year: "numeric" };
  if (time) Object.assign(o, { hour: "2-digit", minute: "2-digit" });
  return new Date(ts * 1000).toLocaleString("fi-FI", o);
}
function dur(s) {
  if (s == null) return "–";
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return `${h} h ${m} min`;
  if (m) return `${m} min ${String(sec).padStart(2, "0")} s`;
  return `${sec} s`;
}
function pillClass(l) {
  return { "Erinomainen": "good", "Hyvä": "info", "Tyydyttävä": "warn", "Heikentynyt": "bad",
    "Poikkeava": "bad", "Takuurajan alittava": "bad" }[l] || "";
}
function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (err ? " err" : "");
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.className = ""), err ? 5200 : 2600);
}
async function api(path, opts = {}) {
  const o = { method: opts.method || "GET", headers: {} };
  if (opts.body !== undefined) {
    o.body = JSON.stringify(opts.body);
    o.headers["Content-Type"] = "application/json";
  }
  const r = await fetch(path, o);
  let data = {};
  try { data = await r.json(); } catch (e) { /* tyhjä */ }
  if (!r.ok) throw new Error(data.virhe || `Virhe ${r.status}`);
  return data;
}
async function act(fn, okMsg) {
  try {
    const r = await fn();
    if (okMsg) toast(okMsg);
    return r;
  } catch (e) {
    toast(e.message, true);
    throw e;
  }
}
function form(el) {
  const o = {};
  $$("[name]", el).forEach(i => (o[i.name] = i.type === "checkbox" ? i.checked : i.value));
  return o;
}

// ---------- tilan haku ----------
async function poll() {
  try {
    S = await api("/api/tila");
    renderConn();
    if (current && current.update) current.update(S);
  } catch (e) {
    $(".conn-txt").textContent = "Ohjelma ei vastaa";
    $(".conn .dot").className = "dot";
  }
}
function renderConn() {
  const y = S.yhteys;
  const dot = $(".conn .dot");
  const busOk = S.vaylatesti && S.vaylatesti.kunnossa;
  dot.className = "dot " + (y.kaynnissa ? (busOk ? "ok" : "wait") : "");
  let txt = y.kaynnissa ? (y.simuloitu ? "Esittelytila" : y.tila) : "Ei yhteyttä";
  if (y.kaynnissa && !y.simuloitu && busOk) txt = "Auto yhdistetty";
  if (S.mittaus) txt += " · mittaus käynnissä";
  $(".conn-txt").textContent = txt;
}

// ---------- reititys ----------
const views = {};
function route() {
  const [name, arg] = (location.hash.replace(/^#\//, "") || "yleiskuva").split("/");
  const v = views[name] || views.yleiskuva;
  $$("#nav a").forEach(a => a.classList.toggle("active", a.dataset.v === name));
  current = v;
  view.innerHTML = "";
  v.render(arg);
  if (S && v.update) v.update(S);
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

// ---------- kennokaavio ----------
function cellSvg(volts) {
  const vals = volts.filter(Boolean);
  if (!vals.length) return `<div class="empty small">Kennojännitteitä ei vielä vastaanotettu.</div>`;
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  const dev = volts.map(v => (v ? (v - mean) * 1000 : 0));
  const lim = Math.max(5, ...dev.map(Math.abs)) * 1.15;
  const W = 960, H = 150, cnt = volts.length, bw = W / cnt;
  let bars = "";
  dev.forEach((d, i) => {
    const h = Math.abs(d) / lim * (H / 2 - 6);
    const y = d >= 0 ? H / 2 - h : H / 2;
    bars += `<rect x="${(i * bw + bw * .14).toFixed(1)}" y="${y.toFixed(1)}" width="${(bw * .72).toFixed(1)}" height="${Math.max(.8, h).toFixed(1)}" rx="1" fill="${Math.abs(d) > 15 ? "var(--bad)" : "var(--accent)"}"><title>Ryhmä ${i + 1}: ${volts[i] ? volts[i].toFixed(4).replace(".", ",") + " V" : "–"} (${d >= 0 ? "+" : ""}${n1(d)} mV)</title></rect>`;
  });
  return `<svg class="cells" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Kennoryhmien poikkeama keskiarvosta">
    <line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="var(--muted)" stroke-width="1"/>${bars}</svg>
    <div class="row small muted"><span>Ryhmä 1</span><span class="spacer"></span><span>Poikkeama keskiarvosta, asteikko ±${n(lim, 0)} mV</span><span class="spacer"></span><span>Ryhmä ${cnt}</span></div>`;
}
function n1(x) { return n(x, 1); }

// =====================================================================
// YLEISKUVA
// =====================================================================
views.yleiskuva = {
  render() {
    view.innerHTML = `
      <div class="head"><div><h1>Yleiskuva</h1><div class="muted">Yhteys autoon ja akun tiedot reaaliajassa</div></div></div>
      <div id="startCard"></div>
      <div id="connCard" class="card"></div>
      <div id="autoCard"></div>
      <div class="grid g4" style="margin-top:16px" id="stats"></div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Kennoryhmät</h2><div id="cellBox"></div></div>
        <div class="card"><h2>Yhteystesti</h2><div id="busBox"><div class="empty small">Yhdistä sovittimeen nähdäksesi, mitä tietoja autosta vastaanotetaan.</div></div></div>
      </div>`;
    this.connRendered = null;
    this.renderStart();
  },
  async renderStart() {
    const [st, { ajoneuvot }, { mittaukset }] = await Promise.all([api("/api/asetukset"), api("/api/ajoneuvot"), api("/api/mittaukset")]);
    const steps = [
      [!!st.yritys_nimi, "Täytä yrityksen tiedot raportteja varten", "#/asetukset"],
      [!!(S && S.yhteys.kaynnissa) || mittaukset.length > 0, "Yhdistä autoon tai kokeile esittelytilaa", null],
      [ajoneuvot.length > 0, "Lisää auto", "#/autot/uusi"],
      [mittaukset.some(m => m.tila === "valmis"), "Tee ensimmäinen pikatarkastus", "#/mittaus"],
    ];
    const box = $("#startCard");
    if (!box || steps.every(x => x[0])) { if (box) box.innerHTML = ""; return; }
    box.innerHTML = `<div class="card start"><h2>Käyttöönotto</h2><ol class="steps-list">${steps.map(([ok, t, h]) =>
      `<li class="${ok ? "done" : ""}"><span class="ic">${ok ? "✓" : ""}</span>${h && !ok ? `<a href="${h}">${t}</a>` : t}</li>`).join("")}</ol></div>`;
  },
  async renderConnCard() {
    const y = S.yhteys;
    const key = y.kaynnissa + ":" + y.simuloitu;
    if (this.connRendered === key) return this.updateConn();
    this.connRendered = key;
    const c = $("#connCard");
    if (!y.kaynnissa) {
      let ports = { portit: [], pyserial: true };
      try { ports = await api("/api/portit"); } catch (e) { /* */ }
      const opts = ports.portit.map(p => `<option value="${esc(p.laite)}">${esc(p.laite)} – ${esc(p.kuvaus)}${p.todennakoinen ? " (OBDLink)" : ""}</option>`).join("");
      c.innerHTML = `
        <h2>Yhdistä</h2>
        ${ports.pyserial ? "" : `<div class="notice warn">Sovittimen yhteysosa puuttuu ohjelmasta. Asenna ohjelma uudelleen.</div>`}
        ${ports.pyserial && !ports.portit.length ? `<div class="notice warn"><b>Sovitinta ei löytynyt.</b> Tarkista, että OBDLink on kytketty USB-kaapelilla. ${ports.windows ? "Windows asentaa sovittimen ajurin yleensä itse ensimmäisellä kytkentäkerralla, kun tietokone on verkossa. Odota hetki ja paina Päivitä portit. Jos sovitin ei vieläkään näy, asenna FTDI:n VCP-ajuri osoitteesta <b>ftdichip.com/drivers/vcp-drivers</b>." : ""}</div>` : ""}
        <div class="grid g2">
          <div>
            <label class="f"><span>${ANDROID ? "OBDLink-sovitin" : "OBDLink-sovittimen portti"}</span>
              <select id="port">${opts || `<option value="">Sovitinta ei löytynyt</option>`}</select></label>
            <div class="row"><button class="btn primary" id="bConnect" ${opts ? "" : "disabled"}>Yhdistä autoon</button>
              <button class="btn" id="bRefresh">Päivitä portit</button></div>
            <p class="small muted" style="margin-top:10px">${ANDROID ? "Kytke sovitin auton OBD-liitäntään ja USB-C-sovittimella puhelimeen. Kun Android kysyy lupaa käyttää sovitinta, valitse Salli." : "Kytke sovitin auton OBD-liitäntään ja tietokoneeseen."} Auton on oltava hereillä, esimerkiksi ovi avattuna tai ilmastointi päällä. <a href="#/ohjeet/yhdistaminen">Ohje</a></p>
          </div>
          <div>
            <label class="f"><span>Esittelytila ilman autoa</span></label>
            <p class="small muted">Simuloitu Model 3 Long Range 2020. Esittelytilassa voit kokeilla kaikkia toimintoja ja nähdä esimerkkiraportin. Aika kulkee nopeutettuna.</p>
            <button class="btn" id="bDemo">Käynnistä esittelytila</button>
          </div>
        </div>`;
      const sel = $("#port");
      if (S && sel && ports.portit.length) {
        api("/api/asetukset").then(s => { if (s.portti && [...sel.options].some(o => o.value === s.portti)) sel.value = s.portti; });
      }
      $("#bRefresh").onclick = () => { this.connRendered = null; this.renderConnCard(); };
      $("#bConnect").onclick = () => act(() => api("/api/yhdista", { method: "POST", body: { tyyppi: "obdlink", portti: $("#port").value } }), "Yhdistetään…").then(poll);
      $("#bDemo").onclick = () => act(() => api("/api/yhdista", { method: "POST", body: { tyyppi: "demo", soc: 12, nopeutus: 60 } }), "Esittelytila käynnistetty").then(poll);
    } else {
      c.innerHTML = `
        <div class="row"><div><h2 style="margin:0">${y.simuloitu ? "Esittelytila" : "Yhdistetty sovittimeen"}</h2>
          <div class="small muted" id="connInfo"></div><div class="notice warn small" id="connErr" hidden style="margin:8px 0 0"></div></div><span class="spacer"></span>
          <button class="btn" id="bDisc">Katkaise yhteys</button></div>
        ${y.simuloitu ? demoControls() : ""}`;
      $("#bDisc").onclick = () => {
        if (S.mittaus && !confirm("Mittaus on käynnissä. Yhteyden katkaisu keskeyttää sen. Jatketaanko?")) return;
        act(() => api("/api/katkaise", { method: "POST" }), "Yhteys katkaistu").then(poll);
      };
      bindDemo(c);
      this.updateConn();
    }
  },
  updateConn() {
    const y = S.yhteys, el = $("#connInfo");
    if (!el) return;
    const t = y.tiedot || {};
    el.textContent = [y.tila, t.sovitin, t.portti && t.portti !== "-" ? t.portti : null, S.vaylatesti ? `${n(S.vaylatesti.kehyksia, 0)} viestiä vastaanotettu` : null].filter(Boolean).join(" · ");
    const er = $("#connErr");
    if (er) {
      const msg = y.virhe && !S.vaylatesti ? y.virhe : "";
      er.textContent = msg;
      er.hidden = !msg;
    }
    updateDemo();
  },
  update(S) {
    this.renderConnCard();
    const L = S.live || {};
    const st = $("#stats");
    if (!S.yhteys.kaynnissa) {
      st.innerHTML = "";
      $("#autoCard").innerHTML = "";
      $("#cellBox").innerHTML = `<div class="empty small">Ei yhteyttä.</div>`;
      return;
    }
    const soh = L.nfp_kwh && L.bol_kwh ? L.nfp_kwh / L.bol_kwh * 100 : null;
    st.innerHTML = [
      stat("Varaustila", L.soc_ui != null ? n(L.soc_ui) : "–", "%", L.soc_avg != null ? `Kennojen keskiarvo ${n(L.soc_avg)} %` : ""),
      stat("Akun jännite", L.pack_v != null ? n(L.pack_v) : "–", "V", L.pack_i != null ? `Virta ${n(L.pack_i)} A` : ""),
      stat("Teho", L.power_kw != null ? n(Math.abs(L.power_kw)) : "–", "kW", L.power_kw == null ? "" : (L.power_kw < -0.3 ? "Lataus" : (L.power_kw > 0.3 ? "Purku" : "Levossa"))),
      stat("Akun lämpötila", L.temp_min != null ? `${n(L.temp_min)}–${n(L.temp_max)}` : "–", "°C", ""),
      stat("Täyden akun energia", L.nfp_kwh != null ? n(L.nfp_kwh) : "–", "kWh", L.bol_kwh ? `Uutena ${n(L.bol_kwh)} kWh` : "Akunhallinnan arvio"),
      stat("Kunto (akunhallinta)", soh != null ? n(soh) : "–", "%", "Pikatarkastus tallentaa arvon"),
      stat("Kennoryhmien ero", L.brick_delta_mv != null ? n(L.brick_delta_mv, 0) : "–", "mV", L.bricks_seen ? `${L.bricks_seen}/${L.brick_count || "–"} ryhmää luettu` : ""),
      stat("Mittarilukema", L.odometer_km != null ? n(L.odometer_km, 0) : "–", "km", L.vin || ""),
    ].join("");
    // tunnistettu auto
    const ac = $("#autoCard");
    if (L.vin && !S.auto_tunnettu) {
      if (ac.dataset.vin !== L.vin) {
        ac.dataset.vin = L.vin;
        ac.innerHTML = `<div class="notice" style="margin-top:16px"><div class="row"><div><b>Autoa ei ole vielä tallennettu.</b> Valmistenumero ${esc(L.vin)} luettiin autosta.</div>
          <span class="spacer"></span><a class="btn primary sm" href="#/autot/uusi">Lisää auto</a></div></div>`;
      }
    } else if (S.auto_tunnettu) {
      if (ac.dataset.known !== String(S.auto_tunnettu.id)) {
        ac.dataset.known = S.auto_tunnettu.id;
        ac.dataset.vin = "";
        ac.innerHTML = `<div class="notice good" style="margin-top:16px"><div class="row"><div><b>${esc(S.auto_tunnettu.nimi)}</b> tunnistettiin valmistenumerosta.</div>
          <span class="spacer"></span><a class="btn sm" href="#/autot/${S.auto_tunnettu.id}">Auton tiedot</a>
          <a class="btn primary sm" href="#/mittaus">${S.mittaus ? "Näytä mittaus" : "Aloita mittaus"}</a></div></div>`;
      }
    } else { ac.innerHTML = ""; ac.dataset.vin = ""; ac.dataset.known = ""; }
    // kennot
    if (!this._cellT || Date.now() - this._cellT > 2000) {
      this._cellT = Date.now();
      api("/api/kennot").then(r => { const b = $("#cellBox"); if (b) b.innerHTML = cellSvg(r.kennot); });
    }
    // väylätesti
    const vt = S.vaylatesti;
    if (vt) {
      $("#busBox").innerHTML = `
        ${vt.kunnossa ? `<div class="notice good">Kaikki mittauksessa tarvittavat tiedot vastaanotetaan.</div>` :
          `<div class="notice warn"><b>Puuttuu:</b> ${esc(vt.puuttuvat.join(", "))}. Odota hetki. Jos tieto ei ilmesty minuutin kuluessa, auto ei lähetä sitä tähän liitäntään.</div>`}
        <table class="t ${this.tech ? "tech" : ""}"><tr><th>Tieto</th><th class="techcol">Tunniste</th><th class="num techcol">Taajuus</th><th></th></tr>
        ${vt.viestit.map(r => `<tr><td>${esc(r.kuvaus)}${r.pakollinen ? "" : ' <span class="muted small">(lisätieto)</span>'}</td><td class="muted techcol">${r.tunniste}</td>
          <td class="num techcol">${r.taajuus_hz ? n(r.taajuus_hz, 1) + " Hz" : "–"}</td>
          <td class="num">${r.nakyy ? '<span class="pill good">Vastaanotetaan</span>' : (r.pakollinen ? '<span class="pill warn">Ei näy</span>' : '<span class="pill">Ei näy</span>')}</td></tr>`).join("")}
        </table>
        <div class="row" style="margin-top:10px"><button class="btn sm" id="techT" type="button">${this.tech ? "Piilota tekniset tiedot" : "Näytä tekniset tiedot"}</button></div>`;
      $("#techT").onclick = () => { this.tech = !this.tech; this.update(S); };
    }
  },
};
function stat(l, v, u, sub) {
  return `<div class="card stat"><div class="lbl">${esc(l)}</div><div class="val">${v}<small>${u}</small></div><div class="sub">${esc(sub)}</div></div>`;
}
function demoControls() {
  return `<div class="card demo" style="margin-top:14px;padding:12px 14px">
    <div class="row small"><b>Esittelytilan ohjaus</b><span class="muted" id="demoState"></span></div>
    <div class="row" style="margin-top:8px">
      <button class="btn sm" data-d="park">Pysäköity</button>
      <button class="btn sm" data-d="drive">Ajo</button>
      <button class="btn sm" data-d="charge" data-p="7">Lataus 7 kW</button>
      <button class="btn sm" data-d="charge" data-p="11">Lataus 11 kW</button>
      <span class="spacer"></span>
      <label class="small muted">Nopeutus <select id="demoAcc" style="width:auto;padding:4px 8px">
        <option value="1">1×</option><option value="10">10×</option><option value="60">60×</option><option value="300">300×</option><option value="600">600×</option></select></label>
    </div></div>`;
}
function bindDemo(root) {
  $$("[data-d]", root).forEach(b => (b.onclick = () => act(() => api("/api/demo", { method: "POST", body: { tila: b.dataset.d, teho: b.dataset.p ? Number(b.dataset.p) : undefined } })).then(poll)));
  const acc = $("#demoAcc", root);
  if (acc) acc.onchange = () => act(() => api("/api/demo", { method: "POST", body: { nopeutus: Number(acc.value) } }), "Nopeutus muutettu");
}
function updateDemo() {
  const d = S.yhteys.demo, el = $("#demoState");
  if (!d || !el) return;
  el.textContent = " · " + ({ park: "pysäköity", drive: "ajossa", charge: "latauksessa", sleep: "lepotilassa" }[d.tila] || d.tila);
  const acc = $("#demoAcc");
  if (acc && document.activeElement !== acc) acc.value = String(d.nopeutus);
}

// =====================================================================
// MITTAUS
// =====================================================================
const PHASE_TEXT = {
  keruu: ["Tietoja luetaan", "Ohjelma lukee akunhallinnan tiedot ja kaikkien kennoryhmien jännitteet. Pidä auto paikallaan. Tarkastus kestää yleensä 1–3 minuuttia."],
  lepo_alku: ["Akku lepää ennen latausta", "Pidä auto pysäköitynä ja hereillä, esimerkiksi ilmastointi päällä tai Leiriytymistila käytössä, jotta sovitin saa virtaa. Lepo tasaa kennojännitteet ja antaa tarkan lähtötason. Jos kytket latauksen jo nyt, mittaus siirtyy suoraan lataukseen."],
  odota_lataus: ["Aloita lataus", "Aseta latausrajaksi 100 % Tesla-sovelluksessa tai auton näytöllä. Kytke latauskaapeli ja aloita lataus. Käytä tavallista vaihtovirtalatausta, enintään 11 kW. Pikalatausta ei käytetä, koska suuri virta lisää häviöitä ja lämpenemistä. Ohjelma tunnistaa latauksen alkamisen itse."],
  lataus: ["Lataus käynnissä", "Mittaus jatkuu itsestään, kunnes akunhallinta ilmoittaa akun täydeksi. Älä irrota sovitinta. Tietokone saa jäädä autoon, kunhan se ei mene lepotilaan."],
  lepo_loppu: ["Akku lepää latauksen jälkeen", "Lataus on valmis. Älä käytä autoa lepojakson aikana. Kennojännitteet tasaantuvat, ja lopulliset arvot tallennetaan raporttia varten."],
  valmis: ["Valmis", "Mittaus on valmis."],
};

views.mittaus = {
  render() {
    view.innerHTML = `<div class="head"><div><h1>Mittaus</h1><div class="muted" id="mSub">Pikatarkastus tai kapasiteettimittaus</div></div></div><div id="mBody"></div>`;
    this.mode = null;
  },
  async update(S) {
    if (S.mittaus) {
      if (this.mode !== "active") { this.mode = "active"; this.renderActive(); }
      this.updateActive(S);
    } else {
      if (this.mode === "active") {
        const last = this.lastId;
        this.mode = null;
        if (last) { location.hash = `#/mittaukset/${last}`; return; }
      }
      if (this.mode !== "new") { this.mode = "new"; await this.renderNew(); }
      this.updateNew(S);
    }
  },
  async renderNew() {
    const { ajoneuvot } = await api("/api/ajoneuvot");
    const s = await api("/api/asetukset");
    const known = S && S.auto_tunnettu ? S.auto_tunnettu.id : null;
    const b = $("#mBody");
    if (!ajoneuvot.length) {
      b.innerHTML = `<div class="card empty"><p>Lisää ensin auto. Ohjelma tunnistaa mallin valmistenumerosta.</p><a class="btn primary" href="#/autot/uusi">Lisää auto</a></div>`;
      return;
    }
    b.innerHTML = `
      <div id="mWarn"></div>
      <div class="card">
        <h2>1. Valitse auto</h2>
        <select id="mVeh">${ajoneuvot.map(v => `<option value="${v.id}" ${v.id === known ? "selected" : ""}>${esc(v.nimi)}${v.rekisteri ? " · " + esc(v.rekisteri) : ""}${v.vin ? " · " + esc(v.vin) : ""}</option>`).join("")}</select>
        <div id="mVehHint" class="small muted" style="margin-top:8px"></div>
      </div>
      <div class="card">
        <h2>2. Valitse mittaus</h2>
        <div class="choice">
          <button data-t="pikatarkastus"><div class="ttl">Pikatarkastus</div>
            <div class="small muted">Akunhallinnan kapasiteettiarvio, kaikkien kennoryhmien jännitteet, lämpötilat ja elinkaaritiedot. Sopii esimerkiksi kauppatilanteeseen.</div>
            <div class="dur">Kesto noin 1–3 minuuttia</div></button>
          <button data-t="kapasiteetti"><div class="ttl">Kapasiteettimittaus</div>
            <div class="small muted">Akun todellinen kapasiteetti mitattuna latauksen aikana. Aloita mahdollisimman tyhjästä akusta, enintään ${esc(s.kapasiteetti_lahto_soc_max)} %:n varauksesta.</div>
            <div class="dur">Kesto latauksen pituus ja lepojaksot, yleensä 8–14 tuntia</div></button>
        </div>
      </div>
      <div class="card">
        <h2>3. Tiedot raporttiin</h2>
        <div class="grid g3">
          <label class="f"><span>Mittarilukema (km)</span><input id="mOdo" inputmode="numeric" placeholder="Luetaan autosta, jos tyhjä"></label>
          <label class="f"><span>Mittaaja</span><input id="mWho" value="${esc(s.mittaaja)}"></label>
          <label class="f"><span>Lisätiedot</span><input id="mNote" placeholder="Esimerkiksi tilaajan nimi"></label>
        </div>
        <div class="row"><button class="btn primary" id="mStart" disabled>Aloita mittaus</button><span class="small muted" id="mStartHint"></span></div>
      </div>`;
    const vs = Object.fromEntries(ajoneuvot.map(v => [v.id, v]));
    const hint = () => {
      const v = vs[$("#mVeh").value];
      if (!v) return;
      const o = v.opitut || {};
      $("#mVehHint").innerHTML = [v.malli ? esc(v.malli) : "Malli tunnistetaan ensimmäisessä mittauksessa",
        o.bol_kwh ? `alkuperäinen kapasiteetti ${n(o.bol_kwh)} kWh` : null,
        o.viimeisin_kunto_pct ? `edellinen kunto ${n(o.viimeisin_kunto_pct)} %` : "ei aiempia mittauksia"].filter(Boolean).join(" · ");
    };
    $("#mVeh").onchange = hint; hint();
    $$(".choice button").forEach(btn => (btn.onclick = () => {
      $$(".choice button").forEach(x => x.classList.remove("sel"));
      btn.classList.add("sel");
      this.type = btn.dataset.t;
      this.updateNew(S);
    }));
    this.type = null;
    $("#mStart").onclick = () => act(() => api("/api/mittaukset", { method: "POST", body: {
      ajoneuvo_id: Number($("#mVeh").value), tyyppi: this.type, mittarilukema: $("#mOdo").value,
      mittaaja: $("#mWho").value, lisatiedot: $("#mNote").value } }), "Mittaus aloitettu").then(poll);
  },
  updateNew(S) {
    const w = $("#mWarn"), st = $("#mStart");
    if (!w || !st) return;
    let msg = "";
    if (!S.yhteys.kaynnissa) msg = `<div class="notice warn"><b>Ei yhteyttä autoon.</b> Yhdistä sovittimeen <a href="#/yleiskuva">Yleiskuva</a>-sivulla.</div>`;
    else if (!S.vaylatesti || !S.vaylatesti.kunnossa) msg = `<div class="notice warn">Odotetaan akun tietoja autosta…</div>`;
    else if (this.type === "kapasiteetti" && S.live.soc_ui > 15) msg = `<div class="notice warn">Akun varaus on ${n(S.live.soc_ui)} %. Tarkin tulos saadaan, kun lataus aloitetaan enintään 15 %:n varauksesta. Voit silti aloittaa mittauksen.</div>`;
    if (w.innerHTML !== msg) w.innerHTML = msg;
    const ready = S.yhteys.kaynnissa && S.vaylatesti && S.vaylatesti.kunnossa && this.type;
    st.disabled = !ready;
    $("#mStartHint").textContent = !this.type ? "Valitse mittauksen tyyppi." : "";
  },
  renderActive() {
    $("#mBody").innerHTML = `
      <div class="steps" id="aSteps"></div>
      <div class="grid g2">
        <div class="card"><h2 id="aTitle"></h2><p id="aText"></p><div id="aProg"></div>
          <div class="row" style="margin-top:14px"><button class="btn" id="aSkip"></button><span class="spacer"></span><button class="btn danger" id="aCancel">Keskeytä mittaus</button></div>
        </div>
        <div class="card"><h2>Tarkistukset</h2><ul class="checks" id="aChecks"></ul>
          <h3>Mittaus</h3><dl class="kv" id="aKv"></dl></div>
      </div>
      <div id="aDemo"></div>
      <div class="card"><h2>Huomiot</h2><div id="aNotes" class="small muted">Ei huomioita.</div></div>`;
    $("#aCancel").onclick = () => {
      if (!confirm("Keskeytetäänkö mittaus? Keskeytetystä mittauksesta ei tehdä raporttia.")) return;
      act(() => api("/api/mittaukset/aktiivinen/keskeyta", { method: "POST" }), "Mittaus keskeytetty").then(() => { this.lastId = null; poll(); });
    };
    $("#aSkip").onclick = () => {
      const v = S.mittaus.vaihe;
      const q = { lepo_alku: "Lyhennetäänkö lepojakso? Lyhyt lepo heikentää tuloksen tarkkuutta.",
        lataus: "Lopetetaanko lataus tähän? Kapasiteetti lasketaan siihen asti mitatusta osuudesta.",
        lepo_loppu: "Lopetetaanko lepojakso ja tehdäänkö raportti nyt?", keruu: "Lopetetaanko tietojen keruu nyt?" }[v];
      if (q && !confirm(q)) return;
      act(() => api("/api/mittaukset/aktiivinen/ohita", { method: "POST" })).then(poll);
    };
    if (S.yhteys.simuloitu) { $("#aDemo").innerHTML = demoControls(); bindDemo($("#aDemo")); }
  },
  updateActive(S) {
    const m = S.mittaus, L = S.live;
    this.lastId = m.test_id;
    $("#mSub").textContent = (m.tyyppi === "kapasiteetti" ? "Kapasiteettimittaus" : "Pikatarkastus") + ` · kesto ${dur(m.kesto_s)}`;
    const idx = m.vaiheet.findIndex(v => v.id === m.vaihe);
    $("#aSteps").innerHTML = m.vaiheet.map((v, i) => `<div class="s ${i < idx ? "done" : (i === idx ? "now" : "")}">${i + 1}. ${esc(v.nimi)}</div>`).join("");
    const [ttl, txt] = PHASE_TEXT[m.vaihe] || ["", ""];
    $("#aTitle").textContent = ttl;
    $("#aText").textContent = txt;
    let prog = "";
    if (m.lepo_tavoite_s) {
      const p = Math.min(100, m.lepo_s / m.lepo_tavoite_s * 100);
      prog = `<div class="row small"><span>Lepoaika ${dur(m.lepo_s)}</span><span class="spacer"></span><span class="muted">tavoite ${dur(m.lepo_tavoite_s)}</span></div><div class="bar"><i style="width:${p}%"></i></div>
        ${m.lepo_s === 0 ? `<p class="small muted" style="margin-top:8px">Lepoaika alkaa, kun akun virta on alle 3 A.</p>` : ""}`;
    } else if (m.vaihe === "lataus") {
      const p = L.soc_avg || 0;
      prog = `<div class="row small"><span>Varaus ${n(L.soc_ui)} %</span><span class="spacer"></span><span class="muted">alussa ${n(m.lataus_alku_soc)} %</span></div><div class="bar"><i style="width:${p}%"></i></div>
        <div class="grid g3" style="margin-top:14px">
          ${miniStat("Akkuun ladattu", n(m.lataus_kwh, 2), "kWh")}
          ${miniStat("Teho", L.power_kw != null ? n(Math.abs(L.power_kw)) : "–", "kW")}
          ${miniStat("Alustava kapasiteetti", m.arvio_taysi_kwh ? n(m.arvio_taysi_kwh) : "–", "kWh")}
        </div>${m.tauko ? `<div class="notice warn" style="margin-top:12px">Lataus on keskeytynyt. Mittaus jatkuu, kun lataus jatkuu.</div>` : ""}`;
    } else if (m.vaihe === "keruu") {
      const p = m.kennot_yht ? m.kennot_luettu / m.kennot_yht * 100 : 0;
      prog = `<div class="row small"><span>Kennoryhmiä luettu ${m.kennot_luettu}/${m.kennot_yht || "–"}</span></div><div class="bar"><i style="width:${p}%"></i></div>`;
    } else if (m.vaihe === "odota_lataus") {
      prog = `<div class="notice">Odotetaan latauksen alkamista. Varaus nyt ${n(L.soc_ui)} %.</div>`;
    }
    $("#aProg").innerHTML = prog;
    const skip = { lepo_alku: "Lyhennä lepoa", lataus: "Lopeta lataus tähän", lepo_loppu: "Valmis nyt", keruu: "Valmis nyt" }[m.vaihe];
    $("#aSkip").style.display = skip ? "" : "none";
    $("#aSkip").textContent = skip || "";
    $("#aChecks").innerHTML = m.tarkistukset.map(c => `<li><span class="ic ${c.ok === true ? "ok" : (c.ok === false ? "no" : "na")}">${c.ok === true ? "✓" : (c.ok === false ? "!" : "·")}</span>
      <div style="flex:1"><div class="row"><span>${esc(c.nimi)}</span><span class="spacer"></span><b>${esc(c.arvo)}</b></div>${c.ohje ? `<div class="small muted">${esc(c.ohje)}</div>` : ""}</div></li>`).join("");
    $("#aKv").innerHTML = `<dt>Varaus</dt><dd>${n(L.soc_ui)} %</dd><dt>Jännite</dt><dd>${n(L.pack_v)} V</dd><dt>Virta</dt><dd>${n(L.pack_i)} A</dd>
      <dt>Energia akkuun</dt><dd>${n(m.e_in_kwh, 2)} kWh</dd><dt>Energia akusta</dt><dd>${n(m.e_out_kwh, 2)} kWh</dd>
      <dt>Kennoryhmien ero</dt><dd>${n(L.brick_delta_mv, 0)} mV</dd>`;
    $("#aNotes").innerHTML = m.huomiot.length ? m.huomiot.map(esc).join("<br>") : "Ei huomioita.";
    if (S.yhteys.simuloitu) updateDemo();
  },
};
function miniStat(l, v, u) {
  return `<div class="stat"><div class="lbl">${l}</div><div class="val" style="font-size:20px">${v}<small>${u}</small></div></div>`;
}

// =====================================================================
// AUTOT
// =====================================================================
views.autot = {
  render(arg) {
    if (arg === "uusi") return this.renderForm(null);
    if (arg) return this.renderOne(Number(arg));
    this.renderList();
  },
  async renderList() {
    view.innerHTML = `<div class="head"><div><h1>Autot</h1><div class="muted">Tallennetut autot ja niiden mittaushistoria</div></div><a class="btn primary" href="#/autot/uusi">Lisää auto</a></div><div class="card" id="vList"></div>`;
    const { ajoneuvot } = await api("/api/ajoneuvot");
    $("#vList").innerHTML = ajoneuvot.length ? `<table class="t"><tr><th>Auto</th><th class="hide-m">Valmistenumero</th><th>Rekisteri</th><th class="num">Kunto</th><th class="num hide-m">Mittauksia</th><th class="hide-m">Viimeisin</th></tr>
      ${ajoneuvot.map(v => `<tr class="click" data-id="${v.id}"><td><b>${esc(v.nimi)}</b><div class="small muted">${esc(v.malli || "Malli tunnistetaan mittauksessa")}</div></td>
        <td class="hide-m">${esc(v.vin || "–")}</td><td>${esc(v.rekisteri || "–")}</td>
        <td class="num">${v.opitut && v.opitut.viimeisin_kunto_pct ? n(v.opitut.viimeisin_kunto_pct) + " %" : "–"}</td>
        <td class="num hide-m">${v.mittauksia}</td><td class="hide-m">${date(v.viimeisin, false)}</td></tr>`).join("")}</table>`
      : `<div class="empty">Ei tallennettuja autoja.</div>`;
    $$("tr.click").forEach(r => (r.onclick = () => (location.hash = `#/autot/${r.dataset.id}`)));
  },
  async renderForm(v) {
    const { mallit } = await api("/api/mallit");
    const live = S && S.live && S.live.vin && !S.auto_tunnettu ? S.live.vin : "";
    view.innerHTML = `<div class="head"><div><h1>${v ? "Muokkaa autoa" : "Lisää auto"}</h1><div class="muted">Malli tunnistetaan valmistenumerosta. Tarkentuneet tiedot tallentuvat autolle ensimmäisen mittauksen jälkeen.</div></div></div>
      <div class="grid g2">
        <div class="card" id="vForm">
          <label class="f"><span>Valmistenumero (VIN)</span><div class="row" style="flex-wrap:nowrap"><input name="vin" value="${esc(v ? v.vin || "" : live)}" maxlength="17" style="text-transform:uppercase">
            ${S && S.live && S.live.vin ? `<button class="btn sm" id="vRead" type="button">Lue autosta</button>` : ""}</div></label>
          <div class="grid g2">
            <label class="f"><span>Nimi</span><input name="nimi" value="${esc(v ? v.nimi : "")}" placeholder="Esimerkiksi Oma Model 3"></label>
            <label class="f"><span>Rekisterinumero</span><input name="rekisteri" value="${esc(v ? v.rekisteri || "" : "")}"></label>
            <label class="f"><span>Omistaja tai tilaaja</span><input name="omistaja" value="${esc(v ? v.omistaja || "" : "")}"></label>
            <label class="f"><span>Vuosimalli</span><input name="vuosimalli" inputmode="numeric" value="${esc(v ? v.vuosimalli || "" : "")}"></label>
            <label class="f"><span>Käyttöönottopäivä</span><input name="kayttoonotto" value="${esc(v ? v.kayttoonotto || "" : "")}" placeholder="pp.kk.vvvv"><small class="muted">Rekisteriotteesta. Tarvitaan akkutakuun laskemiseen.</small></label>
            <label class="f"><span>Väri</span><input name="vari" value="${esc(v ? v.vari || "" : "")}"></label>
          </div>
          <label class="f"><span>Mallipohja</span><select name="malli_id"><option value="">Tunnista automaattisesti</option>
            ${mallit.map(m => `<option value="${m.id}" ${v && v.malli_id === m.id ? "selected" : ""}>${esc(m.nimi)}</option>`).join("")}</select></label>
          <label class="f"><span>Alkuperäinen kapasiteetti (kWh), jos tiedossa</span><input name="viite_kayttaja" inputmode="decimal" value="${esc(v && v.opitut && v.opitut.viite_kayttaja ? String(v.opitut.viite_kayttaja).replace(".", ",") : "")}" placeholder="Luetaan auton akunhallinnasta"></label>
          <label class="f"><span>Lisätiedot</span><textarea name="lisatiedot">${esc(v ? v.lisatiedot || "" : "")}</textarea></label>
          <div class="row"><button class="btn primary" id="vSave">${v ? "Tallenna" : "Lisää auto"}</button><a class="btn" href="#/autot${v ? "/" + v.id : ""}">Peruuta</a></div>
        </div>
        <div class="card"><h2>Tunnistus</h2><div id="vInfo" class="small muted">Syötä valmistenumero.</div></div>
      </div>`;
    const vinInput = $("[name=vin]");
    const decode = async () => {
      const val = vinInput.value.trim();
      if (val.length < 17) { $("#vInfo").innerHTML = "Valmistenumerossa on 17 merkkiä."; return; }
      const r = await api("/api/vin", { method: "POST", body: { vin: val } });
      const t = r.tiedot;
      if (!t.kelvollinen) { $("#vInfo").innerHTML = `<div class="notice warn">${esc(t.virheet.join(" "))}</div>`; return; }
      $("#vInfo").innerHTML = `<dl class="kv"><dt>Valmistaja</dt><dd>${esc(t.valmistaja)}</dd><dt>Malli</dt><dd>${esc(t.malli)}</dd>
        <dt>Vuosimalli</dt><dd>${esc(t.vuosimalli || "–")}</dd><dt>Tehdas</dt><dd>${esc(t.tehdas || "–")}</dd>
        <dt>Voimalinja</dt><dd>${esc(t.voimalinja || "–")}</dd><dt>Akku</dt><dd>${esc(t.akkutyyppi || "–")}</dd></dl>
        ${r.malli ? `<div class="notice" style="margin-top:14px">Todennäköinen mallipohja: <b>${esc(r.malli.nimi)}</b>. Viitekapasiteetti ${n(r.malli.viite_kwh)} kWh, ${esc(r.malli.kemia)}, ${r.malli.sarjakennot} kennoryhmää.
          <div class="small muted">Peruste: ${esc(r.perusteet.join(", "))}. Ensimmäinen mittaus varmistaa tiedot auton akunhallinnasta.</div></div>` : ""}`;
      const yr = $("[name=vuosimalli]");
      if (!yr.value && t.vuosimalli) yr.value = t.vuosimalli;
    };
    vinInput.oninput = () => { vinInput.value = vinInput.value.toUpperCase(); if (vinInput.value.length === 17) decode(); };
    if (vinInput.value.length === 17) decode();
    const rb = $("#vRead");
    if (rb) rb.onclick = () => { vinInput.value = S.live.vin; decode(); };
    $("#vSave").onclick = () => {
      const body = form($("#vForm"));
      const p = v ? api(`/api/ajoneuvot/${v.id}`, { method: "PUT", body }) : api("/api/ajoneuvot", { method: "POST", body });
      act(() => p, "Tallennettu").then(r => (location.hash = `#/autot/${v ? v.id : r.id}`));
    };
  },
  async renderOne(id) {
    const v = await api(`/api/ajoneuvot/${id}`);
    if (location.hash.endsWith("/muokkaa")) return;
    const o = v.opitut || {};
    const m = v.malli || {};
    view.innerHTML = `<div class="head"><div><h1>${esc(v.nimi)}</h1><div class="muted">${esc(m.nimi || "Malli tunnistetaan ensimmäisessä mittauksessa")}</div></div>
      <div class="row"><button class="btn" id="vEdit">Muokkaa</button><a class="btn primary" href="#/mittaus">Uusi mittaus</a></div></div>
      ${!v.mittaukset.length ? `<div class="notice"><b>Seuraava vaihe:</b> tee autolle pikatarkastus. Ohjelma lukee silloin akunhallinnasta alkuperäisen kapasiteetin, kennoryhmien määrän ja akun tyypin ja tallentaa ne autolle.</div>` : ""}
      <div class="grid g2">
        <div class="card"><h2>Perustiedot</h2><dl class="kv">
          <dt>Valmistenumero</dt><dd>${esc(v.vin || "–")}</dd><dt>Rekisteri</dt><dd>${esc(v.rekisteri || "–")}</dd>
          <dt>Omistaja</dt><dd>${esc(v.omistaja || "–")}</dd><dt>Vuosimalli</dt><dd>${esc(v.vuosimalli || "–")}</dd>
          <dt>Käyttöönotto</dt><dd>${esc(v.kayttoonotto || "–")}</dd>
          <dt>Tehdas</dt><dd>${esc((v.vin_tiedot || {}).tehdas || "–")}</dd><dt>Voimalinja</dt><dd>${esc((v.vin_tiedot || {}).voimalinja || "–")}</dd></dl></div>
        <div class="card"><h2>Akku</h2><dl class="kv">
          <dt>Kemia</dt><dd>${esc(m.kemia || o.kemia || "–")}</dd><dt>Kennovalmistaja</dt><dd>${esc(m.kennovalmistaja || "–")}</dd>
          <dt>Kennoryhmiä</dt><dd>${esc(o.kennoryhmat || m.sarjakennot || "–")}${o.kennoryhmat ? " (mitattu)" : (m.sarjakennot ? " (mallipohja)" : "")}</dd>
          <dt>Alkuperäinen kapasiteetti</dt><dd>${o.bol_kwh ? n(o.bol_kwh) + " kWh (akunhallinta)" : (o.viite_kayttaja ? n(o.viite_kayttaja) + " kWh (ilmoitettu)" : (m.viite_kwh ? n(m.viite_kwh) + " kWh (mallitaulukko)" : "–"))}</dd>
          <dt>Viimeisin kunto</dt><dd>${o.viimeisin_kunto_pct ? n(o.viimeisin_kunto_pct) + " %" : "–"}</dd></dl></div>
      </div>
      <div class="card"><h2>Mittaukset</h2>${testTable(v.mittaukset)}</div>
      <div class="row" style="margin-top:16px"><span class="spacer"></span><button class="btn danger sm" id="vDel">Poista auto ja sen mittaukset</button></div>`;
    $("#vEdit").onclick = () => this.renderForm(v);
    bindTestRows();
    $("#vDel").onclick = () => {
      if (!confirm(`Poistetaanko ${v.nimi} ja kaikki sen mittaukset pysyvästi?`)) return;
      act(() => api(`/api/ajoneuvot/${id}`, { method: "DELETE" }), "Auto poistettu").then(() => (location.hash = "#/autot"));
    };
  },
};

function testTable(rows, withCar = false) {
  if (!rows.length) return `<div class="empty">Ei mittauksia.</div>`;
  return `<table class="t"><tr><th>Päivämäärä</th>${withCar ? "<th>Auto</th>" : ""}<th>Mittaus</th><th class="num">Kunto</th><th class="num hide-m">Kapasiteetti</th><th class="num hide-m">Jännite-ero</th><th>Tila</th></tr>
    ${rows.map(t => `<tr class="click" data-tid="${t.id}"><td>${date(t.aloitettu)}</td>${withCar ? `<td>${esc(t.ajoneuvo || "–")}<div class="small muted">${esc(t.rekisteri || "")}</div></td>` : ""}
      <td>${t.tyyppi === "kapasiteetti" ? "Kapasiteettimittaus" : "Pikatarkastus"}</td>
      <td class="num">${t.kunto_pct ? `<span class="pill ${pillClass(t.kunto_luokka)}">${n(t.kunto_pct)} %</span>` : "–"}</td>
      <td class="num hide-m">${t.kapasiteetti_kwh ? n(t.kapasiteetti_kwh) + " kWh" : "–"}</td>
      <td class="num hide-m">${t.ero_mv != null ? n(t.ero_mv, 0) + " mV" : "–"}</td>
      <td>${{ "valmis": '<span class="pill good">Valmis</span>', "käynnissä": '<span class="pill info">Käynnissä</span>' }[t.tila] || `<span class="pill">${esc(t.tila)}</span>`}</td></tr>`).join("")}</table>`;
}
function bindTestRows() {
  $$("tr[data-tid]").forEach(r => (r.onclick = () => (location.hash = `#/mittaukset/${r.dataset.tid}`)));
}

// =====================================================================
// MITTAUKSET
// =====================================================================
views.mittaukset = {
  render(arg) { if (arg) return this.renderOne(Number(arg)); this.renderList(); },
  async renderList() {
    view.innerHTML = `<div class="head"><div><h1>Mittaukset</h1><div class="muted">Ohjelmaan tallennetut ja tiedostoista avatut mittaukset</div></div>
      <label class="btn primary" style="cursor:pointer">Avaa mittaustiedosto<input type="file" id="tOpen" accept=".akux" hidden></label></div>
      <div class="card" id="tList"></div>`;
    const { mittaukset } = await api("/api/mittaukset");
    $("#tList").innerHTML = testTable(mittaukset, true);
    bindTestRows();
    $("#tOpen").onchange = async e => {
      const f = e.target.files[0];
      if (!f) return;
      try {
        const r = await upload("/api/mittaukset/avaa", f);
        toast(r.uusi ? "Mittaus avattu tiedostosta" : "Mittaus oli jo ohjelmassa");
        location.hash = `#/mittaukset/${r.id}`;
      } catch (err) { toast(err.message, true); }
      e.target.value = "";
    };
  },
  async renderOne(id) {
    const t = await api(`/api/mittaukset/${id}`);
    const r = t.tulos || {};
    const y = r.yhteenveto || {};
    const v = t.ajoneuvo || {};
    const done = t.tila === "valmis" && y.teksti;
    view.innerHTML = `<div class="head"><div><h1>${t.tyyppi === "kapasiteetti" ? "Kapasiteettimittaus" : "Pikatarkastus"}</h1>
      <div class="muted">${esc(v.nimi || "")} · ${date(t.aloitettu)}</div></div>
      <div class="row">${done ? `<a class="btn primary" href="/api/mittaukset/${id}/raportti.pdf" target="_blank">Avaa raportti (PDF)</a>` : ""}
        <a class="btn" href="/api/mittaukset/${id}/tiedosto.akux">Mittaustiedosto</a>
        <a class="btn" href="/api/mittaukset/${id}/data.csv">Mittausdata (CSV)</a></div></div>
      ${r.virhe ? `<div class="notice bad">${esc(r.virhe)}</div>` : ""}
      ${!done && !r.virhe ? `<div class="notice warn">Mittaus on tilassa: ${esc(t.tila)}. Raporttia ei voi muodostaa.</div>` : ""}
      ${done ? `
      <div class="grid g3">
        ${stat("Akun kunto", n(y.kunto_pct), "%", `${y.kunto_luokka || ""} · ${(y.kunto_lahde || "").toLowerCase()}`)}
        ${stat("Kapasiteetti", n(y.kapasiteetti_kwh), "kWh", y.epavarmuus_kwh ? `±${n(y.epavarmuus_kwh)} kWh · uutena ${n(r.viite.kwh)} kWh` : `Uutena ${n(r.viite.kwh)} kWh`)}
        ${stat("Kennoryhmien ero", r.kennot ? n(r.kennot.ero_mv, 0) : "–", "mV", r.kennot ? r.kennot.luokka : "")}
      </div>
      <div class="card" style="margin-top:16px"><h2>Yhteenveto</h2><p>${esc(y.teksti)}</p>
        ${y.tulkinta ? `<div class="notice"><b>Mitä tulos tarkoittaa:</b> ${esc(y.tulkinta)}</div>` : ""}
        <table class="t"><tr><th>Arvio</th><th>Tulos</th><th>Luokka</th><th class="hide-m">Selite</th></tr>
        ${(r.arviot || []).map(a => `<tr><td>${esc(a.nimi)}</td><td><b>${esc(a.arvo)}</b></td><td>${a.luokka ? `<span class="pill ${pillClass(a.luokka)}">${esc(a.luokka)}</span>` : ""}</td><td class="small muted hide-m">${esc(a.kuvaus)}</td></tr>`).join("")}</table>
        ${(r.huomiot || []).length ? `<h3>Huomiot</h3><ul class="small">${r.huomiot.map(h => `<li>${esc(h)}</li>`).join("")}</ul>` : ""}
      </div>
      ${r.kennot ? `<div class="card"><h2>${esc(r.kennot_otsikko || "Kennoryhmät")}</h2>${cellSvg(r.kennot.jannitteet)}</div>` : ""}` : ""}
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Tietojen eheys</h2><p class="small muted">Kaikki vastaanotetut viestit on tallennettu muuttamattomina. Tarkistus laskee raakadatan tarkisteen uudelleen ja vertaa sitä raporttiin merkittyyn.</p>
          <div class="small" style="word-break:break-all"><span class="muted">Tarkiste</span> ${esc(t.tarkiste || "–")}</div>
          <div class="row" style="margin-top:10px"><button class="btn sm" id="tVerify">Tarkista raakadata</button><a class="btn sm" href="/api/mittaukset/${id}/raakadata.csv.gz">Lataa raakadata</a><span id="tVerRes" class="small"></span></div></div>
        <div class="card"><h2>Tapahtumat</h2><div class="small" style="max-height:220px;overflow:auto">${(t.tapahtumat || []).map(e => `<div class="row" style="flex-wrap:nowrap;gap:12px;padding:3px 0"><span class="muted" style="min-width:110px">${date(e.t)}</span><span>${esc(e.teksti)}</span></div>`).join("")}</div></div>
      </div>
      <div class="row" style="margin-top:16px"><span class="spacer"></span><button class="btn danger sm" id="tDel">Poista mittaus</button></div>`;
    $("#tVerify").onclick = async () => {
      const res = await act(() => api(`/api/mittaukset/${id}/tarkista`));
      $("#tVerRes").innerHTML = `<span class="pill ${res.ok ? "good" : "bad"}">${esc(res.viesti)}</span> <span class="muted">${res.rivit ? n(res.rivit, 0) + " viestiä" : ""}</span>`;
    };
    $("#tDel").onclick = () => {
      if (!confirm("Poistetaanko mittaus ja sen raakadata pysyvästi?")) return;
      act(() => api(`/api/mittaukset/${id}`, { method: "DELETE" }), "Mittaus poistettu").then(() => history.back());
    };
  },
};

// =====================================================================
// OHJEET
// =====================================================================
views.ohjeet = {
  async render(arg) {
    view.innerHTML = `<div class="head"><div><h1>Ohjeet</h1><div class="muted">Käyttöönotto, mittaukset ja tulosten tulkinta</div></div>
      <a class="btn" href="/api/ohjeet.pdf" target="_blank">Käyttöohje (PDF)</a></div>
      <div class="guide-wrap"><nav class="toc card" id="gToc"></nav><div id="gBody"></div></div>`;
    const { osiot } = await api("/api/ohjeet");
    $("#gToc").innerHTML = osiot.map((o, i) => `<a href="#/ohjeet/${o.id}" data-id="${o.id}">${i + 1}. ${esc(o.otsikko)}</a>`).join("");
    $("#gBody").innerHTML = osiot.map((o, i) => `<section class="card guide" id="g-${o.id}"><h2>${i + 1}. ${esc(o.otsikko)}</h2>${o.html}</section>`).join("");
    if (arg) {
      const el = document.getElementById("g-" + arg);
      if (el) setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      $$("#gToc a").forEach(a => a.classList.toggle("active", a.dataset.id === arg));
    }
  },
};

// =====================================================================
// ASETUKSET
// =====================================================================
views.asetukset = {
  async render() {
    const s = await api("/api/asetukset");
    const ph = s.puhelin || {};
    view.innerHTML = `<div class="head"><div><h1>Asetukset</h1><div class="muted">Raporttien yritystiedot, mittauksen raja-arvot, puhelinkäyttö ja ilmoitukset</div></div>
      <button class="btn primary" id="sSave">Tallenna asetukset</button></div>
    <div id="sForm">
      <div class="card"><h2>Yritys ja raportit</h2>
        <p class="small muted">Tiedot näkyvät jokaisen raportin yläreunassa.</p>
        <div class="grid g2">
          <label class="f"><span>Yrityksen nimi</span><input name="yritys_nimi" value="${esc(s.yritys_nimi)}"></label>
          <label class="f"><span>Y-tunnus</span><input name="yritys_ytunnus" value="${esc(s.yritys_ytunnus)}"></label>
          <label class="f"><span>Osoite</span><input name="yritys_osoite" value="${esc(s.yritys_osoite)}" placeholder="Katuosoite, postinumero ja toimipaikka"></label>
          <label class="f"><span>Puhelin</span><input name="yritys_puhelin" value="${esc(s.yritys_puhelin)}"></label>
          <label class="f"><span>Sähköposti</span><input name="yritys_sahkoposti" value="${esc(s.yritys_sahkoposti)}"></label>
          <label class="f"><span>Verkkosivu</span><input name="yritys_www" value="${esc(s.yritys_www)}"></label>
          <label class="f"><span>Mittaajan nimi</span><input name="mittaaja" value="${esc(s.mittaaja)}"><small class="muted">Ehdotetaan jokaiseen uuteen mittaukseen.</small></label>
          <label class="f"><span>Raportin alatunniste</span><input name="raportin_alatunniste" value="${esc(s.raportin_alatunniste)}" placeholder="Valinnainen"></label>
        </div>
        <div class="row"><label class="btn sm" style="cursor:pointer">Valitse logo<input type="file" id="sLogo" accept="image/png,image/jpeg" hidden></label>
          <span class="small muted">${s.logo ? "Logo on käytössä raporteissa." : "Logoa ei ole valittu. Käytä PNG- tai JPEG-kuvaa."}</span>
          ${s.logo ? `<button class="btn sm" id="sLogoDel" type="button">Poista logo</button>` : ""}</div>
      </div>

      <div class="card"><h2>Mittausten tallennus</h2>
        <p class="small muted">Jokainen valmis mittaus tallennetaan mittaustiedostona (.akux) ja PDF-raporttina. Mittaustiedosto sisältää kaikki mittauksen tiedot ja raakadatan, ja sen voi avata missä tahansa Akux-versiossa kohdasta Mittaukset → Avaa mittaustiedosto.</p>
        <label class="check"><input type="checkbox" name="mittaus_tallennus" ${s.mittaus_tallennus ? "checked" : ""}><span>Tallenna jokainen valmis mittaus automaattisesti</span></label>
        ${ANDROID ? `<p class="small">Tallennuskansio: <b>${esc(s.mittaus_kansio_oletus)}</b></p>` :
          `<label class="f"><span>Tallennuskansio</span><input name="mittaus_kansio" value="${esc(s.mittaus_kansio)}" placeholder="${esc(s.mittaus_kansio_oletus)}"><small class="muted">Jätä tyhjäksi, niin tiedostot tallentuvat kansioon ${esc(s.mittaus_kansio_oletus)}. Voit käyttää myös pilvikansiota, esimerkiksi OneDrivea.</small></label>`}
      </div>

      <div class="card"><h2>Kapasiteettimittaus</h2>
        <p class="small muted">Oletusarvot vastaavat suositeltua mittaustapaa. Muuta niitä vain, jos siihen on syy.</p>
        <div class="grid g3">
          <label class="f"><span>Lepo ennen latausta (min)</span><input name="lepo_alku_min" inputmode="numeric" value="${esc(s.lepo_alku_min)}"></label>
          <label class="f"><span>Lepo latauksen jälkeen (min)</span><input name="lepo_loppu_min" inputmode="numeric" value="${esc(s.lepo_loppu_min)}"></label>
          <label class="f"><span>Lähtövaraus enintään (%)</span><input name="kapasiteetti_lahto_soc_max" inputmode="numeric" value="${esc(s.kapasiteetti_lahto_soc_max)}"></label>
          <label class="f"><span>Akun lämpötila vähintään (°C)</span><input name="lampotila_min" inputmode="numeric" value="${esc(s.lampotila_min)}"></label>
          <label class="f"><span>Akun lämpötila enintään (°C)</span><input name="lampotila_max" inputmode="numeric" value="${esc(s.lampotila_max)}"></label>
        </div>
      </div>

      <div class="grid ${ANDROID ? "" : "g2"}">
        ${ANDROID ? "" : `<div class="card"><h2>Käyttö puhelimella</h2>
          <label class="check"><input type="checkbox" name="puhelin_kaytossa" ${s.puhelin_kaytossa ? "checked" : ""}><span>Salli käyttö puhelimella samassa verkossa</span></label>
          ${!!s.puhelin_kaytossa !== !!ph.kaytossa ? `<div class="notice warn small">Muutos tulee voimaan, kun ohjelma käynnistetään uudelleen.<div style="margin-top:8px"><button class="btn sm" id="sRestart" type="button">Tallenna ja käynnistä uudelleen</button></div></div>` : ""}
          ${ph.kaytossa ? `<p class="small">Avaa puhelimen selaimella:</p>
            ${(ph.osoitteet || []).map(u => `<div class="addr">${esc(u)}</div>`).join("") || `<div class="small muted">Tietokone ei ole yhteydessä verkkoon.</div>`}
            <p class="small muted" style="margin-top:8px">Suojakoodi <b>${esc(ph.avain)}</b>. Koodi kysytään kerran kullakin puhelimella.</p>`
          : `<p class="small muted">Kun käyttö on sallittu, puhelimen osoite ja suojakoodi näkyvät tässä. <a href="#/ohjeet/puhelin">Lue lisää</a></p>`}
        </div>`}
        <div class="card"><h2>Puhelinilmoitukset</h2>
          <label class="check"><input type="checkbox" name="ilmoitukset_kaytossa" ${s.ilmoitukset_kaytossa ? "checked" : ""}><span>Lähetä ilmoitukset puhelimeen</span></label>
          <label class="f"><span>Ilmoitusaiheen osoite (ntfy)</span><input name="ilmoitus_osoite" id="nUrl" value="${esc(s.ilmoitus_osoite)}" placeholder="https://ntfy.sh/akux-oma-aihe"></label>
          <label class="check"><input type="checkbox" name="ilmoitus_vaiheet" ${s.ilmoitus_vaiheet ? "checked" : ""}><span>Mittauksen vaihe vaihtuu</span></label>
          <label class="check"><input type="checkbox" name="ilmoitus_valmis" ${s.ilmoitus_valmis ? "checked" : ""}><span>Mittaus on valmis</span></label>
          <label class="check"><input type="checkbox" name="ilmoitus_ongelmat" ${s.ilmoitus_ongelmat ? "checked" : ""}><span>Ongelma: lataus keskeytyy tai yhteys katkeaa</span></label>
          <div class="row" style="margin-top:10px"><button class="btn sm" id="nTest" type="button">Lähetä testi-ilmoitus</button><a class="small" href="#/ohjeet/ilmoitukset">Ohje käyttöönottoon</a></div>
        </div>
      </div>
    </div>`;
    const save = () => act(() => api("/api/asetukset", { method: "POST", body: form($("#sForm")) }), "Asetukset tallennettu");
    $("#sSave").onclick = () => save().then(() => this.render());
    $("#nTest").onclick = () => act(() => api("/api/ilmoitus/testi", { method: "POST", body: { osoite: $("#nUrl").value } }), "Testi-ilmoitus lähetetty. Tarkista puhelin.");
    const rs = $("#sRestart");
    if (rs) rs.onclick = async () => {
      await save();
      await act(() => api("/api/uudelleen", { method: "POST" }), "Ohjelma käynnistyy uudelleen…");
      waitRestart();
    };
    $("#sLogo").onchange = e => {
      const f = e.target.files[0];
      if (!f) return;
      const rd = new FileReader();
      rd.onload = () => act(() => api("/api/logo", { method: "POST", body: { data: rd.result } }), "Logo tallennettu").then(() => this.render());
      rd.readAsDataURL(f);
    };
    const del = $("#sLogoDel");
    if (del) del.onclick = () => act(() => api("/api/logo", { method: "POST", body: { poista: true } }), "Logo poistettu").then(() => this.render());
  },
};

function waitRestart() {
  let n = 0;
  const t = setInterval(async () => {
    n++;
    try { await api("/api/tila"); clearInterval(t); location.reload(); } catch (e) { if (n > 40) clearInterval(t); }
  }, 1000);
}
async function upload(path, file) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
  let d = {};
  try { d = await r.json(); } catch (e) { /* */ }
  if (!r.ok) throw new Error(d.virhe || `Virhe ${r.status}`);
  return d;
}
function sizeTxt(b) { return b > 1e6 ? n(b / 1e6, 1) + " Mt" : n(b / 1e3, 0) + " kt"; }

// =====================================================================
// YLLÄPITO
// =====================================================================
const STATUS = { ok: ["good", "Kunnossa"], varoitus: ["warn", "Huomioitava"], virhe: ["bad", "Virhe"], info: ["", "Tieto"] };

views.yllapito = {
  async render() {
    const info = await api("/api/tietoja");
    view.innerHTML = `<div class="head"><div><h1>Ylläpito</h1><div class="muted">Laaduntarkistus, päivitykset ja varmuuskopiot</div></div></div>
      <div class="card"><div class="row"><h2 style="margin:0">Laaduntarkistus</h2><span class="spacer"></span><button class="btn primary" id="qRun">Aja tarkistus</button></div>
        <p class="small muted" style="margin-top:8px">Tarkistaa ohjelmatiedostot, tietokannan, levytilan, sovittimen, viestien purun, mittauslaskennan, raportin muodostuksen ja tallennettujen mittausten raakadatan. Tarkistus kestää noin puoli minuuttia eikä muuta tietojasi.</p>
        <div id="qRes"></div></div>
      <div class="grid g2">
        <div class="card"><h2>Päivitys</h2>
          <p class="small">Käytössä on versio <b>${esc(info.versio)}</b>.</p>
          <p class="small muted">Uusin versio julkaistaan GitHubin Releases-sivulla. ${ANDROID ? "Lataa Akux-x.y.z.apk ja asenna se vanhan päälle." : "Lataa Akux-asennus-x.y.z.exe ja aja se. Asennus sulkee Akuxin, päivittää sen ja säilyttää tiedot."} Autot, mittaukset, raportit ja asetukset säilyvät.</p>
          <div class="row"><a class="btn primary" href="https://github.com/anterohu/akux/releases/latest" target="_blank" rel="noopener">Avaa julkaisut</a>
          ${ANDROID ? "" : `<label class="btn" style="cursor:pointer">Asenna lähdekoodipaketista<input type="file" id="uFile" accept=".zip" hidden></label>`}</div>
          <div id="uRes" style="margin-top:12px"></div></div>
        <div class="card"><h2>Varmuuskopiot</h2>
          <p class="small muted">Ohjelma tekee varmuuskopion automaattisesti kerran viikossa ja säilyttää viisi uusinta. Tallenna kopio välillä myös muistitikulle tai pilvipalveluun.</p>
          <div class="row"><a class="btn" href="/api/yllapito/varmuuskopio" id="bNow">Tee varmuuskopio nyt</a>
            <label class="btn" style="cursor:pointer">Palauta varmuuskopio<input type="file" id="rFile" accept=".zip" hidden></label></div>
          <div id="rRes" style="margin-top:12px"></div>
          <div id="bList" style="margin-top:12px"></div></div>
      </div>
      <div class="card"><div class="row"><h2 style="margin:0">Tapahtumaloki</h2><span class="spacer"></span><button class="btn sm" id="lLoad">Näytä loki</button></div>
        <pre id="lBox" class="log" hidden></pre></div>
      <div class="card"><h2>Tietoja ohjelmasta</h2><dl class="kv">
        <dt>Ohjelma</dt><dd>${esc(info.nimi)} ${esc(info.versio)}</dd>
        <dt>Tietojen sijainti</dt><dd style="word-break:break-all">${esc(info.datakansio)}</dd>
        <dt>Järjestelmä</dt><dd>${esc(info.jarjestelma)}</dd></dl>
        <p class="small muted" style="margin-top:12px">${ANDROID ? "Tiedot säilyvät sovelluksen omassa tallennustilassa. Raportit ja varmuuskopiot tallentuvat myös Lataukset/Akux-kansioon, kun avaat ne. " : ""}Viestimäärittelyt perustuvat Tesla-omistajien yhteisön ylläpitämään avoimeen aineistoon. Tesla, Model 3 ja Model Y ovat Tesla, Inc:n tavaramerkkejä. Akux ei ole Teslan tekemä eikä hyväksymä.</p></div>`;

    $("#qRun").onclick = async () => {
      const b = $("#qRun");
      b.disabled = true;
      b.textContent = "Tarkistetaan…";
      $("#qRes").innerHTML = `<div class="bar" style="margin-top:12px"><i class="indet"></i></div>`;
      try {
        const r = await api("/api/yllapito/tarkistus");
        const [cls, lbl] = STATUS[r.tulos];
        $("#qRes").innerHTML = `<div class="notice ${cls}" style="margin-top:12px"><b>${r.tulos === "ok" ? "Kaikki tarkistukset kunnossa." : (r.tulos === "varoitus" ? "Tarkistus valmis, huomioitavaa löytyi." : "Tarkistuksessa löytyi virheitä.")}</b> ${date(r.aika)}</div>
          <table class="t"><tr><th>Tarkistus</th><th>Tulos</th><th class="hide-m">Tieto</th></tr>
          ${r.tarkistukset.map(c => `<tr><td>${esc(c.nimi)}<div class="small muted show-m">${esc(c.tieto)}</div></td><td><span class="pill ${STATUS[c.tila][0]}">${STATUS[c.tila][1]}</span></td><td class="small muted hide-m">${esc(c.tieto)}</td></tr>`).join("")}</table>`;
      } catch (e) {
        $("#qRes").innerHTML = `<div class="notice bad" style="margin-top:12px">${esc(e.message)}</div>`;
      }
      b.disabled = false;
      b.textContent = "Aja tarkistus uudelleen";
    };

    if ($("#uFile")) $("#uFile").onchange = async e => {
      const f = e.target.files[0];
      if (!f) return;
      const box = $("#uRes");
      box.innerHTML = `<div class="small muted">Tarkistetaan pakettia…</div>`;
      try {
        const r = await upload("/api/yllapito/paivitys/tarkista", f);
        box.innerHTML = `<div class="notice ${r.uudempi ? "" : "warn"}">Paketissa on versio <b>${esc(r.versio)}</b>. ${r.uudempi ? "Se on uudempi kuin käytössä oleva." : "Se ei ole uudempi kuin käytössä oleva versio."}</div>
          <button class="btn primary" id="uGo">Asenna versio ${esc(r.versio)}</button>`;
        $("#uGo").onclick = async () => {
          if (!confirm(`Asennetaanko Akux ${r.versio}? Ohjelma sulkeutuu asennuksen ajaksi ja avautuu sen jälkeen uudelleen.`)) return;
          try {
            await upload("/api/yllapito/paivitys", f);
            clearInterval(pollTimer);
            document.body.innerHTML = `<div style="padding:40px;font-family:Inter,system-ui"><h1>Päivitys käynnissä</h1><p>Asennusikkuna avautuu hetken kuluttua. Akux avautuu uudelleen, kun asennus on valmis. Voit sulkea tämän ikkunan.</p></div>`;
          } catch (err) { toast(err.message, true); }
        };
      } catch (err) {
        box.innerHTML = `<div class="notice bad">${esc(err.message)}</div>`;
      }
      e.target.value = "";
    };

    $("#rFile").onchange = async e => {
      const f = e.target.files[0];
      if (!f) return;
      const box = $("#rRes");
      try {
        const r = await upload("/api/yllapito/palauta/tarkista", f);
        box.innerHTML = `<div class="notice warn">Varmuuskopio ${date(r.aika)}, versio ${esc(r.versio)}: ${r.autoja} autoa ja ${r.mittauksia} mittausta. Palautus korvaa nykyiset tiedot. Nykyiset tiedot siirretään ensin talteen.</div>
          <button class="btn primary" id="rGo">Palauta varmuuskopio</button>`;
        $("#rGo").onclick = async () => {
          if (!confirm("Palautetaanko varmuuskopio? Ohjelma käynnistyy sen jälkeen uudelleen.")) return;
          try {
            await upload("/api/yllapito/palauta", f);
            toast("Varmuuskopio palautettu. Ohjelma käynnistyy uudelleen…");
            waitRestart();
          } catch (err) { toast(err.message, true); }
        };
      } catch (err) {
        box.innerHTML = `<div class="notice bad">${esc(err.message)}</div>`;
      }
      e.target.value = "";
    };

    const list = async () => {
      const r = await api("/api/yllapito/varmuuskopiot");
      $("#bList").innerHTML = r.varmuuskopiot.length ? `<table class="t"><tr><th>Varmuuskopio</th><th class="num">Koko</th><th></th></tr>
        ${r.varmuuskopiot.map(b => `<tr><td>${date(b.aika)}</td><td class="num">${sizeTxt(b.koko)}</td><td class="num"><a class="btn sm" href="/api/yllapito/varmuuskopiot/${encodeURIComponent(b.nimi)}">Lataa</a></td></tr>`).join("")}</table>`
        : `<div class="small muted">Varmuuskopioita ei ole vielä tehty.</div>`;
    };
    list();
    $("#bNow").onclick = () => { toast("Varmuuskopio tehdään…"); setTimeout(list, 2500); };
    $("#lLoad").onclick = async () => {
      const r = await api("/api/yllapito/loki");
      const b = $("#lBox");
      b.hidden = false;
      b.textContent = r.loki || "Loki on tyhjä.";
      b.scrollTop = b.scrollHeight;
    };
  },
};

// ---------- sulkeminen ----------
async function quitApp() {
  let body = {};
  if (S && S.mittaus) {
    if (!confirm("Mittaus on käynnissä. Ohjelman sulkeminen keskeyttää mittauksen. Suljetaanko silti?\n\nVoit myös vain sulkea ikkunan: mittaus jatkuu taustalla, ja saat sen näkyviin avaamalla ohjelman uudelleen.")) return;
    body = { vahvistettu: true };
  } else if (!confirm("Suljetaanko Akux?")) return;
  try { await api("/api/sulje", { method: "POST", body }); } catch (e) { toast(e.message, true); return; }
  clearInterval(pollTimer);
  document.body.innerHTML = `<div style="padding:40px;font-family:Inter,system-ui;color:var(--ink)"><h1>Akux on suljettu</h1><p class="muted">Voit sulkea tämän ikkunan.</p></div>`;
  setTimeout(() => { if (ANDROID) window.AkuxAndroid.close(); else window.close(); }, 400);
}
$("#quit").onclick = quitApp;

// ---------- käynnistys ----------
route();
poll();
pollTimer = setInterval(poll, 1000);
