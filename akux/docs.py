"""Käyttöohje. Sama sisältö näytetään ohjelman Ohjeet-sivulla ja ladattavana PDF:nä."""
from __future__ import annotations

OHJE = [
    {
        "id": "aloitus", "otsikko": "Aloitus",
        "osat": [
            ("p", "AKVERI lukee Teslan ajoakun kunnon ja kapasiteetin suoraan auton akunhallinnasta ja kokoaa tiedot "
                  "raportiksi, jonka voi antaa ostajalle, asiakkaalle tai pitää itsellä. Kaikki mittausarvot ovat "
                  "auton akunhallinnan luovuttamia. AKVERI ei käytä omia antureitaan eikä muuta arvoja."),
            ("ul", [
                "<b>Model 3 ja Model Y</b>, kaikki vuosimallit ja akkutyypit (NCA, NMC ja LFP).",
                "<b>Model S ja Model X</b>: vuodesta 2021 valmistetut samalla tavalla kuin Model 3. Vuosien 2012–2021 "
                "Model S ja 2015–2021 Model X käyttävät omaa viestirakennettaan, jonka AKVERI tunnistaa itse. Niiden "
                "akunhallinta ei ilmoita akun alkuperäistä kapasiteettia, joten se kannattaa syöttää auton tietoihin.",
                "<b>Cybertruck</b>: auto tunnistetaan, mutta mittaus on kokeellinen.",
            ]),
            ("ol", [
                "Avaa <b>Asetukset</b> ja täytä yrityksen tiedot, mittaajan nimi ja logo. Tiedot näkyvät jokaisessa raportissa.",
                "Kytke OBDLink-sovitin välikaapelilla auton diagnostiikkaliittimeen ja USB-kaapelilla tietokoneeseen. Bluetooth-mallit (MX+, LX) paritetaan ensin Windowsin Bluetooth-asetuksista.",
                "Herätä auto ja paina <b>Yleiskuva</b>-sivulla <b>Yhdistä autoon</b>.",
                "Lisää auto. Ohjelma lukee valmistenumeron autosta ja tunnistaa mallin.",
                "Tee autolle pikatarkastus. Sen jälkeen voit tehdä kapasiteettimittauksen.",
            ]),
            ("p", "<b>Esimerkkiautot:</b> Autot-sivun painike <b>Lisää esimerkkiautot</b> tuo ohjelmaan kolme autoa "
                  "valmiine mittauksineen ja raportteineen. Niillä näkee heti, miltä raportit ja ohjelman eri näkymät "
                  "näyttävät. Esimerkit poistetaan samasta kohdasta, eikä poisto koske omia autoja."),
            ("note", "Ohjelma ainoastaan lukee tietoja. Se ei lähetä autolle mitään eikä muuta auton asetuksia."),
        ],
    },
    {
        "id": "yhdistaminen", "otsikko": "Yhdistäminen autoon",
        "osat": [
            ("p", "Akun tiedot luetaan auton diagnostiikkaliittimestä OBDLink-sovittimella ja mallille sopivalla "
                  "välikaapelilla. Auton sivulla <b>Kytkentä autoon</b> kertoo juuri sen auton liittimen."),
            ("ul", [
                "<b>Tuetut sovittimet:</b> OBDLink EX ja SX (USB) sekä OBDLink MX+ ja LX (Bluetooth). AKVERI käyttää "
                "OBDLinkin suodatusta, jolla vain akun tiedot välitetään. Tavalliset ELM327-sovittimet eivät pysy "
                "Teslan väylän liikenteen perässä, joten AKVERI ei hyväksy niitä.",
                "<b>Bluetooth:</b> kytke sovitin autoon ja herätä auto. Paina MX+:n painiketta ja muodosta pari "
                "Windowsin tai puhelimen Bluetooth-asetuksista. Sen jälkeen sovitin näkyy AKVERIn sovitinlistassa "
                "merkinnällä Bluetooth. Listalla näkyvät vain OBDLink-sovittimet, eivät muut paritetut laitteet, "
                "kuten kuulokkeet tai auto.",
                "OBDLink CX käyttää Bluetooth Low Energy -yhteyttä, jota AKVERI ei vielä tue.",
            ]),
            ("ul", [
                "<b>Model 3 ja Model Y (2019–2024):</b> liitin on keskikonsolin takapäässä takamatkustajien puolella "
                "paneelin takana. Vuosien 2019–2020 autoissa se on 20-pinninen ja 2021 alkaen 26-pinninen. "
                "Vuodenvaihteen 2020–2021 autoissa laske pinnit tai hanki sarja, jossa on molemmat kaapelit.",
                "<b>Uudistettu Model 3 (2024–) ja Model Y (2025–):</b> liitin ja sen paikka poikkeavat. Varmista "
                "välikaapelin myyjältä, että kaapeli on tehty juuri tälle mallille.",
                "<b>Model S 2012–2021 ja Model X 2015–2021:</b> välikaapelin pitää tuoda voimalinjan CAN-väylä. "
                "Liitin on erilainen vuosien 2012–09/2015 Model S:ssä ja sitä uudemmissa.",
                "<b>Model S ja Model X 2021–04/2024:</b> sininen 20-napainen liitin kosketusnäytön alla langattoman "
                "latausalustan yläpuolella. Tarvitaan Model S/X:lle tehty välikaapeli.",
                "<b>Model S ja Model X 05/2024 alkaen:</b> sovitin kytketään suoraan kuljettajan jalkatilan OBD-liitäntään.",
            ]),
            ("note", "Model 3:n ja Model Y:n jalkatilassa on myös tavallisen näköinen OBD-liitäntä. Se on tarkoitettu "
                     "kolmannen osapuolen laitteille, ja se välittää vain muutaman tiedon, kuten nopeuden ja virtatilan, "
                     "mutta ei akun tietoja. Yhteystesti ja väylän kartoitus kertovat tämän suoraan."),
            ("ol", [
                "Kytke sovitin auton liitäntään ja tietokoneeseen.",
                "Herätä auto avaamalla ovi tai käynnistämällä ilmastointi Tesla-sovelluksesta. Sovitin saa virtaa vain, kun auto on hereillä.",
                "Valitse <b>Yleiskuva</b>-sivulla sovitin ja paina <b>Yhdistä autoon</b>.",
                "Odota, että <b>Yhteystesti</b> näyttää kaikki tarvittavat tiedot vihreinä. Tämä kestää yleensä muutaman sekunnin.",
            ]),
            ("p", "Ensimmäisellä kytkentäkerralla Windows asentaa sovittimen ajurin itse, kun tietokone on verkossa. "
                  "Jos sovitin ei näy listassa, odota hetki ja paina <b>Päivitä portit</b>."),
        ],
    },
    {
        "id": "autot", "otsikko": "Autot",
        "osat": [
            ("p", "Jokainen mitattava auto tallennetaan kerran. Ohjelma tunnistaa valmistenumerosta mallin, "
                  "vuosimallin, valmistustehtaan ja voimalinjan ja valitsee niiden perusteella oikean mallipohjan."),
            ("p", "Ensimmäisessä mittauksessa ohjelma lukee akunhallinnasta akun alkuperäisen kapasiteetin, "
                  "kennoryhmien määrän ja akun tyypin ja tallentaa ne autolle. Jatkossa ohjelma käyttää näitä tietoja "
                  "suoraan."),
            ("ul", [
                "<b>Käyttöönottopäivä</b> tarvitaan akkutakuun voimassaolon laskemiseen. Sen löytää rekisteriotteesta.",
                "<b>Alkuperäinen kapasiteetti</b> kannattaa syöttää käsin vain, jos auto ei ilmoita sitä itse. Näin on vuosien 2012–2021 Model S:ssä ja 2015–2021 Model X:ssä.",
                "<b>Rekisterinumero</b> näkyy raportin etusivulla. Sitä ei voi lukea autosta, joten se syötetään käsin.",
                "<b>Auton kuva</b> on vapaaehtoinen. Lisää se auton sivulla, niin kuva näkyy raportin etusivulla. Puhelimella otetun kuvan asento korjataan automaattisesti.",
                "Auton sivulla näkyy kaikki sen mittaukset ja akun kunnon kehitys.",
            ]),
        ],
    },
    {
        "id": "pikatarkastus", "otsikko": "Pikatarkastus",
        "osat": [
            ("p", "Pikatarkastus kestää 1–3 minuuttia. Se lukee akunhallinnan arvion akun nykyisestä kapasiteetista, "
                  "alkuperäisen kapasiteetin, kaikkien kennoryhmien jännitteet, lämpötilat ja akun elinkaaren "
                  "energialaskurit. Pikatarkastus sopii esimerkiksi kauppatilanteeseen."),
            ("ol", [
                "Valitse <b>Mittaus</b>-sivulla auto ja <b>Pikatarkastus</b>.",
                "Tarkista mittarilukema ja paina <b>Aloita mittaus</b>.",
                "Pidä auto paikallaan, kunnes raportti on valmis.",
            ]),
            ("note", "Kennoryhmien jännite-ero on luotettavin, kun auto on seissyt vähintään 15 minuuttia ilman ajoa tai latausta."),
        ],
    },
    {
        "id": "kapasiteetti", "otsikko": "Kapasiteettimittaus",
        "osat": [
            ("p", "Kapasiteettimittaus selvittää akun todellisen kapasiteetin. Akkuun latauksen aikana menevä energia "
                  "mitataan akun omasta jännitteestä ja virrasta koko latauksen ajan. Tulos ei riipu akunhallinnan "
                  "omasta arviosta, ja raportissa näkyy laskennan jokainen vaihe."),
            ("ol", [
                "<b>Aja akku tyhjäksi.</b> Paras tulos saadaan, kun lataus aloitetaan alle 10 %:n varauksesta. Raja voi olla enintään 15 %.",
                "<b>Huomioi lämpötila.</b> Vertailukelpoinen tulos saadaan, kun akku on 15–35 °C. Talvella mittaus tehdään lämpimässä tilassa tai heti ajon jälkeen.",
                "<b>Aloita mittaus.</b> Pysäköi auto latauspaikalle ja valitse <b>Mittaus</b>-sivulla <b>Kapasiteettimittaus</b>.",
                "<b>Lepo ennen latausta.</b> Akku lepää 30 minuuttia. Pidä auto hereillä, esimerkiksi Leiriytymistilan avulla.",
                "<b>Lataus.</b> Aseta latausrajaksi 100 % ja aloita tavallinen vaihtovirtalataus, enintään 11 kW. Ohjelma tunnistaa latauksen alun ja lopun itse.",
                "<b>Lepo latauksen jälkeen.</b> Älä käytä autoa 30 minuuttiin. Sen jälkeen ohjelma laskee tuloksen ja tekee raportin.",
            ]),
            ("ul", [
                "Pikalatausta ei käytetä, koska suuri virta lisää häviöitä ja lämpenemistä.",
                "Jos lataus keskeytyy, mittaus odottaa ja jatkuu, kun lataus jatkuu.",
                "Jos autosta ei saada hetkeen tietoja, katkon aikana akkuun mennyt energia täydennetään akunhallinnan energialaskennasta, ja asia merkitään raporttiin.",
                "Ikkunan voi sulkea mittauksen ajaksi. Mittaus jatkuu taustalla, ja sen saa näkyviin avaamalla ohjelman uudelleen.",
            ]),
            ("note", "Kytke kannettava tietokone laturiin. Ohjelma estää tietokoneen lepotilan mittauksen aikana."),
        ],
    },
    {
        "id": "testit", "otsikko": "Mittaustyypit",
        "osat": [
            ("p", "AKVERIssa on kahdeksan mittausta. Ne on ryhmitelty sen mukaan, missä mittaus tehdään. "
                  "Akun kunto prosentteina saadaan kapasiteettimittauksesta, ajotestistä ja täydestä akkutestistä. "
                  "Muut mittaukset kertovat akusta asioita, joita kapasiteetti ei kerro."),
            ("ul", [
                "<b>Pikatarkastus</b> (1–3 min): akunhallinnan kapasiteettiarvio, kennoryhmien jännitteet, lämpötilat ja elinkaaritiedot.",
                "<b>Kapasiteettimittaus</b> (8–14 h): akun kapasiteetti mitattuna latauksen aikana.",
                "<b>Itsepurkaustesti</b> (yön yli): kennoryhmien jännitteiden muutos seisonnassa.",
                "<b>Täysi akkutesti</b> (1–2 päivää): kapasiteetti mitattuna sekä ajossa että latauksessa. Tarkin tulos.",
                "<b>Ajotesti</b> (yksi tai useampi ajokerta): kapasiteetti mitattuna tavallisessa ajossa.",
                "<b>Pika-ajotesti</b> (1–2 h): tarkistaa, vastaako akunhallinnan arvio ajossa mitattua.",
                "<b>Kuormitustesti</b> (noin 10 min): kennoryhmien sisäinen resistanssi kiihdytyksissä.",
                "<b>Pikalataustesti</b> (30–45 min): latausteho ja kennoryhmien tasaisuus pikalaturilla.",
            ]),
            ("note", "Raportti näyttää mitatun kunnon vain, kun mittaus täyttää tarkkuusvaatimuksen: kunnon epävarmuus "
                     "enintään ±3 %-yksikköä ja mittauksen laatu vähintään kohtalainen. Muuten raportti kertoo syyn, "
                     "ja kuntona näytetään Teslan akunhallinnan oma arvio."),
        ],
    },
    {
        "id": "ajotestit", "otsikko": "Ajotesti ja täysi akkutesti",
        "osat": [
            ("p", "Ajotestissä akusta ajon aikana otettu energia luetaan Teslan elinkaaren energialaskureista ja "
                  "varaustila akunhallinnasta. Varaustila luetaan levossa ennen ajoa ja sen jälkeen. Täydessä "
                  "akkutestissä ajoa seuraa lataus täyteen, ja tulos yhdistetään kahdesta riippumattomasta mittauksesta."),
            ("ol", [
                "<b>Lataa akku täyteen</b> edellisenä päivänä. Ajo aloitetaan vähintään 80 %:n varauksesta.",
                "<b>Aloita mittaus</b> pysäköitynä ja pidä auto hereillä lepojakson ajan (15 min).",
                "<b>Aja tavalliseen tapaan.</b> Ajotestissä ajetaan enintään 10 %:n ja täydessä akkutestissä enintään 15 %:n varaukseen. Ohjelma ilmoittaa, kun tavoite on saavutettu.",
                "<b>Ajon voi jakaa useaan kertaan.</b> Kun pysäköit, valitse <b>Jatka myöhemmin</b> ja sulje ohjelma. Seuraavalla ajokerralla kytke sovitin ja valitse Mittaus-sivulla <b>Jatka</b>. Älä lataa autoa välillä.",
                "<b>Pysäköi lopuksi</b> ja anna akun levätä. Täydessä akkutestissä aloita sen jälkeen lataus täyteen kuten kapasiteettimittauksessa.",
            ]),
            ("ul", [
                "Jos autoa ladataan tauon aikana, Teslan latauslaskuri paljastaa sen, ja asia merkitään raporttiin.",
                "Pika-ajotesti on lyhyt ajo, jolla tarkistetaan akunhallinnan arvio. Lyhyen ajon varaustilan muutos ei riitä tarkkaan kuntoprosenttiin, joten pika-ajotesti ei anna omaa kuntoa.",
            ]),
            ("note", "Älä käytä ohjelmaa ajon aikana. Aseta tietokone tai puhelin niin, ettei se liiku ajossa, ja noudata liikennesääntöjä."),
        ],
    },
    {
        "id": "muut_testit", "otsikko": "Kuormitus-, pikalataus- ja itsepurkaustesti",
        "osat": [
            ("p", "<b>Kuormitustesti.</b> Kun akusta otetaan suuri virta, kunkin kennoryhmän jännite laskee sen sisäisen "
                  "resistanssin mukaan. Tee turvallisessa paikassa kuusi reipasta kiihdytystä, esimerkiksi 30–80 km/h. "
                  "Ohjelma laskee kiihdytykset itse ja päättää mittauksen, kun pysäköit. Muita selvästi suurempi "
                  "resistanssi viittaa heikentyneeseen kennoryhmään tai liitokseen. Resistanssi riippuu voimakkaasti "
                  "lämpötilasta ja varaustilasta, joten testi aloitetaan vain vertailukelpoisissa olosuhteissa: varaus "
                  "40–80 %, akun lämpötila 10–30 °C ja kennojen lämpötilaero alle 2 °C. Vaatimukset vastaavat DEKRAn "
                  "akkutestiä. Jos ehto ei täyty, ohjelma kertoo syyn. Kylmän akun voi lämmittää ajamalla tai "
                  "esilämmittämällä auton Tesla-sovelluksesta."),
            ("p", "<b>Pikalataustesti.</b> Aloita alle 30 %:n varauksesta. Navigoi pikalaturille auton navigaattorilla, "
                  "jotta akku esilämmitetään. Anna latauksen jatkua vähintään 80 %:iin. Raporttiin tulee latauskäyrä, "
                  "huipputeho, latausaika 20 → 80 % ja kennoryhmien suurin jännite-ero latauksen aikana. Latausteho "
                  "riippuu myös laturista ja akun lämpötilasta."),
            ("p", "<b>Itsepurkaustesti.</b> Aloita illalla. Auto lepää 30 minuuttia, minkä jälkeen ohjelma lukee "
                  "kaikkien kennoryhmien jännitteet. Valitse <b>Jatka myöhemmin</b>, sulje ohjelma ja anna auton "
                  "nukkua yön yli. Aamulla herätä auto, kytke sovitin ja valitse <b>Jatka</b>. Älä aja tai lataa autoa "
                  "seisonnan aikana."),
            ("p", "<b>LFP-akut</b> (esimerkiksi Model 3 ja Model Y Standard Range): LFP-kennon lepojännite muuttuu "
                  "keskimmäisillä varaustiloilla hyvin vähän. Tee itsepurkaustesti heti täyteen latauksen jälkeen, yli "
                  "90 %:n varauksessa. Muuten raportti kertoo, ettei tulosta voitu mitata luotettavasti."),
            ("note", "Itsepurkaustesti vertaa kennoryhmiä toisiinsa, joten auton oma kulutus ei vaikuta tulokseen. "
                     "Mittauksen havaitsemisraja näkyy raportissa. Mitä pidempi seisonta, sitä pienempi poikkeama havaitaan."),
        ],
    },
    {
        "id": "raportti", "otsikko": "Raportti ja tulosten tulkinta",
        "osat": [
            ("p", "Raportti on kaksiosainen. <b>Pääsivuilla</b> (yleensä 4–6 sivua) ovat akun kunto ja tärkeimmät "
                  "tunnusluvut, tulokset luokkineen, mittauksen tulos kaavioineen ja kennoryhmien jännitteet. Kaikkien "
                  "kennoryhmien jännitteet ovat lisäsivulla taulukkona. "
                  "<b>Teknisessä liitteessä</b> ovat mittauksen vaiheet, mittaustarkkuuden erittely, "
                  "akunhallinnan tiedot, menetelmäkuvaus ja sanasto. Liitteen voi "
                  "jättää pois asetuksista, jolloin asiakas saa vain pääsivut."),
            ("ul", [
                "<b>Akun kunto (SOH)</b> on nykyinen kapasiteetti prosentteina alkuperäisestä. Luokat noudattavat AVILOOn käytäntöä: vähintään 90 % on erinomainen, 80–90 % hyvä ja alle 80 % heikentynyt. Alle 70 % alittaa Teslan akkutakuun rajan.",
                "<b>Kennoryhmien jännite-ero</b> levossa: alle 15 mV erinomainen, alle 30 mV hyvä ja alle 50 mV tyydyttävä. Suurempi ero tai yksittäinen poikkeava ryhmä kannattaa tarkistaa.",
                "Raja-arvot perustuvat käytettyjen sähköautojen akkutestien aineistoon (Generational, noin 10 000 testiä: tyypillinen ero noin 8 mV, yli 50 mV vaatii selvittelyä, yli 100 mV viittaa vikaan) sekä akkujärjestelmien täyden latauksen ohjearvoihin (enintään 30 mV hyväksyttävä, vähintään 50 mV vaatii tasauslatauksen).",
                "<b>Jyrkkä alue ja LFP-akku</b>: alle 20 %:n varauksessa kennojännite muuttuu jyrkästi, joten ero on luonnostaan suurempi. LFP-akun jännite on keskivarauksella lähes tasainen, mutta nousee täyden ja laskee tyhjän lähellä hyvin jyrkästi, joten LFP-akun ero on luonnostaan suurempi myös täyteen ladattuna. Se on akkukemian ominaisuus eikä vika. Näillä alueilla rajat ovat alle 50 mV hyvä ja alle 100 mV tyydyttävä. LFP-akun keskivarauksella pieni ero ei yksin todista tasapainoa, joten luokaksi annetaan enintään hyvä.",
                "<b>Mittaustarkkuus</b> (±) kertoo, kuinka paljon mitattu kapasiteetti voi poiketa todellisesta. Se pienenee, kun lataus aloitetaan matalasta varauksesta ja lepojaksot pidetään täysimittaisina.",
                "<b>Vertailu ajomäärään</b> kertoo, onko kapasiteetin alenema keskimääräinen, pienempi vai suurempi kuin samalla ajomäärällä yleensä.",
            ]),
            ("p", "Raportissa kerrotaan tietojen alkuperä: tiedot luetaan auton omasta akunhallintajärjestelmästä, "
                  "eikä AKVERI muuta niitä. Pikatarkastuksen kunto ja kapasiteetti ovat Teslan akunhallinnan ilmoittamia. "
                  "Kapasiteettimittauksessa ja ajotesteissä tulos perustuu auton omiin jännite- ja virtamittauksiin, "
                  "varaustilaan ja energialaskureihin. "
                  "Raportti kuvaa akun tilaa mittaushetkellä, eikä se ole valmistajan lausunto."),
            ("p", "Jokaisen raportin tiedot voidaan todentaa. Kaikki mittauksen aikana vastaanotetut viestit "
                  "tallennetaan muuttamattomina, ja raporttiin merkitään niiden tarkiste. Mittauksen sivulla "
                  "<b>Tarkista raakadata</b> varmistaa, ettei aineistoa ole muutettu."),
            ("ul", [
                "<b>Mittaajan riippumattomuus</b> valitaan mittausta aloitettaessa, ja sitä voi muuttaa mittauksen sivulla. Riippumaton mittaaja ei ole ajoneuvon kaupan osapuoli eikä sidoksissa siihen. Valinta näkyy raportin etusivulla. Jos mittaat esimerkiksi oman myytävän autosi, valitse <b>Ei riippumaton</b>.",
                "<b>Vastuunrajaus</b> on etusivun alareunassa: raportti kuvaa akun tilaa mittaushetkellä, se ei ole takuu, ja ohjelmiston toimittaja ei vastaa mittauksen suorittamisesta eikä tuloksiin perustuvista päätöksistä.",
                "<b>Testin numero</b> ja sivunumero muodossa <b>Sivu 3/14</b> ovat jokaisen sivun alareunassa, joten irrallinen sivu yhdistyy oikeaan raporttiin ja puuttuva sivu huomataan. Raakadatan tarkiste on teknisessä liitteessä.",
                "<b>Kennoryhmien kuvaaja</b> valitaan asetuksista: <b>ryhmät numerojärjestyksessä</b> (oletus) tai <b>moduulikartta</b>, joka näyttää ryhmät akun moduuleittain, jolloin poikkeavan ryhmän moduuli näkyy suoraan. Moduulikartta on käytössä malleille, joiden moduulijako on varmistettu (Model 3, Model S ja Model X).",
            ]),
        ],
    },
    {
        "id": "puhelin", "otsikko": "Käyttö puhelimella",
        "osat": [
            ("p", "Sovitin on kytketty tietokoneeseen, ja puhelimella seurataan ja ohjataan mittausta. "
                  "Puhelin ja tietokone tarvitsevat yhteisen verkon."),
            ("ol", [
                "Valitse <b>Asetukset</b>-sivulla <b>Salli käyttö puhelimella</b> ja tallenna.",
                "Paina <b>Käynnistä uudelleen</b>. Asetukset-sivulle tulee puhelimen osoite ja suojakoodi.",
                "Avaa osoite puhelimen selaimella. Suojakoodia ei kysytä samalla puhelimella uudelleen.",
                "Jos Windows kysyy palomuurin lupaa, salli yhteys yksityisissä verkoissa.",
            ]),
            ("ul", [
                "<b>Kodin Wi-Fi:</b> tietokone ja puhelin samassa Wi-Fi-verkossa.",
                "<b>Puhelimen yhteyspiste:</b> yhdistä tietokone puhelimen yhteyspisteeseen. Toimii myös asiakkaan luona ilman Wi-Fiä.",
                "<b>Tailscale:</b> jos tietokoneessa on Tailscale, mittausta voi seurata mistä tahansa.",
            ]),
        ],
    },
    {
        "id": "android", "otsikko": "AKVERI Android-puhelimessa",
        "osat": [
            ("p", "Android-sovelluksella koko mittauksen voi tehdä pelkällä puhelimella tai tabletilla. Sovelluksessa "
                  "on samat toiminnot, mittaukset ja raportit kuin tietokoneohjelmassa."),
            ("ol", [
                "<b>USB:</b> kytke OBDLink EX välikaapelilla auton diagnostiikkaliittimeen ja USB-C-sovittimella (OTG) puhelimeen. Kun Android kysyy, saako AKVERI käyttää sovitinta, valitse <b>Salli</b>.",
                "<b>Bluetooth:</b> kytke OBDLink MX+ tai LX autoon ja muodosta pari puhelimen Bluetooth-asetuksista. Salli AKVERIlle lähellä olevien laitteiden käyttö, kun sovellus kysyy.",
                "Paina <b>Yleiskuva</b>-sivulla <b>Yhdistä autoon</b> ja jatka kuten tietokoneella.",
            ]),
            ("ul", [
                "AKVERI toimii taustalla, ja ilmoitusalueella näkyy merkintä <b>AKVERI on käynnissä</b>. Mittaus jatkuu, vaikka näyttö sammuu tai vaihdat toiseen sovellukseen.",
                "Kapasiteettimittaus kestää 8–14 tuntia, joten puhelimen on oltava laturissa. Bluetooth-sovittimella puhelimen voi pitää suoraan laturissa. Koska EX käyttää puhelimen USB-C-portin, tarvitaan sen kanssa OTG-sovitin, jossa on latausportti (USB-C-hubi, jossa lataus läpi eli PD).",
                "Raportit ja varmuuskopiot tallentuvat avattaessa puhelimen <b>Lataukset/AKVERI</b>-kansioon, josta ne voi jakaa sähköpostilla tai viestillä.",
                "Sovellus päivitetään asentamalla uusi versio vanhan päälle. Tiedot säilyvät.",
            ]),
            ("note", "Kaikki USB-C-sovittimet eivät välitä dataa ja latausvirtaa yhtä aikaa. Valitse OTG-tuettu sovitin, jossa on PD-latausportti. Jos EX ei näy, kokeile toista sovitinta tai kaapelia. Lyhyeen pikatarkastukseen riittää tavallinen OTG-sovitin."),
        ],
    },
    {
        "id": "ilmoitukset", "otsikko": "Puhelinilmoitukset",
        "osat": [
            ("p", "Ohjelma voi lähettää puhelimeen ilmoituksen, kun mittauksen vaihe vaihtuu, kun mittaus on valmis "
                  "tai kun mittauksessa on ongelma, esimerkiksi lataus keskeytyy. Ilmoitukset kulkevat ntfy-palvelun "
                  "kautta. Voit käyttää omaa ntfy-palvelinta tai maksutonta ntfy.sh-palvelua."),
            ("ol", [
                "Asenna puhelimeen ntfy-sovellus.",
                "Keksi aiheelle pitkä ja yksilöllinen nimi, esimerkiksi akux-oma-7f3k9, ja tilaa se sovelluksessa.",
                "Kirjoita <b>Asetukset</b>-sivulle aiheen osoite, esimerkiksi https://ntfy.sh/akux-oma-7f3k9, ja valitse ilmoituslajit.",
                "Paina <b>Lähetä testi-ilmoitus</b> ja tarkista, että ilmoitus tulee puhelimeen.",
            ]),
            ("note", "ntfy.sh:n aiheet ovat julkisia kaikille, jotka tietävät aiheen nimen. Käytä vaikeasti arvattavaa nimeä tai omaa palvelinta."),
        ],
    },
    {
        "id": "yllapito", "otsikko": "Päivitys ja varmuuskopiot",
        "osat": [
            ("p", "<b>Päivitys:</b> uusin versio julkaistaan GitHubin Releases-sivulla, jonne pääsee myös "
                  "<b>Ylläpito</b>-sivulta. Windowsissa ladataan ja ajetaan AKVERI-asennus-x.y.z.exe, Androidissa "
                  "asennetaan AKVERI-x.y.z.apk vanhan päälle. Autot, mittaukset, raportit ja asetukset säilyvät."),
            ("p", "<b>Mittaustiedostot:</b> jokainen valmis mittaus tallennetaan automaattisesti mittaustiedostona "
                  "(.akveri) ja PDF-raporttina. Windowsissa oletuskansio on Tiedostot/AKVERI/Mittaukset, Androidissa "
                  "Lataukset/AKVERI. Kansion voi vaihtaa asetuksista. Mittaustiedosto sisältää kaikki mittauksen tiedot "
                  "ja raakadatan, ja sen voi avata millä tahansa laitteella, jolle AKVERI on asennettu, kohdasta "
                  "<b>Mittaukset → Avaa mittaustiedosto</b>. Myös aiempien versioiden .akux-tiedostot avautuvat."),
            ("p", "<b>Varmuuskopio:</b> ohjelma tekee varmuuskopion automaattisesti kerran viikossa ja säilyttää "
                  "viisi uusinta. Voit tehdä varmuuskopion myös itse ja tallentaa sen esimerkiksi muistitikulle. "
                  "Palautuksessa nykyiset tiedot siirretään ensin talteen, joten mitään ei menetetä."),
            ("p", "<b>Laaduntarkistus</b> tarkistaa ohjelmatiedostot, tietokannan, levytilan, sovittimen, viestien "
                  "purun, mittauslaskennan, raportin muodostuksen ja kaikkien tallennettujen mittausten raakadatan. "
                  "Aja tarkistus päivityksen jälkeen ja aina, jos ohjelma toimii oudosti."),
        ],
    },
    {
        "id": "ongelmat", "otsikko": "Ongelmatilanteet",
        "osat": [
            ("ul", [
                "<b>Sovitinta ei löydy:</b> irrota ja kytke USB-kaapeli uudelleen ja paina Päivitä portit. Jos sovitin ei vieläkään näy, asenna FTDI:n VCP-ajuri valmistajan sivuilta (ftdichip.com).",
                "<b>Väylä on hiljaa:</b> auto on lepotilassa. Herätä auto avaamalla ovi tai käynnistämällä ilmastointi.",
                "<b>Akun tiedot puuttuvat yhteystestistä:</b> paina <b>Kartoita väylä</b>. Jos liitännässä liikkuu vain muutama viesti, kuten nopeus ja virtatila, sovitin on kytketty jalkatilan liitäntään. Kytke se diagnostiikkaliittimeen välikaapelilla.",
                "<b>Puhelin ei saa yhteyttä:</b> tarkista, että puhelin ja tietokone ovat samassa verkossa ja että Windowsin palomuuri sallii yhteyden.",
                "<b>Ohjelma ei käynnisty:</b> aja asennus uudelleen. Tiedot säilyvät.",
            ]),
        ],
    },
]

