#!/usr/bin/env node
// etusivu.js — akveri.fi:n etusivu kolmella kielellä (suomi, englanti, ruotsi) yhdestä lähteestä.
// Muuta tekstit tähän ja aja: node etusivu.js  → kirjoittaa sivusto/index.html, sivusto/index-en.html ja sivusto/index-sv.html.
// Testi varmistaa, että tiedostot vastaavat tätä lähdettä.
'use strict';
const fs = require('fs');
const path = require('path');

const KIELET = {
  fi: {
    polku: '/', tiedosto: 'index.html', nimi: 'Suomi',
    otsikko: 'AKVERI – sähköauton akun kuntotesti puhelimella',
    kuvaus: 'Mittaa sähköauton akun kunto puhelimella ja saat raportin, jonka aitouden ostaja voi tarkistaa.',
    valikko: ['Näin se toimii', 'Hinta', 'Tarkista raportti', 'Yhteystiedot', 'Lataa sovellus'],
    ylaotsikko: 'Sähköauton akun kuntotesti',
    h1: 'Tiedä akun kunto ennen kauppaa.',
    johdanto: 'AKVERI mittaa sähköauton akun kunnon puhelimella. Saat selkeän raportin, jonka aitouden ostaja voi tarkistaa.',
    lataa: 'Lataa sovellus', play: 'Google Playsta', tarkistaNappi: 'Tarkista raportti', playTila: 'Android-sovellus · Google Play',
    esimerkki: 'Esimerkki', raportti: 'Raportti', kunto: 'Akun kunto', kapasiteetti: 'Käytettävissä', tunnus: 'Raportin tunnus', luku: ['93,7 %', '72,6 kWh'],
    perusteet: [['Mitattu autosta', 'Tulos tulee auton omista mittauksista, ei arviosta.'], ['Aito raportti', 'Ostaja tarkistaa raportin QR-koodilla.'], ['Ei kuukausimaksua', 'Maksat vain tekemäsi mittaukset.']],
    mitenOtsikko: 'Näin se toimii',
    vaiheet: [['Kytke lukulaite', 'Pieni lukulaite kytketään auton OBD-liitäntään ja yhdistetään puhelimeen.'], ['Tee mittaus', 'Sovellus neuvoo vaihe vaiheelta.'], ['Saat raportin', 'Raportissa on akun kunto ja QR-koodi, jolla ostaja voi tarkistaa sen.']],
    tarvitsetOtsikko: 'Mitä tarvitset',
    tarvitset: ['Android-puhelin (Android 10 tai uudempi)', 'OBDLink-lukulaite: MX+, LX, EX tai SX', 'Teslaan lisäksi mallille sopiva OBD-välikaapeli. Muissa merkeissä lukulaite kytketään suoraan.', 'Sähköauto, esimerkiksi:'],
    hintaOtsikko: 'Hinta',
    hinta: 'Sovellus on maksuton. Mittaukset maksetaan krediiteillä, jotka ostetaan sovelluksessa Google Playn kautta. Mittauksen hinta näkyy ennen kuin aloitat. Jos mittaus keskeytyy heti alussa, krediitit palautuvat automaattisesti.',
    hinnasto: 'Hinnat näkyvät sovelluksessa ennen ostoa.',
    tarkistaOtsikko: 'Tarkista raportti', tarkistaOhje: 'Skannaa raportin QR-koodi puhelimen kameralla, niin näet raportin tiedot AKVERIn palvelimelta. Jos koodi ei lue, kirjoita raportin tunnus tarkistussivulle.', tarkista: 'Kirjoita tunnus',
    polut: [['Mittaa akku', 'Myyjälle ja omistajalle', 'Lataa sovellus'], ['Tarkista raportti', 'Ostajalle', 'Skannaa QR-koodi']], valikkoNappi: 'Valikko',
    ala: ['Käyttöehdot', 'Tietosuojaseloste', 'Yhteystiedot'], ytunnus: 'Y-tunnus', kieliValikko: 'Kieli', alatunniste: 'Alatunniste', logo: 'AKVERI – etusivulle', paavalikko: 'Päävalikko'
  },
  en: {
    polku: '/en', tiedosto: 'index-en.html', nimi: 'English',
    otsikko: 'AKVERI – EV battery health check with your phone',
    kuvaus: 'Check an electric car battery with your phone and get a report that a buyer can verify.',
    valikko: ['How it works', 'Price', 'Verify a report', 'Contact', 'Get the app'],
    ylaotsikko: 'EV battery health check',
    h1: 'Know the battery before you buy.',
    johdanto: 'AKVERI checks the health of an electric car battery with your phone. You get a clear report that a buyer can verify.',
    lataa: 'Get the app', play: 'on Google Play', tarkistaNappi: 'Verify a report', playTila: 'Android app · Google Play',
    esimerkki: 'Example', raportti: 'Report', kunto: 'Battery health', kapasiteetti: 'Usable', tunnus: 'Report ID', luku: ['93.7 %', '72.6 kWh'],
    perusteet: [['Measured by the car', 'Results come from the car itself, not an estimate.'], ['Genuine report', 'Buyers verify the report with a QR code.'], ['No subscription', 'Pay only for the checks you run.']],
    mitenOtsikko: 'How it works',
    vaiheet: [['Plug in the reader', 'A small reader plugs into the car’s OBD port and connects to your phone.'], ['Run the check', 'The app guides you step by step.'], ['Get the report', 'The report shows battery health and a QR code the buyer can scan to verify it.']],
    tarvitsetOtsikko: 'What you need',
    tarvitset: ['Android phone (Android 10 or newer)', 'OBDLink reader: MX+, LX, EX or SX', 'For a Tesla, also an OBD adapter cable for the model. On other makes the reader plugs in directly.', 'An electric car, for example:'],
    hintaOtsikko: 'Price',
    hinta: 'The app is free. Checks are paid with credits that you buy in the app through Google Play. You see the price of a check before you start. If a check stops right at the start, the credits are returned automatically.',
    hinnasto: 'Prices are shown in the app before you buy.',
    tarkistaOtsikko: 'Verify a report', tarkistaOhje: 'Scan the QR code on the report with your phone camera to see the report details from the AKVERI server. If the code cannot be read, enter the report ID on the verification page.', tarkista: 'Enter report ID',
    polut: [['Check a battery', 'For sellers and owners', 'Get the app'], ['Verify a report', 'For buyers', 'Scan the QR code']], valikkoNappi: 'Menu',
    ala: ['Terms of use', 'Privacy policy', 'Contact'], ytunnus: 'Business ID', kieliValikko: 'Language', alatunniste: 'Footer', logo: 'AKVERI – home', paavalikko: 'Main menu'
  },
  sv: {
    polku: '/sv', tiedosto: 'index-sv.html', nimi: 'Svenska',
    otsikko: 'AKVERI – kontrollera elbilens batteri med telefonen',
    kuvaus: 'Kontrollera elbilens batteri med telefonen och få en rapport som köparen kan verifiera.',
    valikko: ['Så fungerar det', 'Pris', 'Kontrollera rapport', 'Kontakt', 'Ladda ner appen'],
    ylaotsikko: 'Batteritest för elbilar',
    h1: 'Känn till batteriet innan du köper.',
    johdanto: 'AKVERI mäter elbilens batterihälsa med telefonen. Du får en tydlig rapport som köparen kan verifiera.',
    lataa: 'Ladda ner appen', play: 'på Google Play', tarkistaNappi: 'Kontrollera rapport', playTila: 'Android-app · Google Play',
    esimerkki: 'Exempel', raportti: 'Rapport', kunto: 'Batterihälsa', kapasiteetti: 'Användbar', tunnus: 'Rapport-ID', luku: ['93,7 %', '72,6 kWh'],
    perusteet: [['Mätt av bilen', 'Resultatet kommer från bilens egna mätningar, inte en uppskattning.'], ['Äkta rapport', 'Köparen verifierar rapporten med en QR-kod.'], ['Ingen månadsavgift', 'Du betalar bara för de tester du gör.']],
    mitenOtsikko: 'Så fungerar det',
    vaiheet: [['Anslut läsaren', 'En liten läsare ansluts till bilens OBD-uttag och kopplas till telefonen.'], ['Gör testet', 'Appen guidar dig steg för steg.'], ['Få rapporten', 'Rapporten visar batterihälsan och en QR-kod som köparen kan skanna för att verifiera den.']],
    tarvitsetOtsikko: 'Det här behöver du',
    tarvitset: ['Android-telefon (Android 10 eller nyare)', 'OBDLink-läsare: MX+, LX, EX eller SX', 'För Tesla dessutom en OBD-adapterkabel för modellen. På andra märken ansluts läsaren direkt.', 'En elbil, till exempel:'],
    hintaOtsikko: 'Pris',
    hinta: 'Appen är gratis. Testerna betalas med krediter som du köper i appen via Google Play. Du ser testets pris innan du börjar. Om ett test avbryts direkt i början återförs krediterna automatiskt.',
    hinnasto: 'Priserna visas i appen innan du köper.',
    tarkistaOtsikko: 'Kontrollera en rapport', tarkistaOhje: 'Skanna QR-koden på rapporten med telefonens kamera, så ser du rapportens uppgifter från AKVERIs server. Om koden inte kan läsas, ange rapportkoden på kontrollsidan.', tarkista: 'Ange rapportkod',
    polut: [['Testa ett batteri', 'För säljare och ägare', 'Ladda ner appen'], ['Kontrollera en rapport', 'För köpare', 'Skanna QR-koden']], valikkoNappi: 'Meny',
    ala: ['Användarvillkor', 'Dataskydd', 'Kontakt'], ytunnus: 'FO-nummer', kieliValikko: 'Språk', alatunniste: 'Sidfot', logo: 'AKVERI – startsida', paavalikko: 'Huvudmeny'
  }
};
const MERKIT = ['Tesla', 'Hyundai', 'Kia', 'Nissan Leaf', 'Volkswagen ID.', 'Škoda Enyaq', 'Audi Q4 e-tron', 'Cupra Born'];
const JARJESTYS = ['fi', 'en', 'sv'];
// Alasivujen osoitteet kielittäin (sivut.js kirjoittaa sivut, server.js reitittää osoitteet).
const SIVUPOLUT = {
  tarkista: { fi: '/tarkista', en: '/en/verify', sv: '/sv/kontrollera' },
  yhteystiedot: { fi: '/yhteystiedot', en: '/en/contact', sv: '/sv/kontakt' },
  ehdot: { fi: '/ehdot', en: '/en/terms', sv: '/sv/villkor' },
  tietosuoja: { fi: '/tietosuoja', en: '/en/privacy', sv: '/sv/dataskydd' }
};
const LOGO = '<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="46.5" fill="none" stroke="currentColor" stroke-width="6"/><circle cx="50" cy="50" r="37" fill="none" stroke="currentColor" stroke-opacity=".38" stroke-width="1.8" stroke-dasharray="2 4"/><path d="M33 71 L50 28 L67 71" fill="none" stroke="currentColor" stroke-width="9" stroke-linejoin="round" stroke-linecap="round"/><line x1="40.5" y1="57" x2="59.5" y2="57" stroke="#6CC193" stroke-width="7.5" stroke-linecap="round"/></svg>';
const PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3.5v17a.5.5 0 0 0 .76.43l14-8.5a.5.5 0 0 0 0-.86l-14-8.5A.5.5 0 0 0 5 3.5z" fill="currentColor"/></svg>';
const e = (t) => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const IKONI_MITTAA = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2L4 14h7l-1 8 9-12h-7z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';
const IKONI_QR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 18h2v2h-2zM14 18h2v2h-2zM18 14h2v2h-2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';
// Puhelimessa yläpalkissa näkyvät kielivalinta ja valikkopainike; valikko avautuu painikkeesta (sivusto.js).
const valikkonappi = (t, kielet) => `<span class="kielet mobiili-kielet" role="group" aria-label="${e(t.kieliValikko)}">${kielet}</span><button class="valikkonappi" type="button" aria-expanded="false" aria-controls="paavalikko" aria-label="${e(t.valikkoNappi)}"><span></span><span></span><span></span></button>`;

