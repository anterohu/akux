// akveri/vienti.js — AKVERI-palvelimen (akveri.fi) vienti samalle palvelimelle Vuoropisteen kanssa, mutta täysin erillään.
//
// Erillisyys Vuoropisteestä:
//   - oma järjestelmäkäyttäjä "akveri" (ei kirjautumista), omat kansiot /opt/akveri ja /var/lib/akveri
//   - oma asetustiedosto /etc/akveri/akveri.env (vain root ja akveri). Vuoropisteen yhteisiä asetuksia (/etc/vuoro/yhteinen.env) ei lueta.
//   - oma systemd-palvelu, jonka merkintä X-Palvelinyllapito-Rooli=akveri estää Vuoropisteen siivouksia käsittelemästä sitä
//     Vuoropisteen asiakkaana. Noden yölliset korjauspäivitykset ja lokien siivous koskevat sitä kuten muitakin palveluita.
//   - oma Caddy-osoite (akveri.fi ja www-ohjaus), oma portti (oletus 3090, Vuoropisteen asiakkaiden porttialueen ulkopuolella)
//
// AKVERI-palvelin toimitetaan AKVERIn omasta repositoriosta julkaisupakettina akveri-palvelin-<versio>.zip. Paketissa on
// manifest.json, jossa on jokaisen tiedoston SHA-256-tiiviste. Paketti tarkistetaan ennen kuin se tallennetaan tai viedään.
// Päivitys: varmuuskopio, uusi versio rinnalle, käynnistys ja terveystarkistus. Jos uusi versio ei vastaa, edellinen palautetaan
// automaattisesti. Edellinen versio jää palvelimelle, ja sen voi palauttaa myös käsin.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const dns = require('dns').promises;
const ssh = require('../ssh-ajaja');
const palvelin = require('../palvelinvienti');
const arkisto = require('../arkisto');
const { lainaa } = ssh;

const PALVELU = 'akveri';
const KAYTTAJA = 'akveri';
const KANSIOT = { sovelluskansio: '/opt/akveri', dbKansio: '/var/lib/akveri' };
const NODE_MAJOR = 22;
const LATAUS_NIMI = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(exe|zip|apk|aab|msi)$/;
const PAKETTI_MAX = 20 * 1024 * 1024;
const LATAUS_MAX = 600 * 1024 * 1024;

function profiili(oletuspalvelin, avainPolku, asetukset) {
  const p = ssh.tarkistaSshProfiili({
    host: oletuspalvelin.host, portti: oletuspalvelin.portti, kayttaja: oletuspalvelin.kayttaja, sudo: oletuspalvelin.sudo,
    avain: avainPolku || '', ...KANSIOT, palvelu: PALVELU, sovellusPortti: asetukset.portti, domain: asetukset.domain, tyyppi: 'node'
  });
  p.ajoKayttaja = KAYTTAJA; // oma käyttäjä, ei vuoro-alkuista (Vuoropisteen asiakkaiden poisto ei koske siihen)
  p.terveysPolku = '/api/v1/tila';
  return p;
}
const paivittaisetKansio = (p) => p.dbKansio + '-paivittaiset';
const latauskansio = (p) => p.dbKansio + '-lataukset';

function yksikko(p) {
  return {
    kuvaus: 'AKVERI (' + (p.domain || 'akveri.fi') + ')', rooli: 'akveri',
    ymparisto: ['LUOTETTU_PROXY=1', 'AKVERI_VARMUUSKOPIOT=' + paivittaisetKansio(p), 'AKVERI_LATAUKSET=' + latauskansio(p)],
    ymparistotiedosto: '$ETC/akveri/akveri.env'
  };
}