SANASTO = [
    ("Brutto", "Akun koko energiasisältö, jonka akunhallinta ilmoittaa (täyden akun energia). Sisältää suojavaran."),
    ("Netto", "Käytettävissä oleva energia: brutto vähennettynä akunhallinnan suojavaralla."),
    ("Akun kunto (SOH)", "Akun nykyinen kapasiteetti prosentteina alkuperäisestä kapasiteetista."),
    ("Kapasiteetti", "Energiamäärä, jonka täysi akku sisältää, kilowattitunteina (kWh). Raportissa kapasiteetti on bruttoarvo."),
    ("Käytettävä energia", "Sama kuin nettokapasiteetti: kapasiteetti vähennettynä suojavaralla. Tämä energia on ajossa käytettävissä."),
    ("Suojavara", "Akunhallinnan varaama energia, jota ei anneta käyttöön. Se suojaa akkua syväpurkaukselta. Teslan termi on energy buffer."),
    ("Kennoryhmä", "Rinnan kytkettyjen kennojen ryhmä. Teslan akuissa on tavallisesti 84, 96 tai 106 sarjaan kytkettyä ryhmää."),
    ("Jännite-ero", "Suurimman ja pienimmän kennoryhmän jännitteen ero. Pieni ero kertoo tasaisesti varautuneesta akusta."),
    ("Lepojännite", "Kennon jännite, kun akusta ei ole hetkeen otettu eikä siihen ole ladattu virtaa."),
    ("Akunhallinta (BMS)", "Akun ohjausjärjestelmä, joka valvoo kennoja ja laskee akun varaustilan ja energian."),
    ("Varaustila", "Akun varaus prosentteina. Raportissa käytetään kennoryhmien keskiarvoa, joka sisältää suojavaran."),
    ("Sisäinen resistanssi", "Akun sisäinen vastus. Siinä syntyy latauksessa lämpöä, joka ei varastoidu akkuun."),
    ("Epävarmuus", "Arvio siitä, kuinka paljon mitattu tulos voi poiketa todellisesta arvosta."),
    ("Tarkiste", "Raakadatasta laskettu tunniste, jonka avulla voidaan todentaa, ettei aineistoa ole muutettu."),
    ("Elinkaaren energialaskurit", "Akunhallinnan laskurit, jotka kertovat akusta otetun ja siihen ladatun energian koko akun käyttöiän ajalta."),
    ("Itsepurkautuminen", "Kennoryhmän varauksen hidas väheneminen seisonnassa. Muita nopeampi itsepurkautuminen viittaa sisäiseen vuotoon."),
    ("Havaitsemisraja", "Pienin poikkeama, jonka mittaus pystyy luotettavasti erottamaan mittauskohinasta."),
]
SANASTO.sort(key=lambda x: x[0].lower())


