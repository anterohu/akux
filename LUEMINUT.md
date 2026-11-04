# Akux 1.2

Akux mittaa Tesla Model 3:n ja Model Y:n ajoakun kunnon ja kapasiteetin OBDLink-sovittimella ja tekee tuloksista selkeän ja yksityiskohtaisen PDF-raportin ostajalle, asiakkaalle tai omaan käyttöön.

## Asennus Windowsiin

1. Pura paketti esimerkiksi työpöydälle.
2. Kaksoisnapsauta **Asenna.bat**.

Asennus tekee kaiken itse: lataa tarvittavat osat, rakentaa sovelluksen **Akux.exe**, asentaa sen, lisää pikakuvakkeen työpöydälle ja Käynnistä-valikkoon ja avaa ohjelman. Ensimmäinen asennus kestää noin 5–10 minuuttia ja vaatii verkkoyhteyden. Tietokoneelle ei tarvitse asentaa mitään muuta.

Asennuksen jälkeen ohjelma avataan pikakuvakkeesta **Akux**. Se avautuu omaan ikkunaansa, eikä erillistä komentoikkunaa ole. Purkamasi kansion voi poistaa asennuksen jälkeen.

Sovellus rakennetaan omalla tietokoneellasi, joten Windowsin SmartScreen ei varoita siitä. Asennus poistaa purettujen tiedostojen latauseston itse.

## Asennus Android-puhelimeen tai -tablettiin

1. Avaa puhelimella GitHubista Akux-repon **Releases**-sivu ja lataa uusin **Akux-x.y.z.apk**.
2. Avaa ladattu tiedosto. Android kysyy kerran luvan asentaa sovelluksia tästä lähteestä. Salli se.
3. Avaa Akux. Kytke OBDLink EX auton OBD-liitäntään ja USB-C-sovittimella (OTG) puhelimeen ja salli Akuxille pääsy sovittimeen.

Vaatimus: Android 10 tai uudempi. Päivitys asennetaan samalla tavalla uuden version päälle, ja tiedot säilyvät.

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

Avaa **Ylläpito** ja valitse uusi Akux-paketti (zip). Ohjelma tarkistaa version, asentaa sen ja avautuu uudelleen. Vaihtoehtoisesti voit purkaa paketin ja ajaa sen **Asenna.bat**-tiedoston.

Autot, mittaukset, raportit ja asetukset säilyvät, koska ne ovat eri kansiossa kuin ohjelma. Päivityksessä ei tarvitse poistaa, siirtää eikä nimetä uudelleen yhtään tiedostoa.

## Tietojen sijainti

- Mittaukset, raportit, asetukset ja varmuuskopiot: `%APPDATA%\Akux`
- Ohjelma: `%LOCALAPPDATA%\Programs\Akux`
- Rakennustyökalut uusia versioita varten: `%LOCALAPPDATA%\Akux\rakennus`

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
```

GitHub ajaa jokaisen muutoksen jälkeen kaikki testit, oikean Windows-asennuksen sekä Android-sovelluksen rakennuksen ja kokonaistestin Android-emulaattorissa. Hyväksytty Android-versio julkaistaan Releases-sivulle.

## Android-sovelluksen allekirjoitusavain

Android hyväksyy päivityksen vain, jos se on allekirjoitettu samalla avaimella kuin aiempi versio. Avain on repon kansiossa `android/` (`akux.jks` ja `signing.properties`). Säilytä avaimesta varmuuskopio turvallisessa paikassa, ja pidä repo yksityisenä.

## Lähteet ja lisenssit

- CAN-viestien määrittelyt: Tesla Model 3 DBC, https://github.com/joshwardell/model3dbc (MIT-lisenssi).
- Uudemman ohjelmistoversion energiaviestin rakenne: Battery-Emulator, https://github.com/dalathegreat/Battery-Emulator.
- OBD-liitännän kolmannen osapuolen CAN-väylä: Tesla, huoltodokumentti CD-20-17-001.
- Fontti Inter, SIL Open Font License 1.1 (`akux/data/fonts/LISENSSI-Inter.txt`).

Tesla, Model 3 ja Model Y ovat Tesla, Inc:n tavaramerkkejä. Akux ei ole Teslan tekemä eikä hyväksymä.
