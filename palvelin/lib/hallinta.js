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
const { osoiteOsasta } = require('./posti');
const kayttajat = require('./kayttajat');
const KIELTEN_NIMET = { fi: 'suomi', en: 'englanti', sv: 'ruotsi' };
const { normalisoiTunnus, muotoileTunnus, MITTAUSTYYPIT, OLETUSHINTA, OLETUSTUOTTEET, OLETUS_VAHIMMAISVERSIO, VERSIO_RE, vertaaVersioita } = require('./sovellus');

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

const HUOLTOTILAT = ['pois', 'sivusto', 'kaikki'];
const HUOLTOVIESTI = 'Palvelu on tilapäisesti huollossa. Palaamme pian.';

function luoHallinta({ varasto, sovellus, env = process.env, nyt = () => Date.now(), rajoitin, postitus }) {
  const istunnot = new Map();
  const sallitut = ipraja.jasenna(env.HALLINTA_SALLITUT_IP || '');
  const asetukset = () => varasto.get('asetukset');
  // Omat lataukset (esim. Windows-versio). Tuotannossa tietokansion ulkopuolella (AKVERI_LATAUKSET), koska tiedostot ovat suuria.
  const latauskansio = path.resolve(env.AKVERI_LATAUKSET || path.join(varasto.kansio, 'lataukset'));
  let alustus = null; // { salaisuus, salasanaTiiviste, nimi, sahkoposti, vanhenee } — kesken oleva käyttöönotto (alkutunnus tai kutsu)

  function sallittu(req) { return ipraja.sallittu(sallitut, ipOsoite(req, env)); }
  function evasteet(req) {
    const ulos = {};
    for (const osa of String(req.headers.cookie || '').split(';')) { const i = osa.indexOf('='); if (i > 0) ulos[osa.slice(0, i).trim()] = osa.slice(i + 1).trim(); }
    return ulos;
  }
  // Istunto on voimassa vain, jos käyttäjä on yhä olemassa (poisto Hallintatyökalusta katkaisee istunnon heti).
  function istunto(req) {
    const t = evasteet(req)[EVASTE];
    const i = t && istunnot.get(t);
    if (!i || i.vanhenee < nyt() || !kayttajat.tiedot(varasto).kayttajat[i.kayttaja]) { if (t) istunnot.delete(t); return null; }
    return i;
  }
  function asetaEvaste(res, arvo, ikaS) {
    const turvallinen = String(env.JULKINEN_OSOITE || '').startsWith('https://') ? '; Secure' : '';
    res.setHeader('Set-Cookie', `${EVASTE}=${arvo}; HttpOnly; SameSite=Strict; Path=/${turvallinen}; Max-Age=${ikaS}`);
  }
  const onKayttajia = () => Object.keys(kayttajat.tiedot(varasto).kayttajat).length > 0;

  // ------------------------------------------------------------ käyttöönotto ja kirjautuminen
  // Ensimmäinen käyttäjä: alkutunnus. Muut: Hallintatyökalun luoma kertakäyttöinen kutsu.
  async function aloitaAlustus(req, body) {
    if (rajoitin.kayta('alustus:' + ipOsoite(req, env), 10, 3600000)) throw new Virhe('Liian monta yritystä. Yritä tunnin kuluttua uudelleen.', 429);
    let nimi, sahkoposti;
    if (body.kutsu) {
      const k = kayttajat.haeKutsu(varasto, body.kutsu, nyt());
      if (!k) throw new Virhe('Kutsu ei ole voimassa. Pyydä uusi kutsu.', 403);
      ({ nimi, sahkoposti } = k);
    } else {
      if (onKayttajia()) throw new Virhe('Hallinnan tunnus on jo luotu.', 409);
      const alkutunnus = String(env.AKVERI_ALKUTUNNUS || '');
      if (alkutunnus.length < 32) throw new Virhe('Alkutunnusta ei ole asetettu palvelimelle. Aja AKVERIn julkaisu Hallintatyökalussa.', 503);
      if (!vakioaikainenVertailu(String(body.alkutunnus || ''), alkutunnus)) throw new Virhe('Alkutunnus ei täsmää.', 403);
      try { nimi = kayttajat.tarkistaNimi(body.nimi); sahkoposti = kayttajat.tarkistaPosti(body.sahkoposti); } catch (e) { throw new Virhe(e.message); }
    }
    const vika = salasanaKelpaa(body.salasana);
    if (vika) throw new Virhe(vika);
    const salaisuus = totp.luoSalaisuus();
    alustus = { salaisuus, salasanaTiiviste: await tiivistaSalasana(body.salasana), nimi, sahkoposti, kutsu: body.kutsu || null, vanhenee: nyt() + 15 * 60000 };
    return { salaisuus, otpauth: totp.otpauthUrl({ salaisuus, tili: sahkoposti, myontaja: 'AKVERI' }), nimi, sahkoposti };
  }
  function vahvistaAlustus(req, body) {
    if (!alustus || alustus.vanhenee < nyt() || (alustus.kutsu || null) !== (body.kutsu || null)) throw new Virhe('Käyttöönotto on vanhentunut. Aloita alusta.', 409);
    if (alustus.kutsu) { if (!kayttajat.haeKutsu(varasto, alustus.kutsu, nyt())) throw new Virhe('Kutsu ei ole enää voimassa.', 403); }
    else {
      if (onKayttajia()) throw new Virhe('Hallinnan tunnus on jo luotu.', 409);
      if (!vakioaikainenVertailu(String(body.alkutunnus || ''), String(env.AKVERI_ALKUTUNNUS || ''))) throw new Virhe('Alkutunnus ei täsmää.', 403);
    }
    const askel = totp.tarkistaKoodi(alustus.salaisuus, body.koodi, nyt());
    if (askel === null) throw new Virhe('Koodi ei täsmää. Tarkista puhelimen kellonaika ja yritä uudelleen.');
    try { kayttajat.lisaaKayttaja(varasto, { nimi: alustus.nimi, sahkoposti: alustus.sahkoposti, salasana: alustus.salasanaTiiviste, totp: alustus.salaisuus, askel, kutsu: alustus.kutsu }, nyt()); }
    catch (e) { throw new Virhe(e.message, 409); }
    alustus = null;
    return { ok: true };
  }
  async function kirjaudu(req, res, body) {
    const ip = ipOsoite(req, env);
    if (rajoitin.kayta('kirjaudu:' + ip, 10, 15 * 60000) || rajoitin.kayta('kirjaudu:kaikki', 60, 3600000)) throw new Virhe('Liian monta kirjautumisyritystä. Yritä myöhemmin uudelleen.', 429);
    const o = kayttajat.tiedot(varasto);
    if (!Object.keys(o.kayttajat).length) throw new Virhe('Hallinnan tunnusta ei ole vielä luotu.', 409);
    const rivi = kayttajat.haePostilla(o, body.sahkoposti);
    const k = rivi && rivi[1];
    const salasanaOk = await tarkistaSalasana(body.salasana, k ? k.salasana : 'scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA$' + 'A'.repeat(86));
    const askel = k ? totp.tarkistaKoodi(k.totp, body.koodi, nyt()) : null;
    if (!k || !salasanaOk || askel === null || askel <= (k.viimeisinAskel || 0)) {
      await new Promise(r => setTimeout(r, 400));
      throw new Virhe('Sähköposti, salasana tai vahvistuskoodi on väärin.', 401);
    }
    k.viimeisinAskel = askel; k.viimeksiKirjautunut = new Date(nyt()).toISOString();
    varasto.tallenna('omistaja');
    const t = crypto.randomBytes(32).toString('base64url');
    istunnot.set(t, { vanhenee: nyt() + ISTUNTO_MS, kayttaja: rivi[0] });
    asetaEvaste(res, t, ISTUNTO_MS / 1000);
    return { ok: true, nimi: k.nimi };
  }
  async function vaihdaSalasana(req, body) {
    const i = istunto(req);
    const k = kayttajat.tiedot(varasto).kayttajat[i.kayttaja];
    if (!(await tarkistaSalasana(body.nykyinen, k.salasana))) throw new Virhe('Nykyinen salasana on väärin.', 403);
    const vika = salasanaKelpaa(body.uusi);
    if (vika) throw new Virhe(vika);
    k.salasana = await tiivistaSalasana(body.uusi);
    varasto.tallenna('omistaja');
    for (const [t, x] of istunnot) if (x.kayttaja === i.kayttaja) istunnot.delete(t);
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
  const testiRiviAuki = testiRivi;
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
  // ---- Tietosuoja: tietojen poisto pyynnöstä ja säilytysajat (ks. tietosuojaseloste)
  // Tilin poisto: tili lakkaa toimimasta ja sen tunnistetiedot poistetaan. Krediittien kirjanpito ja ostot säilytetään
  // kirjanpitolain edellyttämän ajan; niissä on vain satunnainen tilitunnus. Rekisteröidyt raportit säilyvät, koska raportin
  // vastaanottajalla on oikeutettu etu tarkistaa ne; raportin tiedot voi poistaa erikseen.
  function poistaTili(id, body) {
    const t = haeTili(id);
    if (body.vahvista !== t.id) throw new Virhe('Vahvista poisto kirjoittamalla tilitunnus.');
    for (const x of Object.values(varasto.get('testit'))) {
      if (x.tili !== t.id) continue;
      if (x.hyvityspyynto) { x.hyvityspyynto.syy = ''; x.hyvityspyynto.tiedot = ''; }
      if (x.tila === 'varattu') { x.tila = 'peruttu'; x.peruttu = new Date(nyt()).toISOString(); x.perumisenSyy = 'Tili poistettu'; }
    }
    varasto.tallenna('testit');
    delete varasto.get('tilit')[t.id];
    varasto.tallenna('tilit');
    return { ok: true, poistettu: t.id };
  }
  function tyhjennaRaportti(x, syy) {
    x.raportti = null; x.tila = 'poistettu'; x.poistettu = new Date(nyt()).toISOString(); x.poistonSyy = syy;
    if (x.hyvityspyynto) { x.hyvityspyynto.syy = ''; x.hyvityspyynto.tiedot = ''; }
  }
  function poistaRaportinTiedot(tunnus, body) {
    const x = haeTesti(tunnus);
    const syy = yksiRivi(puhdista(body.syy, 200));
    if (!syy) throw new Virhe('Kirjoita poiston syy (esim. rekisteröidyn pyyntö).');
    tyhjennaRaportti(x, syy);
    varasto.tallenna('testit');
    return testiRiviAuki(x);
  }
  // Säilytysajat, ajetaan kerran vuorokaudessa: viestit 2 vuotta, hyvityspyyntöjen tekstit 2 vuotta, raportit 10 vuotta.
  function sailytysajat() {
    const nytMs = nyt(), V2 = 2 * 365 * 86400000, V10 = 10 * 366 * 86400000;
    let viestit = 0, raportit = 0, pyynnot = 0;
    const v = varasto.get('viestit');
    for (const [id, x] of Object.entries(v)) if (nytMs - Date.parse(x.aika) > V2) { delete v[id]; viestit++; }
    for (const x of Object.values(varasto.get('testit'))) {
      if (x.raportti && nytMs - Date.parse(x.rekisteroity || x.varattu) > V10) { tyhjennaRaportti(x, 'Säilytysaika päättyi'); raportit++; }
      if (x.hyvityspyynto && (x.hyvityspyynto.syy || x.hyvityspyynto.tiedot) && nytMs - Date.parse(x.hyvityspyynto.aika) > V2) { x.hyvityspyynto.syy = ''; x.hyvityspyynto.tiedot = ''; pyynnot++; }
    }
    if (viestit) varasto.tallenna('viestit');
    if (raportit || pyynnot) varasto.tallenna('testit');
    return { viestit, raportit, pyynnot };
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
    varasto.kirjaa({ tili: t.tili, muutos: t.krediitit || 1, syy: 'hyvitys', viite: t.tunnus, tekija: 'omistaja', selite });
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
      hinnat: Object.fromEntries(MITTAUSTYYPIT.map(t => [t, Number.isInteger((a.hinnat || {})[t]) && a.hinnat[t] >= 1 ? a.hinnat[t] : OLETUSHINTA])),
      hyvitysaikaMin: Number(a.hyvitysaikaMin) > 0 ? Number(a.hyvitysaikaMin) : 60,
      vahimmaisversio: VERSIO_RE.test(String(a.vahimmaisversio)) ? a.vahimmaisversio : OLETUS_VAHIMMAISVERSIO, uusinVersio: a.uusinVersio || '',
      asiakirjat: { ehdot: a.asiakirjat && a.asiakirjat.ehdot || null, tietosuoja: a.asiakirjat && a.asiakirjat.tietosuoja || null },
      huoltotila: huoltotila(),
      posti: postiNakyma()
    };
  }
  // Huoltotila: pois, vain sivusto tai sivusto ja sovelluksen palvelu (krediitit, mittausten rekisteröinti, raporttien tarkistus).
  // Hallinta, käyttöehdot ja tietosuojaseloste toimivat aina. Kirjautunut hallinnan käyttäjä näkee sivuston normaalisti.
  // Sähköposti: palvelin, ilmoitusten lähettäjä (noreply), omien viestien lähettäjä (info) ja ilmoitusten vastaanottaja.
  // Salasanaa ei koskaan palauteta selaimelle.
  function postiNakyma() {
    const p = asetukset().posti;
    return p ? { host: p.host, port: p.port, secure: !!p.secure, user: p.user || '', salasanaAsetettu: !!p.pass, lahettaja: p.lahettaja || '', lahettajaOmat: p.lahettajaOmat || '', vastaanottaja: p.vastaanottaja || '' } : null;
  }
  function huoltotila() {
    const h = asetukset().huoltotila || {};
    return { tila: HUOLTOTILAT.includes(h.tila) ? h.tila : 'pois', viesti: typeof h.viesti === 'string' && h.viesti.trim() ? h.viesti : HUOLTOVIESTI, muutettu: h.muutettu || null };
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
    if (body.hinnat !== undefined) {
      if (!body.hinnat || typeof body.hinnat !== 'object') throw new Virhe('Anna mittausten hinnat.');
      const uusi = {};
      for (const t of MITTAUSTYYPIT) {
        const n = Number(body.hinnat[t] === undefined ? (a.hinnat || {})[t] || OLETUSHINTA : body.hinnat[t]);
        if (!Number.isInteger(n) || n < 1 || n > 100) throw new Virhe('Mittauksen hinta on 1–100 krediittiä.');
        uusi[t] = n;
      }
      a.hinnat = uusi;
    }
    if (body.posti !== undefined) {
      if (body.posti === null) delete a.posti;
      else {
        const p = body.posti || {};
        const host = yksiRivi(puhdista(p.host, 200)).toLowerCase();
        if (!/^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$/.test(host)) throw new Virhe('Anna sähköpostipalvelimen nimi, esimerkiksi smtp.esimerkki.fi.');
        const port = Number(p.port);
        if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Virhe('Portti on yleensä 587 tai 465.');
        const osoite = (s, kentta, pakollinen) => {
          const t = yksiRivi(puhdista(s, 200));
          if (!t && !pakollinen) return '';
          if (!osoiteOsasta(t)) throw new Virhe(`${kentta}: anna sähköpostiosoite tai muoto "AKVERI <osoite@akveri.fi>".`);
          return t;
        };
        const vanha = a.posti || {};
        a.posti = {
          host, port, secure: p.secure === true, user: yksiRivi(puhdista(p.user, 200)),
          pass: typeof p.pass === 'string' && p.pass !== '' ? p.pass.slice(0, 500) : (vanha.pass || ''),
          lahettaja: osoite(p.lahettaja, 'Ilmoitusten lähettäjä', true),
          lahettajaOmat: osoite(p.lahettajaOmat, 'Omien viestien lähettäjä', false),
          vastaanottaja: osoite(p.vastaanottaja, 'Ilmoitusten vastaanottaja', true)
        };
      }
    }
    if (body.huoltotila !== undefined) {
      const h = body.huoltotila || {};
      if (!HUOLTOTILAT.includes(h.tila)) throw new Virhe('Valitse huoltotila.');
      if (typeof h.viesti === 'string' && h.viesti.trim().length > 500) throw new Virhe('Huoltoviestissä voi olla enintään 500 merkkiä.');
      a.huoltotila = { tila: h.tila, viesti: yksiRivi(puhdista(h.viesti, 500)) || HUOLTOVIESTI, muutettu: new Date(nyt()).toISOString() };
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
    const kieli = ['en', 'sv'].includes(body.kieli) ? body.kieli : 'fi'; // sivun kieli: vastaus samalla kielellä
    if (!nimi || !teksti) throw new Virhe('Täytä nimi ja viesti.');
    if (!SAHKOPOSTI.test(sahkoposti)) throw new Virhe('Tarkista sähköpostiosoite.');
    if (body.suostumus !== true) throw new Virhe('Hyväksy tietojen käyttö viestiin vastaamiseen.');
    if (rajoitin.kayta('viesti:' + ipOsoite(req, env), 5, 3600000)) throw new Virhe('Liian monta viestiä. Yritä myöhemmin uudelleen.', 429);
    const v = varasto.get('viestit');
    if (Object.keys(v).length >= 5000) throw new Virhe('Viestien vastaanotto on hetkellisesti täynnä. Lähetä viesti sähköpostilla.', 503);
    v[crypto.randomBytes(8).toString('hex')] = { aika: new Date(nyt()).toISOString(), nimi, sahkoposti, aihe, testitunnus, kieli, viesti: teksti, kasitelty: false };
    varasto.tallenna('viestit');
    if (postitus) postitus.ilmoitaTaustalla(`AKVERI: uusi yhteydenotto${aihe ? ' (' + aihe + ')' : ''}`, `Lähettäjä: ${nimi} <${sahkoposti}>\n${kieli !== 'fi' ? 'Kieli: ' + KIELTEN_NIMET[kieli] + '\n' : ''}${testitunnus ? 'Raportti: ' + muotoileTunnus(testitunnus) + '\n' : ''}\n${teksti}\n\nVastaa viestiin akveri.fi/hallinta → Viestit.\n`);
    return { ok: true };
  }

  async function kasitteleJulkinen(req, res, polku) {
    try {
      if (polku === '/api/sivusto/tiedot' && req.method === 'GET') {
        const a = julkisetAsetukset();
        // Julkinen sähköposti: yhteystietojen osoite tai, jos sitä ei ole, omien viestien osoite (info).
        const yt = { ...a.yhteystiedot };
        if (!yt.sahkoposti && postitus && postitus.infoOsoite()) yt.sahkoposti = postitus.infoOsoite();
        return json(res, 200, { yhteystiedot: yt, playLinkki: a.playLinkki, hinnasto: a.hinnasto, hyvitysaikaMin: a.hyvitysaikaMin });
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
      if (p === '/tila' && req.method === 'GET') {
        const i = istunto(req);
        const k = i && kayttajat.tiedot(varasto).kayttajat[i.kayttaja];
        return json(res, 200, { alustettu: onKayttajia(), kirjautunut: !!k, nimi: k ? k.nimi : null, alkutunnusAsetettu: String(env.AKVERI_ALKUTUNNUS || '').length >= 32 });
      }
      if (p === '/kutsu' && req.method === 'POST') {
        // Kutsulinkin tarkistus ennen käyttöönottoa: kertoo vain nimen ja sähköpostin, jolle kutsu on tehty.
        if (rajoitin.kayta('kutsu:' + ipOsoite(req, env), 20, 3600000)) throw new Virhe('Liian monta yritystä.', 429);
        const k = kayttajat.haeKutsu(varasto, (await lueJson(req)).kutsu, nyt());
        if (!k) throw new Virhe('Kutsu ei ole voimassa. Pyydä uusi kutsu.', 404);
        return json(res, 200, { nimi: k.nimi, sahkoposti: k.sahkoposti });
      }
      if (p === '/alusta' && req.method === 'POST') return json(res, 200, await aloitaAlustus(req, await lueJson(req)));
      if (p === '/alusta/vahvista' && req.method === 'POST') return json(res, 200, vahvistaAlustus(req, await lueJson(req)));
      if (p === '/kirjaudu' && req.method === 'POST') return json(res, 200, await kirjaudu(req, res, await lueJson(req)));
      if (p === '/ulos' && req.method === 'POST') { const t = evasteet(req)[EVASTE]; if (t) istunnot.delete(t); asetaEvaste(res, '', 0); return json(res, 200, { ok: true }); }
      if (!istunto(req)) throw new Virhe('Kirjaudu sisään.', 401);
      const body = req.method === 'GET' ? {} : await lueJson(req, 128 * 1024);
      if (p === '/salasana' && req.method === 'POST') return json(res, 200, await vaihdaSalasana(req, body));
      if (p === '/kayttajat' && req.method === 'GET') return json(res, 200, kayttajat.lista(varasto, nyt()));
      if (p === '/yhteenveto' && req.method === 'GET') return json(res, 200, yhteenveto());
      if (p === '/tilit' && req.method === 'GET') return json(res, 200, { tilit: tilit(kysely) });
      let m = /^\/tilit\/(T[0-9A-Z]{12})(\/krediitit|\/tila)?$/.exec(p);
      if (m && !m[2] && req.method === 'GET') return json(res, 200, tili(m[1]));
      if (m && m[2] === '/krediitit' && req.method === 'POST') return json(res, 200, muutaKrediitteja(m[1], body));
      if (m && m[2] === '/tila' && req.method === 'POST') return json(res, 200, tilinTila(m[1], body));
      if (m && !m[2] && req.method === 'DELETE') return json(res, 200, poistaTili(m[1], body));
      if (p === '/testit' && req.method === 'GET') return json(res, 200, { testit: testit(kysely) });
      m = /^\/testit\/([A-Za-z0-9-]{10,20})\/(hyvita|mitatoi|hylkaa-pyynto|poista-tiedot)$/.exec(p);
      if (m && req.method === 'POST') return json(res, 200, m[2] === 'hyvita' ? hyvita(m[1], body) : m[2] === 'mitatoi' ? mitatoi(m[1], body) : m[2] === 'poista-tiedot' ? poistaRaportinTiedot(m[1], body) : hylkaaHyvityspyynto(m[1], body));
      if (p === '/ostot' && req.method === 'GET') return json(res, 200, { ostot: ostot() });
      if (p === '/viestit' && req.method === 'GET') return json(res, 200, { viestit: viestit() });
      m = /^\/viestit\/([a-f0-9]{16})$/.exec(p);
      if (m && req.method === 'POST') { const v = varasto.get('viestit')[m[1]]; if (!v) throw new Virhe('Viestiä ei löydy.', 404); v.kasitelty = body.kasitelty !== false; varasto.tallenna('viestit'); return json(res, 200, { ok: true }); }
      const mv = /^\/viestit\/([a-f0-9]{16})\/vastaa$/.exec(p);
      if (mv && req.method === 'POST') {
        const v = varasto.get('viestit')[mv[1]]; if (!v) throw new Virhe('Viestiä ei löydy.', 404);
        const teksti = puhdista(body.teksti, 5000);
        if (!teksti.trim()) throw new Virhe('Kirjoita vastaus.');
        if (!postitus || !postitus.kaytossa()) throw new Virhe('Sähköpostia ei ole asetettu. Aseta se kohdassa Sivusto ja ehdot → Sähköposti.', 409);
        try { await postitus.omaViesti(v.sahkoposti, 'Re: AKVERI' + (v.aihe ? ': ' + v.aihe : ''), teksti); }
        catch (e) { throw new Virhe('Vastauksen lähetys epäonnistui: ' + e.message, 502); }
        v.vastaukset = [...(v.vastaukset || []), { aika: new Date(nyt()).toISOString(), teksti }].slice(-20); v.kasitelty = true;
        varasto.tallenna('viestit');
        return json(res, 200, { ok: true });
      }
      if (p === '/posti/testi' && req.method === 'POST') {
        if (!postitus || !postitus.kaytossa()) throw new Virhe('Sähköpostia ei ole asetettu.', 409);
        try { await postitus.ilmoita('AKVERI: sähköpostin testi', 'Tämä on testiviesti akveri.fi:n hallinnasta. Jos luet tämän, ilmoitukset toimivat.\n'); }
        catch (e) { throw new Virhe('Testiviesti epäonnistui: ' + e.message, 502); }
        return json(res, 200, { ok: true });
      }
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

  // Onko pyynnön tekijä kirjautunut hallintaan (huoltotilan ohitus samassa selaimessa).
  const kirjautunut = (req) => !!istunto(req);
  return { kasittele, kasitteleJulkinen, sallittu, julkisetAsetukset, latauskansio, sailytysajat, huoltotila, kirjautunut };
}

module.exports = { luoHallinta, tiivistaSalasana, tarkistaSalasana };