def as_html() -> list[dict]:
    out = []
    for sec in OHJE:
        html = []
        for kind, body in sec["osat"]:
            if kind == "p":
                html.append(f"<p>{body}</p>")
            elif kind == "note":
                html.append(f'<div class="notice">{body}</div>')
            else:
                tag = "ol" if kind == "ol" else "ul"
                html.append(f"<{tag}>" + "".join(f"<li>{x}</li>" for x in body) + f"</{tag}>")
        out.append({"id": sec["id"], "otsikko": sec["otsikko"], "html": "".join(html)})
    out.append({"id": "sanasto", "otsikko": "Sanasto",
                "html": "<dl class='gloss'>" + "".join(f"<dt>{a}</dt><dd>{b}</dd>" for a, b in SANASTO) + "</dl>"})
    return out


def build_pdf(path, settings=None):
    """Käyttöohje PDF-muodossa."""
    from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import A4
    from . import NIMI, VERSIO
    from .report import ST, LINE, PANEL, INK, MUTED  # rekisteröi myös fontit

    def footer(c, d):
        c.saveState()
        c.setFont("Inter", 7)
        c.setFillColor(MUTED)
        c.drawString(18 * mm, 10 * mm, f"{NIMI} {VERSIO} · Käyttöohje")
        c.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Sivu {d.page}")
        c.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=f"{NIMI} – käyttöohje", author=NIMI)
    E = [Paragraph(f"{NIMI}", ST["h1"]), Paragraph("Käyttöohje", ST["sub"]), Spacer(1, 4 * mm),
         Paragraph(f"Versio {VERSIO}", ST["small"]), Spacer(1, 8 * mm)]
    E.append(Paragraph("Sisältö", ST["h3"]))
    for i, sec in enumerate(OHJE, 1):
        E.append(Paragraph(f"{i}. {sec['otsikko']}", ST["body"]))
    E.append(Paragraph(f"{len(OHJE) + 1}. Sanasto", ST["body"]))
    E.append(PageBreak())
    for i, sec in enumerate(OHJE, 1):
        block = [Paragraph(f"{i}. {sec['otsikko']}", ST["h2"])]
        for kind, body in sec["osat"]:
            if kind == "p":
                block.append(Paragraph(body, ST["body"]))
                block.append(Spacer(1, 2 * mm))
            elif kind == "note":
                t = Table([[Paragraph(body, ST["smallink"])]], colWidths=[A4[0] - 36 * mm])
                t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                       ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
                block += [t, Spacer(1, 2 * mm)]
            else:
                items = [ListItem(Paragraph(x, ST["body"]), leftIndent=14) for x in body]
                block.append(ListFlowable(items, bulletType="1" if kind == "ol" else "bullet",
                                          start="1" if kind == "ol" else None, bulletFontName="Inter",
                                          bulletFormat="%s." if kind == "ol" else None,
                                          bulletFontSize=9, leftIndent=14,
                                          bulletColor=INK if kind == "ol" else MUTED))
                block.append(Spacer(1, 2 * mm))
        E.append(KeepTogether(block[:3]))
        E += block[3:]
        E.append(Spacer(1, 5 * mm))
    E.append(Paragraph(f"{len(OHJE) + 1}. Sanasto", ST["h2"]))
    rows = [[Paragraph(a, ST["cellb"]), Paragraph(b, ST["cell"])] for a, b in SANASTO]
    t = Table(rows, colWidths=[48 * mm, A4[0] - 36 * mm - 48 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    E.append(t)
    doc.build(E, onFirstPage=footer, onLaterPages=footer)
    return path
