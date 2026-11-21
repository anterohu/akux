"use strict";
/* AKVERI – käyttöliittymä */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const view = $("#view");
let S = null;            // viimeisin /api/tila
let current = null;      // aktiivinen näkymä
let pollTimer = null;

// ---------- apufunktiot ----------
const ANDROID = !!window.AkveriAndroid;
// Esittelytila ja esimerkkiautot vain testitileille (merkitään akveri.fi:n hallinnassa). Asiakkaat eivät näe niitä.
async function esittelySallittu() { try { return !!(await api("/api/tietoja")).esittely; } catch (e) { return false; } }
const MALLIRYHMAT = [
  ["Model 3", m => m.malli_koodi === "3"],
  ["Model Y", m => m.malli_koodi === "Y"],
  ["Model S ja Model X 2021–", m => m.alusta !== "sx" && /[SX]/.test(m.malli_koodi)],
  ["Model S 2012–2021 ja Model X 2015–2021", m => m.alusta === "sx"],
  ["Cybertruck", m => m.malli_koodi === "C"],
  ["Hyundai", m => m.merkki === "Hyundai"],
  ["Kia", m => m.merkki === "Kia"],
  ["Nissan", m => m.merkki === "Nissan"],
  ["Volkswagen-konserni (MEB)", m => m.alusta === "meb"],
  ["MG", m => m.merkki === "MG"],
];
const MERKIT = ["Tesla", "Hyundai", "Kia", "Nissan", "Volkswagen", "Škoda", "Audi", "Cupra", "MG"];
const merkki = m => (m && m.merkki) || "Tesla";
// Mallivalikon sisältö merkin mukaan; Teslan mallit ryhmitellään mallisarjoittain
function malliOptions(mallit, brand, selected) {
  const opt = m => `<option value="${m.id}" ${m.id === selected ? "selected" : ""}>${esc(m.nimi)}</option>`;
  const list = mallit.filter(m => merkki(m) === brand);
  const first = `<option value="">${brand === "Tesla" ? "Tunnista automaattisesti" : "Valitse malli"}</option>`;
  if (brand === "Tesla")
    return first + MALLIRYHMAT.slice(0, 5).map(([nimi, f]) => `<optgroup label="${nimi}">${list.filter(f).map(opt).join("")}</optgroup>`).join("");
  return first + list.map(opt).join("");
}
const cellsTxt = c => (Array.isArray(c) ? c.join(" tai ") : (c || ""));
const guideHtml = (g, card = false) => `${card ? "<h2>Kytkentä autoon</h2>" : `<h3 style="margin:14px 0 6px">Kytkentä autoon</h3>`}<div class="small"><b>${esc(g.liitin)}.</b> ${esc(g.ohje)}</div>${g.varmistettu ? "" : `<div class="small muted" style="margin-top:6px">Tätä kytkentää ei ole vielä varmistettu AKVERIlla. Tarkista väylä ensimmäisellä kytkentäkerralla Yleiskuvan kohdasta Kartoita väylä.</div>`}`;
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function n(x, d = 1) {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return Number(x).toLocaleString(LOKAALI, { minimumFractionDigits: d, maximumFractionDigits: d });
}
function date(ts, time = true) {
  if (!ts) return "–";
  const o = { day: "numeric", month: "numeric", year: "numeric" };
  if (time) Object.assign(o, { hour: "2-digit", minute: "2-digit" });
  return new Date(ts * 1000).toLocaleString(LOKAALI, o);
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
// AKVERIn oma vahvistusikkuna selaimen confirm/alert-ikkunoiden sijaan (niissä näkyisi sivun osoite).
// Tapahtumat: päivämäärä otsikkona kerran, kellonaika aina samanlevyisessä sarakkeessa. Ei omaa vieritysaluetta.
function tapahtumalista(rivit) {
  let pv = null;
  return `<div class="tapahtumat small">${rivit.map(e => {
    const d = new Date(e.t * 1000);
    const p = date(e.t, false);
    const otsikko = p !== pv ? `<div class="tp-pv muted">${esc(p)}</div>` : "";
    pv = p;
    const klo = `${d.getHours()}.${String(d.getMinutes()).padStart(2, "0")}`;
    return `${otsikko}<div class="tp"><span class="tp-klo muted">${klo}</span><span class="tp-teksti">${esc(e.teksti)}</span></div>`;
  }).join("")}</div>`;
}

function kysy(teksti, { ok = "OK", peru = "Peruuta", vaara = false } = {}) {
  return new Promise(valmis => {
    const tausta = document.createElement("div");
    tausta.className = "kysely-tausta";
    tausta.innerHTML = `<div class="kysely" role="alertdialog" aria-modal="true"><p></p><div class="row"><span class="spacer"></span>
      ${peru ? '<button class="btn" data-v="0"></button>' : ""}<button class="btn ${vaara ? "danger" : "primary"}" data-v="1"></button></div></div>`;
    tausta.querySelector("p").textContent = teksti;
    tausta.querySelector('[data-v="1"]').textContent = ok;
    if (peru) tausta.querySelector('[data-v="0"]').textContent = peru;
    const nappain = e => { if (e.key === "Escape") loppu(false); };
    const loppu = v => { tausta.remove(); document.removeEventListener("keydown", nappain); valmis(v); };
    tausta.onclick = e => {
      const b = e.target.closest("[data-v]");
      if (b) loppu(b.dataset.v === "1");
      else if (e.target === tausta && peru) loppu(false);
    };
    document.addEventListener("keydown", nappain);
    document.body.appendChild(tausta);
    tausta.querySelector('[data-v="1"]').focus();
  });
}
const ilmoita = teksti => kysy(teksti, { peru: null });
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

// ---------- valikko puhelimessa ----------
$("#menuBtn").onclick = () => document.body.classList.toggle("menu-open");
$$("#nav a").forEach(a => a.addEventListener("click", () => document.body.classList.remove("menu-open")));

// ---------- reititys ----------
const views = {};
// Mistä alanäkymään tultiin: Takaisin-painike palaa samaan paikkaan
let prevHash = "", curHash = "";
function backLink(fallback, label) {
  const from = prevHash && prevHash !== curHash ? prevHash : "";
  const target = from && (/^#\/autot\/\d+$/.test(from) || from === "#/mittaukset" || from === "#/autot") ? from : fallback;
  const lbl = target === "#/mittaukset" ? "Mittaukset" : target === "#/autot" ? "Autot" : /^#\/autot\/\d+$/.test(target) ? "Auton tiedot" : label;
  return { html: `<a class="back" href="${target}">← ${esc(lbl)}</a>`, target };
}
function route() {
  if (location.hash !== curHash) { prevHash = curHash; curHash = location.hash; }
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
function cellSvg(volts, raja = 15) {
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
    bars += `<rect x="${(i * bw + bw * .14).toFixed(1)}" y="${y.toFixed(1)}" width="${(bw * .72).toFixed(1)}" height="${Math.max(.8, h).toFixed(1)}" rx="1" fill="${Math.abs(d) > raja ? "var(--bad)" : "var(--accent)"}"><title>Ryhmä ${i + 1}: ${volts[i] ? volts[i].toFixed(4).replace(".", ",") + " V" : "–"} (${d >= 0 ? "+" : ""}${n1(d)} mV)</title></rect>`;
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
        <div class="card"><h2>Yhteystesti</h2><div id="busBox"><div class="empty small">Yhdistä sovittimeen nähdäksesi, mitä tietoja autosta vastaanotetaan.</div></div><div id="scanBox"></div></div>
      </div>`;
    this.connRendered = null;
    this.renderStart();
  },
  async renderStart() {
    const [st, { ajoneuvot }, { mittaukset }, E] = await Promise.all([api("/api/asetukset"), api("/api/ajoneuvot"), api("/api/mittaukset"), esittelySallittu()]);
    const steps = [
      [!!(st.kaytto || st.yritys_nimi), "Valitse käyttötapa: yksityinen tai yritys", "#/asetukset"],
      [!!(S && S.yhteys.kaynnissa) || mittaukset.length > 0, E ? "Yhdistä autoon tai kokeile esittelytilaa" : "Yhdistä autoon", null],
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
      let hkOpts = "";
      try {
        const { mallit } = await api("/api/mallit");
        const hk = mallit.filter(m => m.merkki && m.merkki !== "Tesla");
        const brands = [...new Set(hk.map(m => m.merkki))];
        hkOpts = brands.map(b => `<optgroup label="${esc(b)}">${hk.filter(m => m.merkki === b).map(m =>
          `<option value="${esc(m.id)}">${esc(m.nimi)}</option>`).join("")}</optgroup>`).join("");
      } catch (e) { /* */ }
      const E = await esittelySallittu();
      const opts = ports.portit.map(p => `<option value="${esc(p.laite)}">${esc(p.laite)} – ${esc(p.kuvaus)}${p.todennakoinen ? " (OBDLink)" : ""}</option>`).join("");
      c.innerHTML = `
        <h2>Yhdistä</h2>
        ${ports.pyserial ? "" : `<div class="notice warn">Sovittimen yhteysosa puuttuu ohjelmasta. Asenna ohjelma uudelleen.</div>`}
        ${ports.pyserial && !ports.portit.length ? `<div class="notice warn"><b>Sovitinta ei löytynyt.</b> Tarkista, että OBDLink on kytketty USB-kaapelilla. Bluetooth-mallit (MX+, LX) näkyvät listassa, kun sovitin on ensin paritettu ${ANDROID ? "puhelimen" : "Windowsin"} Bluetooth-asetuksista. ${ports.windows ? "Windows asentaa sovittimen ajurin yleensä itse ensimmäisellä kytkentäkerralla, kun tietokone on verkossa. Odota hetki ja paina Päivitä portit. Jos sovitin ei vieläkään näy, asenna FTDI:n VCP-ajuri osoitteesta <b>ftdichip.com/drivers/vcp-drivers</b>." : ""}</div>` : ""}
        <div class="grid g2">
          <div>
            <label class="f"><span>Auto</span>
              <select id="connModel"><option value="" disabled selected>Valitse merkki ja malli</option>
                <optgroup label="Tesla"><option value="tesla">Tesla (malli tunnistetaan automaattisesti)</option></optgroup>${hkOpts}</select></label>
            <label class="f"><span>${ANDROID ? "OBDLink-sovitin" : "OBDLink-sovittimen portti"}</span>
              <select id="port">${opts || `<option value="">Sovitinta ei löytynyt</option>`}</select></label>
            <div class="row"><button class="btn primary" id="bConnect" disabled>Yhdistä autoon</button>
              <button class="btn" id="bRefresh">Päivitä portit</button></div>
            <p class="small muted" style="margin-top:10px">${ANDROID ? "Kytke sovitin auton diagnostiikkaliittimeen ja USB-C-sovittimella puhelimeen. Kun Android kysyy lupaa käyttää sovitinta, valitse Salli." : "Kytke sovitin auton diagnostiikkaliittimeen ja tietokoneeseen."} Auton on oltava hereillä: Teslassa riittää oven avaaminen, muissa merkeissä virta päälle. <a href="#/ohjeet/yhdistaminen">Ohje</a></p>
          </div>
          ${E ? `<div class="demo-paneeli">
            <div class="row" style="align-items:baseline"><h3>Esittelytila</h3><span class="spacer"></span><span class="merkinta">Testitili</span></div>
            <p class="small muted">Kokeile kaikkia toimintoja ilman autoa. Valittu auto simuloidaan, ja aika kulkee nopeutettuna.</p>
            <label class="f"><span>Simuloitava auto</span>
            <select id="demoCar">
              <optgroup label="Tesla"><option value="m3-lr">Model 3 Long Range 2020 (NCA)</option><option value="m3-lfp">Model 3 SR+ 2020, LFP-akku</option>
                <option value="my-lr">Model Y Long Range 2022 (NMC)</option><option value="ms-85">Model S 85 2015</option></optgroup>
              <optgroup label="Hyundai ja Kia"><option value="kona-64">Hyundai Kona Electric 64 kWh</option><option value="ioniq-28">Hyundai Ioniq Electric 28 kWh</option>
                <option value="ev6-77">Kia EV6 77,4 kWh</option></optgroup>
              <optgroup label="Nissan"><option value="leaf-40">Nissan Leaf 40 kWh</option><option value="leaf-24">Nissan Leaf 24 kWh</option></optgroup>
              <optgroup label="Volkswagen-konserni"><option value="id3-58">Volkswagen ID.3 58 kWh</option><option value="enyaq-77">Škoda Enyaq 77 kWh</option>
                <option value="q4-77">Audi Q4 e-tron 77 kWh</option><option value="born-58">Cupra Born 58 kWh</option></optgroup>
              <optgroup label="MG"><option value="mg4-64">MG4 Electric 64 kWh</option><option value="mgzs-44">MG ZS EV 44,5 kWh</option></optgroup>
            </select></label>
            <div class="row"><button class="btn primary" id="bDemo">Käynnistä esittelytila</button>
              <button class="btn" id="bEx">Esimerkkiraportit</button></div>
          </div>` : ""}
        </div>`;
      const sel = $("#port");
      if (S && sel && ports.portit.length) {
        api("/api/asetukset").then(s => {
          if (s.portti && [...sel.options].some(o => o.value === s.portti)) sel.value = s.portti;
          const cm = $("#connModel");
          if (cm && s.yhteys_malli && [...cm.options].some(o => o.value === s.yhteys_malli)) cm.value = s.yhteys_malli;
          const b = $("#bConnect"); if (b && cm) b.disabled = !cm.value;
        });
      }
      // Yhdistä on käytössä, kun sovitin on löytynyt ja auton merkki ja malli on valittu.
      const paivitaYhdista = () => { const b = $("#bConnect"); if (b) b.disabled = !(opts && $("#connModel").value); };
      $("#connModel").onchange = paivitaYhdista;
      paivitaYhdista();
      $("#bRefresh").onclick = () => { this.connRendered = null; this.renderConnCard(); };
      $("#bConnect").onclick = () => act(() => api("/api/yhdista", { method: "POST", body: { tyyppi: "obdlink", portti: $("#port").value, malli_id: $("#connModel").value } }), "Yhdistetään…").then(poll);
      if ($("#bEx")) $("#bEx").onclick = () => act(() => api("/api/esimerkit", { method: "POST", body: {} }), "Esimerkkiautot ovat käytettävissä").then(() => (location.hash = "#/mittaukset"));
      if ($("#bDemo")) $("#bDemo").onclick = () => act(() => api("/api/yhdista", { method: "POST", body: { tyyppi: "demo", soc: 12, nopeutus: 60, auto: $("#demoCar").value } }), "Esittelytila käynnistetty").then(poll);
    } else {
      c.innerHTML = `
        <div class="row"><div><h2 style="margin:0">${y.simuloitu ? "Esittelytila" : "Yhdistetty sovittimeen"}</h2>
          <div class="small muted" id="connInfo"></div><div class="notice warn small" id="connErr" hidden style="margin:8px 0 0"></div></div><span class="spacer"></span>
          <button class="btn" id="bDisc">Katkaise yhteys</button></div>
        ${y.simuloitu ? demoControls() : ""}`;
      $("#bDisc").onclick = async () => {
        if (S.mittaus && !(await kysy("Mittaus on käynnissä. Yhteyden katkaisu keskeyttää sen. Jatketaanko?", { ok: "Katkaise yhteys", vaara: true }))) return;
        act(() => api("/api/katkaise", { method: "POST" }), "Yhteys katkaistu").then(poll);
      };
      bindDemo(c);
      this.updateConn();
    }
  },
  async scan() {
    const box = $("#scanBox");
    try { await api("/api/vaylakartoitus", { method: "POST", body: {} }); } catch (e) { toast(e.message, true); return; }
    box.innerHTML = `<h3>Väylän kartoitus</h3><p class="small muted">Kuunnellaan liitäntää 10 sekuntia ilman suodatusta…</p><div class="bar"><i class="indet"></i></div>`;
    let r;
    for (let i = 0; i < 30; i++) {
      await new Promise(ok => setTimeout(ok, 1000));
      r = await api("/api/vaylakartoitus");
      if (r.tila === "valmis") break;
    }
    const cls = { ok: "good", rajattu: "bad", ei: "warn" }[r.arvio] || "";
    box.innerHTML = `<h3>Väylän kartoitus</h3><div class="notice ${cls}">${esc(r.teksti)}</div>
      <p class="small muted">Liitännässä liikkui ${r.lajeja} erilaista viestiä.</p>
      ${r.viestit.length ? `<table class="t"><tr><th>Tunniste</th><th class="num">Taajuus</th><th>Tieto</th></tr>
      ${r.viestit.map(v => `<tr><td>${esc(v.tunniste)}</td><td class="num">${n(v.taajuus_hz, 1)} Hz</td><td class="small ${v.kuvaus ? "" : "muted"}">${esc(v.kuvaus || "Ei käytössä AKVERIssa")}${v.pituus ? ` <span class="muted">· <span>${v.pituus} tavua</span></span>` : ""}${v.vastaamatta ? ` <span class="pill warn">Ei vastausta</span>` : ""}</td></tr>`).join("")}</table>` : ""}`;
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
    const soh = L.nfp_kwh && L.viite_kwh ? L.nfp_kwh / L.viite_kwh * 100 : null;
    st.innerHTML = [
      stat("Varaustila", L.soc_ui != null ? n(L.soc_ui) : "–", "%", L.soc_avg != null ? `Kennojen keskiarvo ${n(L.soc_avg)} %` : ""),
      stat("Akun jännite", L.pack_v != null ? n(L.pack_v) : "–", "V", L.pack_i != null ? `Virta ${n(L.pack_i)} A` : ""),
      stat("Teho", L.power_kw != null ? n(Math.abs(L.power_kw)) : "–", "kW", L.power_kw == null ? "" : (L.power_kw < -0.3 ? "Lataus" : (L.power_kw > 0.3 ? "Purku" : "Levossa"))),
      stat("Akun lämpötila", L.temp_min != null ? `${n(L.temp_min)}–${n(L.temp_max)}` : "–", "°C", ""),
      ...(L.kunto_piilotettu ? [
        stat("Täyden akun energia", "–", "kWh", "Näkyy mittauksen aikana"),
        stat("Akun kunto", "–", "%", "Näkyy mittauksen aikana ja raportissa")] : [
        stat("Täyden akun energia", L.nfp_kwh != null ? n(L.nfp_kwh) : "–", "kWh", L.kyselyalusta ? "Akunhallinnan kuntoarviosta" : "Teslan akunhallinta"),
        L.soh_jumissa
          ? stat("Akunhallinnan kunto", n(L.bms_soh_pct), "%", "Akunhallinnan oma lukema, ei todellinen kunto. Kunto saadaan kapasiteettimittauksella.")
          : stat("Akun kunto", soh != null ? n(soh) : "–", "%", L.viite_kwh ? `Uutena ${n(L.viite_kwh)} kWh, ${esc(L.viite_lahde || "")}` : "Alkuperäistä kapasiteettia ei tiedetä")]),
      L.kunto_piilotettu
        ? stat("Kennoryhmät", L.bricks_seen ? `${L.bricks_seen}/${L.brick_count || "–"}` : "–", "", "Jännite-ero näkyy mittauksen aikana ja raportissa")
        : stat("Kennoryhmien ero", L.brick_delta_mv != null && L.kennot_valmiit ? n(L.brick_delta_mv, 0) : (L.bricks_seen ? "Luetaan" : "–"), L.brick_delta_mv != null && L.kennot_valmiit ? "mV" : "", L.bricks_seen ? `${L.bricks_seen}/${L.brick_count || "–"} ryhmää luettu` : ""),
      stat("Mittarilukema", L.odometer_km != null ? n(L.odometer_km, 0) : "–", "km", L.vin || ""),
    ].join("") + (L.kennolukutapa ? `<div class="small muted" style="grid-column:1/-1">${esc(L.kennolukutapa)}</div>` : "");
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
      api("/api/kennot").then(r => {
        const b = $("#cellBox");
        if (!b) return;
        b.innerHTML = r.piilotettu
          ? `<div class="empty small">${r.luettu ? `${r.luettu} kennoryhmän jännitteet luettu.` : "Kennoryhmien jännitteitä luetaan."} Jännitteet, jännite-ero ja akun kunto näkyvät mittauksen aikana ja raportissa. Pikatarkastus kestää 1–3 minuuttia.</div>
             <div class="row" style="margin-top:10px;justify-content:center"><a class="btn primary sm" href="#/mittaus">Tee pikatarkastus</a></div>`
          : cellSvg(r.kennot);
      });
    }
    // väylätesti
    const vt = S.vaylatesti;
    const restricted = vt && !vt.kyselyt && !vt.kunnossa && vt.kehyksia > 300 &&
      !vt.viestit.some(r => r.pakollinen && r.nakyy) && vt.viestit.some(r => r.nakyy);
    // Kyselyihin perustuva merkki: muut ohjainlaitteet vastaavat, mutta akunhallinta ei.
    const bmsHiljaa = vt && vt.kyselyt && !vt.kunnossa && !vt.viestit.some(r => r.pakollinen && r.nakyy && r.tunniste !== "–");
    if (vt) {
      $("#busBox").innerHTML = `
        ${vt.kunnossa ? `<div class="notice good"><b>Yhteys toimii.</b> Kaikki mittauksessa tarvittavat tiedot vastaanotetaan.${L.platform_name ? ` Viestiarkkitehtuuri: ${esc(L.platform_name)}.` : ""}</div>` :
          (restricted ? `<div class="notice bad"><b>Tämä liitäntä ei välitä akun tietoja.</b> Autosta tulee viestejä, mutta vain muutama tieto, kuten nopeus ja virtatila. Kytke sovitin Teslan diagnostiikkaliittimeen välikaapelilla. Liitin on keskikonsolin takapäässä takamatkustajien puolella paneelin takana: vuosien 2019–2020 autoissa 20-pinninen ja 2021 alkaen 26-pinninen. <a href="#/ohjeet/yhdistaminen">Ohje</a></div>` :
          bmsHiljaa ? `<div class="notice warn"><b>Akunhallinta ei vielä vastaa.</b> Käynnistä auto (READY tai virta päällä) ja varmista, että yhdistettäessä on valittu auton oikea malli.</div>` :
          `<div class="notice warn"><b>Tietoja saatu ${vt.saatu}/${vt.tarvitaan}.</b> Odota hetki. Puuttuvat tiedot on merkitty alla. ${vt.kyselyt ? "Jos ne eivät ilmesty minuutin kuluessa, tarkista, että auto on käynnissä (READY) ja malli on oikea." : "Jos ne eivät ilmesty minuutin kuluessa, auto ei lähetä niitä tähän liitäntään."}</div>`)}
        ${vt.kunnossa && !this.busAuki ? `<div class="row" style="margin-top:10px"><button class="btn sm" id="busAuki" type="button">Näytä vastaanotetut tiedot</button></div>` : `
        <table class="t ${this.tech ? "tech" : ""}"><tr><th>Tieto</th><th class="techcol">Tunniste</th><th class="num techcol">Taajuus</th><th></th></tr>
        ${vt.viestit.map(r => `<tr><td>${esc(r.kuvaus)}${r.pakollinen ? "" : ' <span class="muted small">(lisätieto)</span>'}</td><td class="muted techcol">${r.tunniste}</td>
          <td class="num techcol">${r.taajuus_hz ? n(r.taajuus_hz, 1) + " Hz" : "–"}</td>
          <td class="num">${r.maara && !r.nakyy ? `<span class="pill warn">${esc(r.maara)}</span>` : r.nakyy ? `<span class="pill good">${r.maara ? esc(r.maara) : (vt.kyselyt ? "Vastaa" : "Vastaanotetaan")}</span>` : (r.pakollinen ? `<span class="pill warn">${vt.kyselyt ? "Ei vastaa" : "Ei näy"}</span>` : `<span class="pill">${vt.kyselyt ? "Ei vastaa" : "Ei näy"}</span>`)}</td></tr>`).join("")}
        </table>
        <div class="row" style="margin-top:10px"><button class="btn sm" id="techT" type="button">${this.tech ? "Piilota tekniset tiedot" : "Näytä tekniset tiedot"}</button>
          ${S.yhteys.simuloitu ? "" : `<button class="btn sm" id="scanB" type="button">Kartoita väylä</button>`}
          ${vt.kunnossa ? `<button class="btn sm" id="busKiinni" type="button">Piilota</button>` : ""}</div>`}`;
      const ba = $("#busAuki"), bk = $("#busKiinni"), tt = $("#techT");
      if (ba) ba.onclick = () => { this.busAuki = true; this.update(S); };
      if (bk) bk.onclick = () => { this.busAuki = false; this.update(S); };
      if (tt) tt.onclick = () => { this.tech = !this.tech; this.update(S); };
      const sb = $("#scanB");
      if (sb) sb.onclick = () => this.scan();
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
      <button class="btn sm" data-d="kiihdytys">Kiihdytykset</button>
      <button class="btn sm" data-d="pikalataus">Pikalataus</button>
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
  el.textContent = " · " + ({ park: "pysäköity", drive: "ajossa", kiihdytys: "kiihdytyksiä", pikalataus: "pikalatauksessa", charge: "latauksessa", sleep: "lepotilassa" }[d.tila] || d.tila);
  const acc = $("#demoAcc");
  if (acc && document.activeElement !== acc) acc.value = String(d.nopeutus);
}

// =====================================================================
// MITTAUS
// =====================================================================
const TYYPPI = {
  pikatarkastus: "Pikatarkastus", kapasiteetti: "Kapasiteettimittaus", taysi: "Täysi akkutesti",
  ajotesti: "Ajotesti", pika_ajo: "Pika-ajotesti", kuormitus: "Kuormitustesti",
  pikalataus: "Pikalataustesti", itsepurkaus: "Itsepurkaustesti",
};
const tyyppi = t => TYYPPI[t] || t;
const AJO_TURVA = ANDROID ? "Älä käytä sovellusta ajon aikana. Aseta puhelin telineeseen tai paikkaan, jossa se ei liiku ajossa." : "Älä käytä ohjelmaa ajon aikana. Aseta tietokone niin, ettei se liiku ajossa.";
// Muut merkit kuin Tesla (akunhallinta vastaa kyselyihin vain, kun auto on päällä tai latautuu)
const PIDA_PAALLA = "Pidä auto käynnistettynä (READY tai virta päällä) tämän vaiheen ajan, muuten akunhallinta ei vastaa kyselyihin. Ilmastointi kannattaa sammuttaa, jotta akun virta pysyy pienenä.";
const PHASE_TEXT_KYSELY = {
  lepo_alku: "Pidä auto pysäköitynä. Lepo tasaa kennojännitteet ja antaa tarkan lähtötason. Jos kytket latauksen jo nyt, mittaus siirtyy suoraan lataukseen.",
  odota_lataus: "Aseta latausrajaksi 100 % auton näytöllä tai sovelluksessa. Kytke latauskaapeli ja aloita lataus. Käytä tavallista vaihtovirtalatausta, enintään 11 kW. Pikalatausta ei käytetä, koska suuri virta lisää häviöitä ja lämpenemistä. Ohjelma tunnistaa latauksen alkamisen itse.",
  lepo_ajo_alku: "Pidä auto pysäköitynä. Lepo antaa tarkan lähtövarauksen. Jos lähdet ajamaan ennen lepojakson loppua, mittaus jatkuu, mutta tulos on epätarkempi.",
  lepo_itse_alku: "Pysäköi auto lepojakson ajaksi. Lopuksi ohjelma lukee kaikkien kennoryhmien lähtöjännitteet.",
  lepo_ajo_loppu: "Pysäköi auto lepojakson ajaksi. Lepo antaa tarkan loppuvarauksen. Älä kytke latausta ennen kuin mittaus on valmis.",
};
const PHASE_TEXT = {
  mittarilukema: ["Mittarilukema", "Auto ei ilmoittanut mittarilukemaa. Kirjoita lukema mittaristosta, niin se tulee raporttiin."],
  keruu: ["Tietoja luetaan", "Ohjelma lukee akunhallinnan tiedot ja kaikkien kennoryhmien jännitteet. Pidä auto paikallaan. Tarkastus kestää yleensä 1–3 minuuttia."],
  lepo_alku: ["Akku lepää ennen latausta", "Pidä auto pysäköitynä ja hereillä, esimerkiksi ilmastointi päällä tai Leiriytymistila käytössä, jotta sovitin saa virtaa. Lepo tasaa kennojännitteet ja antaa tarkan lähtötason. Jos kytket latauksen jo nyt, mittaus siirtyy suoraan lataukseen."],
  odota_lataus: ["Aloita lataus", "Aseta latausrajaksi 100 % Tesla-sovelluksessa tai auton näytöllä. Kytke latauskaapeli ja aloita lataus. Käytä tavallista vaihtovirtalatausta, enintään 11 kW. Pikalatausta ei käytetä, koska suuri virta lisää häviöitä ja lämpenemistä. Ohjelma tunnistaa latauksen alkamisen itse."],
  lataus: ["Lataus käynnissä", "Mittaus jatkuu itsestään, kunnes akunhallinta ilmoittaa akun täydeksi. Älä irrota sovitinta. " + (ANDROID
    ? "Puhelin saa jäädä autoon. Pidä se laturissa, jos lataus kestää pitkään."
    : "Tietokone saa jäädä autoon, kunhan se ei mene lepotilaan.")],
  lepo_loppu: ["Akku lepää latauksen jälkeen", "Lataus on valmis. Älä käytä autoa lepojakson aikana. Kennojännitteet tasaantuvat, ja lopulliset arvot tallennetaan raporttia varten."],
  lepo_ajo_alku: ["Akku lepää ennen ajoa", "Pidä auto pysäköitynä ja hereillä. Lepo antaa tarkan lähtövarauksen. Jos lähdet ajamaan ennen lepojakson loppua, mittaus jatkuu, mutta tulos on epätarkempi."],
  ajo: ["Aja autoa", "Aja tavalliseen tapaan, kunnes tavoite on saavutettu. Ajon voi jakaa useaan kertaan: valitse Jatka myöhemmin, kun pysäköit, ja jatka mittausta seuraavalla ajokerralla. Älä lataa autoa ennen kuin tavoite on saavutettu. " + AJO_TURVA],
  lepo_ajo_loppu: ["Akku lepää ajon jälkeen", "Pysäköi auto ja pidä se hereillä lepojakson ajan. Lepo antaa tarkan loppuvarauksen. Älä kytke latausta ennen kuin mittaus on valmis."],
  kuorma_lepo: ["Lepoarvot", "Pidä auto paikallaan. Ohjelma lukee kennoryhmien lepojännitteet ennen kiihdytyksiä."],
  kuormitus: ["Tee kiihdytykset", "Tee turvallisessa paikassa reippaita kiihdytyksiä, esimerkiksi 30–80 km/h, ja noudata liikennesääntöjä. Ohjelma laskee kiihdytykset itse. Pysäköi auto lopuksi, niin mittaus päättyy. " + AJO_TURVA],
  odota_pikalataus: ["Aloita pikalataus", "Jos autossa on akun esilämmitys, navigoi pikalaturille auton navigaattorilla, jotta akku lämpenee ja teho on vertailukelpoinen. Kytke laturi. Ohjelma tunnistaa latauksen alkamisen itse."],
  pikalataus: ["Pikalataus käynnissä", "Anna latauksen jatkua vähintään 80 %:iin. Mittaus päättyy, kun lataus loppuu, tai voit lopettaa sen painikkeesta."],
  lepo_itse_alku: ["Lepo ja lähtöarvot", "Pysäköi auto ja pidä se hereillä lepojakson ajan. Lopuksi ohjelma lukee kaikkien kennoryhmien lähtöjännitteet."],
  odotus: ["Seisonta", "Auto saa nyt nukkua. Valitse Jatka myöhemmin ja sulje ohjelma. Kun seisonta-aika on kulunut, herätä auto, kytke sovitin ja jatka mittausta Mittaus-sivulta. Älä aja tai lataa autoa seisonnan aikana."],
  itse_loppu: ["Loppuarvot", "Ohjelma lukee kennoryhmien loppujännitteet. Pidä auto paikallaan."],
  valmis: ["Valmis", "Mittaus on valmis."],
};
const TESTIRYHMAT = s => [
  ["Paikallaan", [
    ["pikatarkastus", "Akunhallinnan kapasiteettiarvio, kaikkien kennoryhmien jännitteet, lämpötilat ja elinkaaritiedot. Sopii esimerkiksi kauppatilanteeseen.", "1–3 minuuttia"],
    ["kapasiteetti", `Akun todellinen kapasiteetti mitattuna latauksen aikana. Aloita mahdollisimman tyhjästä akusta, enintään ${s.kapasiteetti_lahto_soc_max} %:n varauksesta.`, "Yleensä 8–14 tuntia"],
    ["itsepurkaus", "Kennoryhmien jännitteet seisonnan alussa ja lopussa. Paljastaa kennoryhmän, joka purkautuu muita nopeammin. LFP-akussa aloitetaan täydestä akusta.", `Yön yli, vähintään ${s.itsepurkaus_tunnit} tuntia`],
  ]],
  ["Ajossa", [
    ["taysi", "Kapasiteetti mitataan kahdesti: purkamalla ajossa ja lataamalla täyteen. Kaksi riippumatonta mittausta antaa tarkimman tuloksen.", "Ajo täydestä akusta alle 15 %:iin ja lataus, yleensä 1–2 päivää"],
    ["ajotesti", `Kapasiteetti mitattuna tavallisessa ajossa. Aloita täydestä akusta ja aja enintään ${s.ajo_loppu_soc} %:n varaukseen. Ajon voi jakaa useaan kertaan.`, "Yksi tai useampi ajokerta"],
    ["pika_ajo", `Tarkistaa, vastaako akunhallinnan kapasiteettiarvio ajossa mitattua. Varaus laskee ${s.pika_ajo_soc} %-yksikköä. Ei anna omaa kuntoprosenttia.`, "Noin 1–2 tunnin ajo"],
    ["kuormitus", `Kennoryhmien sisäinen resistanssi ${s.kuormitus_tapahtumat} reippaalla kiihdytyksellä. Paljastaa heikon kennoryhmän tai liitoksen. Edellyttää: varaus 40–80 %, akku 10–30 °C ja lämpötilaero alle 2 °C.`, "Noin 10 minuuttia"],
  ]],
  ["Pikalaturilla", [
    ["pikalataus", "Latausteho, latauskäyrä ja kennoryhmien tasaisuus suurella latausvirralla. Aloita alle 30 %:n varauksesta.", "30–45 minuuttia"],
  ]],
];
const SKIP = {
  lepo_alku: ["Lyhennä lepoa", "Lyhennetäänkö lepojakso? Lyhyt lepo heikentää tuloksen tarkkuutta.", "Lyhennä lepoa"],
  lataus: ["Lopeta lataus tähän", "Lopetetaanko lataus tähän? Kapasiteetti lasketaan siihen asti mitatusta osuudesta.", "Lopeta lataus"],
  lepo_loppu: ["Valmis nyt", "Lopetetaanko lepojakso ja tehdäänkö raportti nyt?", "Tee raportti nyt"],
  lepo_ajo_alku: ["Lyhennä lepoa", "Lyhennetäänkö lepojakso? Lyhyt lepo heikentää tuloksen tarkkuutta.", "Lyhennä lepoa"],
  ajo: ["Lopeta ajo tähän", "Lopetetaanko ajo-osuus tähän? Tulos lasketaan siihen asti ajetusta osuudesta, ja lyhyt ajo heikentää tarkkuutta.", "Lopeta ajo"],
  lepo_ajo_loppu: ["Valmis nyt", "Lopetetaanko lepojakso ja tehdäänkö raportti nyt? Lyhyt lepo heikentää tuloksen tarkkuutta.", "Tee raportti nyt"],
  kuorma_lepo: ["Ohita lepoarvot", "Ohitetaanko lepoarvojen lukeminen?", "Ohita lepoarvot"],
  kuormitus: ["Valmis nyt", "Lopetetaanko kuormitustesti ja tehdäänkö raportti nyt?", "Tee raportti nyt"],
  pikalataus: ["Valmis nyt", "Lopetetaanko pikalataustesti ja tehdäänkö raportti nyt?", "Tee raportti nyt"],
  lepo_itse_alku: ["Lyhennä lepoa", "Lyhennetäänkö lepojakso? Lähtöarvot luetaan heti.", "Lyhennä lepoa"],
};

views.mittaus = {
  render() {
    view.innerHTML = `<div class="head"><div><h1>Mittaus</h1><div class="muted" id="mSub">Valitse auto ja mittaus</div></div></div><div id="mBody"></div>`;
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
    if ($("#mSub")) $("#mSub").textContent = "Valitse auto ja mittaus";
    const { ajoneuvot } = await api("/api/ajoneuvot");
    const s = await api("/api/asetukset");
    const known = S && S.auto_tunnettu ? S.auto_tunnettu.id : null;
    const b = $("#mBody");
    if (!ajoneuvot.length) {
      b.innerHTML = `<div class="card empty"><p>Lisää ensin auto. Ohjelma tunnistaa mallin valmistenumerosta.</p><a class="btn primary" href="#/autot/uusi">Lisää auto</a></div>`;
      return;
    }
    const { mittaukset } = await api("/api/mittaukset");
    const open = mittaukset.filter(t => t.tila === "kesken");
    b.innerHTML = `
      ${open.length ? `<div class="card"><h2>Kesken olevat mittaukset</h2>
        <p class="small muted">Nämä mittaukset jatkuvat siitä, mihin ne jäivät. Kytke sovitin samaan autoon ja valitse Jatka.</p>
        <table class="t">${open.map(t => `<tr><td><b>${esc(tyyppi(t.tyyppi))}</b><div class="small muted">${esc(t.ajoneuvo || "")}${t.rekisteri ? " · " + esc(t.rekisteri) : ""} · aloitettu ${date(t.aloitettu)}</div></td>
          <td class="num" style="white-space:nowrap"><button class="btn sm primary" data-jatka="${t.id}">Jatka</button> <button class="btn sm" data-hylkaa="${t.id}">Hylkää</button></td></tr>`).join("")}</table></div>` : ""}
      <div id="mWarn"></div>
      <div class="card">
        <h2>1. Valitse auto</h2>
        <select id="mVeh">${ajoneuvot.map(v => `<option value="${v.id}" ${v.id === known ? "selected" : ""}>${esc(v.nimi)}${v.rekisteri ? " · " + esc(v.rekisteri) : ""}${v.vin ? " · " + esc(v.vin) : ""}</option>`).join("")}</select>
        <div id="mVehHint" class="small muted" style="margin-top:8px"></div>
      </div>
      <div class="card">
        <h2>2. Valitse mittaus</h2>
        ${TESTIRYHMAT(s).map(([g, items]) => [g, items.filter(([k]) => !(S.live && (S.live.ei_testit || []).includes(k)))]).filter(([, items]) => items.length).map(([g, items]) => `<h3 class="grp">${g}</h3><div class="choice">${items.map(([k, txt, d]) =>
          `<button data-t="${k}"><div class="ttl">${tyyppi(k)}</div><div class="small muted">${esc(txt)}</div><div class="dur">${esc(d)}<span data-hinta="${k}"></span></div></button>`).join("")}</div>`).join("")}
      </div>
      <div class="card">
        <h2>3. Tiedot raporttiin</h2>
        <div class="grid g3">
          <label class="f"><span>Mittarilukema (km)</span><input id="mOdo" inputmode="numeric" placeholder="Luetaan autosta, jos tyhjä"></label>
          <label class="f"><span>Mittauksen suorittaja</span><input id="mWho" maxlength="80" value="${esc(s.mittaaja)}" placeholder="Nimi tai yritys"></label>
          <label class="f"><span>Lisätiedot</span><input id="mNote" placeholder="Esimerkiksi tilaajan nimi"></label>
        </div>
        <p class="small muted">Mittauksen suorittaja näkyy raportissa ja akveri.fi:n tarkistussivulla. Tulokset luetaan auton akunhallinnasta, eikä niitä voi muuttaa.</p>
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
    // Piilotetaan testit, jotka eivät anna todellista tulosta valitun auton mallilla (myös ilman yhteyttä).
    const rajaa = () => {
      const v = vs[$("#mVeh").value] || {};
      const ei = new Set([...(v.ei_testit || []), ...((S && S.live && S.live.ei_testit) || [])]);
      $$(".choice button[data-t]", b).forEach(x => {
        const pois = ei.has(x.dataset.t);
        x.style.display = pois ? "none" : "";
        if (pois && x.classList.contains("sel")) { x.classList.remove("sel"); this.type = null; this.updateNew(S); }
      });
      $$(".choice", b).forEach(c => {
        const nakyy = [...c.querySelectorAll("button[data-t]")].some(x => x.style.display !== "none");
        c.style.display = nakyy ? "" : "none";
        const h = c.previousElementSibling;
        if (h && h.classList.contains("grp")) h.style.display = nakyy ? "" : "none";
      });
    };
    $("#mVeh").onchange = () => { hint(); rajaa(); }; hint();
    $$("[data-jatka]", b).forEach(x => (x.onclick = () => act(() => api(`/api/mittaukset/${x.dataset.jatka}/jatka`, { method: "POST" }), "Mittaus jatkuu").then(poll)));
    $$("[data-hylkaa]", b).forEach(x => (x.onclick = async () => {
      if (!(await kysy("Hylätäänkö kesken oleva mittaus? Siitä ei tehdä raporttia.", { ok: "Hylkää mittaus", vaara: true }))) return;
      act(() => api(`/api/mittaukset/${x.dataset.hylkaa}/hylkaa`, { method: "POST" }), "Mittaus hylätty").then(() => { this.mode = null; poll(); });
    }));
    $$(".choice button").forEach(btn => (btn.onclick = () => {
      $$(".choice button").forEach(x => x.classList.remove("sel"));
      btn.classList.add("sel");
      this.type = btn.dataset.t;
      this.updateNew(S);
    }));
    this.type = null;
    rajaa();
    // Mittausten hinnat haetaan palvelimelta: hallinnassa tehty muutos näkyy tässä heti.
    this.hinnat = null;
    if (!(S && S.yhteys.simuloitu)) api("/api/krediitit").then(d => {
      this.hinnat = d.hinnat || null; this.saldo = d.saldo; this.testitili = !!d.testitili;
      // Hinta näkyy jokaisessa mittaustyypin kortissa, jotta valinnan voi tehdä hinnan perusteella
      $$("[data-hinta]").forEach(e => { const h = this.hinnat && this.hinnat[e.dataset.hinta]; e.innerHTML = h ? ` · <b>${h}</b> ${h === 1 ? "krediitti" : "krediittiä"}` : ""; });
      this.updateNew(S);
    }).catch(() => {});
    $("#mStart").onclick = () => !$("#mWho").value.trim() ? ilmoita("Kirjoita mittauksen suorittaja (nimi tai yritys). Se näkyy raportissa.") : act(() => api("/api/mittaukset", { method: "POST", body: {
      ajoneuvo_id: Number($("#mVeh").value), tyyppi: this.type, mittarilukema: $("#mOdo").value,
      mittaaja: $("#mWho").value.trim(), lisatiedot: $("#mNote").value } }), S && S.yhteys.simuloitu ? "Esittelymittaus aloitettu" : "Mittaus aloitettu").then(poll);
  },
  updateNew(S) {
    const w = $("#mWarn"), st = $("#mStart");
    if (!w || !st) return;
    let msg = "";
    // Auto ei ilmoita akun kuntoa (esim. akunhallinnan vanha ohjelmistoversio): pikatarkastusta ei voi ostaa.
    const puuttuu = !!(S.live && S.live.kunto_puuttuu);
    const pk = $('.choice button[data-t="pikatarkastus"]');
    if (pk) {
      pk.classList.toggle("estetty", puuttuu);
      let h = pk.querySelector(".estoteksti");
      if (puuttuu && !h) { h = document.createElement("div"); h.className = "estoteksti small"; h.textContent = "Tämä auto ei ilmoita akun kuntoa. Akun kunto saadaan kapasiteettimittauksella."; pk.appendChild(h); }
      if (!puuttuu && h) h.remove();
    }
    if (puuttuu && this.type === "pikatarkastus") msg = `<div class="notice warn"><b>Pikatarkastus ei ole saatavilla tälle autolle.</b> Auton akunhallinta ei ilmoita akun kuntoa. Valitse kapasiteettimittaus.</div>`;
    else if (!S.yhteys.kaynnissa) msg = `<div class="notice warn"><b>Ei yhteyttä autoon.</b> Yhdistä sovittimeen <a href="#/yleiskuva">Yleiskuva</a>-sivulla.</div>`;
    else if (!S.vaylatesti || !S.vaylatesti.kunnossa) msg = `<div class="notice warn">Odotetaan akun tietoja autosta…</div>`;
    else if (this.type === "kapasiteetti" && S.live.soc_ui > 15) msg = `<div class="notice warn">Akun varaus on ${n(S.live.soc_ui)} %. Tarkin tulos saadaan, kun lataus aloitetaan enintään 15 %:n varauksesta. Voit silti aloittaa mittauksen.</div>`;
    else if ((this.type === "taysi" || this.type === "ajotesti") && S.live.soc_ui != null && S.live.soc_ui < 80) msg = `<div class="notice warn">Akun varaus on ${n(S.live.soc_ui)} %. Tarkin tulos saadaan, kun ajo aloitetaan vähintään 80 %:n varauksesta. Voit silti aloittaa mittauksen.</div>`;
    else if (this.type === "pikalataus" && S.live.soc_ui != null && S.live.soc_ui > 30) msg = `<div class="notice warn">Akun varaus on ${n(S.live.soc_ui)} %. Latauskäyrä saadaan kattavimmin, kun lataus aloitetaan alle 30 %:n varauksesta.</div>`;
    if (w.innerHTML !== msg) w.innerHTML = msg;
    const ready = S.yhteys.kaynnissa && S.vaylatesti && S.vaylatesti.kunnossa && this.type && !(puuttuu && this.type === "pikatarkastus");
    st.disabled = !ready;
    const hinta = this.hinnat && this.hinnat[this.type];
    $("#mStartHint").textContent = !this.type ? "Valitse mittauksen tyyppi." : S.yhteys.simuloitu ? "Esittelytilan mittaus ei käytä krediittejä."
      : this.testitili ? "Testitili: mittaus ei käytä krediittejä."
      : hinta ? `Hinta ${hinta} ${hinta === 1 ? "krediitti" : "krediittiä"}${this.saldo != null ? ` (sinulla ${this.saldo})` : ""}. Jos mittaus keskeytyy heti alussa, krediitit palautuvat.`
      : "Mittauksen hinta näytetään, kun yhteys AKVERI-palveluun on muodostettu.";
  },
  renderActive() {
    $("#mBody").innerHTML = `
      <div class="steps" id="aSteps"></div>
      <div class="grid g2">
        <div class="card"><h2 id="aTitle"></h2><p id="aText"></p><div id="aProg"></div>
          <div class="row" style="margin-top:14px"><button class="btn" id="aSkip"></button><button class="btn primary" id="aPause" style="display:none">Jatka myöhemmin</button><span class="spacer"></span><button class="btn danger" id="aCancel">Keskeytä mittaus</button></div>
        </div>
        <div class="card"><h2>Tarkistukset</h2><ul class="checks" id="aChecks"></ul>
          <h3>Mittaus</h3><dl class="kv" id="aKv"></dl></div>
      </div>
      <div id="aDemo"></div>
      <div class="card"><h2>Huomiot</h2><div id="aNotes" class="small muted">Ei huomioita.</div></div>`;
    $("#aCancel").onclick = async () => {
      if (!(await kysy("Keskeytetäänkö mittaus? Keskeytetystä mittauksesta ei tehdä raporttia.", { ok: "Keskeytä mittaus", vaara: true }))) return;
      act(() => api("/api/mittaukset/aktiivinen/keskeyta", { method: "POST" })).then(r => {
        toast({ peruttu: "Mittaus keskeytetty. Krediitti palautui tilillesi.", peru_odottaa: "Mittaus keskeytetty. Krediitti palautuu, kun verkkoyhteys palaa.",
          hyvitettavissa: "Mittaus keskeytetty. Jos keskeytys johtui AKVERIsta, pyydä hyvitystä mittauksen sivulla." }[r.lupa] || "Mittaus keskeytetty");
        this.lastId = null; poll(); });
    };
    $("#aPause").onclick = () => act(() => api("/api/mittaukset/aktiivinen/tauko", { method: "POST" }),
      "Mittaus tallennettu. Jatka sitä myöhemmin Mittaus-sivulta.").then(() => { this.lastId = null; poll(); });
    $("#aSkip").onclick = async () => {
      const [, q, ok] = SKIP[S.mittaus.vaihe] || [];
      if (q && !(await kysy(q, { ok, peru: "Jatka mittausta" }))) return;
      act(() => api("/api/mittaukset/aktiivinen/ohita", { method: "POST" })).then(poll);
    };
    if (S.yhteys.simuloitu) { $("#aDemo").innerHTML = demoControls(); bindDemo($("#aDemo")); }
  },
  updateActive(S) {
    const m = S.mittaus, L = S.live;
    this.lastId = m.test_id;
    $("#mSub").textContent = tyyppi(m.tyyppi) + ` · kesto ${dur(m.kesto_s)}` + (m.osat > 1 ? ` · osa ${m.osat}` : "");
    const idx = m.vaiheet.findIndex(v => v.id === m.vaihe);
    $("#aSteps").innerHTML = m.vaiheet.map((v, i) => `<div class="s ${i < idx ? "done" : (i === idx ? "now" : "")}">${i + 1}. ${esc(v.nimi)}</div>`).join("");
    let [ttl, txt] = PHASE_TEXT[m.vaihe] || ["", ""];
    if (S.live && S.live.kyselyalusta) {
      // Muut merkit kuin Tesla: akunhallinta vastaa vain, kun auto on päällä tai latautuu
      if (PHASE_TEXT_KYSELY[m.vaihe]) txt = PHASE_TEXT_KYSELY[m.vaihe];
      if (/^(lepo_|kuorma_lepo|itse_loppu|keruu)/.test(m.vaihe)) txt += " " + PIDA_PAALLA;
    }
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
      const kaikki = m.kennot_yht && m.kennot_luettu >= m.kennot_yht;
      prog = `<div class="row small"><span>Kennoryhmiä luettu ${m.kennot_luettu}/${m.kennot_yht || "–"}</span></div><div class="bar"><i style="width:${p}%"></i></div>
        <p class="small muted" style="margin-top:8px">${kaikki ? "Kaikki kennoryhmät on luettu. Tarkastus varmistaa vielä lukemat ja valmistuu automaattisesti." : "Tarkastus valmistuu automaattisesti, kun kaikki tiedot on luettu."}</p>`;
    } else if (m.vaihe === "odota_lataus") {
      prog = `<div class="notice">Odotetaan latauksen alkamista. Varaus nyt ${n(L.soc_ui)} %.</div>`;
    } else if (m.vaihe === "ajo") {
      const a = m.ajo_alku_soc, z = m.ajo_tavoite_soc, c = m.soc_nyt;
      const p = (a != null && z != null && c != null && a > z) ? Math.max(0, Math.min(100, (a - c) / (a - z) * 100)) : 0;
      prog = `<div class="row small"><span>Tavoite: ${esc(m.ajo_tavoite)}</span><span class="spacer"></span><span class="muted">alussa ${n(a)} %</span></div><div class="bar"><i style="width:${p}%"></i></div>
        <div class="grid g3" style="margin-top:14px">
          ${miniStat("Varaus nyt", n(c), "%")}
          ${miniStat("Ajettu", m.ajo_km != null ? n(m.ajo_km, 0) : "–", "km")}
          ${miniStat("Energiaa akusta", n(m.ajo_kwh, 1), "kWh")}
        </div>${m.tavoite_saavutettu ? `<div class="notice good" style="margin-top:12px"><b>Tavoite saavutettu.</b> Pysäköi auto, niin mittaus jatkuu lepojaksolla.</div>` : ""}`;
    } else if (m.tyyppi === "kuormitus" && m.vaihe === "kuormitus") {
      const p = Math.min(100, m.kuorma_tapahtumat / m.kuorma_tavoite * 100);
      prog = `<div class="row small"><span>Kiihdytyksiä ${m.kuorma_tapahtumat}/${m.kuorma_tavoite}</span><span class="spacer"></span><span class="muted">suurin teho ${m.teho_max_kw ? n(m.teho_max_kw, 0) + " kW" : "–"}</span></div><div class="bar"><i style="width:${p}%"></i></div>
        ${m.kuorma_tapahtumat >= m.kuorma_tavoite ? `<div class="notice good" style="margin-top:12px">Kiihdytyksiä on riittävästi. Pysäköi auto, niin mittaus päättyy.</div>` : ""}`;
    } else if (m.vaihe === "pikalataus") {
      prog = `<div class="row small"><span>Varaus ${n(m.soc_nyt)} %</span></div><div class="bar"><i style="width:${m.soc_nyt || 0}%"></i></div>
        <div class="grid g3" style="margin-top:14px">
          ${miniStat("Teho nyt", m.teho_kw != null ? n(Math.max(0, m.teho_kw), 0) : "–", "kW")}
          ${miniStat("Huipputeho", m.huipputeho_kw != null ? n(m.huipputeho_kw, 0) : "–", "kW")}
          ${miniStat("Ladattu", n(m.lataus_kwh, 1), "kWh")}
        </div>`;
    } else if (m.vaihe === "odota_pikalataus") {
      prog = `<div class="notice">Odotetaan pikalatauksen alkamista. Varaus nyt ${n(L.soc_ui)} %.</div>`;
    } else if (m.vaihe === "odotus") {
      const p = Math.min(100, m.odotus_s / m.odotus_tavoite_s * 100);
      prog = `<div class="row small"><span>Seisonta ${dur(m.odotus_s)}</span><span class="spacer"></span><span class="muted">tavoite ${dur(m.odotus_tavoite_s)}</span></div><div class="bar"><i style="width:${p}%"></i></div>`;
    }
    if (m.vaihe === "mittarilukema") {
      // Auto ei ilmoittanut mittarilukemaa: se kysytään ennen raportin tekemistä. Kenttää ei piirretä uudelleen kirjoittaessa.
      if (!$("#aOdo")) {
        $("#aProg").innerHTML = `<label class="f"><span>Mittarilukema (km)</span><input id="aOdo" inputmode="numeric" autocomplete="off"></label>
          <div class="row" style="margin-top:10px"><button class="btn primary" id="aOdoOk">Tee raportti</button><button class="btn" id="aOdoEi">Lukema ei ole tiedossa</button></div>`;
        const laheta = km => act(() => api("/api/mittaukset/aktiivinen/mittarilukema", { method: "POST", body: { mittarilukema: km } })).then(poll);
        $("#aOdoOk").onclick = () => {
          const km = $("#aOdo").value.replace(/\s/g, "");
          if (!/^\d{1,7}$/.test(km)) return ilmoita("Kirjoita mittarilukema kilometreinä mittaristosta.");
          laheta(km);
        };
        $("#aOdoEi").onclick = () => laheta(null);
        $("#aOdo").focus();
      }
    } else $("#aProg").innerHTML = prog;
    const skip = (SKIP[m.vaihe] || [])[0];
    $("#aSkip").style.display = skip ? "" : "none";
    $("#aSkip").textContent = skip || "";
    $("#aPause").style.display = m.voi_tauottaa ? "" : "none";
    $("#aChecks").innerHTML = m.tarkistukset.map(c => `<li><span class="ic ${c.ok === true ? "ok" : (c.ok === false ? "no" : "na")}">${c.ok === true ? "✓" : (c.ok === false ? "!" : "·")}</span>
      <div style="flex:1"><div class="row"><span>${esc(c.nimi)}</span><span class="spacer"></span><b>${esc(c.arvo)}</b></div>${c.ohje ? `<div class="small muted">${esc(c.ohje)}</div>` : ""}</div></li>`).join("");
    $("#aKv").innerHTML = `<dt>Varaus</dt><dd>${n(L.soc_ui)} %</dd><dt>Jännite</dt><dd>${n(L.pack_v)} V</dd><dt>Virta</dt><dd>${n(L.pack_i)} A</dd>
      <dt>Energia akkuun</dt><dd>${n(m.e_in_kwh, 2)} kWh</dd><dt>Energia akusta</dt><dd>${n(m.e_out_kwh, 2)} kWh</dd>
      <dt>Kennoryhmien ero</dt><dd>${L.brick_delta_mv != null ? `${n(L.brick_delta_mv, 0)} mV` : (L.bricks_seen ? "Näkyy tuloksessa" : "–")}</dd>`;
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
    if (arg && location.hash.endsWith("/muokkaa")) {
      return api(`/api/ajoneuvot/${Number(arg)}`).then(v => this.renderForm(v));
    }
    if (arg) return this.renderOne(Number(arg));
    this.renderList();
  },
  async renderList() {
    const [{ ajoneuvot }, E] = await Promise.all([api("/api/ajoneuvot"), esittelySallittu()]);
    const hasEx = ajoneuvot.some(v => v.opitut && v.opitut.esimerkki);
    view.innerHTML = `<div class="head"><div><h1>Autot</h1><div class="muted">Tallennetut autot ja niiden mittaushistoria</div></div>
      <div class="row">${hasEx || E ? `<button class="btn" id="vEx">${hasEx ? "Poista esimerkkiautot" : "Lisää esimerkkiautot"}</button>` : ""}<a class="btn primary" href="#/autot/uusi">Lisää auto</a></div></div>
      ${hasEx || !E ? "" : `<p class="small muted" style="margin:-8px 0 16px">Esimerkkiautoissa (vähintään yksi auto kustakin tuetusta merkistä) on valmiit raportit kaikista mittaustyypeistä, joten näet heti, miltä kaikki näyttää.</p>`}
      <div class="card" id="vList"></div>`;
    if ($("#vEx")) $("#vEx").onclick = async () => hasEx
      ? ((await kysy("Poistetaanko esimerkkiautot ja niiden mittaukset? Omiin autoihisi ei kosketa.", { ok: "Poista esimerkkiautot", vaara: true })) &&
         act(() => api("/api/esimerkit", { method: "POST", body: { poista: true } }), "Esimerkkiautot poistettu").then(() => this.renderList()))
      : act(() => api("/api/esimerkit", { method: "POST", body: {} }), "Esimerkkiautot lisätty").then(() => this.renderList());
    $("#vList").innerHTML = ajoneuvot.length ? `<table class="t"><tr><th>Auto</th><th class="hide-m">Valmistenumero</th><th>Rekisteri</th><th class="num">Kunto</th><th class="num hide-m">Mittauksia</th><th class="hide-m">Viimeisin</th></tr>
      ${ajoneuvot.map(v => `<tr class="click" data-id="${v.id}"><td><b>${esc(v.nimi)}</b>${v.opitut && v.opitut.esimerkki ? ` <span class="pill">Esimerkki</span>` : ""}<div class="small muted">${esc(v.malli || "Malli tunnistetaan mittauksessa")}</div></td>
        <td class="hide-m">${esc(v.vin || "–")}</td><td>${esc(v.rekisteri || "–")}</td>
        <td class="num">${v.opitut && v.opitut.viimeisin_kunto_pct ? n(v.opitut.viimeisin_kunto_pct) + " %" : "–"}</td>
        <td class="num hide-m">${v.mittauksia}</td><td class="hide-m">${date(v.viimeisin, false)}</td></tr>`).join("")}</table>`
      : `<div class="empty">Ei tallennettuja autoja.</div>`;
    $$("tr.click").forEach(r => (r.onclick = () => (location.hash = `#/autot/${r.dataset.id}`)));
  },
  async renderForm(v) {
    const { mallit } = await api("/api/mallit");
    // Uutta autoa lisättäessä autosta luettu valmistenumero esitäytetään, jos sitä ei ole vielä tallennettu.
    const live = (!v && S && S.live && S.live.vin && !S.auto_tunnettu) ? S.live.vin : "";
    const sel0 = v ? v.malli_id || "" : (S && S.live && S.live.malli_id) || "";
    const brand0 = merkki(mallit.find(m => m.id === sel0)) || "Tesla";
    const bk = v ? { html: `<a class="back" href="#/autot/${v.id}">← ${esc(v.nimi)}</a>` } : backLink("#/autot", "Autot");
    view.innerHTML = `${bk.html}<div class="head"><div><h1>${v ? "Muokkaa autoa" : "Lisää auto"}</h1><div class="muted">Malli tunnistetaan valmistenumerosta. Tarkentuneet tiedot tallentuvat autolle ensimmäisen mittauksen jälkeen.</div></div></div>
      <div class="grid g2">
        <div class="card" id="vForm">
          <label class="f"><span>Valmistenumero (VIN)</span><div class="row" style="flex-wrap:nowrap"><input name="vin" value="${esc(v ? v.vin || "" : live)}" maxlength="17" style="text-transform:uppercase">
            ${S && S.live && S.live.vin ? `<button class="btn sm" id="vRead" type="button">Lue autosta</button>` : ""}</div></label>
          <div class="grid g2">
            <label class="f"><span>Nimi</span><input name="nimi" value="${esc(v ? v.nimi : "")}" placeholder="Esimerkiksi asiakkaan auto"></label>
            <label class="f"><span>Rekisterinumero</span><input name="rekisteri" value="${esc(v ? v.rekisteri || "" : "")}"></label>
            <label class="f"><span>Omistaja tai tilaaja</span><input name="omistaja" value="${esc(v ? v.omistaja || "" : "")}"></label>
            <label class="f"><span>Vuosimalli</span><input name="vuosimalli" inputmode="numeric" value="${esc(v ? v.vuosimalli || "" : "")}"></label>
            <label class="f"><span>Käyttöönottopäivä</span><input name="kayttoonotto" value="${esc(v ? v.kayttoonotto || "" : "")}" placeholder="pp.kk.vvvv"><small class="muted">Rekisteriotteesta. Tarvitaan akkutakuun laskemiseen.</small></label>
            <label class="f"><span>Väri</span><input name="vari" value="${esc(v ? v.vari || "" : "")}"></label>
          </div>
          <div class="grid g2">
            <label class="f"><span>Merkki</span><select id="vBrand">${MERKIT.map(b => `<option ${b === brand0 ? "selected" : ""}>${esc(b)}</option>`).join("")}</select></label>
            <label class="f"><span>Malli ja akku</span><select name="malli_id" id="vModel">${malliOptions(mallit, brand0, sel0)}</select></label>
          </div>
          <label class="f"><span>Alkuperäinen kapasiteetti (kWh), jos tiedossa</span><input name="viite_kayttaja" inputmode="decimal" value="${esc(v && v.opitut && v.opitut.viite_kayttaja ? String(v.opitut.viite_kayttaja).replace(".", ",") : "")}" placeholder="Luetaan auton akunhallinnasta"></label>
          <label class="f"><span>Lisätiedot</span><textarea name="lisatiedot">${esc(v ? v.lisatiedot || "" : "")}</textarea></label>
          <div class="row"><button class="btn primary" id="vSave">${v ? "Tallenna" : "Lisää auto"}</button><a class="btn" href="#/autot${v ? "/" + v.id : ""}">Peruuta</a></div>
        </div>
        <div class="card"><h2>Tunnistus</h2><div id="vInfo" class="small muted">Syötä valmistenumero.</div></div>
      </div>`;
    const brandSel = $("#vBrand"), modelSel = $("#vModel");
    const setBrand = (b, keep) => {
      if (!MERKIT.includes(b)) return;
      brandSel.value = b;
      modelSel.innerHTML = malliOptions(mallit, b, keep ? modelSel.value : "");
    };
    brandSel.onchange = () => setBrand(brandSel.value, false);
    const vinInput = $("[name=vin]");
    const decode = async () => {
      const val = vinInput.value.trim();
      if (val.length < 17) { $("#vInfo").innerHTML = "Valmistenumerossa on 17 merkkiä."; return; }
      const r = await api("/api/vin", { method: "POST", body: { vin: val } });
      const t = r.tiedot;
      if (!t.kelvollinen) { $("#vInfo").innerHTML = `<div class="notice warn">${esc(t.virheet.join(" "))}</div>`; return; }
      $("#vInfo").innerHTML = `<dl class="kv"><dt>Valmistaja</dt><dd>${esc(t.valmistaja)}</dd><dt>Malli</dt><dd>${esc(t.malli || "Valitse alta")}</dd>
        <dt>Vuosimalli</dt><dd>${esc(t.vuosimalli || "–")}</dd><dt>Tehdas</dt><dd>${esc(t.tehdas || "–")}</dd>
        <dt>Voimalinja</dt><dd>${esc(t.voimalinja || "–")}</dd><dt>Akku</dt><dd>${esc(t.akkutyyppi || "–")}</dd></dl>
        ${t.huomautus ? `<div class="notice warn" style="margin-top:14px">${esc(t.huomautus)}</div>` : ""}
        ${r.malli ? `<div class="notice" style="margin-top:14px">Todennäköinen mallipohja: <b>${esc(r.malli.nimi)}</b>. Viitekapasiteetti ${n(r.malli.viite_kwh)} kWh${r.malli.likiarvo ? " (likiarvo)" : ""}, ${esc(r.malli.kemia)}${cellsTxt(r.malli.sarjakennot) ? ", " + cellsTxt(r.malli.sarjakennot) + " kennoryhmää" : ""}.
          <div class="small muted">Peruste: ${esc(r.perusteet.join(", "))}. ${r.malli.alusta === "sx" ? "Tämän mallin akunhallinta ei ilmoita alkuperäistä kapasiteettia. Syötä se alle, jos tiedät sen." : "Ensimmäinen mittaus varmistaa tiedot auton akunhallinnasta."}</div></div>` : (t.merkki && t.merkki !== "Tesla" ? `<div class="notice" style="margin-top:14px">Valmistenumerosta ei voi päätellä mallia ja akun kokoa. <b>Valitse malli alta</b> rekisteriotteen tai myyntitietojen mukaan.</div>` : "")}
        ${r.liitanta ? guideHtml(r.liitanta) : ""}`;
      // Merkki päätellään valmistenumerosta
      const vb = t.merkki || (t.kelvollinen ? "Tesla" : null);
      if (vb && vb !== brandSel.value) setBrand(vb, false);
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
    const o = v.opitut || {};
    const m = v.malli || {};
    view.innerHTML = `<a class="back" href="#/autot">← Autot</a><div class="head"><div><h1>${esc(v.nimi)}</h1><div class="muted">${esc(m.nimi || "Malli tunnistetaan ensimmäisessä mittauksessa")}</div></div>
      <div class="row"><button class="btn" id="vEdit">Muokkaa</button><a class="btn primary" href="#/mittaus">Uusi mittaus</a></div></div>
      ${!v.mittaukset.length ? `<div class="notice"><b>Seuraava vaihe:</b> tee autolle pikatarkastus. Ohjelma lukee silloin akunhallinnasta alkuperäisen kapasiteetin, kennoryhmien määrän ja akun tyypin ja tallentaa ne autolle.</div>` : ""}
      <div class="grid g2">
        <div class="card"><h2>Perustiedot</h2><dl class="kv">
          <dt>Valmistenumero</dt><dd>${esc(v.vin || "–")}</dd><dt>Rekisteri</dt><dd>${esc(v.rekisteri || "–")}</dd>
          <dt>Omistaja</dt><dd>${esc(v.omistaja || "–")}</dd><dt>Vuosimalli</dt><dd>${esc(v.vuosimalli || "–")}</dd>
          <dt>Käyttöönottopäivä</dt><dd>${esc(v.kayttoonotto || "–")}</dd>
          <dt>Tehdas</dt><dd>${esc((v.vin_tiedot || {}).tehdas || "–")}</dd><dt>Voimalinja</dt><dd>${esc((v.vin_tiedot || {}).voimalinja || "–")}</dd></dl></div>
        <div class="card"><h2>Akku</h2><dl class="kv">
          <dt>Akkutyyppi</dt><dd>${esc(m.kennotyyppi || m.kemia || o.kemia || "–")}</dd>
          <dt>Kennoryhmiä</dt><dd>${esc(o.kennoryhmat || cellsTxt(m.sarjakennot) || "–")}${o.kennoryhmat ? " (mitattu)" : (m.sarjakennot ? " (mallipohja)" : "")}</dd>
          <dt>Alkuperäinen kapasiteetti</dt><dd>${o.bol_kwh ? n(o.bol_kwh) + " kWh (akunhallinta)" : (o.viite_kayttaja ? n(o.viite_kayttaja) + " kWh (ilmoitettu)" : (m.viite_kwh ? n(m.viite_kwh) + " kWh (mallitaulukko)" : "–"))}</dd>
          <dt>Viimeisin kunto</dt><dd>${o.viimeisin_kunto_pct ? n(o.viimeisin_kunto_pct) + " %" : "–"}</dd></dl></div>
      </div>
      ${v.liitanta ? `<div class="card">${guideHtml(v.liitanta, true)}</div>` : ""}
      <div class="card"><h2>Mittaukset</h2>${testTable(v.mittaukset)}</div>
      <div class="vaaravyohyke"><button class="btn danger" id="vDel">Poista auto ja sen mittaukset</button></div>`;
    $("#vEdit").onclick = () => (location.hash = `#/autot/${v.id}/muokkaa`);
    bindTestRows();
    $("#vDel").onclick = async () => {
      if (!(await kysy(`Poistetaanko ${v.nimi} ja kaikki sen mittaukset pysyvästi?`, { ok: "Poista auto", vaara: true }))) return;
      act(() => api(`/api/ajoneuvot/${id}`, { method: "DELETE" }), "Auto poistettu").then(() => (location.hash = "#/autot"));
    };
  },
};

function testTable(rows, withCar = false) {
  if (!rows.length) return `<div class="empty">Ei mittauksia.</div>`;
  return `<table class="t"><tr><th class="hide-m">Päivämäärä</th>${withCar ? "<th>Auto</th>" : ""}<th>Mittaus</th><th class="num">Kunto</th><th class="num hide-m">Kapasiteetti</th><th class="num hide-m">Jännite-ero</th><th class="hide-m">Tila</th></tr>
    ${rows.map(t => `<tr class="click" data-tid="${t.id}"><td class="hide-m">${date(t.aloitettu)}</td>${withCar ? `<td>${esc(t.ajoneuvo || "–")}<div class="small muted">${esc(t.rekisteri || "")}</div></td>` : ""}
      <td>${esc(tyyppi(t.tyyppi))}<div class="small muted show-m">${date(t.aloitettu)}</div>${t.osat > 1 ? `<div class="small muted">${t.osat} osaa</div>` : ""}${t.tila !== "valmis" ? `<div class="show-m">${tilaPill(t.tila)}</div>` : ""}</td>
      <td class="num">${t.kunto_pct ? `<span class="pill ${pillClass(t.kunto_luokka)}">${n(t.kunto_pct)} %</span>` : "–"}</td>
      <td class="num hide-m">${t.kapasiteetti_kwh ? n(t.kapasiteetti_kwh) + " kWh" : "–"}</td>
      <td class="num hide-m">${t.ero_mv != null ? n(t.ero_mv, 0) + " mV" : "–"}</td>
      <td class="hide-m">${tilaPill(t.tila)}</td></tr>`).join("")}</table>`;
}
function tilaPill(tila) {
  return { "valmis": '<span class="pill good">Valmis</span>', "käynnissä": '<span class="pill info">Käynnissä</span>', "kesken": '<span class="pill warn">Kesken</span>', "keskeytetty": '<span class="pill">Keskeytetty</span>' }[tila] || `<span class="pill">${esc(tila)}</span>`;
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
      <label class="btn primary" style="cursor:pointer">Avaa mittaustiedosto<input type="file" id="tOpen" ${ANDROID ? "" : `accept=".akveri"`} hidden></label></div>
      <div class="card" id="tList"></div>`;
    const { mittaukset } = await api("/api/mittaukset");
    $("#tList").innerHTML = testTable(mittaukset, true);
    bindTestRows();
    $("#tOpen").onchange = async e => {
      const f = e.target.files[0];
      if (!f) return;
      try {
        const r = await upload("/api/mittaukset/avaa", f);
        toast((r.uusi ? "Mittaus avattu tiedostosta" : "Mittaus oli jo ohjelmassa, ja se avattiin")
          + (r.laskettu_uudelleen ? `. Tulos laskettiin uudelleen versiolla ${r.laskettu_uudelleen}.` : ""));
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
    const bk = backLink("#/mittaukset", "Mittaukset");
    view.innerHTML = `${bk.html}<div class="head"><div><h1>${esc(tyyppi(t.tyyppi))}</h1>
      <div class="muted">${esc(v.nimi || "")} · ${date(t.aloitettu)}</div></div>
      <div class="row">${done ? `<a class="btn primary" href="/api/mittaukset/${id}/raportti.pdf" target="_blank">Avaa raportti (PDF)</a>` : ""}
        <a class="btn" href="/api/mittaukset/${id}/tiedosto.akveri">Mittaustiedosto</a>
        <a class="btn" href="/api/mittaukset/${id}/data.csv">Mittausdata (CSV)</a></div></div>
      ${r.virhe ? `<div class="notice bad">${esc(r.virhe)}</div>` : ""}
      ${t.tulos_odottaa ? `<div class="notice warn"><b>Mittaus on valmis.</b> Tulos ja raportti näytetään, kun raportti on rekisteröity akveri.fi-palveluun. Rekisteröinti tehdään automaattisesti, kun verkkoyhteys on käytettävissä.</div>` : ""}
      ${!done && !r.virhe && !t.tulos_odottaa && !["peruttu", "peru_odottaa", "tarkistus_odottaa", "tarkistettava"].includes((t.lupa || {}).tila) ? (t.tila === "kesken" ? `<div class="notice warn"><b>Mittaus on kesken.</b> Jatka sitä <a href="#/mittaus">Mittaus</a>-sivulta, kun sovitin on kytketty samaan autoon.</div>`
        : `<div class="notice warn">Mittaus on tilassa: ${esc(t.tila)}. Raporttia ei voi muodostaa.</div>`) : ""}
      ${done ? `
      <div class="grid g3">
        ${stat("Akun kunto", n(y.kunto_pct), "%", `${y.kunto_luokka || ""} · ${(y.kunto_lahde || "").toLowerCase()}`)}
        ${stat("Kapasiteetti", n(y.kapasiteetti_kwh), "kWh", y.epavarmuus_kwh ? `±${n(y.epavarmuus_kwh)} kWh · uutena ${n(r.viite.kwh)} kWh` : (y.kunto_lahde === "Akunhallinnan arvio" ? `Akunhallinnan arvio, ei mitattu · uutena ${n(r.viite.kwh)} kWh` : `Uutena ${n(r.viite.kwh)} kWh`))}
        ${stat("Kennoryhmien ero", r.kennot ? n(r.kennot.ero_mv, 0) : "–", r.kennot ? "mV" : "", r.kennot ? r.kennot.luokka : "Ei luettu")}
      </div>
      <div class="card" style="margin-top:16px"><h2>Yhteenveto</h2><p>${esc(y.teksti)}</p>
        ${y.tulkinta ? `<div class="notice"><b>Mitä tulos tarkoittaa:</b> ${esc(y.tulkinta)}</div>` : ""}
        <table class="t arviot"><tr><th>Arvio</th><th>Tulos</th><th class="hide-m">Luokka</th><th class="hide-m">Selite</th></tr>
        ${(r.arviot || []).map(a => `<tr><td>${esc(a.nimi)}</td><td><b>${esc(a.arvo)}</b>${a.luokka ? `<div class="show-m"><span class="pill ${pillClass(a.luokka)}">${esc(a.luokka)}</span></div>` : ""}</td><td class="hide-m">${a.luokka ? `<span class="pill ${pillClass(a.luokka)}">${esc(a.luokka)}</span>` : ""}</td><td class="small muted hide-m">${esc(a.kuvaus)}</td></tr>`).join("")}</table>
        ${(r.huomiot || []).length ? `<h3>Huomiot</h3><ul class="small">${r.huomiot.map(h => `<li>${esc(h)}</li>`).join("")}</ul>` : ""}
      </div>
      ${r.kennot ? `<div class="card"><h2>${esc(r.kennot_otsikko || "Kennoryhmät")}</h2>${cellSvg(r.kennot.jannitteet, r.kennot.poikkeama_raja_mv || 15)}${r.kennot.selite ? `<p class="muted small">${esc(r.kennot.selite)}</p>` : ""}</div>` : ""}` : ""}
      ${lupaKortti(t)}
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Tietojen eheys</h2><p class="small muted">Kaikki vastaanotetut viestit on tallennettu muuttamattomina. Tarkistus laskee raakadatan tarkisteen uudelleen ja vertaa sitä raporttiin merkittyyn.</p>
          <div class="small" style="word-break:break-all"><span class="muted">Tarkiste</span> ${esc(t.tarkiste || "–")}</div>
          <div class="row" style="margin-top:10px"><button class="btn sm" id="tVerify">Tarkista raakadata</button><a class="btn sm" href="/api/mittaukset/${id}/raakadata.csv.gz">Lataa raakadata</a><span id="tVerRes" class="small"></span></div></div>
        <div class="card"><h2>Tapahtumat</h2>${tapahtumalista(t.tapahtumat || [])}</div>
      </div>
      ${done ? `<div class="card" style="margin-top:16px"><h2>Tuloksen laskenta</h2>
        <p class="small muted">Tulos on laskettu AKVERIn versiolla ${esc(r.versio || "–")}${r.mittausversio && r.mittausversio !== r.versio ? ` (mittaus tallennettu versiolla ${esc(r.mittausversio)})` : ""}.
        Uudelleenlaskenta käyttää samaa tallennettua mittausdataa ja ohjelman nykyisiä arviointiperusteita. Mittausdata ei muutu.</p>
        <div class="row"><button class="btn sm" id="tRecalc">Laske uudelleen nykyisellä versiolla</button>
        ${t.tyyppi === "taysi" ? `<button class="btn sm" id="tSplit">Jaa kapasiteettimittaukseksi ja ajotestiksi</button>` : ""}
        <span id="tCalcRes" class="small"></span></div></div>` : ""}
      <div class="vaaravyohyke"><button class="btn danger" id="tDel">Poista mittaus</button></div>`;
    if ($("#tPoistaPalvelusta")) $("#tPoistaPalvelusta").onclick = async () => {
      if (!(await kysy("Poistetaanko raportin tiedot akveri.fi-palvelusta? Raporttia ei voi sen jälkeen tarkistaa QR-koodilla eikä tunnuksella. Poistoa ei voi perua.", { ok: "Poista tiedot", vaara: true }))) return;
      act(() => api(`/api/mittaukset/${id}/poista-palvelusta`, { method: "POST" }), "Raportin tiedot poistettu palvelusta.").then(() => this.renderOne(id));
    };
    if ($("#tRefund")) $("#tRefund").onclick = () => act(() => api(`/api/mittaukset/${id}/hyvityspyynto`, { method: "POST", body: { syy: $("#tRefundTxt").value } }),
      "Hyvityspyyntö lähetetty. Saat krediitin takaisin, kun pyyntö on käsitelty.").then(() => this.renderOne(id));
    const rc = $("#tRecalc");
    if (rc) rc.onclick = async () => {
      if (!(await kysy("Lasketaanko tulos uudelleen nykyisellä versiolla? Aiemmin tallennetut PDF-raportit eivät muutu, mutta uusi raportti muodostetaan uudella laskennalla.", { ok: "Laske uudelleen" }))) return;
      const res = await act(() => api(`/api/mittaukset/${id}/laske-uudelleen`, { method: "POST" }), "Tulos laskettu uudelleen");
      if (res) this.renderOne(id);
    };
    const sp = $("#tSplit");
    if (sp) sp.onclick = async () => {
      if (!(await kysy("Jaetaanko täysi akkutesti kahdeksi erilliseksi mittaukseksi (kapasiteettimittaus ja ajotesti)? Kumpikin saa oman raportin samasta mittausdatasta. Alkuperäinen täysi testi säilyy ennallaan.", { ok: "Jaa osiin" }))) return;
      const res = await act(() => api(`/api/mittaukset/${id}/jaa`, { method: "POST" }), "Täysi testi jaettu osiin");
      if (res) $("#tCalcRes").innerHTML = res.osat.map(o => o.id ? `<a href="#/mittaukset/${o.id}">${esc(o.nimi)} (nro ${o.id})</a>` : `<span class="muted">${esc(o.syy)}</span>`).join(" · ");
    };
    $("#tVerify").onclick = async () => {
      const res = await act(() => api(`/api/mittaukset/${id}/tarkista`));
      $("#tVerRes").innerHTML = `<span class="pill ${res.ok ? "good" : "bad"}">${esc(res.viesti)}</span> <span class="muted">${res.rivit ? n(res.rivit, 0) + " viestiä" : ""}</span>`;
    };
    $("#tDel").onclick = async () => {
      if (!(await kysy("Poistetaanko mittaus ja sen raakadata pysyvästi?", { ok: "Poista mittaus", vaara: true }))) return;
      act(() => api(`/api/mittaukset/${id}`, { method: "DELETE" }), "Mittaus poistettu").then(() => (location.hash = bk.target));
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
// KREDIITIT
// =====================================================================
// ---------- testilupa ja krediitit ----------
const LUPA_TILAT = {
  rekisteroity: ["good", "Rekisteröity", "Raportti on rekisteröity. Vastaanottaja voi tarkistaa sen QR-koodilla tai osoitteessa akveri.fi/v/"],
  varattu: ["warn", "Odottaa rekisteröintiä", "Raportti rekisteröidään tarkistettavaksi, kun mittaus on valmis ja verkkoyhteys on käytettävissä. Tarkistusosoite: akveri.fi/v/"],
  peruttu: ["bad", "Peruttu", "Testilupa peruttiin ja krediitit palautuivat. Mittauksesta ei tehdä raporttia."],
  peru_odottaa: ["warn", "Peruminen odottaa", "Lupa perutaan ja krediitit palautuvat, kun verkkoyhteys palaa."],
  tarkistus_odottaa: ["bad", "Tulosta ei voitu varmistaa", "Mitatut arvot eivät läpäisseet järkevyystarkistusta, joten raporttia ei tehdä. Krediitit palautetaan, kun verkkoyhteys on käytettävissä. Syy näkyy mittauksen tapahtumissa."],
  tarkistettava: ["bad", "Tulosta ei voitu varmistaa", "Mitatut arvot eivät läpäisseet järkevyystarkistusta, joten raporttia ei tehdä. Hyvityspyyntö lähetettiin automaattisesti, ja krediitit palautetaan, kun se on käsitelty. Syy näkyy mittauksen tapahtumissa."],
  osa: ["good", "Osa mittauksesta", "Tämä on osa täydestä akkutestistä. Tarkistettava raportti on koko mittauksen raportti: akveri.fi/v/"],
  tuotu: ["", "Avattu tiedostosta", "Mittaus on avattu mittaustiedostosta. Raportti rekisteröidään sillä laitteella, jolla mittaus tehtiin. Tarkistusosoite: akveri.fi/v/"],
  ei_rekisteroitavissa: ["bad", "Rekisteröinti hylätty", "AKVERI-palvelu ei hyväksynyt raportin rekisteröintiä. Syy näkyy tapahtumissa. Ota tarvittaessa yhteyttä asiakaspalveluun."],
  esimerkki: ["", "Esittelytila", "Esittelytilan mittaus. Raporttiin tulee ESIMERKKI-leima, eikä sitä voi tarkistaa akveri.fi:ssä."],
  vanha: ["", "Ei tarkistettavissa", "Mittaus on tehty ennen raporttien tarkistuspalvelua (versio 2.0), joten raporttia ei voi tarkistaa akveri.fi:ssä."],
  poistettu: ["", "Poistettu palvelusta", "Raportin tiedot on poistettu akveri.fi-palvelusta, joten raporttia ei voi enää tarkistaa. Mittaus ja raportti ovat edelleen tällä laitteella."],
};
function lupaKortti(t) {
  const l = t.lupa || {};
  const [cls, otsikko, teksti] = LUPA_TILAT[l.tila] || LUPA_TILAT.vanha;
  const linkki = l.tunnus && ["rekisteroity", "varattu", "osa", "tuotu"].includes(l.tila) ? `<a href="https://akveri.fi/v/${esc(l.tunnus)}" target="_blank" rel="noopener">${esc(l.tunnus)}</a>` : "";
  return `<div class="card" style="margin-top:16px"><h2>Raportin tarkistus ${cls ? `<span class="pill ${cls}">${otsikko}</span>` : `<span class="pill">${otsikko}</span>`}</h2>
    <p class="small">${esc(teksti)}${linkki}</p>
    ${["tarkistus_odottaa", "tarkistettava"].includes(l.tila) ? (() => {
      const e = [...(t.tapahtumat || [])].reverse().find(x => /^Tulosta ei voitu varmistaa: /.test(x.teksti || ""));
      return e ? `<div class="notice bad small">${esc(e.teksti.replace(/^Tulosta ei voitu varmistaa: /, ""))}</div>` : "";
    })() : ""}
    ${l.testi ? `<div class="notice warn">Testimittaus: tehty testitilillä, ei kuluttanut krediittiä. Raporttiin tulee TESTIMITTAUS-leima, eikä sitä voi käyttää todistuksena.</div>` : ""}
    ${l.tunnus ? `<p class="small muted">Raportin tunnus ${esc(l.tunnus)}</p>` : ""}
    ${l.hyvitettavissa ? `<h3>Pyydä hyvitystä</h3><p class="small muted">Jos mittaus keskeytyi AKVERIsta johtuvasta syystä (esimerkiksi ohjelma pysähtyi tai yhteys katkesi ohjelman virheen vuoksi), kerro mitä tapahtui. Mittauksen tapahtumaloki lähetetään pyynnön mukana.</p>
      <textarea id="tRefundTxt" rows="3" style="width:100%" maxlength="1500" placeholder="Mitä tapahtui?"></textarea>
      <div class="row" style="margin-top:8px"><button class="btn sm primary" id="tRefund">Lähetä hyvityspyyntö</button></div>` : ""}
    ${l.tila === "rekisteroity" ? `<h3>Tietosuoja</h3><p class="small muted">Voit poistaa raportin tiedot akveri.fi-palvelusta. Tarkistussivu näyttää sen jälkeen, että tiedot on poistettu, eikä raporttia voi enää tarkistaa. Mittaus ja raportti säilyvät tällä laitteella. Poistoa ei voi perua.</p>
      <div class="vaaravyohyke"><button class="btn danger" id="tPoistaPalvelusta">Poista raportti palvelusta</button></div>` : ""}</div>`;
}

views.krediitit = {
  async render() {
    view.innerHTML = `<div class="head"><div><h1>Krediitit</h1><div class="muted">Mittaukset maksetaan krediiteillä. Kunkin mittauksen hinta näkyy ennen aloitusta.</div></div></div><div id="kBody"><div class="card">Haetaan…</div></div>`;
    let d;
    try { d = await api("/api/krediitit"); }
    catch (e) { $("#kBody").innerHTML = `<div class="notice warn"><b>Krediittitilannetta ei saatu.</b> ${esc(e.message)}</div>`; return; }
    const ostot = ANDROID && window.AkveriAndroid.osta;
    const kpl = x => `${x} ${x === 1 ? "krediitti" : "krediittiä"}`;
    const hyvitys = d.hyvitysaikaMin || 60;
    $("#kBody").innerHTML = `
      <div class="card ksaldo">
        <div class="lbl">Krediittejä käytettävissä</div>
        <div class="ksaldo-arvo">${esc(d.saldo)}</div>
        ${d.avoimetLuvat ? `<div class="small muted">${d.avoimetLuvat} mittausta kesken</div>` : ""}
      </div>
      ${d.versiot && d.versiot.paivitys_pakollinen ? `<div class="notice bad kvali"><b>Päivitä AKVERI.</b> Versio ${esc(d.versiot.nykyinen)} on liian vanha. Mittauksia voi aloittaa vasta, kun AKVERI on päivitetty vähintään versioon ${esc(d.versiot.vahimmaisversio)}.${ANDROID ? ` <a href="https://play.google.com/store/apps/details?id=fi.akveri.app" target="_blank" rel="noopener">Avaa Google Play</a>` : ""}</div>`
        : d.versiot && d.versiot.paivitys_saatavilla ? `<div class="notice kvali">Uusi versio ${esc(d.versiot.uusin)} on saatavilla.${ANDROID ? ` <a href="https://play.google.com/store/apps/details?id=fi.akveri.app" target="_blank" rel="noopener">Avaa Google Play</a>` : ""}</div>` : ""}
      ${d.testitili ? `<div class="notice warn kvali"><b>Testitili.</b> Mittaukset eivät kuluta krediittejä. Raportteihin tulee TESTIMITTAUS-leima, ja tarkistussivu näyttää ne testimittauksina.</div>` : ""}
      <div class="card kvali"><h2>Osta krediittejä</h2>
        ${ostot ? `<p class="muted">Maksu tehdään Google Playssa. Krediitit tulevat tilillesi heti, kun Google on vahvistanut maksun.</p>
          <div class="ktuotteet" id="kTuotteet">${(d.tuotteet || []).map(p => `<button class="btn ktuote" data-tuote="${esc(p.tuote)}"><span class="ktuote-n">${p.krediitit}</span><span>${p.krediitit === 1 ? "krediitti" : "krediittiä"}</span></button>`).join("")}</div>
          <p class="small muted" id="kHinnat">Hinnat näkyvät Google Playn ostoikkunassa.</p>`
        : `<p>Krediitit ostetaan AKVERIn Android-sovelluksessa Google Playn kautta. Tällä laitteella käytetään tilin krediittejä.</p>`}
        <div id="kViesti"></div>
      </div>
      ${d.hinnat ? `<div class="card kvali"><h2>Mittausten hinnat</h2>
        <table class="t khinnat">${["pikatarkastus", "kapasiteetti", "taysi", "ajotesti", "pika_ajo", "kuormitus", "pikalataus", "itsepurkaus"].filter(k => d.hinnat[k]).map(k => `<tr><td>${esc(tyyppi(k))}</td><td class="num"><b>${kpl(d.hinnat[k])}</b></td></tr>`).join("")}</table>
        <p class="small muted">Krediitit veloitetaan, kun mittaus aloitetaan. Jos mittaus keskeytyy ${hyvitys} minuutin kuluessa alusta, krediitit palautuvat automaattisesti. Myöhemmin keskeytyneestä mittauksesta voit lähettää hyvityspyynnön mittauksen sivulta.</p></div>` : ""}
      <div class="card kvali tietosuoja"><h2>Tili ja tietosuoja</h2>
        <dl class="kv"><dt>Tilitunnus</dt><dd><code>${esc(d.tili)}</code></dd></dl>
        <p class="small muted">Tilitunnus yksilöi tämän laitteen krediitit. Kerro se asiakaspalvelulle, jos kysyt ostosta tai hyvityksestä. Tilin salaista avainta ei näytetä.</p>
        <details class="kvali"><summary>Mitä tietoja tilistä tallennetaan</summary>
          <p class="small muted">akveri.fi-palvelussa on tästä tilistä vain satunnainen tilitunnus, krediittien kirjanpito, ostot ja rekisteröityjen raporttien tiedot. Mittaukset ja autot ovat vain tällä laitteella.</p>
          <p class="small muted">Krediittien kirjanpito ja ostot säilytetään kirjanpitolain edellyttämän ajan ilman muita tunnisteita. Anonyymi mittausaineisto ei sisällä tunnisteita, joten se ei muutu.</p>
          <p class="small"><a href="https://akveri.fi${({ en: "/en/privacy", sv: "/sv/dataskydd" })[typeof KIELI === "string" ? KIELI : "fi"] || "/tietosuoja"}" target="_blank" rel="noopener">Tietosuojaseloste</a></p>
        </details>
        <div class="ktoiminnot"><a class="btn" href="/api/tietosuoja/akveri-tietoni.zip">Lataa tietoni</a></div>
        <div class="vaaravyohyke">
          <p class="small muted"><b>Tilin poisto:</b> tili ja sen jäljellä olevat krediitit poistuvat, eikä niitä voi palauttaa. Voit poistaa samalla rekisteröityjen raporttien tiedot.</p>
          <button class="btn danger" id="kPoistaTili">Poista tili</button>
        </div></div>`;
    $("#kPoistaTili").onclick = async () => {
      if (!(await kysy(`Poistetaanko tili? Tilillä on ${d.saldo} krediittiä, jotka poistuvat tilin mukana eikä niitä voi palauttaa. Poistoa ei voi perua.`, { ok: "Poista tili", vaara: true }))) return;
      const raportit = await kysy("Poistetaanko myös rekisteröityjen raporttien tiedot tarkistuspalvelusta? Valitse Jätä raportit, jos ne jäävät tarkistettaviksi esimerkiksi auton ostajalle.", { ok: "Poista myös raportit", peru: "Jätä raportit", vaara: true });
      try {
        const r = await api("/api/tietosuoja/poista-tili", { method: "POST", body: { vahvista: true, raportit } });
        toast((r.raportteja ? `Tili poistettu. Raportteja poistettu palvelusta: ${r.raportteja}.` : "Tili poistettu.") + " Sovellus luo uuden tyhjän tilin, kun käytät krediittejä seuraavan kerran.");
        views.krediitit.render();
      } catch (e) { toast(e.message, true); }
    };
    $$("[data-tuote]").forEach(b => (b.onclick = () => {
      $("#kViesti").innerHTML = "";
      try { window.AkveriAndroid.osta(b.dataset.tuote, d.tili); } catch (e) { toast("Ostoa ei voitu aloittaa.", true); }
    }));
  },
};

// Android-sovellus kutsuu tätä, kun Google Play on käsitellyt oston (myös sovelluksen käynnistyessä keskeneräisille ostoille).
window.akveriOsto = async function (tuote, ostotunnus) {
  try {
    const r = await api("/api/krediitit/osto", { method: "POST", body: { tuote, ostotunnus } });
    if (r.odottaa) { toast("Maksu odottaa vahvistusta. Krediitit tulevat tilillesi, kun Google on vahvistanut maksun."); return; }
    try { window.AkveriAndroid.kuluta(ostotunnus); } catch (e) { /* kulutetaan seuraavalla käynnistyksellä */ }
    if (r.hyvitetty) toast(`${r.hyvitetty} ${r.hyvitetty === 1 ? "krediitti" : "krediittiä"} lisätty. Saldo ${r.saldo}.`);
    if (current === views.krediitit) views.krediitit.render();
  } catch (e) {
    toast("Oston kirjaus epäonnistui: " + e.message + " Osto on tallessa Google Playssa, ja se kirjataan uudelleen, kun avaat sovelluksen.", true);
  }
};
window.akveriOstoVirhe = function (viesti) { if (viesti) toast(viesti, true); };

// =====================================================================
// ASETUKSET
// =====================================================================
views.asetukset = {
  async render() {
    const [s, E, info] = await Promise.all([api("/api/asetukset"), esittelySallittu(), api("/api/tietoja")]);
    // Käyttötapa: aiemmissa asennuksissa valintaa ei ole, jolloin yritys, jos yrityksen nimi on täytetty
    const kaytto = s.kaytto || (s.yritys_nimi ? "yritys" : "henkilo");
    const valinta = (name, arvo, opts) => `<select name="${name}">${opts.map(([k, t]) => `<option value="${k}" ${arvo === k ? "selected" : ""}>${t}</option>`).join("")}</select>`;
    view.innerHTML = `<div class="head"><div><h1>Asetukset</h1></div>
      <button class="btn primary" id="sSave">Tallenna</button></div>
    <div id="sForm">
      <div class="card"><h2>Kieli</h2>
        <label class="f"><span>Ohjelman ja raporttien kieli</span><select id="sKieli">${[["fi", "Suomi"], ["en", "English"], ["sv", "Svenska"]].map(([k, t]) => `<option value="${k}" ${KIELI === k ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      </div>
      <div class="card"><h2>Raporttien tiedot</h2>
        <div class="valinta" role="radiogroup">
          <label class="check"><input type="radio" name="kaytto" value="henkilo" ${kaytto === "henkilo" ? "checked" : ""}><span><b>Yksityinen käyttö</b><span class="small muted">Raportissa on AKVERIn tunnus ja nimesi mittaajana.</span></span></label>
          <label class="check"><input type="radio" name="kaytto" value="yritys" ${kaytto === "yritys" ? "checked" : ""}><span><b>Yritys</b><span class="small muted">Yrityksen nimi, yhteystiedot ja logo raportin yläreunassa.</span></span></label>
        </div>
        <div id="sYritys" class="grid g2" style="margin-top:14px" ${kaytto === "yritys" ? "" : "hidden"}>
            <label class="f"><span>Yrityksen nimi</span><input name="yritys_nimi" maxlength="80" value="${esc(s.yritys_nimi)}"></label>
            <label class="f"><span>Y-tunnus</span><input name="yritys_ytunnus" maxlength="20" value="${esc(s.yritys_ytunnus)}"></label>
            <label class="f"><span>Osoite</span><input name="yritys_osoite" maxlength="120" value="${esc(s.yritys_osoite)}" placeholder="Katuosoite, postinumero ja toimipaikka"></label>
            <label class="f"><span>Puhelin</span><input name="yritys_puhelin" maxlength="40" value="${esc(s.yritys_puhelin)}"></label>
            <label class="f"><span>Sähköposti</span><input name="yritys_sahkoposti" maxlength="80" value="${esc(s.yritys_sahkoposti)}"></label>
            <label class="f"><span>Verkkosivu</span><input name="yritys_www" maxlength="80" value="${esc(s.yritys_www)}"></label>
        </div>
        <div class="grid g2" style="margin-top:14px">
          <label class="f"><span id="sNimiOtsikko">${kaytto === "yritys" ? "Mittauksen suorittaja" : "Nimesi"}</span><input name="mittaaja" maxlength="80" value="${esc(s.mittaaja)}" placeholder="Etunimi Sukunimi"></label>
        </div>
        <div id="sLogoRivi" class="row" ${kaytto === "yritys" ? "" : "hidden"}><label class="btn sm" style="cursor:pointer">Valitse logo<input type="file" id="sLogo" accept="image/png,image/jpeg" hidden></label>
          <span class="small muted">${s.logo ? "Logo on käytössä raporteissa." : "Logoa ei ole valittu. Käytä PNG- tai JPEG-kuvaa."}</span>
          ${s.logo ? `<button class="btn sm" id="sLogoDel" type="button">Poista logo</button>` : ""}</div>
      </div>
    </div>
    <div class="card"><h2>Varmuuskopio</h2>
      <p class="small muted">Ohjelma tekee varmuuskopion automaattisesti kerran viikossa. Tallenna kopio välillä myös muualle.</p>
      <div class="row"><a class="btn" href="/api/yllapito/varmuuskopio" id="bNow">Tee varmuuskopio nyt</a>
        <label class="btn" style="cursor:pointer">Palauta varmuuskopio<input type="file" id="rFile" accept=".zip" hidden></label></div>
      <div id="rRes" style="margin-top:12px"></div>
      <div id="bList" style="margin-top:12px"></div></div>
    <div class="card"><h2>Tietoja</h2>
      <dl class="kv"><dt>Versio</dt><dd>${esc(info.nimi)} ${esc(info.versio)}</dd>
        <dt>Päivitykset</dt><dd>${ANDROID ? "Google Play päivittää AKVERIn automaattisesti." : "Asenna uusi versio vanhan päälle. Tiedot säilyvät."}</dd></dl>
      <details class="small muted" style="margin-top:10px"><summary>Tavaramerkit ja aineistot</summary>
        <p>Viestimäärittelyt perustuvat Tesla-omistajien yhteisön ylläpitämään avoimeen aineistoon. Muiden merkkien kyselyt perustuvat avoimiin aineistoihin (OBD-PIDs-for-HKMC-EVs, evDash, Open Vehicle Monitoring System, Battery-Emulator ja py-nissan-leaf-obd-ble). Tesla, Model 3, Model Y, Model S, Model X ja Cybertruck ovat Tesla, Inc:n tavaramerkkejä; Hyundai, Ioniq ja Kona Hyundai Motor Companyn; Kia, EV6, e-Niro ja e-Soul Kia Corporationin; Nissan ja Leaf Nissan Motor Co:n; Volkswagen, ID.3, ID.4 ja ID.5 Volkswagen AG:n; Škoda ja Enyaq Škoda Auto a.s:n; Audi ja Q4 e-tron Audi AG:n; Cupra ja Born SEAT S.A:n sekä MG ja ZS SAIC Motor Corporationin tavaramerkkejä.</p></details>
      <p class="small muted" style="margin-top:8px">AKVERI ei ole minkään autonvalmistajan tekemä eikä hyväksymä.</p></div>
    ${E ? `<div class="card kehittaja"><h2>Kehittäjän työkalut</h2>
      <p class="small muted">Näkyy vain testitileillä.</p>
      <div class="row" style="margin-top:14px"><h3 style="margin:0">Laaduntarkistus</h3><span class="spacer"></span><button class="btn" id="qRun" type="button">Aja tarkistus</button></div>
      <div id="qRes"></div>
      <div class="row" style="margin-top:14px"><h3 style="margin:0">Tapahtumaloki</h3><span class="spacer"></span><button class="btn sm" id="lLoad" type="button">Näytä loki</button></div>
      <pre id="lBox" class="log" hidden></pre>
    </div>` : ""}`;
    const paivitaKaytto = () => {
      const yritys = $('input[name="kaytto"]:checked').value === "yritys";
      $("#sYritys").hidden = !yritys;
      $("#sLogoRivi").hidden = !yritys;
      $("#sNimiOtsikko").textContent = yritys ? "Mittauksen suorittaja" : "Nimesi";
    };
    $$('input[name="kaytto"]').forEach(r => (r.onchange = paivitaKaytto));
    $("#sSave").onclick = () => act(() => api("/api/asetukset", { method: "POST", body: form($("#sForm")) }), "Asetukset tallennettu").then(() => this.render());
    $("#sKieli").onchange = async e => {
      try { await api("/api/kieli", { method: "POST", body: { kieli: e.target.value } }); } catch (x) { toast(x.message, true); return; }
      asetaKieli(e.target.value); location.reload();
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
    this.varmuuskopiot();
    if (E) this.kehittaja();
  },
  varmuuskopiot() {
    $("#rFile").onchange = async e => {
      const f = e.target.files[0];
      if (!f) return;
      const box = $("#rRes");
      try {
        const r = await upload("/api/yllapito/palauta/tarkista", f);
        box.innerHTML = `<div class="notice warn">Varmuuskopio ${date(r.aika)}, versio ${esc(r.versio)}: ${r.autoja} autoa ja ${r.mittauksia} mittausta. Palautus korvaa nykyiset tiedot. Nykyiset tiedot siirretään ensin talteen.</div>
          <button class="btn primary" id="rGo">Palauta varmuuskopio</button>`;
        $("#rGo").onclick = async () => {
          if (!(await kysy("Palautetaanko varmuuskopio? Ohjelma käynnistyy sen jälkeen uudelleen.", { ok: "Palauta" }))) return;
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
      const b = $("#bList");
      if (!b) return;
      b.innerHTML = r.varmuuskopiot.length ? `<table class="t"><tr><th>Varmuuskopio</th><th class="num">Koko</th><th></th></tr>
        ${r.varmuuskopiot.map(x => `<tr><td>${date(x.aika)}</td><td class="num">${sizeTxt(x.koko)}</td><td class="num"><a class="btn sm" href="/api/yllapito/varmuuskopiot/${encodeURIComponent(x.nimi)}">Lataa</a></td></tr>`).join("")}</table>`
        : `<div class="small muted">Varmuuskopioita ei ole vielä tehty.</div>`;
    };
    list();
    $("#bNow").onclick = () => { toast("Varmuuskopio tehdään…"); setTimeout(list, 2500); };
  },
  kehittaja() {
    $("#qRun").onclick = async () => {
      const b = $("#qRun");
      b.disabled = true;
      b.textContent = "Tarkistetaan…";
      $("#qRes").innerHTML = `<div class="bar" style="margin-top:12px"><i class="indet"></i></div>`;
      try {
        const r = await api("/api/yllapito/tarkistus");
        $("#qRes").innerHTML = `<div class="notice ${STATUS[r.tulos][0]}" style="margin-top:12px"><b>${r.tulos === "ok" ? "Kaikki tarkistukset kunnossa." : (r.tulos === "varoitus" ? "Tarkistus valmis, huomioitavaa löytyi." : "Tarkistuksessa löytyi virheitä.")}</b> ${date(r.aika)}</div>
          <table class="t"><tr><th>Tarkistus</th><th>Tulos</th><th class="hide-m">Tieto</th></tr>
          ${r.tarkistukset.map(c => `<tr><td>${esc(c.nimi)}<div class="small muted show-m">${esc(c.tieto)}</div></td><td><span class="pill ${STATUS[c.tila][0]}">${STATUS[c.tila][1]}</span></td><td class="small muted hide-m">${esc(c.tieto)}</td></tr>`).join("")}</table>`;
      } catch (e) {
        $("#qRes").innerHTML = `<div class="notice bad" style="margin-top:12px">${esc(e.message)}</div>`;
      }
      b.disabled = false;
      b.textContent = "Aja tarkistus uudelleen";
    };
    $("#lLoad").onclick = async () => {
      const r = await api("/api/yllapito/loki");
      const b = $("#lBox");
      b.hidden = false;
      b.textContent = r.loki || "Loki on tyhjä.";
      b.scrollTop = b.scrollHeight;
    };
  },
};
const STATUS = { ok: ["good", "Kunnossa"], varoitus: ["warn", "Huomioitava"], virhe: ["bad", "Virhe"], info: ["", "Tieto"] };
// Vanha Ylläpito-osoite avaa Asetukset
views.yllapito = views.asetukset;

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

// ---------- sulkeminen ----------
async function quitApp() {
  let body = {};
  if (S && S.mittaus) {
    if (!(await kysy("Mittaus on käynnissä. Ohjelman sulkeminen keskeyttää mittauksen. Suljetaanko silti?\n\nVoit myös vain sulkea ikkunan: mittaus jatkuu taustalla, ja saat sen näkyviin avaamalla ohjelman uudelleen.", { ok: "Sulje AKVERI", vaara: true }))) return;
    body = { vahvistettu: true };
  } else if (!(await kysy("Suljetaanko AKVERI?", { ok: "Sulje" }))) return;
  try { await api("/api/sulje", { method: "POST", body }); } catch (e) { toast(e.message, true); return; }
  clearInterval(pollTimer);
  document.body.innerHTML = `<div style="padding:40px;font-family:Inter,system-ui;color:var(--ink)"><h1>AKVERI on suljettu</h1><p class="muted">Voit sulkea tämän ikkunan.</p></div>`;
  setTimeout(() => {
    if (ANDROID) window.AkveriAndroid.close();
    else if (window.pywebview && window.pywebview.api) window.pywebview.api.sulje();
    else window.close();
  }, 400);
}
$("#quit").onclick = quitApp;

// Windowsin sovellusikkunassa tiedostot avataan oletusohjelmassa ja tallennetaan valittuun paikkaan
document.addEventListener("click", e => {
  const a = e.target.closest && e.target.closest('a[href^="/api/"]');
  if (!a || !window.pywebview || !window.pywebview.api) return;
  e.preventDefault();
  const href = a.getAttribute("href");
  const open = a.target === "_blank";
  window.pywebview.api[open ? "avaa" : "tallenna"](href).then(r => {
    if (r && r.ok && r.polku) toast("Tallennettu: " + r.polku);
    else if (r && !r.ok && !r.peruttu) toast(r.virhe || "Tiedoston käsittely epäonnistui", true);
  });
});
$("#quitM").onclick = e => { e.preventDefault(); document.body.classList.remove("menu-open"); quitApp(); };

// ---------- käynnistys ----------
// Kieli: ensimmäisellä käynnistyksellä asiakas valitsee kielen. Valinta tallennetaan ohjelmaan (koskee myös raportteja).
async function kaynnista() {
  let k = null;
  try { k = (await api("/api/kieli")).kieli; } catch (e) { /* ohjelma vastaa pian */ }
  if (k && k !== KIELI) { asetaKieli(k); location.reload(); return; }
  if (!k) { naytaKielivalinta(); return; }
  await alustaKieli();
  if (ANDROID && window.AkveriAndroid.asetaKieli) { try { window.AkveriAndroid.asetaKieli(KIELI); } catch (e) { /* vanha sovellus */ } }
  route();
  poll();
  pollTimer = setInterval(poll, 1000);
}
function naytaKielivalinta() {
  view.innerHTML = `<div class="card kielivalinta" style="max-width:460px;margin:40px auto;text-align:center">
    <h1>AKVERI</h1><p class="muted">Valitse kieli · Choose your language · Välj språk</p>
    <div class="row" style="justify-content:center;gap:10px;flex-wrap:wrap">
      <button class="btn primary" data-kieli="fi">Suomi</button><button class="btn primary" data-kieli="en">English</button><button class="btn primary" data-kieli="sv">Svenska</button>
    </div><p class="small muted" style="margin-top:14px">Kielen voi vaihtaa myöhemmin asetuksista. · You can change it later in Settings. · Du kan ändra det senare i inställningarna.</p></div>`;
  $$("[data-kieli]").forEach(b => (b.onclick = async () => {
    try { await api("/api/kieli", { method: "POST", body: { kieli: b.dataset.kieli } }); } catch (e) { toast(e.message, true); return; }
    asetaKieli(b.dataset.kieli); location.reload();
  }));
}
kaynnista();
// Google Play: kesken jääneet ostot kirjataan, kun käyttöliittymä on valmis
if (ANDROID && window.AkveriAndroid.palautaOstot) setTimeout(() => { try { window.AkveriAndroid.palautaOstot(); } catch (e) { /* ei Google Playta */ } }, 1500);
