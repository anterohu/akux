# AKVERI-palvelin (akveri.fi)

Palvelin hoitaa neljä asiaa:

1. **Esittelysivusto** – etusivu, hinnat, käyttöehdot, tietosuojaseloste ja yhteystiedot. Asennustiedostoja ei jaeta sivustolla: sovellus ladataan vain Google Playsta.
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

## Tiedot palvelimella

| Polku | Sisältö |
|---|---|
| `/opt/akveri` | Ohjelma (vaihdetaan päivityksessä, edellinen versio jää kansioon `/opt/akveri.edellinen`) |
| `/var/lib/akveri` | Tiedot: tilit, testit, ostot, viestit, asetukset, kirjanpito, allekirjoitusavain, päivittäiset varmuuskopiot (`varmuuskopiot/`) ja omat lataukset (`lataukset/`) |
| `/var/lib/akveri-varmuuskopiot` | Hallintatyökalun ottamat varmuuskopiot (ennen jokaista päivitystä) |
| `/etc/akveri/akveri.env` | Asetukset (vain root ja `akveri`-käyttäjä) |
| `/etc/akveri/google-palvelutili.json` | Google Play -palvelutilin avain |

Palvelu ajetaan omalla järjestelmäkäyttäjällä `akveri` (ei kirjautumista). Vuoropisteen palvelut ja tiedot eivät näy sille, eikä AKVERI näy niille.

## Google Play -ostojen tarkistus

1. Play Consolessa: luo kertakäyttöiset tuotteet (esim. `akveri_testi_1`, `akveri_testi_5`, `akveri_testi_20`) ja aseta hinnat.
2. Google Cloudissa: luo palvelutili ja sille JSON-avain. Play Consolessa: Käyttäjät ja oikeudet → kutsu palvelutilin sähköpostiosoite ja anna oikeus "Talous- ja tilaustietojen tarkastelu" sekä "Tilausten ja tilausten hallinta".
3. Hallintatyökalun AKVERI-välilehdellä: lisää sovelluksen paketti (`fi.akux.app`) ja palvelutilin avaintiedosto, ja paina Julkaise.
4. akveri.fi/hallinta → Sivusto ja ehdot: tarkista, että tuotetunnukset ja krediittimäärät vastaavat Play Consolea.

## Ympäristömuuttujat

Katso `server.js`:n alku. Hallintatyökalu kirjoittaa ne tiedostoon `/etc/akveri/akveri.env`.

## Kehitys

```
node palvelin/server.js                 # http://127.0.0.1:3200
node --test palvelin/testit/*.test.js   # testit
node palvelin/kokoa.js                  # julkaisupaketti palvelin/dist/akveri-palvelin-<versio>.zip
```

Palvelimen versio (`package.json`) on aina sama kuin sovelluksen versio (`akux/__init__.py`). `kokoa.js` ei tee pakettia, jos ne eroavat.
