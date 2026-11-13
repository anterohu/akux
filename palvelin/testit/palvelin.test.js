// AKVERI-palvelimen testit: krediitit, ostot, testiluvat, raportin tarkistus, hallinta ja sivusto.
// Ajo: node --test palvelin/testit/
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const zlib = require('zlib');
const { luoPalvelin } = require('../server');
const totp = require('../lib/totp');
const { kokoa } = require('../kokoa');

const ALKUTUNNUS = 'a'.repeat(48);
const PAKETTI = 'fi.akux.app';

// Google Play -rajapinnan korvike: palvelutilin avain, OAuth ja ostojen tiedot muistissa.
function googleKorvike() {
  const { privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const ostot = new Map(); // ostotunnus -> vastaus
  const perutut = [];
  const kutsut = [];
  async function haku(url, o = {}) {
    kutsut.push(url);
    const vastaa = (status, d) => ({ ok: status === 200, status, json: async () => d });
    if (url === 'https://oauth2.googleapis.com/token') {
      const assertion = new URLSearchParams(o.body).get('assertion');
      const [h, s, a] = assertion.split('.');
      const ok = crypto.verify('RSA-SHA256', Buffer.from(h + '.' + s), crypto.createPublicKey(privateKey), Buffer.from(a, 'base64url'));
      return ok ? vastaa(200, { access_token: 'tunnus', expires_in: 3600 }) : vastaa(401, { error: 'invalid_grant' });
    }
    assert.equal(o.headers.Authorization, 'Bearer tunnus');
    const m = /\/applications\/([^/]+)\/purchases\/products\/([^/]+)\/tokens\/(.+)$/.exec(url);
    if (m) { assert.equal(m[1], PAKETTI); const v = ostot.get(decodeURIComponent(m[3])); return v && v.tuote === decodeURIComponent(m[2]) ? vastaa(200, v.vastaus) : vastaa(404, {}); }
    if (/voidedpurchases/.test(url)) return vastaa(200, { voidedPurchases: perutut });
    return vastaa(404, {});
  }
  const tili = { client_email: 'akveri@projekti.iam.gserviceaccount.com', private_key: privateKey.export({ type: 'pkcs8', format: 'pem' }) };
  return { haku, tili, ostot, perutut, kutsut };
}

async function kaynnista(t, { lisaEnv = {}, kello } = {}) {
  const kansio = fs.mkdtempSync(path.join(os.tmpdir(), 'akveri-palvelin-'));
  const g = googleKorvike();
  const tiliTiedosto = path.join(kansio, 'palvelutili.json');
  fs.writeFileSync(tiliTiedosto, JSON.stringify(g.tili));
  const aika = kello || { t: Date.parse('2026-11-13T10:00:00Z') };
  const palvelin = luoPalvelin({
    env: { DB_DIR: path.join(kansio, 'data'), JULKINEN_OSOITE: 'https://akveri.fi', AKVERI_ALKUTUNNUS: ALKUTUNNUS, GOOGLE_PLAY_PAKETTI: PAKETTI, GOOGLE_PALVELUTILI: tiliTiedosto, ...lisaEnv },
    nyt: () => aika.t, haku: g.haku
  });
  await new Promise(r => palvelin.listen(0, '127.0.0.1', r));
  const osoite = `http://127.0.0.1:${palvelin.address().port}`;
  t.after(() => { palvelin.close(); fs.rmSync(kansio, { recursive: true, force: true }); });
  async function pyynto(polku, { method = 'GET', body, auth, otsakkeet = {}, evaste } = {}) {
    const h = { ...otsakkeet };
    if (body !== undefined) h['Content-Type'] = 'application/json';
    if (auth) h.Authorization = `AKVERI ${auth.tili}.${auth.avain}`;
    if (polku.startsWith('/api/v1/') && !('X-AKVERI-Versio' in h) && !otsakkeet.ilmanVersiota) h['X-AKVERI-Versio'] = '2.0.0';
    delete h.ilmanVersiota;
    if (evaste) h.Cookie = evaste;
    const r = await fetch(osoite + polku, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body), redirect: 'manual' });
    const teksti = await r.text();
    let d = null; try { d = JSON.parse(teksti); } catch (e) { d = teksti; }
    return { status: r.status, d, h: r.headers };
  }
  return { palvelin, pyynto, g, aika, kansio };
}

