// tarkista.js — raportin tarkistussivu (/v/<tunnus> tai /tarkista?tunnus=...). Tiedot piirretään DOM-solmuina.
(function () {
  'use strict';
  // Sivun kieli (tarkista.html, tarkista-en.html, tarkista-sv.html)
  var KIELI = (document.documentElement.lang || 'fi').slice(0, 2);
  var LOKAALI = { fi: 'fi-FI', en: 'en-GB', sv: 'sv-FI' }[KIELI] || 'fi-FI';
  var KAANNOKSET = {
    fi: {
      tilat: {
        valmis: ['Raportti on rekisteröity', 'Tulokset on luettu auton akunhallinnasta, ja AKVERI on laskenut ja varmentanut ne. Mittauksen suorittaja ei voi muuttaa tuloksia. Alla olevat tiedot tallennettiin AKVERIn palvelimelle mittauksen päätyttyä: vertaa niitä raporttiin.'],
        varattu: ['Mittaus on kesken tai raporttia ei ole rekisteröity', 'Tällä tunnuksella on aloitettu mittaus, mutta raporttia ei ole rekisteröity. Raporttia ei voi pitää tarkistettuna.'],
        peruttu: ['Mittaus on peruttu', 'Mittaus on keskeytetty ja peruttu. Tällä tunnuksella tehty raportti ei ole kelvollinen.'],
        mitatoity: ['Raportti on mitätöity', 'AKVERI on mitätöinyt tämän raportin. Raporttia ei pidä käyttää.'],
        poistettu: ['Raportin tiedot on poistettu', 'Raportin tiedot on poistettu palvelusta (säilytysaika päättyi tai tiedot poistettiin pyynnöstä). Raporttia ei voi enää tarkistaa.'],
        testi: ['Testimittaus – ei kelpaa todistukseksi', 'Tämä mittaus on tehty AKVERIn omassa testauksessa. Tiedot näytetään testausta varten, mutta raporttia ei voi käyttää auton akun kunnon todistuksena.']
      },
      eiLoydy: 'Raporttia ei löydy',
      eiLoydyTeksti: 'Tunnuksella {} ei ole rekisteröityä mittausta. Tarkista tunnus raportin ensimmäiseltä sivulta. Jos tunnus on oikein, raporttia ei ole tehty AKVERIlla tai sitä on muutettu.',
      syy: 'Syy: ', klo: ' klo ', kunto: 'Akun kunto', kapasiteetti: 'Kapasiteetti',
      kentat: ['Raportin tunnus', 'Mittaus aloitettu', 'Mittaus', 'Auto', 'Valmistenumero', 'Mittarilukema', 'Mitattu', 'Mittaus päättyi', 'Raportin numero', 'Mittaajan riippumattomuus', 'Raakadatan tarkiste', 'Rekisteröity', 'Laskettu uudelleen', 'AKVERI-versio', 'Mittauksen suorittaja'],
      riippumaton: 'Riippumaton mittaaja', sidoksissa: 'Mittaaja on kaupan osapuoli tai sidoksissa siihen',
      haetaan: 'Haetaan…', eiOnnistu: 'Tarkistus ei onnistunut.', verkko: 'Tarkistus ei onnistunut. Tarkista verkkoyhteys ja yritä uudelleen.',
      vinMuoto: 'Valmistenumerossa on 17 merkkiä (ei kirjaimia I, O eikä Q).', vinOk: 'Valmistenumero täsmää: raportti on tehty tästä autosta.',
      vinEi: 'Valmistenumero ei täsmää. Raportti ei koske tätä autoa.', vinVirhe: 'Vertailu ei onnistunut.', tyypit: {}
    },
    en: {
      tilat: {
        valmis: ['The report is registered', 'The results were read from the car\u2019s battery management system, and AKVERI calculated and verified them. The person who carried out the test cannot change the results. The details below were saved on the AKVERI server when the test ended: compare them with the report.'],
        varattu: ['The test is in progress or the report has not been registered', 'A test was started with this ID, but no report has been registered. The report cannot be considered verified.'],
        peruttu: ['The test was cancelled', 'The test was interrupted and cancelled. A report with this ID is not valid.'],
        mitatoity: ['The report has been invalidated', 'AKVERI has invalidated this report. It should not be used.'],
        poistettu: ['The report details have been deleted', 'The report details have been deleted from the service (the retention period ended or the details were deleted on request). The report can no longer be verified.'],
        testi: ['Test measurement – not valid as a certificate', 'This test was made in AKVERI’s own testing. The details are shown for testing purposes, but the report cannot be used as evidence of the battery’s condition.']
      },
      eiLoydy: 'Report not found',
      eiLoydyTeksti: 'No test is registered with the ID {}. Check the ID on the first page of the report. If the ID is correct, the report was not made with AKVERI or it has been altered.',
      syy: 'Reason: ', klo: ' ', kunto: 'Battery health', kapasiteetti: 'Capacity',
      kentat: ['Report ID', 'Test started', 'Test', 'Car', 'VIN', 'Odometer', 'Tested', 'Test ended', 'Report number', 'Independence of the tester', 'Raw data checksum', 'Registered', 'Recalculated', 'AKVERI version', 'Test carried out by'],
      riippumaton: 'Independent tester', sidoksissa: 'The tester is a party to the sale or connected to it',
      haetaan: 'Checking…', eiOnnistu: 'The check failed.', verkko: 'The check failed. Check your network connection and try again.',
      vinMuoto: 'A VIN has 17 characters (no letters I, O or Q).', vinOk: 'The VIN matches: the report was made for this car.',
      vinEi: 'The VIN does not match. The report does not concern this car.', vinVirhe: 'The comparison failed.',
      tyypit: { 'Pikatarkastus': 'Quick check', 'Kapasiteettimittaus': 'Capacity test', 'Täysi akkutesti': 'Full battery test', 'Ajotesti': 'Driving test', 'Pika-ajotesti': 'Quick driving test', 'Kuormitustesti': 'Load test', 'Pikalataustesti': 'Fast charging test', 'Itsepurkaustesti': 'Self-discharge test' }
    },
    sv: {
      tilat: {
        valmis: ['Rapporten är registrerad', 'Resultaten har lästs från bilens batterihanteringssystem, och AKVERI har beräknat och verifierat dem. Den som utförde testet kan inte ändra resultaten. Uppgifterna nedan sparades på AKVERIs server när testet avslutades: jämför dem med rapporten.'],
        varattu: ['Testet pågår eller rapporten har inte registrerats', 'Ett test har startats med den här koden, men ingen rapport har registrerats. Rapporten kan inte betraktas som kontrollerad.'],
        peruttu: ['Testet har annullerats', 'Testet avbröts och annullerades. En rapport med den här koden är inte giltig.'],
        mitatoity: ['Rapporten har ogiltigförklarats', 'AKVERI har ogiltigförklarat den här rapporten. Rapporten ska inte användas.'],
        poistettu: ['Rapportens uppgifter har raderats', 'Rapportens uppgifter har raderats ur tjänsten (lagringstiden har gått ut eller uppgifterna raderades på begäran). Rapporten kan inte längre kontrolleras.'],
        testi: ['Testmätning – gäller inte som intyg', 'Den här mätningen har gjorts i AKVERIs egen testning. Uppgifterna visas för testning, men rapporten kan inte användas som intyg på batteriets skick.']
      },
      eiLoydy: 'Rapporten hittades inte',
      eiLoydyTeksti: 'Det finns inget registrerat test med koden {}. Kontrollera koden på rapportens första sida. Om koden är rätt har rapporten inte gjorts med AKVERI eller så har den ändrats.',
      syy: 'Orsak: ', klo: ' kl. ', kunto: 'Batterihälsa', kapasiteetti: 'Kapacitet',
      kentat: ['Rapportkod', 'Testet startades', 'Test', 'Bil', 'Chassinummer', 'Mätarställning', 'Testat', 'Testet avslutades', 'Rapportnummer', 'Testarens oberoende', 'Kontrollsumma för rådata', 'Registrerad', 'Omräknad', 'AKVERI-version', 'Testet utfört av'],
      riippumaton: 'Oberoende testare', sidoksissa: 'Testaren är part i affären eller har anknytning till den',
      haetaan: 'Hämtar…', eiOnnistu: 'Kontrollen misslyckades.', verkko: 'Kontrollen misslyckades. Kontrollera nätverksanslutningen och försök igen.',
      vinMuoto: 'Ett chassinummer har 17 tecken (inte bokstäverna I, O eller Q).', vinOk: 'Chassinumret stämmer: rapporten gäller den här bilen.',
      vinEi: 'Chassinumret stämmer inte. Rapporten gäller inte den här bilen.', vinVirhe: 'Jämförelsen misslyckades.',
      tyypit: { 'Pikatarkastus': 'Snabbkontroll', 'Kapasiteettimittaus': 'Kapacitetstest', 'Täysi akkutesti': 'Fullständigt batteritest', 'Ajotesti': 'Körtest', 'Pika-ajotesti': 'Snabbt körtest', 'Kuormitustesti': 'Belastningstest', 'Pikalataustesti': 'Snabbladdningstest', 'Itsepurkaustesti': 'Självurladdningstest' }
    }
  };
  var S = KAANNOKSET[KIELI] || KAANNOKSET.fi;
  var LUOKAT = { valmis: ['ok', '✓'], varattu: ['kesken', '!'], peruttu: ['ei', '✕'], mitatoity: ['ei', '✕'], poistettu: ['ei', '✕'], testi: ['kesken', '!'] };
  var TILAT = {};
  Object.keys(LUOKAT).forEach(function (k) { TILAT[k] = { luokka: LUOKAT[k][0], ikoni: LUOKAT[k][1], otsikko: S.tilat[k][0], teksti: S.tilat[k][1] }; });
  function el(nimi, teksti, luokka) { var e = document.createElement(nimi); if (teksti !== undefined && teksti !== null) e.textContent = teksti; if (luokka) e.className = luokka; return e; }
  function luku(x, des) { return x === null || x === undefined ? '' : Number(x).toLocaleString(LOKAALI, { minimumFractionDigits: des, maximumFractionDigits: des }); }
  function aika(s) { if (!s) return ''; var d = new Date(typeof s === 'number' ? s * 1000 : s); return d.toLocaleDateString(LOKAALI) + S.klo + d.toLocaleTimeString(LOKAALI, { hour: '2-digit', minute: '2-digit' }); }
  // Kielivalinta säilyttää tarkistettavan tunnuksen (esim. /v/AK… → /en/verify?tunnus=AK…).
  function kielilinkit(t) {
    var a = document.querySelectorAll('.kielet a[hreflang], .kielet a[aria-current]');
    for (var i = 0; i < a.length; i++) a[i].href = a[i].getAttribute('href').split('?')[0] + (t ? '?tunnus=' + encodeURIComponent(t) : '');
  }
  function normalisoi(t) { return String(t || '').toUpperCase().replace(/[\s-]/g, ''); }

  var tulos, vinlomake, nykyinen = '';
  function piirra(d, tunnus) {
    while (tulos.firstChild) tulos.removeChild(tulos.firstChild);
    vinlomake.classList.add('piilossa');
    if (!d.loytyi) {
      var ei = el('div', null, 'tila ei'); ei.appendChild(el('div', '✕', 'ikoni'));
      var t = el('div'); t.appendChild(el('h2', S.eiLoydy)); t.appendChild(el('p', S.eiLoydyTeksti.replace('{}', tunnus)));
      ei.appendChild(t); tulos.appendChild(ei); return;
    }
    var tila = TILAT[d.tila] || TILAT.varattu;
    if (d.testi) tila = TILAT.testi;
    var otsake = el('div', null, 'tila ' + tila.luokka); otsake.appendChild(el('div', tila.ikoni, 'ikoni'));
    var ot = el('div'); ot.appendChild(el('h2', tila.otsikko)); ot.appendChild(el('p', tila.teksti));
    if (d.mitatoinninSyy) ot.appendChild(el('p', S.syy + d.mitatoinninSyy));
    otsake.appendChild(ot); tulos.appendChild(otsake);
    if (d.tila !== 'valmis') { var dl0 = el('dl'); [[S.kentat[0], d.tunnus], [S.kentat[1], aika(d.varattu)]].forEach(function (r) { dl0.appendChild(el('dt', r[0])); dl0.appendChild(el('dd', r[1])); }); tulos.appendChild(dl0); return; }
    var ruudut = el('div', null, 'lukuruutu');
    if (d.kuntoPct !== null && d.kuntoPct !== undefined) { var k1 = el('div', null, 'kortti'); k1.appendChild(el('b', luku(d.kuntoPct, 1) + ' %')); k1.appendChild(el('span', S.kunto)); ruudut.appendChild(k1); }
    if (d.kapasiteettiKwh) { var k2 = el('div', null, 'kortti'); k2.appendChild(el('b', luku(d.kapasiteettiKwh, 1) + ' kWh')); k2.appendChild(el('span', S.kapasiteetti)); ruudut.appendChild(k2); }
    if (ruudut.childNodes.length) tulos.appendChild(ruudut);
    var dl = el('dl');
    var K = S.kentat;
    [[K[0], d.tunnus, 1], [K[2], S.tyypit[d.tyyppi] || d.tyyppi], [K[3], [d.merkki, d.malli].filter(Boolean).join(' ')], [K[4], d.vin],
     [K[5], d.mittarilukema !== null && d.mittarilukema !== undefined ? luku(d.mittarilukema, 0) + ' km' : ''],
     [K[6], aika(d.mitattu)], [K[7], aika(d.paattynyt)], [K[8], d.raporttinumero],
     [K[14], d.suorittaja],
     [K[9], d.riippumaton === true ? S.riippumaton : d.riippumaton === false ? S.sidoksissa : ''],
     [K[10], d.tarkiste, 1], [K[11], aika(d.rekisteroity)], [K[12], d.paivitetty ? aika(d.paivitetty) : ''], [K[13], d.versio]
    ].forEach(function (r) { if (!r[1]) return; dl.appendChild(el('dt', r[0])); var dd = el('dd', r[1]); if (r[2]) dd.className = 'tunnus'; dl.appendChild(dd); });
    tulos.appendChild(dl);
    if (d.vin) vinlomake.classList.remove('piilossa');
  }
  function tarkista(tunnus) {
    var n = normalisoi(tunnus);
    if (!n) return;
    nykyinen = n;
    tulos.textContent = S.haetaan;
    fetch('/api/v1/vahvistus/' + encodeURIComponent(n)).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) { if (!x.ok) { tulos.textContent = (KIELI === 'fi' && x.d.virhe) || S.eiOnnistu; return; } if (x.d.tunnus) document.getElementById('tunnus').value = x.d.tunnus; piirra(x.d, tunnus); })
      .catch(function () { tulos.textContent = S.verkko; });
  }
  document.addEventListener('DOMContentLoaded', function () {
    tulos = document.getElementById('tulos'); vinlomake = document.getElementById('vinlomake');
    var syote = document.getElementById('tunnus');
    var m = /^\/v\/([A-Za-z0-9-]{10,20})$/.exec(location.pathname);
    var alku = m ? m[1] : new URLSearchParams(location.search).get('tunnus');
    if (alku) { syote.value = alku; kielilinkit(normalisoi(alku)); tarkista(alku); }
    document.getElementById('tarkistuslomake').addEventListener('submit', function (e) {
      e.preventDefault();
      var t = normalisoi(syote.value);
      if (t) { history.replaceState(null, '', KIELI === 'fi' ? '/v/' + t : location.pathname + '?tunnus=' + t); kielilinkit(t); tarkista(t); }
    });
    vinlomake.addEventListener('submit', function (e) {
      e.preventDefault();
      var vin = document.getElementById('vin').value.toUpperCase().replace(/\s/g, '');
      var ilmo = document.getElementById('vintulos');
      if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) { ilmo.textContent = S.vinMuoto; ilmo.className = 'ilmoitus nakyy virhe'; return; }
      fetch('/api/v1/vahvistus/' + encodeURIComponent(nykyinen) + '?vin=' + encodeURIComponent(vin)).then(function (r) { return r.json(); }).then(function (d) {
        if (d.vinTasmaa === true) { ilmo.textContent = S.vinOk; ilmo.className = 'ilmoitus nakyy ok'; }
        else if (d.vinTasmaa === false) { ilmo.textContent = S.vinEi; ilmo.className = 'ilmoitus nakyy virhe'; }
        else { ilmo.textContent = (KIELI === 'fi' && d.virhe) || S.vinVirhe; ilmo.className = 'ilmoitus nakyy virhe'; }
      }).catch(function () { ilmo.textContent = S.vinVirhe; ilmo.className = 'ilmoitus nakyy virhe'; });
    });
  });
})();
