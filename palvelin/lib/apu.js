// apu.js — HTTP-apufunktiot: JSON-vastaus, rungon luku kokorajalla, asiakkaan IP-osoite ja pyyntörajoitin.
'use strict';
const crypto = require('crypto');

function json(res, status, obj, otsakkeet = {}) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...otsakkeet });
  res.end(JSON.stringify(obj));
}

class Virhe extends Error {
  constructor(viesti, status = 400) { super(viesti); this.status = status; }
}

function lueRunko(req, max = 32 * 1024) {
  return new Promise((resolve, reject) => {
    const osat = []; let koko = 0; let katkaistu = false;
    req.on('data', d => {
      if (katkaistu) return;
      koko += d.length;
      if (koko > max) { katkaistu = true; reject(new Virhe('Pyyntö on liian suuri.', 413)); req.resume(); return; }
      osat.push(d);
    });
    req.on('end', () => { if (!katkaistu) resolve(Buffer.concat(osat)); });
    req.on('error', reject);
  });
}

async function lueJson(req, max) {
  const raaka = await lueRunko(req, max);
  if (!raaka.length) return {};
  try { const d = JSON.parse(raaka.toString('utf8')); if (d && typeof d === 'object' && !Array.isArray(d)) return d; } catch (e) { /* alla */ }
  throw new Virhe('Virheellinen pyyntö.');
}

// Luotetaan täsmälleen yhteen välityspalvelimeen (Caddy samalla koneella): sen lisäämä viimeinen arvo on asiakkaan osoite.
function ipOsoite(req, env) {
  if (env.LUOTETTU_PROXY === '1') {
    const x = String(req.headers['x-forwarded-for'] || '').split(',').pop().trim();
    if (x) return x;
  }
  return req.socket.remoteAddress || '?';
}

function luoRajoitin(nyt = () => Date.now()) {
  const kartta = new Map();
  return {
    // Palauttaa true, jos raja on jo täynnä (pyyntö hylätään).
    kayta(avain, raja, ikkunaMs) {
      const t = nyt();
      const lista = (kartta.get(avain) || []).filter(a => t - a < ikkunaMs);
      if (lista.length >= raja) { kartta.set(avain, lista); return true; }
      lista.push(t); kartta.set(avain, lista);
      if (kartta.size > 50000) for (const [k, v] of kartta) if (!v.some(a => t - a < ikkunaMs)) kartta.delete(k);
      return false;
    }
  };
}

function puhdista(s, max) {
  return String(s == null ? '' : s).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').trim().slice(0, max);
}
const yksiRivi = (s) => s.replace(/[\r\n]+/g, ' ');

// Tunnukset Crockfordin base32-aakkostolla (ei sekoittuvia merkkejä I, L, O, U).
const AAKKOSTO = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
function satunnaisTunnus(merkkeja) {
  const tavut = crypto.randomBytes(merkkeja);
  let s = '';
  for (let i = 0; i < merkkeja; i++) s += AAKKOSTO[tavut[i] & 31];
  return s;
}
function vakioaikainenVertailu(a, b) {
  const x = Buffer.from(String(a)), y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

module.exports = { json, Virhe, lueRunko, lueJson, ipOsoite, luoRajoitin, puhdista, yksiRivi, satunnaisTunnus, vakioaikainenVertailu, AAKKOSTO };
