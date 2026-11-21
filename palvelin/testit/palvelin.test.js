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
const PAKETTI = 'fi.akveri.app';

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

async function kaynnista(t, { lisaEnv = {}, kello, oletukset = false } = {}) {
  const kansio = fs.mkdtempSync(path.join(os.tmpdir(), 'akveri-palvelin-'));
  if (!oletukset) {
    // Testit käyttävät kiinteitä testituotteita ja yhden krediitin hintoja; oletushinnat testataan erikseen.
    fs.mkdirSync(path.join(kansio, 'data'), { recursive: true });
    fs.writeFileSync(path.join(kansio, 'data', 'asetukset.json'), JSON.stringify({
      tuotteet: [{ tuote: 'akveri_testi_1', krediitit: 1 }, { tuote: 'akveri_testi_5', krediitit: 5 }, { tuote: 'akveri_testi_20', krediitit: 20 }],
      hinnat: { pikatarkastus: 1, kapasiteetti: 1, taysi: 1, ajotesti: 1, pika_ajo: 1, kuormitus: 1, pikalataus: 1, itsepurkaus: 1 }
    }));
  }
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

  const yv = { tyyppi: 'Täysi akkutesti', merkki: 'Tesla', malli: 'Model 3 Long Range', vin: VIN, mittarilukema: 61234, kunto_pct: 93.7, kapasiteetti_kwh: 72.6, mitattu: 1763020000, paattynyt: 1763060000, raporttinumero: '2026-00009', riippumaton: true, suorittaja: 'Autoliike Esimerkki Oy\r\nX-Injektio: 1' };
  const r = await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: a, body: { tunnus: lupa.tunnus, tarkiste: TARKISTE, yhteenveto: yv, versio: '2.0.0' } });
  assert.equal(r.status, 200);
  v = (await pyynto('/api/v1/vahvistus/' + lupa.tunnus.toLowerCase())).d;
  assert.equal(v.tila, 'valmis'); assert.equal(v.kuntoPct, 93.7); assert.equal(v.vin, '5YJ········000123');
  assert.equal(v.tarkiste, TARKISTE.slice(0, 16));
  assert.equal(v.suorittaja, 'Autoliike Esimerkki Oy X-Injektio: 1', 'mittauksen suorittaja näkyy tarkistussivulla yhtenä rivinä');
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
  const a = await pyynto('/api/hallinta/alusta', { method: 'POST', otsakkeet: H, body: { alkutunnus: ALKUTUNNUS, nimi: 'Antero Omistaja', sahkoposti: 'omistaja@akveri.fi', salasana: 'pitka-salasana-123' } });
  assert.equal(a.status, 200);
  assert.equal((await pyynto('/api/hallinta/alusta/vahvista', { method: 'POST', otsakkeet: H, body: { alkutunnus: ALKUTUNNUS, koodi: totp.koodiNyt(a.d.salaisuus, aika.t) } })).status, 200);
  aika.t += 31000;
  const k = await pyynto('/api/hallinta/kirjaudu', { method: 'POST', otsakkeet: H, body: { sahkoposti: 'Omistaja@akveri.fi', salasana: 'pitka-salasana-123', koodi: totp.koodiNyt(a.d.salaisuus, aika.t) } });
  assert.equal(k.status, 200);
  const cookie = k.h.get('set-cookie');
  assert.match(cookie, /HttpOnly; SameSite=Strict; Path=\/; Secure/);
  return { evaste: cookie.split(';')[0], otsakkeet: H, salaisuus: a.d.salaisuus };
}

