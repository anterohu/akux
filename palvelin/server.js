#!/usr/bin/env node
// server.js — akveri.fi: esittelysivusto, raportin tarkistus, sovelluksen krediittirajapinta ja omistajan hallinta.
// Ei ulkoisia riippuvuuksia (Node 22). Ajetaan omalla järjestelmäkäyttäjällä Caddyn takana (ks. README.md).
//
// Ympäristömuuttujat:
//   PORT                     kuunneltava portti (oletus 3200)
//   BIND_HOST                kuunneltava osoite (tuotannossa 127.0.0.1)
//   DB_DIR                   tietokansio (oletus ./data)
//   JULKINEN_OSOITE          esim. https://akveri.fi
//   LUOTETTU_PROXY=1         Caddy samalla koneella: asiakkaan IP-osoite otetaan X-Forwarded-For-otsakkeesta
//   AKVERI_ALKUTUNNUS        hallinnan tunnuksen kertaluonteinen luonti (Hallintatyökalu asettaa)
//   HALLINTA_SALLITUT_IP     valinnainen IP-rajaus hallinnalle (esim. "203.0.113.5, 198.51.100.0/24")
//   GOOGLE_PLAY_PAKETTI      Android-sovelluksen paketti (esim. fi.akveri.app)
//   GOOGLE_PALVELUTILI       polku Google Play -palvelutilin avaintiedostoon (JSON)
//   AKVERI_VARMUUSKOPIOT     päivittäisten varmuuskopioiden kansio (oletus DB_DIR/varmuuskopiot)
//   AKVERI_LATAUKSET         omien latausten kansio (oletus DB_DIR/lataukset)
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const { Varasto } = require('./lib/varasto');
const { GooglePlay } = require('./lib/google');
const { luoSovellusRajapinta } = require('./lib/sovellus');
const { luoHallinta } = require('./lib/hallinta');
const { json, luoRajoitin } = require('./lib/apu');

const VERSIO = (() => { try { return require('./package.json').version; } catch (e) { return ''; } })();
const SIVUSTO = path.join(__dirname, 'sivusto');
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8', '.webmanifest': 'application/manifest+json' };
const SIVUT = {
  '/': 'index.html', '/en': 'index-en.html', '/sv': 'index-sv.html', '/tarkista': 'tarkista.html', '/ehdot': 'ehdot.html', '/tietosuoja': 'tietosuoja.html',
  '/yhteystiedot': 'yhteystiedot.html', '/hallinta': 'hallinta.html', '/robots.txt': 'robots.txt'
};
const HALLINNAN_TIEDOSTOT = new Set(['hallinta.html', 'hallinta.js']);
// Huoltotilan aikana toimivat aina: hallinta, käyttöehdot, tietosuojaseloste (Google Playn vaatimus), sivuston tiedot ja tyylit.
const HUOLTO_AINA = new Set(['/hallinta', '/hallinta/', '/ehdot', '/tietosuoja', '/robots.txt']);
const HUOLTO_RESURSSI = /^\/[a-z0-9-]+\.(js|css|svg|png|ico|webmanifest)$/;
function huoltoSivu(viesti) {
  const e = (t) => String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  return `<!doctype html><html lang="fi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex"><title>Huoltokatko · Maintenance · Underhåll | AKVERI</title><link rel="icon" href="/logo.svg" type="image/svg+xml"><link rel="stylesheet" href="/sivusto.css"></head>
<body class="huoltosivu"><main class="leveys huolto"><h1>Huoltokatko</h1><p>${e(viesti)}</p><p lang="en">The service is temporarily down for maintenance. Please try again soon.</p><p lang="sv">Tjänsten är tillfälligt stängd för underhåll. Försök igen snart.</p></main></body></html>`;
}

