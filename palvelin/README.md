# AKVERI-palvelin (akveri.fi)

Palvelin hoitaa neljä asiaa:

1. **Esittelysivusto** – etusivu, hinnat, käyttöehdot, tietosuojaseloste ja yhteystiedot. Asennustiedostoja ei jaeta sivustolla: sovellus ladataan vain Google Playsta.
   Sivut ovat suomeksi, englanniksi (/en) ja ruotsiksi (/sv). Etusivun tekstit ovat tiedostossa `etusivu.js` ja muiden sivujen tekstit tiedostossa `sivut.js`; muutoksen jälkeen aja `node etusivu.js` ja `node sivut.js`. Hallinnassa muokattu käyttöehtojen tai tietosuojaselosteen teksti näkyy suomenkielisellä sivulla; englannin- ja ruotsinkieliset versiot päivitetään `sivut.js`-tiedostoon.
2. **Raportin tarkistus** – `akveri.fi/v/<tunnus>`. Raportin QR-koodi avaa tämän sivun. Sivulla näkyvät palvelimelle rekisteröidyt tiedot, ja ostaja voi verrata auton valmistenumeroa.
3. **Krediittirajapinta sovellukselle** (`/api/v1/...`) – tilit, Google Play -ostojen tarkistus, testiluvat ja raporttien rekisteröinti.
4. **Omistajan hallinta** – `akveri.fi/hallinta`, salasana ja kaksivaiheinen tunnistus. Ei linkkiä julkisilta sivuilta.

Ei ulkoisia riippuvuuksia. Vaatii Node 22:n.

## Krediittien logiikka

- Yksi krediitti = yksi mittaus ja sen raportti. Uudella tilillä ei ole krediittejä.
- Krediitit ostetaan sovelluksessa Google Playn kautta. Palvelin tarkistaa jokaisen oston Googlelta ennen kuin krediitit lisätään. Sama osto hyvittyy vain kerran ja vain sille tilille, jolle se tehtiin.
- Mittauksen alussa sovellus varaa testiluvan: krediitti veloitetaan ja testi saa tunnuksen (esim. `AK-7H2QK-M4XPC`). Ilman lupaa sovellus ei aloita mittausta oikeasta autosta.
- Mittauksen lopuksi sovellus rekisteröi raportin yhteenvedon. Vain rekisteröity raportti näkyy tarkistussivulla kelvollisena. Yksi lupa kelpaa yhteen mittaukseen (raakadatan tarkiste sidotaan lupaan).
- Jos mittaus keskeytyy perumisajan sisällä (oletus 60 min), sovellus perii luvan ja krediitti palautuu. Myöhemmin keskeytyneestä mittauksesta sovellus lähettää hyvityspyynnön, jonka käsittelet hallinnassa (Testit ja hyvitykset).
- Peruttu tai mitätöity lupa näkyy tarkistussivulla, joten sillä tehty raportti ei kelpaa.
- Google Playssa perutut tai hyvitetyt ostot tarkistetaan kahdesti vuorokaudessa, ja vastaavat krediitit vähennetään.
- Omat krediittisi (esim. Windows-versiota varten) lisäät hallinnassa omalle tilillesi. Ohjelmassa ei ole ohitusta, joka toimisi ilman krediittejä.

Kirjanpito (`kirjanpito.jsonl`) on vain lisäyksiä sisältävä tiedosto, jonka jokainen rivi on ketjutettu edelliseen tiivisteellä. Hallinta varoittaa, jos tiedostoa on muutettu palvelimen ulkopuolelta.

## Hallinnan käyttäjät

Ensimmäinen käyttäjä luodaan alkutunnuksella, jonka Hallintatyökalu näyttää AKVERI-näkymässä. Muut käyttäjät lisätään ja poistetaan Hallintatyökalun AKVERI-näkymästä: palvelimella ajetaan `yllapito.js`, joka luo kertakäyttöisen kutsulinkin (24 h). Kirjautuminen: sähköposti, salasana ja kaksivaiheisen tunnistuksen koodi. Poisto katkaisee kirjautumisen heti.

