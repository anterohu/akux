// kayttajat.js — hallinnan (akveri.fi/hallinta) käyttäjät ja kutsut.
//
// Tiedosto omistaja.json: { kayttajat: { <id>: { nimi, sahkoposti, salasana, totp, viimeisinAskel, luotu, viimeksiKirjautunut } },
//                          kutsut: { <tunnuksen tiiviste>: { nimi, sahkoposti, vanhenee } } }
// Ensimmäinen käyttäjä luodaan alkutunnuksella (AKVERI_ALKUTUNNUS). Muut käyttäjät lisätään ja poistetaan Hallintatyökalusta,
// joka ajaa palvelimella komennon yllapito.js. Komento luo kertakäyttöisen kutsulinkin (24 h), jolla käyttäjä asettaa oman
// salasanansa ja kaksivaiheisen tunnistuksen. Verkosta ei voi lisätä käyttäjiä.
// Palvelin lukee tiedoston uudelleen jokaisessa tunnistuksessa, joten komentorivin muutokset (esim. poisto) tulevat voimaan heti.
'use strict';
const crypto = require('crypto');
const { tiiviste } = require('./varasto');

const KUTSU_MS = 24 * 3600000;
const SAHKOPOSTI = /^[^\s@<>()",;:]+@[^\s@<>()",;:]+\.[^\s@<>()",;:]{2,}$/;

function tiedot(varasto) {
  varasto.lataaUudelleen('omistaja');
  const o = varasto.get('omistaja');
  if (o.salasana) {
    // Aiempi yhden käyttäjän muoto: siirretään käyttäjäksi, jonka tunnus on "omistaja".
    o.kayttajat = { [crypto.randomBytes(8).toString('hex')]: { nimi: 'Omistaja', sahkoposti: 'omistaja', salasana: o.salasana, totp: o.totp, viimeisinAskel: o.viimeisinAskel || 0, luotu: o.luotu || null } };
    for (const k of ['salasana', 'totp', 'viimeisinAskel', 'luotu', 'viimeksiKirjautunut']) delete o[k];
    varasto.tallenna('omistaja');
  }
  if (!o.kayttajat || typeof o.kayttajat !== 'object') o.kayttajat = {};
  if (!o.kutsut || typeof o.kutsut !== 'object') o.kutsut = {};
  return o;
}
function normalisoiPosti(s) { return String(s || '').trim().toLowerCase(); }
function tarkistaPosti(s) {
  const p = normalisoiPosti(s);
  if (!SAHKOPOSTI.test(p) || p.length > 160) throw new Error('Sähköpostiosoite ei kelpaa.');
  return p;
}
function tarkistaNimi(s) {
  const n = String(s || '').trim().replace(/\s+/g, ' ');
  if (!/^[A-Za-zÅÄÖåäöÉéÜü0-9 .'-]{2,80}$/.test(n)) throw new Error('Nimessä saa olla kirjaimia, numeroita, välilyöntejä sekä merkit . - \' (2–80 merkkiä).');
  return n;
}
function haePostilla(o, posti) {
  const p = normalisoiPosti(posti);
  return Object.entries(o.kayttajat).find(([, k]) => k.sahkoposti === p) || null;
}
function siivoaKutsut(o, nyt) { for (const [k, v] of Object.entries(o.kutsut)) if (v.vanhenee < nyt) delete o.kutsut[k]; }

// Luo kertakäyttöisen kutsun. Palauttaa kutsutunnuksen (näytetään vain kerran, tallennetaan tiivisteenä).
function luoKutsu(varasto, { sahkoposti, nimi }, nyt = Date.now()) {
  const o = tiedot(varasto);
  const posti = tarkistaPosti(sahkoposti);
  const n = tarkistaNimi(nimi);
  if (haePostilla(o, posti)) throw new Error('Käyttäjä ' + posti + ' on jo olemassa.');
  siivoaKutsut(o, nyt);
  for (const [k, v] of Object.entries(o.kutsut)) if (v.sahkoposti === posti) delete o.kutsut[k]; // uusi kutsu korvaa vanhan
  const tunnus = crypto.randomBytes(32).toString('base64url');
  o.kutsut[tiiviste(tunnus)] = { nimi: n, sahkoposti: posti, vanhenee: nyt + KUTSU_MS };
  varasto.tallenna('omistaja');
  return tunnus;
}
function haeKutsu(varasto, tunnus, nyt = Date.now()) {
  if (!/^[A-Za-z0-9_-]{43}$/.test(String(tunnus || ''))) return null;
  const o = tiedot(varasto);
  const k = o.kutsut[tiiviste(tunnus)];
  return k && k.vanhenee >= nyt ? k : null;
}
function lisaaKayttaja(varasto, { nimi, sahkoposti, salasana, totp, askel, kutsu }, nyt = Date.now()) {
  const o = tiedot(varasto);
  if (haePostilla(o, sahkoposti)) throw new Error('Käyttäjä on jo olemassa.');
  if (kutsu) delete o.kutsut[tiiviste(kutsu)];
  const id = crypto.randomBytes(8).toString('hex');
  o.kayttajat[id] = { nimi, sahkoposti: normalisoiPosti(sahkoposti), salasana, totp, viimeisinAskel: askel || 0, luotu: new Date(nyt).toISOString() };
  varasto.tallenna('omistaja');
  return id;
}
function poista(varasto, sahkoposti) {
  const o = tiedot(varasto);
  const k = haePostilla(o, sahkoposti);
  if (!k) throw new Error('Käyttäjää ' + normalisoiPosti(sahkoposti) + ' ei löydy.');
  if (Object.keys(o.kayttajat).length === 1) throw new Error('Viimeistä käyttäjää ei voi poistaa. Lisää ensin toinen käyttäjä.');
  delete o.kayttajat[k[0]];
  varasto.tallenna('omistaja');
  return { nimi: k[1].nimi, sahkoposti: k[1].sahkoposti };
}
function lista(varasto, nyt = Date.now()) {
  const o = tiedot(varasto);
  return {
    kayttajat: Object.values(o.kayttajat).map(k => ({ nimi: k.nimi, sahkoposti: k.sahkoposti, luotu: k.luotu, viimeksiKirjautunut: k.viimeksiKirjautunut || null })),
    kutsut: Object.values(o.kutsut).filter(k => k.vanhenee >= nyt).map(k => ({ nimi: k.nimi, sahkoposti: k.sahkoposti, vanhenee: new Date(k.vanhenee).toISOString() }))
  };
}

module.exports = { tiedot, luoKutsu, haeKutsu, lisaaKayttaja, poista, lista, haePostilla, tarkistaPosti, tarkistaNimi, normalisoiPosti, KUTSU_MS };
