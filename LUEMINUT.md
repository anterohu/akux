# AKUX 1.5

AKUX lukee Teslan ajoakun kunnon ja kapasiteetin suoraan auton akunhallinnasta OBDLink-sovittimella ja tekee tuloksista selkeän ja yksityiskohtaisen PDF-raportin ostajalle, asiakkaalle tai omaan käyttöön. Kaikki mittausarvot ovat auton akunhallinnan luovuttamia.

Tuetut autot: Model 3 ja Model Y (kaikki vuosimallit ja akkutyypit), Model S ja Model X (2012 alkaen; vuosien 2012–2021 vanhempi viestirakenne tunnistetaan automaattisesti) sekä Cybertruck kokeellisesti. Model S/X- ja Cybertruck-tukea ei ole vielä varmistettu oikealla autolla.

## Asennus

Valmiit ohjelmat ovat GitHubin **Releases**-sivulla: https://github.com/anterohu/akux/releases/latest

**Windows:** lataa `Akux-asennus-x.y.z.exe` ja aja se. AKUX avautuu omaan sovellusikkunaansa, eikä selainta tarvita. Asennus lisää pikakuvakkeen työpöydälle ja Käynnistä-valikkoon. Jos Windows näyttää ilmoituksen *Windows suojasi tietokonettasi*, valitse **Lisätietoja → Suorita silti**. Ilmoitus tulee vain asennusohjelmasta kerran jokaista uutta versiota kohden, ei itse ohjelmasta.

**Tuetut sovittimet:** OBDLink EX ja SX (USB) sekä OBDLink MX+ ja LX (Bluetooth). Bluetooth-sovitin paritetaan ensin Windowsin tai puhelimen Bluetooth-asetuksista, minkä jälkeen se näkyy AKUXin sovitinlistassa. Tavalliset ELM327-sovittimet eivät pysy Teslan väylän perässä, joten AKUX ei hyväksy niitä. OBDLink CX (Bluetooth Low Energy) ei ole vielä tuettu.

**Android (10 tai uudempi):** lataa `Akux-x.y.z.apk` puhelimeen ja avaa se. Android kysyy kerran luvan asentaa sovelluksia tästä lähteestä. Kytke OBDLink EX välikaapelilla auton diagnostiikkaliittimeen ja USB-C-sovittimella (OTG) puhelimeen ja salli AKUXille pääsy sovittimeen. Diagnostiikkaliitin on keskikonsolin takapäässä: vuosien 2019–2020 autoissa 20-pinninen ja 2021 alkaen 26-pinninen. Jalkatilan OBD-liitäntä ei välitä akun tietoja. Kapasiteettimittaukseen (8–14 h) tarvitaan OTG-sovitin, jossa on PD-latausportti, jotta puhelin latautuu mittauksen ajan.

**Päivitys:** lataa uusi versio samasta paikasta ja asenna se vanhan päälle. Autot, mittaukset, raportit ja asetukset säilyvät. Mitään tiedostoja ei tarvitse poistaa, siirtää eikä nimetä uudelleen.

**Vaihtoehto Windowsissa, rakennus omalla koneella:** lataa Releases-sivulta lähdekoodi (zip), pura se ja aja `Asenna.bat`. Tällöin AKUX rakennetaan omalla koneellasi, eikä SmartScreen kysy mitään. Molemmat tavat asentavat ohjelman samaan paikkaan ja käyttävät samoja tietoja.

## Mittaustiedostot

Jokainen valmis mittaus tallennetaan automaattisesti mittaustiedostona (`.akux`) ja PDF-raporttina:

- Windows: `Tiedostot\Akux\Mittaukset` (kansion voi vaihtaa asetuksista, esimerkiksi OneDriveen)
- Android: `Lataukset/Akux`

Mittaustiedosto sisältää kaiken: auton tiedot, mittausnäytteet, kennoryhmien jännitteet, tapahtumat, tuloksen, muuttamattoman raakadatan ja raportin. Sen voi avata missä tahansa AKUX-versiossa ja millä tahansa laitteella kohdasta **Mittaukset → Avaa mittaustiedosto**. Ohjelma tarkistaa avattaessa, ettei tiedostoa ole muutettu.

## Mitä ohjelmassa on

- **Yleiskuva:** yhteys autoon, akun tiedot reaaliajassa, kennoryhmäkaavio ja yhteystesti. Ensimmäisellä käyttökerralla näkyy käyttöönoton tarkistuslista.
- **Mittaus:** kahdeksan mittausta kolmessa ryhmässä. Vaiheet etenevät itsestään, ja mittausolosuhteet tarkistetaan koko ajan.
  - *Paikallaan:* pikatarkastus (1–3 min), kapasiteettimittaus latauksen aikana (8–14 h) ja itsepurkaustesti (yön yli).
  - *Ajossa:* täysi akkutesti (purku ajossa ja lataus täyteen), ajotesti, pika-ajotesti ja kuormitustesti.
  - *Pikalaturilla:* pikalataustesti.
  - Ajotestit ja itsepurkaustesti voi jättää **jatkettavaksi myöhemmin** ja jatkaa ohjelman uudelleenkäynnistyksen jälkeen. Jos autoa ladataan tauon aikana, se havaitaan Teslan latauslaskurista.
  - Raportti näyttää mitatun kunnon vain, kun epävarmuus on enintään ±3 %-yksikköä ja mittauksen laatu riittää. Muuten näytetään Teslan akunhallinnan ilmoittama arvo ja syy.