test('hallinta: käyttöönotto, kirjautuminen ja krediittien käsittely', async (t) => {
  const { pyynto, aika, palvelin } = await kaynnista(t);
  const H = { 'X-AKVERI-Hallinta': '1' };
  assert.equal((await pyynto('/api/hallinta/alusta', { method: 'POST', otsakkeet: H, body: { alkutunnus: 'b'.repeat(48), nimi: 'X Y', sahkoposti: 'x@y.fi', salasana: 'pitka-salasana-123' } })).status, 403);
  const s = await kirjauduHallintaan(pyynto, aika);
  // Uutta tunnusta ei voi luoda, kun tunnus on olemassa
  assert.equal((await pyynto('/api/hallinta/alusta', { method: 'POST', otsakkeet: H, body: { alkutunnus: ALKUTUNNUS, nimi: 'Toinen', sahkoposti: 't@akveri.fi', salasana: 'toinen-salasana-123' } })).status, 409);
  // Sama koodi ei kelpaa toiseen kirjautumiseen
  assert.equal((await pyynto('/api/hallinta/kirjaudu', { method: 'POST', otsakkeet: H, body: { sahkoposti: 'omistaja@akveri.fi', salasana: 'pitka-salasana-123', koodi: totp.koodiNyt(s.salaisuus, aika.t) } })).status, 401);
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
  assert.equal((await put({ playLinkki: 'https://play.google.com/store/apps/details?id=fi.akveri.app' })).status, 200);
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

test('hallinnan käyttäjät: kutsu ylläpitokomennolla, käyttöönotto, kirjautuminen ja poisto katkaisee istunnon', async (t) => {
  const { pyynto, aika, palvelin } = await kaynnista(t);
  const omistaja = await kirjauduHallintaan(pyynto, aika);
  const { suorita } = require('../yllapito');
  const env = { DB_DIR: palvelin.varasto.kansio, JULKINEN_OSOITE: 'https://akveri.fi' };
  const rivit = []; const ulos = (x) => rivit.push(x);
  assert.throws(() => suorita(['lisaa-kayttaja', 'ei-posti', 'Matti'], { env, ulos }), /Sähköposti/);
  suorita(['lisaa-kayttaja', 'matti@akveri.fi', 'Matti Mittaaja'], { env, ulos, nyt: () => aika.t });
  const kutsu = /#kutsu=([A-Za-z0-9_-]{43})$/.exec(rivit.pop())[1];
  const H = { 'X-AKVERI-Hallinta': '1' };
  assert.deepEqual((await pyynto('/api/hallinta/kutsu', { method: 'POST', otsakkeet: H, body: { kutsu } })).d, { nimi: 'Matti Mittaaja', sahkoposti: 'matti@akveri.fi' });
  const a = await pyynto('/api/hallinta/alusta', { method: 'POST', otsakkeet: H, body: { kutsu, salasana: 'mattin-salasana-1' } });
  assert.equal(a.status, 200);
  assert.equal((await pyynto('/api/hallinta/alusta/vahvista', { method: 'POST', otsakkeet: H, body: { kutsu, koodi: totp.koodiNyt(a.d.salaisuus, aika.t) } })).status, 200);
  assert.equal((await pyynto('/api/hallinta/kutsu', { method: 'POST', otsakkeet: H, body: { kutsu } })).status, 404, 'kutsu on kertakäyttöinen');
  aika.t += 31000;
  const k = await pyynto('/api/hallinta/kirjaudu', { method: 'POST', otsakkeet: H, body: { sahkoposti: 'matti@akveri.fi', salasana: 'mattin-salasana-1', koodi: totp.koodiNyt(a.d.salaisuus, aika.t) } });
  assert.equal(k.status, 200);
  const matti = k.h.get('set-cookie').split(';')[0];
  assert.equal((await pyynto('/api/hallinta/yhteenveto', { evaste: matti })).status, 200);
  const lista = JSON.parse((() => { suorita(['lista-kayttajat'], { env, ulos }); return rivit.pop(); })());
  assert.equal(lista.kayttajat.length, 2);
  suorita(['poista-kayttaja', 'matti@akveri.fi'], { env, ulos });
  assert.equal((await pyynto('/api/hallinta/yhteenveto', { evaste: matti })).status, 401, 'poisto katkaisee kirjautumisen heti');
  assert.equal((await pyynto('/api/hallinta/yhteenveto', { evaste: omistaja.evaste })).status, 200);
  assert.throws(() => suorita(['poista-kayttaja', 'omistaja@akveri.fi'], { env, ulos }), /Viimeistä käyttäjää/);
  // Vanhentunut kutsu ei kelpaa
  suorita(['lisaa-kayttaja', 'liisa@akveri.fi', 'Liisa'], { env, ulos, nyt: () => aika.t });
  const vanha = /#kutsu=(.+)$/.exec(rivit.pop())[1];
  aika.t += 25 * 3600000;
  assert.equal((await pyynto('/api/hallinta/kutsu', { method: 'POST', otsakkeet: H, body: { kutsu: vanha } })).status, 404);
});

test('tietosuoja: tilin ja raportin tietojen poisto sekä säilytysajat', async (t) => {
  const { pyynto, aika, palvelin } = await kaynnista(t);
  const s = await kirjauduHallintaan(pyynto, aika);
  const H = s.otsakkeet;
  const tili = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  await pyynto(`/api/hallinta/tilit/${tili.tili}/krediitit`, { method: 'POST', evaste: s.evaste, otsakkeet: H, body: { muutos: 2, selite: 'Testi' } });
  const l1 = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: tili, body: {} })).d;
  await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: tili, body: { tunnus: l1.tunnus, tarkiste: TARKISTE, yhteenveto: { vin: VIN, kunto_pct: 90 } } });
  const l2 = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: tili, body: {} })).d;
  // Raportin tietojen poisto
  assert.equal((await pyynto(`/api/hallinta/testit/${l1.tunnus}/poista-tiedot`, { method: 'POST', evaste: s.evaste, otsakkeet: H, body: {} })).status, 400, 'syy vaaditaan');
  await pyynto(`/api/hallinta/testit/${l1.tunnus}/poista-tiedot`, { method: 'POST', evaste: s.evaste, otsakkeet: H, body: { syy: 'Rekisteröidyn pyyntö' } });
  const v = (await pyynto('/api/v1/vahvistus/' + l1.tunnus)).d;
  assert.equal(v.tila, 'poistettu'); assert.equal(v.kuntoPct, undefined);
  assert.equal(JSON.stringify(palvelin.varasto.get('testit')[l1.tunnus]).includes('000123'), false, 'valmistenumero poistettu');
  // Tilin poisto vaatii vahvistuksen; avoin lupa perutaan ja tili lakkaa toimimasta
  assert.equal((await pyynto(`/api/hallinta/tilit/${tili.tili}`, { method: 'DELETE', evaste: s.evaste, otsakkeet: H, body: { vahvista: 'väärä' } })).status, 400);
  assert.equal((await pyynto(`/api/hallinta/tilit/${tili.tili}`, { method: 'DELETE', evaste: s.evaste, otsakkeet: H, body: { vahvista: tili.tili } })).status, 200);
  assert.equal((await pyynto('/api/v1/saldo', { auth: tili })).status, 401);
  assert.equal((await pyynto('/api/v1/vahvistus/' + l2.tunnus)).d.tila, 'peruttu');
  assert.ok(palvelin.varasto.kirjanpito({ tili: tili.tili }).length >= 2, 'kirjanpito säilyy (kirjanpitolaki)');
  // Säilytysajat: viestit 2 vuotta
  await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Matti', sahkoposti: 'matti@example.com', viesti: 'Kysymys', suostumus: true } });
  assert.deepEqual(palvelin.hallinta.sailytysajat(), { viestit: 0, raportit: 0, pyynnot: 0 });
  aika.t += 2 * 366 * 86400000;
  assert.equal(palvelin.hallinta.sailytysajat().viestit, 1, 'yli kaksi vuotta vanha viesti poistuu');
  assert.equal(Object.keys(palvelin.varasto.get('viestit')).length, 0);
});

