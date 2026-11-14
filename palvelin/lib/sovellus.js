// sovellus.js — AKVERI-sovelluksen rajapinta (/api/v1/...) ja julkinen raportin tarkistus.
//
// Krediittien logiikka (mittauksen hinta krediitteinä asetetaan hallinnassa testityypeittäin, oletus 1):
//   1. Sovellus luo itselleen tilin (tunnus + salainen avain). Tilillä ei ole ilmaisia krediittejä.
//   2. Osto Google Playssa → sovellus lähettää ostotunnuksen → palvelin tarkistaa oston Googlelta → krediitit tilille.
//      Sama osto hyvittyy vain kerran ja vain sille tilille, jolle se tehtiin (Google palauttaa tilin tunnuksen).
//   3. Mittauksen alussa sovellus varaa testiluvan: krediitti veloitetaan heti ja testi saa yksilöllisen tunnuksen,
//      joka tulee raportin QR-koodiin (akveri.fi/v/<tunnus>).
//   4. Mittauksen lopuksi sovellus rekisteröi raportin yhteenvedon. Vasta rekisteröity raportti näkyy tarkistussivulla
//      kelvollisena. Yksi lupa = yksi mittaus: lupaa ei voi käyttää toisen mittauksen raporttiin (raakadatan tarkiste).
//   4b. Testitili (omistaja merkitsee hallinnassa): mittaus ei kuluta krediittiä, mutta lupa merkitään testiksi ja
//      tarkistussivu näyttää sen testimittauksena, joten testitilillä tehty raportti ei kelpaa todistukseksi.
//   5. Jos mittaus keskeytyy pian alun jälkeen (oletus 60 min), sovellus voi perua luvan ja krediitti palautuu.
//      Myöhemmin keskeytyneestä mittauksesta sovellus lähettää hyvityspyynnön, jonka ylläpito käsittelee.
//      Peruttu lupa näkyy tarkistussivulla mitätöitynä, joten perutulla luvalla tehty raportti ei kelpaa.
//
// Henkilötiedot: valmistenumerosta tallennetaan vain alku (valmistajatunnus) ja kuusi viimeistä merkkiä sekä tiiviste,
// jolla ostaja voi tarkistaa oman autonsa numeron. Tilillä ei ole nimeä, sähköpostia eikä puhelinnumeroa.
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { json, Virhe, lueJson, ipOsoite, puhdista, yksiRivi, satunnaisTunnus, vakioaikainenVertailu } = require('./apu');
const { tiiviste } = require('./varasto');

const TUNNUS_RE = /^AK[0-9A-HJKMNP-TV-Z]{10}$/;
const TILI_RE = /^T[0-9A-HJKMNP-TV-Z]{12}$/;
const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/;
// Mittaustyypit ja niiden oletushinta krediitteinä. Omistaja muuttaa hinnat hallinnassa (Sivusto ja ehdot → Lataus ja hinnat),
// ja sovellus hakee ne palvelimelta (saldo-kysely), joten muutos näkyy sovelluksessa heti.
const MITTAUSTYYPIT = ['pikatarkastus', 'kapasiteetti', 'taysi', 'ajotesti', 'pika_ajo', 'kuormitus', 'pikalataus', 'itsepurkaus'];
const OLETUSHINTA = 1;
const OLETUSTUOTTEET = [
  { tuote: 'akveri_testi_1', krediitit: 1 },
  { tuote: 'akveri_testi_5', krediitit: 5 },
  { tuote: 'akveri_testi_20', krediitit: 20 }
];
const OLETUS_HYVITYSAIKA_MIN = 60;
// Sovelluksen versiot: palvelin hyväksyy krediittitoiminnot vain sovellukselta, joka on vähintään vahimmaisversio.
// Rajapinta /api/v1 pidetään taaksepäin yhteensopivana. Jos sitä joskus muutetaan yhteensopimattomasti, uusi rajapinta
// tehdään polkuun /api/v2 ja vanhaa pidetään yllä, kunnes vähimmäisversio on nostettu sen yli.
const OLETUS_VAHIMMAISVERSIO = '2.0.0';
const VERSIO_RE = /^\d{1,3}\.\d{1,3}\.\d{1,3}$/;
function vertaaVersioita(a, b) { const x = a.split('.').map(Number), y = b.split('.').map(Number); for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] - y[i]; return 0; }