function osto(g, ostotunnus, tuote, tili, lisa = {}) {
  g.ostot.set(ostotunnus, { tuote, vastaus: { purchaseState: 0, consumptionState: 0, orderId: 'GPA.1234-' + ostotunnus, obfuscatedExternalAccountId: tili, purchaseTimeMillis: '1763000000000', ...lisa } });
}
const TARKISTE = 'ab'.repeat(32);
const VIN = '5YJ3E7EB1LF000123';

test('tili alkaa nollasta, eikä mittausta voi aloittaa ilman krediittiä', async (t) => {
  const { pyynto } = await kaynnista(t);
  const tili = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  assert.match(tili.tili, /^T[0-9A-Z]{12}$/);
  assert.equal((await pyynto('/api/v1/saldo', { auth: tili })).d.saldo, 0);
  const v = await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: tili, body: {} });
  assert.equal(v.status, 402);
  assert.equal((await pyynto('/api/v1/saldo', { auth: { tili: tili.tili, avain: 'x'.repeat(43) } })).status, 401);
});

test('Google Play -osto hyvittyy kerran ja vain omalle tilille', async (t) => {
  const { pyynto, g } = await kaynnista(t);
  const a = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  const b = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  osto(g, 'token-1', 'akveri_testi_5', a.tili);
  const r1 = await pyynto('/api/v1/osto', { method: 'POST', auth: a, body: { tuote: 'akveri_testi_5', ostotunnus: 'token-1' } });
  assert.equal(r1.status, 200); assert.equal(r1.d.hyvitetty, 5); assert.equal(r1.d.saldo, 5);
  const r2 = await pyynto('/api/v1/osto', { method: 'POST', auth: a, body: { tuote: 'akveri_testi_5', ostotunnus: 'token-1' } });
  assert.equal(r2.d.hyvitetty, 0); assert.equal(r2.d.saldo, 5);
  assert.equal((await pyynto('/api/v1/osto', { method: 'POST', auth: b, body: { tuote: 'akveri_testi_5', ostotunnus: 'token-1' } })).status, 409);
  osto(g, 'token-2', 'akveri_testi_1', a.tili);
  assert.equal((await pyynto('/api/v1/osto', { method: 'POST', auth: b, body: { tuote: 'akveri_testi_1', ostotunnus: 'token-2' } })).status, 409, 'toisen tilin osto ei kelpaa');
  osto(g, 'token-3', 'akveri_testi_1', b.tili, { purchaseState: 2 });
  assert.equal((await pyynto('/api/v1/osto', { method: 'POST', auth: b, body: { tuote: 'akveri_testi_1', ostotunnus: 'token-3' } })).d.odottaa, true);
  assert.equal((await pyynto('/api/v1/osto', { method: 'POST', auth: b, body: { tuote: 'akveri_testi_1', ostotunnus: 'keksitty' } })).status, 402);
  assert.equal((await pyynto('/api/v1/osto', { method: 'POST', auth: b, body: { tuote: 'tuntematon', ostotunnus: 'x' } })).status, 400);
  assert.equal((await pyynto('/api/v1/saldo', { auth: b })).d.saldo, 0);
});

