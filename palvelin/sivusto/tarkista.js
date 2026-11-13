// tarkista.js — raportin tarkistussivu (/v/<tunnus> tai /tarkista?tunnus=...). Tiedot piirretään DOM-solmuina.
(function () {
  'use strict';
  var TILAT = {
    valmis: { luokka: 'ok', ikoni: '✓', otsikko: 'Raportti on rekisteröity', teksti: 'Alla olevat tiedot on tallennettu AKVERIn palvelimelle mittauksen päätyttyä. Vertaa niitä raporttiin.' },
    varattu: { luokka: 'kesken', ikoni: '!', otsikko: 'Mittaus on kesken tai raporttia ei ole rekisteröity', teksti: 'Tällä tunnuksella on aloitettu mittaus, mutta raporttia ei ole rekisteröity. Raporttia ei voi pitää tarkistettuna.' },
    peruttu: { luokka: 'ei', ikoni: '✕', otsikko: 'Mittaus on peruttu', teksti: 'Mittaus on keskeytetty ja peruttu. Tällä tunnuksella tehty raportti ei ole kelvollinen.' },
    mitatoity: { luokka: 'ei', ikoni: '✕', otsikko: 'Raportti on mitätöity', teksti: 'AKVERI on mitätöinyt tämän raportin. Raporttia ei pidä käyttää.' }
  };
  function el(nimi, teksti, luokka) { var e = document.createElement(nimi); if (teksti !== undefined && teksti !== null) e.textContent = teksti; if (luokka) e.className = luokka; return e; }
  function luku(x, des) { return x === null || x === undefined ? '' : Number(x).toLocaleString('fi-FI', { minimumFractionDigits: des, maximumFractionDigits: des }); }
  function aika(s) { if (!s) return ''; var d = new Date(typeof s === 'number' ? s * 1000 : s); return d.toLocaleDateString('fi-FI') + ' klo ' + d.toLocaleTimeString('fi-FI', { hour: '2-digit', minute: '2-digit' }); }
  function normalisoi(t) { return String(t || '').toUpperCase().replace(/[\s-]/g, ''); }

  var tulos, vinlomake, nykyinen = '';
  function piirra(d, tunnus) {
    while (tulos.firstChild) tulos.removeChild(tulos.firstChild);
    vinlomake.classList.add('piilossa');
    if (!d.loytyi) {
      var ei = el('div', null, 'tila ei'); ei.appendChild(el('div', '✕', 'ikoni'));
      var t = el('div'); t.appendChild(el('h2', 'Raporttia ei löydy')); t.appendChild(el('p', 'Tunnuksella ' + tunnus + ' ei ole rekisteröityä mittausta. Tarkista tunnus raportin ensimmäiseltä sivulta. Jos tunnus on oikein, raporttia ei ole tehty AKVERIlla tai sitä on muutettu.'));
      ei.appendChild(t); tulos.appendChild(ei); return;
    }
    var tila = TILAT[d.tila] || TILAT.varattu;
    if (d.testi) tila = { luokka: 'kesken', ikoni: '!', otsikko: 'Testimittaus – ei kelpaa todistukseksi', teksti: 'Tämä mittaus on tehty AKVERIn omassa testauksessa. Tiedot näytetään testausta varten, mutta raporttia ei voi käyttää auton akun kunnon todistuksena.' };
    var otsake = el('div', null, 'tila ' + tila.luokka); otsake.appendChild(el('div', tila.ikoni, 'ikoni'));
    var ot = el('div'); ot.appendChild(el('h2', tila.otsikko)); ot.appendChild(el('p', tila.teksti));
    if (d.mitatoinninSyy) ot.appendChild(el('p', 'Syy: ' + d.mitatoinninSyy));
    otsake.appendChild(ot); tulos.appendChild(otsake);
    if (d.tila !== 'valmis') { var dl0 = el('dl'); [['Raportin tunnus', d.tunnus], ['Mittaus aloitettu', aika(d.varattu)]].forEach(function (r) { dl0.appendChild(el('dt', r[0])); dl0.appendChild(el('dd', r[1])); }); tulos.appendChild(dl0); return; }
    var ruudut = el('div', null, 'lukuruutu');
    if (d.kuntoPct !== null && d.kuntoPct !== undefined) { var k1 = el('div', null, 'kortti'); k1.appendChild(el('b', luku(d.kuntoPct, 1) + ' %')); k1.appendChild(el('span', 'Akun kunto')); ruudut.appendChild(k1); }
    if (d.kapasiteettiKwh) { var k2 = el('div', null, 'kortti'); k2.appendChild(el('b', luku(d.kapasiteettiKwh, 1) + ' kWh')); k2.appendChild(el('span', 'Kapasiteetti')); ruudut.appendChild(k2); }
    if (ruudut.childNodes.length) tulos.appendChild(ruudut);
    var dl = el('dl');
    [['Raportin tunnus', d.tunnus], ['Mittaus', d.tyyppi], ['Auto', [d.merkki, d.malli].filter(Boolean).join(' ')], ['Valmistenumero', d.vin],
     ['Mittarilukema', d.mittarilukema !== null && d.mittarilukema !== undefined ? luku(d.mittarilukema, 0) + ' km' : ''],
     ['Mitattu', aika(d.mitattu)], ['Mittaus päättyi', aika(d.paattynyt)], ['Raportin numero', d.raporttinumero],
     ['Mittaajan riippumattomuus', d.riippumaton === true ? 'Riippumaton mittaaja' : d.riippumaton === false ? 'Mittaaja on kaupan osapuoli tai sidoksissa siihen' : ''],
     ['Raakadatan tarkiste', d.tarkiste], ['Rekisteröity', aika(d.rekisteroity)], ['Laskettu uudelleen', d.paivitetty ? aika(d.paivitetty) : ''], ['AKVERI-versio', d.versio]
    ].forEach(function (r) { if (!r[1]) return; dl.appendChild(el('dt', r[0])); var dd = el('dd', r[1]); if (r[0] === 'Raakadatan tarkiste' || r[0] === 'Raportin tunnus') dd.className = 'tunnus'; dl.appendChild(dd); });
    tulos.appendChild(dl);
    if (d.vin) vinlomake.classList.remove('piilossa');
  }
  function tarkista(tunnus) {
    var n = normalisoi(tunnus);
    if (!n) return;
    nykyinen = n;
    tulos.textContent = 'Haetaan…';
    fetch('/api/v1/vahvistus/' + encodeURIComponent(n)).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) { if (!x.ok) { tulos.textContent = x.d.virhe || 'Tarkistus ei onnistunut.'; return; } if (x.d.tunnus) document.getElementById('tunnus').value = x.d.tunnus; piirra(x.d, tunnus); })
      .catch(function () { tulos.textContent = 'Tarkistus ei onnistunut. Tarkista verkkoyhteys ja yritä uudelleen.'; });
  }
  document.addEventListener('DOMContentLoaded', function () {
    tulos = document.getElementById('tulos'); vinlomake = document.getElementById('vinlomake');
    var syote = document.getElementById('tunnus');
    var m = /^\/v\/([A-Za-z0-9-]{10,20})$/.exec(location.pathname);
    var alku = m ? m[1] : new URLSearchParams(location.search).get('tunnus');
    if (alku) { syote.value = alku; tarkista(alku); }
    document.getElementById('tarkistuslomake').addEventListener('submit', function (e) {
      e.preventDefault();
      var t = normalisoi(syote.value);
      if (t) { history.replaceState(null, '', '/v/' + t); tarkista(t); }
    });
    vinlomake.addEventListener('submit', function (e) {
      e.preventDefault();
      var vin = document.getElementById('vin').value.toUpperCase().replace(/\s/g, '');
      var ilmo = document.getElementById('vintulos');
      if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) { ilmo.textContent = 'Valmistenumerossa on 17 merkkiä (ei kirjaimia I, O eikä Q).'; ilmo.className = 'ilmoitus nakyy virhe'; return; }
      fetch('/api/v1/vahvistus/' + encodeURIComponent(nykyinen) + '?vin=' + encodeURIComponent(vin)).then(function (r) { return r.json(); }).then(function (d) {
        if (d.vinTasmaa === true) { ilmo.textContent = 'Valmistenumero täsmää: raportti on tehty tästä autosta.'; ilmo.className = 'ilmoitus nakyy ok'; }
        else if (d.vinTasmaa === false) { ilmo.textContent = 'Valmistenumero ei täsmää. Raportti ei koske tätä autoa.'; ilmo.className = 'ilmoitus nakyy virhe'; }
        else { ilmo.textContent = d.virhe || 'Vertailu ei onnistunut.'; ilmo.className = 'ilmoitus nakyy virhe'; }
      }).catch(function () { ilmo.textContent = 'Vertailu ei onnistunut.'; ilmo.className = 'ilmoitus nakyy virhe'; });
    });
  });
})();
