#!/usr/bin/env node
// yllapito.js — AKVERI-palvelimen ylläpitokomennot. Hallintatyökalu ajaa näitä palvelimella AKVERIn omalla käyttäjällä.
//   node yllapito.js lisaa-kayttaja <sähköposti> "<Nimi>"   kertakäyttöinen kutsulinkki hallintaan (24 h)
//   node yllapito.js poista-kayttaja <sähköposti>          poistaa käyttäjän, kirjautuminen katkeaa heti
//   node yllapito.js lista-kayttajat                       käyttäjät ja voimassa olevat kutsut (JSON)
// Tietokansio: DB_DIR. Osoite kutsulinkkiin: JULKINEN_OSOITE.
'use strict';
const path = require('path');
const { Varasto } = require('./lib/varasto');
const kayttajat = require('./lib/kayttajat');

function suorita(argv, { env = process.env, ulos = (s) => console.log(s), nyt = () => Date.now() } = {}) {
  const varasto = new Varasto(env.DB_DIR || path.join(__dirname, 'data'), { nyt });
  const [komento, a, b] = argv;
  const osoite = String(env.JULKINEN_OSOITE || 'https://akveri.fi').replace(/\/+$/, '');
  switch (komento) {
    case 'lisaa-kayttaja': {
      const tunnus = kayttajat.luoKutsu(varasto, { sahkoposti: a, nimi: b }, nyt());
      ulos(`KUTSU=${osoite}/hallinta#kutsu=${tunnus}`);
      return 0;
    }
    case 'poista-kayttaja': {
      const k = kayttajat.poista(varasto, a);
      ulos(`Poistettu: ${k.nimi} <${k.sahkoposti}>`);
      return 0;
    }
    case 'lista-kayttajat':
      ulos(JSON.stringify(kayttajat.lista(varasto, nyt())));
      return 0;
    default:
      throw new Error('Tuntematon komento. Komennot: lisaa-kayttaja, poista-kayttaja, lista-kayttajat.');
  }
}

module.exports = { suorita };

if (require.main === module) {
  try { process.exitCode = suorita(process.argv.slice(2)); }
  catch (e) { console.error(e.message); process.exitCode = 2; }
}