test('testilupa, rekisteröinti ja julkinen tarkistus', async (t) => {
  const { pyynto, g } = await kaynnista(t);
  const a = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  osto(g, 'token-1', 'akveri_testi_1', a.tili);
  await pyynto('/api/v1/osto', { method: 'POST', auth: a, body: { tuote: 'akveri_testi_1', ostotunnus: 'token-1' } });
  const lupa = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, body: { alusta: 'android', versio: '2.0.0' } })).d;
  assert.match(lupa.tunnus, /^AK[0-9A-Z]{10}$/);
  assert.equal(lupa.saldo, 0);
  assert.equal(lupa.osoite, 'https://akveri.fi/v/' + lupa.tunnus);
  const avain = (await pyynto('/api/v1/avain')).d.julkinen;
  const julkinen = crypto.createPublicKey({ key: Buffer.from(avain, 'base64'), format: 'der', type: 'spki' });
  assert.ok(crypto.verify(null, Buffer.from(`AKVERI-LUPA|${lupa.tunnus}|${a.tili}|${lupa.varattu}`), julkinen, Buffer.from(lupa.allekirjoitus, 'base64')), 'lupa on allekirjoitettu');

  let v = (await pyynto('/api/v1/vahvistus/' + lupa.tunnusNaytto)).d;
  assert.equal(v.tila, 'varattu'); assert.equal(v.kuntoPct, undefined);

  const yv = { tyyppi: 'Täysi akkutesti', merkki: 'Tesla', malli: 'Model 3 Long Range', vin: VIN, mittarilukema: 61234, kunto_pct: 93.7, kapasiteetti_kwh: 72.6, mitattu: 1763020000, paattynyt: 1763060000, raporttinumero: '2026-00009', riippumaton: true };
  const r = await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: a, body: { tunnus: lupa.tunnus, tarkiste: TARKISTE, yhteenveto: yv, versio: '2.0.0' } });
  assert.equal(r.status, 200);
  v = (await pyynto('/api/v1/vahvistus/' + lupa.tunnus.toLowerCase())).d;
  assert.equal(v.tila, 'valmis'); assert.equal(v.kuntoPct, 93.7); assert.equal(v.vin, '5YJ········000123');
  assert.equal(v.tarkiste, TARKISTE.slice(0, 16));
  assert.equal(JSON.stringify(v).includes(VIN), false, 'koko valmistenumeroa ei näytetä');
  assert.equal((await pyynto(`/api/v1/vahvistus/${lupa.tunnus}?vin=${VIN}`)).d.vinTasmaa, true);
  assert.equal((await pyynto(`/api/v1/vahvistus/${lupa.tunnus}?vin=5YJ3E7EB1LF000124`)).d.vinTasmaa, false);
  // Sama lupa ei kelpaa toiseen mittaukseen, mutta saman mittauksen uudelleenlaskenta päivittää tuloksen
  assert.equal((await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: a, body: { tunnus: lupa.tunnus, tarkiste: 'cd'.repeat(32), yhteenveto: yv } })).status, 409);
  assert.equal((await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: a, body: { tunnus: lupa.tunnus, tarkiste: TARKISTE, yhteenveto: { ...yv, kunto_pct: 93.5 } } })).status, 200);
  v = (await pyynto('/api/v1/vahvistus/' + lupa.tunnus)).d;
  assert.equal(v.kuntoPct, 93.5); assert.ok(v.paivitetty);
  // Rekisteröityä lupaa ei voi perua
  assert.equal((await pyynto('/api/v1/testi/peru', { method: 'POST', auth: a, body: { tunnus: lupa.tunnus } })).status, 409);
  assert.equal((await pyynto('/api/v1/vahvistus/AK0000000000')).d.loytyi, false);
  // Toinen tili ei näe eikä käytä toisen lupaa
  const b = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  assert.equal((await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: b, body: { tunnus: lupa.tunnus, tarkiste: TARKISTE, yhteenveto: yv } })).status, 404);
});

