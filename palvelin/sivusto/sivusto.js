// sivusto.js — akveri.fi:n yhteiset toiminnot. Sama logiikka kuin vuoropiste.fi:ssä:
//   - [data-yt]-kentät täytetään yhteystiedoilla yhdestä lähteestä (hallinnan Asetukset). Jos tietoa ei ole asetettu,
//     oletusteksti hakasulkeissa jää näkyviin, jotta puute huomataan. [data-yt-rivi] piilotetaan, jos tieto puuttuu.
//   - Käyttöehdot ja tietosuojaseloste näytetään hallinnassa muokatulla tekstillä, jos sellainen on. Teksti piirretään
//     DOM-solmuina (ei HTML:nä): "## otsikko", tyhjä rivi erottaa kappaleet, "- " aloittaa luettelon ja {{nimi}},
//     {{yTunnus}}, {{osoite}}, {{sahkoposti}}, {{puhelin}} täytetään yhteystiedoista.
//   - Google Play -linkki, hinnasto ja yhteydenottolomake.
(function () {
  'use strict';
  function el(nimi, teksti) { var e = document.createElement(nimi); if (teksti) e.textContent = teksti; return e; }
  function hae(osoite) { return fetch(osoite, { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : {}; }); }

  function taytaYhteystiedot(yt) {
    var kentat = document.querySelectorAll('[data-yt]');
    for (var i = 0; i < kentat.length; i++) {
      var k = kentat[i], arvo = yt[k.getAttribute('data-yt')];
      if (typeof arvo !== 'string' || !arvo.trim()) continue;
      arvo = arvo.trim();
      var tyyppi = k.getAttribute('data-yt-linkki');
      k.textContent = '';
      if (tyyppi === 'mailto' || tyyppi === 'tel') {
        var a = el('a', arvo); a.href = tyyppi === 'tel' ? 'tel:' + arvo.replace(/[^+0-9]/g, '') : 'mailto:' + arvo; k.appendChild(a);
      } else k.textContent = arvo;
    }
    var rivit = document.querySelectorAll('[data-yt-rivi]');
    for (var j = 0; j < rivit.length; j++) {
      var x = yt[rivit[j].getAttribute('data-yt-rivi')];
      if (!(typeof x === 'string' && x.trim())) rivit[j].classList.add('piilossa');
    }
    var tyhja = document.getElementById('yt-tyhja');
    if (tyhja && Object.keys(yt).some(function (k) { return yt[k]; })) tyhja.classList.add('piilossa');
  }

  function rivinSisalto(kohde, teksti) {
    var osat = teksti.split(/(\{\{[a-zA-Z]+\}\})/);
    for (var i = 0; i < osat.length; i++) {
      var m = /^\{\{([a-zA-Z]+)\}\}$/.exec(osat[i]);
      if (m) { var s = el('span', '[' + m[1] + ']'); s.setAttribute('data-yt', m[1]); if (m[1] === 'sahkoposti') s.setAttribute('data-yt-linkki', 'mailto'); kohde.appendChild(s); }
      else if (osat[i]) kohde.appendChild(document.createTextNode(osat[i]));
    }
  }
  function piirraAsiakirja(laatikko, teksti) {
    while (laatikko.firstChild) laatikko.removeChild(laatikko.firstChild);
    teksti.replace(/\r\n?/g, '\n').split(/\n{2,}/).forEach(function (lohko) {
      lohko = lohko.trim(); if (!lohko) return;
      var rivit = lohko.split('\n');
      if (/^## /.test(rivit[0])) { var h = el('h2'); rivinSisalto(h, rivit[0].slice(3).trim()); laatikko.appendChild(h); rivit = rivit.slice(1); if (!rivit.length) return; }
      if (rivit.every(function (r) { return /^- /.test(r); })) {
        var ul = el('ul'); rivit.forEach(function (r) { var li = el('li'); rivinSisalto(li, r.slice(2)); ul.appendChild(li); }); laatikko.appendChild(ul);
      } else { var p = el('p'); rivinSisalto(p, rivit.join(' ')); laatikko.appendChild(p); }
    });
  }
  function paivamaara(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? (+m[3]) + '.' + (+m[2]) + '.' + m[1] : ''; }

  function asiakirja() {
    var art = document.querySelector('[data-asiakirja]');
    if (!art) return Promise.resolve();
    var laatikko = art.querySelector('.asiakirja-teksti');
    laatikko.classList.add('piilossa');
    var varmistus = setTimeout(function () { laatikko.classList.remove('piilossa'); }, 3000);
    return hae('/api/sivusto/asiakirja/' + art.getAttribute('data-asiakirja')).then(function (d) {
      if (d && typeof d.teksti === 'string' && d.teksti.trim()) {
        piirraAsiakirja(laatikko, d.teksti);
        var v = document.getElementById('asiakirja-versio');
        if (v && d.versio) v.textContent = 'Voimassa ' + paivamaara(d.versio) + ' alkaen';
      }
    }).catch(function () { /* oletusteksti jää näkyviin */ }).then(function () { clearTimeout(varmistus); laatikko.classList.remove('piilossa'); });
  }

  function etusivu(t) {
    // Google Play: kun hallinnassa on linkki, kaikki [data-play]-painikkeet vievät Google Playhin ja tila näyttää
    // "Saatavilla Google Playssa". Ilman linkkiä painikkeet ovat himmennettyjä ja tila on "Tulossa Google Playhin".
    var saatavilla = !!t.playLinkki;
    var napit = document.querySelectorAll('[data-play]');
    for (var i = 0; i < napit.length; i++) {
      var n = napit[i];
      if (saatavilla) { n.href = t.playLinkki; n.rel = 'noopener'; n.removeAttribute('aria-disabled'); n.classList.remove('tulossa'); }
      else { n.removeAttribute('href'); n.setAttribute('aria-disabled', 'true'); n.classList.add('tulossa'); var sm = n.querySelector('small'); if (sm) sm.textContent = 'Tulossa'; }
    }
    var tilat = document.querySelectorAll('[data-play-tila]');
    for (var j = 0; j < tilat.length; j++) {
      tilat[j].classList.toggle('saatavilla', saatavilla);
      var tx = tilat[j].querySelector('[data-play-teksti]');
      if (tx) tx.textContent = saatavilla ? 'Saatavilla Google Playssa · Android 10 tai uudempi' : 'Tulossa Google Playhin. Ilmoitamme julkaisusta tällä sivulla.';
    }
    var hinnasto = document.getElementById('hinnasto');
    if (hinnasto && t.hinnasto) hinnasto.textContent = t.hinnasto;
    var aika = document.getElementById('hyvitysaika');
    if (aika && t.hyvitysaikaMin) aika.textContent = String(t.hyvitysaikaMin);
  }

  function yhteyslomake() {
    var f = document.getElementById('yhteyslomake');
    if (!f) return;
    var ilmo = document.getElementById('y-ilmoitus');
    function nayta(teksti, ok) { ilmo.textContent = teksti; ilmo.className = 'ilmoitus nakyy ' + (ok ? 'ok' : 'virhe'); }
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var nappi = f.querySelector('button[type=submit]');
      var data = { nimi: f.nimi.value, sahkoposti: f.sahkoposti.value, aihe: f.aihe.value, testitunnus: f.testitunnus.value, viesti: f.viesti.value, www: f.www.value, suostumus: document.getElementById('y-suostumus').checked };
      if (!data.nimi.trim() || !data.viesti.trim()) return nayta('Täytä nimi ja viesti.');
      if (!data.suostumus) return nayta('Hyväksy tietojen käyttö viestiin vastaamiseen.');
      nappi.disabled = true;
      fetch('/api/sivusto/viesti', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (x) { if (x.ok) { f.reset(); nayta('Kiitos viestistä. Vastaamme sähköpostilla mahdollisimman pian.', true); } else nayta(x.d.virhe || 'Lähetys epäonnistui.'); })
        .catch(function () { nayta('Lähetys epäonnistui. Tarkista verkkoyhteys ja yritä uudelleen.'); })
        .then(function () { nappi.disabled = false; });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    yhteyslomake();
    var tiedot = hae('/api/sivusto/tiedot').catch(function () { return {}; });
    Promise.all([tiedot, asiakirja()]).then(function (x) {
      var t = x[0] || {};
      taytaYhteystiedot(t.yhteystiedot || {});
      etusivu(t);
    });
  });
})();
