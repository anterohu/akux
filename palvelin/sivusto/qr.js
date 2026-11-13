// Pieni, riippuvuudeton QR-koodin enkooderi (Byte-moodi, EC-taso L, versiot 1-10).
// Toteuttaa ISO/IEC 18004 -standardin QR-koodin luonnin puhtaana JS:na ilman ulkoisia
// kirjastoja tai verkkokutsuja (2FA-salaisuus ei koskaan poistu selaimesta).
'use strict';

// ---- GF(256) Reed-Solomon-apurit ----
const EXP_TABLE = new Array(256);
const LOG_TABLE = new Array(256);
for (let i = 0; i < 8; i++) EXP_TABLE[i] = 1 << i;
for (let i = 8; i < 256; i++) {
  EXP_TABLE[i] = EXP_TABLE[i - 4] ^ EXP_TABLE[i - 5] ^ EXP_TABLE[i - 6] ^ EXP_TABLE[i - 8];
}
for (let i = 0; i < 255; i++) LOG_TABLE[EXP_TABLE[i]] = i;
function glog(n) { if (n < 1) throw new Error('glog(' + n + ')'); return LOG_TABLE[n]; }
function gexp(n) { while (n < 0) n += 255; while (n >= 256) n -= 255; return EXP_TABLE[n]; }

class Poly {
  constructor(num, shift) {
    let offset = 0;
    while (offset < num.length && num[offset] === 0) offset++;
    this.num = new Array(num.length - offset + shift).fill(0);
    for (let i = 0; i < num.length - offset; i++) this.num[i] = num[offset + i];
  }
  get(i) { return this.num[i]; }
  get length() { return this.num.length; }
  multiply(e) {
    const num = new Array(this.length + e.length - 1).fill(0);
    for (let i = 0; i < this.length; i++) {
      for (let j = 0; j < e.length; j++) {
        num[i + j] ^= gexp(glog(this.get(i)) + glog(e.get(j)));
      }
    }
    return new Poly(num, 0);
  }
  mod(e) {
    if (this.length - e.length < 0) return this;
    const ratio = glog(this.get(0)) - glog(e.get(0));
    const num = this.num.slice();
    for (let i = 0; i < e.length; i++) num[i] ^= gexp(glog(e.get(i)) + ratio);
    return new Poly(num, 0).mod(e);
  }
}
function errorCorrectPoly(ecLen) {
  let a = new Poly([1], 0);
  for (let i = 0; i < ecLen; i++) a = a.multiply(new Poly([1, gexp(i)], 0));
  return a;
}

// ---- BCH-koodit muoto-/versiotiedolle (lasketaan, ei tarvitse hakutaulukkoa) ----
function bchDigit(data) { let d = 0; while (data !== 0) { d++; data >>>= 1; } return d; }
const G15 = 0b10100110111; // x^10+x^8+x^5+x^4+x^2+x+1
const G15_MASK = 0b101010000010010;
const G18 = 0b1111100100101; // x^12+x^11+x^10+x^9+x^8+x^5+x^2+1
function bchTypeInfo(data) {
  let d = data << 10;
  while (bchDigit(d) - bchDigit(G15) >= 0) d ^= (G15 << (bchDigit(d) - bchDigit(G15)));
  return ((data << 10) | d) ^ G15_MASK;
}
function bchTypeNumber(data) {
  let d = data << 12;
  while (bchDigit(d) - bchDigit(G18) >= 0) d ^= (G18 << (bchDigit(d) - bchDigit(G18)));
  return (data << 12) | d;
}