test('peruminen palauttaa krediitin vain perumisajan sisällä, ja peruttu lupa ei kelpaa raporttiin', async (t) => {
  const { pyynto, g, aika } = await kaynnista(t);
  const a = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  osto(g, 'token-1', 'akveri_testi_5', a.tili);
  await pyynto('/api/v1/osto', { method: 'POST', auth: a, body: { tuote: 'akveri_testi_5', ostotunnus: 'token-1' } });
  const l1 = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, body: {} })).d;
  aika.t += 30 * 60000;
  const p = await pyynto('/api/v1/testi/peru', { method: 'POST', auth: a, body: { tunnus: l1.tunnus, syy: 'Sovitin ei vastannut' } });
  assert.equal(p.status, 200); assert.equal(p.d.saldo, 5);
  assert.equal((await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: a, body: { tunnus: l1.tunnus, tarkiste: TARKISTE, yhteenveto: {} } })).status, 409);
  assert.equal((await pyynto('/api/v1/vahvistus/' + l1.tunnus)).d.tila, 'peruttu');
  const l2 = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, body: {} })).d;
  aika.t += 61 * 60000;
  assert.equal((await pyynto('/api/v1/testi/peru', { method: 'POST', auth: a, body: { tunnus: l2.tunnus } })).status, 409);
  assert.equal((await pyynto('/api/v1/testi/hyvityspyynto', { method: 'POST', auth: a, body: { tunnus: l2.tunnus, syy: 'Mittaus jumittui' } })).status, 200);
  assert.equal((await pyynto('/api/v1/saldo', { auth: a })).d.saldo, 4);
});

test('Google Playssa peruttu osto vähentää krediitit', async (t) => {
  const { pyynto, g, palvelin } = await kaynnista(t);
  const a = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  osto(g, 'token-1', 'akveri_testi_5', a.tili);
  await pyynto('/api/v1/osto', { method: 'POST', auth: a, body: { tuote: 'akveri_testi_5', ostotunnus: 'token-1' } });
  g.perutut.push({ purchaseToken: 'token-1', orderId: 'GPA.1234-token-1', voidedTimeMillis: String(Date.now()) });
  assert.equal(await palvelin.sovellus.tarkistaPerutut(), 1);
  assert.equal(await palvelin.sovellus.tarkistaPerutut(), 0, 'sama peruminen vähennetään vain kerran');
  assert.equal((await pyynto('/api/v1/saldo', { auth: a })).d.saldo, 0);
});

async function kirjauduHallintaan(pyynto, aika) {
  const H = { 'X-AKVERI-Hallinta': '1' };
  const a = await pyynto('/api/hallinta/alusta', { method: 'POST', otsakkeet: H, body: { alkutunnus: ALKUTUNNUS, salasana: 'pitka-salasana-123' } });
  assert.equal(a.status, 200);
  assert.equal((await pyynto('/api/hallinta/alusta/vahvista', { method: 'POST', otsakkeet: H, body: { alkutunnus: ALKUTUNNUS, koodi: totp.koodiNyt(a.d.salaisuus, aika.t) } })).status, 200);
  aika.t += 31000;
  const k = await pyynto('/api/hallinta/kirjaudu', { method: 'POST', otsakkeet: H, body: { salasana: 'pitka-salasana-123', koodi: totp.koodiNyt(a.d.salaisuus, aika.t) } });
  assert.equal(k.status, 200);
  const cookie = k.h.get('set-cookie');
  assert.match(cookie, /HttpOnly; SameSite=Strict; Path=\/; Secure/);
  return { evaste: cookie.split(';')[0], otsakkeet: H, salaisuus: a.d.salaisuus };
}

