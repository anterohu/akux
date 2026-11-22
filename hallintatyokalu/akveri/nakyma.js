// akveri/nakyma.js — AKVERIn lohko Hallintatyökalussa: akveri.fi-palvelimen julkaisu, päivitys, tila, versiot, asetukset,
// varmuuskopiot, käyttäjät ja omat lataukset. AKVERI on oma oksansa: se päivitetään omalla paketillaan, eikä se riipu
// Vuoropisteestä. Käyttää rungon apufunktioita (runko.js: $, esc, api, merkitseValikko, vaiheetHtml).
'use strict';

rekisteroiLohko({
  osa: 'akveri',
  nimi: 'AKVERI',
  logo: '/osat/akveri/logo.svg',
  valikko: [{ id: 'akveriBtn', teksti: 'akveri.fi' }],
  paivitysLisatieto: '<h2>akveri.fi-palvelin</h2><p class="johdanto">AKVERI-paketin mukana tulee akveri.fi-palvelimen ohjelma. Kun olet päivittänyt AKVERIn, vie uusi versio palvelimelle kohdasta akveri.fi → Päivitä palvelin. Android-sovellus päivitetään Google Playn kautta.</p>',
  aloitus: () => $('#akveriBtn').click()
});

const akveriKoko = (n) => n >= 1048576 ? (n / 1048576).toFixed(1).replace('.', ',') + ' Mt' : Math.max(1, Math.round(n / 1024)) + ' kt';
function akveriJson(polku, metodi, runko) {
  return api(polku, { method: metodi, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(runko || {}) });
}