test('etusivu: kolme kieltä samasta lähteestä, kielivalinta ja ei teknistä sanastoa', async (t) => {
  const etusivu = require('../etusivu');
  for (const s of etusivu.kaikki()) assert.equal(fs.readFileSync(path.join(__dirname, '..', 'sivusto', s.tiedosto), 'utf8'), s.sisalto, `${s.tiedosto} on ajan tasalla (aja node palvelin/etusivu.js)`);
  const { pyynto } = await kaynnista(t);
  for (const [polku, kieli] of [['/', 'fi'], ['/en', 'en'], ['/sv', 'sv']]) {
    const r = await pyynto(polku);
    assert.equal(r.status, 200, polku);
    assert.match(r.d, new RegExp(`<html lang="${kieli}">`));
    for (const k of ['/', '/en', '/sv']) assert.ok(r.d.includes(`href="${k}"`), `${polku}: linkki kieleen ${k}`);
    assert.doesNotMatch(r.d, /SOH|kennoj|akunhallin|diagnostiikka|BMS|style="/i, `${polku}: ei teknistä sanastoa eikä inline-tyylejä`);
    assert.match(r.d, /data-play/);
    assert.doesNotMatch(r.d, /Tulossa|Coming soon|Kommer snart|Ilmoitamme julkaisusta/i, `${polku}: ei "tulossa"-viestejä`);
  }
  const js = fs.readFileSync(path.join(__dirname, '..', 'sivusto', 'sivusto.js'), 'utf8');
  assert.doesNotMatch(js, /Tulossa|Coming soon|Kommer snart|aria-disabled/, 'sivusto.js ei näytä "tulossa"-tilaa eikä himmennä painikkeita');
});

test('tietosuoja ja anonyymi aineisto: oma raportti ja tili pois, tiedot ladattavissa, tilasto ilman tunnisteita, tyyppi tarkistetaan', async (t) => {
  const { pyynto, g, palvelin, aika } = await kaynnista(t);
  const V3 = { 'X-AKVERI-Versio': '2.0.3' };
  const a = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  const b = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  osto(g, 'tok-a', 'akveri_testi_5', a.tili);
  await pyynto('/api/v1/osto', { method: 'POST', auth: a, body: { tuote: 'akveri_testi_5', ostotunnus: 'tok-a' } });
  const rekisteroi = async (tyyppi, raporttiTyyppi, suorittaja = 'Matti Mittaaja') => {
    const l = (await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, otsakkeet: V3, body: { versio: '2.0.3', tyyppi } })).d;
    const yv = { tyyppi: 'Testi', mittaustyyppi: raporttiTyyppi, merkki: 'Tesla', malli: 'Model 3', vin: VIN, mittarilukema: 61234, kunto_pct: 93.7,
      kapasiteetti_kwh: 72.6, mitattu: 1763020000, raporttinumero: '2026-00010', suorittaja,
      anonyymi: { kemia: 'NCA', kennoryhmat: 96, vuosimalli: 2021, jannite_ero_mv: 12, lampo_min_c: 18, tunniste: 'EI SAA TALLENTUA', vin: VIN } };
    const r = await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: a, otsakkeet: V3, body: { tunnus: l.tunnus, tarkiste: TARKISTE, yhteenveto: yv, versio: '2.0.3' } });
    return { l, r };
  };
  // Mittaustyypin on vastattava lupaa (ei halvempaa lupaa kalliimmalle mittaukselle)
  const vaara = await rekisteroi('pikatarkastus', 'taysi');
  assert.equal(vaara.r.status, 409, 'eri mittaustyyppi hylätään');
  const ilmanTyyppia = await pyynto('/api/v1/testi/raportti', { method: 'POST', auth: a, otsakkeet: V3, body: { tunnus: vaara.l.tunnus, tarkiste: TARKISTE, yhteenveto: { merkki: 'Tesla' }, versio: '2.0.3' } });
  assert.equal(ilmanTyyppia.status, 409, 'uusi sovellus ei voi jättää tyyppiä pois');
  const ok1 = await rekisteroi('taysi', 'taysi');
  assert.equal(ok1.r.status, 200);
  const ok2 = await rekisteroi('kapasiteetti', 'kapasiteetti', 'Toinen Henkilö');
  assert.equal(ok2.r.status, 200);
  // Anonyymi aineisto: ei tunnisteita, pyöristetty lukema ja kuukausi
  const tl = palvelin.varasto.get('tilasto').rivit;
  assert.equal(tl.length, 2);
  const json = JSON.stringify(tl);
  for (const kielletty of [VIN, VIN.slice(-6), ok1.l.tunnus, a.tili, 'Matti Mittaaja', '2026-00010', 'EI SAA TALLENTUA', '61234', 'tunniste']) assert.ok(!json.includes(kielletty), kielletty);
  assert.equal(tl[0].mittarilukema_tkm, 61); assert.match(tl[0].kuukausi, /^\d{4}-\d{2}$/); assert.equal(tl[0].kemia, 'NCA');
  // Tilin tiedot (oikeus saada pääsy tietoihin)
  const tiedot = (await pyynto('/api/v1/tili/tiedot', { method: 'POST', auth: a, body: {} })).d;
  assert.equal(tiedot.tili.tunnus, a.tili); assert.equal(tiedot.testit.length, 3); assert.ok(tiedot.kirjanpito.length >= 3);
  assert.ok(!JSON.stringify(tiedot).includes(VIN), 'koko valmistenumeroa ei anneta');
  // Oma raportti pois palvelusta; toisen tilin raporttia ei voi poistaa
  assert.equal((await pyynto('/api/v1/testi/poista-tiedot', { method: 'POST', auth: b, body: { tunnus: ok1.l.tunnus } })).status, 404);
  assert.equal((await pyynto('/api/v1/testi/poista-tiedot', { method: 'POST', auth: a, body: { tunnus: ok1.l.tunnus } })).status, 200);
  assert.equal((await pyynto('/api/v1/vahvistus/' + ok1.l.tunnus)).d.tila, 'poistettu');
  // Hallinta: suorittajan nimen poisto, tilin tiedot, yhteydenotot sähköpostilla, anonyymi aineisto
  const s = await kirjauduHallintaan(pyynto, aika);
  const H = { evaste: s.evaste, otsakkeet: s.otsakkeet };
  assert.equal((await pyynto(`/api/hallinta/testit/${ok2.l.tunnus}/poista-suorittaja`, { method: 'POST', ...H, body: {} })).status, 200);
  const v2 = (await pyynto('/api/v1/vahvistus/' + ok2.l.tunnus)).d;
  assert.equal(v2.tila, 'valmis'); assert.equal(v2.suorittaja, '');
  assert.equal((await pyynto(`/api/hallinta/tilit/${a.tili}/tiedot`, H)).d.tili.tunnus, a.tili);
  await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Anna', sahkoposti: 'Anna@Example.com', viesti: 'Poistakaa tietoni', suostumus: true } });
  await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Bo', sahkoposti: 'bo@example.com', viesti: 'Hej', suostumus: true } });
  assert.equal((await pyynto('/api/hallinta/tietosuoja/viestit?sahkoposti=anna@example.com', H)).d.viestit.length, 1);
  assert.equal((await pyynto('/api/hallinta/tietosuoja/viestit?sahkoposti=anna@example.com', { method: 'DELETE', ...H })).d.poistettu, 1);
  assert.equal(Object.keys(palvelin.varasto.get('viestit')).length, 1, 'muut viestit säilyvät');
  assert.equal((await pyynto('/api/hallinta/tilasto', H)).d.rivit.length, 2);
  assert.equal((await pyynto('/api/hallinta/yhteenveto', H)).d.tilastoRiveja, 2);
  // Tilin poisto sovelluksesta raporttien kanssa: tili lakkaa toimimasta, kirjanpito ja anonyymi aineisto säilyvät
  assert.equal((await pyynto('/api/v1/tili/poista', { method: 'POST', auth: a, body: {} })).status, 400, 'vaatii vahvistuksen');
  const pois = (await pyynto('/api/v1/tili/poista', { method: 'POST', auth: a, body: { vahvista: true, raportit: true } })).d;
  assert.equal(pois.raportteja, 1);
  assert.equal((await pyynto('/api/v1/saldo', { auth: a })).status, 401);
  assert.equal((await pyynto('/api/v1/vahvistus/' + ok2.l.tunnus)).d.tila, 'poistettu');
  assert.ok(palvelin.varasto.kirjanpito({ tili: a.tili }).length >= 3, 'kirjanpito säilyy');
  assert.equal(palvelin.varasto.get('tilasto').rivit.length, 2, 'anonyymi aineisto säilyy');
});