test('hallinta: käyttöönotto, kirjautuminen ja krediittien käsittely', async (t) => {
  const { pyynto, aika, palvelin } = await kaynnista(t);
  const H = { 'X-AKVERI-Hallinta': '1' };
  assert.equal((await pyynto('/api/hallinta/alusta', { method: 'POST', otsakkeet: H, body: { alkutunnus: 'b'.repeat(48), salasana: 'pitka-salasana-123' } })).status, 403);
  const s = await kirjauduHallintaan(pyynto, aika);
  // Uutta tunnusta ei voi luoda, kun tunnus on olemassa
  assert.equal((await pyynto('/api/hallinta/alusta', { method: 'POST', otsakkeet: H, body: { alkutunnus: ALKUTUNNUS, salasana: 'toinen-salasana-123' } })).status, 409);
  // Sama koodi ei kelpaa toiseen kirjautumiseen
  assert.equal((await pyynto('/api/hallinta/kirjaudu', { method: 'POST', otsakkeet: H, body: { salasana: 'pitka-salasana-123', koodi: totp.koodiNyt(s.salaisuus, aika.t) } })).status, 401);
  // Ilman istuntoa tai ilman otsaketta ei pääse
  assert.equal((await pyynto('/api/hallinta/yhteenveto')).status, 401);
  const tili = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  assert.equal((await pyynto(`/api/hallinta/tilit/${tili.tili}/krediitit`, { method: 'POST', evaste: s.evaste, body: { muutos: 3, selite: 'Oma tili' } })).status, 403, 'muutos vaatii hallinnan otsakkeen');
  assert.equal((await pyynto(`/api/hallinta/tilit/${tili.tili}/krediitit`, { method: 'POST', evaste: s.evaste, otsakkeet: H, body: { muutos: 3 } })).status, 400, 'syy on pakollinen');
  const m = await pyynto(`/api/hallinta/tilit/${tili.tili}/krediitit`, { method: 'POST', evaste: s.evaste, otsakkeet: H, body: { muutos: 3, selite: 'Oma tili' } });
  assert.equal(m.d.saldo, 3);
  const lupa = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: tili, body: {} })).d;
  await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: tili, body: { tunnus: lupa.tunnus, tarkiste: TARKISTE, yhteenveto: { vin: VIN } } });
  assert.equal((await pyynto(`/api/hallinta/testit/${lupa.tunnus}/hyvita`, { method: 'POST', evaste: s.evaste, otsakkeet: H, body: { selite: 'Virheellinen mittaus' } })).status, 409, 'rekisteröidyn raportin hyvitys vaatii mitätöinnin vahvistuksen');
  const hv = await pyynto(`/api/hallinta/testit/${lupa.tunnus}/hyvita`, { method: 'POST', evaste: s.evaste, otsakkeet: H, body: { selite: 'Virheellinen mittaus', mitatoi: true } });
  assert.equal(hv.d.tila, 'mitatoity');
  assert.equal((await pyynto('/api/v1/vahvistus/' + lupa.tunnus)).d.tila, 'mitatoity');
  assert.equal((await pyynto('/api/v1/saldo', { auth: tili })).d.saldo, 3);
  assert.equal((await pyynto(`/api/hallinta/testit/${lupa.tunnus}/hyvita`, { method: 'POST', evaste: s.evaste, otsakkeet: H, body: { selite: 'uudelleen', mitatoi: true } })).status, 409, 'ei toista hyvitystä');
  const yv = (await pyynto('/api/hallinta/yhteenveto', { evaste: s.evaste })).d;
  assert.equal(yv.kirjanpitoEhja, true); assert.equal(yv.googleKaytossa, true);
  // Kirjanpidon muokkaus palvelimen ulkopuolelta havaitaan
  const kp = path.join(palvelin.varasto.kansio, 'kirjanpito.jsonl');
  fs.writeFileSync(kp, fs.readFileSync(kp, 'utf8').replace('"muutos":3', '"muutos":30'));
  const { Varasto } = require('../lib/varasto');
  assert.equal(new Varasto(palvelin.varasto.kansio).kirjanpitoEhja, false);
});

