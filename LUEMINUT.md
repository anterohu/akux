# AKVERI 2.0

AKVERI lukee sähköauton ajoakun kunnon ja kapasiteetin suoraan auton akunhallinnasta OBDLink-sovittimella ja tekee tuloksista selkeän ja yksityiskohtaisen PDF-raportin ostajalle, asiakkaalle tai omaan käyttöön. Kaikki mittausarvot ovat auton akunhallinnan luovuttamia.

Tuetut autot: Model 3 ja Model Y (kaikki vuosimallit ja akkutyypit), Model S ja Model X (2012 alkaen; vuosien 2012–2021 vanhempi viestirakenne tunnistetaan automaattisesti) sekä Cybertruck kokeellisesti. Model S/X- ja Cybertruck-tukea ei ole vielä varmistettu oikealla autolla.

Muut merkit (versiosta 1.8 alkaen): Hyundai Ioniq Electric, Kona Electric, Ioniq 5 ja Ioniq 6, Kia e-Niro, e-Soul ja EV6, Nissan Leaf (24, 30, 40 ja 62 kWh) sekä Volkswagen-konsernin MEB-alustan autot (Volkswagen ID.3, ID.4 ja ID.5, Škoda Enyaq, Audi Q4 e-tron ja Cupra Born). Näiden autojen akunhallinta vastaa vain kyselyihin, joten auton on oltava mittauksen aikana päällä tai latauksessa. Muiden merkkien tukea ei ole vielä varmistettu oikealla autolla. Erot Teslaan on kuvattu ohjelman ohjeissa kohdassa Muut merkit.

## Asennus ja krediitit

**Android (10 tai uudempi):** AKVERI asennetaan Google Playsta. Mittaukset maksetaan krediiteillä, jotka ostetaan sovelluksen **Krediitit**-sivulla. Yksi krediitti kattaa yhden mittauksen ja sen raportin. Esittelytila ei käytä krediittejä.

**Windows:** Windows-versiota ei toistaiseksi jaeta asiakkaille. Omistaja lataa sen akveri.fi/hallinta-sivun kohdasta **Omat lataukset**. Windows-versio käyttää samaa krediittijärjestelmää: krediitit lisätään tilille hallinnassa.

**Raportin tarkistus:** jokaisella mittauksella on tunnus (esim. AK-7H2QK-M4XPC). Raportin QR-koodi avaa sivun akveri.fi/v/tunnus, jolla vastaanottaja näkee rekisteröidyt tulokset. Mittauksen aloittaminen vaatii verkkoyhteyden. Valmis raportti rekisteröidään automaattisesti, tarvittaessa heti kun yhteys palaa.

**akveri.fi-palvelin:** kansio `palvelin/` (ks. `palvelin/README.md`). Hallintatyökalun AKVERI-välilehdeltä viedään päivityspaketti `akveri-paivitys-x.y.z.zip`: se päivittää palvelimen ja vie Windows-asennuksen ja Android-sovelluksen Omiin latauksiin. Paketti `akveri-palvelin-x.y.z.zip` sisältää pelkän palvelimen.

**Tuetut sovittimet:** OBDLink EX ja SX (USB) sekä OBDLink MX+ ja LX (Bluetooth). Bluetooth-sovitin paritetaan ensin Windowsin tai puhelimen Bluetooth-asetuksista, minkä jälkeen se näkyy AKVERIn sovitinlistassa. Tavalliset ELM327-sovittimet eivät pysy Teslan väylän perässä, joten AKVERI ei hyväksy niitä. OBDLink CX (Bluetooth Low Energy) ei ole vielä tuettu.

**Kytkentä puhelimeen:** kytke OBDLink EX välikaapelilla auton diagnostiikkaliittimeen ja USB-C-sovittimella (OTG) puhelimeen ja salli AKVERIlle pääsy sovittimeen. Teslan diagnostiikkaliitin on keskikonsolin takapäässä: vuosien 2019–2020 autoissa 20-pinninen ja 2021 alkaen 26-pinninen. Jalkatilan OBD-liitäntä ei välitä akun tietoja. Kapasiteettimittaukseen (8–14 h) tarvitaan OTG-sovitin, jossa on PD-latausportti, jotta puhelin latautuu mittauksen ajan.

**Päivitys:** Google Play päivittää sovelluksen. Windowsissa asenna uusi versio vanhan päälle. Autot, mittaukset, raportit ja asetukset säilyvät. Mitään tiedostoja ei tarvitse poistaa, siirtää eikä nimetä uudelleen.

## Mittaustiedostot

Jokainen valmis mittaus tallennetaan automaattisesti mittaustiedostona (`.akveri`) ja PDF-raporttina:

- Windows: `Tiedostot\AKVERI\Mittaukset` (kansion voi vaihtaa asetuksista, esimerkiksi OneDriveen)
- Android: `Lataukset/AKVERI`

Mittaustiedosto sisältää kaiken: auton tiedot, mittausnäytteet, kennoryhmien jännitteet, tapahtumat, tuloksen, muuttamattoman raakadatan ja raportin. Sen voi avata missä tahansa AKVERI-versiossa ja millä tahansa laitteella kohdasta **Mittaukset → Avaa mittaustiedosto**. Ohjelma tarkistaa avattaessa, ettei tiedostoa ole muutettu.

## Mitä ohjelmassa on

- **Yleiskuva:** yhteys autoon, akun tiedot reaaliajassa, kennoryhmäkaavio ja yhteystesti. Ensimmäisellä käyttökerralla näkyy käyttöönoton tarkistuslista.
- **Mittaus:** kahdeksan mittausta kolmessa ryhmässä. Vaiheet etenevät itsestään, ja mittausolosuhteet tarkistetaan koko ajan.
  - *Paikallaan:* pikatarkastus (1–3 min), kapasiteettimittaus latauksen aikana (8–14 h) ja itsepurkaustesti (yön yli).
  - *Ajossa:* täysi akkutesti (purku ajossa ja lataus täyteen), ajotesti, pika-ajotesti ja kuormitustesti.
  - *Pikalaturilla:* pikalataustesti.
  - Ajotestit ja itsepurkaustesti voi jättää **jatkettavaksi myöhemmin** ja jatkaa ohjelman uudelleenkäynnistyksen jälkeen. Jos autoa ladataan tauon aikana, se havaitaan latauslaskurista. Latausvaiheen tauon aikana akkuun mennyt tai siitä kulunut energia (esimerkiksi lämmitys) luetaan auton elinkaaren energialaskureista.
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

Androidissa Google Play päivittää AKVERIn. Windowsissa asenna uusi versio vanhan päälle (katso Asennus).


## Tietojen sijainti

- Mittaustiedostot ja raportit: `Tiedostot\AKVERI\Mittaukset` tai asetuksissa valittu kansio
- Ohjelman autot, mittaushistoria, asetukset ja varmuuskopiot: `%APPDATA%\AKVERI`
- Ohjelma: `%LOCALAPPDATA%\Programs\AKVERI`
- Rakennustyökalut (vain Asenna.bat-rakennuksessa): `%LOCALAPPDATA%\AKVERI\rakennus`

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

Android hyväksyy päivityksen vain, jos se on allekirjoitettu samalla avaimella kuin aiempi versio. Avain on repon kansiossa `android/` (`akveri.jks` ja `signing.properties`). Säilytä avaimesta varmuuskopio turvallisessa paikassa, ja pidä repo yksityisenä.

## Lähteet ja lisenssit

- CAN-viestien määrittelyt: Tesla Model 3 DBC, https://github.com/joshwardell/model3dbc (MIT-lisenssi).
- Model S 2012–2021 / Model X 2015–2021: Open Vehicle Monitoring System, https://github.com/openvehicles/Open-Vehicle-Monitoring-System-3 (MIT-lisenssi), ja Battery-Emulatorin TESLA-LEGACY-BATTERY.
- Uudemman ohjelmistoversion energiaviestin rakenne: Battery-Emulator, https://github.com/dalathegreat/Battery-Emulator.
- Hyundai ja Kia: OBD-PIDs-for-HKMC-EVs, https://github.com/JejuSoul/OBD-PIDs-for-HKMC-EVs, ja evDash, https://github.com/nickn17/evDash (MIT-lisenssi).
- Nissan Leaf: Open Vehicle Monitoring System (vehicle_nissanleaf), Battery-Emulator ja py-nissan-leaf-obd-ble, https://github.com/pbutterworth/py-nissan-leaf-obd-ble.
- Volkswagen-konsernin MEB: evDash (CarVWID3) ja Battery-Emulator.
- OBD-liitännän kolmannen osapuolen CAN-väylä: Tesla, huoltodokumentti CD-20-17-001.
- Fontti Inter, SIL Open Font License 1.1 (`akveri/data/fonts/LISENSSI-Inter.txt`).

Tesla, Model 3, Model Y, Model S, Model X ja Cybertruck ovat Tesla, Inc:n tavaramerkkejä. Hyundai, Kia, Nissan, Volkswagen, Škoda, Audi ja Cupra sekä niiden mallinimet ovat omistajiensa tavaramerkkejä. AKVERI ei ole minkään autonvalmistajan tekemä eikä hyväksymä.