// ---- Versiotaulukko (versiot 1-10): [ecCodewordsPerBlock, [ [blocks, dataCodewords], ... ] ] ----
// EC-taso: 0=L, 1=M, 2=Q, 3=H (QR-standardin sisäinen järjestys formaatti-informaatiossa on eri,
// ks. FORMAT_EC_BITS alempana).
const RS_BLOCKS = {
  1: [[7, [[1, 19]]], [10, [[1, 16]]], [13, [[1, 13]]], [17, [[1, 9]]]],
  2: [[10, [[1, 34]]], [16, [[1, 28]]], [22, [[1, 22]]], [28, [[1, 16]]]],
  3: [[15, [[1, 55]]], [26, [[1, 44]]], [18, [[2, 17]]], [22, [[2, 13]]]],
  4: [[20, [[1, 80]]], [18, [[2, 32]]], [26, [[2, 24]]], [16, [[4, 9]]]],
  5: [[26, [[1, 108]]], [24, [[2, 43]]], [18, [[2, 15], [2, 16]]], [22, [[2, 11], [2, 12]]]],
  6: [[18, [[2, 68]]], [16, [[4, 27]]], [24, [[4, 19]]], [28, [[4, 15]]]],
  7: [[20, [[2, 78]]], [18, [[4, 31]]], [18, [[2, 14], [4, 15]]], [26, [[4, 13], [1, 14]]]],
  8: [[24, [[2, 97]]], [22, [[2, 38], [2, 39]]], [22, [[4, 18], [2, 19]]], [26, [[4, 14], [2, 15]]]],
  9: [[30, [[2, 116]]], [22, [[3, 36], [2, 37]]], [20, [[4, 16], [4, 17]]], [24, [[4, 12], [4, 13]]]],
  10: [[18, [[2, 68], [2, 69]]], [26, [[4, 43], [1, 44]]], [24, [[6, 19], [2, 20]]], [28, [[6, 15], [2, 16]]]]
};
// Formaatti-informaation EC-tason bitit (QR-standardi): L=01, M=00, Q=11, H=10.
const FORMAT_EC_BITS = { L: 0b01, M: 0b00, Q: 0b11, H: 0b10 };
const EC_INDEX = { L: 0, M: 1, Q: 2, H: 3 };
// Jäljelle jäävät "remainder"-bitit datan sijoituksen jälkeen, versioittain.
const REMAINDER_BITS = { 1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0 };
// Kohdistuskuvioiden (alignment pattern) keskipisteet versioittain (versio 1:llä ei ole yhtään).
const ALIGNMENT_POSITIONS = {
  2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
  7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]
};
// Palauttaa TODELLISET kohdistuskuvioiden keskipisteet (rivi,sarake) versiolle — kaikki
// positio-listan risteytykset PAITSI ne kolme jotka osuisivat finder-kuvioiden päälle
// (vasen yläkulma, oikea yläkulma, vasen alakulma). Tätä samaa listaa käyttävät sekä
// matriisin rakennus (buildMatrix) että isFunctionModule — jos nämä kaksi olisivat
// erilliset/epäjohdonmukaiset (kuten aiemmassa versiossa), maskaus rikkoisi datan vaikka
// itse kuvio näyttäisi rakenteellisesti oikealta.
function validAlignmentCenters(version) {
  const positions = ALIGNMENT_POSITIONS[version] || [];
  if (!positions.length) return [];
  const first = positions[0];
  const last = positions[positions.length - 1];
  const centers = [];
  for (const r of positions) {
    for (const c of positions) {
      const isTopLeft = (r === first && c === first);
      const isTopRight = (r === first && c === last);
      const isBottomLeft = (r === last && c === first);
      if (isTopLeft || isTopRight || isBottomLeft) continue;
      centers.push([r, c]);
    }
  }
  return centers;
}

function byteCapacity(version, level) {
  const blocks = RS_BLOCKS[version][EC_INDEX[level]][1];
  let totalData = 0;
  for (const [count, dataLen] of blocks) totalData += count * dataLen;
  // Byte-moodi: 4-bittinen moodi-indikaattori + merkkimäärä-indikaattori (8 bittiä versioille <10,
  // 16 bittiä versioille >=10) + itse data-tavut. Palautetaan käytettävissä oleva tavumäärä datalle.
  const countBits = version < 10 ? 8 : 16;
  const headerBits = 4 + countBits;
  return Math.floor((totalData * 8 - headerBits) / 8);
}

function pickVersion(byteLength, level) {
  for (let v = 1; v <= 10; v++) {
    if (byteCapacity(v, level) >= byteLength) return v;
  }
  throw new Error('Data on liian pitkä QR-koodiksi tuetuilla versioilla (1-10): ' + byteLength + ' tavua.');
}

function utf8Bytes(str) {
  return Array.from(typeof Buffer !== 'undefined' ? Buffer.from(str, 'utf8') : new TextEncoder().encode(str));
}