test('hallinta: asetukset, asiakirjat, lataukset ja IP-rajaus', async (t) => {
  const { pyynto, aika, palvelin } = await kaynnista(t);
  const s = await kirjauduHallintaan(pyynto, aika);
  const put = (body) => pyynto('/api/hallinta/asetukset', { method: 'PUT', evaste: s.evaste, otsakkeet: s.otsakkeet, body });
  assert.equal((await put({ yhteystiedot: { nimi: 'Testi Oy', yTunnus: '123' } })).status, 400);
  assert.equal((await put({ yhteystiedot: { nimi: 'Testi Oy', yTunnus: '1234567-8', sahkoposti: 'tuki@akveri.fi' } })).status, 200);
  assert.equal((await put({ playLinkki: 'https://example.com/apk' })).status, 400, 'lataus vain Google Playn kautta');
  assert.equal((await put({ playLinkki: 'https://play.google.com/store/apps/details?id=fi.akux.app' })).status, 200);
  assert.equal((await put({ tuotteet: [{ tuote: 'akveri_testi_1', krediitit: 1 }, { tuote: 'akveri_testi_1', krediitit: 2 }] })).status, 400);
  assert.equal((await put({ asiakirja: { tyyppi: 'ehdot', teksti: '## Ehdot\n\nPalvelun tarjoaa {{nimi}}.' } })).status, 200);
  const tiedot = (await pyynto('/api/sivusto/tiedot')).d;
  assert.equal(tiedot.yhteystiedot.nimi, 'Testi Oy'); assert.match(tiedot.playLinkki, /^https:\/\/play\.google\.com/);
  assert.match((await pyynto('/api/sivusto/asiakirja/ehdot')).d.teksti, /\{\{nimi\}\}/);
  // Omat lataukset vain kirjautuneelle, ei polkujen ohitusta
  fs.mkdirSync(path.join(palvelin.varasto.kansio, 'lataukset'));
  fs.writeFileSync(path.join(palvelin.varasto.kansio, 'lataukset', 'AKVERI-2.0.0.exe'), 'MZ');
  assert.equal((await pyynto('/api/hallinta/lataukset/AKVERI-2.0.0.exe')).status, 401);
  const l = await pyynto('/api/hallinta/lataukset/AKVERI-2.0.0.exe', { evaste: s.evaste });
  assert.equal(l.status, 200); assert.equal(l.d, 'MZ');
  assert.equal((await pyynto('/api/hallinta/lataukset/..%2Fomistaja.json', { evaste: s.evaste })).status, 404);
  assert.equal((await pyynto('/api/hallinta/lataukset', { evaste: s.evaste })).d.lataukset.length, 1);
  // Julkisella sivustolla ei ole asennustiedostoja
  assert.equal((await pyynto('/AKVERI-2.0.0.exe')).status, 404);
  assert.equal((await pyynto('/lataukset/AKVERI-2.0.0.exe')).status, 404);
});

test('hallinnan IP-rajaus piilottaa sivun ja rajapinnan', async (t) => {
  const { pyynto } = await kaynnista(t, { lisaEnv: { HALLINTA_SALLITUT_IP: '203.0.113.5' } });
  assert.equal((await pyynto('/hallinta')).status, 404);
  assert.equal((await pyynto('/hallinta.js')).status, 404);
  assert.equal((await pyynto('/api/hallinta/tila')).status, 404);
  assert.equal((await pyynto('/')).status, 200);
});