function muotoileTunnus(t) { return t ? `${t.slice(0, 2)}-${t.slice(2, 7)}-${t.slice(7)}` : ''; }
function normalisoiTunnus(t) { return String(t || '').toUpperCase().replace(/[\s-]/g, '').replace(/O/g, '0').replace(/[IL]/g, '1'); }

// Allekirjoitusavain (Ed25519) syntyy ensimmäisellä käynnistyksellä tietokansioon. Testiluvat allekirjoitetaan sillä,
// joten luvan aitouden voi tarkistaa julkisella avaimella (/api/v1/avain) myös ilman palvelimen tietokantaa.
function lataaAvain(kansio) {
  const polku = path.join(kansio, 'allekirjoitus.pem');
  if (!fs.existsSync(polku)) {
    const { privateKey } = crypto.generateKeyPairSync('ed25519');
    fs.writeFileSync(polku, privateKey.export({ type: 'pkcs8', format: 'pem' }), { mode: 0o600, flag: 'wx' });
  }
  const yksityinen = crypto.createPrivateKey(fs.readFileSync(polku));
  return { yksityinen, julkinen: crypto.createPublicKey(yksityinen).export({ type: 'spki', format: 'der' }).toString('base64') };
}

function luoSovellusRajapinta({ varasto, google, env = process.env, nyt = () => Date.now(), rajoitin, postitus }) {
  const avain = lataaAvain(varasto.kansio);
  const tilit = () => varasto.get('tilit');
  const testit = () => varasto.get('testit');
  const ostot = () => varasto.get('ostot');
  const asetukset = () => varasto.get('asetukset');
  const hinnat = () => {
    const a = asetukset().hinnat || {};
    const h = {};
    for (const t of MITTAUSTYYPIT) h[t] = Number.isInteger(a[t]) && a[t] >= 1 ? a[t] : OLETUSHINTA;
    return h;
  };
  const tuotteet = () => (Array.isArray(asetukset().tuotteet) && asetukset().tuotteet.length ? asetukset().tuotteet : OLETUSTUOTTEET);
  const vahimmaisversio = () => (VERSIO_RE.test(String(asetukset().vahimmaisversio)) ? asetukset().vahimmaisversio : OLETUS_VAHIMMAISVERSIO);
  const uusinVersio = () => (VERSIO_RE.test(String(asetukset().uusinVersio)) ? asetukset().uusinVersio : '');
  // Sovellus kertoo versionsa otsakkeessa X-AKVERI-Versio. Liian vanha versio ei saa krediittitoimintoja (426).
  function tarkistaVersio(req) {
    const v = String(req.headers['x-akveri-versio'] || '');
    if (!VERSIO_RE.test(v) || vertaaVersioita(v, vahimmaisversio()) < 0) {
      throw new Virhe(`AKVERIn versio ${v || '(tuntematon)'} on liian vanha. Päivitä AKVERI uusimpaan versioon (vähintään ${vahimmaisversio()}).`, 426);
    }
  }
  const hyvitysaikaMs = () => (Number(asetukset().hyvitysaikaMin) > 0 ? Number(asetukset().hyvitysaikaMin) : OLETUS_HYVITYSAIKA_MIN) * 60000;

  function rajoita(req, nimi, raja, ikkunaMs) {
    if (rajoitin.kayta(nimi + ':' + ipOsoite(req, env), raja, ikkunaMs)) throw new Virhe('Liian monta pyyntöä. Yritä hetken kuluttua uudelleen.', 429);
  }

  // Tunnistus: otsake "Authorization: AKVERI <tilitunnus>.<avain>"
  function tunnista(req) {
    const m = /^AKVERI (T[0-9A-Z]{12})\.([A-Za-z0-9_-]{43})$/.exec(String(req.headers.authorization || ''));
    const tili = m && tilit()[m[1]];
    if (!tili || !vakioaikainenVertailu(tili.avainTiiviste, tiiviste(m[2]))) throw new Virhe('Tunnistus epäonnistui. Sovelluksen tili ei ole voimassa.', 401);
    if (tili.suljettu) throw new Virhe('Tili on suljettu. Ota yhteyttä AKVERIn asiakaspalveluun.', 403);
    return tili;
  }

  function allekirjoita(teksti) { return crypto.sign(null, Buffer.from(teksti), avain.yksityinen).toString('base64'); }

  function vapaatLuvat(tili) { return Object.values(testit()).filter(t => t.tili === tili && t.tila === 'varattu').length; }

  // ------------------------------------------------------------ toiminnot
  function luoTili(req) {
    rajoita(req, 'tili', 10, 3600000);
    let id;
    do { id = 'T' + satunnaisTunnus(12); } while (tilit()[id]);
    const salainen = crypto.randomBytes(32).toString('base64url');
    tilit()[id] = { id, avainTiiviste: tiiviste(salainen), luotu: new Date(nyt()).toISOString() };
    varasto.tallenna('tilit');
    return { tili: id, avain: salainen };
  }

  function saldo(tili) {
    return { tili: tili.id, saldo: varasto.saldo(tili.id), avoimetLuvat: vapaatLuvat(tili.id), hyvitysaikaMin: hyvitysaikaMs() / 60000, testitili: !!tili.testitili, hinnat: hinnat() };
  }

  async function osto(tili, body) {
    const tuote = puhdista(body.tuote, 100);
    const ostotunnus = puhdista(body.ostotunnus, 4000);
    const maaritys = tuotteet().find(t => t.tuote === tuote);
    if (!maaritys) throw new Virhe('Tuntematon tuote.');
    if (!ostotunnus) throw new Virhe('Ostotunnus puuttuu.');
    const avainOsto = tiiviste(ostotunnus);
    const aiempi = ostot()[avainOsto];
    if (aiempi) {
      if (aiempi.tili !== tili.id) throw new Virhe('Osto on jo käytetty toisella tilillä.', 409);
      return { ...saldo(tili), hyvitetty: 0, jo: true };
    }
    const g = await google.tarkistaOsto(tuote, ostotunnus);
    if (g.tila === 'odottaa') return { ...saldo(tili), hyvitetty: 0, odottaa: true };
    if (g.tila !== 'maksettu') throw new Virhe('Google Play ei vahvistanut ostoa.', 402);
    // Osto on sidottu siihen tiliin, jolle sovellus sen teki (obfuscatedAccountId). Toisen tilin ostotunnus ei kelpaa.
    if (g.tili !== tili.id) throw new Virhe('Osto on tehty toiselle tilille.', 409);
    ostot()[avainOsto] = { tili: tili.id, tuote, krediitit: maaritys.krediitit, tilaus: g.tilaus, testiosto: !!g.testiosto, aika: new Date(nyt()).toISOString(), tila: 'hyvitetty' };
    varasto.tallenna('ostot');
    varasto.kirjaa({ tili: tili.id, muutos: maaritys.krediitit, syy: 'osto', viite: g.tilaus || avainOsto.slice(0, 16), selite: tuote + (g.testiosto ? ' (testiosto)' : '') });
    return { ...saldo(tili), hyvitetty: maaritys.krediitit };
  }

  function varaa(tili, body) {
    if (vapaatLuvat(tili.id) >= 5) throw new Virhe('Tilillä on jo viisi avointa testilupaa. Viimeistele tai peru aiemmat mittaukset ensin.', 409);
    const testi = !!tili.testitili;
    // Vanhempi sovellus ei kerro mittaustyyppiä: silloin käytetään oletushintaa.
    const tyyppi = MITTAUSTYYPIT.includes(body.tyyppi) ? body.tyyppi : '';
    if (body.tyyppi !== undefined && !tyyppi) throw new Virhe('Tuntematon mittaustyyppi.');
    const hinta = tyyppi ? hinnat()[tyyppi] : OLETUSHINTA;
    if (!testi && varasto.saldo(tili.id) < hinta) throw new Virhe(`Krediitit eivät riitä. Tämä mittaus maksaa ${hinta} ${hinta === 1 ? 'krediitin' : 'krediittiä'}. Osta krediittejä Krediitit-näkymässä.`, 402);
    let tunnus;
    do { tunnus = 'AK' + satunnaisTunnus(10); } while (testit()[tunnus]);
    const varattu = new Date(nyt()).toISOString();
    const allekirjoitus = allekirjoita(`AKVERI-LUPA|${tunnus}|${tili.id}|${varattu}`);
    testit()[tunnus] = { tunnus, tili: tili.id, tila: 'varattu', varattu, alusta: puhdista(body.alusta, 20), sovellusversio: puhdista(body.versio, 20), allekirjoitus, ...(tyyppi ? { mittaustyyppi: tyyppi } : {}), ...(testi ? { testi: true } : { krediitit: hinta }) };
    varasto.tallenna('testit');
    if (!testi) varasto.kirjaa({ tili: tili.id, muutos: -hinta, syy: 'testi', viite: tunnus, ...(tyyppi ? { selite: tyyppi } : {}) });
    return { testi, hinta: testi ? 0 : hinta, tunnus, tunnusNaytto: muotoileTunnus(tunnus), varattu, allekirjoitus, osoite: julkinenOsoite() + '/v/' + tunnus, saldo: varasto.saldo(tili.id), hyvitysaikaMin: hyvitysaikaMs() / 60000 };
  }

  function haeOmaTesti(tili, tunnus) {
    const t = testit()[normalisoiTunnus(tunnus)];
    if (!t || t.tili !== tili.id) throw new Virhe('Testilupaa ei löydy.', 404);
    return t;
  }

  function peru(tili, body) {
    const t = haeOmaTesti(tili, body.tunnus);
    if (t.tila === 'peruttu') return { ok: true, jo: true, saldo: varasto.saldo(tili.id) };
    if (t.tila !== 'varattu') throw new Virhe('Raportti on jo rekisteröity, joten lupaa ei voi perua.', 409);
    if (nyt() - Date.parse(t.varattu) > hyvitysaikaMs()) throw new Virhe(`Luvan voi perua ${hyvitysaikaMs() / 60000} minuutin kuluessa. Lähetä hyvityspyyntö, niin ylläpito käsittelee sen.`, 409);
    t.tila = 'peruttu'; t.peruttu = new Date(nyt()).toISOString(); t.perumisenSyy = yksiRivi(puhdista(body.syy, 300));
    varasto.tallenna('testit');
    if (!t.testi) varasto.kirjaa({ tili: tili.id, muutos: t.krediitit || 1, syy: 'peruutus', viite: t.tunnus, selite: t.perumisenSyy });
    return { ok: true, saldo: varasto.saldo(tili.id) };
  }

  function hyvityspyynto(tili, body) {
    const t = haeOmaTesti(tili, body.tunnus);
    if (t.tila !== 'varattu') throw new Virhe('Hyvitystä voi pyytää vain keskeytyneestä mittauksesta, jonka raporttia ei ole rekisteröity.', 409);
    if (t.hyvityspyynto) return { ok: true, jo: true };
    t.hyvityspyynto = { aika: new Date(nyt()).toISOString(), syy: puhdista(body.syy, 1500), tiedot: puhdista(body.tiedot, 4000), tila: 'avoin' };
    varasto.tallenna('testit');
    if (postitus) postitus.ilmoitaTaustalla('AKVERI: uusi hyvityspyyntö', `Mittaus ${muotoileTunnus(t.tunnus)}, tili ${tili.id}.\nSyy: ${t.hyvityspyynto.syy || '-'}\n\nKäsittele pyyntö akveri.fi/hallinta → Testit ja hyvitykset.\n`);
    return { ok: true };
  }

  function lukuTaiNull(x, min, max) {
    if (x === null || x === undefined || x === '') return null;
    const n = Number(x);
    if (!Number.isFinite(n) || n < min || n > max) throw new Virhe('Raportin tiedoissa on virheellinen luku.');
    return Math.round(n * 100) / 100;
  }

  // ---- Anonyymi mittausaineisto ohjelmiston kehittämiseen (tietosuojaseloste: "Anonyymi mittausaineisto").
  // Rivillä ei ole tunnisteita (raportin tunnus, tili, valmistenumero, rekisterinumero, suorittaja, tarkka aika).
  // Mittarilukema pyöristetään tuhanteen kilometriin ja aika kuukauteen, ja rivi lisätään satunnaiseen kohtaan, jotta
  // sitä ei voi yhdistää raporttiin rekisteröintijärjestyksen perusteella. Siksi rivi ei poistu tietojen poiston mukana.
  const ANON_TEKSTIT = { alusta: 30, kemia: 40, kennotyyppi: 60 };
  const ANON_LUVUT = { vuosimalli: [1990, 2100], kennoryhmat: [1, 1000], uutena_kwh: [0, 400], jannite_ero_mv: [0, 5000],
    ero_bms_pct: [-100, 100], epavarmuus_kwh: [0, 100], lampo_min_c: [-60, 100], lampo_max_c: [-60, 100],
    soc_alku_pct: [0, 100], soc_loppu_pct: [0, 100], kesto_h: [0, 1000], suojavara_kwh: [0, 50] };
  function lisaaTilastoon(t, r, y, versio) {
    const a = y.anonyymi && typeof y.anonyymi === 'object' ? y.anonyymi : {};
    const rivi = {
      kuukausi: r.mitattu ? new Date(r.mitattu * 1000).toISOString().slice(0, 7) : new Date(nyt()).toISOString().slice(0, 7),
      mittaustyyppi: t.mittaustyyppi || '', merkki: r.merkki, malli: r.malli,
      mittarilukema_tkm: r.mittarilukema !== null && r.mittarilukema !== undefined ? Math.round(r.mittarilukema / 1000) : null,
      kunto_pct: r.kuntoPct, kapasiteetti_kwh: r.kapasiteettiKwh, versio: yksiRivi(puhdista(versio, 20)), testi: !!t.testi
    };
    for (const [k, n] of Object.entries(ANON_TEKSTIT)) if (typeof a[k] === 'string') rivi[k] = yksiRivi(puhdista(a[k], n));
    for (const [k, [min, max]] of Object.entries(ANON_LUVUT)) {
      const v = Number(a[k]);
      if (a[k] !== null && a[k] !== undefined && a[k] !== '' && Number.isFinite(v) && v >= min && v <= max) rivi[k] = Math.round(v * 10) / 10;
    }
    const tl = varasto.get('tilasto');
    if (!Array.isArray(tl.rivit)) tl.rivit = [];
    tl.rivit.splice(crypto.randomInt(tl.rivit.length + 1), 0, rivi);
    varasto.tallenna('tilasto');
  }
  function tilasto() { const tl = varasto.get('tilasto'); return Array.isArray(tl.rivit) ? tl.rivit : []; }

  function rekisteroi(tili, body) {
    const t = haeOmaTesti(tili, body.tunnus);
    if (t.tila === 'peruttu' || t.tila === 'mitatoity' || t.tila === 'poistettu') throw new Virhe('Testilupa on peruttu tai poistettu, joten raporttia ei voi rekisteröidä.', 409);
    const tarkiste = String(body.tarkiste || '').toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(tarkiste)) throw new Virhe('Raakadatan tarkiste puuttuu.');
    if (t.raportti && t.raportti.tarkiste !== tarkiste) throw new Virhe('Tällä testiluvalla on jo rekisteröity toinen mittaus. Yksi lupa kelpaa yhteen mittaukseen.', 409);
    const y = body.yhteenveto && typeof body.yhteenveto === 'object' ? body.yhteenveto : {};
    // Raportin mittaustyypin on vastattava ostettua lupaa (hinta määräytyy tyypin mukaan). Versiosta 2.0.3 alkaen
    // sovellus kertoo tyypin aina; vanhemmat versiot eivät kerro sitä raportissa.
    const rv = String(body.versio || '');
    const vaatiiTyypin = !/^\d+\.\d+\.\d+$/.test(rv) || vertaaVersioita(rv, '2.0.3') >= 0;
    if (t.mittaustyyppi && (y.mittaustyyppi || vaatiiTyypin) && y.mittaustyyppi !== t.mittaustyyppi) {
      throw new Virhe('Mittauksen tyyppi ei vastaa testilupaa, joten raporttia ei voi rekisteröidä.', 409);
    }
    const vin = String(y.vin || '').toUpperCase();
    const raportti = {
      tarkiste,
      tyyppi: yksiRivi(puhdista(y.tyyppi, 60)),
      merkki: yksiRivi(puhdista(y.merkki, 40)),
      malli: yksiRivi(puhdista(y.malli, 140)),
      vinAlku: VIN_RE.test(vin) ? vin.slice(0, 3) : '',
      vinLoppu: VIN_RE.test(vin) ? vin.slice(-6) : '',
      vinTiiviste: VIN_RE.test(vin) ? tiiviste('AKVERI-VIN|' + vin) : '',
      mittarilukema: lukuTaiNull(y.mittarilukema, 0, 3000000),
      kuntoPct: lukuTaiNull(y.kunto_pct, 0, 150),
      kapasiteettiKwh: lukuTaiNull(y.kapasiteetti_kwh, 0, 400),
      mitattu: lukuTaiNull(y.mitattu, 1.5e9, 4e9),
      paattynyt: lukuTaiNull(y.paattynyt, 1.5e9, 4e9),
      raporttinumero: yksiRivi(puhdista(y.raporttinumero, 30)),
      versio: yksiRivi(puhdista(body.versio, 20)),
      // Mittauksen suorittajaksi ilmoitettu nimi tai yritys (näkyy raportissa ja tarkistussivulla)
      suorittaja: yksiRivi(puhdista(y.suorittaja, 80)),
      riippumaton: y.riippumaton === true ? true : y.riippumaton === false ? false : null
    };
    const edellinen = t.raportti;
    t.raportti = raportti;
    if (!edellinen) { t.rekisteroity = new Date(nyt()).toISOString(); t.tila = 'valmis'; lisaaTilastoon(t, raportti, y, body.versio); }
    else t.paivitetty = new Date(nyt()).toISOString(); // uudelleenlaskenta uudemmalla versiolla: sama raakadata, päivitetty tulos
    if (t.hyvityspyynto && t.hyvityspyynto.tila === 'avoin') t.hyvityspyynto.tila = 'raportti rekisteröity';
    varasto.tallenna('testit');
    return { ok: true, tunnus: t.tunnus, osoite: julkinenOsoite() + '/v/' + t.tunnus, rekisteroity: t.rekisteroity };
  }

  // Julkinen tarkistus: näyttää vain raportin tunnistetiedot ja tuloksen, ei tilin tietoja.
  function vahvistus(req, tunnus, vinKysely) {
    rajoita(req, 'vahvistus', 120, 3600000);
    const t = testit()[normalisoiTunnus(tunnus)];
    if (!TUNNUS_RE.test(normalisoiTunnus(tunnus)) || !t) return { loytyi: false };
    const r = t.raportti || {};
    const ulos = {
      loytyi: true, tunnus: muotoileTunnus(t.tunnus), tila: t.tila, testi: !!t.testi, varattu: t.varattu, rekisteroity: t.rekisteroity || null, paivitetty: t.paivitetty || null,
      mitatoinninSyy: t.tila === 'mitatoity' ? (t.mitatoinninSyy || '') : undefined
    };
    if (t.tila === 'poistettu') ulos.poistonSyy = 'Raportin tiedot on poistettu.';
    if (t.tila === 'valmis') Object.assign(ulos, {
      tyyppi: r.tyyppi, merkki: r.merkki, malli: r.malli, vin: r.vinAlku ? `${r.vinAlku}········${r.vinLoppu}` : '',
      mittarilukema: r.mittarilukema, kuntoPct: r.kuntoPct, kapasiteettiKwh: r.kapasiteettiKwh, mitattu: r.mitattu, paattynyt: r.paattynyt,
      raporttinumero: r.raporttinumero, tarkiste: r.tarkiste.slice(0, 16), versio: r.versio, suorittaja: r.suorittaja || '', riippumaton: r.riippumaton
    });
    if (vinKysely && t.tila === 'valmis' && r.vinTiiviste) {
      rajoita(req, 'vin', 20, 3600000);
      ulos.vinTasmaa = vakioaikainenVertailu(r.vinTiiviste, tiiviste('AKVERI-VIN|' + String(vinKysely).toUpperCase().replace(/\s/g, '')));
    }
    return ulos;
  }

  function julkinenOsoite() { return String(env.JULKINEN_OSOITE || 'https://akveri.fi').replace(/\/+$/, ''); }

  // ------------------------------------------------------------ reititys
  // ---- Tietosuoja (tietosuojaseloste: oikeus saada pääsy tietoihin ja oikeus tietojen poistoon).
  // Samat toiminnot ovat sovelluksessa (asiakas itse) ja akveri.fi-hallinnassa (pyynnöstä).
  // Raportin tiedot: tarkistussivu näyttää sen jälkeen vain "tiedot on poistettu".
  function tyhjennaRaportti(x, syy) {
    x.raportti = null; x.tila = 'poistettu'; x.poistettu = new Date(nyt()).toISOString(); x.poistonSyy = syy;
    if (x.hyvityspyynto) { x.hyvityspyynto.syy = ''; x.hyvityspyynto.tiedot = ''; }
  }
  // Tilin poisto: tili lakkaa toimimasta, avoimet testiluvat perutaan ja hyvityspyyntöjen tekstit poistetaan.
  // raportit: true poistaa myös tilin rekisteröityjen raporttien tiedot. Krediittien kirjanpito ja ostot säilytetään
  // kirjanpitolain edellyttämän ajan (niissä on vain satunnainen tilitunnus).
  function poistaTiliTiedot(tiliId, { raportit = false, syy = 'Tili poistettu' } = {}) {
    let raportteja = 0;
    for (const x of Object.values(testit())) {
      if (x.tili !== tiliId) continue;
      if (x.hyvityspyynto) { x.hyvityspyynto.syy = ''; x.hyvityspyynto.tiedot = ''; }
      if (x.tila === 'varattu') { x.tila = 'peruttu'; x.peruttu = new Date(nyt()).toISOString(); x.perumisenSyy = syy; }
      if (raportit && x.raportti) { tyhjennaRaportti(x, syy); raportteja++; }
    }
    varasto.tallenna('testit');
    delete tilit()[tiliId];
    varasto.tallenna('tilit');
    return { ok: true, poistettu: tiliId, raportteja };
  }
  // Kaikki tiliin liittyvät tiedot luettavassa muodossa (sovelluksen "Lataa tietoni" ja hallinnan vienti).
  function tilinTiedot(tiliId) {
    const t = tilit()[tiliId];
    if (!t) throw new Virhe('Tiliä ei löydy.', 404);
    return {
      muodostettu: new Date(nyt()).toISOString(),
      tili: { tunnus: t.id, luotu: t.luotu, saldo: varasto.saldo(t.id), testitili: !!t.testitili, suljettu: !!t.suljettu },
      kirjanpito: varasto.kirjanpito({ tili: t.id, raja: 100000 }).map(r => ({ aika: r.aika, muutos: r.muutos, syy: r.syy, viite: r.viite || '', selite: r.selite || '' })),
      ostot: Object.values(ostot()).filter(o => o.tili === t.id).map(o => ({ aika: o.aika, tuote: o.tuote, krediitit: o.krediitit, tila: o.tila, testiosto: !!o.testiosto })),
      testit: Object.values(testit()).filter(x => x.tili === t.id).map(x => ({
        tunnus: muotoileTunnus(x.tunnus), tila: x.tila, varattu: x.varattu, rekisteroity: x.rekisteroity || null,
        mittaustyyppi: x.mittaustyyppi || '', krediitit: x.krediitit ?? null,
        raportti: x.raportti ? { tyyppi: x.raportti.tyyppi, merkki: x.raportti.merkki, malli: x.raportti.malli,
          valmistenumero: x.raportti.vinAlku ? `${x.raportti.vinAlku}…${x.raportti.vinLoppu}` : '', mittarilukema: x.raportti.mittarilukema,
          kuntoPct: x.raportti.kuntoPct, kapasiteettiKwh: x.raportti.kapasiteettiKwh, suorittaja: x.raportti.suorittaja || '',
          raporttinumero: x.raportti.raporttinumero } : null,
        hyvityspyynto: x.hyvityspyynto ? { aika: x.hyvityspyynto.aika, tila: x.hyvityspyynto.tila, syy: x.hyvityspyynto.syy || '' } : null
      }))
    };
  }
  // Asiakkaan oma raportti pois tarkistuspalvelusta (vain oman tilin raportti)
  function poistaOmaRaportti(tili, body) {
    const x = testit()[normalisoiTunnus(body.tunnus || '')];
    if (!x || x.tili !== tili.id) throw new Virhe('Raporttia ei löydy tältä tililtä.', 404);
    if (!x.raportti) throw new Virhe('Raportin tietoja ei ole palvelussa.', 409);
    tyhjennaRaportti(x, 'Raportin omistajan pyyntö');
    varasto.tallenna('testit');
    return { ok: true, tila: x.tila };
  }

  async function kasittele(req, res, polku, kysely) {
    try {
      if (polku === '/api/v1/tila' && req.method === 'GET') return json(res, 200, { ok: true, palvelu: 'akveri', versio: env.AKVERI_VERSIO || '', ostot: google.kaytossa, rajapinta: 1, vahimmaisversio: vahimmaisversio(), uusinVersio: uusinVersio() });
      if (polku === '/api/v1/avain' && req.method === 'GET') return json(res, 200, { algoritmi: 'Ed25519', julkinen: avain.julkinen });
      if (polku === '/api/v1/tuotteet' && req.method === 'GET') return json(res, 200, { tuotteet: tuotteet(), hinnat: hinnat() });
      const vm = /^\/api\/v1\/vahvistus\/([A-Za-z0-9-]{10,20})$/.exec(polku);
      if (vm && req.method === 'GET') return json(res, 200, vahvistus(req, vm[1], kysely.get('vin')));
      if (req.method !== 'POST' && polku !== '/api/v1/saldo') throw new Virhe('Tuntematon pyyntö.', 404);
      tarkistaVersio(req);
      if (polku === '/api/v1/tili') return json(res, 200, luoTili(req));
      rajoita(req, 'api', 600, 3600000);
      const tili = tunnista(req);
      if (polku === '/api/v1/saldo' && req.method === 'GET') return json(res, 200, saldo(tili));
      const body = await lueJson(req);
      if (polku === '/api/v1/osto') return json(res, 200, await osto(tili, body));
      if (polku === '/api/v1/testi/varaa') return json(res, 200, varaa(tili, body));
      if (polku === '/api/v1/testi/peru') return json(res, 200, peru(tili, body));
      if (polku === '/api/v1/testi/hyvityspyynto') return json(res, 200, hyvityspyynto(tili, body));
      if (polku === '/api/v1/testi/raportti') return json(res, 200, rekisteroi(tili, body));
      if (polku === '/api/v1/testi/poista-tiedot') return json(res, 200, poistaOmaRaportti(tili, body));
      if (polku === '/api/v1/tili/tiedot') return json(res, 200, tilinTiedot(tili.id));
      if (polku === '/api/v1/tili/poista') {
        if (body.vahvista !== true) throw new Virhe('Vahvista tilin poisto.');
        return json(res, 200, poistaTiliTiedot(tili.id, { raportit: body.raportit === true, syy: 'Tilin omistajan pyyntö' }));
      }
      throw new Virhe('Tuntematon pyyntö.', 404);
    } catch (e) {
      if (e instanceof Virhe) return json(res, e.status, { virhe: e.message });
      console.error('[api]', e && e.stack || e);
      return json(res, 502, { virhe: e && /Google/.test(e.message) ? e.message : 'Palvelinvirhe. Yritä hetken kuluttua uudelleen.' });
    }
  }

  // Googlessa perutut tai hyvitetyt ostot: krediitit vähennetään (saldo voi mennä miinukselle, jolloin uusia lupia ei saa).
  async function tarkistaPerutut() {
    if (!google.kaytossa) return 0;
    const a = asetukset();
    const alku = Number(a.perututTarkistettu) || (nyt() - 30 * 86400000);
    const lista = await google.perututOstot(alku - 86400000);
    let maara = 0;
    for (const v of lista) {
      const o = ostot()[tiiviste(v.ostotunnus)];
      if (!o || o.tila === 'peruttu') continue;
      o.tila = 'peruttu'; o.peruttu = new Date(v.aika || nyt()).toISOString();
      varasto.kirjaa({ tili: o.tili, muutos: -o.krediitit, syy: 'osto peruttu', viite: o.tilaus, selite: 'Google Play perui tai hyvitti oston' });
      maara++;
    }
    if (maara) varasto.tallenna('ostot');
    a.perututTarkistettu = nyt();
    varasto.tallenna('asetukset');
    return maara;
  }

  return { kasittele, tarkistaPerutut, google, julkinenAvain: avain.julkinen, tuotteet, tyhjennaRaportti, poistaTiliTiedot, tilinTiedot, tilasto };
}

module.exports = { luoSovellusRajapinta, MITTAUSTYYPIT, OLETUSHINTA, muotoileTunnus, normalisoiTunnus, TUNNUS_RE, TILI_RE, OLETUSTUOTTEET, OLETUS_VAHIMMAISVERSIO, vertaaVersioita, VERSIO_RE };