async function naytaAkveriNakyma() {
  const sisalto = $('#paasisalto');
  sisalto.innerHTML = '<div class="kortti"><h2>AKVERI</h2><p class="ohje">Ladataan…</p></div>';
  let d;
  try { d = await api('/api/akveri/asetukset'); } catch (e) { sisalto.innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; return; }
  const a = d.asetukset;
  const uusin = d.paketit[0];
  sisalto.innerHTML = `
    <div class="kortti">
      <h2>AKVERI (${esc(a.domain)})</h2>
      <p class="johdanto">AKVERIn esittelysivusto, raporttien tarkistus, sovelluksen krediitit ja hallinta (${esc(a.domain)}/hallinta). ${a.erillinenPalvelin ? `AKVERI on omalla palvelimellaan (<code>${esc(a.palvelinHost)}</code>).` : `AKVERI asennetaan samalle palvelimelle kuin Vuoropiste${d.palvelin.host ? ` (<code>${esc(d.palvelin.host)}</code>)` : ''}.`} Asennus on aina erillään Vuoropisteestä: oma käyttäjä <code>akveri</code>, omat kansiot <code>/opt/akveri</code> ja <code>/var/lib/akveri</code>, oma asetustiedosto ja oma osoite. Vuoropisteen päivitykset eivät koske AKVERIin, eikä AKVERIn päivitys Vuoropisteeseen.</p>
      ${(a.erillinenPalvelin ? a.palvelinHost : d.palvelin.host) ? '' : '<div class="viesti virhe">Palvelinta ei ole asetettu. Aseta palvelinyhteys kohdassa Asetukset → Palvelinyhteys tai valitse AKVERIlle oma palvelin asetuksista.</div>'}
      <div class="toiminnot">
        ${a.julkaistu ? `<button type="button" id="akVieBtn" ${uusin ? '' : 'disabled'}>Päivitä palvelin versioon ${uusin ? esc(uusin.versio) : '–'}</button>` : `<button type="button" id="akJulkaiseBtn" ${uusin ? '' : 'disabled'}>Julkaise AKVERI</button>`}
        <button type="button" id="akTilaBtn" class="toissijainen">Tarkista tila</button>
        <button type="button" id="akDnsBtn" class="toissijainen">Tarkista DNS</button>
        ${a.julkaistu ? '<button type="button" id="akPalautaBtn" class="vaara">Palauta edellinen versio</button>' : ''}
      </div>
      ${a.julkaistu ? '' : '<p class="ohje">Julkaise tekee kaiken kerralla: tarkistaa DNS:n, luo käyttäjän ja kansiot, asentaa Noden ja palvelun, lisää osoitteen Caddyyn, kirjoittaa asetukset ja vie uusimman palvelinpaketin. Toiminto on turvallista ajaa uudelleen.</p>'}
      <div id="akTulos"></div>
    </div>

    <div class="kortti">
      <h2>Palvelinpaketit (versiot)</h2>
      <p class="johdanto">AKVERI-palvelimen julkaisupaketti <code>akveri-palvelin-x.y.z.zip</code> tulee AKVERIn GitHub-julkaisusta. Paketti tarkistetaan (tuote, versio ja jokaisen tiedoston tarkiste) ennen kuin se tallennetaan. Vanhat versiot säilyvät tässä, joten minkä tahansa version voi viedä uudelleen.</p>
      <div class="toiminnot"><label class="nappi toissijainen" for="akPakettiTiedosto">Lisää paketti…</label><input type="file" id="akPakettiTiedosto" accept=".zip" class="piilossa"></div>
      <div id="akPakettiViesti"></div>
      <table><thead><tr><th>Versio</th><th>Koko</th><th>Lisätty</th><th></th></tr></thead><tbody>
      ${d.paketit.length ? d.paketit.map((p, i) => `<tr><td><strong>${esc(p.versio)}</strong>${i === 0 ? ' (uusin)' : ''}</td><td>${akveriKoko(p.koko)}</td><td>${esc(muotoilePvm(p.tallennettu))}</td>
        <td class="toiminnot-solu">${a.julkaistu ? `<button type="button" class="toissijainen akVieVersio" data-v="${esc(p.versio)}">Vie palvelimelle</button> ` : ''}<a class="nappi toissijainen" href="/api/akveri/paketit/${esc(p.versio)}">Lataa</a> <button type="button" class="vaara akPoistaPaketti" data-v="${esc(p.versio)}">Poista</button></td></tr>`).join('')
        : '<tr><td colspan="4">Ei paketteja. Lisää AKVERI-palvelimen julkaisupaketti.</td></tr>'}
      </tbody></table>
    </div>

    <div class="kortti">
      <h2>Asetukset</h2>
      <div class="rivi">
        <div><label for="akDomain">Verkkotunnus</label><input type="text" id="akDomain" value="${esc(a.domain)}" autocomplete="off"></div>
        <div><label for="akPortti">Portti palvelimella <small>Vuoropisteen asiakkaat käyttävät portteja 3101–5100</small></label><input type="number" id="akPortti" value="${esc(a.portti)}"></div>
        <div><label for="akPaketti">Android-sovelluksen paketti</label><input type="text" id="akPaketti" value="${esc(a.paketti)}" autocomplete="off"></div>
      </div>
      <div class="rivi">
        <div><label for="akIp">Hallinnan sallitut IP-osoitteet <small>Valinnainen. Tyhjä = hallinta ei ole rajattu osoitteisiin (kirjautuminen vaatii silti salasanan ja vahvistuskoodin).</small></label><input type="text" id="akIp" value="${esc(a.sallitutIp)}" placeholder="203.0.113.5, 198.51.100.0/24" autocomplete="off"></div>
      </div>
      <h3>Palvelin</h3>
      <div class="rivi"><div><label for="akErillinen">AKVERIn palvelin</label><select id="akErillinen"><option value="ei" ${a.erillinenPalvelin ? '' : 'selected'}>Sama kuin Vuoropisteellä${d.palvelin.host ? ' (' + esc(d.palvelin.host) + ')' : ''}</option><option value="kylla" ${a.erillinenPalvelin ? 'selected' : ''}>Oma palvelin</option></select></div></div>
      <div class="rivi" id="akOmaPalvelin" ${a.erillinenPalvelin ? '' : 'style="display:none"'}>
        <div><label for="akHost">Palvelimen osoite</label><input type="text" id="akHost" value="${esc(a.palvelinHost)}" autocomplete="off"></div>
        <div><label for="akSshPortti">SSH-portti</label><input type="number" id="akSshPortti" value="${esc(a.palvelinPortti)}"></div>
        <div><label for="akSshKayttaja">SSH-käyttäjä</label><input type="text" id="akSshKayttaja" value="${esc(a.palvelinKayttaja)}" autocomplete="off"></div>
      </div>
      <p class="ohje" id="akOmaPalvelinOhje" ${a.erillinenPalvelin ? '' : 'style="display:none"'}>Omalle palvelimelle kirjaudutaan Hallintatyökalun SSH-avaimella. Lisää avaimen julkinen osa (Asetukset → Palvelinyhteys → Näytä julkinen avain) palvelimen tiedostoon ~/.ssh/authorized_keys. Palvelimen vaihto ei siirrä tietoja: vie ensin varmuuskopio vanhalta palvelimelta.</p>
      <h3>Google Play -ostojen tarkistus</h3>
      <p class="ohje">Palvelin tarkistaa jokaisen krediittioston Googlelta palvelutilin avaimella. Ohje: AKVERIn <code>palvelin/README.md</code>, kohta Google Play -ostojen tarkistus. Avain salataan tässä työkalussa ja tallennetaan palvelimelle tiedostoon, jonka vain AKVERI voi lukea.</p>
      <p>${a.googleTiliAsetettu ? `<span class="viesti ok" style="display:inline-block">Palvelutili asetettu: <code>${esc(a.googleTiliSahkoposti)}</code></span>` : '<span class="viesti virhe" style="display:inline-block">Palvelutiliä ei ole asetettu. Krediittien osto ei toimi ennen kuin avain on asetettu.</span>'}</p>
      <div class="toiminnot"><label class="nappi toissijainen" for="akGoogleTiedosto">${a.googleTiliAsetettu ? 'Vaihda palvelutilin avain…' : 'Valitse palvelutilin avain (.json)…'}</label><input type="file" id="akGoogleTiedosto" accept=".json,application/json" class="piilossa">
        ${a.googleTiliAsetettu ? '<button type="button" id="akGooglePoista" class="vaara">Poista avain</button>' : ''}</div>
      <div class="toiminnot"><button type="button" id="akTallennaBtn">Tallenna asetukset</button>${a.julkaistu ? '<button type="button" id="akAsetuksetPalvelimelleBtn" class="toissijainen">Vie asetukset palvelimelle</button>' : ''}</div>
      <p class="ohje">Tallennus koskee tätä työkalua. Palvelin saa muutetut asetukset painikkeella Vie asetukset palvelimelle (tai seuraavassa julkaisussa). AKVERI käynnistyy silloin uudelleen.</p>
      <div id="akAsetusViesti"></div>
    </div>

    ${a.julkaistu ? `
    <div class="kortti">
      <h2>Hallinnan käyttöönotto</h2>
      <p class="johdanto">Avaa <a href="https://${esc(a.domain)}/hallinta" target="_blank" rel="noopener">${esc(a.domain)}/hallinta</a>. Ensimmäisellä kerralla tarvitset alkutunnuksen, salasanan ja todennussovelluksen. Alkutunnus kelpaa vain tunnuksen luontiin.</p>
      <div class="toiminnot"><button type="button" id="akAlkutunnusBtn" class="toissijainen">Näytä alkutunnus</button><code id="akAlkutunnus" style="user-select:all"></code></div>
    </div>

    <div class="kortti">
      <h2>Hallinnan käyttäjät</h2>
      <p class="johdanto">Lisää ja poista ${esc(a.domain)}/hallinta-käyttäjiä. Uusi käyttäjä saa kertakäyttöisen kutsulinkin (voimassa 24 tuntia), jolla hän asettaa oman salasanansa ja kaksivaiheisen tunnistuksen. Toimita linkki käyttäjälle turvallisesti. Poisto katkaisee kirjautumisen heti. Viimeistä käyttäjää ei voi poistaa.</p>
      <div class="rivi"><div><label for="akKNimi">Nimi</label><input type="text" id="akKNimi" autocomplete="off"></div><div><label for="akKPosti">Sähköposti</label><input type="text" id="akKPosti" autocomplete="off"></div></div>
      <div class="toiminnot"><button type="button" id="akKLisaa" class="toissijainen">Luo kutsu</button><button type="button" id="akKLista" class="toissijainen">Näytä käyttäjät</button></div>
      <div id="akKTulos"></div>
    </div>

    <div class="kortti">
      <h2>Omat lataukset</h2>
      <p class="johdanto">Windows-versio ja muut tiedostot, jotka ovat vain sinun ladattavissasi hallinnan kohdassa Omat lataukset. Asiakkaille ei jaeta asennustiedostoja: sovellus ladataan Google Playsta.</p>
      <div class="toiminnot"><label class="nappi toissijainen" for="akLatausTiedosto">Lähetä tiedosto palvelimelle…</label><input type="file" id="akLatausTiedosto" accept=".exe,.msi,.zip,.apk,.aab" class="piilossa"><button type="button" id="akLatauksetBtn" class="toissijainen">Näytä palvelimen tiedostot</button></div>
      <div id="akLatausViesti"></div><div id="akLataukset"></div>
    </div>

    <div class="kortti">
      <h2>Varmuuskopiot</h2>
      <p class="johdanto">Palvelin ottaa AKVERIn tiedoista kopion päivittäin (30 uusinta) ja ennen jokaista päivitystä. Tiedot ovat AKVERIn omia liiketoimintatietoja, joten kopion voi ladata myös omalle koneelle talteen.</p>
      <div class="toiminnot"><button type="button" id="akKopioiBtn" class="toissijainen">Ota varmuuskopio nyt</button><button type="button" id="akKopiotBtn" class="toissijainen">Näytä varmuuskopiot</button></div>
      <div id="akKopiot"></div>
    </div>` : ''}
    <div class="kortti" id="akDnsKortti" style="display:none"></div>`;

  const tulos = $('#akTulos');
  const odota = (kohde, teksti) => { kohde.innerHTML = `<div class="viesti">${esc(teksti)}</div>`; };
  async function palvelinToiminto(polku, runko, teksti) {
    odota(tulos, teksti || 'Odota…');
    try {
      const r = await akveriJson('/api/akveri/' + polku, 'POST', runko);
      if (r.dns) naytaDns(r.dns);
      tulos.innerHTML = vaiheetHtml(r) + (r.ok && r.osoite ? `<div class="viesti ok">AKVERI on käytössä osoitteessa <a href="${esc(r.osoite)}" target="_blank" rel="noopener">${esc(r.osoite)}</a> (versio ${esc(r.versio || '')}).</div>` : '');
      return r;
    } catch (e) { tulos.innerHTML = vaiheetHtml(e.data && e.data.vaiheet ? e.data : { ok: false, virhe: e.message }); return null; }
  }
  function naytaDns(dns) {
    const k = $('#akDnsKortti');
    k.style.display = '';
    k.innerHTML = `<h2>DNS-tietueet</h2><p class="johdanto">Lisää verkkotunnuksen hallinnassa nämä A-tietueet palvelimen osoitteeseen. Voimaantulo kestää yleensä minuuteista muutamaan tuntiin.</p>
      <table><thead><tr><th>Nimi</th><th>Tyyppi</th><th>Arvo</th><th>Tila</th></tr></thead><tbody>${dns.tietueet.map(t => `<tr><td><code>${esc(t.nimi)}</code></td><td>${esc(t.tyyppi)}</td><td><code>${esc(t.arvo)}</code></td><td>${t.ok ? '✓ kunnossa' : `✗ ${t.nykyinen.length ? 'osoittaa: ' + esc(t.nykyinen.join(', ')) : 'puuttuu'}`}</td></tr>`).join('')}</tbody></table>`;
  }

  const kaynnista = (id, fn) => { const e = $('#' + id); if (e) e.addEventListener('click', fn); };
  kaynnista('akJulkaiseBtn', async () => { const r = await palvelinToiminto('julkaise', {}, 'Julkaistaan. Ensimmäinen julkaisu voi kestää useita minuutteja (Node, Caddy ja varmenne).'); if (r && r.ok) setTimeout(naytaAkveriNakyma, 1500); });
  kaynnista('akVieBtn', () => palvelinToiminto('vie', { versio: uusin.versio }, 'Viedään versiota ' + uusin.versio + '. Palvelin ottaa ensin varmuuskopion. Jos uusi versio ei käynnisty, edellinen palautetaan automaattisesti.'));
  kaynnista('akDnsBtn', async () => { try { naytaDns(await akveriJson('/api/akveri/dns', 'POST')); } catch (e) { tulos.innerHTML = vaiheetHtml({ ok: false, virhe: e.message }); } });
  kaynnista('akPalautaBtn', () => { if (confirm('Palautetaanko edellinen versio? Nykyinen versio jää palvelimelle, joten palautuksen voi perua tekemällä saman uudelleen.')) palvelinToiminto('palauta', {}, 'Palautetaan edellistä versiota…'); });
  kaynnista('akTilaBtn', async () => {
    odota(tulos, 'Haetaan tilaa…');
    try {
      const t = await akveriJson('/api/akveri/tila', 'POST');
      if (!t.ok) { tulos.innerHTML = vaiheetHtml(t); return; }
      tulos.innerHTML = `<table><tbody>
        <tr><th>Palvelu</th><td>${t.tila === 'active' ? '✓ käynnissä' : '✗ ' + esc(t.tila || 'ei asennettu')}${t.kaynnistyyKoneenMukana ? ', käynnistyy palvelimen mukana' : ''}</td></tr>
        <tr><th>Vastaa</th><td>${t.vastaa ? '✓ kyllä' : '✗ ei'}</td></tr>
        <tr><th>Versio</th><td>${esc(t.versio || '–')}${t.edellinen ? ` (edellinen ${esc(t.edellinen)} tallessa)` : ''}</td></tr>
        <tr><th>Caddy</th><td>${t.caddy === 'active' ? '✓ käynnissä' : '✗ ' + esc(t.caddy)}</td></tr>
        <tr><th>Levyn käyttö</th><td>${esc(t.levy)}</td></tr></tbody></table>
        <details><summary>Loki (40 viimeistä riviä)</summary><pre class="vi-tuloste">${esc(t.loki || '')}</pre></details>`;
    } catch (e) { tulos.innerHTML = vaiheetHtml({ ok: false, virhe: e.message }); }
  });

  // Paketit
  $('#akPakettiTiedosto').addEventListener('change', async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const v = $('#akPakettiViesti'); odota(v, 'Tarkistetaan pakettia…');
    try { const r = await api('/api/akveri/paketit', { method: 'POST', body: f }); v.innerHTML = `<div class="viesti ok">Paketti ${esc(r.paketti.versio)} tarkistettu ja tallennettu (${r.paketti.tiedostoja} tiedostoa).</div>`; setTimeout(naytaAkveriNakyma, 1200); }
    catch (err) { v.innerHTML = `<div class="viesti virhe">${esc(err.message)}</div>`; }
    e.target.value = '';
  });
  document.querySelectorAll('.akVieVersio').forEach(b => b.addEventListener('click', () => {
    if (confirm(`Viedäänkö versio ${b.dataset.v} palvelimelle?`)) palvelinToiminto('vie', { versio: b.dataset.v }, 'Viedään versiota ' + b.dataset.v + '…');
  }));
  document.querySelectorAll('.akPoistaPaketti').forEach(b => b.addEventListener('click', async () => {
    if (!confirm(`Poistetaanko version ${b.dataset.v} paketti tästä työkalusta? Palvelimeen poisto ei vaikuta.`)) return;
    try { await api('/api/akveri/paketit/' + b.dataset.v, { method: 'DELETE' }); naytaAkveriNakyma(); } catch (e) { $('#akPakettiViesti').innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; }
  }));

  // Asetukset
  let googleTili;
  $('#akGoogleTiedosto').addEventListener('change', async (e) => {
    const f = e.target.files[0]; if (!f) return;
    googleTili = await f.text();
    $('#akAsetusViesti').innerHTML = `<div class="viesti">Avain ${esc(f.name)} valittu. Tallenna asetukset.</div>`;
  });
  $('#akErillinen').addEventListener('change', () => { const n = $('#akErillinen').value === 'kylla' ? '' : 'none'; $('#akOmaPalvelin').style.display = n; $('#akOmaPalvelinOhje').style.display = n; });
  const tallenna = () => akveriJson('/api/akveri/asetukset', 'PUT', { domain: $('#akDomain').value, portti: Number($('#akPortti').value), paketti: $('#akPaketti').value, sallitutIp: $('#akIp').value,
    erillinenPalvelin: $('#akErillinen').value === 'kylla', palvelinHost: $('#akHost').value, palvelinPortti: Number($('#akSshPortti').value), palvelinKayttaja: $('#akSshKayttaja').value, ...(googleTili ? { googleTili } : {}) });
  $('#akTallennaBtn').addEventListener('click', async () => {
    try { await tallenna(); $('#akAsetusViesti').innerHTML = '<div class="viesti ok">Asetukset tallennettu.</div>'; setTimeout(naytaAkveriNakyma, 1200); }
    catch (e) { $('#akAsetusViesti').innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; }
  });
  kaynnista('akGooglePoista', async () => {
    if (!confirm('Poistetaanko palvelutilin avain tästä työkalusta? Palvelimelta se poistuu, kun viet asetukset palvelimelle.')) return;
    try { await akveriJson('/api/akveri/asetukset', 'PUT', { poistaSalaisuus: 'googleTili' }); naytaAkveriNakyma(); } catch (e) { $('#akAsetusViesti').innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; }
  });
  kaynnista('akAsetuksetPalvelimelleBtn', async () => { try { await tallenna(); } catch (e) { $('#akAsetusViesti').innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; return; } palvelinToiminto('asetukset-palvelimelle', {}, 'Viedään asetuksia palvelimelle…'); });
  kaynnista('akAlkutunnusBtn', async () => { try { $('#akAlkutunnus').textContent = (await api('/api/akveri/alkutunnus')).alkutunnus || 'Ei vielä luotu'; } catch (e) { $('#akAlkutunnus').textContent = e.message; } });

  // Hallinnan käyttäjät
  const kayttajaLista = async () => {
    const k = $('#akKTulos'); odota(k, 'Haetaan…');
    try {
      const r = await akveriJson('/api/akveri/kayttajat', 'POST');
      if (!r.ok) { k.innerHTML = vaiheetHtml(r); return; }
      const rivit = r.kayttajat.map(x => `<tr><td>${esc(x.nimi)}</td><td>${esc(x.sahkoposti)}</td><td>${x.viimeksiKirjautunut ? 'Kirjautunut ' + esc(muotoilePvm(x.viimeksiKirjautunut)) : 'Ei vielä kirjautunut'}</td><td class="toiminnot-solu"><button type="button" class="vaara akKPoista" data-p="${esc(x.sahkoposti)}">Poista</button></td></tr>`)
        .concat(r.kutsut.map(x => `<tr><td>${esc(x.nimi)}</td><td>${esc(x.sahkoposti)}</td><td>Kutsu voimassa ${esc(muotoilePvm(x.vanhenee))} asti</td><td></td></tr>`));
      k.innerHTML = `<table><thead><tr><th>Nimi</th><th>Sähköposti</th><th>Tila</th><th></th></tr></thead><tbody>${rivit.join('') || '<tr><td colspan="4">Ei käyttäjiä.</td></tr>'}</tbody></table>`;
      k.querySelectorAll('.akKPoista').forEach(b => b.addEventListener('click', async () => {
        if (!confirm(`Poistetaanko käyttäjä ${b.dataset.p}? Kirjautuminen päättyy heti.`)) return;
        const r2 = await akveriJson('/api/akveri/poista-kayttaja', 'POST', { sahkoposti: b.dataset.p });
        if (!r2.ok) { k.innerHTML = vaiheetHtml(r2); return; }
        kayttajaLista();
      }));
    } catch (e) { k.innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; }
  };
  kaynnista('akKLista', kayttajaLista);
  kaynnista('akKLisaa', async () => {
    const k = $('#akKTulos'); odota(k, 'Luodaan kutsua…');
    try {
      const r = await akveriJson('/api/akveri/lisaa-kayttaja', 'POST', { nimi: $('#akKNimi').value, sahkoposti: $('#akKPosti').value });
      k.innerHTML = r.ok && r.linkki ? `<div class="viesti ok">Kutsu luotu. Linkki näytetään vain nyt ja on voimassa 24 tuntia:<br><code style="user-select:all;word-break:break-all;">${esc(r.linkki)}</code></div>` : vaiheetHtml(r);
    } catch (e) { k.innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; }
  });

  // Omat lataukset
  const latausLista = async () => {
    const k = $('#akLataukset'); odota(k, 'Haetaan…');
    try {
      const r = await akveriJson('/api/akveri/lataukset', 'POST');
      if (!r.ok) { k.innerHTML = vaiheetHtml(r); return; }
      k.innerHTML = r.lataukset.length ? `<table><tbody>${r.lataukset.map(l => `<tr><td>${esc(l.nimi)}</td><td>${akveriKoko(l.koko)}</td><td class="toiminnot-solu"><button type="button" class="vaara akPoistaLataus" data-n="${esc(l.nimi)}">Poista</button></td></tr>`).join('')}</tbody></table>` : '<p class="ohje">Palvelimella ei ole tiedostoja.</p>';
      k.querySelectorAll('.akPoistaLataus').forEach(b => b.addEventListener('click', async () => {
        if (!confirm(`Poistetaanko ${b.dataset.n} palvelimelta?`)) return;
        await akveriJson('/api/akveri/poista-lataus', 'POST', { nimi: b.dataset.n }); latausLista();
      }));
    } catch (e) { k.innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; }
  };
  kaynnista('akLatauksetBtn', latausLista);
  const lt = $('#akLatausTiedosto');
  if (lt) lt.addEventListener('change', async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const v = $('#akLatausViesti'); odota(v, `Lähetetään ${f.name} (${akveriKoko(f.size)})…`);
    try {
      const r = await api('/api/akveri/lataus?nimi=' + encodeURIComponent(f.name), { method: 'POST', body: f });
      v.innerHTML = r.ok ? `<div class="viesti ok">${esc(f.name)} on palvelimella. Lataa se hallinnan kohdasta Omat lataukset.</div>` : vaiheetHtml(r);
      latausLista();
    } catch (err) { v.innerHTML = `<div class="viesti virhe">${esc(err.message)}</div>`; }
    e.target.value = '';
  });

  // Varmuuskopiot
  const kopiot = async () => {
    const k = $('#akKopiot'); odota(k, 'Haetaan…');
    try {
      const r = await akveriJson('/api/akveri/varmuuskopiot', 'POST');
      if (!r.ok) { k.innerHTML = vaiheetHtml(r); return; }
      k.innerHTML = r.varmuuskopiot.length ? `<table><tbody>${r.varmuuskopiot.map(c => `<tr><td>${esc(c.nimi)}</td><td>${akveriKoko(c.koko)}</td><td class="toiminnot-solu"><a class="nappi toissijainen" href="/api/akveri/varmuuskopio?nimi=${encodeURIComponent(c.nimi)}">Lataa</a></td></tr>`).join('')}</tbody></table>` : '<p class="ohje">Ei varmuuskopioita.</p>';
    } catch (e) { k.innerHTML = `<div class="viesti virhe">${esc(e.message)}</div>`; }
  };
  kaynnista('akKopiotBtn', kopiot);
  kaynnista('akKopioiBtn', async () => { const r = await palvelinToiminto('varmuuskopioi', {}, 'Otetaan varmuuskopio…'); if (r && r.ok) kopiot(); });
}

$('#akveriBtn').addEventListener('click', () => {
  VALITTU_ID = null;
  merkitseValikko('akveriBtn');
  document.querySelectorAll('.asiakaslista li').forEach(li => li.classList.remove('valittu'));
  naytaAkveriNakyma();
});