test('sivusto: sivut, suojausotsakkeet ja yhteydenottolomake', async (t) => {
  const { pyynto } = await kaynnista(t);
  for (const s of ['/', '/tarkista', '/v/AK7H2QKM4XPC', '/ehdot', '/tietosuoja', '/yhteystiedot', '/hallinta', '/sivusto.css', '/sivusto.js', '/tarkista.js', '/qr.js', '/logo.svg', '/robots.txt']) {
    const r = await pyynto(s);
    assert.equal(r.status, 200, s);
  }
  const etusivu = await pyynto('/');
  assert.match(etusivu.h.get('content-security-policy'), /script-src 'self'; /);
  assert.doesNotMatch(etusivu.h.get('content-security-policy'), /unsafe-inline/);
  assert.equal(etusivu.h.get('x-frame-options'), 'DENY');
  assert.equal(etusivu.h.get('strict-transport-security'), 'max-age=31536000');
  assert.equal((await pyynto('/hallinta')).h.get('x-robots-tag'), 'noindex, nofollow, noarchive');
  assert.equal((await pyynto('/ei-ole')).status, 404);
  assert.equal((await pyynto('/../server.js')).status, 404);
  assert.equal((await pyynto('/lib/varasto.js')).status, 404);
  // Sivuilla ei ole inline-tyylejä eikä -skriptejä (tiukka sisältöpolitiikka estäisi ne)
  const kansio = path.join(__dirname, '..', 'sivusto');
  for (const f of fs.readdirSync(kansio).filter(n => n.endsWith('.html'))) {
    const html = fs.readFileSync(path.join(kansio, f), 'utf8');
    assert.doesNotMatch(html, / style="|<style|<script>|onclick=/, f);
    assert.doesNotMatch(html, /\.apk|\.exe/, f + ': asennustiedostoja ei jaeta sivustolla');
  }
  const ok = await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Matti', sahkoposti: 'matti@example.com', viesti: 'Kysymys', suostumus: true } });
  assert.equal(ok.status, 200);
  assert.equal((await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Matti', sahkoposti: 'x', viesti: 'Kysymys', suostumus: true } })).status, 400);
  assert.equal((await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Matti', sahkoposti: 'matti@example.com', viesti: 'Kysymys' } })).status, 400);
});

test('julkaisupaketti sisältää manifestin ja oikeat tiedostot', async (t) => {
  const kansio = fs.mkdtempSync(path.join(os.tmpdir(), 'akveri-paketti-'));
  t.after(() => fs.rmSync(kansio, { recursive: true, force: true }));
  const tulos = kokoa(kansio);
  const zip = fs.readFileSync(tulos.polku);
  // Luetaan keskushakemisto
  const eocd = zip.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  const maara = zip.readUInt16LE(eocd + 10);
  let p = zip.readUInt32LE(eocd + 16);
  const tiedostot = {};
  for (let i = 0; i < maara; i++) {
    const koko = zip.readUInt32LE(p + 20), nimiPit = zip.readUInt16LE(p + 28), lisa = zip.readUInt16LE(p + 30), komm = zip.readUInt16LE(p + 32), paikka = zip.readUInt32LE(p + 42);
    const nimi = zip.toString('utf8', p + 46, p + 46 + nimiPit);
    const alku = paikka + 30 + zip.readUInt16LE(paikka + 26) + zip.readUInt16LE(paikka + 28);
    tiedostot[nimi] = zlib.inflateRawSync(zip.subarray(alku, alku + koko));
    p += 46 + nimiPit + lisa + komm;
  }
  const manifest = JSON.parse(tiedostot['manifest.json']);
  assert.equal(manifest.tuote, 'akveri-palvelin');
  assert.equal(manifest.versio, require('../package.json').version);
  assert.ok(tiedostot['server.js'] && tiedostot['sivusto/index.html'] && tiedostot['lib/varasto.js']);
  assert.equal(Object.keys(tiedostot).some(n => /testit\/|data\//.test(n)), false);
  for (const [nimi, sha] of Object.entries(manifest.tiedostot)) assert.equal(crypto.createHash('sha256').update(tiedostot[nimi]).digest('hex'), sha, nimi);
});

test('testitili: mittaus ei kuluta krediittiä ja tarkistus näyttää testimittauksen', async (t) => {
  const { pyynto, aika } = await kaynnista(t);
  const s = await kirjauduHallintaan(pyynto, aika);
  const tili = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  assert.equal((await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: tili, body: {} })).status, 402);
  const r = await pyynto(`/api/hallinta/tilit/${tili.tili}/tila`, { method: 'POST', evaste: s.evaste, otsakkeet: s.otsakkeet, body: { testitili: true } });
  assert.equal(r.d.testitili, true);
  const lupa = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: tili, body: {} })).d;
  assert.equal(lupa.testi, true); assert.equal(lupa.saldo, 0);
  await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: tili, body: { tunnus: lupa.tunnus, tarkiste: TARKISTE, yhteenveto: { kunto_pct: 90 } } });
  const v = (await pyynto('/api/v1/vahvistus/' + lupa.tunnus)).d;
  assert.equal(v.tila, 'valmis'); assert.equal(v.testi, true);
  assert.equal((await pyynto(`/api/hallinta/testit/${lupa.tunnus}/hyvita`, { method: 'POST', evaste: s.evaste, otsakkeet: s.otsakkeet, body: { selite: 'x', mitatoi: true } })).status, 409);
  const l2 = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: tili, body: {} })).d;
  await pyynto('/api/v1/testi/peru', { method: 'POST', auth: tili, body: { tunnus: l2.tunnus } });
  assert.equal((await pyynto('/api/v1/saldo', { auth: tili })).d.saldo, 0, 'testiluvan peruminen ei luo krediittiä');
  // Testitilan poisto palauttaa normaalin veloituksen
  await pyynto(`/api/hallinta/tilit/${tili.tili}/tila`, { method: 'POST', evaste: s.evaste, otsakkeet: s.otsakkeet, body: { testitili: false } });
  assert.equal((await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: tili, body: {} })).status, 402);
  assert.equal((await pyynto('/api/hallinta/yhteenveto', { evaste: s.evaste })).d.testimittaukset30, 2);
});

