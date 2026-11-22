// akveri/reitit.js — Hallintatyökalun AKVERI-välilehden rajapinta (/api/akveri/...).
//
// AKVERI on oma tuotteensa omalla päivitysradallaan: palvelinpaketti (akveri-palvelin-<versio>.zip) tulee AKVERIn
// repositoriosta, ja se tallennetaan tähän työkaluun versioittain. Palvelimena käytetään samaa oletuspalvelinta kuin
// Vuoropisteessä (sama SSH-yhteys), mutta AKVERI asennetaan omalle käyttäjälleen ja kansioihinsa (ks. akveri/vienti.js).
// Palvelimen toiminnot ajetaan yksi kerrallaan yhteisellä lukolla (palvelinlukko.js), jotta ne eivät häiritse Vuoropisteen
// portaalin toimintoja.
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const store = require('../store');
const asetukset = require('./asetukset');
const akveri = require('./vienti');
const palvelinvienti = require('../palvelinvienti');
const palvelinlukko = require('../palvelinlukko');

// Lukee pyynnön rungon raakana tiedostoon kokorajalla (ei koko tiedostoa muistiin).
function lueRaakaTiedostoon(req, max) {
  return new Promise((resolve, reject) => {
    const kohde = path.join(os.tmpdir(), 'akveri-lahetys-' + crypto.randomBytes(8).toString('hex'));
    const virta = fs.createWriteStream(kohde, { mode: 0o600 });
    let koko = 0; let valmis = false;
    const lopeta = (e) => { if (valmis) return; valmis = true; virta.destroy(); fs.rm(kohde, { force: true }, () => {}); reject(e); };
    req.on('data', (d) => { koko += d.length; if (koko > max) { lopeta(new Error(`Tiedosto on liian suuri (enintään ${Math.round(max / 1048576)} Mt).`)); req.resume(); } });
    req.on('error', lopeta);
    virta.on('error', lopeta);
    virta.on('finish', () => { if (!valmis) { valmis = true; resolve({ polku: kohde, koko }); } });
    req.pipe(virta);
  });
}

// SSH-yhteys AKVERIn palvelimelle: sama kuin Vuoropisteellä (toimiva yhteys haetaan kuten portaalille) tai erillinen palvelin
// samalla Hallintatyökalun SSH-avaimella.
async function akveriYhteys(DATA_DIR, a) {
  const { valitseYhteys, oletusAvaimenPolku } = require('../palvelinyhteys');
  if (a.erillinenPalvelin) {
    if (!a.palvelinHost) throw new Error('Anna AKVERIn palvelimen osoite asetuksissa.');
    const avain = oletusAvaimenPolku(DATA_DIR);
    const prof = akveri.profiili({ host: a.palvelinHost, portti: a.palvelinPortti, kayttaja: a.palvelinKayttaja, sudo: a.palvelinSudo }, fs.existsSync(avain) ? avain : '', a);
    return { prof, testi: await palvelinvienti.testaa(prof), host: a.palvelinHost };
  }
  const o = store.haeOletuspalvelin(DATA_DIR);
  if (!o.host) throw new Error('Aseta ensin palvelinyhteys kohdassa Asetukset → Palvelinyhteys, tai valitse AKVERIlle oma palvelin asetuksista.');
  const v = await valitseYhteys(DATA_DIR, o, a, akveri, palvelinvienti);
  return { ...v, host: o.host };
}

