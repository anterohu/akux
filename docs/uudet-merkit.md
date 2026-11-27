# Uudet merkit: valmiit tiedot, liittämättä ohjelmaan

Tässä haarassa (`uudet-merkit`) on kuuden uuden alustan kyselytiedot avoimista lähteistä tiedostossa
`akveri/data/uudet/alustat.json`. Ohjelma ei vielä käytä niitä. Jokainen alusta liitetään vasta, kun siitä on
saatu ainakin yksi mittaustiedosto oikeasta autosta.

## Alustat

| Alusta | Mallit | Kennot | Kunto | Energialaskurit | Mitä AKVERIin tarvitaan |
| --- | --- | --- | --- | --- | --- |
| Stellantis e-CMP | Peugeot e-208, e-2008, Opel Corsa-e, Mokka-e, Citroën ë-C4, DS 3 | kaikki 108 | kyllä (voi olla yli 100 %) | ei | vain uusi alustamoduuli |
| VW e-up!, Citigo e, Mii electric | | kaikki 84 | kyllä | ei | MEB-moduulin muunnelma (11-bittinen väylä, oma kennojärjestys) |
| Renault Zoe vaihe 1 | Zoe 22 kWh, ZE40 | kaikki 96 | kyllä | ei | uusi moduuli, palvelu 21 |
| Renault Zoe vaihe 2 | Zoe ZE50 | ei | kyllä (vanha ohjelmistoversio liian pieni) | kyllä | diagnostiikkaistunto 1003 ennen kyselyjä |
| BMW i3 ja MINI Cooper SE | | vain ääriarvot | kyllä | kyllä | laajennettu osoitus ja oma väyläasetus: suurin työ |
| Ford Mustang Mach-E | | ei | kyllä (vaihdettu akunhallinta voi näyttää liikaa) | ei | vain uusi alustamoduuli |
| Jaguar I-Pace | | ei | kyllä | ei | vain uusi alustamoduuli |

Ford Explorer EV ja Ford Capri ovat MEB-alustaa, joten ne toimivat jo nykyisellä Volkswagen-tuella.

## Ei toteutettavissa nyt

- **Volvo ja Polestar:** akunhallinta luetaan Ethernet-väylän (DoIP) kautta, eikä OBDLink tue sitä.
- **Mercedes-Benz EQ:** suojattu diagnostiikkayhdyskäytävä, ei avoimia tietoja.
- **BYD:** varaustila ja kennojen ääriarvot tunnetaan, kuntoa ei ole varmistettu.
- **Toyota bZ4X, Subaru Solterra, Xpeng, Zeekr, NIO:** avoimia lähteitä ei löytynyt.

## Aiempien merkkien opit, jotka on otettu huomioon

1. **Kunto voi olla jumissa tai väärin.** Jokaiselle alustalle on kirjattu, milloin akunhallinnan kuntoon ei voi
   luottaa (Zoe vaihe 2, Mach-E). e-CMP:n kunto voi olla yli 100 %, joten jumissa olevan kunnon sääntöä ei saa
   soveltaa siihen.
2. **Väylä vaihtelee saman auton sisällä.** Jokaiselle ohjainlaitteelle on kirjattu tunnisteen pituus (11 tai 29
   bittiä), protokolla ja erityisvaatimukset (BMW:n kohdetavu, Zoen istunto 1003).
3. **Kennot voivat puuttua tai tulla ryhminä.** Kennolukutapa on kirjattu, ja testit, joita ei voi tehdä ilman
   kennojännitteitä, on ehdotettu estettäviksi.
4. **Sama tunniste tarkoittaa eri merkeissä eri asiaa.** Esimerkiksi 22490C on Fordissa kunto ja Jaguarissa virta.
   Kyselyt sidotaan aina alustaan.
5. **Mittarilukema ja valmistenumero voivat puuttua.** Puuttuvat tiedot on lueteltu; mittarilukema kysytään
   mittauksen lopussa.
6. **Kuntotiedot pitää voida tarkistaa ennen ostoa.** Jokaiselle alustalle on kirjattu kuntotiedon kyselyt
   (`kunto_tunnisteet`), joilla pikatarkastus estetään, jos auto ei ilmoita kuntoa.

## Liittämisen järjestys

1. **VW e-up! ja e-CMP:** eniten tietoa, pienin työ.
2. **Zoe vaihe 1 ja vaihe 2.**
3. **Mach-E ja I-Pace:** vain akunhallinnan kunto ja perustiedot.
4. **BMW i3 ja MINI:** vaativat uuden väyläominaisuuden.

Jokaiseen liitokseen kuuluu alustamoduuli (`akveri/<alusta>.py`), simulaattori, mallit `profiles.json`-tiedostoon,
testit kaikille mittaustyypeille sekä oikean auton mittaustiedosto ennen julkaisua.

## Lähteet

- [evDash](https://github.com/nickn17/evDash) (MIT): e-CMP, Zoe, BMW i3, VW e-up!
- [ABRP:n avoimet kyselyt](https://github.com/iternio/ev-obd-pids) (Apache-2.0): Zoe ZE50, MINI Cooper SE, Mach-E, I-Pace
- [Stellantiksen akkuraportti](https://public.servicebox.peugeot.com/APddb/Battery_Report_Peugeot_8.08.2024.pdf): e-CMP-pakettien ampeeritunnit
- [Ford SSM 54995](https://static.nhtsa.gov/odi/tsbs/2026/MC-11035301-0001.pdf): Mach-E:n akunhallinnan kunto vaihdon jälkeen
- [OVMS: Renault Zoe vaihe 2](https://docs.openvehicles.com/en/latest/components/vehicle_renaultzoe_ph2/docs/index.html) ja [BMW i3](https://ovms.readthedocs.io/en/latest/components/vehicle_bmwi3/docs/index.html)