class BitBuffer {
  constructor() { this.buffer = []; this.length = 0; }
  get(index) { return ((this.buffer[Math.floor(index / 8)] >>> (7 - index % 8)) & 1) === 1; }
  put(num, length) { for (let i = 0; i < length; i++) this.putBit(((num >>> (length - i - 1)) & 1) === 1); }
  putBit(bit) {
    const bufIndex = Math.floor(this.length / 8);
    if (this.buffer.length <= bufIndex) this.buffer.push(0);
    if (bit) this.buffer[bufIndex] |= (0x80 >>> (this.length % 8));
    this.length++;
  }
}

function createData(version, level, bytes) {
  const buf = new BitBuffer();
  buf.put(0b0100, 4); // Byte-moodin indikaattori
  const countBits = version < 10 ? 8 : 16;
  buf.put(bytes.length, countBits);
  for (const b of bytes) buf.put(b, 8);

  const blocks = RS_BLOCKS[version][EC_INDEX[level]][1];
  let totalDataCodewords = 0;
  for (const [count, dataLen] of blocks) totalDataCodewords += count * dataLen;
  const totalDataBits = totalDataCodewords * 8;

  // Terminaattori (enintään 4 nollabittiä, tai vähemmän jos tila loppuu).
  if (buf.length + 4 <= totalDataBits) buf.put(0, 4);
  while (buf.length % 8 !== 0) buf.putBit(false);
  // Täyteaskeleet 0xEC/0x11 vuorotellen kunnes data-alue on täynnä.
  const padBytes = [0xEC, 0x11];
  let padIndex = 0;
  while (buf.length < totalDataBits) { buf.put(padBytes[padIndex % 2], 8); padIndex++; }

  // Pura bittipuskuri tavuiksi.
  const dataCodewords = [];
  for (let i = 0; i < totalDataCodewords; i++) {
    let byte = 0;
    for (let b = 0; b < 8; b++) byte = (byte << 1) | (buf.get(i * 8 + b) ? 1 : 0);
    dataCodewords.push(byte);
  }

  // Jaa datatavut lohkoihin ja laske jokaiselle Reed-Solomon-virheenkorjaustavut.
  const ecCodewordsPerBlock = RS_BLOCKS[version][EC_INDEX[level]][0];
  const rsPoly = errorCorrectPoly(ecCodewordsPerBlock);
  const dataBlocks = [];
  const ecBlocks = [];
  let offset = 0;
  for (const [count, dataLen] of blocks) {
    for (let i = 0; i < count; i++) {
      const blockData = dataCodewords.slice(offset, offset + dataLen);
      offset += dataLen;
      dataBlocks.push(blockData);
      const rawPoly = new Poly(blockData, ecCodewordsPerBlock);
      const modPoly = rawPoly.mod(rsPoly);
      const ec = new Array(ecCodewordsPerBlock).fill(0);
      for (let i2 = 0; i2 < ec.length; i2++) {
        const idx = i2 + modPoly.length - ec.length;
        ec[i2] = idx >= 0 ? modPoly.get(idx) : 0;
      }
      ecBlocks.push(ec);
    }
  }

  // Lomita lohkot standardin mukaisesti (sarake kerrallaan yli kaikkien lohkojen).
  const maxDataLen = Math.max(...dataBlocks.map(b => b.length));
  const finalBytes = [];
  for (let i = 0; i < maxDataLen; i++) {
    for (const block of dataBlocks) if (i < block.length) finalBytes.push(block[i]);
  }
  for (let i = 0; i < ecCodewordsPerBlock; i++) {
    for (const block of ecBlocks) finalBytes.push(block[i]);
  }

  const finalBuf = new BitBuffer();
  for (const byte of finalBytes) finalBuf.put(byte, 8);
  for (let i = 0; i < REMAINDER_BITS[version]; i++) finalBuf.putBit(false);
  return finalBuf;
}

