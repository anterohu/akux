// akveri/asetukset.js — AKVERIn asetukset Hallintatyökalussa.
// Tiedot tallennetaan Hallintatyökalun salattuun tietotiedostoon (data/tiedot.json, kohta akveri), mutta koodi on
// AKVERIn omassa kansiossa, jotta AKVERIn osa päivitetään erillään Vuoropisteestä.
'use strict';
const store = require('../store');
const salaus = require('../crypto');
const { lue, kirjoita, HOST_RE } = store;
const muidenVaraukset = (dataDir) => require('../palvelinyhteys').muidenVaraukset(dataDir, 'akveri');

// ---- AKVERI (akveri.fi) samalla palvelimella, erillään Vuoropisteestä ----
// Oma järjestelmäkäyttäjä, kansiot, portti, asetustiedosto ja Caddy-osoite. Salaisuudet (hallinnan alkutunnus ja Google Play
// -palvelutilin avain) salataan levyllä eikä niitä palauteta käyttöliittymään.
// Palvelin: oletuksena sama kuin Vuoropisteellä (oletuspalvelin). erillinenPalvelin=true: AKVERI omalla palvelimellaan (samalla SSH-avaimella).
const AKVERI_OLETUS = { domain: 'akveri.fi', portti: 3090, paketti: 'fi.akveri.app', sallitutIp: '', julkaistu: false, erillinenPalvelin: false, palvelinHost: '', palvelinPortti: 22, palvelinKayttaja: 'root', palvelinSudo: false };
const AKVERI_SALAISET = ['alkutunnus', 'googleTili'];
function haeAkveri(dataDir) {
  const v = { ...AKVERI_OLETUS, ...(lue(dataDir).akveri || {}) };
  const ulos = { ...v };
  for (const k of AKVERI_SALAISET) { ulos[k + 'Asetettu'] = !!v[k]; delete ulos[k]; }
  if (v.googleTili) { try { ulos.googleTiliSahkoposti = JSON.parse(salaus.pura(v.googleTili, dataDir)).client_email || ''; } catch (e) { ulos.googleTiliSahkoposti = ''; } }
  return ulos;
}
function haeAkveriSalaisena(dataDir) {
  const v = { ...AKVERI_OLETUS, ...(lue(dataDir).akveri || {}) };
  for (const k of AKVERI_SALAISET) v[k] = v[k] ? salaus.pura(v[k], dataDir) : '';
  return v;
}
function tallennaAkveri(dataDir, kentat) {
  const k = kentat || {};
  const data = lue(dataDir);
  const v = { ...AKVERI_OLETUS, ...(data.akveri || {}) };
  if (k.domain !== undefined) {
    const d = String(k.domain).trim().toLowerCase();
    if (!/^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/.test(d)) throw new Error('AKVERIn verkkotunnus ei kelpaa. Anna se muodossa akveri.fi, ilman https://-alkua.');
    for (const muu of muidenVaraukset(dataDir).domainit) {
      if (d === muu || d.endsWith('.' + muu)) throw new Error(`AKVERIn osoite ei voi olla verkkotunnuksen ${muu} alla, koska se on toisen palvelun käytössä.`);
    }
    v.domain = d;
  }
  if (k.portti !== undefined) {
    const n = Number(k.portti);
    if (!Number.isInteger(n) || n < 1024 || n > 65535) throw new Error('AKVERIn portin pitää olla luku väliltä 1024–65535.');
    const muut = muidenVaraukset(dataDir);
    if (muut.portit.includes(n)) throw new Error('Portti on jo toisen palvelun käytössä. Valitse toinen portti (oletus 3090).');
    const vali = muut.porttivalit.find(([a, b]) => n >= a && n <= b);
    if (vali) throw new Error(`Portit ${vali[0]}–${vali[1]} on varattu toisen palvelun asiakkaille. Valitse toinen portti (oletus 3090).`);
    v.portti = n;
  }
  if (k.paketti !== undefined) {
    const pk = String(k.paketti).trim();
    if (!/^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/.test(pk)) throw new Error('Sovelluksen paketin nimi on muotoa fi.akveri.app.');
    v.paketti = pk;
  }
  if (k.sallitutIp !== undefined) {
    const t = String(k.sallitutIp).trim().slice(0, 500);
    if (t && !/^[0-9a-fA-F.:/, ]+$/.test(t)) throw new Error('Anna IP-osoitteet pilkulla erotettuina (esim. 203.0.113.5, 198.51.100.0/24).');
    v.sallitutIp = t;
  }
  if (k.julkaistu !== undefined) v.julkaistu = k.julkaistu === true;
  if (k.erillinenPalvelin !== undefined) v.erillinenPalvelin = k.erillinenPalvelin === true;
  if (k.palvelinHost !== undefined) {
    const h = String(k.palvelinHost).trim();
    if (h && (!HOST_RE.test(h) || /^-/.test(h))) throw new Error('AKVERIn palvelimen osoite ei kelpaa. Anna verkkonimi tai IP-osoite ilman https://-alkua.');
    v.palvelinHost = h;
  }
  if (k.palvelinPortti !== undefined) { const n = Number(k.palvelinPortti); if (!Number.isInteger(n) || n < 1 || n > 65535) throw new Error('SSH-portin pitää olla luku väliltä 1–65535.'); v.palvelinPortti = n; }
  if (k.palvelinKayttaja !== undefined) { const u = String(k.palvelinKayttaja).trim(); if (!/^[a-z_][a-z0-9_-]{0,31}$/i.test(u)) throw new Error('SSH-käyttäjätunnus ei kelpaa.'); v.palvelinKayttaja = u; }
  if (k.palvelinSudo !== undefined) v.palvelinSudo = k.palvelinSudo === true;
  if (v.erillinenPalvelin && !v.palvelinHost) throw new Error('Anna AKVERIn oman palvelimen osoite tai valitse sama palvelin kuin Vuoropisteellä.');
  if (k.alkutunnus !== undefined && String(k.alkutunnus).trim()) {
    const s = String(k.alkutunnus).trim();
    if (!/^[A-Za-z0-9_-]{32,128}$/.test(s)) throw new Error('Alkutunnus ei kelpaa.');
    v.alkutunnus = salaus.salaa(s, dataDir);
  }
  if (k.googleTili !== undefined && String(k.googleTili).trim()) {
    let j;
    try { j = JSON.parse(String(k.googleTili)); } catch (e) { throw new Error('Palvelutilin avain ei ole kelvollista JSONia. Lataa Google Cloudista ladattu .json-tiedosto sellaisenaan.'); }
    if (!j || j.type !== 'service_account' || !/^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$/.test(String(j.client_email || '')) || !/-----BEGIN PRIVATE KEY-----/.test(String(j.private_key || ''))) {
      throw new Error('Tiedosto ei ole Google Cloudin palvelutilin avain (type service_account, client_email ja private_key puuttuvat).');
    }
    v.googleTili = salaus.salaa(JSON.stringify({ type: j.type, project_id: j.project_id, private_key_id: j.private_key_id, private_key: j.private_key, client_email: j.client_email, token_uri: j.token_uri || 'https://oauth2.googleapis.com/token' }), dataDir);
  }
  if (k.poistaSalaisuus && AKVERI_SALAISET.includes(k.poistaSalaisuus)) v[k.poistaSalaisuus] = '';
  data.akveri = v;
  kirjoita(dataDir, data);
  return haeAkveri(dataDir);
}

module.exports = { haeAkveri, haeAkveriSalaisena, tallennaAkveri, AKVERI_OLETUS };