## Tietosuoja ja säilytysajat

- Tilin tietojen poisto pyynnöstä: hallinta → Tilit ja krediitit → tili → Tilin tietojen poisto. Kirjanpito ja ostot säilyvät kirjanpitolain ajan (niissä on vain satunnainen tilitunnus).
- Raportin tietojen poisto: Testit ja hyvitykset → Poista tiedot. Tarkistussivu kertoo, että tiedot on poistettu.
- Automaattisesti kerran vuorokaudessa: yhteydenotot poistetaan 2 vuoden, hyvityspyyntöjen tekstit 2 vuoden ja raporttien tiedot 10 vuoden jälkeen.
- Palvelimelle ei kerry turhaa dataa: päivittäisiä varmuuskopioita säilytetään 30, palvelimella on vain nykyinen ja edellinen versio, ja Hallintatyökalun versiovarastossa 10 uusinta pakettia.

## Tiedot palvelimella

| Polku | Sisältö |
|---|---|
| `/opt/akveri` | Ohjelma (vaihdetaan päivityksessä, edellinen versio jää kansioon `/opt/akveri.edellinen`) |
| `/var/lib/akveri` | Tiedot: tilit, testit, ostot, viestit, asetukset, kirjanpito ja allekirjoitusavain |
| `/var/lib/akveri-paivittaiset` | Palvelimen omat päivittäiset varmuuskopiot (30 uusinta) |
| `/var/lib/akveri-lataukset` | Omat lataukset (esim. Windows-versio), vain hallinnasta kirjautuneena |
| `/var/lib/akveri-varmuuskopiot` | Hallintatyökalun ottamat varmuuskopiot (ennen jokaista päivitystä) |
| `/etc/akveri/akveri.env` | Asetukset (vain root ja `akveri`-käyttäjä) |
| `/etc/akveri/google-palvelutili.json` | Google Play -palvelutilin avain |

Palvelu ajetaan omalla järjestelmäkäyttäjällä `akveri` (ei kirjautumista). Vuoropisteen palvelut ja tiedot eivät näy sille, eikä AKVERI näy niille.

## Google Play -ostojen tarkistus

1. Play Consolessa: luo kertakäyttöiset tuotteet, joiden tunnukset ovat valmiina palvelimen oletuksissa: `akveri_krediitit_1` (1 krediitti), `akveri_krediitit_3`, `akveri_krediitit_10` ja `akveri_krediitit_30`. Aseta hinnat, esimerkiksi 9,90 €, 24,90 €, 69 € ja 179 €.
2. Google Cloudissa: luo palvelutili ja sille JSON-avain. Play Consolessa: Käyttäjät ja oikeudet → kutsu palvelutilin sähköpostiosoite ja anna oikeus "Talous- ja tilaustietojen tarkastelu" sekä "Tilausten ja tilausten hallinta".
3. Hallintatyökalun AKVERI-välilehdellä: lisää sovelluksen paketti (`fi.akveri.app`) ja palvelutilin avaintiedosto, ja paina Julkaise.
4. akveri.fi/hallinta → Sivusto ja ehdot: tarkista, että tuotetunnukset ja krediittimäärät vastaavat Play Consolea.

## Ympäristömuuttujat

Katso `server.js`:n alku. Hallintatyökalu kirjoittaa ne tiedostoon `/etc/akveri/akveri.env`.

## Kehitys

```
node palvelin/server.js                 # http://127.0.0.1:3200
node --test palvelin/testit/*.test.js   # testit
node palvelin/kokoa.js                  # palvelinpaketti palvelin/dist/akveri-palvelin-<versio>.zip
node palvelin/kokoa-oksa.js             # Hallintatyökalun paketti palvelin/dist/akveri-<versio>.zip (palvelinpaketti mukana)
```

Palvelimen versio (`package.json`) on aina sama kuin sovelluksen versio (`akveri/__init__.py`). `kokoa.js` ei tee pakettia, jos ne eroavat.
