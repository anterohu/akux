#!/usr/bin/env node
'use strict';
// Kokoaa Hallintatyökalun AKVERI-paketin akveri-<versio>.zip (Hallintatyökalu → AKVERI → Päivitys).
// Paketissa on Hallintatyökalun AKVERI-näkymän koodi (hallintatyokalu/akveri) ja akveri.fi-palvelimen paketti
// akveri/palvelin/akveri-palvelin-<versio>.zip, jonka AKVERI-näkymä tuo pakettilistaansa asennuksen jälkeen.
//   node palvelin/kokoa-oksa.js [kohdekansio]
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { kokoa, rakennaZip } = require('./kokoa');

const REPO = path.join(__dirname, '..');
const OKSA = path.join(REPO, 'hallintatyokalu', 'akveri');
const HT = 'myyja-tyokalut/hallintatyokalu/akveri/';
const VAATII_RUNKO = '1.0.0';

function listaa(kansio, rel = '') {
  return fs.readdirSync(path.join(kansio, rel), { withFileTypes: true }).flatMap(e => {
    const r = rel ? rel + '/' + e.name : e.name;
    return e.isDirectory() ? listaa(kansio, r) : [r];
  });
}

function kokoaOksa(kohde = path.join(__dirname, 'dist')) {
  const versio = require('./package.json').version;
  fs.mkdirSync(kohde, { recursive: true });
  const palvelin = kokoa(fs.mkdtempSync(path.join(require('os').tmpdir(), 'akveri-palvelin-')));
  const tiedostot = listaa(OKSA).filter(n => !n.startsWith('.')).sort().map(n => {
    let data = fs.readFileSync(path.join(OKSA, n));
    if (n === 'osa.json') data = Buffer.from(JSON.stringify({ ...JSON.parse(data), versio, vaatiiRunko: VAATII_RUNKO }, null, 2) + '\n');
    return { nimi: HT + n, data };
  });
  tiedostot.push({ nimi: HT + 'palvelin/' + path.basename(palvelin.polku), data: fs.readFileSync(palvelin.polku) });
  const manifest = { osa: 'akveri', nimi: 'AKVERI', versio, vaatiiRunko: VAATII_RUNKO, tiedostot: {} };
  for (const t of tiedostot) manifest.tiedostot[t.nimi] = crypto.createHash('sha256').update(t.data).digest('hex');
  const polku = path.join(kohde, `akveri-${versio}.zip`);
  fs.writeFileSync(polku, rakennaZip([{ nimi: 'manifest.json', data: Buffer.from(JSON.stringify(manifest, null, 2)) }, ...tiedostot]));
  fs.rmSync(path.dirname(palvelin.polku), { recursive: true, force: true });
  return { polku, versio, tiedostoja: tiedostot.length };
}

module.exports = { kokoaOksa };
if (require.main === module) {
  try { const t = kokoaOksa(process.argv[2]); console.log(`${t.polku} (${t.tiedostoja} tiedostoa)`); }
  catch (e) { console.error(e.message); process.exit(1); }
}
