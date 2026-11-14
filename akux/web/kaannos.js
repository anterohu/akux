"use strict";
/* AKVERI – käyttöliittymän kieli (suomi, englanti, ruotsi).
   Käyttöliittymä kirjoitetaan suomeksi. Kun kieli on englanti tai ruotsi, jokainen näkyvä teksti (myös palvelimen viestit)
   käännetään samalla sanastolla kuin raportit (akux/data/kielet/*.json). {} sanastossa = vaihtuva osa, esim. luku.
   Käännös tehdään sivulle lisätyille tekstisolmuille ja title-, placeholder- ja aria-label-määreille. */
const KIELI = (() => { try { return localStorage.getItem("akveri-kieli") || "fi"; } catch (e) { return "fi"; } })();
const LOKAALI = { fi: "fi-FI", en: "en-GB", sv: "sv-FI" }[KIELI] || "fi-FI";
let SANASTO = {}, KUVIOT = [];

function _rakennaKuviot() {
  KUVIOT = Object.keys(SANASTO).filter(k => k.includes("{}")).map(k => {
    const osat = k.split("{}").map(s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return [new RegExp("^" + osat.join("(.+?)") + "$", "s"), SANASTO[k]];
  }).sort((a, b) => b[0].source.length - a[0].source.length);
}
const _VALIMUISTI = new Map();
// Englanniksi desimaalipilkku → piste (vain numeroiden välissä, luettelot "1, 2" säilyvät).
const _desimaalit = s => (KIELI === "en" ? s.replace(/(?<=\d),(?=\d)/g, ".") : s);
function tr(teksti) {
  if (KIELI === "fi" || typeof teksti !== "string") return teksti;
  const ydin = teksti.trim();
  if (!ydin) return teksti;
  if (!/[A-Za-zÅÄÖåäö]/.test(ydin)) return _desimaalit(teksti);
  if (_VALIMUISTI.has(teksti)) return _VALIMUISTI.get(teksti);
  const tulos = _desimaalit(_tr(teksti, ydin));
  if (_VALIMUISTI.size > 5000) _VALIMUISTI.clear();
  _VALIMUISTI.set(teksti, tulos);
  return tulos;
}
const _MERKIT = { "Hyundain": "Hyundai", "Kian": "Kia", "Nissanin": "Nissan", "Volkswagenin": "Volkswagen", "Škodan": "Škoda", "Audin": "Audi", "Cupran": "Cupra", "MG:n": "MG" };
const _MERKKI_RX = new RegExp("(^|[^A-Za-zÅÄÖåäöŠš])(" + Object.keys(_MERKIT).join("|") + ")(?= )");
const _LAUSE_RX = /(?<=[.!?])\s+(?=[A-ZÅÄÖ0-9(])/;
function _tr(teksti, ydin) {
  const m = _MERKKI_RX.exec(teksti);
  if (m) {
    const merkki = _MERKIT[m[2]];
    return _tr2(teksti.replace(new RegExp(_MERKKI_RX.source, "g"), "$1Teslan"), null).replace(/Tesla/g, merkki);
  }
  return _tr2(teksti, ydin);
}
function _tr2(teksti, ydin) {
  ydin = ydin || teksti.trim();
  const alku = teksti.slice(0, teksti.length - teksti.trimStart().length), loppu = teksti.slice(teksti.trimEnd().length);
  if (Object.prototype.hasOwnProperty.call(SANASTO, ydin)) return alku + SANASTO[ydin] + loppu;
  for (const [rx, kohde] of KUVIOT) {
    const m = rx.exec(ydin);
    if (m && !m.slice(1).some(g => _LAUSE_RX.test(g))) {
      const osat = kohde.split("{}");
      let tulos = osat[0];
      m.slice(1).forEach((g, i) => { tulos += _tr2(g, null) + (osat[i + 1] ?? ""); });
      return alku + tulos + loppu;
    }
  }
  const lauseet = ydin.split(_LAUSE_RX);
  if (lauseet.length > 1) return alku + lauseet.map(x => _tr2(x, null)).join(" ") + loppu;
  return teksti;
}
const _MAAREET = ["title", "placeholder", "aria-label"];
function kaannaSolmu(juuri) {
  if (KIELI === "fi" || !juuri) return;
  if (juuri.nodeType === 3) { const u = tr(juuri.nodeValue); if (u !== juuri.nodeValue) juuri.nodeValue = u; return; }
  if (juuri.nodeType !== 1 || juuri.tagName === "SCRIPT" || juuri.tagName === "STYLE" || juuri.tagName === "TEXTAREA") return;
  const kaynti = document.createTreeWalker(juuri, NodeFilter.SHOW_TEXT, { acceptNode: n => (n.parentNode && /^(SCRIPT|STYLE|TEXTAREA)$/.test(n.parentNode.tagName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) });
  const solmut = []; while (kaynti.nextNode()) solmut.push(kaynti.currentNode);
  for (const s of solmut) { const u = tr(s.nodeValue); if (u !== s.nodeValue) s.nodeValue = u; }
  const el = [juuri, ...juuri.querySelectorAll("[title],[placeholder],[aria-label],input[type=button],input[type=submit]")];
  for (const e of el) {
    for (const a of _MAAREET) if (e.hasAttribute && e.hasAttribute(a)) { const v = e.getAttribute(a), u = tr(v); if (u !== v) e.setAttribute(a, u); }
    if (e.tagName === "INPUT" && (e.type === "button" || e.type === "submit")) { const u = tr(e.value); if (u !== e.value) e.value = u; }
  }
}
async function alustaKieli() {
  document.documentElement.lang = KIELI;
  if (KIELI === "fi") return;
  try { const r = await fetch("/api/kieli/sanasto?kieli=" + KIELI); if (r.ok) SANASTO = await r.json(); } catch (e) { /* suomeksi */ }
  _rakennaKuviot();
  kaannaSolmu(document.body);
  document.title = tr(document.title);
  new MutationObserver(muutokset => {
    for (const m of muutokset) {
      if (m.type === "characterData") kaannaSolmu(m.target);
      else if (m.type === "attributes") kaannaSolmu(m.target.nodeType === 1 ? m.target : null);
      else m.addedNodes.forEach(kaannaSolmu);
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: _MAAREET });
  // Selaimen omat ikkunat
  const _alert = window.alert.bind(window), _confirm = window.confirm.bind(window), _prompt = window.prompt.bind(window);
  window.alert = m => _alert(tr(String(m)));
  window.confirm = m => _confirm(tr(String(m)));
  window.prompt = (m, d) => _prompt(tr(String(m)), d);
}
function asetaKieli(kieli) {
  try { localStorage.setItem("akveri-kieli", kieli); } catch (e) { /* */ }
}