// ---------------------------------------------------------------- julkaisupaketti
const SEMVER = /^\d{1,3}\.\d{1,3}\.\d{1,3}$/;
function turvallinenNimi(n) {
  return typeof n === 'string' && n.length < 300 && !n.startsWith('/') && !n.includes('\\') && !n.split('/').some(o => o === '..' || o === '' || o === '.') && /^[A-Za-z0-9._/-]+$/.test(n);
}
// Lukee ja tarkistaa akveri-palvelin-<versio>.zip-paketin. Palauttaa { versio, tiedostot: [{ nimi, data }], node }.
function lueJulkaisupaketti(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < 100) throw new Error('Tiedosto ei ole AKVERI-palvelimen julkaisupaketti.');
  if (buf.length > PAKETTI_MAX) throw new Error('Paketti on liian suuri.');
  let osat;
  try { osat = arkisto.lueZip(buf); } catch (e) { throw new Error('Paketti ei ole kelvollinen zip-tiedosto: ' + e.message); }
  const m = osat.find(o => o.nimi === 'manifest.json');
  if (!m) throw new Error('Paketista puuttuu manifest.json. Kokoa paketti AKVERI-repositoriossa komennolla node palvelin/kokoa.js.');
  let manifest;
  try { manifest = JSON.parse(m.data.toString('utf8')); } catch (e) { throw new Error('Paketin manifest.json on vioittunut.'); }
  if (manifest.tuote !== 'akveri-palvelin') throw new Error('Paketti ei ole AKVERI-palvelimen paketti (tuote: ' + String(manifest.tuote) + ').');
  if (!SEMVER.test(String(manifest.versio))) throw new Error('Paketin versio puuttuu tai on virheellinen.');
  const lista = manifest.tiedostot && typeof manifest.tiedostot === 'object' ? manifest.tiedostot : {};
  const tiedostot = [];
  for (const o of osat) {
    if (o.nimi === 'manifest.json') continue;
    if (!turvallinenNimi(o.nimi)) throw new Error('Paketissa on virheellinen tiedostonimi: ' + o.nimi);
    if (!lista[o.nimi]) throw new Error('Paketissa on tiedosto, jota manifest ei luettele: ' + o.nimi);
    if (crypto.createHash('sha256').update(o.data).digest('hex') !== lista[o.nimi]) throw new Error('Tiedoston tarkiste ei täsmää: ' + o.nimi + '. Paketti on vioittunut tai sitä on muutettu.');
    tiedostot.push({ nimi: o.nimi, data: o.data });
  }
  for (const n of Object.keys(lista)) if (!tiedostot.some(t => t.nimi === n)) throw new Error('Paketista puuttuu tiedosto: ' + n);
  for (const pakollinen of ['server.js', 'package.json', 'sivusto/index.html', 'lib/sovellus.js']) {
    if (!tiedostot.some(t => t.nimi === pakollinen)) throw new Error('Paketista puuttuu ' + pakollinen + '.');
  }
  let pkg;
  try { pkg = JSON.parse(tiedostot.find(t => t.nimi === 'package.json').data.toString('utf8')); } catch (e) { throw new Error('Paketin package.json on vioittunut.'); }
  if (pkg.version !== manifest.versio || pkg.name !== 'akveri-palvelin') throw new Error('Paketin package.json ei vastaa manifestia.');
  return { versio: manifest.versio, tiedostot, node: Number(manifest.node) || NODE_MAJOR };
}

// Paikallinen versiovarasto: DATA_DIR/akveri/paketit/akveri-palvelin-<versio>.zip
const pakettikansio = (dataDir) => path.join(dataDir, 'akveri', 'paketit');
function vertaaVersioita(a, b) { const x = a.split('.').map(Number), y = b.split('.').map(Number); for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] - y[i]; return 0; }
function tallennaPaketti(dataDir, buf) {
  const t = lueJulkaisupaketti(buf);
  fs.mkdirSync(pakettikansio(dataDir), { recursive: true, mode: 0o700 });
  const kohde = path.join(pakettikansio(dataDir), `akveri-palvelin-${t.versio}.zip`);
  const tmp = kohde + '.uusi';
  fs.writeFileSync(tmp, buf, { mode: 0o600 });
  fs.renameSync(tmp, kohde);
  // Versiovarasto ei kasva rajatta: säilytetään 10 uusinta versiota.
  for (const vanha of listaaPaketit(dataDir).slice(10)) fs.rmSync(path.join(pakettikansio(dataDir), vanha.nimi), { force: true });
  return { versio: t.versio, tiedostoja: t.tiedostot.length, koko: buf.length };
}
function listaaPaketit(dataDir) {
  let nimet = [];
  try { nimet = fs.readdirSync(pakettikansio(dataDir)); } catch (e) { return []; }
  return nimet.map(n => /^akveri-palvelin-(\d{1,3}\.\d{1,3}\.\d{1,3})\.zip$/.exec(n)).filter(Boolean).map(m => {
    const s = fs.statSync(path.join(pakettikansio(dataDir), m[0]));
    return { versio: m[1], nimi: m[0], koko: s.size, tallennettu: s.mtime.toISOString() };
  }).sort((a, b) => vertaaVersioita(b.versio, a.versio));
}
function paketinPolku(dataDir, versio) {
  if (!SEMVER.test(String(versio))) throw new Error('Virheellinen versio.');
  const p = path.join(pakettikansio(dataDir), `akveri-palvelin-${versio}.zip`);
  if (!fs.existsSync(p)) throw new Error('Versiota ' + versio + ' ei ole tallennettu tähän työkaluun.');
  return p;
}
function poistaPaketti(dataDir, versio) { fs.rmSync(paketinPolku(dataDir, versio)); }