// AKVERI-paketin mukana tuleva akveri.fi-palvelimen paketti (akveri/palvelin/akveri-palvelin-x.y.z.zip) siirretään
// versiovarastoon, josta se viedään palvelimelle. Näin AKVERIn yksi paketti päivittää sekä näkymät että palvelinohjelman.
function tuoMukanaTulevatPaketit(DATA_DIR, kansio = path.join(__dirname, 'palvelin')) {
  let nimet = [];
  try { nimet = fs.readdirSync(kansio).filter(n => /^akveri-palvelin-\d{1,3}\.\d{1,3}\.\d{1,3}\.zip$/.test(n)); } catch (e) { return; }
  // Samannimiseksi tallennettu paketti korvataan, jos mukana tulevan sisältö on muuttunut (sama versio, korjattu sisältö).
  const tallennetut = new Map(akveri.listaaPaketit(DATA_DIR).map(x => [x.nimi, x]));
  for (const n of nimet) {
    try {
      const uusi = fs.readFileSync(path.join(kansio, n));
      if (tallennetut.has(n)) {
        let vanha = null;
        try { vanha = fs.readFileSync(akveri.paketinPolku(DATA_DIR, tallennetut.get(n).versio)); } catch (e) { /* luetaan uudelleen alla */ }
        if (vanha && vanha.equals(uusi)) continue;
      }
      akveri.tallennaPaketti(DATA_DIR, uusi);
    } catch (e) { /* viallinen paketti ei estä */ }
  }
}

