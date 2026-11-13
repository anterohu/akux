// hallinta.js — omistajan hallinta (akveri.fi/hallinta) ja sivuston julkiset tiedot.
//
// Turvallisuus (sama periaate kuin vuoropiste.fi:n hallinnassa):
//   - Tunnus luodaan kerran alkutunnuksella (AKVERI_ALKUTUNNUS), jonka Hallintatyökalu asettaa palvelimelle.
//     Verkosta ei voi luoda uutta tunnusta, kun tunnus on jo olemassa.
//   - Kirjautuminen vaatii salasanan ja kaksivaiheisen tunnistuksen koodin. Käytettyä koodia ei voi käyttää uudelleen.
//   - Istunto on httpOnly-evästeessä (SameSite=Strict), ja jokainen muutospyyntö vaatii lisäksi oman otsakkeen.
//   - Hallinnan voi rajata IP-osoitteisiin (HALLINTA_SALLITUT_IP). Hallintaan ei ole linkkiä julkisilta sivuilta.
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { promisify } = require('util');
const scrypt = promisify(crypto.scrypt);
const totp = require('./totp');
const ipraja = require('./ipraja');
const { json, Virhe, lueJson, ipOsoite, puhdista, yksiRivi, vakioaikainenVertailu } = require('./apu');
const { normalisoiTunnus, muotoileTunnus, OLETUSTUOTTEET, OLETUS_VAHIMMAISVERSIO, VERSIO_RE, vertaaVersioita } = require('./sovellus');