- **Esimerkkiautot:** Autot-sivulta saa kolme esimerkkiautoa, joissa on valmiit raportit kaikista mittaustyypeistä, joten ohjelmaa voi tutkia ilman autoa.
- **Autot:** ohjelma tunnistaa auton valmistenumerosta ja oppii akun tiedot ensimmäisessä mittauksessa. Mittaus estetään, jos kytketty auto ei ole sama kuin valittu.
- **Mittaukset:** tulokset, raportit, mittausdata ja raakadatan eheyden tarkistus.
- **Ohjeet:** koko käyttöohje ohjelmassa ja PDF-muodossa.
- **Asetukset:** raporttien yritystiedot ja logo, mittauksen raja-arvot, puhelinkäyttö ja puhelinilmoitukset.
- **Ylläpito:** laaduntarkistus, linkki uusimpaan versioon, varmuuskopiot ja palautus sekä tapahtumaloki.

## Raportti

Raportti on kaksiosainen. Pääsivut on tarkoitettu asiakkaalle, tekninen liite tarkistajalle. Liitteen voi jättää pois asetuksista.

**Pääsivut**
1. Etusivu: akun kunto, kapasiteetti brutto ja netto, jännite-ero, Teslan akunhallinnan omat arvot, mitä tulos tarkoittaa ja auton tiedot (myös rekisterinumero ja vapaaehtoinen auton kuva). Allekirjoituskohta ja raportin tunnistetiedot QR-koodina.
2. Yhteenveto, tulokset luokkineen (myös akkutakuu) ja mittauksen tiedot.
3. Mittauksen oma sivu kaavioineen: kapasiteettimittaus, purkumittaus ajossa, lataus- ja purkumittauksen vertailu, kennoryhmien resistanssi, pikalatauksen tehokäyrä tai itsepurkautuminen.
4. Kennoryhmät: kaaviot ja tunnusluvut sekä kunnon kehitys, jos autosta on aiempia mittauksia.
5. Lisäsivu: jokaisen kennoryhmän jännite taulukkona, kapasiteettimittauksessa myös matalassa varauksessa.

**Tekninen liite**
- Mittauksen vaiheet ja mittaustarkkuuden erittely.
- Akunhallinnan tiedot ja elinkaaren energialaskurit.
- Menetelmä ja tietolähteet, mittauksen tapahtumat ja raakadatan tarkiste.
- Sanasto.

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
python tests/test_mallit.py          # kaikki mallit, Model S/X:n vanha viestirakenne
python tests/test_testityypit.py     # kaikki testityypit, tauko ja jatko, lataus tauon aikana
python tests/test_autot_ja_kemiat.py # datan luku bitintarkasti ja jokainen testi NCA-, LFP- ja NMC-akuilla sekä Model S:llä
```

GitHub ajaa jokaisen muutoksen jälkeen kaikki testit, rakentaa Windows-asennusohjelman ja testaa asennuksen, mittauksen, raportin ja päivityksen oikealla Windows-koneella sekä rakentaa Android-sovelluksen ja testaa sen Android-emulaattorissa. Vasta kun kaikki on hyväksytty, versio julkaistaan Releases-sivulle.

## Android-sovelluksen allekirjoitusavain

Android hyväksyy päivityksen vain, jos se on allekirjoitettu samalla avaimella kuin aiempi versio. Avain on repon kansiossa `android/` (`akux.jks` ja `signing.properties`). Säilytä avaimesta varmuuskopio turvallisessa paikassa, ja pidä repo yksityisenä.

## Lähteet ja lisenssit

- CAN-viestien määrittelyt: Tesla Model 3 DBC, https://github.com/joshwardell/model3dbc (MIT-lisenssi).
- Model S 2012–2021 / Model X 2015–2021: Open Vehicle Monitoring System, https://github.com/openvehicles/Open-Vehicle-Monitoring-System-3 (MIT-lisenssi), ja Battery-Emulatorin TESLA-LEGACY-BATTERY.
- Uudemman ohjelmistoversion energiaviestin rakenne: Battery-Emulator, https://github.com/dalathegreat/Battery-Emulator.
- OBD-liitännän kolmannen osapuolen CAN-väylä: Tesla, huoltodokumentti CD-20-17-001.
- Fontti Inter, SIL Open Font License 1.1 (`akux/data/fonts/LISENSSI-Inter.txt`).

Tesla, Model 3, Model Y, Model S, Model X ja Cybertruck ovat Tesla, Inc:n tavaramerkkejä. AKUX ei ole Teslan tekemä eikä hyväksymä.