async function kasittele(req, res, p, ctx) {
  if (!p.startsWith('/api/akveri/')) return false;
  const { DATA_DIR, send, readBody } = ctx;
  const osa = p.slice('/api/akveri/'.length);
  const virhe = (e, koodi = 400) => send(res, koodi, { ok: false, virhe: e.message, vaiheet: e.vaiheet || [{ nimi: 'Virhe', ok: false, tuloste: e.message }] });
  try {
    if (osa === 'asetukset' && req.method === 'GET') {
      tuoMukanaTulevatPaketit(DATA_DIR);
      const o = store.haeOletuspalvelin(DATA_DIR);
      send(res, 200, { asetukset: asetukset.haeAkveri(DATA_DIR), palvelin: { host: o.host }, paketit: akveri.listaaPaketit(DATA_DIR), lukko: palvelinlukko.tila() });
      return true;
    }
    if (osa === 'asetukset' && req.method === 'PUT') {
      const body = await readBody(req);
      delete body.alkutunnus; delete body.julkaistu; // alkutunnus luodaan työkalussa, julkaisutila asetetaan julkaisussa
      send(res, 200, { asetukset: asetukset.tallennaAkveri(DATA_DIR, body) });
      return true;
    }
    if (osa === 'alkutunnus' && req.method === 'GET') {
      // Hallinnan (akveri.fi/hallinta) ensimmäinen kirjautuminen. Työkalu on paikallinen ja pääsalasanalla suojattu.
      send(res, 200, { alkutunnus: asetukset.haeAkveriSalaisena(DATA_DIR).alkutunnus || '' });
      return true;
    }
    // ---- palvelinpaketit (versiot)
    if (osa === 'paketit' && req.method === 'POST') {
      const t = await lueRaakaTiedostoon(req, akveri.PAKETTI_MAX);
      try { send(res, 200, { paketti: akveri.tallennaPaketti(DATA_DIR, fs.readFileSync(t.polku)), paketit: akveri.listaaPaketit(DATA_DIR) }); }
      finally { fs.rmSync(t.polku, { force: true }); }
      return true;
    }
    const pm = /^paketit\/(\d{1,3}\.\d{1,3}\.\d{1,3})$/.exec(osa);
    if (pm && req.method === 'GET') {
      const polku = akveri.paketinPolku(DATA_DIR, pm[1]);
      res.writeHead(200, { 'Content-Type': 'application/zip', 'Content-Disposition': `attachment; filename="akveri-palvelin-${pm[1]}.zip"`, 'Content-Length': fs.statSync(polku).size });
      fs.createReadStream(polku).pipe(res);
      return true;
    }
    if (pm && req.method === 'DELETE') { akveri.poistaPaketti(DATA_DIR, pm[1]); send(res, 200, { paketit: akveri.listaaPaketit(DATA_DIR) }); return true; }

    // ---- palvelintoiminnot
    const tm = /^(dns|testaa|julkaise|vie|asetukset-palvelimelle|tila|palauta|varmuuskopioi|varmuuskopiot|lataukset|poista-lataus|lataus|kayttajat|lisaa-kayttaja|poista-kayttaja)$/.exec(osa);
    const lataaKopio = osa === 'varmuuskopio' && req.method === 'GET';
    if (!(tm && req.method === 'POST') && !lataaKopio) return false;
    const toiminto = lataaKopio ? 'varmuuskopio' : tm[1];
    const a = asetukset.haeAkveriSalaisena(DATA_DIR);
    const o = store.haeOletuspalvelin(DATA_DIR);
    const host = a.erillinenPalvelin ? a.palvelinHost : o.host;
    if (!host) throw new Error(a.erillinenPalvelin ? 'Anna AKVERIn palvelimen osoite asetuksissa.' : 'Aseta ensin palvelinyhteys kohdassa Asetukset → Palvelinyhteys, tai valitse AKVERIlle oma palvelin asetuksista.');
    if (toiminto === 'dns') { send(res, 200, await akveri.dnsTila(host, a.domain)); return true; }
    let lahetys = null;
    if (toiminto === 'lataus') {
      const nimi = akveri.tarkistaLatausnimi(new URL(req.url, 'http://x').searchParams.get('nimi'));
      lahetys = { nimi, ...(await lueRaakaTiedostoon(req, akveri.LATAUS_MAX)) };
    }
    const body = ['vie', 'poista-lataus', 'lisaa-kayttaja', 'poista-kayttaja'].includes(toiminto) ? await readBody(req) : {};
    try {
      await palvelinlukko.kanssa('AKVERI', async () => {
        const valittu = await akveriYhteys(DATA_DIR, a);
        const prof = valittu.prof;
        if (!prof) throw new Error('SSH-avainta ei löydy. Luo avain kohdassa Asetukset → Palvelinyhteys.');
        if (toiminto === 'testaa') return send(res, 200, valittu.testi || await palvelinvienti.testaa(prof));
        if (toiminto === 'tila') return send(res, 200, await akveri.tila(prof));
        if (toiminto === 'palauta') return send(res, 200, await akveri.palautaEdellinen(prof));
        if (toiminto === 'varmuuskopioi') return send(res, 200, await palvelinvienti.varmuuskopioi(prof));
        if (toiminto === 'varmuuskopiot') return send(res, 200, await palvelinvienti.listaaVarmuuskopiot(prof));
        if (toiminto === 'lataukset') return send(res, 200, await akveri.listaaLataukset(prof));
        if (toiminto === 'poista-lataus') return send(res, 200, await akveri.poistaLataus(prof, body.nimi));
        if (toiminto === 'lataus') return send(res, 200, await akveri.vieLataus(prof, lahetys.nimi, lahetys.polku));
        if (toiminto === 'kayttajat') return send(res, 200, await akveri.kayttajat(prof, a, 'lista'));
        if (toiminto === 'lisaa-kayttaja') return send(res, 200, await akveri.kayttajat(prof, a, 'lisaa', body));
        if (toiminto === 'poista-kayttaja') return send(res, 200, await akveri.kayttajat(prof, a, 'poista', body));
        if (toiminto === 'varmuuskopio') {
          // AKVERIn tiedot ovat omistajan omaa liiketoimintadataa (ei Vuoropisteen asiakkaiden tietoja), joten kopion saa ladata talteen.
          const nimi = new URL(req.url, 'http://x').searchParams.get('nimi');
          const polku = await palvelinvienti.lataaVarmuuskopio(prof, nimi);
          res.writeHead(200, { 'Content-Type': 'application/gzip', 'Content-Disposition': `attachment; filename="akveri-${palvelinvienti.turvallinenKopioNimi(nimi)}"`, 'Content-Length': fs.statSync(polku).size });
          await new Promise((ok) => fs.createReadStream(polku).on('close', ok).pipe(res));
          fs.rmSync(polku, { force: true });
          return;
        }
        if (toiminto === 'asetukset-palvelimelle') {
          if (!a.alkutunnus) throw new Error('AKVERIa ei ole vielä julkaistu. Käytä Julkaise-painiketta.');
          return send(res, 200, await akveri.paivitaAsetukset(prof, a, a.alkutunnus));
        }
        if (toiminto === 'vie') {
          if (!a.julkaistu) throw new Error('AKVERIa ei ole vielä julkaistu. Käytä ensin Julkaise-painiketta.');
          return send(res, 200, await akveri.vie(prof, DATA_DIR, String(body.versio || '')));
        }
        if (toiminto === 'julkaise') {
          // Yksi painallus: DNS, yhteys, valmistelu (käyttäjä, kansiot, Node, palvelu, Caddy, asetukset) ja uusin paketti.
          const paketit = akveri.listaaPaketit(DATA_DIR);
          if (!paketit.length) throw new Error('Lisää ensin AKVERI-palvelimen julkaisupaketti (akveri-palvelin-x.y.z.zip).');
          const dns = await akveri.dnsTila(host, a.domain);
          if (!dns.ok) return send(res, 200, { ok: false, virhe: 'DNS ei vielä osoita palvelimelle. Lisää alla olevat tietueet ja yritä uudelleen, kun ne ovat voimassa.', dns, vaiheet: [{ nimi: 'DNS', ok: false, tuloste: dns.tietueet.filter(t => !t.ok).map(t => `${t.nimi} (A) → ${t.arvo}`).join('\n') }] });
          let vaiheet = [{ nimi: 'DNS', ok: true, tuloste: 'Tietueet osoittavat palvelimelle.' }];
          let alkutunnus = a.alkutunnus;
          if (!alkutunnus) { alkutunnus = crypto.randomBytes(32).toString('base64url'); asetukset.tallennaAkveri(DATA_DIR, { alkutunnus }); }
          const v = await akveri.valmistele(prof, a, alkutunnus);
          vaiheet = vaiheet.concat(v.vaiheet || []);
          if (!v.ok) return send(res, 200, { ...v, vaiheet });
          const t = await akveri.vie(prof, DATA_DIR, paketit[0].versio);
          vaiheet = vaiheet.concat(t.vaiheet || []);
          if (!t.ok) return send(res, 200, { ...t, vaiheet });
          asetukset.tallennaAkveri(DATA_DIR, { julkaistu: true });
          return send(res, 200, { ok: true, vaiheet, huomiot: v.huomiot || [], osoite: 'https://' + a.domain, versio: paketit[0].versio });
        }
      });
    } finally {
      if (lahetys) fs.rmSync(lahetys.polku, { force: true });
    }
    return true;
  } catch (e) {
    if (!res.headersSent) virhe(e);
    return true;
  }
}

