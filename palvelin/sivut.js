#!/usr/bin/env node
// sivut.js — akveri.fi:n alasivut (raportin tarkistus, yhteystiedot, käyttöehdot, tietosuojaseloste) kolmella kielellä.
// Yläpalkki, kielivalinta ja alatunniste ovat samat kuin etusivulla (etusivu.js). Muuta tekstit tähän ja aja:
//   node sivut.js  → kirjoittaa sivusto/<sivu>.html, <sivu>-en.html ja <sivu>-sv.html.
// Testi varmistaa, että tiedostot vastaavat tätä lähdettä.
//
// Käyttöehdot ja tietosuojaseloste: hallinnassa muokattu teksti korvaa suomenkielisen oletustekstin. Englannin- ja
// ruotsinkieliset versiot ovat tässä tiedostossa, ja ne päivitetään tänne, jos suomenkielistä tekstiä muutetaan.
'use strict';
const fs = require('fs');
const path = require('path');
const { KIELET, JARJESTYS, SIVUPOLUT, LOGO, e } = require('./etusivu');

const YT = {
  nimi: '<span data-yt="nimi">[yrityksen nimi]</span>',
  yTunnus: '<span data-yt="yTunnus">[Y-tunnus]</span>',
  osoite: '<span data-yt="osoite">[osoite]</span>',
  posti: '<span data-yt="sahkoposti" data-yt-linkki="mailto">[sähköposti]</span>'
};