function luoPalvelin({ env = process.env, nyt = () => Date.now(), haku } = {}) {
  env = { ...env, AKVERI_VERSIO: env.AKVERI_VERSIO || VERSIO };
  const varasto = new Varasto(env.DB_DIR || path.join(__dirname, 'data'), { nyt, varmuuskopiokansio: env.AKVERI_VARMUUSKOPIOT });
  const google = new GooglePlay({ paketti: env.GOOGLE_PLAY_PAKETTI, palvelutiliTiedosto: env.GOOGLE_PALVELUTILI, haku, nyt });
  const rajoitin = luoRajoitin(nyt);
  const sovellus = luoSovellusRajapinta({ varasto, google, env, nyt, rajoitin });
  const hallinta = luoHallinta({ varasto, sovellus, env, nyt, rajoitin });

  function staattinen(req, res, polku) {
    let nimi = SIVUT[polku];
    if (!nimi && /^\/v\/[A-Za-z0-9-]{10,20}$/.test(polku)) nimi = 'tarkista.html';
    if (!nimi && /^\/[a-z0-9-]+\.(js|css|svg|png|ico|webmanifest)$/.test(polku)) nimi = polku.slice(1);
    if (!nimi) { res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' }); return res.end(fs.readFileSync(path.join(SIVUSTO, '404.html'))); }
    if (HALLINNAN_TIEDOSTOT.has(nimi)) {
      if (!hallinta.sallittu(req)) { res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }); return res.end('Sivua ei löydy'); }
      res.setHeader('X-Robots-Tag', 'noindex, nofollow, noarchive');
      res.setHeader('Cache-Control', 'no-store');
    }
    const tiedosto = path.join(SIVUSTO, nimi);
    fs.readFile(tiedosto, (err, buf) => {
      if (err) { res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }); return res.end('Sivua ei löydy'); }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(tiedosto)] || 'application/octet-stream', 'Cache-Control': res.getHeader('Cache-Control') || 'no-cache' });
      res.end(req.method === 'HEAD' ? undefined : buf);
    });
  }

  const palvelin = http.createServer((req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Referrer-Policy', 'same-origin');
    res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    if (String(env.JULKINEN_OSOITE || '').startsWith('https://')) res.setHeader('Strict-Transport-Security', 'max-age=31536000');
    res.setHeader('Content-Security-Policy', "default-src 'self'; style-src 'self'; img-src 'self' data:; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'");
    let osoite;
    try { osoite = new URL(req.url || '/', 'http://x'); } catch (e) { res.writeHead(400); return res.end(); }
    const polku = osoite.pathname;
    const virhe = () => { if (!res.headersSent) json(res, 500, { virhe: 'Palvelinvirhe.' }); };
    // Huoltotila (akveri.fi/hallinta → Sivusto ja ehdot → Huoltotila)
    const huolto = hallinta.huoltotila();
    if (huolto.tila !== 'pois' && !HUOLTO_AINA.has(polku) && !HUOLTO_RESURSSI.test(polku) && !polku.startsWith('/api/hallinta/') && !polku.startsWith('/api/sivusto/')) {
      const sovellukselle = polku.startsWith('/api/v1/');
      if ((!sovellukselle || huolto.tila === 'kaikki') && !hallinta.kirjautunut(req)) {
        res.setHeader('Retry-After', '600');
        if (polku.startsWith('/api/')) return json(res, 503, { virhe: 'AKVERI-palvelu on tilapäisesti huollossa. Yritä hetken kuluttua uudelleen.', huolto: true });
        res.writeHead(503, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        return res.end(req.method === 'HEAD' ? undefined : huoltoSivu(huolto.viesti));
      }
    }
    if (polku.startsWith('/api/v1/')) return sovellus.kasittele(req, res, polku, osoite.searchParams).catch(virhe);
    if (polku.startsWith('/api/hallinta/')) return hallinta.kasittele(req, res, polku, osoite.searchParams).catch(virhe);
    if (polku.startsWith('/api/sivusto/')) return hallinta.kasitteleJulkinen(req, res, polku).catch(virhe);
    if (polku.startsWith('/api/')) return json(res, 404, { virhe: 'Tuntematon pyyntö.' });
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405, { Allow: 'GET, HEAD' }); return res.end(); }
    if (polku === '/hallinta/') { res.writeHead(302, { Location: '/hallinta' }); return res.end(); }
    staattinen(req, res, polku);
  });

  // Päivittäinen varmuuskopio tietokansioon ja Google Playssa perumisten tarkistus kahdesti vuorokaudessa.
  const ajastimet = [];
  function ajoitetut() {
    try { varasto.varmuuskopioi(); } catch (e) { console.error('[varmuuskopio]', e.message); }
    try { const s = hallinta.sailytysajat(); if (s.viestit || s.raportit || s.pyynnot) console.log('[säilytysajat] poistettu', JSON.stringify(s)); } catch (e) { console.error('[säilytysajat]', e.message); }
  }
  palvelin.kaynnista = () => {
    ajoitetut();
    ajastimet.push(setInterval(ajoitetut, 3 * 3600000));
    const perutut = () => sovellus.tarkistaPerutut().then(n => { if (n) console.log(`[google] perutuista ostoista vähennetty: ${n}`); }).catch(e => console.error('[google]', e.message));
    ajastimet.push(setTimeout(perutut, 60000));
    ajastimet.push(setInterval(perutut, 12 * 3600000));
    for (const a of ajastimet) a.unref();
  };
  palvelin.on('close', () => { for (const a of ajastimet) clearInterval(a); });
  palvelin.varasto = varasto;
  palvelin.sovellus = sovellus;
  palvelin.hallinta = hallinta;
  return palvelin;
}

module.exports = { luoPalvelin, VERSIO };

if (require.main === module) {
  const portti = Number(process.env.PORT || 3200);
  let palvelin;
  try { palvelin = luoPalvelin(); } catch (e) { console.error('AKVERI-palvelin ei käynnistynyt: ' + e.message); process.exit(1); }
  palvelin.listen(portti, process.env.BIND_HOST || '127.0.0.1', () => {
    palvelin.kaynnista();
    console.log(`AKVERI-palvelin ${VERSIO} käynnissä portissa ${portti}`);
    if (!process.env.JULKINEN_OSOITE) console.warn('VAROITUS: JULKINEN_OSOITE puuttuu, tarkistuslinkit käyttävät osoitetta https://akveri.fi.');
    if (!palvelin.sovellus.google.kaytossa) console.warn('VAROITUS: Google Play -ostojen tarkistus ei ole käytössä (GOOGLE_PLAY_PAKETTI tai GOOGLE_PALVELUTILI puuttuu).');
  });
  const sammuta = () => palvelin.close(() => process.exit(0));
  process.on('SIGTERM', sammuta);
  process.on('SIGINT', sammuta);
}