function isFunctionModule(moduleCount, version, row, col) {
  // Finder-kuviot + erottimet (3 kulmaa, 9x9-alue kussakin).
  if (row < 8 && col < 8) return true;
  if (row < 8 && col >= moduleCount - 8) return true;
  if (row >= moduleCount - 8 && col < 8) return true;
  // Ajastuskuviot.
  if (row === 6 || col === 6) return true;
  // Kohdistuskuviot (vain todelliset keskipisteet — ei finder-kulmien kanssa päällekkäiset).
  for (const [r, c] of validAlignmentCenters(version)) {
    if (Math.abs(row - r) <= 2 && Math.abs(col - c) <= 2) return true;
  }
  // Tumma moduuli.
  if (row === 4 * version + 9 && col === 8) return true;
  // Formaatti-informaatioalueet.
  if ((row === 8 && (col < 9 || col >= moduleCount - 8)) || (col === 8 && (row < 9 || row >= moduleCount - 7))) return true;
  // Versiotietoalueet (versio >= 7).
  if (version >= 7) {
    if (row < 6 && col >= moduleCount - 11 && col < moduleCount - 8) return true;
    if (col < 6 && row >= moduleCount - 11 && row < moduleCount - 8) return true;
  }
  return false;
}

function buildMatrix(version, level, bitBuffer) {
  const moduleCount = 17 + 4 * version;
  const modules = Array.from({ length: moduleCount }, () => new Array(moduleCount).fill(null));

  function setFinder(row, col) {
    for (let r = -1; r <= 7; r++) {
      for (let c = -1; c <= 7; c++) {
        if (row + r < 0 || row + r >= moduleCount || col + c < 0 || col + c >= moduleCount) continue;
        const dark = (r >= 0 && r <= 6 && (c === 0 || c === 6)) ||
                     (c >= 0 && c <= 6 && (r === 0 || r === 6)) ||
                     (r >= 2 && r <= 4 && c >= 2 && c <= 4);
        modules[row + r][col + c] = dark;
      }
    }
  }
  setFinder(0, 0);
  setFinder(0, moduleCount - 7);
  setFinder(moduleCount - 7, 0);

  // Ajastuskuviot.
  for (let i = 8; i < moduleCount - 8; i++) {
    if (modules[6][i] === null) modules[6][i] = (i % 2 === 0);
    if (modules[i][6] === null) modules[i][6] = (i % 2 === 0);
  }

  // Kohdistuskuviot (sama todellinen keskipistelista kuin isFunctionModule käyttää).
  for (const [r, c] of validAlignmentCenters(version)) {
    for (let dr = -2; dr <= 2; dr++) {
      for (let dc = -2; dc <= 2; dc++) {
        const dark = Math.max(Math.abs(dr), Math.abs(dc)) !== 1;
        modules[r + dr][c + dc] = dark;
      }
    }
  }

  // Tumma moduuli (aina tumma).
  modules[4 * version + 9][8] = true;

  // TÄRKEÄÄ: varataan formaatti-/versiotietoalueet (asetetaan väliaikaisesti false) ENNEN
  // datan sijoittelua, jotta siksak-algoritmi ei vahingossa täytä niitä data-biteillä — nämä
  // alueet eivät koskaan ole osa data-zigzagia, ja niiden lopulliset arvot kirjoitetaan vasta
  // maskauksen jälkeen (eivätkä ne koskaan käy maskauksen läpi).
  for (let row = 0; row < moduleCount; row++) {
    for (let c = 0; c < moduleCount; c++) {
      if (modules[row][c] !== null) continue;
      if (isFunctionModule(moduleCount, version, row, c)) modules[row][c] = false;
    }
  }

  // Data + EC-bittien sijoitus siksak-kuvioon oikealta vasemmalle, pariskaraokoiden mukaan,
  // hypäten pystysuoran ajastuspylvään (sarake 6) yli.
  let bitIndex = 0;
  let dir = -1; // ylöspäin
  let col = moduleCount - 1;
  while (col > 0) {
    if (col === 6) col--;
    for (let count = 0; count < moduleCount; count++) {
      const row = dir === -1 ? moduleCount - 1 - count : count;
      for (let c = 0; c < 2; c++) {
        const cc = col - c;
        if (modules[row][cc] !== null) continue; // funktiomoduuli, ei kosketa
        let bit = false;
        if (bitIndex < bitBuffer.length) bit = bitBuffer.get(bitIndex);
        bitIndex++;
        modules[row][cc] = bit;
      }
    }
    dir = -dir;
    col -= 2;
  }

  // Maski (kiinteä maski 0: (row+col)%2===0 kääntää bitin) — sovelletaan vain datamoduuleihin.
  for (let row = 0; row < moduleCount; row++) {
    for (let c = 0; c < moduleCount; c++) {
      if (isFunctionModule(moduleCount, version, row, c)) continue;
      if ((row + c) % 2 === 0) modules[row][c] = !modules[row][c];
    }
  }

  // Formaatti-informaatio (EC-taso + maskinumero 0), sijoitetaan kahteen paikkaan standardin
  // ISO/IEC 18004 tarkkojen koordinaattien mukaan (ei laskettuna kaavalla — liian virhealtis).
  const formatData = (FORMAT_EC_BITS[level] << 3) | 0;
  const formatBits = bchTypeInfo(formatData);
  // Kopio A: vaakasuora rivi8 sarakkeissa 0-5,7,8 (i=0..7) + pystysuora sarake8 riveissä 7,5,4,3,2,1,0 (i=8..14).
  const copyA = [
    [8, 0], [8, 1], [8, 2], [8, 3], [8, 4], [8, 5], [8, 7], [8, 8],
    [7, 8], [5, 8], [4, 8], [3, 8], [2, 8], [1, 8], [0, 8]
  ];
  // Kopio B: pystysuora sarake8 riveissä moduleCount-1..moduleCount-7 (i=0..6) +
  // vaakasuora rivi8 sarakkeissa moduleCount-8..moduleCount-1 (i=7..14).
  const copyB = [
    [moduleCount - 1, 8], [moduleCount - 2, 8], [moduleCount - 3, 8], [moduleCount - 4, 8],
    [moduleCount - 5, 8], [moduleCount - 6, 8], [moduleCount - 7, 8],
    [8, moduleCount - 8], [8, moduleCount - 7], [8, moduleCount - 6], [8, moduleCount - 5],
    [8, moduleCount - 4], [8, moduleCount - 3], [8, moduleCount - 2], [8, moduleCount - 1]
  ];
  for (let i = 0; i < 15; i++) {
    const bit = ((formatBits >> (14 - i)) & 1) === 1;
    modules[copyA[i][0]][copyA[i][1]] = bit;
    modules[copyB[i][0]][copyB[i][1]] = bit;
  }
  modules[moduleCount - 8][8] = true; // aina tumma moduuli (erillään formaatti-informaatiosta)

  // Versiotieto (vain versio >= 7).
  if (version >= 7) {
    const versionBits = bchTypeNumber(version);
    for (let i = 0; i < 18; i++) {
      const bit = ((versionBits >> i) & 1) === 1;
      const a = Math.floor(i / 3);
      const b = i % 3;
      modules[a][moduleCount - 11 + b] = bit;
      modules[moduleCount - 11 + b][a] = bit;
    }
  }

  return { moduleCount, modules: modules.map(row => row.map(v => !!v)) };
}