const TEKSTIT = {
  tarkista: {
    fi: {
      otsikko: 'Raportin tarkistus – AKVERI', kuvaus: 'Tarkista AKVERI-akkuraportin aitous raportin tunnuksella.',
      sisalto: `<section class="leveys tulos">
  <h1>Raportin tarkistus</h1>
  <p class="selite">Tarkistus näyttää AKVERIn palvelimelle rekisteröidyt tiedot. Vertaa niitä raporttiin: jos luvut, auto tai päivämäärä poikkeavat, raporttia on muutettu.</p>
  <form class="rivi-lomake ei-tulosteeseen" id="tarkistuslomake"><label class="vh" for="tunnus">Raportin tunnus</label><input id="tunnus" name="tunnus" placeholder="AK-XXXXX-XXXXX" autocomplete="off" required><button class="nappi" type="submit">Tarkista</button></form>
  <div id="tulos" aria-live="polite"></div>
  <form class="kortti ei-tulosteeseen piilossa" id="vinlomake">
    <h2>Vertaa valmistenumeroa</h2>
    <p class="selite">Kirjoita auton koko valmistenumero (VIN, 17 merkkiä). Numeroa ei tallenneta: tarkistus kertoo vain, onko raportti tehty tästä autosta.</p>
    <div class="rivi-lomake"><label class="vh" for="vin">Valmistenumero</label><input id="vin" maxlength="17" autocomplete="off" spellcheck="false" required><button class="nappi" type="submit">Vertaa</button></div>
    <div class="ilmoitus" id="vintulos"></div>
  </form>
</section>`
    },
    en: {
      otsikko: 'Verify a report – AKVERI', kuvaus: 'Check that an AKVERI battery report is genuine using its report ID.',
      sisalto: `<section class="leveys tulos">
  <h1>Verify a report</h1>
  <p class="selite">The check shows the details registered on the AKVERI server. Compare them with the report: if the figures, the car or the date differ, the report has been altered.</p>
  <form class="rivi-lomake ei-tulosteeseen" id="tarkistuslomake"><label class="vh" for="tunnus">Report ID</label><input id="tunnus" name="tunnus" placeholder="AK-XXXXX-XXXXX" autocomplete="off" required><button class="nappi" type="submit">Verify</button></form>
  <div id="tulos" aria-live="polite"></div>
  <form class="kortti ei-tulosteeseen piilossa" id="vinlomake">
    <h2>Compare the VIN</h2>
    <p class="selite">Enter the car's full vehicle identification number (VIN, 17 characters). The number is not stored: the check only tells whether the report was made for this car.</p>
    <div class="rivi-lomake"><label class="vh" for="vin">VIN</label><input id="vin" maxlength="17" autocomplete="off" spellcheck="false" required><button class="nappi" type="submit">Compare</button></div>
    <div class="ilmoitus" id="vintulos"></div>
  </form>
</section>`
    },
    sv: {
      otsikko: 'Kontrollera en rapport – AKVERI', kuvaus: 'Kontrollera att en AKVERI-batterirapport är äkta med rapportens kod.',
      sisalto: `<section class="leveys tulos">
  <h1>Kontrollera en rapport</h1>
  <p class="selite">Kontrollen visar de uppgifter som registrerats på AKVERIs server. Jämför dem med rapporten: om siffrorna, bilen eller datumet avviker har rapporten ändrats.</p>
  <form class="rivi-lomake ei-tulosteeseen" id="tarkistuslomake"><label class="vh" for="tunnus">Rapportkod</label><input id="tunnus" name="tunnus" placeholder="AK-XXXXX-XXXXX" autocomplete="off" required><button class="nappi" type="submit">Kontrollera</button></form>
  <div id="tulos" aria-live="polite"></div>
  <form class="kortti ei-tulosteeseen piilossa" id="vinlomake">
    <h2>Jämför chassinumret</h2>
    <p class="selite">Ange bilens fullständiga chassinummer (VIN, 17 tecken). Numret sparas inte: kontrollen visar bara om rapporten gäller den här bilen.</p>
    <div class="rivi-lomake"><label class="vh" for="vin">Chassinummer</label><input id="vin" maxlength="17" autocomplete="off" spellcheck="false" required><button class="nappi" type="submit">Jämför</button></div>
    <div class="ilmoitus" id="vintulos"></div>
  </form>
</section>`
    }
  },

  yhteystiedot: {
    fi: {
      otsikko: 'Yhteystiedot – AKVERI', kuvaus: 'Ota yhteyttä AKVERIin.',
      sisalto: `<section class="leveys">
  <div class="proosa"><h1>Yhteystiedot</h1>
  <p><b data-yt="nimi">[yrityksen nimi]</b><br><span data-yt-rivi="yTunnus">Y-tunnus <span data-yt="yTunnus"></span><br></span><span data-yt="osoite"></span></p>
  <p><span data-yt-rivi="sahkoposti">Sähköposti: <span data-yt="sahkoposti" data-yt-linkki="mailto"></span><br></span><span data-yt-rivi="puhelin">Puhelin: <span data-yt="puhelin" data-yt-linkki="tel"></span></span></p>
  <p class="paivays" id="yt-tyhja">Yhteystiedot päivitetään pian.</p></div>
  <form class="kortti proosa" id="yhteyslomake" novalidate>
    <h2>Lähetä viesti</h2>
    <p class="selite">Jos asia koskee mittausta, kirjoita mukaan raportin tai testin tunnus. Vastaamme sähköpostilla.</p>
    <label for="y-nimi">Nimi</label><input id="y-nimi" name="nimi" autocomplete="name" required maxlength="120">
    <label for="y-posti">Sähköposti</label><input id="y-posti" name="sahkoposti" type="email" autocomplete="email" required maxlength="160">
    <label for="y-aihe">Aihe</label><select id="y-aihe" name="aihe">AIHEET</select>
    <label for="y-tunnus">Raportin tai testin tunnus (valinnainen)</label><input id="y-tunnus" name="testitunnus" maxlength="20" autocomplete="off">
    <label for="y-viesti">Viesti</label><textarea id="y-viesti" name="viesti" required maxlength="3000"></textarea>
    <div class="vh" aria-hidden="true"><label for="y-www">Jätä tyhjäksi</label><input id="y-www" name="www" tabindex="-1" autocomplete="off"></div>
    <label class="valinta"><input type="checkbox" id="y-suostumus"> <span>Tietojani saa käyttää viestiin vastaamiseen <a href="TIETOSUOJA">tietosuojaselosteen</a> mukaisesti.</span></label>
    <p><button class="nappi" type="submit">Lähetä</button></p>
    <div class="ilmoitus" id="y-ilmoitus" role="status"></div>
  </form>
</section>`,
      aiheet: ['Kysymys', 'Mittaus tai raportti', 'Krediitit ja ostot', 'Yhteistyö', 'Tietosuoja']
    },
    en: {
      otsikko: 'Contact – AKVERI', kuvaus: 'Contact AKVERI.',
      sisalto: `<section class="leveys">
  <div class="proosa"><h1>Contact</h1>
  <p><b data-yt="nimi">[yrityksen nimi]</b><br><span data-yt-rivi="yTunnus">Business ID <span data-yt="yTunnus"></span><br></span><span data-yt="osoite"></span></p>
  <p><span data-yt-rivi="sahkoposti">Email: <span data-yt="sahkoposti" data-yt-linkki="mailto"></span><br></span><span data-yt-rivi="puhelin">Phone: <span data-yt="puhelin" data-yt-linkki="tel"></span></span></p>
  <p class="paivays" id="yt-tyhja">Contact details will be added soon.</p></div>
  <form class="kortti proosa" id="yhteyslomake" novalidate>
    <h2>Send a message</h2>
    <p class="selite">If your message concerns a test, please include the report or test ID. We reply by email.</p>
    <label for="y-nimi">Name</label><input id="y-nimi" name="nimi" autocomplete="name" required maxlength="120">
    <label for="y-posti">Email</label><input id="y-posti" name="sahkoposti" type="email" autocomplete="email" required maxlength="160">
    <label for="y-aihe">Subject</label><select id="y-aihe" name="aihe">AIHEET</select>
    <label for="y-tunnus">Report or test ID (optional)</label><input id="y-tunnus" name="testitunnus" maxlength="20" autocomplete="off">
    <label for="y-viesti">Message</label><textarea id="y-viesti" name="viesti" required maxlength="3000"></textarea>
    <div class="vh" aria-hidden="true"><label for="y-www">Leave empty</label><input id="y-www" name="www" tabindex="-1" autocomplete="off"></div>
    <label class="valinta"><input type="checkbox" id="y-suostumus"> <span>My details may be used to reply to this message as described in the <a href="TIETOSUOJA">privacy policy</a>.</span></label>
    <p><button class="nappi" type="submit">Send</button></p>
    <div class="ilmoitus" id="y-ilmoitus" role="status"></div>
  </form>
</section>`,
      aiheet: ['Question', 'Test or report', 'Credits and purchases', 'Partnership', 'Privacy']
    },
    sv: {
      otsikko: 'Kontakt – AKVERI', kuvaus: 'Kontakta AKVERI.',
      sisalto: `<section class="leveys">
  <div class="proosa"><h1>Kontakt</h1>
  <p><b data-yt="nimi">[yrityksen nimi]</b><br><span data-yt-rivi="yTunnus">FO-nummer <span data-yt="yTunnus"></span><br></span><span data-yt="osoite"></span></p>
  <p><span data-yt-rivi="sahkoposti">E-post: <span data-yt="sahkoposti" data-yt-linkki="mailto"></span><br></span><span data-yt-rivi="puhelin">Telefon: <span data-yt="puhelin" data-yt-linkki="tel"></span></span></p>
  <p class="paivays" id="yt-tyhja">Kontaktuppgifterna läggs till inom kort.</p></div>
  <form class="kortti proosa" id="yhteyslomake" novalidate>
    <h2>Skicka ett meddelande</h2>
    <p class="selite">Om ärendet gäller ett test, ange rapportens eller testets kod. Vi svarar per e-post.</p>
    <label for="y-nimi">Namn</label><input id="y-nimi" name="nimi" autocomplete="name" required maxlength="120">
    <label for="y-posti">E-post</label><input id="y-posti" name="sahkoposti" type="email" autocomplete="email" required maxlength="160">
    <label for="y-aihe">Ämne</label><select id="y-aihe" name="aihe">AIHEET</select>
    <label for="y-tunnus">Rapportens eller testets kod (frivilligt)</label><input id="y-tunnus" name="testitunnus" maxlength="20" autocomplete="off">
    <label for="y-viesti">Meddelande</label><textarea id="y-viesti" name="viesti" required maxlength="3000"></textarea>
    <div class="vh" aria-hidden="true"><label for="y-www">Lämna tomt</label><input id="y-www" name="www" tabindex="-1" autocomplete="off"></div>
    <label class="valinta"><input type="checkbox" id="y-suostumus"> <span>Mina uppgifter får användas för att svara på meddelandet enligt <a href="TIETOSUOJA">dataskyddsbeskrivningen</a>.</span></label>
    <p><button class="nappi" type="submit">Skicka</button></p>
    <div class="ilmoitus" id="y-ilmoitus" role="status"></div>
  </form>
</section>`,
      aiheet: ['Fråga', 'Test eller rapport', 'Krediter och köp', 'Samarbete', 'Dataskydd']
    }
  },

  ehdot: {
    fi: {
      otsikko: 'Käyttöehdot – AKVERI', kuvaus: 'AKVERI-sovelluksen ja akveri.fi-palvelun käyttöehdot.', h1: 'Käyttöehdot',
      teksti: `<h2>1. Palveluntarjoaja</h2>
<p>Palvelun tarjoaa ${YT.nimi} (Y-tunnus ${YT.yTunnus}), ${YT.osoite}. Yhteydenotot: ${YT.posti}.</p>
<h2>2. Palvelun sisältö</h2>
<p>AKVERI on sovellus, joka lukee sähköauton ajoakun tietoja auton akunhallinnasta ja muodostaa niistä raportin. akveri.fi-palvelussa raportin aitouden voi tarkistaa raportin tunnuksella.</p>
<h2>3. Krediitit ja maksaminen</h2>
<ul>
<li>Mittaukset maksetaan krediiteillä, jotka ostetaan sovelluksessa Google Playn kautta. Maksun käsittelee Google, ja ostoon sovelletaan myös Google Playn ehtoja.</li>
<li>Mittauksen hinta krediitteinä riippuu mittaustyypistä, ja se näkyy sovelluksessa ennen mittauksen aloittamista. Hinta kattaa mittauksen ja sen raportin, ja krediitit veloitetaan mittauksen alussa.</li>
<li>Jos mittaus keskeytyy ennen raportin valmistumista, krediitit palautuvat automaattisesti, kun keskeytys tapahtuu sovelluksessa ilmoitetun ajan kuluessa mittauksen alusta. Myöhemmin AKVERIsta johtuvasta syystä keskeytyneen mittauksen krediitit palautetaan hyvityspyynnöstä.</li>
<li>Krediitit ovat tilikohtaisia eikä niitä vaihdeta rahaksi. Google Playssa peruttu tai hyvitetty osto vähentää vastaavat krediitit.</li>
</ul>
<h2>4. Raportin tarkistus</h2>
<p>Raportti rekisteröidään palveluun mittauksen päätyttyä. Tarkistussivulla näkyvät raportin tunnus, mittauksen tyyppi, auton merkki ja malli, valmistenumeron alku ja loppu, mittarilukema, mittauksen suorittaja ja keskeiset tulokset. Raportin voi mitätöidä, jos sen todetaan perustuvan virheelliseen mittaukseen tai jos sovellusta on käytetty näiden ehtojen vastaisesti.</p>
<h2>5. Tulosten luonne ja vastuunrajoitus</h2>
<p>Raportin tulokset luetaan auton akunhallinnasta, ja AKVERI laskee ja varmentaa ne; mittauksen suorittaja ei voi muuttaa tuloksia. Raportti kuvaa akun tilaa mittaushetkellä, ja sen tarkkuus on ilmoitettu raportissa. Raportti ei ole takuu akun tai ajoneuvon kunnosta eikä niiden kestosta. Palveluntarjoaja ei vastaa mittauksen suorittamisesta, auton käsittelystä mittauksen aikana eikä tuloksiin perustuvista päätöksistä. Vastuu rajoittuu kaikissa tapauksissa kyseisestä mittauksesta maksettuun hintaan, ellei pakottava lainsäädäntö muuta edellytä.</p>
<h2>6. Kielletty käyttö</h2>
<p>Sovellusta ei saa muokata, purkaa tai käyttää tavalla, jolla kierretään krediittien veloitus tai raportin tarkistus. Raportin tietojen muuttaminen on kielletty.</p>
<h2>7. Kuluttajan oikeudet</h2>
<p>Kuluttaja-asiakkaalla on kuluttajansuojalain mukaiset oikeudet. Digitaalisen sisällön toimitus alkaa heti oston jälkeen, kun asiakas on ostaessaan antanut siihen suostumuksensa.</p>
<h2>8. Ehtojen muuttaminen</h2>
<p>Ehtoja voidaan muuttaa. Voimassa oleva versio on aina tällä sivulla, ja sen päivämäärä näkyy otsikon alla.</p>
<h2>9. Sovellettava laki</h2>
<p>Ehtoihin sovelletaan Suomen lakia. Kuluttaja voi viedä riidan kuluttajariitalautakunnan käsiteltäväksi.</p>`
    },
    en: {
      otsikko: 'Terms of use – AKVERI', kuvaus: 'Terms of use for the AKVERI app and the akveri.fi service.', h1: 'Terms of use',
      huomio: 'This is a translation. If the language versions differ, the Finnish version applies.',
      teksti: `<h2>1. Service provider</h2>
<p>The service is provided by ${YT.nimi} (Business ID ${YT.yTunnus}), ${YT.osoite}. Contact: ${YT.posti}.</p>
<h2>2. The service</h2>
<p>AKVERI is an app that reads data on an electric car's traction battery from the car's battery management system and compiles it into a report. On akveri.fi, anyone can check that a report is genuine using its report ID.</p>
<h2>3. Credits and payment</h2>
<ul>
<li>Tests are paid for with credits bought in the app through Google Play. Payments are processed by Google, and Google Play's terms also apply to purchases.</li>
<li>The price of a test in credits depends on the test type and is shown in the app before the test starts. The price covers the test and its report, and the credits are charged when the test starts.</li>
<li>If a test is interrupted before the report is ready, the credits are returned automatically when the interruption occurs within the time stated in the app from the start of the test. If a test is interrupted later for a reason attributable to AKVERI, the credits are returned on request.</li>
<li>Credits belong to the account and cannot be exchanged for money. A purchase cancelled or refunded on Google Play removes the corresponding credits.</li>
</ul>
<h2>4. Report verification</h2>
<p>A report is registered with the service when the test ends. The verification page shows the report ID, the test type, the car's make and model, the beginning and end of the VIN, the odometer reading, who carried out the test and the main results. A report may be invalidated if it is found to be based on a faulty test or if the app has been used in breach of these terms.</p>
<h2>5. Nature of the results and limitation of liability</h2>
<p>The results in the report are read from the car's battery management system and calculated and verified by AKVERI; the person who carries out the test cannot change them. The report describes the condition of the battery at the time of the test, and its accuracy is stated in the report. The report is not a guarantee of the condition or durability of the battery or the vehicle. The service provider is not responsible for how the test is carried out, for the handling of the car during the test or for decisions based on the results. In all cases, liability is limited to the price paid for the test in question, unless mandatory law requires otherwise.</p>
<h2>6. Prohibited use</h2>
<p>The app may not be modified, reverse engineered or used in a way that circumvents the charging of credits or the verification of reports. Altering the contents of a report is prohibited.</p>
<h2>7. Consumer rights</h2>
<p>Consumers have the rights provided by the Finnish Consumer Protection Act. Delivery of digital content begins immediately after purchase when the customer has given consent to this at the time of purchase.</p>
<h2>8. Changes to the terms</h2>
<p>These terms may be changed. The current version is always available on this page.</p>
<h2>9. Governing law</h2>
<p>These terms are governed by Finnish law. Consumers may refer a dispute to the Consumer Disputes Board in Finland.</p>`
    },
    sv: {
      otsikko: 'Användarvillkor – AKVERI', kuvaus: 'Användarvillkor för appen AKVERI och tjänsten akveri.fi.', h1: 'Användarvillkor',
      huomio: 'Detta är en översättning. Om språkversionerna skiljer sig åt gäller den finska versionen.',
      teksti: `<h2>1. Tjänsteleverantör</h2>
<p>Tjänsten tillhandahålls av ${YT.nimi} (FO-nummer ${YT.yTunnus}), ${YT.osoite}. Kontakt: ${YT.posti}.</p>
<h2>2. Tjänstens innehåll</h2>
<p>AKVERI är en app som läser uppgifter om elbilens drivbatteri från bilens batterihanteringssystem och sammanställer dem i en rapport. På akveri.fi kan vem som helst kontrollera att en rapport är äkta med rapportens kod.</p>
<h2>3. Krediter och betalning</h2>
<ul>
<li>Testerna betalas med krediter som köps i appen via Google Play. Betalningen hanteras av Google, och Google Plays villkor gäller också för köpet.</li>
<li>Priset för ett test i krediter beror på testtypen och visas i appen innan testet startas. Priset omfattar testet och dess rapport, och krediterna debiteras när testet startar.</li>
<li>Om ett test avbryts innan rapporten är klar återförs krediterna automatiskt, om avbrottet sker inom den tid från testets start som anges i appen. Om ett test avbryts senare av en orsak som beror på AKVERI återförs krediterna på begäran.</li>
<li>Krediterna hör till kontot och kan inte växlas till pengar. Ett köp som har annullerats eller återbetalats i Google Play drar av motsvarande krediter.</li>
</ul>
<h2>4. Kontroll av rapporter</h2>
<p>Rapporten registreras i tjänsten när testet har avslutats. På kontrollsidan visas rapportens kod, testtypen, bilens märke och modell, chassinumrets början och slut, mätarställningen, vem som utförde testet och de viktigaste resultaten. En rapport kan ogiltigförklaras om den visar sig bygga på ett felaktigt test eller om appen har använts i strid med dessa villkor.</p>
<h2>5. Resultatens karaktär och ansvarsbegränsning</h2>
<p>Rapportens resultat läses från bilens batterihanteringssystem och beräknas och verifieras av AKVERI; den som utför testet kan inte ändra dem. Rapporten beskriver batteriets skick vid testtillfället, och dess noggrannhet anges i rapporten. Rapporten är ingen garanti för batteriets eller fordonets skick eller hållbarhet. Tjänsteleverantören ansvarar inte för hur testet utförs, för hanteringen av bilen under testet eller för beslut som grundar sig på resultaten. Ansvaret är i alla fall begränsat till det pris som betalats för testet i fråga, om inte tvingande lagstiftning kräver annat.</p>
<h2>6. Förbjuden användning</h2>
<p>Appen får inte ändras, dekompileras eller användas på ett sätt som kringgår debiteringen av krediter eller kontrollen av rapporter. Det är förbjudet att ändra uppgifterna i en rapport.</p>
<h2>7. Konsumentens rättigheter</h2>
<p>Konsumenter har de rättigheter som följer av den finska konsumentskyddslagen. Leveransen av digitalt innehåll börjar direkt efter köpet, när kunden har gett sitt samtycke till det vid köpet.</p>
<h2>8. Ändringar av villkoren</h2>
<p>Villkoren kan ändras. Den gällande versionen finns alltid på den här sidan.</p>
<h2>9. Tillämplig lag</h2>
<p>På villkoren tillämpas finsk lag. Konsumenter kan föra en tvist till konsumenttvistenämnden i Finland.</p>`
    }
  },

  tietosuoja: {
    fi: {
      otsikko: 'Tietosuojaseloste – AKVERI', kuvaus: 'AKVERI-sovelluksen ja akveri.fi-palvelun tietosuojaseloste.', h1: 'Tietosuojaseloste',
      teksti: `<h2>Rekisterinpitäjä</h2>
<p>${YT.nimi}, Y-tunnus ${YT.yTunnus}, ${YT.osoite}. Tietosuoja-asiat: ${YT.posti}.</p>
<h2>Mitä tietoja käsitellään</h2>
<ul>
<li><b>Sovelluksen tili:</b> satunnainen tilitunnus ja sen salaisen avaimen tiiviste. Tiliin ei liitetä nimeä, sähköpostia eikä puhelinnumeroa.</li>
<li><b>Ostot:</b> Google Playn tilausnumero, ostettu tuote ja ostoaika. Maksutiedot käsittelee Google, eikä niitä välitetä AKVERIlle.</li>
<li><b>Rekisteröidyt raportit:</b> raportin tunnus, mittauksen tyyppi ja aika, auton merkki ja malli, valmistenumeron kolme ensimmäistä ja kuusi viimeistä merkkiä, valmistenumeron tiiviste, mittarilukema, mittaustulokset, raakadatan tarkiste sekä mittauksen suorittajaksi ilmoitettu nimi tai yritys, joka näkyy myös tarkistussivulla. Rekisterikilpeä tai auton omistajaa ei tallenneta palveluun.</li>
<li><b>Yhteydenotot:</b> lomakkeella lähetetty nimi, sähköpostiosoite ja viesti.</li>
<li><b>Tekniset lokit:</b> IP-osoite käsitellään väliaikaisesti väärinkäytösten estämiseksi (pyyntöjen rajoitus).</li>
</ul>
<h2>Käsittelyn tarkoitus ja peruste</h2>
<p>Tietoja käsitellään palvelun toimittamiseksi (sopimus), krediittien kirjanpitoon (lakisääteinen velvoite ja sopimus), raporttien aitouden tarkistamiseksi (oikeutettu etu: raportin vastaanottajan mahdollisuus varmistaa raportin aitous) ja yhteydenottoihin vastaamiseksi (oikeutettu etu).</p>
<h2>Säilytysaika</h2>
<p>Rekisteröity raportti säilytetään, jotta sen voi tarkistaa myös myöhemmin auton myynnin yhteydessä, kuitenkin enintään kymmenen vuotta. Krediittien kirjanpito säilytetään kirjanpitolain edellyttämän ajan. Yhteydenotot poistetaan, kun asia on käsitelty, viimeistään kahden vuoden kuluttua.</p>
<h2>Anonyymi mittausaineisto</h2>
<p>Jokaisesta rekisteröidystä mittauksesta tallennetaan erikseen anonyymi tilastorivi ohjelmiston kehittämistä varten: auton merkki, malli ja vuosimalli, akkutyyppi, mittaustyyppi, mittauksen kuukausi, mittarilukema tuhannen kilometrin tarkkuudella ja mittaustulokset. Rivillä ei ole raportin tunnusta, tilitunnusta, valmistenumeroa, rekisterinumeroa, mittauksen suorittajaa eikä tarkkaa aikaa, eikä sitä voi yhdistää raporttiin, autoon tai henkilöön. Siksi se ei ole henkilötieto eikä poistu tietojen poiston yhteydessä.</p>
<h2>Tietojen luovutus ja siirrot</h2>
<p>Tietoja ei myydä eikä luovuteta markkinointiin. Ostojen tarkistuksessa palvelu on yhteydessä Googlen rajapintaan. Palvelin sijaitsee EU:ssa.</p>
<h2>Evästeet ja seuranta</h2>
<p>Sivusto ei käytä seuranta- eikä mainosevästeitä eikä ulkopuolisia analytiikkapalveluita. Ylläpidon kirjautumisessa käytetään vain kirjautumisen edellyttämää välttämätöntä evästettä.</p>
<h2 id="poisto">Oikeutesi ja tietojen poisto</h2>
<p>Sinulla on oikeus saada pääsy tietoihisi, oikaista ne, pyytää niiden poistamista tai käsittelyn rajoittamista sekä vastustaa käsittelyä. Sovelluksen Krediitit-näkymässä voit itse ladata tilisi tiedot, poistaa raportin tarkistuspalvelusta ja poistaa tilisi. Pyynnön voit lähettää myös yhteystietosivun lomakkeella tai sähköpostilla. Kerro pyynnössä sovelluksen tilitunnus (sovelluksen Krediitit-sivulla) tai raportin tunnus. Tilin poiston jälkeen krediittien kirjanpito ja ostotiedot säilytetään kirjanpitolain edellyttämän ajan; niissä on vain satunnainen tilitunnus. Voit tehdä valituksen tietosuojavaltuutetulle (tietosuoja.fi).</p>`
    },
    en: {
      otsikko: 'Privacy policy – AKVERI', kuvaus: 'Privacy policy for the AKVERI app and the akveri.fi service.', h1: 'Privacy policy',
      huomio: 'This is a translation. If the language versions differ, the Finnish version applies.',
      teksti: `<h2>Controller</h2>
<p>${YT.nimi}, Business ID ${YT.yTunnus}, ${YT.osoite}. Privacy matters: ${YT.posti}.</p>
<h2>What data is processed</h2>
<ul>
<li><b>App account:</b> a random account ID and a hash of its secret key. No name, email address or phone number is linked to the account.</li>
<li><b>Purchases:</b> the Google Play order number, the product purchased and the time of purchase. Payment details are processed by Google and are not passed on to AKVERI.</li>
<li><b>Registered reports:</b> the report ID, the test type and time, the car's make and model, the first three and last six characters of the VIN, a hash of the VIN, the odometer reading, the test results, a checksum of the raw data and the name or company given as having carried out the test, which is also shown on the verification page. The registration plate and the car's owner are not stored in the service.</li>
<li><b>Messages:</b> the name, email address and message sent with the contact form.</li>
<li><b>Technical logs:</b> IP addresses are processed temporarily to prevent misuse (rate limiting).</li>
</ul>
<h2>Purpose and legal basis</h2>
<p>Data is processed to provide the service (contract), to keep records of credits (legal obligation and contract), to verify that reports are genuine (legitimate interest: the recipient of a report can confirm that it is genuine) and to reply to messages (legitimate interest).</p>
<h2>Retention</h2>
<p>A registered report is kept so that it can also be verified later when the car is sold, but for no longer than ten years. Records of credits are kept for the period required by the Finnish Accounting Act. Messages are deleted once the matter has been dealt with, at the latest after two years.</p>
<h2>Anonymous test data</h2>
<p>For each registered test, a separate anonymous statistics row is stored for developing the software: the car's make, model and model year, battery type, test type, the month of the test, the odometer reading rounded to the nearest thousand kilometres and the test results. The row contains no report ID, account ID, VIN, registration plate, name of the person who carried out the test or exact time, and it cannot be linked to a report, a car or a person. It is therefore not personal data and is not removed when data is deleted.</p>
<h2>Disclosure and transfers</h2>
<p>Data is not sold or disclosed for marketing. To verify purchases, the service connects to Google's interface. The server is located in the EU.</p>
<h2>Cookies and tracking</h2>
<p>The website does not use tracking or advertising cookies or third-party analytics. Only a strictly necessary cookie is used when the administrator signs in.</p>
<h2 id="poisto">Your rights and deletion of data</h2>
<p>You have the right to access your data, have it corrected, request its deletion or restriction of processing, and object to processing. In the app's Credits view you can download your account data, remove a report from the verification service and delete your account yourself. You can also send a request using the contact form or by email. Please include the app account ID (shown on the Credits page in the app) or the report ID. After an account is deleted, credit records and purchase details are kept for the period required by the Accounting Act; they contain only the random account ID. You may lodge a complaint with the Finnish Data Protection Ombudsman (tietosuoja.fi).</p>`
    },
    sv: {
      otsikko: 'Dataskyddsbeskrivning – AKVERI', kuvaus: 'Dataskyddsbeskrivning för appen AKVERI och tjänsten akveri.fi.', h1: 'Dataskyddsbeskrivning',
      huomio: 'Detta är en översättning. Om språkversionerna skiljer sig åt gäller den finska versionen.',
      teksti: `<h2>Personuppgiftsansvarig</h2>
<p>${YT.nimi}, FO-nummer ${YT.yTunnus}, ${YT.osoite}. Dataskyddsfrågor: ${YT.posti}.</p>
<h2>Vilka uppgifter behandlas</h2>
<ul>
<li><b>Konto i appen:</b> ett slumpmässigt konto-id och en hash av dess hemliga nyckel. Inget namn, ingen e-postadress och inget telefonnummer kopplas till kontot.</li>
<li><b>Köp:</b> Google Plays ordernummer, den köpta produkten och tidpunkten för köpet. Betalningsuppgifterna hanteras av Google och lämnas inte ut till AKVERI.</li>
<li><b>Registrerade rapporter:</b> rapportens kod, testtyp och tidpunkt, bilens märke och modell, chassinumrets tre första och sex sista tecken, en hash av chassinumret, mätarställningen, testresultaten, en kontrollsumma för rådata samt det namn eller företag som angetts som utförare av testet, vilket också visas på kontrollsidan. Registreringsskylten och bilens ägare sparas inte i tjänsten.</li>
<li><b>Kontakter:</b> namn, e-postadress och meddelande som skickats via kontaktformuläret.</li>
<li><b>Tekniska loggar:</b> IP-adresser behandlas tillfälligt för att förhindra missbruk (begränsning av förfrågningar).</li>
</ul>
<h2>Ändamål och rättslig grund</h2>
<p>Uppgifterna behandlas för att tillhandahålla tjänsten (avtal), för bokföringen av krediter (rättslig förpliktelse och avtal), för att kontrollera att rapporter är äkta (berättigat intresse: mottagaren av en rapport kan försäkra sig om att den är äkta) och för att svara på kontakter (berättigat intresse).</p>
<h2>Lagringstid</h2>
<p>En registrerad rapport sparas så att den kan kontrolleras även senare när bilen säljs, dock högst tio år. Bokföringen av krediter sparas den tid som bokföringslagen kräver. Kontakter raderas när ärendet har behandlats, senast efter två år.</p>
<h2>Anonyma mätdata</h2>
<p>För varje registrerat test sparas separat en anonym statistikrad för utveckling av programvaran: bilens märke, modell och årsmodell, batterityp, testtyp, testmånad, mätarställning avrundad till närmaste tusen kilometer och testresultaten. Raden innehåller ingen rapportkod, inget konto-id, inget chassinummer, ingen registreringsskylt, inte namnet på den som utfört testet och ingen exakt tidpunkt, och den kan inte kopplas till en rapport, en bil eller en person. Den är därför inte personuppgifter och raderas inte när uppgifter raderas.</p>
<h2>Utlämnande och överföringar</h2>
<p>Uppgifterna säljs inte och lämnas inte ut för marknadsföring. Vid kontrollen av köp kommunicerar tjänsten med Googles gränssnitt. Servern finns inom EU.</p>
<h2>Kakor och spårning</h2>
<p>Webbplatsen använder inte spårnings- eller reklamkakor och inga utomstående analystjänster. Endast en nödvändig kaka används när administratören loggar in.</p>
<h2 id="poisto">Dina rättigheter och radering av uppgifter</h2>
<p>Du har rätt att få tillgång till dina uppgifter, få dem rättade, begära att de raderas eller att behandlingen begränsas samt att invända mot behandlingen. I appens vy Krediter kan du själv ladda ner kontots uppgifter, ta bort en rapport från kontrolltjänsten och radera ditt konto. Du kan också skicka en begäran via kontaktformuläret eller per e-post. Ange appens konto-id (på sidan Krediter i appen) eller rapportens kod. När ett konto har raderats sparas bokföringen av krediter och köpuppgifterna den tid som bokföringslagen kräver; de innehåller endast det slumpmässiga konto-id:t. Du kan lämna in ett klagomål till dataombudsmannen (tietosuoja.fi).</p>`
    }
  }
};