test('vanha sovellusversio ei saa krediittitoimintoja, ja vähimmäisversiota voi nostaa hallinnassa', async (t) => {
  const { pyynto, aika } = await kaynnista(t);
  assert.equal((await pyynto('/api/v1/tili', { method: 'POST', otsakkeet: { ilmanVersiota: true } })).status, 426);
  assert.equal((await pyynto('/api/v1/tili', { method: 'POST', otsakkeet: { 'X-AKVERI-Versio': '1.9.1' } })).status, 426);
  const tili = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  let tila = (await pyynto('/api/v1/tila')).d;
  assert.equal(tila.vahimmaisversio, '2.0.0'); assert.equal(tila.rajapinta, 1);
  const s = await kirjauduHallintaan(pyynto, aika);
  const put = (body) => pyynto('/api/hallinta/asetukset', { method: 'PUT', evaste: s.evaste, otsakkeet: s.otsakkeet, body });
  assert.equal((await put({ vahimmaisversio: '2.1' })).status, 400);
  assert.equal((await put({ vahimmaisversio: '2.1.0', uusinVersio: '2.0.5' })).status, 400, 'uusin ei voi olla vähimmäistä pienempi');
  assert.equal((await put({ vahimmaisversio: '2.1.0', uusinVersio: '2.2.0' })).status, 200);
  tila = (await pyynto('/api/v1/tila')).d;
  assert.equal(tila.uusinVersio, '2.2.0');
  const r = await pyynto('/api/v1/saldo', { auth: tili });
  assert.equal(r.status, 426); assert.match(r.d.virhe, /vähintään 2\.1\.0/);
  assert.equal((await pyynto('/api/v1/saldo', { auth: tili, otsakkeet: { 'X-AKVERI-Versio': '2.1.0' } })).status, 200);
  // Julkinen tarkistus toimii versiosta riippumatta (raportin vastaanottajalla ei ole sovellusta)
  assert.equal((await pyynto('/api/v1/vahvistus/AK0000000000', { otsakkeet: { ilmanVersiota: true } })).status, 200);
});