function generateQRMatrix(text, level) {
  level = level || 'L';
  const bytes = utf8Bytes(text);
  const version = pickVersion(bytes.length, level);
  const bitBuffer = createData(version, level, bytes);
  return buildMatrix(version, level, bitBuffer);
}

// Piirtää matriisin inline-SVG-merkkijonoksi (moduulikoko + hiljainen reuna moduuleina).
// Ei ulkoisia riippuvuuksia eikä verkkokutsuja — kaikki pysyy selaimen omassa DOM:issa.
function qrMatrixToSvg(text, opts) {
  opts = opts || {};
  const level = opts.level || 'L';
  const moduleSize = opts.moduleSize || 5;
  const quiet = opts.quietModules === undefined ? 4 : opts.quietModules;
  const { moduleCount, modules } = generateQRMatrix(text, level);
  const size = (moduleCount + quiet * 2) * moduleSize;
  let rects = '';
  for (let r = 0; r < moduleCount; r++) {
    for (let c = 0; c < moduleCount; c++) {
      if (!modules[r][c]) continue;
      const x = (c + quiet) * moduleSize;
      const y = (r + quiet) * moduleSize;
      rects += `<rect x="${x}" y="${y}" width="${moduleSize}" height="${moduleSize}"/>`;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" shape-rendering="crispEdges" role="img" aria-label="${opts.label || 'QR-koodi'}"><rect width="${size}" height="${size}" fill="#fff"/><g fill="#000">${rects}</g></svg>`;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { generateQRMatrix, qrMatrixToSvg };
}
if (typeof window !== 'undefined') {
  window.QR = { generateQRMatrix, qrMatrixToSvg };
}
