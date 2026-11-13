#!/usr/bin/env node
// kokoa.js — kokoaa AKVERI-palvelimen julkaisupaketin: akveri-palvelin-<versio>.zip
//
// Paketti viedään palvelimelle Hallintatyökalun AKVERI-välilehdeltä. Pakettiin tulee manifest.json, jossa on tuotteen nimi,
// versio ja jokaisen tiedoston SHA-256-tiiviste. Hallintatyökalu tarkistaa manifestin ennen vientiä, joten väärä tai
// vioittunut paketti ei päädy palvelimelle. Testit, data ja paikalliset tiedostot jätetään pois.
//
// Käyttö: node palvelin/kokoa.js [kohdekansio]   (oletus: palvelin/dist)
'use strict';
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');

const JUURI = __dirname;
const MUKAAN = ['server.js', 'yllapito.js', 'package.json', 'README.md', 'lib', 'sivusto'];

function listaa(rel) {
  const polku = path.join(JUURI, rel);
  const s = fs.statSync(polku);
  if (s.isFile()) return [rel];
  return fs.readdirSync(polku).sort().flatMap(n => listaa(rel + '/' + n));
}

const CRC = (() => { const t = new Int32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c; } return t; })();
function crc32(buf) { if (zlib.crc32) return zlib.crc32(buf) >>> 0; let c = -1; for (const b of buf) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ -1) >>> 0; }

// Zip-arkisto (deflate). Aikaleima kiinteä, joten sama sisältö tuottaa aina saman paketin.
function rakennaZip(tiedostot) {
  const osat = []; const keskus = []; let siirto = 0;
  const dosAika = 0, dosPvm = ((2026 - 1980) << 9) | (1 << 5) | 1;
  for (const { nimi, data } of tiedostot) {
    const n = Buffer.from(nimi, 'utf8');
    const pakattu = zlib.deflateRawSync(data, { level: 9 });
    const crc = crc32(data);
    const lh = Buffer.alloc(30);
    lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(0x0800, 6); lh.writeUInt16LE(8, 8);
    lh.writeUInt16LE(dosAika, 10); lh.writeUInt16LE(dosPvm, 12); lh.writeUInt32LE(crc, 14);
    lh.writeUInt32LE(pakattu.length, 18); lh.writeUInt32LE(data.length, 22); lh.writeUInt16LE(n.length, 26); lh.writeUInt16LE(0, 28);
    osat.push(lh, n, pakattu);
    const ch = Buffer.alloc(46);
    ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(0x0800, 8); ch.writeUInt16LE(8, 10);
    ch.writeUInt16LE(dosAika, 12); ch.writeUInt16LE(dosPvm, 14); ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(pakattu.length, 20);
    ch.writeUInt32LE(data.length, 24); ch.writeUInt16LE(n.length, 28); ch.writeUInt32LE((0o100644 << 16) >>> 0, 38); ch.writeUInt32LE(siirto, 42);
    keskus.push(ch, n);
    siirto += lh.length + n.length + pakattu.length;
  }
  const kk = Buffer.concat(keskus);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(tiedostot.length, 8); eocd.writeUInt16LE(tiedostot.length, 10);
  eocd.writeUInt32LE(kk.length, 12); eocd.writeUInt32LE(siirto, 16);
  return Buffer.concat([...osat, kk, eocd]);
}

function kokoa(kohde = path.join(JUURI, 'dist')) {
  const pkg = JSON.parse(fs.readFileSync(path.join(JUURI, 'package.json'), 'utf8'));
  const sovellus = fs.readFileSync(path.join(JUURI, '..', 'akux', '__init__.py'), 'utf8').match(/VERSIO\s*=\s*"([^"]+)"/);
  if (sovellus && sovellus[1] !== pkg.version) throw new Error(`Palvelimen versio ${pkg.version} ei vastaa sovelluksen versiota ${sovellus[1]}. Päivitä palvelin/package.json.`);
  const tiedostot = MUKAAN.flatMap(listaa).filter(n => !/(^|\/)(\.|data\/|dist\/|testit\/)/.test(n)).map(nimi => ({ nimi, data: fs.readFileSync(path.join(JUURI, nimi)) }));
  const manifest = {
    tuote: 'akveri-palvelin', versio: pkg.version, node: pkg.engines.node.replace(/[^0-9]/g, '') || '22',
    terveysPolku: '/api/v1/tila',
    tiedostot: Object.fromEntries(tiedostot.map(t => [t.nimi, crypto.createHash('sha256').update(t.data).digest('hex')]))
  };
  const zip = rakennaZip([{ nimi: 'manifest.json', data: Buffer.from(JSON.stringify(manifest, null, 2) + '\n') }, ...tiedostot]);
  fs.mkdirSync(kohde, { recursive: true });
  const polku = path.join(kohde, `akveri-palvelin-${pkg.version}.zip`);
  fs.writeFileSync(polku, zip);
  return { polku, versio: pkg.version, tiedostoja: tiedostot.length, koko: zip.length };
}

module.exports = { kokoa, rakennaZip };

if (require.main === module) {
  try { const t = kokoa(process.argv[2]); console.log(`Paketti valmis: ${t.polku} (${t.tiedostoja} tiedostoa, ${(t.koko / 1024).toFixed(0)} kt)`); }
  catch (e) { console.error(e.message); process.exit(1); }
}
