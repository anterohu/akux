# Akux 1.2

Akux mittaa Tesla Model 3:n ja Model Y:n ajoakun kunnon ja kapasiteetin OBDLink-sovittimella ja tekee tuloksista selkeän ja yksityiskohtaisen PDF-raportin ostajalle, asiakkaalle tai omaan käyttöön.

## Asennus

Valmiit ohjelmat ovat GitHubin **Releases**-sivulla: https://github.com/anterohu/akux/releases/latest

**Windows:** lataa `Akux-asennus-x.y.z.exe` ja aja se. Asennus lisää pikakuvakkeen työpöydälle ja Käynnistä-valikkoon. Jos Windows näyttää ilmoituksen *Windows suojasi tietokonettasi*, valitse **Lisätietoja → Suorita silti**. Ilmoitus tulee vain asennusohjelmasta kerran jokaista uutta versiota kohden, ei itse ohjelmasta.

**Android (10 tai uudempi):** lataa `Akux-x.y.z.apk` puhelimeen ja avaa se. Android kysyy kerran luvan asentaa sovelluksia tästä lähteestä. Kytke OBDLink EX välikaapelilla auton diagnostiikkaliittimeen ja USB-C-sovittimella (OTG) puhelimeen ja salli Akuxille pääsy sovittimeen. Diagnostiikkaliitin on keskikonsolin takapäässä: vuosien 2019–2020 autoissa 20-pinninen ja 2021 alkaen 26-pinninen. Jalkatilan OBD-liitäntä ei välitä akun tietoja.

**Päivitys:** lataa uusi versio samasta paikasta ja asenna se vanhan päälle. Autot, mittaukset, raportit ja asetukset säilyvät. Mitään tiedostoja ei tarvitse poistaa, siirtää eikä nimetä uudelleen.

**Vaihtoehto Windowsissa, rakennus omalla koneella:** lataa Releases-sivulta lähdekoodi (zip), pura se ja aja `Asenna.bat`. Tällöin Akux rakennetaan omalla koneellasi, eikä SmartScreen kysy mitään. Molemmat tavat asentavat ohjelman samaan paikkaan ja käyttävät samoja tietoja.

## Mittaustiedostot

Jokainen valmis mittaus tallennetaan automaattisesti mittaustiedostona (`.akux`) ja PDF-raporttina:

- Windows: `Tiedostot\Akux\Mittaukset` (kansion voi vaihtaa asetuksista, esimerkiksi OneDriveen)
- Android: `Lataukset/Akux`

Mittaustiedosto sisältää kaiken: auton tiedot, mittausnäytteet, kennoryhmien jännitteet, tapahtumat, tuloksen, muuttamattoman raakadatan ja raportin. Sen voi avata missä tahansa Akux-versiossa ja millä tahansa laitteella kohdasta **Mittaukset → Avaa mittaustiedosto**. Ohjelma tarkistaa avattaessa, ettei tiedostoa ole muutettu.

## Mitä ohjelmassa on

- **Yleiskuva:** yhteys autoon, akun tiedot reaaliajassa, kennoryhmäkaavio ja yhteystesti. Ensimmäisellä käyttökerralla näkyy käyttöönoton tarkistuslista.
- **Mittaus:** pikatarkastus (1–3 min) tai ohjattu kapasiteettimittaus. Vaiheet etenevät itsestään, ja mittausolosuhteet tarkistetaan koko ajan.
- **Autot:** ohjelma tunnistaa auton valmistenumerosta ja oppii akun tiedot ensimmäisessä mittauksessa. Mittaus estetään, jos kytketty auto ei ole sama kuin valittu.
- **Mittaukset:** tulokset, raportit, mittausdata ja raakadatan eheyden tarkistus.
- **Ohjeet:** koko käyttöohje ohjelmassa ja PDF-muodossa.
- **Asetukset:** raporttien yritystiedot ja logo, mittauksen raja-arvot, puhelinkäyttö ja puhelinilmoitukset.
- **Ylläpito:** laaduntarkistus, päivitys zip-paketista, varmuuskopiot ja palautus sekä tapahtumaloki.

