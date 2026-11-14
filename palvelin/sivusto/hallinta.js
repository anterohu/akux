// hallinta.js — akveri.fi/hallinta. Kaikki palvelimelta tuleva teksti piirretään textContentina (ei HTML:nä).
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  function el(nimi, teksti, luokka) { var e = document.createElement(nimi); if (teksti !== undefined && teksti !== null) e.textContent = String(teksti); if (luokka) e.className = luokka; return e; }
  function tyhjenna(e) { while (e.firstChild) e.removeChild(e.firstChild); return e; }
  function aika(s) { if (!s) return ''; var d = new Date(s); return isNaN(d) ? '' : d.toLocaleDateString('fi-FI') + ' ' + d.toLocaleTimeString('fi-FI', { hour: '2-digit', minute: '2-digit' }); }
  function koko(n) { return n >= 1048576 ? (n / 1048576).toFixed(1).replace('.', ',') + ' Mt' : Math.max(1, Math.round(n / 1024)) + ' kt'; }
  function tunnus(t) { return t ? t.slice(0, 2) + '-' + t.slice(2, 7) + '-' + t.slice(7) : ''; }
  var TILAT = { varattu: 'Kesken', valmis: 'Rekisteröity', peruttu: 'Peruttu', mitatoity: 'Mitätöity', poistettu: 'Tiedot poistettu' };

  function api(polku, valinnat) {
    valinnat = valinnat || {};
    var o = { method: valinnat.method || 'GET', credentials: 'same-origin', headers: { 'X-AKVERI-Hallinta': '1' } };
    if (valinnat.body !== undefined) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(valinnat.body); }
    return fetch('/api/hallinta' + polku, o).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (r.status === 401 && polku !== '/kirjaudu') { naytaNakyma('kirjautuminen'); throw new Error('Kirjaudu sisään.'); }
        if (!r.ok) throw new Error(d.virhe || 'Pyyntö epäonnistui.');
        return d;
      });
    });
  }
  function ilmoita(teksti, ok, kohde) {
    var i = kohde || $('#ilmoitus');
    i.textContent = teksti; i.className = 'ilmoitus nakyy ' + (ok ? 'ok' : 'virhe');
    if (ok) setTimeout(function () { if (i.textContent === teksti) i.className = 'ilmoitus'; }, 5000);
  }
  function virhe(kohde) { return function (e) { ilmoita(e.message, false, kohde); }; }

  function naytaNakyma(n) {
    ['alustus', 'kirjautuminen', 'hallinta'].forEach(function (x) { $('#nakyma-' + x).classList.toggle('piilossa', x !== n); });
    $('#ylavalikko').classList.toggle('piilossa', n !== 'hallinta');
    if (n === 'hallinta') valitse('yleiskatsaus');
  }
  function valitse(v) {
    document.querySelectorAll('#valilehdet button').forEach(function (b) { b.classList.toggle('valittu', b.getAttribute('data-v') === v); });
    document.querySelectorAll('[data-nakyma]').forEach(function (d) { d.classList.toggle('piilossa', d.getAttribute('data-nakyma') !== v); });
    $('#ilmoitus').className = 'ilmoitus';
    (LATAA[v] || function () {})();
  }

  function taulu(taulukko, otsikot, rivit, luoRivi) {
    tyhjenna(taulukko);
    var thead = el('thead'), tr = el('tr');
    otsikot.forEach(function (o) { var th = el('th', o.replace(/^#/, '')); if (o[0] === '#') th.className = 'luku'; tr.appendChild(th); });
    thead.appendChild(tr); taulukko.appendChild(thead);
    var tbody = el('tbody');
    if (!rivit.length) { var t = el('tr'), td = el('td', 'Ei rivejä.'); td.colSpan = otsikot.length; t.appendChild(td); tbody.appendChild(t); }
    rivit.forEach(function (r) { tbody.appendChild(luoRivi(r)); });
    taulukko.appendChild(tbody);
  }
  function solu(tr, teksti, luokka) { var td = el('td', teksti, luokka); tr.appendChild(td); return td; }
  function nappi(teksti, toiminto, luokka) { var b = el('button', teksti, 'nappi pieni ' + (luokka || 'toissijainen')); b.type = 'button'; b.addEventListener('click', toiminto); return b; }

  // Pieni lomake taulukon rivin alle (syy tai krediittimuutos)
  function rivilomake(tr, kentat, painike, laheta) {
    var vanha = tr.nextSibling && tr.nextSibling.classList && tr.nextSibling.classList.contains('rivilomake') ? tr.nextSibling : null;
    if (vanha) { vanha.remove(); return; }
    var lr = el('tr', null, 'rivilomake'), td = el('td'); td.colSpan = tr.children.length;
    var f = el('form', null, 'rivi-lomake');
    var syotteet = kentat.map(function (k) { var i = el('input'); i.placeholder = k.otsikko; i.setAttribute('aria-label', k.otsikko); if (k.tyyppi) i.type = k.tyyppi; i.required = true; f.appendChild(i); return i; });
    if (kentat.some(function (k) { return k.vahvistus; })) {
      var kv = kentat.filter(function (k) { return k.vahvistus; })[0];
      var lab = el('label', null, 'valinta'), cb = el('input'); cb.type = 'checkbox'; lab.appendChild(cb); lab.appendChild(el('span', kv.vahvistus)); f.appendChild(lab); syotteet.vahvistus = cb;
    }
    var b = el('button', painike, 'nappi pieni'); b.type = 'submit'; f.appendChild(b);
    f.addEventListener('submit', function (e) { e.preventDefault(); laheta(syotteet.map(function (s) { return s.value; }), syotteet.vahvistus ? syotteet.vahvistus.checked : undefined); });
    td.appendChild(f); lr.appendChild(td); tr.after(lr); syotteet[0] && syotteet[0].focus();
  }

  var MITTAUSNIMET = { pikatarkastus: 'Pikatarkastus', kapasiteetti: 'Kapasiteettimittaus', taysi: 'Täysi akkutesti', ajotesti: 'Ajotesti', pika_ajo: 'Pika-ajotesti', kuormitus: 'Kuormitustesti', pikalataus: 'Pikalataustesti', itsepurkaus: 'Itsepurkaustesti' };
  function piirraHinnat(h) {
    var r = $('#hintaruudukko'); r.textContent = '';
    Object.keys(MITTAUSNIMET).forEach(function (t) {
      var l = el('label', MITTAUSNIMET[t]); l.setAttribute('for', 'hinta-' + t);
      var i = el('input'); i.type = 'number'; i.min = '1'; i.max = '100'; i.step = '1'; i.id = 'hinta-' + t; i.value = (h && h[t]) || 1; i.setAttribute('data-hinta', t);
      var d = el('div'); d.appendChild(l); d.appendChild(i); r.appendChild(d);
    });
  }
  function luetutHinnat() { var h = {}; document.querySelectorAll('[data-hinta]').forEach(function (i) { h[i.getAttribute('data-hinta')] = Number(i.value); }); return h; }
  function naytaPosti(p) {
    $('#posti-tila').textContent = p ? ('Käytössä: ' + p.host + ':' + p.port + (p.salasanaAsetettu ? ', salasana tallennettu.' : '.')) : 'Sähköpostia ei ole asetettu. Ilmoituksia ei lähetetä, eikä viesteihin voi vastata täältä.';
    p = p || {};
    $('#po-host').value = p.host || ''; $('#po-port').value = p.port || 587; $('#po-secure').checked = !!p.secure; $('#po-user').value = p.user || ''; $('#po-pass').value = '';
    $('#po-lahettaja').value = p.lahettaja || ''; $('#po-omat').value = p.lahettajaOmat || ''; $('#po-vastaanottaja').value = p.vastaanottaja || '';
  }
  var HUOLTO_KUVAUS = { pois: 'Huoltotila on pois päältä.', sivusto: 'Sivusto on huoltotilassa. Sovellus toimii normaalisti.', kaikki: 'Sivusto ja sovelluksen palvelu ovat huoltotilassa.' };
  function naytaHuolto(h) {
    h = h || { tila: 'pois', viesti: '' };
    $('#ht-tila').value = h.tila; $('#ht-viesti').value = h.viesti || '';
    var p = $('#huolto-nyt'); p.textContent = 'Nyt: ' + HUOLTO_KUVAUS[h.tila] + (h.muutettu ? ' Muutettu ' + aika(h.muutettu) + '.' : '');
    p.className = 'paivays' + (h.tila === 'pois' ? '' : ' huomio-teksti');
  }
  var LATAA = {
    yleiskatsaus: function () {
      api('/yhteenveto').then(function (d) {
        var k = tyhjenna($('#tunnusluvut'));
        [['Tilejä', d.tilit], ['Krediittejä tileillä', d.krediititTileilla], ['Mittauksia 30 pv', d.testit30], ['Rekisteröityjä raportteja 30 pv', d.raportit30],
         ['Avoimia testilupia', d.avoimetLuvat], ['Avoimia hyvityspyyntöjä', d.hyvityspyynnot], ['Ostoja 30 pv', d.ostot30], ['Uusia viestejä', d.uudetViestit]]
          .forEach(function (x) { var c = el('div', null, 'kortti'); c.appendChild(el('b', x[1])); c.appendChild(el('span', x[0])); k.appendChild(c); });
        var h = tyhjenna($('#huomiot'));
        h.appendChild(el('h2', 'Tila'));
        var ul = el('ul', null, 'lista');
        ul.appendChild(el('li', d.googleKaytossa ? 'Google Play -ostojen tarkistus on käytössä.' : 'Google Play -ostojen tarkistus EI ole käytössä' + (d.googleVirhe ? ': ' + d.googleVirhe : '. Lisää palvelutilin avain ja sovelluksen paketti Hallintatyökalun AKVERI-välilehdellä.')));
        ul.appendChild(el('li', d.kirjanpitoEhja ? 'Krediittien kirjanpito on eheä (' + d.kirjanpitoRiveja + ' riviä).' : 'VAROITUS: krediittien kirjanpidon tarkisteketju ei täsmää. Kirjanpitoa on muutettu palvelimen ulkopuolelta. Selvitä syy ennen kuin jatkat.'));
        ul.appendChild(el('li', d.viimeisinVarmuuskopio ? 'Viimeisin varmuuskopio: ' + d.viimeisinVarmuuskopio : 'Varmuuskopiota ei ole vielä otettu.'));
        if (d.testitilit && d.testitilit.length) ul.appendChild(el('li', 'Testitilejä käytössä: ' + d.testitilit.join(', ') + '. Niiden mittaukset eivät kuluta krediittejä ja näkyvät tarkistussivulla testimittauksina. Esittelytila ja esimerkkiautot näkyvät sovelluksessa vain testitileillä. Testimittauksia 30 pv: ' + d.testimittaukset30 + '.'));
        ul.appendChild(el('li', 'Palvelimen versio: ' + (d.versio || 'tuntematon')));
        h.appendChild(ul);
      }).catch(virhe());
    },
    tilit: function () { haeTilit(''); },
    testit: function () { haeTestit(); },
    ostot: function () {
      api('/ostot').then(function (d) {
        taulu($('#ostotaulu'), ['Aika', 'Tili', 'Tuote', '#Krediitit', 'Tilaus', 'Tila'], d.ostot, function (o) {
          var tr = el('tr'); solu(tr, aika(o.aika)); solu(tr, o.tili, 'tunnus'); solu(tr, o.tuote + (o.testiosto ? ' (testiosto)' : '')); solu(tr, o.krediitit, 'luku'); solu(tr, o.tilaus, 'tunnus'); solu(tr, o.tila === 'peruttu' ? 'Peruttu Google Playssa' : 'Hyvitetty tilille'); return tr;
        });
      }).catch(virhe());
    },
    viestit: function () {
      api('/viestit').then(function (d) {
        taulu($('#viestitaulu'), ['Aika', 'Lähettäjä', 'Aihe', 'Viesti', ''], d.viestit, function (v) {
          var tr = el('tr'); if (!v.kasitelty) tr.className = 'uusi';
          solu(tr, aika(v.aika));
          var l = solu(tr, v.nimi); l.appendChild(el('br')); var a = el('a', v.sahkoposti); a.href = 'mailto:' + v.sahkoposti; l.appendChild(a);
          solu(tr, v.aihe + (v.testitunnus ? ' · ' + tunnus(v.testitunnus) : '') + (v.kieli === 'en' ? ' · englanniksi' : v.kieli === 'sv' ? ' · ruotsiksi' : ''));
          var vv = solu(tr, v.viesti); vv.style.whiteSpace = 'pre-wrap';
          var t = solu(tr, ''); var r = el('div', null, 'toimintorivi'); t.appendChild(r);
          if (v.vastaukset && v.vastaukset.length) { var vs = el('div', 'Vastattu ' + aika(v.vastaukset[v.vastaukset.length - 1].aika), 'paivays'); l.appendChild(vs); }
          r.appendChild(nappi('Vastaa', function () {
            if (t.querySelector('textarea')) return;
            var ta = el('textarea'); ta.value = 'Hei ' + v.nimi + ',\n\n'; ta.setAttribute('aria-label', 'Vastaus osoitteeseen ' + v.sahkoposti); ta.rows = 6;
            var laheta = nappi('Lähetä vastaus', function () {
              if (!ta.value.trim()) return;
              laheta.disabled = true;
              api('/viestit/' + v.id + '/vastaa', { method: 'POST', body: { teksti: ta.value } }).then(function () { ilmoita('Vastaus lähetetty osoitteeseen ' + v.sahkoposti + '.', true); LATAA.viestit(); }).catch(function (e) { laheta.disabled = false; virhe()(e); });
            });
            t.appendChild(ta); t.appendChild(laheta); ta.focus();
          }));
          r.appendChild(nappi(v.kasitelty ? 'Merkitse uudeksi' : 'Merkitse käsitellyksi', function () { api('/viestit/' + v.id, { method: 'POST', body: { kasitelty: !v.kasitelty } }).then(LATAA.viestit).catch(virhe()); }));
          r.appendChild(nappi('Poista', function () { if (window.confirm('Poistetaanko viesti pysyvästi?')) api('/viestit/' + v.id, { method: 'DELETE' }).then(LATAA.viestit).catch(virhe()); }, 'vaara'));
          return tr;
        });
      }).catch(virhe());
    },
    asetukset: function () {
      api('/asetukset').then(function (a) {
        var y = a.yhteystiedot || {};
        $('#yt-nimi').value = y.nimi || ''; $('#yt-ytunnus').value = y.yTunnus || ''; $('#yt-osoite').value = y.osoite || ''; $('#yt-sahkoposti').value = y.sahkoposti || ''; $('#yt-puhelin').value = y.puhelin || '';
        $('#as-play').value = a.playLinkki || ''; $('#as-hinnasto').value = a.hinnasto || ''; $('#as-hyvitysaika').value = a.hyvitysaikaMin;
        piirraTuotteet(a.tuotteet); piirraHinnat(a.hinnat);
        $('#ve-min').value = a.vahimmaisversio || ''; $('#ve-uusin').value = a.uusinVersio || '';
        asiakirjat = a.asiakirjat || {}; naytaAsiakirja();
        naytaHuolto(a.huoltotila); naytaPosti(a.posti);
      }).catch(virhe());
    },
    lataukset: function () {
      api('/lataukset').then(function (d) {
        taulu($('#lataustaulu'), ['Tiedosto', '#Koko', 'Päivitetty', ''], d.lataukset, function (l) {
          var tr = el('tr'); solu(tr, l.nimi); solu(tr, koko(l.koko), 'luku'); solu(tr, aika(l.muokattu));
          var a = el('a', 'Lataa', 'nappi pieni'); a.href = '/api/hallinta/lataukset/' + encodeURIComponent(l.nimi); a.setAttribute('download', l.nimi); solu(tr, '').appendChild(a); return tr;
        });
      }).catch(virhe());
    },
    kirjanpito: function () {
      api('/kirjanpito').then(function (d) {
        $('#kirjanpitotila').textContent = d.ehja ? 'Tarkisteketju on eheä. Kirjanpitoa ei voi muokata, korjaukset tehdään uusina riveinä.' : 'VAROITUS: tarkisteketju ei täsmää.';
        taulu($('#kirjanpitotaulu'), ['Aika', 'Tili', '#Muutos', 'Syy', 'Viite', 'Selite', 'Tekijä'], d.rivit, kirjanpitorivi);
      }).catch(virhe());
    },
    tunnus: function () {
      api('/kayttajat').then(function (d) {
        var rivit = d.kayttajat.map(function (k) { return { nimi: k.nimi, posti: k.sahkoposti, tila: 'Käytössä', aika: k.viimeksiKirjautunut ? 'Kirjautunut ' + aika(k.viimeksiKirjautunut) : 'Ei vielä kirjautunut' }; })
          .concat(d.kutsut.map(function (k) { return { nimi: k.nimi, posti: k.sahkoposti, tila: 'Kutsuttu', aika: 'Kutsu voimassa ' + aika(k.vanhenee) + ' asti' }; }));
        taulu($('#kayttajataulu'), ['Nimi', 'Sähköposti', 'Tila', ''], rivit, function (r) { var tr = el('tr'); solu(tr, r.nimi); solu(tr, r.posti); solu(tr, r.tila); solu(tr, r.aika); return tr; });
      }).catch(virhe());
    }
  };
  function kirjanpitorivi(r) {
    var tr = el('tr'); solu(tr, aika(r.aika)); solu(tr, r.tili, 'tunnus'); solu(tr, (r.muutos > 0 ? '+' : '') + r.muutos, 'luku'); solu(tr, r.syy); solu(tr, r.viite && /^AK/.test(r.viite) ? tunnus(r.viite) : r.viite, 'tunnus'); solu(tr, r.selite); solu(tr, r.tekija === 'omistaja' ? 'Ylläpito' : 'Järjestelmä'); return tr;
  }

  function haeTilit(haku) {
    api('/tilit?haku=' + encodeURIComponent(haku)).then(function (d) {
      taulu($('#tilitaulu'), ['Tili', 'Luotu', '#Saldo', 'Muistiinpano', 'Tila', ''], d.tilit, function (t) {
        var tr = el('tr'); solu(tr, t.id, 'tunnus'); solu(tr, aika(t.luotu)); solu(tr, t.saldo, 'luku'); solu(tr, t.muistiinpano); solu(tr, (t.suljettu ? 'Suljettu' : 'Käytössä') + (t.testitili ? ' · testitili' : ''));
        solu(tr, '').appendChild(nappi('Avaa', function () { avaaTili(t.id); })); return tr;
      });
    }).catch(virhe());
  }
  function avaaTili(id) {
    api('/tilit/' + id).then(function (d) {
      var k = tyhjenna($('#tilitiedot')); k.classList.remove('piilossa');
      k.appendChild(el('h2', 'Tili ' + d.tili.id));
      k.appendChild(el('p', 'Saldo ' + d.tili.saldo + ' krediittiä · luotu ' + aika(d.tili.luotu) + (d.tili.suljettu ? ' · SULJETTU' : '') + (d.tili.testitili ? ' · TESTITILI' : '')));
      var tt = el('div', null, 'kortti');
      tt.appendChild(el('h3', 'Testitili'));
      tt.appendChild(el('p', 'Testitilin mittaukset eivät kuluta krediittejä. Tarkistussivu ja raportti merkitsevät ne testimittauksiksi, joten niitä ei voi käyttää todistuksena. Käytä omaan testaukseen ennen krediittien käyttöönottoa. Oikeisiin raportteihin lisää omalle tilille krediittejä.'));
      tt.appendChild(nappi(d.tili.testitili ? 'Poista testitila' : 'Merkitse testitiliksi', function () {
        api('/tilit/' + id + '/tila', { method: 'POST', body: { testitili: !d.tili.testitili } }).then(function () { ilmoita(d.tili.testitili ? 'Testitila poistettu.' : 'Tili on nyt testitili.', true); avaaTili(id); haeTilit(''); }).catch(virhe());
      }, d.tili.testitili ? 'vaara' : 'toissijainen'));
      k.appendChild(tt);
      var f = el('form', null, 'rivi-lomake');
      var m = el('input'); m.type = 'number'; m.placeholder = 'Muutos (esim. 5 tai -1)'; m.setAttribute('aria-label', 'Krediittimuutos'); m.required = true;
      var s = el('input'); s.placeholder = 'Syy (näkyy kirjanpidossa)'; s.setAttribute('aria-label', 'Syy'); s.required = true;
      var b = el('button', 'Kirjaa', 'nappi'); b.type = 'submit';
      f.appendChild(m); f.appendChild(s); f.appendChild(b);
      f.addEventListener('submit', function (e) { e.preventDefault(); api('/tilit/' + id + '/krediitit', { method: 'POST', body: { muutos: Number(m.value), selite: s.value } }).then(function () { ilmoita('Krediitit kirjattu.', true); avaaTili(id); haeTilit($('#tili-haku').value); }).catch(virhe()); });
      k.appendChild(el('h3', 'Krediittien lisäys tai vähennys')); k.appendChild(f);
      var f2 = el('form', null, 'rivi-lomake'); var mm = el('input'); mm.value = d.tili.muistiinpano; mm.placeholder = 'Muistiinpano (esim. oma tili)'; mm.setAttribute('aria-label', 'Muistiinpano');
      var b2 = el('button', 'Tallenna muistiinpano', 'nappi toissijainen'); b2.type = 'submit'; f2.appendChild(mm); f2.appendChild(b2);
      f2.addEventListener('submit', function (e) { e.preventDefault(); api('/tilit/' + id + '/tila', { method: 'POST', body: { muistiinpano: mm.value } }).then(function () { ilmoita('Tallennettu.', true); haeTilit(''); }).catch(virhe()); });
      k.appendChild(el('h3', 'Muistiinpano')); k.appendChild(f2);
      k.appendChild(el('p')).appendChild(nappi(d.tili.suljettu ? 'Avaa tili uudelleen' : 'Sulje tili', function () {
        if (d.tili.suljettu || window.confirm('Suljetaanko tili? Sovellus ei voi sen jälkeen aloittaa mittauksia tällä tilillä.')) api('/tilit/' + id + '/tila', { method: 'POST', body: { suljettu: !d.tili.suljettu } }).then(function () { avaaTili(id); }).catch(virhe());
      }, d.tili.suljettu ? 'toissijainen' : 'vaara'));
      var pt = el('div', null, 'kortti');
      pt.appendChild(el('h3', 'Tilin tietojen poisto'));
      pt.appendChild(el('p', 'Tietosuojapyynnöstä: tili lakkaa toimimasta ja sen tunnistetiedot poistetaan. Avoimet testiluvat perutaan ja hyvityspyyntöjen tekstit poistetaan. Krediittien kirjanpito ja ostot säilytetään kirjanpitolain edellyttämän ajan (niissä on vain satunnainen tilitunnus). Rekisteröidyt raportit säilyvät tarkistusta varten; ne voi poistaa erikseen Testit-näkymästä. Poistoa ei voi perua.'));
      var pf = el('form', null, 'rivi-lomake'); var pv = el('input'); pv.placeholder = 'Kirjoita tilitunnus vahvistukseksi'; pv.setAttribute('aria-label', 'Vahvistus');
      var pb = el('button', 'Poista tilin tiedot', 'nappi vaara'); pb.type = 'submit'; pf.appendChild(pv); pf.appendChild(pb);
      pf.addEventListener('submit', function (e) { e.preventDefault(); api('/tilit/' + id, { method: 'DELETE', body: { vahvista: pv.value.trim() } }).then(function () { ilmoita('Tilin tiedot poistettu.', true); $('#tilitiedot').classList.add('piilossa'); haeTilit(''); }).catch(virhe()); });
      pt.appendChild(pf); k.appendChild(pt);
      k.appendChild(el('h3', 'Kirjanpito'));
      var t1 = el('table'); var w1 = el('div', null, 'taulukko'); w1.appendChild(t1); k.appendChild(w1);
      taulu(t1, ['Aika', 'Tili', '#Muutos', 'Syy', 'Viite', 'Selite', 'Tekijä'], d.kirjanpito, kirjanpitorivi);
      k.appendChild(el('h3', 'Testit'));
      var t2 = el('table'); var w2 = el('div', null, 'taulukko'); w2.appendChild(t2); k.appendChild(w2);
      piirraTestit(t2, d.testit);
      k.scrollIntoView({ behavior: 'smooth' });
    }).catch(virhe());
  }

  function haeTestit() {
    api('/testit?haku=' + encodeURIComponent($('#testi-haku').value) + '&suodatin=' + encodeURIComponent($('#testi-suodatin').value)).then(function (d) { piirraTestit($('#testitaulu'), d.testit); }).catch(virhe());
  }
  function piirraTestit(taulukko, testit) {
    var paivita = function () { if (taulukko.id === 'testitaulu') haeTestit(); else if (testit[0]) avaaTili(testit[0].tili); };
    taulu(taulukko, ['Tunnus', 'Tili', 'Aloitettu', 'Tila', 'Auto ja tulos', 'Hyvityspyyntö', ''], testit, function (t) {
      var tr = el('tr'); var a = el('a', tunnus(t.tunnus), 'tunnus'); a.href = '/v/' + t.tunnus; a.target = '_blank'; a.rel = 'noopener'; solu(tr, '').appendChild(a);
      solu(tr, t.tili, 'tunnus'); solu(tr, aika(t.varattu)); solu(tr, (TILAT[t.tila] || t.tila) + (t.hyvitetty ? ' (hyvitetty)' : '') + (t.testi ? ' · testi' : ''));
      var r = t.raportti; solu(tr, r ? [r.merkki, r.malli, r.kuntoPct != null ? r.kuntoPct + ' %' : '', r.kapasiteettiKwh ? r.kapasiteettiKwh + ' kWh' : ''].filter(Boolean).join(' · ') : '');
      var hp = t.hyvityspyynto; var hs = solu(tr, hp ? hp.tila + ' ' + aika(hp.aika) + (hp.syy ? ': ' + hp.syy : '') : ''); if (hp && hp.tiedot) { hs.appendChild(el('br')); hs.appendChild(el('small', hp.tiedot)); }
      var tt = solu(tr, ''); var rr = el('div', null, 'toimintorivi'); tt.appendChild(rr);
      if (!t.hyvitetty && !t.testi && t.tila !== 'peruttu') rr.appendChild(nappi('Hyvitä', function () {
        rivilomake(tr, [{ otsikko: 'Hyvityksen syy' }].concat(t.tila === 'valmis' ? [{ vahvistus: 'Raportti mitätöidään' }] : []), 'Hyvitä krediitti', function (arvot, mitatoi) {
          api('/testit/' + t.tunnus + '/hyvita', { method: 'POST', body: { selite: arvot[0], mitatoi: mitatoi === true } }).then(function () { ilmoita('Krediitti palautettu tilille.', true); paivita(); }).catch(virhe());
        });
      }));
      if (t.tila === 'valmis') rr.appendChild(nappi('Mitätöi', function () {
        rivilomake(tr, [{ otsikko: 'Mitätöinnin syy (näkyy tarkistussivulla)' }], 'Mitätöi raportti', function (arvot) {
          api('/testit/' + t.tunnus + '/mitatoi', { method: 'POST', body: { syy: arvot[0] } }).then(function () { ilmoita('Raportti mitätöity.', true); paivita(); }).catch(virhe());
        });
      }, 'vaara'));
      if (t.raportti) rr.appendChild(nappi('Poista tiedot', function () {
        rivilomake(tr, [{ otsikko: 'Poiston syy (esim. rekisteröidyn pyyntö)' }], 'Poista raportin tiedot', function (arvot) {
          if (!window.confirm('Poistetaanko raportin tiedot pysyvästi? Tarkistussivu näyttää sen jälkeen, että tiedot on poistettu.')) return;
          api('/testit/' + t.tunnus + '/poista-tiedot', { method: 'POST', body: { syy: arvot[0] } }).then(function () { ilmoita('Raportin tiedot poistettu.', true); paivita(); }).catch(virhe());
        });
      }, 'vaara'));
      if (hp && hp.tila === 'avoin') rr.appendChild(nappi('Hylkää pyyntö', function () {
        rivilomake(tr, [{ otsikko: 'Perustelu' }], 'Hylkää', function (arvot) { api('/testit/' + t.tunnus + '/hylkaa-pyynto', { method: 'POST', body: { selite: arvot[0] } }).then(function () { ilmoita('Hyvityspyyntö hylätty.', true); paivita(); }).catch(virhe()); });
      }));
      return tr;
    });
  }

  var tuotteet = [];
  function piirraTuotteet(lista) {
    tuotteet = (lista || []).map(function (t) { return { tuote: t.tuote, krediitit: t.krediitit }; });
    taulu($('#tuotetaulu'), ['Tuotetunnus (Play Console)', '#Krediittejä', ''], tuotteet, function (t) {
      var tr = el('tr');
      var i1 = el('input'); i1.value = t.tuote; i1.setAttribute('aria-label', 'Tuotetunnus'); i1.addEventListener('input', function () { t.tuote = i1.value.trim(); }); solu(tr, '').appendChild(i1);
      var i2 = el('input'); i2.type = 'number'; i2.min = 1; i2.value = t.krediitit; i2.setAttribute('aria-label', 'Krediittejä'); i2.addEventListener('input', function () { t.krediitit = Number(i2.value); }); solu(tr, '', 'luku').appendChild(i2);
      solu(tr, '').appendChild(nappi('Poista', function () { tuotteet.splice(tuotteet.indexOf(t), 1); piirraTuotteet(tuotteet); }));
      return tr;
    });
  }
  var asiakirjat = {};
  function naytaAsiakirja() { var a = asiakirjat[$('#ak-tyyppi').value]; $('#ak-teksti').value = a && a.teksti || ''; }

  var kutsuTunnus = '';
  function alusta() {
    document.querySelectorAll('#valilehdet button').forEach(function (b) { b.addEventListener('click', function () { valitse(b.getAttribute('data-v')); }); });
    $('#ulos').addEventListener('click', function () { api('/ulos', { method: 'POST' }).then(function () { naytaNakyma('kirjautuminen'); }); });
    $('#kirjautumislomake').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/kirjaudu', { method: 'POST', body: { sahkoposti: $('#k-posti').value.trim(), salasana: $('#k-salasana').value, koodi: $('#k-koodi').value.trim() } })
        .then(function () { $('#k-salasana').value = ''; $('#k-koodi').value = ''; naytaNakyma('hallinta'); }).catch(virhe($('#kirjautumisilmoitus')));
    });
    $('#alustuslomake').addEventListener('submit', function (e) {
      e.preventDefault();
      if ($('#a-salasana').value !== $('#a-salasana2').value) return ilmoita('Salasanat eivät täsmää.', false, $('#alustusilmoitus'));
      var runko = kutsuTunnus ? { kutsu: kutsuTunnus, salasana: $('#a-salasana').value } : { alkutunnus: $('#a-alkutunnus').value.trim(), nimi: $('#a-nimi').value, sahkoposti: $('#a-posti').value, salasana: $('#a-salasana').value };
      api('/alusta', { method: 'POST', body: runko }).then(function (d) {
        $('#alustuslomake').classList.add('piilossa'); $('#alustusvahvistus').classList.remove('piilossa');
        $('#a-avain').textContent = d.salaisuus;
        $('#a-qr').innerHTML = window.QR.qrMatrixToSvg(d.otpauth, { level: 'M', moduleSize: 4, label: 'QR-koodi todennussovellukseen' });
        $('#alustusilmoitus').className = 'ilmoitus';
      }).catch(virhe($('#alustusilmoitus')));
    });
    $('#alustusvahvistus').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/alusta/vahvista', { method: 'POST', body: kutsuTunnus ? { kutsu: kutsuTunnus, koodi: $('#a-koodi').value.trim() } : { alkutunnus: $('#a-alkutunnus').value.trim(), koodi: $('#a-koodi').value.trim() } })
        .then(function () { ilmoita('Tunnus on luotu. Kirjaudu sisään.', true, $('#kirjautumisilmoitus')); naytaNakyma('kirjautuminen'); }).catch(virhe($('#alustusilmoitus')));
    });
    $('#tilihaku').addEventListener('submit', function (e) { e.preventDefault(); haeTilit($('#tili-haku').value); });
    $('#testihaku').addEventListener('submit', function (e) { e.preventDefault(); haeTestit(); });
    $('#perutut').addEventListener('click', function () { api('/perutut-ostot', { method: 'POST' }).then(function (d) { ilmoita(d.vahennetty ? 'Perutuista ostoista vähennettiin krediittejä: ' + d.vahennetty + ' ostoa.' : 'Uusia perumisia ei ole.', true); LATAA.ostot(); }).catch(virhe()); });
    $('#ytlomake').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/asetukset', { method: 'PUT', body: { yhteystiedot: { nimi: $('#yt-nimi').value, yTunnus: $('#yt-ytunnus').value, osoite: $('#yt-osoite').value, sahkoposti: $('#yt-sahkoposti').value, puhelin: $('#yt-puhelin').value } } })
        .then(function () { ilmoita('Yhteystiedot tallennettu.', true); }).catch(virhe());
    });
    $('#lisaa-tuote').addEventListener('click', function () { tuotteet.push({ tuote: '', krediitit: 1 }); piirraTuotteet(tuotteet); });
    $('#myyntilomake').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/asetukset', { method: 'PUT', body: { playLinkki: $('#as-play').value.trim(), hinnasto: $('#as-hinnasto').value, hyvitysaikaMin: Number($('#as-hyvitysaika').value), tuotteet: tuotteet, hinnat: luetutHinnat() } })
        .then(function (a) { piirraTuotteet(a.tuotteet); piirraHinnat(a.hinnat); ilmoita('Tallennettu.', true); }).catch(virhe());
    });
    $('#versiolomake').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/asetukset', { method: 'PUT', body: { vahimmaisversio: $('#ve-min').value.trim(), uusinVersio: $('#ve-uusin').value.trim() } })
        .then(function () { ilmoita('Versiot tallennettu.', true); }).catch(virhe());
    });
    $('#postilomake').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/asetukset', { method: 'PUT', body: { posti: { host: $('#po-host').value.trim(), port: Number($('#po-port').value), secure: $('#po-secure').checked, user: $('#po-user').value.trim(), pass: $('#po-pass').value, lahettaja: $('#po-lahettaja').value.trim(), lahettajaOmat: $('#po-omat').value.trim(), vastaanottaja: $('#po-vastaanottaja').value.trim() } } })
        .then(function (a) { naytaPosti(a.posti); ilmoita('Sähköpostiasetukset tallennettu.', true); }).catch(virhe());
    });
    $('#po-testi').addEventListener('click', function () { api('/posti/testi', { method: 'POST' }).then(function () { ilmoita('Testiviesti lähetetty ilmoitusten osoitteeseen.', true); }).catch(virhe()); });
    $('#huoltolomake').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/asetukset', { method: 'PUT', body: { huoltotila: { tila: $('#ht-tila').value, viesti: $('#ht-viesti').value } } })
        .then(function (a) { naytaHuolto(a.huoltotila); ilmoita(a.huoltotila.tila === 'pois' ? 'Huoltotila on pois päältä.' : 'Huoltotila on päällä.', true); }).catch(virhe());
    });
    $('#ak-tyyppi').addEventListener('change', naytaAsiakirja);
    $('#asiakirjalomake').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/asetukset', { method: 'PUT', body: { asiakirja: { tyyppi: $('#ak-tyyppi').value, teksti: $('#ak-teksti').value } } })
        .then(function (a) { asiakirjat = a.asiakirjat; ilmoita($('#ak-teksti').value.trim() ? 'Asiakirja tallennettu ja julkaistu.' : 'Muokattu teksti poistettu, sivulla näkyy oletusteksti.', true); }).catch(virhe());
    });
    $('#salasanalomake').addEventListener('submit', function (e) {
      e.preventDefault();
      api('/salasana', { method: 'POST', body: { nykyinen: $('#s-nykyinen').value, uusi: $('#s-uusi').value } }).then(function (d) { ilmoita(d.viesti, true, $('#kirjautumisilmoitus')); naytaNakyma('kirjautuminen'); }).catch(virhe());
    });
    $('#varmuuskopio').addEventListener('click', function () { api('/varmuuskopio', { method: 'POST' }).then(function (d) { ilmoita(d.nimi ? 'Varmuuskopio otettu: ' + d.nimi : 'Varmuuskopio on jo otettu tällä sekunnilla.', true); }).catch(virhe()); });

    var kutsu = (/[#&]kutsu=([A-Za-z0-9_-]{43})/.exec(location.hash) || [])[1] || '';
    if (kutsu) {
      history.replaceState(null, '', '/hallinta'); // kutsutunnus ei jää osoiteriville eikä selaimen historiaan
      naytaNakyma('alustus');
      $('#a-ensimmainen').classList.add('piilossa');
      $('#a-otsikko').textContent = 'Hallinnan kutsu';
      api('/kutsu', { method: 'POST', body: { kutsu: kutsu } }).then(function (k) {
        $('#a-ohje').textContent = 'Tervetuloa, ' + k.nimi + '. Luo salasana tunnukselle ' + k.sahkoposti + ' ja ota käyttöön kaksivaiheinen tunnistus todennussovelluksella.';
      }).catch(function (e) { $('#a-ohje').textContent = e.message; $('#alustuslomake').classList.add('piilossa'); });
      kutsuTunnus = kutsu;
      return;
    }
    api('/tila').then(function (t) {
      if (t.kirjautunut) naytaNakyma('hallinta');
      else if (t.alustettu) naytaNakyma('kirjautuminen');
      else {
        naytaNakyma('alustus');
        if (!t.alkutunnusAsetettu) ilmoita('Palvelimelle ei ole asetettu alkutunnusta. Aja AKVERIn julkaisu Hallintatyökalussa.', false, $('#alustusilmoitus'));
      }
    }).catch(function (e) { document.body.textContent = e.message; });
  }
  document.addEventListener('DOMContentLoaded', alusta);
})();
