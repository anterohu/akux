// varasto.js — AKVERI-palvelimen tiedot levyllä (DB_DIR). Ei ulkoisia riippuvuuksia.
//
// Tiedostot:
//   tilit.json        sovelluksen tilit (tunnus, avaimen tiiviste, luontiaika, tila)
//   testit.json       testiluvat ja niiden rekisteröidyt raportit
//   ostot.json        Google Play -ostot (tunnisteena ostotunnuksen tiiviste, jotta sama osto ei hyvity kahdesti)
//   viestit.json      yhteydenottolomakkeen viestit
//   asetukset.json    yhteystiedot, asiakirjat ja sivuston asetukset (hallinnassa muokattavat)
//   omistaja.json     hallinnan tunnus (salasanan tiiviste ja kaksivaiheisen tunnistuksen salaisuus)
//   tilasto.json      anonyymi mittausaineisto ohjelmiston kehittämiseen (ei tunnisteita, satunnainen järjestys)
//   kirjanpito.jsonl  krediittien kirjanpito: vain lisäyksiä, jokainen rivi ketjutettu edelliseen tiivisteellä
//
// Krediittisaldo lasketaan aina kirjanpidosta, ei tallenneta erikseen. Kirjanpitoa ei koskaan muokata:
// korjaukset tehdään uusina riveinä (esim. hyvitys tai Googlen peruma osto), jolloin jokainen muutos jäljittyy.
// Kirjoitukset tehdään väliaikaistiedoston ja uudelleennimeämisen kautta, joten keskeytys ei jätä puolikasta tiedostoa.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const TIEDOSTOT = ['tilit', 'testit', 'ostot', 'viestit', 'asetukset', 'omistaja', 'tilasto'];
const KIRJANPITO = 'kirjanpito.jsonl';
const VARMUUSKOPIOITA = 30;

function tiiviste(teksti) { return crypto.createHash('sha256').update(String(teksti)).digest('hex'); }

class Varasto {
  // varmuuskopiokansio: päivittäiset kopiot. Tuotannossa tietokansion ulkopuolella (AKVERI_VARMUUSKOPIOT), jotta
  // Hallintatyökalun ottama tietokansion kopio ei sisällä aiempia kopioita.
  constructor(kansio, { nyt = () => Date.now(), varmuuskopiokansio } = {}) {
    if (!kansio) throw new Error('Tietokansio puuttuu (DB_DIR).');
    this.kansio = path.resolve(kansio);
    this.varmuuskopiokansio = path.resolve(varmuuskopiokansio || path.join(this.kansio, 'varmuuskopiot'));
    this.nyt = nyt;
    fs.mkdirSync(this.kansio, { recursive: true, mode: 0o700 });
    this.data = {};
    for (const n of TIEDOSTOT) this.data[n] = this._lue(n);
    this.saldot = new Map();
    this.ketju = '';
    this.kirjanpitoEhja = true;
    this.kirjanpitoRiveja = 0;
    this._lataaKirjanpito();
  }