## Raportti

1. Yhteenveto: kunto, kapasiteetti, jännite-ero, sanallinen tulos, mitä tulos tarkoittaa ja auton tiedot. Sivulla on allekirjoituskohta.
2. Arviot luokkineen (myös akkutakuu) ja mittausolosuhteet.
3. Kapasiteettimittaus: latauskäyrä, laskennan jokainen vaihe, luotettavuuden tarkistukset ja epävarmuuden erittely.
4. Kennoryhmät: kaaviot ja tunnusluvut, kapasiteettimittauksessa myös matalassa varauksessa.
5. Jokaisen kennoryhmän jännitetaulukko.
6. Akunhallinnan tiedot, elinkaaren energialaskurit, vertailu ajomäärään ja kunnon kehitys.
7. Menetelmä ja tietolähteet, mittauksen tapahtumat ja raakadatan tarkiste.
8. Sanasto.

## Päivittäminen

Lataa uusi versio Releases-sivulta ja asenna se vanhan päälle (katso Asennus). Ylläpito-sivulla on suora linkki julkaisuihin.

## Tietojen sijainti

- Mittaustiedostot ja raportit: `Tiedostot\Akux\Mittaukset` tai asetuksissa valittu kansio
- Ohjelman autot, mittaushistoria, asetukset ja varmuuskopiot: `%APPDATA%\Akux`
- Ohjelma: `%LOCALAPPDATA%\Programs\Akux`
- Rakennustyökalut (vain Asenna.bat-rakennuksessa): `%LOCALAPPDATA%\Akux\rakennus`

## Linux ja macOS

```
chmod +x kaynnista.sh
./kaynnista.sh
```
Linuxissa käyttäjän pitää kuulua `dialout`-ryhmään sarjaportin käyttämiseksi.

## Testit

```
python tests/test_kokonaisuus.py     # pikatarkastus ja kapasiteettimittaus simulaattorilla
python tests/test_reunatapaukset.py  # lataustauko, datakatko, ohitukset, keskeytykset
python tests/test_obdlink.py         # sovittimen alustus ja viestien luku
python tests/test_yllapito.py        # asetukset, ilmoitukset, varmuuskopio, päivitys, puhelinsuojaus
python tests/test_android_silta.py   # Android-sovelluksen USB-yhteys ja käynnistys
python tests/test_mittaustiedosto.py # mittaustiedoston tallennus, avaus ja eheys
```

GitHub ajaa jokaisen muutoksen jälkeen kaikki testit, rakentaa Windows-asennusohjelman ja testaa asennuksen, mittauksen, raportin ja päivityksen oikealla Windows-koneella sekä rakentaa Android-sovelluksen ja testaa sen Android-emulaattorissa. Vasta kun kaikki on hyväksytty, versio julkaistaan Releases-sivulle.

## Android-sovelluksen allekirjoitusavain

Android hyväksyy päivityksen vain, jos se on allekirjoitettu samalla avaimella kuin aiempi versio. Avain on repon kansiossa `android/` (`akux.jks` ja `signing.properties`). Säilytä avaimesta varmuuskopio turvallisessa paikassa, ja pidä repo yksityisenä.

## Lähteet ja lisenssit

- CAN-viestien määrittelyt: Tesla Model 3 DBC, https://github.com/joshwardell/model3dbc (MIT-lisenssi).
- Uudemman ohjelmistoversion energiaviestin rakenne: Battery-Emulator, https://github.com/dalathegreat/Battery-Emulator.
- OBD-liitännän kolmannen osapuolen CAN-väylä: Tesla, huoltodokumentti CD-20-17-001.
- Fontti Inter, SIL Open Font License 1.1 (`akux/data/fonts/LISENSSI-Inter.txt`).

Tesla, Model 3 ja Model Y ovat Tesla, Inc:n tavaramerkkejä. Akux ei ole Teslan tekemä eikä hyväksymä.
