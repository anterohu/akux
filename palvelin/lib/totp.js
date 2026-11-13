// totp.js — kaksivaiheinen tunnistautuminen (TOTP, RFC 6238). Sama toteutus kuin vuoropiste.fi-portaalissa (kopio, ei yhteistä koodia tuotteiden välillä).
// Sama menetelmä kuin varausjärjestelmän totp.js, mutta tarkistus palauttaa käytetyn aika-askeleen,
// jotta jo käytettyä koodia ei voi käyttää uudelleen (toistohyökkäyksen esto).
'use strict';
const crypto = require('crypto');

const AAKKOSTO = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

function base32(buf) {
  let bitit = '';
  for (const tavu of buf) bitit += tavu.toString(2).padStart(8, '0');
  let ulos = '';
  for (let i = 0; i + 5 <= bitit.length; i += 5) ulos += AAKKOSTO[parseInt(bitit.substr(i, 5), 2)];
  return ulos;
}
function base32Pura(s) {
  let bitit = '';
  for (const m of String(s || '').toUpperCase().replace(/[^A-Z2-7]/g, '')) bitit += AAKKOSTO.indexOf(m).toString(2).padStart(5, '0');
  const tavut = [];
  for (let i = 0; i + 8 <= bitit.length; i += 8) tavut.push(parseInt(bitit.substr(i, 8), 2));
  return Buffer.from(tavut);
}
function luoSalaisuus() { return base32(crypto.randomBytes(20)); } // 160 bittiä, 32 merkkiä

function hotp(salaisuus, laskuri) {
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(laskuri));
  const h = crypto.createHmac('sha1', base32Pura(salaisuus)).update(buf).digest();
  const o = h[h.length - 1] & 0xf;
  const koodi = ((h[o] & 0x7f) << 24) | ((h[o + 1] & 0xff) << 16) | ((h[o + 2] & 0xff) << 8) | (h[o + 3] & 0xff);
  return String(koodi % 1000000).padStart(6, '0');
}
const askel = (at) => Math.floor(Math.floor(at / 1000) / 30);
function koodiNyt(salaisuus, at = Date.now()) { return hotp(salaisuus, askel(at)); }

// Palauttaa täsmäävän aika-askeleen tai null. Sallitaan ±1 askel (±30 s) kellopoikkeamalle.
function tarkistaKoodi(salaisuus, koodi, at = Date.now()) {
  if (!salaisuus || !/^\d{6}$/.test(String(koodi || ''))) return null;
  const nyt = askel(at);
  for (let w = -1; w <= 1; w++) {
    const odotettu = Buffer.from(hotp(salaisuus, nyt + w));
    if (crypto.timingSafeEqual(odotettu, Buffer.from(String(koodi)))) return nyt + w;
  }
  return null;
}

function otpauthUrl({ salaisuus, tili, myontaja }) {
  const e = encodeURIComponent;
  return `otpauth://totp/${e(myontaja)}:${e(tili)}?secret=${salaisuus}&issuer=${e(myontaja)}&algorithm=SHA1&digits=6&period=30`;
}

module.exports = { luoSalaisuus, koodiNyt, tarkistaKoodi, otpauthUrl, base32, base32Pura };
