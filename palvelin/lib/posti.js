// posti.js — sähköpostin lähetys SMTP:llä ilman ulkoisia riippuvuuksia (Node 22: net ja tls).
//
// Tuetaan tavallisimmat palvelut: portti 465 (salattu heti alusta) tai 587 (STARTTLS, pakollinen) ja kirjautuminen
// AUTH PLAIN tai AUTH LOGIN. Salaamatonta yhteyttä ei käytetä, paitsi paikalliseen osoitteeseen (127.0.0.1, testit).
// Otsakkeisiin ei päästetä rivinvaihtoja (otsakeinjektio), ja otsikko koodataan RFC 2047 -muotoon.
'use strict';
const net = require('net');
const tls = require('tls');
const crypto = require('crypto');

const AIKARAJA_MS = 20000;
const RIVINVAIHTO = /[\r\n]/;

function osoiteOsasta(s) {
  const m = /<([^<>\s]+@[^<>\s]+)>/.exec(String(s || ''));
  if (m) return m[1];
  const t = String(s || '').trim();
  return /^[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+$/.test(t) ? t : '';
}
const koodaa = (t) => /^[\x20-\x7e]*$/.test(t) ? t : '=?UTF-8?B?' + Buffer.from(t, 'utf8').toString('base64') + '?=';
function osoiteOtsake(s) {
  const osoite = osoiteOsasta(s);
  const m = /^\s*"?([^"<]*?)"?\s*<[^<>]+>\s*$/.exec(String(s || ''));
  return m && m[1] ? `${koodaa(m[1].trim())} <${osoite}>` : osoite;
}

function rakennaViesti({ from, to, replyTo, subject, text, nyt = new Date() }) {
  for (const k of [from, to, replyTo, subject]) if (k && RIVINVAIHTO.test(k)) throw new Error('Otsakkeessa ei saa olla rivinvaihtoa.');
  const domain = osoiteOsasta(from).split('@')[1] || 'localhost';
  const rungot = Buffer.from(String(text || '').replace(/\r?\n/g, '\r\n'), 'utf8').toString('base64').replace(/.{76}/g, '$&\r\n');
  const otsakkeet = [
    `From: ${osoiteOtsake(from)}`, `To: ${osoiteOtsake(to)}`, ...(replyTo ? [`Reply-To: ${osoiteOtsake(replyTo)}`] : []),
    `Subject: ${koodaa(String(subject || ''))}`, `Date: ${nyt.toUTCString().replace('GMT', '+0000')}`,
    `Message-ID: <${crypto.randomBytes(12).toString('hex')}@${domain}>`, 'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=utf-8', 'Content-Transfer-Encoding: base64'
  ];
  return otsakkeet.join('\r\n') + '\r\n\r\n' + rungot + '\r\n';
}