// ---------------------------------------------------------------- asetukset palvelimelle
function puhdasArvo(v) {
  const s = String(v == null ? '' : v);
  if (/[\r\n"'\\$`]/.test(s)) throw new Error('Asetuksessa on merkkejä, joita ei sallita.');
  return s;
}
function ymparistoTiedosto(p, a, alkutunnus) {
  const rivit = [
    ['JULKINEN_OSOITE', 'https://' + a.domain],
    ['AKVERI_ALKUTUNNUS', alkutunnus],
    ['HALLINTA_SALLITUT_IP', a.sallitutIp],
    ['GOOGLE_PLAY_PAKETTI', a.paketti],
    // @ETC@ korvataan palvelimella /etc-polulla (testeissä tilapäinen kansio)
    ['GOOGLE_PALVELUTILI', a.googleTili ? '@ETC@/akveri/google-palvelutili.json' : '']
  ];
  return rivit.filter(([, v]) => String(v) !== '').map(([k, v]) => `${k}="${puhdasArvo(v)}"`).join('\n') + '\n';
}

// Lähettää salaisuudet palvelimelle vakiosyötteenä (ei komentorivillä), tilapäiseen tiedostoon, jonka vain lähettäjä voi lukea.
async function lahetaTiedosto(vaiheet, p, nimi, sisalto) {
  const tmp = `/tmp/akveri-${crypto.randomBytes(8).toString('hex')}`;
  const summa = crypto.createHash('sha256').update(sisalto).digest('hex');
  const t = await palvelin.vaihe(vaiheet, nimi, p,
    `set -eu; umask 077; cat > ${lainaa(tmp)}; echo "SHA=$( (sha256sum ${lainaa(tmp)} 2>/dev/null || shasum -a 256 ${lainaa(tmp)}) | cut -d' ' -f1)"`,
    { eiYlennysta: true, stdin: sisalto, aikaraja: 60000 });
  if (!String(t.stdout.toString('utf8')).includes('SHA=' + summa)) throw new palvelin.VientiVirhe('Lähetetyn tiedoston tarkiste ei täsmää. Yritä uudelleen.', vaiheet);
  return tmp;
}

function asetusSkripti(p, envTmp, googleTmp) {
  return [
    'set -eu',
    'ETC="${VUORO_ETC:-/etc}"',
    `RUNUSER=${lainaa(p.ajoKayttaja)}; SVC=${lainaa(p.palvelu)}; PAIV=${lainaa(paivittaisetKansio(p))}; LAT=${lainaa(latauskansio(p))}`,
    'mkdir -p "$ETC/akveri" "$PAIV" "$LAT"',
    'chown "$RUNUSER":"$RUNUSER" "$PAIV" "$LAT" 2>/dev/null || true; chmod 750 "$PAIV" "$LAT"',
    'chown root:"$RUNUSER" "$ETC/akveri" 2>/dev/null || true; chmod 750 "$ETC/akveri"',
    `install -m 640 ${lainaa(envTmp)} "$ETC/akveri/akveri.env.uusi" && mv "$ETC/akveri/akveri.env.uusi" "$ETC/akveri/akveri.env"`,
    `rm -f ${lainaa(envTmp)}`,
    'sed -i "s|@ETC@|$ETC|g" "$ETC/akveri/akveri.env"',
    'chown root:"$RUNUSER" "$ETC/akveri/akveri.env" 2>/dev/null || true; chmod 640 "$ETC/akveri/akveri.env"',
    googleTmp ? `install -m 640 ${lainaa(googleTmp)} "$ETC/akveri/google-palvelutili.json"; rm -f ${lainaa(googleTmp)}; chown root:"$RUNUSER" "$ETC/akveri/google-palvelutili.json" 2>/dev/null || true; chmod 640 "$ETC/akveri/google-palvelutili.json"` : 'rm -f "$ETC/akveri/google-palvelutili.json"',
    // www-osoite ohjataan pääosoitteeseen (sama tapa kuin vuoropiste.fi:ssä)
    'if [ -d "$ETC/caddy/vuoro.d" ]; then',
    '  SN="$ETC/caddy/vuoro.d/$SVC-www.caddy"',
    '  printf \'www.%s {\\n\\tredir https://%s{uri} permanent\\n}\\n\' ' + lainaa(p.domain) + ' ' + lainaa(p.domain) + ' > "$SN"',
    '  chmod 644 "$SN"',
    '  if command -v caddy >/dev/null 2>&1 && ! caddy validate --config "$ETC/caddy/Caddyfile" --adapter caddyfile >/dev/null 2>&1; then rm -f "$SN"; echo "Caddyn asetukset eivät läpäisseet tarkistusta, www-ohjausta ei otettu käyttöön." >&2; exit 22; fi',
    '  systemctl reload caddy 2>/dev/null || true',
    'fi',
    'systemctl daemon-reload',
    // Käynnissä oleva palvelu lukee uudet asetukset vasta uudelleenkäynnistyksessä
    'if systemctl is-active "$SVC" >/dev/null 2>&1; then systemctl restart "$SVC" || true; fi',
    'echo "AKVERIn asetukset kirjoitettu: $ETC/akveri/akveri.env"'
  ].join('\n');
}

async function kirjoitaAsetukset(vaiheet, p, a, alkutunnus) {
  const envTmp = await lahetaTiedosto(vaiheet, p, 'Asetusten lähetys', Buffer.from(ymparistoTiedosto(p, a, alkutunnus)));
  const googleTmp = a.googleTili ? await lahetaTiedosto(vaiheet, p, 'Google Play -avaimen lähetys', Buffer.from(a.googleTili)) : '';
  await palvelin.vaihe(vaiheet, 'AKVERIn asetukset', p, asetusSkripti(p, envTmp, googleTmp), { aikaraja: 120000 });
}

// Valmistelu: käyttäjä, kansiot, Node, systemd-palvelu, Caddy-osoite ja asetukset. Turvallista ajaa uudelleen.
function valmistele(p, a, alkutunnus) {
  return palvelin.suorita(async (vaiheet) => {
    const v = await palvelin.valmistele(p, { yksikko: yksikko(p), nodeMajor: NODE_MAJOR });
    for (const x of v.vaiheet || []) vaiheet.push(x);
    if (!v.ok) throw new palvelin.VientiVirhe(v.virhe || 'Palvelimen valmistelu epäonnistui.', vaiheet);
    await kirjoitaAsetukset(vaiheet, p, a, alkutunnus);
    return { huomiot: v.huomiot || [] };
  });
}
function paivitaAsetukset(p, a, alkutunnus) {
  return palvelin.suorita(async (vaiheet) => { await kirjoitaAsetukset(vaiheet, p, a, alkutunnus); return {}; });
}

// Vienti: tallennettu paketti palvelimelle. Varmuuskopio, terveystarkistus ja automaattinen palautus (palvelinvienti.paivita).
function vie(p, dataDir, versio) {
  const t = lueJulkaisupaketti(fs.readFileSync(paketinPolku(dataDir, versio)));
  return palvelin.paivita(p, async () => ({ tiedostot: t.tiedostot }), { uusiAsennus: false, nodeMajor: Math.max(NODE_MAJOR, t.node) });
}

// Tila: palvelu, versiot, vastaako palvelu, Caddy, levytila ja lokin loppu.
function tila(p) {
  return palvelin.suorita(async (vaiheet) => {
    const t = await palvelin.vaihe(vaiheet, 'AKVERIn tila', p, [
      `APP=${lainaa(p.sovelluskansio)}; SVC=${lainaa(p.palvelu)}; PORT=${p.sovellusPortti}`,
      'ver() { [ -f "$1/package.json" ] && sed -n \'s/.*"version": *"\\([0-9.]*\\)".*/\\1/p\' "$1/package.json" | head -n1 || true; }',
      'echo "TILA=$(systemctl is-active "$SVC" 2>/dev/null || true)"',
      'echo "KAYNNISTYS=$(systemctl is-enabled "$SVC" 2>/dev/null || true)"',
      'echo "VERSIO=$(ver "$APP")"',
      'echo "EDELLINEN=$(ver "$APP.edellinen")"',
      'V=ei; if command -v curl >/dev/null 2>&1 && curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/v1/tila"; then V=kylla; fi; echo "VASTAA=$V"',
      'echo "CADDY=$(systemctl is-active caddy 2>/dev/null || true)"',
      'echo "LEVY=$(df -P / 2>/dev/null | awk \'NR==2{print $5}\')"',
      'echo "---"',
      'journalctl -u "$SVC" -n 40 --no-pager -o short-iso 2>/dev/null || true'
    ].join('\n'), { aikaraja: 60000 });
    const teksti = t.stdout.toString('utf8');
    const arvo = (k) => ((teksti.match(new RegExp('^' + k + '=(.*)$', 'm')) || [])[1] || '').trim();
    return { tila: arvo('TILA'), kaynnistyyKoneenMukana: arvo('KAYNNISTYS') === 'enabled', versio: arvo('VERSIO'), edellinen: arvo('EDELLINEN'),
      vastaa: arvo('VASTAA') === 'kylla', caddy: arvo('CADDY'), levy: arvo('LEVY'), loki: teksti.split('---\n').slice(1).join('---\n') };
  });
}

// Palauttaa edellisen version (kansio /opt/akveri.edellinen). Nykyinen versio jää tilalle edelliseksi, joten palautuksen voi perua.
function palautaEdellinen(p) {
  return palvelin.suorita(async (vaiheet) => {
    await palvelin.vaihe(vaiheet, 'Edellisen version palautus', p, [
      'set -u',
      `APP=${lainaa(p.sovelluskansio)}; SVC=${lainaa(p.palvelu)}; PORT=${p.sovellusPortti}`,
      '[ -f "$APP.edellinen/server.js" ] || { echo "Palvelimella ei ole edellistä versiota." >&2; exit 50; }',
      'rm -rf "$APP.vaihto"',
      'systemctl stop "$SVC" 2>/dev/null || true',
      'mv "$APP" "$APP.vaihto" && mv "$APP.edellinen" "$APP" && mv "$APP.vaihto" "$APP.edellinen"',
      'systemctl start "$SVC" || true',
      'OK=0; for I in $(seq 1 30); do if command -v curl >/dev/null 2>&1; then curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/v1/tila" && OK=1; else sleep 3; systemctl is-active "$SVC" >/dev/null 2>&1 && OK=1; fi; [ "$OK" = 1 ] && break; sleep 1; done',
      'if [ "$OK" != 1 ]; then',
      '  echo "Palautettu versio ei käynnistynyt, otetaan uudempi versio takaisin käyttöön." >&2',
      '  systemctl stop "$SVC" 2>/dev/null || true',
      '  mv "$APP" "$APP.vaihto" && mv "$APP.edellinen" "$APP" && mv "$APP.vaihto" "$APP.edellinen"',
      '  systemctl start "$SVC" || true; exit 41',
      'fi',
      'echo "Edellinen versio on käytössä ja vastaa."'
    ].join('\n'), { aikaraja: 5 * 60 * 1000 });
    return {};
  });
}

// Omat lataukset (esim. Windows-versio): vain omistajan ladattavissa hallinnasta kirjautuneena.
function tarkistaLatausnimi(nimi) {
  const n = String(nimi || '');
  if (!LATAUS_NIMI.test(n)) throw new Error('Tiedostonimi ei kelpaa. Sallitut päätteet: .exe, .msi, .zip, .apk ja .aab. Nimessä saa olla kirjaimia, numeroita, piste, viiva ja alaviiva.');
  return n;
}
function vieLataus(p, nimi, tiedostoPolku) {
  const n = tarkistaLatausnimi(nimi);
  return palvelin.suorita(async (vaiheet) => {
    const koko = fs.statSync(tiedostoPolku).size;
    if (koko > LATAUS_MAX) throw new palvelin.VientiVirhe('Tiedosto on liian suuri (enintään 600 Mt).', vaiheet);
    const summa = await new Promise((ok, ei) => { const h = crypto.createHash('sha256'); fs.createReadStream(tiedostoPolku).on('data', d => h.update(d)).on('end', () => ok(h.digest('hex'))).on('error', ei); });
    const tmp = `/tmp/akveri-lataus-${crypto.randomBytes(8).toString('hex')}`;
    const t = await palvelin.vaihe(vaiheet, 'Tiedoston lähetys', p,
      `set -eu; umask 077; cat > ${lainaa(tmp)}; echo "SHA=$( (sha256sum ${lainaa(tmp)} 2>/dev/null || shasum -a 256 ${lainaa(tmp)}) | cut -d' ' -f1)"`,
      { eiYlennysta: true, stdin: { tiedosto: tiedostoPolku }, aikaraja: 60 * 60 * 1000 });
    if (!String(t.stdout.toString('utf8')).includes('SHA=' + summa)) {
      try { await palvelin.vaihe([], 'Siivous', p, `rm -f ${lainaa(tmp)}`, { eiYlennysta: true, aikaraja: 30000 }); } catch (e) { /* tilapäiskansio tyhjenee viimeistään uudelleenkäynnistyksessä */ }
      throw new palvelin.VientiVirhe('Lähetetyn tiedoston tarkiste ei täsmää. Yritä uudelleen.', vaiheet);
    }
    await palvelin.vaihe(vaiheet, 'Tiedoston asennus', p, [
      'set -eu',
      `LAT=${lainaa(latauskansio(p))}; RUNUSER=${lainaa(p.ajoKayttaja)}`,
      '[ -d "$LAT" ] || { echo "Latauskansiota ei ole. Aja ensin AKVERIn julkaisu." >&2; exit 50; }',
      `install -m 640 ${lainaa(tmp)} "$LAT/${n}.uusi" && rm -f ${lainaa(tmp)}`,
      `chown "$RUNUSER":"$RUNUSER" "$LAT/${n}.uusi" 2>/dev/null || true`,
      `mv "$LAT/${n}.uusi" "$LAT/${n}"`,
      `echo "Tallennettu: ${n}"`
    ].join('\n'), { aikaraja: 120000 });
    return { nimi: n, koko, sha256: summa };
  });
}
function listaaLataukset(p) {
  return palvelin.suorita(async (vaiheet) => {
    const t = await palvelin.vaihe(vaiheet, 'Omat lataukset', p,
      `LAT=${lainaa(latauskansio(p))}; [ -d "$LAT" ] || exit 0; for f in "$LAT"/*; do [ -f "$f" ] || continue; echo "$(basename "$f")|$(wc -c < "$f" | tr -d ' ')"; done; echo`, { aikaraja: 60000 });
    return { lataukset: t.stdout.toString('utf8').split('\n').filter(r => r.includes('|')).map(r => { const [nimi, koko] = r.split('|'); return { nimi, koko: Number(koko) }; }).filter(x => LATAUS_NIMI.test(x.nimi)) };
  });
}
function poistaLataus(p, nimi) {
  const n = tarkistaLatausnimi(nimi);
  return palvelin.suorita(async (vaiheet) => {
    await palvelin.vaihe(vaiheet, 'Tiedoston poisto', p, `set -eu; rm -f ${lainaa(latauskansio(p) + '/' + n)}; echo "Poistettu: ${n}"`, { aikaraja: 60000 });
    return {};
  });
}

// DNS: akveri.fi ja www.akveri.fi osoittavat palvelimelle?
async function haeOsoitteet(nimi) { try { return (await dns.lookup(nimi, { all: true })).map(x => x.address).sort(); } catch (e) { return []; } }
async function dnsTila(host, domain, tarkistaOsoite = haeOsoitteet) {
  const palvelinOsoitteet = await tarkistaOsoite(host);
  const tulokset = [];
  for (const t of [{ nimi: domain, selite: 'Sivusto, tarkistus ja sovelluksen rajapinta' }, { nimi: 'www.' + domain, selite: 'www-osoite (ohjataan pääosoitteeseen)' }]) {
    const osoitteet = await tarkistaOsoite(t.nimi);
    tulokset.push({ nimi: t.nimi, tyyppi: 'A', selite: t.selite, arvo: palvelinOsoitteet[0] || '(palvelimen IP-osoite)', ok: palvelinOsoitteet.length > 0 && osoitteet.some(a => palvelinOsoitteet.includes(a)), nykyinen: osoitteet });
  }
  return { palvelin: palvelinOsoitteet, tietueet: tulokset, ok: tulokset.every(t => t.ok) };
}

// Hallinnan (akveri.fi/hallinta) käyttäjät: kutsu, poisto ja luettelo palvelimen ylläpitokomennolla (yllapito.js).
function kayttajat(p, a, toiminto, { sahkoposti = '', nimi = '' } = {}) {
  const posti = String(sahkoposti).trim().toLowerCase();
  const n = String(nimi).trim().replace(/\s+/g, ' ');
  if (toiminto !== 'lista' && !/^[a-z0-9._%+-]{1,64}@[a-z0-9.-]{1,200}\.[a-z]{2,24}$/.test(posti)) return Promise.resolve({ ok: false, virhe: 'Sähköpostiosoite ei kelpaa.', vaiheet: [] });
  if (toiminto === 'lisaa' && !/^[A-Za-zÅÄÖåäöÉéÜü0-9 .'-]{2,80}$/.test(n)) return Promise.resolve({ ok: false, virhe: 'Nimessä saa olla kirjaimia, numeroita, välilyöntejä sekä merkit . - \' (2–80 merkkiä).', vaiheet: [] });
  const komento = toiminto === 'lisaa' ? `lisaa-kayttaja ${lainaa(posti)} ${lainaa(n)}` : toiminto === 'poista' ? `poista-kayttaja ${lainaa(posti)}` : 'lista-kayttajat';
  return palvelin.suorita(async (vaiheet) => {
    const t = await palvelin.vaihe(vaiheet, toiminto === 'lisaa' ? 'Käyttäjän kutsu' : toiminto === 'poista' ? 'Käyttäjän poisto' : 'Hallinnan käyttäjät', p, [
      'set -eu',
      `APP=${lainaa(p.sovelluskansio)}; DB=${lainaa(p.dbKansio)}; RUNUSER=${lainaa(p.ajoKayttaja)}`,
      '[ -f "$APP/yllapito.js" ] || { echo "AKVERIa ei ole vielä viety palvelimelle (tai versio on vanha). Julkaise tai päivitä AKVERI ensin." >&2; exit 50; }',
      'NODEBIN=$(command -v node)', 'cd "$APP"',
      `runuser -u "$RUNUSER" -- env DB_DIR="$DB" JULKINEN_OSOITE=${lainaa('https://' + a.domain)} "$NODEBIN" yllapito.js ${komento}`
    ].join('\n'), { aikaraja: 60000 });
    const ulos = t.stdout.toString('utf8').trim();
    if (toiminto === 'lisaa') return { linkki: (ulos.match(/^KUTSU=(https:\/\/\S+)$/m) || [])[1] || '' };
    if (toiminto === 'poista') return { viesti: ulos.split('\n').pop() };
    try { return JSON.parse(ulos.split('\n').pop()); } catch (e) { throw new palvelin.VientiVirhe('Käyttäjäluettelo ei ole odotetussa muodossa.', vaiheet); }
  });
}

module.exports = {
  kayttajat, PALVELU, KAYTTAJA, KANSIOT, profiili, yksikko, lueJulkaisupaketti, tallennaPaketti, listaaPaketit, paketinPolku, poistaPaketti,
  ymparistoTiedosto, asetusSkripti, valmistele, paivitaAsetukset, vie, tila, palautaEdellinen, vieLataus, listaaLataukset, poistaLataus,
  tarkistaLatausnimi, dnsTila, latauskansio, paivittaisetKansio, PAKETTI_MAX, LATAUS_MAX
};