test('alasivut kolmella kielellä: ajan tasalla, reitit, kielivalinta, ei suomea englannin- ja ruotsinkielisillä sivuilla', async (t) => {
  const sivut = require('../sivut');
  for (const s of sivut.kaikki()) assert.equal(fs.readFileSync(path.join(__dirname, '..', 'sivusto', s.tiedosto), 'utf8'), s.sisalto, `${s.tiedosto} on ajan tasalla (aja node palvelin/sivut.js)`);
  const { pyynto, palvelin } = await kaynnista(t);
  const SUOMEA = /\b(ja|tai|Tarkista|raportti\w*|mittau\w*|Yhteystiedot|Käyttöehdot|Tietosuoja\w*|sähköposti|Lähetä|Viesti|Kysymys)\b/;
  for (const s of sivut.kaikki()) {
    const r = await pyynto(s.polku);
    assert.equal(r.status, 200, s.polku);
    assert.equal(r.d, s.sisalto, `${s.polku} → ${s.tiedosto}`);
    assert.match(r.d, new RegExp(`<html lang="${s.kieli}">`));
    for (const k of ['fi', 'en', 'sv']) assert.ok(r.d.includes(`hreflang="${k}"`), `${s.polku}: kieliversio ${k}`);
    assert.doesNotMatch(r.d, /style="|<script>/, `${s.polku}: ei inline-tyylejä eikä -skriptejä`);
    if (s.kieli !== 'fi') {
      const naky = r.d.replace(/<head>[\s\S]*?<\/head>/, '').replace(/<[^>]+>/g, ' ').replace(/\[[^\]]+\]/g, '').replace(/tietosuoja\.fi/g, '');
      assert.doesNotMatch(naky, SUOMEA, `${s.polku}: näkyvä teksti on käännetty`);
      assert.ok(!/data-asiakirja/.test(r.d), `${s.polku}: hallinnan suomenkielinen teksti ei korvaa käännöstä`);
    }
  }
  // Ehdot vastaavat mittaustyyppikohtaista hinnoittelua
  for (const k of ['fi', 'en', 'sv']) assert.doesNotMatch(sivut.TEKSTIT.ehdot[k].teksti, /Yksi krediitti|One credit|En kredit/);
  assert.match(sivut.TEKSTIT.ehdot.fi.teksti, /riippuu mittaustyypistä/);
  // Tarkistuksen ja lomakkeen skriptit tuntevat kaikki kielet
  const tj = fs.readFileSync(path.join(__dirname, '..', 'sivusto', 'tarkista.js'), 'utf8');
  for (const k of ['fi', 'en', 'sv']) assert.match(tj, new RegExp(`\\n    ${k}: \\{`));
  const sj = fs.readFileSync(path.join(__dirname, '..', 'sivusto', 'sivusto.js'), 'utf8');
  assert.match(sj, /kieli: KIELI/);
  // Yhteydenoton kieli tallentuu, jotta vastaus osataan kirjoittaa samalla kielellä
  const v = await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Anna', sahkoposti: 'anna@example.com', aihe: 'Kysymys', viesti: 'Hello', suostumus: true, kieli: 'en' } });
  assert.equal(v.status, 200);
  const w = await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Bo', sahkoposti: 'bo@example.com', viesti: 'Hej', suostumus: true, kieli: '<x>' } });
  assert.equal(w.status, 200);
  const kielet = Object.values(palvelin.varasto.get('viestit')).map(x => x.nimi + ':' + x.kieli).sort();
  assert.deepEqual(kielet, ['Anna:en', 'Bo:fi'], 'tuntematon kieli tallentuu suomeksi');
});