// Lähettää yhden viestin. asetus: { host, port, secure, user, pass }.
function laheta(asetus, viesti) {
  const lahettaja = osoiteOsasta(viesti.from), vastaanottaja = osoiteOsasta(viesti.to);
  if (!lahettaja || !vastaanottaja) return Promise.reject(new Error('Lähettäjän tai vastaanottajan osoite puuttuu.'));
  const data = rakennaViesti(viesti);
  const paikallinen = asetus.host === '127.0.0.1' || asetus.host === 'localhost';
  return new Promise((ok, virhe) => {
    let soketti = asetus.secure ? tls.connect({ host: asetus.host, port: asetus.port, servername: asetus.host }) : net.connect({ host: asetus.host, port: asetus.port });
    let puskuri = '', odottaja = null, valmis = false;
    const lopeta = (e) => { if (valmis) return; valmis = true; clearTimeout(ajastin); try { soketti.destroy(); } catch (x) { /* */ } e ? virhe(e) : ok(); };
    const ajastin = setTimeout(() => lopeta(new Error('Sähköpostipalvelin ei vastannut ajoissa.')), asetus.aikaraja || AIKARAJA_MS);
    const kuuntele = (s) => {
      s.setEncoding('utf8');
      s.on('data', (d) => {
        puskuri += d;
        // Vastaus on valmis, kun viimeinen rivi on muotoa "123 teksti".
        const rivit = puskuri.split('\r\n'); if (rivit[rivit.length - 1] !== '') return;
        const viimeinen = rivit[rivit.length - 2] || '';
        if (!/^\d{3} /.test(viimeinen) && !/^\d{3}$/.test(viimeinen)) return;
        const vastaus = puskuri; puskuri = '';
        if (odottaja) { const o = odottaja; odottaja = null; o(vastaus); }
      });
      s.on('error', (e) => lopeta(new Error('Yhteys sähköpostipalvelimeen epäonnistui: ' + e.message)));
      s.on('close', () => lopeta(new Error('Sähköpostipalvelin katkaisi yhteyden.')));
    };
    const odota = () => new Promise((r) => { odottaja = r; });
    const komento = async (rivi, odotettu) => {
      if (rivi !== null) soketti.write(rivi + '\r\n');
      const v = await odota();
      if (!new RegExp('^' + odotettu).test(v)) throw new Error('Sähköpostipalvelin hylkäsi: ' + v.trim().split('\r\n').pop().slice(0, 200));
      return v;
    };
    kuuntele(soketti);
    (async () => {
      await komento(null, '220');
      let ehlo = await komento('EHLO akveri', '250');
      if (!asetus.secure) {
        if (/STARTTLS/i.test(ehlo)) {
          await komento('STARTTLS', '220');
          soketti.removeAllListeners('data'); soketti.removeAllListeners('close'); soketti.removeAllListeners('error');
          soketti = tls.connect({ socket: soketti, servername: asetus.host, rejectUnauthorized: !paikallinen });
          kuuntele(soketti);
          await new Promise((r, e) => { soketti.once('secureConnect', r); soketti.once('error', e); });
          ehlo = await komento('EHLO akveri', '250');
        } else if (!paikallinen) throw new Error('Sähköpostipalvelin ei tue salattua yhteyttä (STARTTLS). Käytä porttia 465 tai 587.');
      }
      if (asetus.user) {
        if (/AUTH[^\r\n]*PLAIN/i.test(ehlo)) await komento('AUTH PLAIN ' + Buffer.from(`\0${asetus.user}\0${asetus.pass || ''}`).toString('base64'), '235');
        else { await komento('AUTH LOGIN', '334'); await komento(Buffer.from(asetus.user).toString('base64'), '334'); await komento(Buffer.from(asetus.pass || '').toString('base64'), '235'); }
      }
      await komento(`MAIL FROM:<${lahettaja}>`, '250');
      await komento(`RCPT TO:<${vastaanottaja}>`, '25');
      await komento('DATA', '354');
      await komento(data.replace(/^\./gm, '..') + '.', '250');
      soketti.write('QUIT\r\n');
      lopeta();
    })().catch(lopeta);
  });
}


// Hallinnan sähköpostiasetus (asetukset.posti): ilmoitukset vastaanottajalle ilmoitusten lähettäjältä (noreply, vastausosoitteena
// omien viestien osoite) ja omat viestit omien viestien lähettäjältä (info). Lähetys ei koskaan kaada pyyntöä.
function luoPostitus(varasto, { lahetin = laheta } = {}) {
  const asetus = () => (varasto.get('asetukset').posti || null);
  const kaytossa = () => { const a = asetus(); return !!(a && a.host && a.lahettaja); };
  async function ilmoita(otsikko, teksti) {
    const a = asetus();
    if (!kaytossa() || !a.vastaanottaja) return false;
    const info = osoiteOsasta(a.lahettajaOmat);
    await lahetin(a, { from: a.lahettaja, to: a.vastaanottaja, ...(info ? { replyTo: info } : {}), subject: otsikko, text: teksti });
    return true;
  }
  async function omaViesti(vastaanottaja, otsikko, teksti) {
    const a = asetus();
    if (!kaytossa()) throw new Error('Sähköpostia ei ole asetettu (Sivusto ja ehdot → Sähköposti).');
    await lahetin(a, { from: a.lahettajaOmat || a.lahettaja, to: vastaanottaja, subject: otsikko, text: teksti });
  }
  const ilmoitaTaustalla = (otsikko, teksti) => { ilmoita(otsikko, teksti).catch(e => console.error('[posti] ilmoitus epäonnistui:', e.message)); };
  return { kaytossa, ilmoita, ilmoitaTaustalla, omaViesti, infoOsoite: () => osoiteOsasta((asetus() || {}).lahettajaOmat) };
}

module.exports = { laheta, rakennaViesti, osoiteOsasta, luoPostitus };