const ISTUNTO_MS = 8 * 3600000;
const EVASTE = 'akveri_hallinta';
const SAHKOPOSTI = /^[^\s@<>()",;:]+@[^\s@<>()",;:]+\.[^\s@<>()",;:]{2,}$/;
const LATAUS_NIMI = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(exe|zip|apk|aab|msi)$/;

async function tiivistaSalasana(s) {
  const suola = crypto.randomBytes(16);
  const h = await scrypt(String(s), suola, 64, { N: 16384, r: 8, p: 1 });
  return ['scrypt', 16384, 8, 1, suola.toString('base64url'), h.toString('base64url')].join('$');
}
async function tarkistaSalasana(s, tallennettu) {
  const o = String(tallennettu || '').split('$');
  if (o.length !== 6 || o[0] !== 'scrypt') return false;
  const odotettu = Buffer.from(o[5], 'base64url');
  const saatu = await scrypt(String(s), Buffer.from(o[4], 'base64url'), odotettu.length, { N: Number(o[1]), r: Number(o[2]), p: Number(o[3]) });
  return crypto.timingSafeEqual(saatu, odotettu);
}
function salasanaKelpaa(s) {
  const t = String(s || '');
  if (t.length < 12) return 'Salasanan pitää olla vähintään 12 merkkiä.';
  if (t.length > 200) return 'Salasana on liian pitkä.';
  return '';
}

function luoHallinta({ varasto, sovellus, env = process.env, nyt = () => Date.now(), rajoitin }) {
  const istunnot = new Map();
  const sallitut = ipraja.jasenna(env.HALLINTA_SALLITUT_IP || '');
  const omistaja = () => varasto.get('omistaja');
  const asetukset = () => varasto.get('asetukset');
  // Omat lataukset (esim. Windows-versio). Tuotannossa tietokansion ulkopuolella (AKVERI_LATAUKSET), koska tiedostot ovat suuria.
  const latauskansio = path.resolve(env.AKVERI_LATAUKSET || path.join(varasto.kansio, 'lataukset'));
  let alustus = null; // { salaisuus, salasanaTiiviste, vanhenee } — kesken oleva käyttöönotto

  function sallittu(req) { return ipraja.sallittu(sallitut, ipOsoite(req, env)); }
  function evasteet(req) {
    const ulos = {};
    for (const osa of String(req.headers.cookie || '').split(';')) { const i = osa.indexOf('='); if (i > 0) ulos[osa.slice(0, i).trim()] = osa.slice(i + 1).trim(); }
    return ulos;
  }
  function istunto(req) {
    const t = evasteet(req)[EVASTE];
    const i = t && istunnot.get(t);
    if (!i || i.vanhenee < nyt()) { if (t) istunnot.delete(t); return null; }
    return i;
  }
  function asetaEvaste(res, arvo, ikaS) {
    const turvallinen = String(env.JULKINEN_OSOITE || '').startsWith('https://') ? '; Secure' : '';
    res.setHeader('Set-Cookie', `${EVASTE}=${arvo}; HttpOnly; SameSite=Strict; Path=/${turvallinen}; Max-Age=${ikaS}`);
  }

  // ------------------------------------------------------------ käyttöönotto ja kirjautuminen
  async function aloitaAlustus(req, body) {
    if (omistaja().salasana) throw new Virhe('Hallinnan tunnus on jo luotu.', 409);
    const alkutunnus = String(env.AKVERI_ALKUTUNNUS || '');
    if (alkutunnus.length < 32) throw new Virhe('Alkutunnusta ei ole asetettu palvelimelle. Aja AKVERIn julkaisu Hallintatyökalussa.', 503);
    if (rajoitin.kayta('alustus:' + ipOsoite(req, env), 10, 3600000)) throw new Virhe('Liian monta yritystä. Yritä tunnin kuluttua uudelleen.', 429);
    if (!vakioaikainenVertailu(String(body.alkutunnus || ''), alkutunnus)) throw new Virhe('Alkutunnus ei täsmää.', 403);
    const vika = salasanaKelpaa(body.salasana);
    if (vika) throw new Virhe(vika);
    const salaisuus = totp.luoSalaisuus();
    alustus = { salaisuus, salasanaTiiviste: await tiivistaSalasana(body.salasana), vanhenee: nyt() + 15 * 60000 };
    return { salaisuus, otpauth: totp.otpauthUrl({ salaisuus, tili: 'hallinta', myontaja: 'AKVERI' }) };
  }
  function vahvistaAlustus(req, body) {
    if (omistaja().salasana) throw new Virhe('Hallinnan tunnus on jo luotu.', 409);
    if (!alustus || alustus.vanhenee < nyt()) throw new Virhe('Käyttöönotto on vanhentunut. Aloita alusta.', 409);
    if (!vakioaikainenVertailu(String(body.alkutunnus || ''), String(env.AKVERI_ALKUTUNNUS || ''))) throw new Virhe('Alkutunnus ei täsmää.', 403);
    const askel = totp.tarkistaKoodi(alustus.salaisuus, body.koodi, nyt());
    if (askel === null) throw new Virhe('Koodi ei täsmää. Tarkista puhelimen kellonaika ja yritä uudelleen.');
    Object.assign(omistaja(), { salasana: alustus.salasanaTiiviste, totp: alustus.salaisuus, viimeisinAskel: askel, luotu: new Date(nyt()).toISOString() });
    varasto.tallenna('omistaja');
    alustus = null;
    return { ok: true };
  }
  async function kirjaudu(req, res, body) {
    const ip = ipOsoite(req, env);
    if (rajoitin.kayta('kirjaudu:' + ip, 10, 15 * 60000) || rajoitin.kayta('kirjaudu:kaikki', 60, 3600000)) throw new Virhe('Liian monta kirjautumisyritystä. Yritä myöhemmin uudelleen.', 429);
    const o = omistaja();
    if (!o.salasana) throw new Virhe('Hallinnan tunnusta ei ole vielä luotu.', 409);
    const salasanaOk = await tarkistaSalasana(body.salasana, o.salasana);
    const askel = totp.tarkistaKoodi(o.totp, body.koodi, nyt());
    if (!salasanaOk || askel === null || askel <= (o.viimeisinAskel || 0)) {
      await new Promise(r => setTimeout(r, 400));
      throw new Virhe('Salasana tai vahvistuskoodi on väärin.', 401);
    }
    o.viimeisinAskel = askel; o.viimeksiKirjautunut = new Date(nyt()).toISOString();
    varasto.tallenna('omistaja');
    const t = crypto.randomBytes(32).toString('base64url');
    istunnot.set(t, { vanhenee: nyt() + ISTUNTO_MS });
    asetaEvaste(res, t, ISTUNTO_MS / 1000);
    return { ok: true };
  }
  async function vaihdaSalasana(body) {
    const o = omistaja();
    if (!(await tarkistaSalasana(body.nykyinen, o.salasana))) throw new Virhe('Nykyinen salasana on väärin.', 403);
    const vika = salasanaKelpaa(body.uusi);
    if (vika) throw new Virhe(vika);
    o.salasana = await tiivistaSalasana(body.uusi);
    varasto.tallenna('omistaja');
    istunnot.clear();
    return { ok: true, viesti: 'Salasana vaihdettu. Kirjaudu uudelleen.' };
  }

  // ------------------------------------------------------------ näkymät
  function yhteenveto() {
    const testit = Object.values(varasto.get('testit'));
    const ostot = Object.values(varasto.get('ostot'));
    const kk = nyt() - 30 * 86400000;
    let krediititYhteensa = 0;
    for (const id of Object.keys(varasto.get('tilit'))) krediititYhteensa += varasto.saldo(id);
    let varmuus = '';
    try { varmuus = fs.readdirSync(varasto.varmuuskopiokansio).filter(n => /^\d{4}/.test(n) && !n.endsWith('.kesken')).sort().pop() || ''; } catch (e) { /* ei vielä */ }
    return {
      tilit: Object.keys(varasto.get('tilit')).length,
      krediititTileilla: krediititYhteensa,
      testit30: testit.filter(t => Date.parse(t.varattu) > kk && !t.testi).length,
      testimittaukset30: testit.filter(t => Date.parse(t.varattu) > kk && t.testi).length,
      testitilit: Object.values(varasto.get('tilit')).filter(t => t.testitili).map(t => t.id),
      raportit30: testit.filter(t => t.rekisteroity && Date.parse(t.rekisteroity) > kk).length,
      avoimetLuvat: testit.filter(t => t.tila === 'varattu').length,
      hyvityspyynnot: testit.filter(t => t.hyvityspyynto && t.hyvityspyynto.tila === 'avoin').length,
      ostot30: ostot.filter(o => Date.parse(o.aika) > kk && !o.testiosto).length,
      testiostot30: ostot.filter(o => Date.parse(o.aika) > kk && o.testiosto).length,
      uudetViestit: Object.values(varasto.get('viestit')).filter(v => !v.kasitelty).length,
      kirjanpitoEhja: varasto.kirjanpitoEhja, kirjanpitoRiveja: varasto.kirjanpitoRiveja,
      googleKaytossa: sovellus.google.kaytossa, googleVirhe: sovellus.google.virhe || '',
      viimeisinVarmuuskopio: varmuus, versio: env.AKVERI_VERSIO || ''
    };
  }
  function tiliRivi(t) { return { id: t.id, luotu: t.luotu, suljettu: !!t.suljettu, testitili: !!t.testitili, saldo: varasto.saldo(t.id), muistiinpano: t.muistiinpano || '' }; }
  function tilit(kysely) {
    const haku = String(kysely.get('haku') || '').toUpperCase().replace(/[\s-]/g, '');
    return Object.values(varasto.get('tilit')).filter(t => !haku || t.id.includes(haku) || String(t.muistiinpano || '').toUpperCase().includes(haku))
      .sort((a, b) => String(b.luotu).localeCompare(String(a.luotu))).slice(0, 200).map(tiliRivi);
  }
  function haeTili(id) { const t = varasto.get('tilit')[String(id).toUpperCase()]; if (!t) throw new Virhe('Tiliä ei löydy.', 404); return t; }
  function testiRivi(t) { return { ...t, tunnusNaytto: muotoileTunnus(t.tunnus), allekirjoitus: undefined }; }
  function tili(id) {
    const t = haeTili(id);
    return { tili: tiliRivi(t), kirjanpito: varasto.kirjanpito({ tili: t.id, raja: 300 }), testit: Object.values(varasto.get('testit')).filter(x => x.tili === t.id).sort((a, b) => b.varattu.localeCompare(a.varattu)).slice(0, 200).map(testiRivi) };
  }
  function muutaKrediitteja(id, body) {
    const t = haeTili(id);
    const muutos = Number(body.muutos);
    if (!Number.isInteger(muutos) || muutos === 0 || Math.abs(muutos) > 1000) throw new Virhe('Anna muutos kokonaislukuna (esim. 5 tai -2).');
    const selite = yksiRivi(puhdista(body.selite, 300));
    if (!selite) throw new Virhe('Kirjoita muutokselle syy. Se näkyy kirjanpidossa.');
    varasto.kirjaa({ tili: t.id, muutos, syy: 'ylläpito', tekija: 'omistaja', selite });
    return tiliRivi(t);
  }
  function tilinTila(id, body) {
    const t = haeTili(id);
    if (body.suljettu !== undefined) t.suljettu = body.suljettu === true;
    if (body.testitili !== undefined) t.testitili = body.testitili === true;
    if (body.muistiinpano !== undefined) t.muistiinpano = yksiRivi(puhdista(body.muistiinpano, 200));
    varasto.tallenna('tilit');
    return tiliRivi(t);
  }
  function testit(kysely) {
    const haku = normalisoiTunnus(kysely.get('haku') || '');
    const suodatin = String(kysely.get('suodatin') || '');
    return Object.values(varasto.get('testit')).filter(t => (!haku || t.tunnus.includes(haku) || t.tili.includes(haku))
      && (!suodatin || (suodatin === 'hyvityspyynnot' ? (t.hyvityspyynto && t.hyvityspyynto.tila === 'avoin') : t.tila === suodatin)))
      .sort((a, b) => b.varattu.localeCompare(a.varattu)).slice(0, 300).map(testiRivi);
  }
  function haeTesti(tunnus) { const t = varasto.get('testit')[normalisoiTunnus(tunnus)]; if (!t) throw new Virhe('Testiä ei löydy.', 404); return t; }
  // Hyvitys: krediitti palautuu ja lupa merkitään perutuksi (ei rekisteröityä raporttia) tai mitätöidyksi (rekisteröity raportti).
  function hyvita(tunnus, body) {
    const t = haeTesti(tunnus);
    const selite = yksiRivi(puhdista(body.selite, 300));
    if (!selite) throw new Virhe('Kirjoita hyvityksen syy.');
    if (t.hyvitetty) throw new Virhe('Testi on jo hyvitetty.', 409);
    if (t.testi) throw new Virhe('Testitilin mittaus ei kuluttanut krediittiä, joten sitä ei hyvitetä.', 409);
    if (t.tila === 'peruttu') throw new Virhe('Lupa on jo peruttu ja krediitti palautettu.', 409);
    if (t.tila === 'valmis' && body.mitatoi !== true) throw new Virhe('Raportti on rekisteröity. Hyvitys mitätöi raportin: vahvista mitätöinti.', 409);
    if (t.tila === 'valmis' || t.tila === 'mitatoity') { t.tila = 'mitatoity'; t.mitatoinninSyy = t.mitatoinninSyy || 'Mittaus on hyvitetty asiakkaalle.'; }
    else t.tila = 'peruttu';
    t.hyvitetty = new Date(nyt()).toISOString();
    if (t.hyvityspyynto) t.hyvityspyynto.tila = 'hyvitetty';
    varasto.tallenna('testit');
    varasto.kirjaa({ tili: t.tili, muutos: 1, syy: 'hyvitys', viite: t.tunnus, tekija: 'omistaja', selite });
    return testiRivi(t);
  }
  function mitatoi(tunnus, body) {
    const t = haeTesti(tunnus);
    const syy = yksiRivi(puhdista(body.syy, 300));
    if (!syy) throw new Virhe('Kirjoita mitätöinnin syy. Se näkyy tarkistussivulla.');
    if (t.tila === 'mitatoity') throw new Virhe('Raportti on jo mitätöity.', 409);
    t.tila = 'mitatoity'; t.mitatoinninSyy = syy; t.mitatoitu = new Date(nyt()).toISOString();
    varasto.tallenna('testit');
    return testiRivi(t);
  }
  function hylkaaHyvityspyynto(tunnus, body) {
    const t = haeTesti(tunnus);
    if (!t.hyvityspyynto || t.hyvityspyynto.tila !== 'avoin') throw new Virhe('Avointa hyvityspyyntöä ei ole.', 409);
    t.hyvityspyynto.tila = 'hylätty'; t.hyvityspyynto.vastaus = yksiRivi(puhdista(body.selite, 300));
    varasto.tallenna('testit');
    return testiRivi(t);
  }
  function ostot() {
    return Object.values(varasto.get('ostot')).sort((a, b) => String(b.aika).localeCompare(String(a.aika))).slice(0, 500);
  }
  function viestit() { return Object.entries(varasto.get('viestit')).map(([id, v]) => ({ id, ...v })).sort((a, b) => b.aika.localeCompare(a.aika)).slice(0, 500); }

  // Hallinnassa muokattavat asetukset
  function julkisetAsetukset() {
    const a = asetukset();
    return {
      yhteystiedot: a.yhteystiedot || {}, playLinkki: a.playLinkki || '', hinnasto: a.hinnasto || '',
      tuotteet: Array.isArray(a.tuotteet) && a.tuotteet.length ? a.tuotteet : OLETUSTUOTTEET,
      hyvitysaikaMin: Number(a.hyvitysaikaMin) > 0 ? Number(a.hyvitysaikaMin) : 60,
      vahimmaisversio: VERSIO_RE.test(String(a.vahimmaisversio)) ? a.vahimmaisversio : OLETUS_VAHIMMAISVERSIO, uusinVersio: a.uusinVersio || '',
      asiakirjat: { ehdot: a.asiakirjat && a.asiakirjat.ehdot || null, tietosuoja: a.asiakirjat && a.asiakirjat.tietosuoja || null }
    };
  }
  function tallennaAsetukset(body) {
    const a = asetukset();
    if (body.yhteystiedot) {
      const y = body.yhteystiedot;
      const uusi = {};
      for (const [k, max] of [['nimi', 120], ['yTunnus', 20], ['osoite', 200], ['sahkoposti', 120], ['puhelin', 40]]) uusi[k] = yksiRivi(puhdista(y[k], max));
      if (uusi.yTunnus && !/^\d{7}-\d$/.test(uusi.yTunnus)) throw new Virhe('Y-tunnus on muotoa 1234567-8.');
      if (uusi.sahkoposti && !SAHKOPOSTI.test(uusi.sahkoposti)) throw new Virhe('Tarkista sähköpostiosoite.');
      a.yhteystiedot = uusi;
    }
    if (body.playLinkki !== undefined) {
      const l = puhdista(body.playLinkki, 300);
      if (l && !/^https:\/\/play\.google\.com\/store\/apps\/details\?id=[A-Za-z0-9._]+(&[A-Za-z0-9=._-]*)?$/.test(l)) throw new Virhe('Anna Google Play -linkki muodossa https://play.google.com/store/apps/details?id=…');
      a.playLinkki = l;
    }
    if (body.hinnasto !== undefined) a.hinnasto = puhdista(body.hinnasto, 2000);
    if (body.hyvitysaikaMin !== undefined) {
      const m = Number(body.hyvitysaikaMin);
      if (!Number.isInteger(m) || m < 10 || m > 24 * 60) throw new Virhe('Automaattisen perumisen aika on 10–1440 minuuttia.');
      a.hyvitysaikaMin = m;
    }
    for (const k of ['vahimmaisversio', 'uusinVersio']) {
      if (body[k] === undefined) continue;
      const v = puhdista(body[k], 20);
      if (k === 'uusinVersio' && !v) { a.uusinVersio = ''; continue; }
      if (!VERSIO_RE.test(v)) throw new Virhe('Versio on muotoa 2.0.0.');
      a[k] = v;
    }
    if (a.uusinVersio && vertaaVersioita(a.uusinVersio, a.vahimmaisversio || OLETUS_VAHIMMAISVERSIO) < 0) throw new Virhe('Uusin versio ei voi olla pienempi kuin vähimmäisversio.');
    if (body.tuotteet !== undefined) {
      if (!Array.isArray(body.tuotteet) || !body.tuotteet.length || body.tuotteet.length > 10) throw new Virhe('Anna 1–10 tuotetta.');
      const lista = body.tuotteet.map(t => ({ tuote: puhdista(t.tuote, 100), krediitit: Number(t.krediitit) }));
      for (const t of lista) {
        if (!/^[a-z0-9][a-z0-9._]{0,98}$/.test(t.tuote)) throw new Virhe('Tuotetunnus on Play Consolen tunnus, esim. akveri_testi_5 (pienet kirjaimet, numerot, _ ja .).');
        if (!Number.isInteger(t.krediitit) || t.krediitit < 1 || t.krediitit > 1000) throw new Virhe('Krediittimäärä on 1–1000.');
      }
      if (new Set(lista.map(t => t.tuote)).size !== lista.length) throw new Virhe('Sama tuotetunnus on listassa kahdesti.');
      a.tuotteet = lista;
    }
    if (body.asiakirja) {
      const tyyppi = body.asiakirja.tyyppi;
      if (!['ehdot', 'tietosuoja'].includes(tyyppi)) throw new Virhe('Tuntematon asiakirja.');
      a.asiakirjat = a.asiakirjat || {};
      const teksti = puhdista(body.asiakirja.teksti, 60000);
      a.asiakirjat[tyyppi] = teksti ? { teksti, versio: new Date(nyt()).toISOString() } : null;
    }
    varasto.tallenna('asetukset');
    return julkisetAsetukset();
  }

  function lataukset() {
    try {
      return fs.readdirSync(latauskansio).filter(n => LATAUS_NIMI.test(n)).map(n => {
        const s = fs.statSync(path.join(latauskansio, n));
        return { nimi: n, koko: s.size, muokattu: s.mtime.toISOString() };
      }).sort((a, b) => b.muokattu.localeCompare(a.muokattu));
    } catch (e) { return []; }
  }
  function lahetaLataus(res, nimi) {
    if (!LATAUS_NIMI.test(nimi)) throw new Virhe('Tiedostoa ei löydy.', 404);
    const polku = path.join(latauskansio, nimi);
    let s;
    try { s = fs.lstatSync(polku); } catch (e) { throw new Virhe('Tiedostoa ei löydy.', 404); }
    if (!s.isFile()) throw new Virhe('Tiedostoa ei löydy.', 404);
    res.writeHead(200, { 'Content-Type': 'application/octet-stream', 'Content-Length': s.size, 'Content-Disposition': `attachment; filename="${nimi}"`, 'Cache-Control': 'no-store' });
    fs.createReadStream(polku).pipe(res);
  }

  // ------------------------------------------------------------ julkinen sivuston rajapinta
  async function viesti(req, body) {
    if (puhdista(body.www, 50)) return { ok: true }; // piilokenttä: botit täyttävät sen
    const nimi = yksiRivi(puhdista(body.nimi, 120));
    const sahkoposti = yksiRivi(puhdista(body.sahkoposti, 160));
    const teksti = puhdista(body.viesti, 3000);
    const aihe = yksiRivi(puhdista(body.aihe, 60));
    const testitunnus = normalisoiTunnus(body.testitunnus || '').slice(0, 12);
    if (!nimi || !teksti) throw new Virhe('Täytä nimi ja viesti.');
    if (!SAHKOPOSTI.test(sahkoposti)) throw new Virhe('Tarkista sähköpostiosoite.');
    if (body.suostumus !== true) throw new Virhe('Hyväksy tietojen käyttö viestiin vastaamiseen.');
    if (rajoitin.kayta('viesti:' + ipOsoite(req, env), 5, 3600000)) throw new Virhe('Liian monta viestiä. Yritä myöhemmin uudelleen.', 429);
    const v = varasto.get('viestit');
    if (Object.keys(v).length >= 5000) throw new Virhe('Viestien vastaanotto on hetkellisesti täynnä. Lähetä viesti sähköpostilla.', 503);
    v[crypto.randomBytes(8).toString('hex')] = { aika: new Date(nyt()).toISOString(), nimi, sahkoposti, aihe, testitunnus, viesti: teksti, kasitelty: false };
    varasto.tallenna('viestit');
    return { ok: true };
  }

  async function kasitteleJulkinen(req, res, polku) {
    try {
      if (polku === '/api/sivusto/tiedot' && req.method === 'GET') {
        const a = julkisetAsetukset();
        return json(res, 200, { yhteystiedot: a.yhteystiedot, playLinkki: a.playLinkki, hinnasto: a.hinnasto, hyvitysaikaMin: a.hyvitysaikaMin });
      }
      const am = /^\/api\/sivusto\/asiakirja\/(ehdot|tietosuoja)$/.exec(polku);
      if (am && req.method === 'GET') return json(res, 200, julkisetAsetukset().asiakirjat[am[1]] || {});
      if (polku === '/api/sivusto/viesti' && req.method === 'POST') return json(res, 200, await viesti(req, await lueJson(req, 16 * 1024)));
      throw new Virhe('Tuntematon pyyntö.', 404);
    } catch (e) {
      if (e instanceof Virhe) return json(res, e.status, { virhe: e.message });
      console.error('[sivusto]', e); return json(res, 500, { virhe: 'Palvelinvirhe.' });
    }
  }

  async function kasittele(req, res, polku, kysely) {
    try {
      if (!sallittu(req)) throw new Virhe('Sivua ei löydy.', 404);
      const p = polku.slice('/api/hallinta'.length);
      // Muutospyynnöissä vaaditaan oma otsake: toinen sivusto ei voi lähettää sitä selaimen kautta.
      if (req.method !== 'GET' && req.headers['x-akveri-hallinta'] !== '1') throw new Virhe('Pyyntö hylättiin.', 403);
      if (p === '/tila' && req.method === 'GET') return json(res, 200, { alustettu: !!omistaja().salasana, kirjautunut: !!istunto(req), alkutunnusAsetettu: String(env.AKVERI_ALKUTUNNUS || '').length >= 32 });
      if (p === '/alusta' && req.method === 'POST') return json(res, 200, await aloitaAlustus(req, await lueJson(req)));
      if (p === '/alusta/vahvista' && req.method === 'POST') return json(res, 200, vahvistaAlustus(req, await lueJson(req)));
      if (p === '/kirjaudu' && req.method === 'POST') return json(res, 200, await kirjaudu(req, res, await lueJson(req)));
      if (p === '/ulos' && req.method === 'POST') { const t = evasteet(req)[EVASTE]; if (t) istunnot.delete(t); asetaEvaste(res, '', 0); return json(res, 200, { ok: true }); }
      if (!istunto(req)) throw new Virhe('Kirjaudu sisään.', 401);
      const body = req.method === 'GET' ? {} : await lueJson(req, 128 * 1024);
      if (p === '/salasana' && req.method === 'POST') return json(res, 200, await vaihdaSalasana(body));
      if (p === '/yhteenveto' && req.method === 'GET') return json(res, 200, yhteenveto());
      if (p === '/tilit' && req.method === 'GET') return json(res, 200, { tilit: tilit(kysely) });
      let m = /^\/tilit\/(T[0-9A-Z]{12})(\/krediitit|\/tila)?$/.exec(p);
      if (m && !m[2] && req.method === 'GET') return json(res, 200, tili(m[1]));
      if (m && m[2] === '/krediitit' && req.method === 'POST') return json(res, 200, muutaKrediitteja(m[1], body));
      if (m && m[2] === '/tila' && req.method === 'POST') return json(res, 200, tilinTila(m[1], body));
      if (p === '/testit' && req.method === 'GET') return json(res, 200, { testit: testit(kysely) });
      m = /^\/testit\/([A-Za-z0-9-]{10,20})\/(hyvita|mitatoi|hylkaa-pyynto)$/.exec(p);
      if (m && req.method === 'POST') return json(res, 200, m[2] === 'hyvita' ? hyvita(m[1], body) : m[2] === 'mitatoi' ? mitatoi(m[1], body) : hylkaaHyvityspyynto(m[1], body));
      if (p === '/ostot' && req.method === 'GET') return json(res, 200, { ostot: ostot() });
      if (p === '/viestit' && req.method === 'GET') return json(res, 200, { viestit: viestit() });
      m = /^\/viestit\/([a-f0-9]{16})$/.exec(p);
      if (m && req.method === 'POST') { const v = varasto.get('viestit')[m[1]]; if (!v) throw new Virhe('Viestiä ei löydy.', 404); v.kasitelty = body.kasitelty !== false; varasto.tallenna('viestit'); return json(res, 200, { ok: true }); }
      if (m && req.method === 'DELETE') { delete varasto.get('viestit')[m[1]]; varasto.tallenna('viestit'); return json(res, 200, { ok: true }); }
      if (p === '/asetukset' && req.method === 'GET') return json(res, 200, julkisetAsetukset());
      if (p === '/asetukset' && req.method === 'PUT') return json(res, 200, tallennaAsetukset(body));
      if (p === '/lataukset' && req.method === 'GET') return json(res, 200, { lataukset: lataukset() });
      m = /^\/lataukset\/([^/]+)$/.exec(p);
      if (m && req.method === 'GET') return lahetaLataus(res, decodeURIComponent(m[1]));
      if (p === '/varmuuskopio' && req.method === 'POST') return json(res, 200, { nimi: varasto.varmuuskopioi(true) });
      if (p === '/perutut-ostot' && req.method === 'POST') return json(res, 200, { vahennetty: await sovellus.tarkistaPerutut() });
      if (p === '/kirjanpito' && req.method === 'GET') return json(res, 200, { rivit: varasto.kirjanpito({ raja: 500 }), ehja: varasto.kirjanpitoEhja });
      throw new Virhe('Tuntematon pyyntö.', 404);
    } catch (e) {
      if (e instanceof Virhe) return json(res, e.status, { virhe: e.message });
      console.error('[hallinta]', e); return json(res, 500, { virhe: 'Palvelinvirhe: ' + (e && e.message || '') });
    }
  }

  return { kasittele, kasitteleJulkinen, sallittu, julkisetAsetukset, latauskansio };
}

module.exports = { luoHallinta, tiivistaSalasana, tarkistaSalasana };
