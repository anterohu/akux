// google.js — Google Play -ostojen tarkistus palvelimella (Google Play Developer API, androidpublisher v3).
//
// Sovellus ei koskaan itse päätä, että osto on maksettu: se lähettää Google Playn antaman ostotunnuksen
// palvelimelle, ja palvelin kysyy Googlelta, onko osto todella maksettu, mikä tuote se on ja kenen tilille se
// tehtiin. Vasta sitten krediitit lisätään. Palvelutilin avain (JSON) on vain palvelimella (ks. README).
//
// Kirjautuminen: palvelutilin avaimella allekirjoitettu JWT vaihdetaan OAuth-tunnukseen (RS256), ilman kirjastoja.
'use strict';
const crypto = require('crypto');
const fs = require('fs');

const LAAJUUS = 'https://www.googleapis.com/auth/androidpublisher';
const RAJAPINTA = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications/';

function b64url(x) { return Buffer.from(typeof x === 'string' ? x : JSON.stringify(x)).toString('base64url'); }

class GooglePlay {
  // asetukset: { paketti, palvelutili (JSON-olio) | palvelutiliTiedosto }, haku: fetch-yhteensopiva funktio (testeissä korvataan)
  constructor({ paketti, palvelutili, palvelutiliTiedosto, haku = globalThis.fetch, nyt = () => Date.now() } = {}) {
    this.paketti = String(paketti || '');
    this.haku = haku;
    this.nyt = nyt;
    this.tunnus = null;
    this.virhe = '';
    try {
      this.tili = palvelutili || (palvelutiliTiedosto && fs.existsSync(palvelutiliTiedosto) ? JSON.parse(fs.readFileSync(palvelutiliTiedosto, 'utf8')) : null);
    } catch (e) { this.tili = null; this.virhe = 'Palvelutilin avaintiedosto ei ole kelvollista JSONia.'; }
    if (this.tili && (!this.tili.client_email || !this.tili.private_key)) { this.tili = null; this.virhe = 'Palvelutilin avaimesta puuttuu client_email tai private_key.'; }
  }
  get kaytossa() { return !!(this.tili && /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/.test(this.paketti)); }

  async _oauth() {
    if (this.tunnus && this.tunnus.vanhenee - 60000 > this.nyt()) return this.tunnus.arvo;
    const iat = Math.floor(this.nyt() / 1000);
    const otsikko = b64url({ alg: 'RS256', typ: 'JWT' });
    const sisalto = b64url({ iss: this.tili.client_email, scope: LAAJUUS, aud: this.tili.token_uri || 'https://oauth2.googleapis.com/token', iat, exp: iat + 3600 });
    const allekirjoitus = crypto.createSign('RSA-SHA256').update(otsikko + '.' + sisalto).sign(this.tili.private_key).toString('base64url');
    const r = await this.haku(this.tili.token_uri || 'https://oauth2.googleapis.com/token', {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion: `${otsikko}.${sisalto}.${allekirjoitus}` }).toString(),
      signal: AbortSignal.timeout(15000)
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.access_token) throw new Error('Google Play -kirjautuminen epäonnistui' + (d.error ? ` (${d.error})` : '') + '. Tarkista palvelutilin oikeudet Play Consolessa.');
    this.tunnus = { arvo: d.access_token, vanhenee: this.nyt() + (Number(d.expires_in) || 3600) * 1000 };
    return this.tunnus.arvo;
  }

  async _get(polku) {
    const r = await this.haku(RAJAPINTA + encodeURIComponent(this.paketti) + polku, { headers: { Authorization: 'Bearer ' + await this._oauth() }, signal: AbortSignal.timeout(15000) });
    const d = await r.json().catch(() => ({}));
    return { status: r.status, d };
  }

  // Palauttaa { tila: 'maksettu' | 'odottaa' | 'peruttu' | 'tuntematon', tilaus, tili, testiosto, aika }.
  async tarkistaOsto(tuote, ostotunnus) {
    if (!this.kaytossa) throw new Error('Ostojen tarkistus ei ole käytössä: Google Play -palvelutili tai sovelluksen paketti puuttuu.');
    const { status, d } = await this._get('/purchases/products/' + encodeURIComponent(tuote) + '/tokens/' + encodeURIComponent(ostotunnus));
    if (status === 404 || status === 410 || status === 400) return { tila: 'tuntematon' };
    if (status !== 200) throw new Error(`Google Play ei vastannut odotetusti (${status}). Yritä myöhemmin uudelleen.`);
    const tila = d.purchaseState === 0 ? 'maksettu' : d.purchaseState === 2 ? 'odottaa' : 'peruttu';
    return { tila, tilaus: d.orderId || '', tili: d.obfuscatedExternalAccountId || '', testiosto: d.purchaseType === 0, aika: Number(d.purchaseTimeMillis) || null, kulutettu: d.consumptionState === 1 };
  }

  // Google Playssa perutut tai hyvitetyt ostot annetusta hetkestä alkaen: [{ ostotunnus, tilaus, aika }]
  async perututOstot(alkaen) {
    if (!this.kaytossa) return [];
    const ulos = [];
    let sivu = '';
    for (let i = 0; i < 20; i++) {
      const { status, d } = await this._get('/purchases/voidedpurchases?type=0&startTime=' + Math.floor(alkaen) + (sivu ? '&token=' + encodeURIComponent(sivu) : ''));
      if (status !== 200) throw new Error(`Perumisten haku epäonnistui (${status}).`);
      for (const v of d.voidedPurchases || []) ulos.push({ ostotunnus: v.purchaseToken, tilaus: v.orderId || '', aika: Number(v.voidedTimeMillis) || null });
      sivu = d.tokenPagination && d.tokenPagination.nextPageToken;
      if (!sivu) break;
    }
    return ulos;
  }
}

module.exports = { GooglePlay };