test('huoltotila: vain sivusto tai sivusto ja sovelluksen palvelu; hallinta, ehdot ja kirjautunut käyttäjä toimivat', async (t) => {
  const { pyynto, aika } = await kaynnista(t);
  const s = await kirjauduHallintaan(pyynto, aika);
  const put = (huoltotila) => pyynto('/api/hallinta/asetukset', { method: 'PUT', evaste: s.evaste, otsakkeet: s.otsakkeet, body: { huoltotila } });
  const tili = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  assert.equal((await put({ tila: 'jotain' })).status, 400);
  assert.equal((await put({ tila: 'sivusto', viesti: 'x'.repeat(501) })).status, 400);
  const r = await put({ tila: 'sivusto', viesti: 'Huolto <klo 22>' });
  assert.equal(r.status, 200); assert.equal(r.d.huoltotila.tila, 'sivusto');
  for (const sivu of ['/', '/en', '/sv', '/tarkista', '/v/AK7H2QKM4XPC', '/yhteystiedot']) {
    const v = await pyynto(sivu);
    assert.equal(v.status, 503, sivu);
    assert.match(v.d, /Huolto &lt;klo 22&gt;/);
  }
  for (const sivu of ['/ehdot', '/tietosuoja', '/en/terms', '/en/privacy', '/sv/villkor', '/sv/dataskydd', '/hallinta', '/sivusto.css', '/logo.svg']) assert.equal((await pyynto(sivu)).status, 200, `${sivu} toimii huollon aikana`);
  for (const sivu of ['/en/verify', '/sv/kontakt']) assert.equal((await pyynto(sivu)).status, 503, sivu);
  assert.equal((await pyynto('/', { evaste: s.evaste })).status, 200, 'kirjautunut näkee sivuston');
  assert.equal((await pyynto('/api/v1/saldo', { auth: tili })).status, 200, 'sovellus toimii, kun vain sivusto on huollossa');
  assert.equal((await put({ tila: 'kaikki', viesti: 'Huolto' })).status, 200);
  const sov = await pyynto('/api/v1/saldo', { auth: tili });
  assert.equal(sov.status, 503); assert.equal(sov.d.huolto, true); assert.match(sov.d.virhe, /huollossa/);
  assert.equal((await pyynto('/api/hallinta/yhteenveto', { evaste: s.evaste })).status, 200, 'hallinta toimii');
  assert.equal((await put({ tila: 'pois', viesti: '' })).status, 200);
  assert.equal((await pyynto('/')).status, 200);
  assert.equal((await pyynto('/api/v1/saldo', { auth: tili })).status, 200);
});

test('mittausten hinnat: hallinnassa testityypeittäin, sovellus saa ne saldon mukana, veloitus ja palautus hinnan mukaan', async (t) => {
  const { pyynto, g, aika } = await kaynnista(t);
  const s = await kirjauduHallintaan(pyynto, aika);
  const put = (body) => pyynto('/api/hallinta/asetukset', { method: 'PUT', evaste: s.evaste, otsakkeet: s.otsakkeet, body });
  const a = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  assert.equal((await pyynto('/api/v1/saldo', { auth: a })).d.hinnat.taysi, 1, 'oletushinta 1');
  assert.equal((await put({ hinnat: { taysi: 0 } })).status, 400);
  assert.equal((await put({ hinnat: { taysi: 1.5 } })).status, 400);
  const r = await put({ hinnat: { taysi: 3, pikatarkastus: 1 } });
  assert.equal(r.status, 200); assert.equal(r.d.hinnat.taysi, 3); assert.equal(r.d.hinnat.kapasiteetti, 1);
  assert.equal((await pyynto('/api/v1/saldo', { auth: a })).d.hinnat.taysi, 3, 'muutos näkyy sovellukselle heti');
  assert.equal((await pyynto('/api/v1/tuotteet')).d.hinnat.taysi, 3);
  osto(g, 'tok-h', 'akveri_testi_5', a.tili);
  assert.equal((await pyynto('/api/v1/osto', { method: 'POST', auth: a, body: { tuote: 'akveri_testi_5', ostotunnus: 'tok-h' } })).d.saldo, 5);
  assert.equal((await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, body: { tyyppi: 'tuntematon' } })).status, 400);
  const v = await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, body: { tyyppi: 'taysi' } });
  assert.equal(v.status, 200); assert.equal(v.d.hinta, 3); assert.equal(v.d.saldo, 2);
  const liian = await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, body: { tyyppi: 'taysi' } });
  assert.equal(liian.status, 402); assert.match(liian.d.virhe, /3 krediittiä/);
  assert.equal((await pyynto('/api/v1/testi/peru', { method: 'POST', auth: a, body: { tunnus: v.d.tunnus, syy: 'keskeytyi' } })).d.saldo, 5, 'peruminen palauttaa koko hinnan');
  const p = await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, body: { tyyppi: 'pikatarkastus' } });
  assert.equal(p.d.hinta, 1); assert.equal(p.d.saldo, 4);
  assert.equal((await put({ hinnat: { pikatarkastus: 2 } })).status, 200);
  assert.equal((await pyynto('/api/v1/testi/peru', { method: 'POST', auth: a, body: { tunnus: p.d.tunnus } })).d.saldo, 5, 'palautus aloitushetken hinnalla');
  assert.equal((await pyynto('/api/v1/testi/varaa', { method: 'POST', auth: a, body: {} })).d.hinta, 1, 'vanha sovellus ilman tyyppiä: oletushinta');
});

// Pieni SMTP-palvelin testeihin: kirjaa komennot ja viestit.
function smtpPalvelin() {
  const net = require('net');
  const viestit = []; const komennot = [];
  const s = net.createServer((c) => {
    c.setEncoding('utf8'); c.write('220 testi ESMTP\r\n');
    let data = false, puskuri = '', nyky = {};
    c.on('data', (d) => {
      puskuri += d;
      let i;
      while ((i = puskuri.indexOf('\r\n')) >= 0) {
        const rivi = puskuri.slice(0, i); puskuri = puskuri.slice(i + 2);
        if (data) { if (rivi === '.') { data = false; viestit.push(nyky); nyky = {}; c.write('250 ok\r\n'); } else nyky.data = (nyky.data || '') + rivi + '\n'; continue; }
        komennot.push(rivi);
        if (/^EHLO/.test(rivi)) c.write('250-testi\r\n250 AUTH PLAIN LOGIN\r\n');
        else if (/^AUTH PLAIN /.test(rivi)) c.write(Buffer.from(rivi.slice(11), 'base64').toString() === '\0posti\0salainen' ? '235 ok\r\n' : '535 väärä\r\n');
        else if (/^MAIL FROM:/.test(rivi)) { nyky.from = rivi; c.write('250 ok\r\n'); }
        else if (/^RCPT TO:/.test(rivi)) { nyky.to = rivi; c.write('250 ok\r\n'); }
        else if (rivi === 'DATA') { data = true; c.write('354 jatka\r\n'); }
        else if (rivi === 'QUIT') { c.write('221 hei\r\n'); c.end(); }
        else c.write('500 ?\r\n');
      }
    });
  });
  return new Promise(r => s.listen(0, '127.0.0.1', () => r({ portti: s.address().port, viestit, komennot, sulje: () => s.close() })));
}