function sivu(kieli) {
  const t = KIELET[kieli];
  const playNappi = (iso) => `<a class="play-nappi${iso ? ' iso' : ''}" data-play href="#lataa">${PLAY}<span><small>${e(t.lataa)}</small>${e(t.play)}</span></a>`;
  const playTila = `<p class="play-tila" data-play-tila><span class="piste"></span><span data-play-teksti>${e(t.playTila)}</span></p>`;
  const kielet = JARJESTYS.map(k => k === kieli
    ? `<a href="${KIELET[k].polku}" lang="${k}" aria-current="page">${k.toUpperCase()}</a>`
    : `<a href="${KIELET[k].polku}" lang="${k}" hreflang="${k}">${k.toUpperCase()}</a>`).join('');
  return `<!doctype html>
<html lang="${kieli}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${e(t.otsikko)}</title>
<meta name="description" content="${e(t.kuvaus)}">
${JARJESTYS.map(k => `<link rel="alternate" hreflang="${k}" href="https://akveri.fi${KIELET[k].polku}">`).join('\n')}
<link rel="icon" href="/logo.svg" type="image/svg+xml">
<link rel="stylesheet" href="/sivusto.css">
<script src="/sivusto.js" defer></script>
</head>
<body data-sivu="etusivu">
<div class="yla-tausta"><header class="leveys yla">
  <a class="logo" href="${t.polku}" aria-label="${e(t.logo)}">${LOGO}<span>AKVERI</span></a>
  ${valikkonappi(t, kielet)}
  <nav class="valikko" id="paavalikko" aria-label="${e(t.paavalikko)}"><a href="#miten">${e(t.valikko[0])}</a><a href="#hinta">${e(t.valikko[1])}</a><a href="#tarkista">${e(t.valikko[2])}</a><a href="${SIVUPOLUT.yhteystiedot[kieli]}">${e(t.valikko[3])}</a><span class="kielet" role="group" aria-label="${e(t.kieliValikko)}">${kielet}</span><a class="nappi pieni" href="#lataa">${e(t.valikko[4])}</a></nav>
</header></div>
<main>

<section class="leveys sankari">
  <div>
    <p class="ylaotsikko">${e(t.ylaotsikko)}</p>
    <h1>${e(t.h1)}</h1>
    <p class="johdanto">${e(t.johdanto)}</p>
    <div class="polut">
      <a class="polku ensisijainen" data-play-linkki href="#lataa">${IKONI_MITTAA}<b>${e(t.polut[0][0])}</b><span>${e(t.polut[0][1])}</span><em>${e(t.polut[0][2])} ›</em></a>
      <a class="polku" href="${SIVUPOLUT.tarkista[kieli]}">${IKONI_QR}<b>${e(t.polut[1][0])}</b><span>${e(t.polut[1][1])}</span><em>${e(t.polut[1][2])} ›</em></a>
    </div>
    ${playTila}
  </div>
  <div class="kortti raporttikuva" aria-label="${e(t.esimerkki)}">
    <div class="otsake"><span>${e(t.raportti)}</span><span class="merkki neutraali">${e(t.esimerkki)}</span></div>
    <div class="kunto"><span class="iso">${e(t.luku[0])}</span><span>${e(t.kunto)}</span></div>
    <div class="palkki" aria-hidden="true"><span></span></div>
    <div class="rivi"><span>${e(t.kapasiteetti)}</span><b>${e(t.luku[1])}</b></div>
    <div class="rivi"><span>${e(t.tunnus)}</span><b class="tunnus">AK-7H2QK-M4XPC</b></div>
  </div>
</section>

<section class="leveys perusteet">
${t.perusteet.map(([o, s]) => `  <div><b>${e(o)}</b><span>${e(s)}</span></div>`).join('\n')}
</section>

<section class="osio" id="miten"><div class="leveys">
  <h2>${e(t.mitenOtsikko)}</h2>
  <div class="ruudukko vaiheet">
${t.vaiheet.map(([o, s], i) => `    <div class="kortti"><span class="numero">${i + 1}</span><h3>${e(o)}</h3><p>${e(s)}</p></div>`).join('\n')}
  </div>
</div></section>

<section class="osio" id="lataa"><div class="leveys">
  <div class="kortti lataa">
    <div>
      <h2>${e(t.tarvitsetOtsikko)}</h2>
      <ul class="lista">
${t.tarvitset.map(r => `        <li>${e(r)}</li>`).join('\n')}
      </ul>
      <div class="merkit">${MERKIT.map(m => `<span>${e(m)}</span>`).join('')}</div>
    </div>
    <div class="lataa-toiminto">
      ${playNappi(true)}
      ${playTila}
    </div>
  </div>
</div></section>

<section class="osio" id="hinta"><div class="leveys">
  <h2>${e(t.hintaOtsikko)}</h2>
  <p class="selite">${e(t.hinta)}</p>
  <p class="selite"${kieli === 'fi' ? ' id="hinnasto"' : ''}>${e(t.hinnasto)}</p>
</div></section>

<section class="osio" id="tarkista"><div class="leveys">
  <h2>${e(t.tarkistaOtsikko)}</h2>
  <p class="selite">${e(t.tarkistaOhje)}</p>
  <p><a class="nappi toissijainen" href="${SIVUPOLUT.tarkista[kieli]}">${e(t.tarkista)}</a></p>
</div></section>

</main>
<footer class="ala">
  <div class="leveys">
    <div><b data-yt="nimi">[yrityksen nimi]</b><span data-yt-rivi="yTunnus"> · ${e(t.ytunnus)} <span data-yt="yTunnus"></span></span><br><span data-yt="osoite"></span></div>
    <nav aria-label="${e(t.alatunniste)}"><a href="${SIVUPOLUT.ehdot[kieli]}">${e(t.ala[0])}</a><a href="${SIVUPOLUT.tietosuoja[kieli]}">${e(t.ala[1])}</a><a href="${SIVUPOLUT.yhteystiedot[kieli]}">${e(t.ala[2])}</a></nav>
  </div>
</footer>
</body>
</html>
`;
}

function kaikki() { return JARJESTYS.map(k => ({ tiedosto: KIELET[k].tiedosto, sisalto: sivu(k) })); }

module.exports = { KIELET, JARJESTYS, SIVUPOLUT, LOGO, e, valikkonappi, kaikki };

if (require.main === module) {
  for (const s of kaikki()) fs.writeFileSync(path.join(__dirname, 'sivusto', s.tiedosto), s.sisalto);
  console.log('Etusivu kirjoitettu: ' + kaikki().map(s => s.tiedosto).join(', '));
}
