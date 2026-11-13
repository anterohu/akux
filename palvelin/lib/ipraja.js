// portaali/ipraja.js — sallittujen IP-osoitteiden lista (esim. YLLAPITO_SALLITUT_IP="203.0.113.5, 198.51.100.0/24, 2001:db8::1").
// Tyhjä lista = ei rajausta. Tukee IPv4-osoitteita ja -aliverkkoja (CIDR) sekä täsmällisiä IPv6-osoitteita.
'use strict';
const net = require('net');

function v4Luvuksi(osoite) {
  const o = osoite.split('.').map(Number);
  return (((o[0] * 256 + o[1]) * 256 + o[2]) * 256 + o[3]) >>> 0;
}
// IPv4-osoite voi tulla muodossa ::ffff:1.2.3.4 (kaksoispinon pistoke).
function siivoa(osoite) {
  let a = String(osoite || '').trim().toLowerCase();
  if (a.startsWith('::ffff:') && net.isIPv4(a.slice(7))) a = a.slice(7);
  return a;
}

function jasenna(lista) {
  const saannot = [];
  for (const raaka of String(lista || '').split(',')) {
    const osa = raaka.trim().toLowerCase();
    if (!osa) continue;
    const [osoite, pituus] = osa.split('/');
    if (net.isIPv4(osoite)) {
      const n = pituus === undefined ? 32 : Number(pituus);
      if (!Number.isInteger(n) || n < 0 || n > 32) throw new Error(`Virheellinen aliverkko: ${osa}`);
      saannot.push({ v: 4, osoite: v4Luvuksi(osoite), n });
    } else if (net.isIPv6(osoite) && pituus === undefined) {
      saannot.push({ v: 6, teksti: new URL(`http://[${osoite}]/`).hostname });
    } else throw new Error(`Virheellinen IP-osoite: ${osa}`);
  }
  return saannot;
}

function sallittu(saannot, osoite) {
  if (!saannot.length) return true;
  const a = siivoa(osoite);
  if (net.isIPv4(a)) {
    const x = v4Luvuksi(a);
    return saannot.some(s => s.v === 4 && (s.n === 0 || (x >>> (32 - s.n)) === (s.osoite >>> (32 - s.n))));
  }
  if (net.isIPv6(a)) {
    const t = new URL(`http://[${a}]/`).hostname;
    return saannot.some(s => s.v === 6 && s.teksti === t);
  }
  return false;
}

module.exports = { jasenna, sallittu };