test('sähköposti: ilmoitukset noreply-osoitteesta vastaanottajalle, vastaus info-osoitteesta, salasanaa ei palauteta', async (t) => {
  const smtp = await smtpPalvelin(); t.after(smtp.sulje);
  const { pyynto, aika } = await kaynnista(t);
  const s = await kirjauduHallintaan(pyynto, aika);
  const put = (body) => pyynto('/api/hallinta/asetukset', { method: 'PUT', evaste: s.evaste, otsakkeet: s.otsakkeet, body });
  const posti = { host: '127.0.0.1', port: smtp.portti, user: 'posti', pass: 'salainen', lahettaja: 'AKVERI <noreply@akveri.fi>', lahettajaOmat: 'AKVERI <info@akveri.fi>', vastaanottaja: 'omistaja@akveri.fi' };
  assert.equal((await put({ posti: { ...posti, lahettaja: 'ei osoite' } })).status, 400);
  assert.equal((await put({ posti: { ...posti, vastaanottaja: '' } })).status, 400);
  const r = await put({ posti });
  assert.equal(r.status, 200); assert.equal(r.d.posti.salasanaAsetettu, true); assert.equal(r.d.posti.pass, undefined);
  assert.ok(!JSON.stringify((await pyynto('/api/hallinta/asetukset', { evaste: s.evaste })).d).includes('salainen'), 'salasana ei näy selaimelle');
  assert.equal((await put({ posti: { ...posti, pass: '' } })).status, 200, 'tyhjä salasana säilyttää tallennetun');
  assert.equal((await pyynto('/api/hallinta/posti/testi', { method: 'POST', evaste: s.evaste, otsakkeet: s.otsakkeet })).status, 200);
  assert.equal(smtp.viestit.length, 1);
  assert.match(smtp.viestit[0].from, /<noreply@akveri\.fi>/); assert.match(smtp.viestit[0].to, /<omistaja@akveri\.fi>/);
  assert.match(smtp.viestit[0].data, /Reply-To: info@akveri\.fi/);
  // yhteydenotto → ilmoitus omistajalle
  const v = await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Olli Ostaja', sahkoposti: 'olli@esim.fi', aihe: 'Raportti', viesti: 'Kysymys\nraportista', suostumus: true } });
  assert.equal(v.status, 200);
  for (let i = 0; i < 50 && smtp.viestit.length < 2; i++) await new Promise(r => setTimeout(r, 20));
  assert.equal(smtp.viestit.length, 2); assert.match(smtp.viestit[1].data, /Subject: AKVERI: uusi yhteydenotto \(Raportti\)/);
  assert.match(Buffer.from(smtp.viestit[1].data.split('\n\n')[1].replace(/\n/g, ''), 'base64').toString(), /Olli Ostaja <olli@esim\.fi>/);
  // vastaus info-osoitteesta
  const id = (await pyynto('/api/hallinta/viestit', { evaste: s.evaste })).d.viestit[0].id;
  assert.equal((await pyynto(`/api/hallinta/viestit/${id}/vastaa`, { method: 'POST', evaste: s.evaste, otsakkeet: s.otsakkeet, body: { teksti: ' ' } })).status, 400);
  const va = await pyynto(`/api/hallinta/viestit/${id}/vastaa`, { method: 'POST', evaste: s.evaste, otsakkeet: s.otsakkeet, body: { teksti: 'Hei Olli,\n\nkiitos.' } });
  assert.equal(va.status, 200, JSON.stringify(va.d));
  assert.match(smtp.viestit[2].from, /<info@akveri\.fi>/); assert.match(smtp.viestit[2].to, /<olli@esim\.fi>/);
  assert.equal((await pyynto('/api/hallinta/viestit', { evaste: s.evaste })).d.viestit[0].vastaukset.length, 1);
  assert.equal((await pyynto('/api/sivusto/tiedot')).d.yhteystiedot.sahkoposti, 'info@akveri.fi', 'julkinen osoite on info');
  assert.ok(smtp.komennot.some(k => k.startsWith('AUTH PLAIN')));
});

test('sähköposti: otsakkeisiin ei voi syöttää rivinvaihtoja', () => {
  const posti = require('../lib/posti');
  assert.throws(() => posti.rakennaViesti({ from: 'a@b.fi', to: 'c@d.fi\r\nBcc: x@y.fi', subject: 'x', text: 'y' }), /rivinvaihto/);
  assert.match(posti.rakennaViesti({ from: 'AKVERI <a@b.fi>', to: 'c@d.fi', subject: 'Hei', text: 'x' }), /^From: AKVERI <a@b\.fi>\r\n/);
});

test('hallinnan sähköposti: ohje verkkotunnuksen omalle sähköpostille sekä lähetyspalvelun valinta (sama kuin vuoropiste.fi:ssä)', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'sivusto', 'hallinta.html'), 'utf8');
  const js = fs.readFileSync(path.join(__dirname, '..', 'sivusto', 'hallinta.js'), 'utf8');
  assert.match(html, /class="posti-ohje"/);
  assert.match(html, /SPF-tietue/);
  assert.match(html, /vain sähköpostin ohjaus/);
  assert.match(html, /id="po-vastaus"/);
  assert.match(html, /<select id="po-palvelu">.*webhotelli.*gmail.*muu/s);
  assert.doesNotMatch(html + js, /brevo/i);
  assert.match(js, /hostingpalvelu/);
  assert.match(js, /smtp\.gmail\.com/);
  // Sama ohjeteksti molemmissa hallinnoissa (verkkotunnusta lukuun ottamatta)
  const vp = path.join(__dirname, '..', '..', '..', 'vuoro', 'myyja-tyokalut', 'vuoropiste-sivusto', 'sivusto', 'yllapito.html');
  if (fs.existsSync(vp)) {
    const ohje = (s) => (/<details class="posti-ohje">[\s\S]*?<\/details>/.exec(s) || [''])[0].replace(/akveri\.fi|vuoropiste\.fi/g, 'X').replace(/\s+/g, ' ');
    assert.equal(ohje(html), ohje(fs.readFileSync(vp, 'utf8')));
  }
});