// ---- Rungolle annettavat tiedot (palvelinyhteys, palvelinylläpito ja yhteyden varmuuskopio)
function varaukset(dataDir) {
  const a = asetukset.haeAkveri(dataDir);
  return { domainit: [a.domain], portit: [a.portti] };
}
function palvelimet(dataDir) {
  const a = asetukset.haeAkveri(dataDir);
  const host = a.erillinenPalvelin ? a.palvelinHost : store.haeOletuspalvelin(dataDir).host;
  if (!host) return [];
  return [{ host, nimi: 'AKVERI', yhteys: async () => (await akveriYhteys(dataDir, asetukset.haeAkveriSalaisena(dataDir))).prof }];
}
function vieYhteys(dataDir) {
  const a = asetukset.haeAkveri(dataDir);
  return { erillinenPalvelin: !!a.erillinenPalvelin, palvelinHost: a.palvelinHost || '', palvelinPortti: a.palvelinPortti, palvelinKayttaja: a.palvelinKayttaja, palvelinSudo: !!a.palvelinSudo };
}
function tuoYhteys(dataDir, t) {
  if (!t) return '';
  asetukset.tallennaAkveri(dataDir, t.erillinenPalvelin ? t : { erillinenPalvelin: false });
  return t.erillinenPalvelin ? 'AKVERIn oma palvelin ' + t.palvelinHost : 'AKVERI samalla palvelimella';
}

module.exports = { kasittele, tuoMukanaTulevatPaketit, akveriYhteys, varaukset, palvelimet, vieYhteys, tuoYhteys };
