# Uudet merkit: valmiit tiedot, liittämättä ohjelmaan

Haarassa `uudet-merkit` on 13 uuden alustan kyselytiedot avoimista lähteistä koneluettavassa muodossa
(`akveri/data/uudet/alustat.json`) sekä moottori, joka tekee niistä samanlaiset kyselyt ja vastausten purun kuin
nykyisillä alustoilla (`akveri/uudet/`). Ohjelma ei vielä käytä niitä. Alusta liitetään vasta, kun siitä on
mittaustiedosto oikeasta autosta.

## Alustat

| Alusta | Merkit | Kennot | Kunto | Energialaskurit | Väylä | Liittämisen työ |
| --- | --- | --- | --- | --- | --- | --- |
| e-CMP | Peugeot, Opel, Citroën, DS | kaikki 108 | kyllä, voi olla yli 100 % | ei | 11-bit | pieni |
| e-up! | Volkswagen, Škoda, SEAT | kaikki 84 | kyllä | ei | 11-bit | pieni |
| Zoe vaihe 1 | Renault | kaikki 96 | kyllä | ei | 11-bit, palvelu 21 | pieni, lämpötila puuttuu |
| Zoe vaihe 2 | Renault | ei | kyllä | ladattu | 29-bit, istunto 1003 | keskikokoinen |
| i3 / Cooper SE | BMW, MINI | vain ääriarvot | kyllä | kyllä | 11-bit, laajennettu osoitus | suuri |
| Mach-E | Ford | ei | kyllä | ei | 11-bit | pieni |
| I-Pace | Jaguar | ei | kyllä | ei | 11-bit | pieni |
| Ampera-e / Bolt | Opel, Chevrolet | ei | kapasiteetti kWh | ei | 11-bit | pieni |
| U5 | Aiways | ei | kyllä (1 %) | ei | 11-bit | pieni |
| e-Platform 3.0 | BYD | ei | ei | kyllä (1 kWh) | 11-bit | pieni, tavujärjestys varmistettava |
| Honda e | Honda | ei | kyllä | ei | 29-bit | pieni |
| 6e | Mazda | ei | ei | ei | 11-bit | pieni, vain perustiedot |
| Polestar 2 | Polestar (Volvo?) | ei | kyllä | ei | DoIP (Ethernet) | suuri, vain Windows |

Ford Explorer EV ja Ford Capri ovat MEB-alustaa, joten ne toimivat jo nykyisellä Volkswagen-tuella.

## Ei toteutettavissa nyt

Mercedes-Benz EQ, Volvo EX30 ja EX90, Toyota bZ4X, Subaru Solterra, Lexus RZ, Nissan Ariya, Xpeng, Zeekr, NIO,
Smart, Dacia Spring, Fiat 500e ja Jeep Avenger. Syyt on kirjattu tiedostoon kohtaan `ei_toteutettavissa`.

## Aiempien merkkien opit ja niiden testit

Testitiedosto `tests/test_uudet_alustat.py` (20 testiä) varmistaa jokaiselle alustalle:

| Opittu | Mistä | Mitä testataan |
| --- | --- | --- |
| Kunto voi olla jumissa tai yli 100 % | Hyundai, Peugeot | e-CMP:n 103 % säilyy, raportissa enintään 100 %; jumissa olevan kunnon sääntöä ei sovelleta |
| Väylä vaihtelee saman auton sisällä | Volkswagen | jokaisen osoitteen pituus vastaa väylää (11-bit = 3 merkkiä, 29-bit = 8) |
| Kuntoa ei aina saada | Volkswagen | pikatarkastus on estetty, jos alustalla ei ole kuntotietoa |
| Kennot vain ääriarvoina | MG | itsepurkaus on estetty alustoilla, joilla ei ole yksittäisiä kennoja |
| Sama tunniste, eri merkitys | Ford ja Jaguar | 22490C puretaan Fordissa kunnoksi ja Jaguarissa virraksi |
| Mittarilukema voi puuttua | Tesla, Ioniq | puuttuva mittarilukema on kirjattu |
| Kennojärjestys poikkeaa | e-up! | 84 kennoa numeroituu kerran ja oikein |
| Laskuri pyörähtää ympäri | Zoe, BMW, BYD | jokaisen kentän koko alue mahtuu sen tavuihin, ja pyörähdysraja on kirjattu |
| Virran etumerkki vaihtelee lähteittäin | kaikki | jokaiseen virtaan on kirjattu, mihin suuntaan purku on positiivinen |

Lisäksi jokaiselle alustalle testataan:
- **Purku:** jokaisen kentän tuottaminen ja purku, myös alueen reunoilla.
- **Virheelliset vastaukset:** lyhyet, tyhjät ja satunnaiset vastaukset eivät kaada eivätkä tuota mahdottomia arvoja.
- **Koko auto:** kaikki vastaukset tuotetaan tunnetuista arvoista ja puretaan takaisin samaan tilaan.

## Liittäminen ohjelmaan (alustaa kohden)

1. **Oikean auton mittaustiedosto:** se tallentaa raa'at vastaukset ja auton kieltävät vastaukset.
2. **Varmistus:** tiedostosta tarkistetaan kentät, joiden varmuus on `arvio`, sekä virran etumerkki ajossa.
3. **Alustamoduuli:** `akveri/<alusta>.py` saman mallin mukaan kuin `meb.py`; moottorin `Alusta`-luokka antaa kyselyt ja purun valmiina.
4. **Mallit:** auton mallit tiedostoon `profiles.json`.
5. **Simulaattori ja testit:** simulaattori ja testit kaikille mittaustyypeille (`tests/test_autot_ja_kemiat.py`).
6. **Uudet väyläominaisuudet:** BMW:n laajennettu osoitus, Zoen istunto 1003 ja Polestarin DoIP lisätään tiedostoon `sources.py`.

## Lähteet

- [evDash](https://github.com/nickn17/evDash) (MIT): e-CMP, Zoe, BMW i3, VW e-up!
- [ABRP:n avoimet kyselyt](https://github.com/iternio/ev-obd-pids) (Apache-2.0): Zoe ZE50, MINI Cooper SE, Mach-E, I-Pace, Bolt, Aiways U5, Honda e, Mazda 6e
- [BYD:n kyselyluettelo](https://github.com/loryanstrant/BYD-PID-list): BYD Atto 3 ja Dolphin
- [Polestar 2:n DoIP-esimerkki](https://gist.github.com/ckurtz22/8d8c6060a595cc8e60325c81b5ff981f): akunhallinnan osoite ja kunto
- [Stellantiksen akkuraportti](https://public.servicebox.peugeot.com/APddb/Battery_Report_Peugeot_8.08.2024.pdf): e-CMP-pakettien ampeeritunnit
- [Ford SSM 54995](https://static.nhtsa.gov/odi/tsbs/2026/MC-11035301-0001.pdf): Mach-E:n kunto akunhallinnan vaihdon jälkeen
- [OVMS: Renault Zoe vaihe 2](https://docs.openvehicles.com/en/latest/components/vehicle_renaultzoe_ph2/docs/index.html) ja [BMW i3](https://ovms.readthedocs.io/en/latest/components/vehicle_bmwi3/docs/index.html)