// Paikallinen SMTP-palvelin (127.0.0.1, salaamaton vain testissä): AUTH PLAIN/LOGIN, hylkää vieraan lähettäjän.
function smtpKorvike(t, { kayttaja = 'noreply@akveri.fi', salasana = 'postin-salasana' } = {}) {
  const net = require('net');
  const viestit = [];
  const palvelin = net.createServer((s) => {
    let puskuri = '', data = null, auth = false, tila = '';
    const w = (r) => s.write(r + '\r\n');
    w('220 testi ESMTP');
    s.on('data', (d) => {
      puskuri += d.toString();
      let i;
      while ((i = puskuri.indexOf('\r\n')) >= 0) {
        const l = puskuri.slice(0, i); puskuri = puskuri.slice(i + 2);
        if (data !== null) { if (l === '.') { viestit.push(data); data = null; w('250 OK'); } else data += l + '\n'; continue; }
        if (tila === 'u') { tila = Buffer.from(l, 'base64').toString() === kayttaja ? 'p' : 'x'; w('334 UGFzc3dvcmQ6'); continue; }
        if (tila === 'p' || tila === 'x') { auth = tila === 'p' && Buffer.from(l, 'base64').toString() === salasana; tila = ''; w(auth ? '235 OK' : '535 5.7.8 Authentication failed'); continue; }
        const k = l.slice(0, 4).toUpperCase();
        if (k === 'EHLO') { s.write('250-testi\r\n250 AUTH LOGIN\r\n'); }
        else if (k === 'AUTH') { tila = 'u'; w('334 VXNlcm5hbWU6'); }
        else if (k === 'MAIL') { if (!auth) w('530 Authentication required'); else if (!l.includes('<' + kayttaja + '>')) w('553 5.7.1 Sender address rejected'); else w('250 OK'); }
        else if (k === 'RCPT') w('250 OK');
        else if (k === 'DATA') { data = ''; w('354 Go'); }
        else if (k === 'QUIT') { w('221 Bye'); s.end(); }
        else w('250 OK');
      }
    });
    s.on('error', () => {});
  });
  return new Promise((ok) => palvelin.listen(0, '127.0.0.1', () => { t.after(() => palvelin.close()); ok({ portti: palvelin.address().port, viestit }); }));
}

test('sähköposti: verkkotunnuksen oma postilaatikko toimii, ja virheistä kerrotaan selkeästi', async (t) => {
  const smtp = await smtpKorvike(t);
  const { pyynto, aika } = await kaynnista(t);
  const s = await kirjauduHallintaan(pyynto, aika);
  const put = (body) => pyynto('/api/hallinta/asetukset', { method: 'PUT', evaste: s.evaste, otsakkeet: s.otsakkeet, body });
  const testi = () => pyynto('/api/hallinta/posti/testi', { method: 'POST', evaste: s.evaste, otsakkeet: s.otsakkeet, body: {} });
  const asetus = { host: '127.0.0.1', port: smtp.portti, secure: false, user: 'noreply@akveri.fi', pass: 'postin-salasana', lahettaja: 'AKVERI <noreply@akveri.fi>', lahettajaOmat: 'AKVERI <noreply@akveri.fi>', vastaanottaja: 'omistaja@example.com' };
  assert.equal((await put({ posti: asetus })).status, 200);
  const ok = await testi();
  assert.equal(ok.status, 200, JSON.stringify(ok.d));
  assert.match(ok.d.viesti, /omistaja@example\.com/);
  assert.equal(smtp.viestit.length, 1);
  assert.match(smtp.viestit[0], /^From: AKVERI <noreply@akveri\.fi>$/m);
  // Gmail-tapa: lähettäjä on Gmail-osoite, vastaukset ohjataan verkkotunnuksen osoitteeseen
  assert.equal((await put({ posti: { ...asetus, vastausosoite: 'info@akveri.fi' } })).status, 200);
  assert.equal((await pyynto('/api/hallinta/asetukset', { evaste: s.evaste, otsakkeet: s.otsakkeet })).d.posti.vastausosoite, 'info@akveri.fi');
  assert.equal((await testi()).status, 200);
  assert.match(smtp.viestit[1], /^Reply-To: info@akveri\.fi$/m);
  assert.equal((await put({ posti: { ...asetus, vastausosoite: 'ei osoite' } })).status, 400);
  assert.equal((await put({ posti: asetus })).status, 200);
  smtp.viestit.length = 1;
  // Uusi yhteydenotto lähettää ilmoituksen omistajalle
  await pyynto('/api/sivusto/viesti', { method: 'POST', body: { nimi: 'Matti', sahkoposti: 'matti@example.com', viesti: 'Kysymys akusta', suostumus: true } });
  for (let i = 0; i < 50 && smtp.viestit.length < 2; i++) await new Promise((r) => setTimeout(r, 20));
  assert.equal(smtp.viestit.length, 2, 'yhteydenotosta lähtee ilmoitus');
  // Väärä salasana
  assert.equal((await put({ posti: { ...asetus, pass: 'vaara' } })).status, 200);
  const v1 = await testi();
  assert.equal(v1.status, 502); assert.match(v1.d.virhe, /^Kirjautuminen epäonnistui\. Tarkista käyttäjätunnus \(koko sähköpostiosoite\) ja salasana\./);
  // Lähettäjä eri kuin käyttäjätunnus
  assert.equal((await put({ posti: { ...asetus, lahettaja: 'AKVERI <info@akveri.fi>' } })).status, 200);
  const v2 = await testi();
  assert.equal(v2.status, 502); assert.match(v2.d.virhe, /lähettäjää info@akveri\.fi\. Käytä lähettäjänä samaa osoitetta kuin käyttäjätunnus/);
  // Väärä portti
  assert.equal((await put({ posti: { ...asetus, port: 1 } })).status, 200);
  const v3 = await testi();
  assert.equal(v3.status, 502); assert.match(v3.d.virhe, /ei saatu yhteyttä porttiin 1\. Tarkista portti/);
});