const SIVUT = ['tarkista', 'yhteystiedot', 'ehdot', 'tietosuoja'];
const TIEDOSTO = (sivu, kieli) => kieli === 'fi' ? `${sivu}.html` : `${sivu}-${kieli}.html`;

function sivu(nimi, kieli) {
  const k = KIELET[kieli], t = TEKSTIT[nimi][kieli];
  const kotipolku = k.polku === '/' ? '/' : k.polku;
  const ankkuri = (a) => (k.polku === '/' ? '/' : k.polku) + '#' + a;
  const kielet = JARJESTYS.map(x => x === kieli
    ? `<a href="${SIVUPOLUT[nimi][x]}" lang="${x}" aria-current="page">${x.toUpperCase()}</a>`
    : `<a href="${SIVUPOLUT[nimi][x]}" lang="${x}" hreflang="${x}">${x.toUpperCase()}</a>`).join('');
  let sisalto;
  if (t.sisalto) {
    sisalto = t.sisalto.replace('TIETOSUOJA', SIVUPOLUT.tietosuoja[kieli])
      .replace('AIHEET', (t.aiheet || []).map((a, i) => `<option value="${e(TEKSTIT.yhteystiedot.fi.aiheet[i])}">${e(a)}</option>`).join(''));
  } else {
    // Käyttöehdot ja tietosuojaseloste: suomenkielinen teksti voidaan korvata hallinnassa muokatulla (data-asiakirja).
    sisalto = `<section class="leveys"><article class="proosa"${kieli === 'fi' ? ` data-asiakirja="${nimi}"` : ''}>
<h1>${e(t.h1)}</h1><p class="paivays" id="asiakirja-versio">${t.huomio ? e(t.huomio) : ''}</p>
<div class="asiakirja-teksti">
${t.teksti}
</div></article></section>`;
  }
  return `<!doctype html>
<html lang="${kieli}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${e(t.otsikko)}</title>
<meta name="description" content="${e(t.kuvaus)}">
${JARJESTYS.map(x => `<link rel="alternate" hreflang="${x}" href="https://akveri.fi${SIVUPOLUT[nimi][x]}">`).join('\n')}
<link rel="icon" href="/logo.svg" type="image/svg+xml">
<link rel="stylesheet" href="/sivusto.css">
<script src="/sivusto.js" defer></script>${nimi === 'tarkista' ? '<script src="/tarkista.js" defer></script>' : ''}
</head>
<body data-sivu="${nimi}">
<div class="yla-tausta"><header class="leveys yla">
  <a class="logo" href="${kotipolku}" aria-label="${e(k.logo)}">${LOGO}<span>AKVERI</span></a>
  <nav class="valikko" aria-label="${e(k.paavalikko)}"><a href="${ankkuri('miten')}">${e(k.valikko[0])}</a><a href="${ankkuri('hinta')}">${e(k.valikko[1])}</a><a href="${SIVUPOLUT.tarkista[kieli]}">${e(k.valikko[2])}</a><a href="${SIVUPOLUT.yhteystiedot[kieli]}">${e(k.valikko[3])}</a><span class="kielet" role="group" aria-label="${e(k.kieliValikko)}">${kielet}</span><a class="nappi pieni" href="${ankkuri('lataa')}">${e(k.valikko[4])}</a></nav>
</header></div>
<main>

${sisalto}

</main>
<footer class="ala">
  <div class="leveys">
    <div><b data-yt="nimi">[yrityksen nimi]</b><span data-yt-rivi="yTunnus"> · ${e(k.ytunnus)} <span data-yt="yTunnus"></span></span><br><span data-yt="osoite"></span></div>
    <nav aria-label="${e(k.alatunniste)}"><a href="${SIVUPOLUT.ehdot[kieli]}">${e(k.ala[0])}</a><a href="${SIVUPOLUT.tietosuoja[kieli]}">${e(k.ala[1])}</a><a href="${SIVUPOLUT.yhteystiedot[kieli]}">${e(k.ala[2])}</a><a href="${SIVUPOLUT.tarkista[kieli]}">${e(k.valikko[2])}</a></nav>
  </div>
</footer>
</body>
</html>
`;
}

function kaikki() {
  const t = [];
  for (const s of SIVUT) for (const k of JARJESTYS) t.push({ sivu: s, kieli: k, polku: SIVUPOLUT[s][k], tiedosto: TIEDOSTO(s, k), sisalto: sivu(s, k) });
  return t;
}

// Reitit server.js:lle: osoite → tiedosto
function reitit() { return Object.fromEntries(kaikki().map(s => [s.polku, s.tiedosto])); }

module.exports = { kaikki, reitit, TEKSTIT };

if (require.main === module) {
  for (const s of kaikki()) fs.writeFileSync(path.join(__dirname, 'sivusto', s.tiedosto), s.sisalto);
  console.log('Alasivut kirjoitettu: ' + kaikki().map(s => s.tiedosto).join(', '));
}