  _polku(nimi) { return path.join(this.kansio, nimi + '.json'); }
  _lue(nimi) {
    try { const d = JSON.parse(fs.readFileSync(this._polku(nimi), 'utf8')); return d && typeof d === 'object' ? d : {}; }
    catch (e) {
      if (e.code === 'ENOENT') return {};
      // Rikkinäistä tiedostoa ei ylikirjoiteta hiljaa: ohjelma ei käynnisty, ja syy näkyy lokissa.
      throw new Error(`Tiedosto ${nimi}.json on vioittunut (${e.message}). Palauta se varmuuskopiosta.`);
    }
  }
  _kirjoitaTiedosto(polku, sisalto) {
    const tmp = polku + '.uusi-' + process.pid;
    const fd = fs.openSync(tmp, 'w', 0o600);
    try { fs.writeSync(fd, sisalto); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(tmp, polku);
  }
  tallenna(nimi) {
    if (!TIEDOSTOT.includes(nimi)) throw new Error('Tuntematon tiedosto: ' + nimi);
    this._kirjoitaTiedosto(this._polku(nimi), JSON.stringify(this.data[nimi], null, 1) + '\n');
  }
  get(nimi) { return this.data[nimi]; }
  // Lukee tiedoston levyltä uudelleen (esim. ylläpitokomento on muuttanut sitä palvelimen ollessa käynnissä).
  lataaUudelleen(nimi) { if (TIEDOSTOT.includes(nimi)) this.data[nimi] = this._lue(nimi); return this.data[nimi]; }

  // ------------------------------------------------------------ kirjanpito
  _lataaKirjanpito() {
    let teksti = '';
    try { teksti = fs.readFileSync(path.join(this.kansio, KIRJANPITO), 'utf8'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    for (const rivi of teksti.split('\n')) {
      if (!rivi.trim()) continue;
      let r;
      try { r = JSON.parse(rivi); } catch (e) { this.kirjanpitoEhja = false; continue; }
      const { ketju, ...sisalto } = r;
      if (ketju !== tiiviste(this.ketju + JSON.stringify(sisalto))) this.kirjanpitoEhja = false;
      this.ketju = ketju || this.ketju;
      this.saldot.set(r.tili, (this.saldot.get(r.tili) || 0) + Number(r.muutos || 0));
      this.kirjanpitoRiveja++;
    }
  }
  // Lisää kirjanpitoon rivin ja palauttaa sen. muutos: +n tai -n krediittiä.
  kirjaa({ tili, muutos, syy, viite = '', tekija = 'jarjestelma', selite = '' }) {
    if (!Number.isInteger(muutos) || muutos === 0 || Math.abs(muutos) > 10000) throw new Error('Virheellinen krediittimuutos.');
    const sisalto = { aika: new Date(this.nyt()).toISOString(), tili, muutos, syy, viite, tekija, selite: String(selite).slice(0, 300) };
    const ketju = tiiviste(this.ketju + JSON.stringify(sisalto));
    const rivi = JSON.stringify({ ...sisalto, ketju }) + '\n';
    const fd = fs.openSync(path.join(this.kansio, KIRJANPITO), 'a', 0o600);
    try { fs.writeSync(fd, rivi); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    this.ketju = ketju;
    this.saldot.set(tili, (this.saldot.get(tili) || 0) + muutos);
    this.kirjanpitoRiveja++;
    return { ...sisalto, ketju };
  }
  saldo(tili) { return this.saldot.get(tili) || 0; }
  kirjanpito({ tili = null, raja = 200 } = {}) {
    let teksti = '';
    try { teksti = fs.readFileSync(path.join(this.kansio, KIRJANPITO), 'utf8'); } catch (e) { return []; }
    const rivit = [];
    for (const r of teksti.split('\n')) { if (!r.trim()) continue; try { const x = JSON.parse(r); if (!tili || x.tili === tili) rivit.push(x); } catch (e) { /* rikkinäinen rivi näkyy eheystarkistuksessa */ } }
    return rivit.slice(-raja).reverse();
  }

  // ------------------------------------------------------------ varmuuskopiot
  // Päivittäinen kopio kansioon <varmuuskopiokansio>/AAAA-KK-PP. Säilytetään 30 uusinta. Palauttaa luodun kansion nimen tai ''.
  varmuuskopioi(pakota = false) {
    const juuri = this.varmuuskopiokansio;
    fs.mkdirSync(juuri, { recursive: true, mode: 0o700 });
    const nimi = new Date(this.nyt()).toISOString().slice(0, 10) + (pakota ? '-' + new Date(this.nyt()).toISOString().slice(11, 19).replace(/:/g, '') : '');
    const kohde = path.join(juuri, nimi);
    if (fs.existsSync(kohde)) return '';
    const tmp = kohde + '.kesken';
    fs.rmSync(tmp, { recursive: true, force: true });
    fs.mkdirSync(tmp, { mode: 0o700 });
    for (const n of [...TIEDOSTOT.map(t => t + '.json'), KIRJANPITO]) {
      const lahde = path.join(this.kansio, n);
      if (fs.existsSync(lahde)) fs.copyFileSync(lahde, path.join(tmp, n));
    }
    fs.renameSync(tmp, kohde);
    const kaikki = fs.readdirSync(juuri).filter(n => /^\d{4}-\d{2}-\d{2}/.test(n) && !n.endsWith('.kesken')).sort();
    for (const vanha of kaikki.slice(0, Math.max(0, kaikki.length - VARMUUSKOPIOITA))) fs.rmSync(path.join(juuri, vanha), { recursive: true, force: true });
    return nimi;
  }
}

module.exports = { Varasto, tiiviste, TIEDOSTOT, KIRJANPITO };