test('oletushinnat ja krediittipaketit: lyhyet testit 1, ajo- ja itsepurkaustesti 2, kapasiteetti 3, täysi 4; paketit 1, 3, 10 ja 30', async (t) => {
  const { pyynto } = await kaynnista(t, { oletukset: true });
  const d = (await pyynto('/api/v1/tuotteet')).d;
  assert.deepEqual(d.tuotteet.map(x => [x.tuote, x.krediitit]), [['akveri_krediitit_1', 1], ['akveri_krediitit_3', 3], ['akveri_krediitit_10', 10], ['akveri_krediitit_30', 30]]);
  assert.deepEqual(d.hinnat, { pikatarkastus: 1, kapasiteetti: 3, taysi: 4, ajotesti: 2, pika_ajo: 1, kuormitus: 1, pikalataus: 1, itsepurkaus: 2 });
});

test('päivityspaketti sisältää sovellustiedostot ja palvelin siirtää ne Omiin latauksiin', async (t) => {
  const { siirraLataukset } = require('../server');
  const v = require('../package.json').version;
  const kansio = fs.mkdtempSync(path.join(os.tmpdir(), 'akveri-paivitys-'));
  t.after(() => fs.rmSync(kansio, { recursive: true, force: true }));
  const sov = path.join(kansio, 'sovellukset');
  fs.mkdirSync(sov);
  fs.writeFileSync(path.join(sov, `AKVERI-asennus-${v}.exe`), 'exe');
  fs.writeFileSync(path.join(sov, `AKVERI-${v}.apk`), 'apk');
  fs.writeFileSync(path.join(sov, `AKVERI-${v}.aab`), 'aab');          // Play Consoleen, ei pakettiin
  fs.writeFileSync(path.join(sov, 'AKVERI-asennus-0.0.1.exe'), 'vanha'); // väärä versio, ei pakettiin
  const tulos = kokoa(kansio, sov);
  assert.ok(tulos.polku.endsWith(`akveri-paivitys-${v}.zip`));
  const zip = fs.readFileSync(tulos.polku);
  const eocd = zip.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  let p = zip.readUInt32LE(eocd + 16); const nimet = []; let manifest;
  for (let i = 0; i < zip.readUInt16LE(eocd + 10); i++) {
    const koko = zip.readUInt32LE(p + 20), np = zip.readUInt16LE(p + 28), paikka = zip.readUInt32LE(p + 42);
    const nimi = zip.toString('utf8', p + 46, p + 46 + np); nimet.push(nimi);
    if (nimi === 'manifest.json') { const a = paikka + 30 + zip.readUInt16LE(paikka + 26) + zip.readUInt16LE(paikka + 28); manifest = JSON.parse(zlib.inflateRawSync(zip.subarray(a, a + koko))); }
    p += 46 + np + zip.readUInt16LE(p + 30) + zip.readUInt16LE(p + 32);
  }
  assert.deepEqual(nimet.filter(n => n.startsWith('lataukset/')).sort(), [`lataukset/AKVERI-${v}.apk`, `lataukset/AKVERI-asennus-${v}.exe`]);
  assert.equal(manifest.tuote, 'akveri-palvelin');
  assert.ok(manifest.tiedostot[`lataukset/AKVERI-asennus-${v}.exe`] && manifest.tiedostot['server.js']);

  // Palvelin siirtää tiedostot ja poistaa saman sovelluksen vanhat versiot, muut tiedostot jäävät
  const lahde = path.join(kansio, 'lahde'); const kohde = path.join(kansio, 'kohde');
  fs.mkdirSync(lahde); fs.mkdirSync(kohde);
  fs.writeFileSync(path.join(lahde, `AKVERI-asennus-${v}.exe`), 'uusi');
  fs.writeFileSync(path.join(kohde, 'AKVERI-asennus-1.0.0.exe'), 'vanha');
  fs.writeFileSync(path.join(kohde, 'muu-tiedosto.zip'), 'oma');
  siirraLataukset(lahde, kohde);
  assert.deepEqual(fs.readdirSync(kohde).sort(), [`AKVERI-asennus-${v}.exe`, 'muu-tiedosto.zip']);
  assert.equal(fs.readFileSync(path.join(kohde, `AKVERI-asennus-${v}.exe`), 'utf8'), 'uusi');
  assert.deepEqual(siirraLataukset(path.join(kansio, 'ei-ole'), kohde), []);
});

test('autojen kokemukset: tunnisteet karsitaan ja aineisto näkyy hallinnassa', async (t) => {
  const { pyynto, aika } = await kaynnista(t);
  const tili = (await pyynto('/api/v1/tili', { method: 'POST' })).d;
  const kokemus = {
    tila: 'estetty', mittaustyyppi: 'pikatarkastus', alusta: 'meb', merkki: 'Volkswagen', malli: 'ID.4 77 kWh',
    vin_alku: 'WVGZZZE2', vin: 'WVGZZZE2ZMP032376', rekisteri: 'ABC-123', mittaaja: 'Antero', vuosimalli: 2021,
    kunto_saatu: false, mittarilukema_autosta: true, kennoryhmat_autosta: 96,
    kyselyt: { 'BMS 2250CE': { vastauksia: 0, ei_vastausta: 3, kielto: 49, pituus: 0 }, '<script>': { vastauksia: 1 } }
  };
  assert.equal((await pyynto('/api/v1/kokemus', { method: 'POST', auth: tili, body: kokemus })).status, 200);
  assert.equal((await pyynto('/api/v1/kokemus', { method: 'POST', auth: tili, body: { ...kokemus, tila: 'muu' } })).status, 400);
  assert.equal((await pyynto('/api/v1/kokemus', { method: 'POST', body: kokemus })).status, 401);
  const s = await kirjauduHallintaan(pyynto, aika);
  const r = (await pyynto('/api/hallinta/kokemukset', { evaste: s.evaste, otsakkeet: s.otsakkeet })).d.rivit;
  assert.equal(r.length, 1);
  const k = r[0];
  assert.equal(k.vin_alku, 'WVGZZZE2');
  for (const pois of ['vin', 'rekisteri', 'mittaaja', 'tili']) assert.equal(k[pois], undefined, pois);
  assert.deepEqual(Object.keys(k.kyselyt), ['BMS 2250CE']);
  assert.equal(k.kyselyt['BMS 2250CE'].kielto, 49);
  assert.equal(k.kunto_saatu, false);
  assert.match(k.kuukausi, /^\d{4}-\d{2}$/);
});
