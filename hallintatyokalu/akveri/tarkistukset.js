// akveri/tarkistukset.js — AKVERIn laaduntarkistukset Hallintatyökalun AKVERI-lohkossa.
'use strict';
const fs = require('fs');
const path = require('path');

async function akveriErillisyysTesti() {
  const os = require('os');
  const crypto = require('crypto');
  const tulokset = [];
  const k = (nimi, ok, lisatieto) => tulokset.push({ nimi, ok: !!ok, lisatieto: ok ? undefined : lisatieto });
  const heittaa = (f) => { try { f(); return null; } catch (e) { return e.message; } };
  const store = require('./asetukset');
  const ak = require('./vienti');
  const pv = require('../palvelinvienti');
  const { rakennaKansioZip } = require('../public/kansio-zip');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vuoro-akveri-'));
  try {
    const p = ak.profiili({ host: 'palvelin.example.fi', portti: 22, kayttaja: 'root' }, '', { portti: 3090, domain: 'akveri.fi' });
    const yks = pv.valmisteluSkripti(p, { yksikko: ak.yksikko(p) });
    k('AKVERI ajetaan omalla käyttäjällä akveri', p.ajoKayttaja === 'akveri' && /User=akveri/.test(yks));
    k('AKVERI ei lue Vuoropisteen yhteisiä asetuksia', !/yhteinen\.env|LICENSE_FILE/.test(yks) && /akveri\/akveri\.env/.test(yks));
    k('AKVERIn palvelu on merkitty, joten Vuoropisteen ensisiivous ohittaa sen', /X-Palvelinyllapito-Rooli=akveri/.test(yks) && /X-Palvelinyllapito-Rooli=.*continue/.test(pv.siivoaVanhatAsennukset.toString()));
    const vuoro = pv.valmisteluSkripti({ ...p, palvelu: 'vuoro-x', ajoKayttaja: 'vuoro-x' }, {});
    k('Vuoropisteen palveluyksikkö on ennallaan', /yhteinen\.env/.test(vuoro) && !/X-Palvelinyllapito-Rooli/.test(vuoro));
    k('AKVERIn osoite ei voi olla toisen palvelun verkkotunnuksen alla', /toisen palvelun/.test(heittaa(() => store.tallennaAkveri(tmp, { domain: 'a.vuoropiste.fi' })) || ''));
    k('AKVERIn portti ei voi olla Vuoropisteen asiakkaiden alueella', /asiakkaille/.test(heittaa(() => store.tallennaAkveri(tmp, { portti: 3101 })) || ''));
    store.tallennaAkveri(tmp, { alkutunnus: 'z'.repeat(43) });
    const levylla = fs.readdirSync(tmp).map(f => { try { return fs.readFileSync(path.join(tmp, f), 'utf8'); } catch (e) { return ''; } }).join('');
    k('Hallinnan alkutunnus on salattu levyllä', !levylla.includes('z'.repeat(43)) && store.haeAkveriSalaisena(tmp).alkutunnus === 'z'.repeat(43));
    // Julkaisupaketti
    const tied = { 'server.js': 'x', 'package.json': JSON.stringify({ name: 'akveri-palvelin', version: '2.0.0' }), 'sivusto/index.html': 'x', 'lib/sovellus.js': 'x' };
    const m = { tuote: 'akveri-palvelin', versio: '2.0.0', tiedostot: {} };
    for (const [n, d] of Object.entries(tied)) m.tiedostot[n] = crypto.createHash('sha256').update(d).digest('hex');
    const zip = (muutos) => Buffer.from(rakennaKansioZip([{ nimi: 'manifest.json', data: JSON.stringify(m) }, ...Object.entries({ ...tied, ...(muutos || {}) }).map(([nimi, d]) => ({ nimi, data: d }))].map(o => ({ nimi: o.nimi, data: new TextEncoder().encode(o.data) }))));
    k('Kelvollinen AKVERI-palvelinpaketti hyväksytään', ak.lueJulkaisupaketti(zip()).versio === '2.0.0');
    k('Muutettu paketti hylätään', /tarkiste/.test(heittaa(() => ak.lueJulkaisupaketti(zip({ 'server.js': 'muutettu' }))) || ''));
    k('Paketti ei voi sisältää ylimääräisiä tiedostoja', /manifest/.test(heittaa(() => ak.lueJulkaisupaketti(zip({ 'lib/x.js': 'x' }))) || ''));
    // AKVERI-paketin mukana tuleva akveri.fi-palvelimen ohjelma kelpaa versiovarastoon
    const mukana = fs.existsSync(path.join(__dirname, 'palvelin')) ? fs.readdirSync(path.join(__dirname, 'palvelin')).filter(n => /^akveri-palvelin-\d+\.\d+\.\d+\.zip$/.test(n)) : [];
    k('AKVERI-paketin mukana on akveri.fi-palvelimen ohjelma, joka kelpaa versiovarastoon', mukana.length === 1 && !heittaa(() => ak.lueJulkaisupaketti(fs.readFileSync(path.join(__dirname, 'palvelin', mukana[0])))), mukana.length === 1 ? 'Palvelinpaketti ei kelpaa' : `Kansiossa akveri/palvelin pitää olla tasan yksi palvelinpaketti (nyt ${mukana.length})`);
    {
      // Saman version korjattu palvelinpaketti korvaa versiovarastoon aiemmin tallennetun, muuttumaton ei kirjoitu uudelleen.
      const { tuoMukanaTulevatPaketit } = require('./reitit');
      const mk = fs.mkdtempSync(path.join(tmp, 'mukana-'));
      fs.writeFileSync(path.join(mk, 'akveri-palvelin-2.0.0.zip'), zip());
      tuoMukanaTulevatPaketit(tmp, mk);
      const eka = fs.readFileSync(ak.paketinPolku(tmp, '2.0.0'));
      const tied2 = { ...tied, 'sivusto/index.html': 'korjattu' };
      const m2 = { tuote: 'akveri-palvelin', versio: '2.0.0', tiedostot: {} };
      for (const [n, d] of Object.entries(tied2)) m2.tiedostot[n] = crypto.createHash('sha256').update(d).digest('hex');
      const zip2 = Buffer.from(rakennaKansioZip([{ nimi: 'manifest.json', data: JSON.stringify(m2) }, ...Object.entries(tied2).map(([nimi, d]) => ({ nimi, data: d }))].map(o => ({ nimi: o.nimi, data: new TextEncoder().encode(o.data) }))));
      fs.writeFileSync(path.join(mk, 'akveri-palvelin-2.0.0.zip'), zip2);
      tuoMukanaTulevatPaketit(tmp, mk);
      const toka = fs.readFileSync(ak.paketinPolku(tmp, '2.0.0'));
      k('Saman version korjattu akveri.fi-palvelinpaketti päivittyy versiovarastoon', eka.equals(zip()) && toka.equals(zip2) && ak.listaaPaketit(tmp).length === 1);
    }
    k('Omien latausten nimet rajataan (ei polkuja)', !!heittaa(() => ak.tarkistaLatausnimi('../akveri.env')) && ak.tarkistaLatausnimi('AKVERI-asennus-2.0.0.exe'));
    k('Hallinnan käyttäjän kutsu tarkistaa sähköpostin ja nimen ennen palvelinkomentoa', (await ak.kayttajat(p, { domain: 'akveri.fi' }, 'lisaa', { sahkoposti: 'x; rm -rf /', nimi: 'X' })).ok === false && (await ak.kayttajat(p, { domain: 'akveri.fi' }, 'lisaa', { sahkoposti: 'a@b.fi', nimi: '$(id)' })).ok === false);
    k('AKVERIn oma palvelin vaatii kelvollisen osoitteen', /oman palvelimen osoite/.test(heittaa(() => store.tallennaAkveri(tmp, { erillinenPalvelin: true })) || '') && /ei kelpaa/.test(heittaa(() => store.tallennaAkveri(tmp, { erillinenPalvelin: true, palvelinHost: 'x y' })) || ''));
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
  return { ok: tulokset.every(t => t.ok), tulokset };
}

const TARKISTUKSET = [
  {
    id: 'akveri-erillisyys',
    tuote: 'akveri',
    nimi: 'AKVERI erillään Vuoropisteestä',
    kuvaus: 'Varmistaa, että AKVERI asennetaan Vuoropisteestä erilleen (oma käyttäjä, asetustiedosto, portti ja osoite, tarvittaessa oma palvelin), ettei Vuoropisteen ensisiivous koske siihen, että AKVERIn hallinnan käyttäjien lisäys ja poisto tarkistavat syötteet ennen palvelinkomentoa, että AKVERI-palvelimen julkaisupaketti tarkistetaan tiedostokohtaisesti ja että salaisuudet salataan. Käyttää väliaikaista tietokantaa.',
    kesto: 'alle sekunti',
    aja: async () => {
      const r = await akveriErillisyysTesti();
      const e = r.tulokset.filter(t => !t.ok).length;
      return { ok: r.ok, yhteenveto: r.ok ? `${r.tulokset.length} tarkistusta läpi` : `${e} / ${r.tulokset.length} tarkistusta epäonnistui`, tiedot: r };
    }
  },
];

module.exports = { TARKISTUKSET, akveriErillisyysTesti };
