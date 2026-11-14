"""Käyttöohje. Sama sisältö näytetään ohjelman Ohjeet-sivulla ja ladattavana PDF:nä."""
from __future__ import annotations

# Alustakohtaiset osat: osan kolmas kenttä tai listan kohdan toinen kenttä on "pc" (tietokone) tai "android".
# Ilman merkintää osa näytetään kaikilla alustoilla.
PC, AND = "pc", "android"

OHJE = [
    {
        "id": "aloitus", "otsikko": "Aloitus",
        "osat": [
            ("p", "AKVERI lukee sähköauton ajoakun kunnon ja kapasiteetin suoraan auton akunhallinnasta ja kokoaa tiedot "
                  "raportiksi, jonka voi antaa ostajalle, asiakkaalle tai pitää itsellä. Kaikki mittausarvot ovat "
                  "auton akunhallinnan luovuttamia. AKVERI ei käytä omia antureitaan eikä muuta arvoja."),
            ("p", "<b>Tuetut autot</b>"),
            ("ul", [
                "<b>Tesla</b>: Model 3 ja Model Y kaikki vuosimallit ja akkutyypit sekä Model S ja Model X.",
                "<b>Hyundai ja Kia</b>: Ioniq Electric, Kona Electric, e-Niro, e-Soul, Ioniq 5, Ioniq 6 ja EV6.",
                "<b>Nissan Leaf</b>: 24, 30, 40 ja 62 kWh.",
                "<b>Volkswagen-konsernin MEB-alusta</b>: Volkswagen ID.3, ID.4 ja ID.5, Škoda Enyaq, Audi Q4 e-tron ja Cupra Born.",
                "<b>MG</b>: MG4 Electric, MG5 Electric ja MG ZS EV.",
            ]),
            ("p", "Merkkien erot on koottu kohtaan <b>Automerkit</b>."),
            ("ol", [
                "Avaa <b>Asetukset</b> ja valitse käyttötapa. Yksityisessä käytössä raporttiin tulee nimesi, yrityksellä yrityksen tiedot ja logo.",
                ("Kytke OBDLink-sovitin auton diagnostiikkaliittimeen ja USB-kaapelilla tietokoneeseen. Bluetooth-mallit (MX+ ja LX) paritetaan ensin Windowsin Bluetooth-asetuksista.", PC),
                ("Kytke OBDLink-sovitin auton diagnostiikkaliittimeen. USB-mallin (EX) kanssa tarvitaan USB-C-sovitin (OTG). Bluetooth-mallit (MX+ ja LX) paritetaan ensin puhelimen Bluetooth-asetuksista.", AND),
                "Herätä auto ja paina <b>Yleiskuva</b>-sivulla <b>Yhdistä autoon</b>.",
                "Lisää auto. Ohjelma lukee valmistenumeron autosta ja tunnistaa mallin.",
                "Tee autolle pikatarkastus. Sen jälkeen voit tehdä kapasiteettimittauksen.",
            ]),
            ("note", "Ohjelma ainoastaan lukee tietoja. Se ei lähetä autolle mitään eikä muuta auton asetuksia."),
        ],
    },
    {
        "id": "yhdistaminen", "otsikko": "Yhdistäminen autoon",
        "osat": [
            ("p", "Akun tiedot luetaan auton OBD-liitännästä OBDLink-sovittimella. Useimmissa merkeissä sovitin kytketään "
                  "suoraan kuljettajan jalkatilan OBD-liitäntään. Teslassa tarvitaan lisäksi mallille sopiva "
                  "OBD-välikaapeli (haaroituskaapeli). Auton sivun kohta <b>Kytkentä autoon</b> kertoo juuri sen auton liittimen."),
            ("ul", [
                "<b>Tuetut sovittimet:</b> OBDLink EX ja SX (USB) sekä OBDLink MX+ ja LX (Bluetooth). AKVERI käyttää "
                "OBDLinkin suodatusta, jolla vain akun tiedot välitetään. Tavalliset ELM327-sovittimet eivät pysy "
                "auton väylän liikenteen perässä, joten AKVERI ei hyväksy niitä.",
                ("<b>Bluetooth:</b> kytke sovitin autoon ja herätä auto. Paina MX+:n painiketta ja muodosta pari "
                 "Windowsin Bluetooth-asetuksista. Sen jälkeen sovitin näkyy AKVERIn sovitinlistassa merkinnällä "
                 "Bluetooth. Listalla näkyvät vain OBDLink-sovittimet, eivät muut paritetut laitteet.", PC),
                ("<b>Bluetooth:</b> kytke sovitin autoon ja herätä auto. Paina MX+:n painiketta ja muodosta pari "
                 "puhelimen Bluetooth-asetuksista. Salli AKVERIlle lähellä olevien laitteiden käyttö, kun sovellus "
                 "kysyy. Listalla näkyvät vain OBDLink-sovittimet, eivät muut paritetut laitteet.", AND),
                "OBDLink CX käyttää Bluetooth Low Energy -yhteyttä, jota AKVERI ei vielä tue.",
            ]),
            ("ol", [
                ("Kytke sovitin auton liitäntään ja tietokoneeseen.", PC),
                ("Kytke sovitin auton liitäntään. USB-sovitin kytketään puhelimeen USB-C-sovittimella (OTG). Kun Android kysyy, saako AKVERI käyttää sovitinta, valitse <b>Salli</b>.", AND),
                "Herätä auto. Teslassa riittää oven avaaminen tai ilmastoinnin käynnistys auton sovelluksesta. Muissa merkeissä kytke auto päälle (READY) tai virta päälle. Sovitin saa virtaa vain, kun auto on hereillä.",
                "Valitse <b>Yleiskuva</b>-sivulla sovitin ja tarvittaessa auton malli ja paina <b>Yhdistä autoon</b>.",
                "Odota, että <b>Yhteystesti</b> näyttää kaikki tarvittavat tiedot vihreinä. Tämä kestää yleensä muutaman sekunnin.",
            ]),
            ("p", "Ensimmäisellä kytkentäkerralla Windows asentaa sovittimen ajurin itse, kun tietokone on verkossa. "
                  "Jos sovitin ei näy listassa, odota hetki ja paina <b>Päivitä portit</b>.", PC),
            ("p", "<b>Teslan diagnostiikkaliitin</b>"),
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
            ("note", "Teslan Model 3:n ja Model Y:n jalkatilassa on myös tavallisen näköinen OBD-liitäntä. Se välittää vain "
                     "muutaman tiedon, kuten nopeuden ja virtatilan, mutta ei akun tietoja. Yhteystesti ja väylän "
                     "kartoitus kertovat tämän suoraan."),
            ("note", "Välikaapeli kytketään kaapelin valmistajan ohjeen mukaan, eikä auton johtoja leikata tai muuteta. "
                     "Kytke ja irrota kaapeli auton ollessa pysäköitynä. Verhoilupaneelien irrotus ja kaapelin "
                     "kytkentä tehdään omalla vastuulla."),
        ],
    },
    {
        "id": "hyundai_kia", "otsikko": "Automerkit",
        "osat": [
            ("p", "Kaikkien merkkien mittaukset ja raportit tehdään samalla tavalla. Akunhallinnat kuitenkin ilmoittavat "
                  "eri tietoja eri tarkkuudella, ja se näkyy raportissa. Teslan akunhallinta lähettää tietonsa "
                  "väylälle itse. Muiden merkkien akunhallinta vastaa kyselyihin, joten AKVERI kysyy tiedot vuorotellen. "
                  "Kyselyt ovat pelkkiä lukupyyntöjä; ne eivät muuta auton asetuksia. Muissa kuin Teslassa auton malli "
                  "valitaan Yleiskuvan Yhdistä-kohdan Auto-luettelosta ennen yhdistämistä, koska valmistenumerosta ei "
                  "voi päätellä akun kokoa."),
            ("p", "<b>Tesla</b>"),
            ("ul", [
                "Akunhallinta ilmoittaa täyden akun energian, suojavaran ja akun elinkaaren energialaskurit. "
                "Kennoryhmien jännitteet 1 mV:n tarkkuudella.",
                "Vuosien 2012–2021 Model S ja 2015–2021 Model X eivät ilmoita akun alkuperäistä kapasiteettia. Syötä se "
                "auton tietoihin, niin kunto lasketaan siitä.",
            ]),
            ("p", "<b>Hyundai ja Kia</b>"),
            ("ul", [
                "Tuetut mallit: Ioniq Electric 28 ja 38 kWh, Kona Electric 39 ja 64 kWh, Kia e-Niro 39 ja 64 kWh, "
                "e-Soul 64 kWh sekä E-GMP-alustan Ioniq 5, Ioniq 6 ja Kia EV6.",
                "Akunhallinta vastaa vain, kun auto on käynnistetty (READY tai virta päällä) tai latautuu. Kun mittaus "
                "pyytää lepojakson loppuarvoja, käynnistä auto hetkeksi.",
                "Akunhallinta ilmoittaa oman kuntoarvionsa (SOH) prosentteina, ei täyden akun energiaa. AKVERI laskee "
                "energia-arvion kuntoarviosta ja mallin alkuperäisestä kapasiteetista. Mitattu kapasiteetti "
                "(kapasiteettimittaus, ajotesti) on tästä riippumaton.",
                "Suojavaraa ei ilmoiteta, joten raportissa näytetään käytettävän energian sijaan akunhallinnan kuntoarvio.",
                "Kennojännitteet ilmoitetaan 20 mV:n tarkkuudella. Pienet jännite-erot eivät erotu, ja kennoluokituksen "
                "raja on suhteutettu tähän tarkkuuteen. Itsepurkaustestiä ei siksi voi tehdä.",
            ]),
            ("p", "<b>Nissan Leaf</b>"),
            ("ul", [
                "Akunhallinta ilmoittaa kennojännitteet 1 mV:n tarkkuudella, joten itsepurkaustesti on mahdollinen.",
                "Akunhallinta ilmoittaa jäljellä olevan kapasiteetin ampeeritunteina ja 40 ja 62 kWh:n akuissa myös "
                "kuntoprosenttina. 24 ja 30 kWh:n akuissa kunto lasketaan ampeeritunneista ja uuden akun "
                "ampeerituntimäärästä (likiarvo).",
                "Elinkaaren energialaskureita ei ole. Kapasiteettimittaus perustuu jännitteen ja virran mittaukseen.",
                "Virran suunta varmistetaan varaustilan muutoksesta (noin 0,5 %-yksikköä ajoa tai latausta). Mittauksen "
                "lataus- tai ajovaihe alkaa, kun suunta on varmistunut.",
                "24 ja 30 kWh:n akkujen kennokemia (LMO-pohjainen) poikkeaa NMC-kennoista. Lepojännitteeseen perustuvat "
                "arviot ovat näissä likimääräisiä.",
            ]),
            ("p", "<b>Volkswagen-konsernin MEB (ID.3, ID.4, ID.5, Enyaq, Q4 e-tron, Born)</b>"),
            ("ul", [
                "Kennojännitteet 1 mV:n tarkkuudella. Kennot luetaan yksi kerrallaan, joten koko akun kennokierros "
                "kestää noin 10 sekuntia.",
                "Akunhallinta ilmoittaa varaustilan 0,4 %:n portain. Kapasiteettimittaus perustuu energian mittaukseen, "
                "joten porrastus vaikuttaa tulokseen vain vähän.",
                "Akunhallinnan kuntoarvio (SOH) on vain uudemmissa ohjelmistoversioissa. Muuten käytetään akun "
                "suurinta energiasisältöä.",
                "Kennomäärä (84, 96 tai 108) tarkistetaan autosta ensimmäisellä kennokierroksella.",
                "ID.7 ja 86 kWh:n akku eivät ole vielä mukana.",
            ]),
            ("p", "<b>MG (MG4 Electric, MG5 Electric ja MG ZS EV)</b>"),
            ("ul", [
                "Tuetut mallit: MG4 Electric 51, 64 ja 77 kWh, MG5 Electric 50,3 ja 61,1 kWh sekä MG ZS EV 44,5 kWh "
                "(2019–2021), 51 kWh ja 72,6 kWh (2022 alkaen).",
                "Akunhallinta ilmoittaa kennojännitteet lohkoittain: kunkin lohkon matalimman ja korkeimman kennon "
                "jännitteen. Raportissa on lohkojen ääriarvot, ja jännite-ero on koko akun korkeimman ja matalimman "
                "kennon erotus.",
                "Itsepurkaustestiä ei voi tehdä, koska yksittäisten kennojen jännitteitä ei ilmoiteta.",
                "Elinkaaren energialaskureita ei ole. Kapasiteettimittaus perustuu jännitteen ja virran mittaukseen.",
            ]),
            ("note", "Ajomäärään perustuva vertailu tehdään vain malleille, joista on riittävä vertailuaineisto. "
                     "Muilla malleilla raportissa ei ole tätä kohtaa."),
        ],
    },
    {
        "id": "krediitit", "otsikko": "Krediitit ja raportin tarkistus",
        "osat": [
            ("p", "Mittaukset maksetaan krediiteillä. Kunkin mittauksen hinta näkyy ennen aloitusta. Krediitit ostetaan "
                  "Android-sovelluksen <b>Krediitit</b>-sivulla Google Playn kautta. Krediitit veloitetaan, kun mittaus "
                  "aloitetaan.", PC),
            ("p", "Mittaukset maksetaan krediiteillä. Kunkin mittauksen hinta näkyy ennen aloitusta. Krediitit ostetaan "
                  "<b>Krediitit</b>-sivulla Google Playn kautta. Krediitit veloitetaan, kun mittaus aloitetaan.", AND),
            ("ul", [
                "<b>Raportin tunnus:</b> jokainen mittaus saa tunnuksen (esimerkiksi AK-7H2QK-M4XPC). Tunnus ja QR-koodi ovat "
                "raportin ensimmäisellä sivulla. QR-koodi avaa sivun akveri.fi/v/tunnus, jolla raportin vastaanottaja näkee "
                "rekisteröidyt tulokset ja voi verrata auton valmistenumeroa.",
                "<b>Rekisteröinti:</b> valmis mittaus rekisteröidään akveri.fi-palveluun automaattisesti, ja tulos näkyy heti "
                "rekisteröinnin jälkeen. Jos verkkoyhteyttä ei ole, rekisteröinti tehdään heti, kun yhteys palaa. Mittauksen "
                "aloittaminen vaatii verkkoyhteyden.",
                "<b>Järkevyystarkistus:</b> jos mittauksen tulos on mahdoton, esimerkiksi auton malli on valittu väärin, "
                "raporttia ei rekisteröidä ja krediitit palautetaan automaattisesti. Syy näkyy mittauksen sivulla.",
                "<b>Keskeytys:</b> jos mittaus keskeytyy heti alussa, sen krediitit palautuvat automaattisesti. "
                "Jos mittaus keskeytyy myöhemmin AKVERIsta johtuvasta syystä, lähetä mittauksen sivulta hyvityspyyntö.",
                "<b>Akun kunto ennen mittausta:</b> akun kunto ja kapasiteetti näkyvät mittauksen aikana ja raportissa, eivät "
                "yhteyden muodostamisen jälkeen ilman mittausta.",
                "<b>Uudelleenlaskenta:</b> kun AKVERI päivittyy, aiemman mittauksen voi laskea uudelleen ilman uutta krediittiä. "
                "Tarkistussivun tulos päivittyy samalla.",
            ]),
            ("p", "<b>Mitä tietoja akveri.fi-palveluun lähetetään</b>"),
            ("ul", [
                "Satunnainen tilitunnus, jolla krediitit pidetään tallessa. Tiliin ei liitetä nimeä, sähköpostia eikä puhelinnumeroa.",
                "Google Play -oston tunniste, jolla palvelu tarkistaa maksun Googlelta. Maksukortin tietoja AKVERI ei näe.",
                "Mittauksen yhteenveto: mittauksen tyyppi ja aika, auton merkki ja malli, valmistenumeron kolme ensimmäistä ja kuusi "
                "viimeistä merkkiä (koko numero vain tiivisteenä), mittarilukema, akun kunto ja kapasiteetti, mittauksen "
                "suorittaja, ohjelman versio ja raakadatan tarkiste.",
                "Hyvityspyynnössä kirjoittamasi kuvaus ja mittauksen tapahtumaloki.",
                "Anonyymi tilastorivi ohjelmiston kehittämiseen: merkki, malli, vuosimalli, akkutyyppi, mittaustyyppi, kuukausi, "
                "mittarilukema tuhansina kilometreinä ja tulokset. Rivillä ei ole tunnisteita, eikä sitä voi yhdistää raporttiin.",
            ]),
            ("p", "Rekisterikilpeä, auton omistajaa, lisätietoja, yrityksen tietoja, kuvia eikä mittausdataa lähetetä. Ne pysyvät "
                  "vain tällä laitteella ja mittaustiedostossa. Tarkemmin: akveri.fi/tietosuoja."),
            ("p", "<b>Tietosuoja</b>"),
            ("ul", [
                "<b>Lataa tietoni</b> (Krediitit): akveri.fi-palvelun kaikki tämän tilin tiedot yhtenä tiedostona.",
                "<b>Poista raportti palvelusta</b> (mittauksen sivu): raporttia ei voi sen jälkeen tarkistaa. Mittaus ja raportti "
                "säilyvät laitteella.",
                "<b>Poista tili</b> (Krediitit): tili ja sen krediitit poistuvat. Voit poistaa samalla rekisteröityjen raporttien "
                "tiedot. Krediittien kirjanpito säilyy kirjanpitolain edellyttämän ajan ilman muita tunnisteita.",
            ]),
            ("note", "Tili on tallennettu ohjelman tietoihin. Varmuuskopio sisältää tilin, joten kun palautat varmuuskopion uuteen "
                     "laitteeseen, krediitit siirtyvät mukana. Säilytä varmuuskopio huolellisesti."),
        ],
    },
    {
        "id": "autot", "otsikko": "Autot",
        "osat": [
            ("p", "Jokainen mitattava auto tallennetaan kerran. Ohjelma tunnistaa valmistenumerosta merkin, mallin, "
                  "vuosimallin ja valmistustehtaan ja valitsee niiden perusteella oikean mallipohjan. Jos valmistenumero "
                  "ei riitä akun koon tunnistamiseen, malli valitaan luettelosta."),
            ("p", "Ensimmäisessä mittauksessa ohjelma lukee akunhallinnasta akun tiedot, kuten kennoryhmien määrän ja "
                  "akun tyypin, ja tallentaa ne autolle. Jatkossa ohjelma käyttää näitä tietoja suoraan."),
            ("ul", [
                "<b>Käyttöönottopäivä</b> tarvitaan akkutakuun voimassaolon laskemiseen. Sen löytää rekisteriotteesta.",
                "<b>Alkuperäinen kapasiteetti</b> kannattaa syöttää käsin vain, jos ohjelma pyytää sitä. Näin on mallissa, "
                "jonka akunhallinta ei ilmoita sitä itse.",
                "<b>Rekisterinumero</b> näkyy raportin etusivulla. Sitä ei voi lukea autosta, joten se syötetään käsin.",
                "<b>Auton kuva</b> on vapaaehtoinen. Lisää se auton sivulla, niin kuva näkyy raportin etusivulla. Puhelimella otetun kuvan asento korjataan automaattisesti.",
                "Auton sivulla näkyvät kaikki sen mittaukset ja akun kunnon kehitys.",
            ]),
        ],
    },
    {
        "id": "pikatarkastus", "otsikko": "Pikatarkastus",
        "osat": [
            ("p", "Pikatarkastus kestää 1–3 minuuttia. Se lukee akunhallinnan arvion akun nykyisestä kunnosta ja "
                  "kapasiteetista, kennoryhmien jännitteet, lämpötilat ja auton ilmoittamat elinkaaritiedot. "
                  "Pikatarkastus sopii esimerkiksi kauppatilanteeseen."),
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
                "<b>Lepo ennen latausta.</b> Akku lepää 30 minuuttia. Pidä auto hereillä, jotta sovitin saa virtaa. Ohjelma kertoo mittauksen aikana, miten se tehdään juuri tässä autossa.",
                "<b>Lataus.</b> Aseta latausrajaksi 100 % ja aloita tavallinen vaihtovirtalataus, enintään 11 kW. Ohjelma tunnistaa latauksen alun ja lopun itse.",
                "<b>Lepo latauksen jälkeen.</b> Älä käytä autoa 30 minuuttiin. Sen jälkeen ohjelma laskee tuloksen ja tekee raportin.",
            ]),
            ("ul", [
                "Pikalatausta ei käytetä, koska suuri virta lisää häviöitä ja lämpenemistä.",
                "Jos lataus keskeytyy, mittaus odottaa ja jatkuu, kun lataus jatkuu.",
                "Jos autosta ei saada hetkeen tietoja, katkon aikana akkuun mennyt energia täydennetään akunhallinnan tiedoista, ja asia merkitään raporttiin.",
                ("Ikkunan voi sulkea mittauksen ajaksi. Mittaus jatkuu taustalla, ja sen saa näkyviin avaamalla ohjelman uudelleen.", PC),
                ("Mittaus jatkuu taustalla, vaikka näyttö sammuu tai vaihdat toiseen sovellukseen.", AND),
            ]),
            ("note", "Kytke kannettava tietokone laturiin. Ohjelma estää tietokoneen lepotilan mittauksen aikana.", PC),
            ("note", "Mittaus kestää 8–14 tuntia, joten pidä puhelin laturissa koko ajan. Katso kohta <b>Puhelimen käyttö</b>.", AND),
        ],
    },
    {
        "id": "testit", "otsikko": "Mittaustyypit",
        "osat": [
            ("p", "AKVERIssa on kahdeksan mittausta. Ne on ryhmitelty sen mukaan, missä mittaus tehdään. "
                  "Akun kunto prosentteina saadaan kapasiteettimittauksesta, ajotestistä ja täydestä akkutestistä. "
                  "Muut mittaukset kertovat akusta asioita, joita kapasiteetti ei kerro. Mittaukset, joita auton "
                  "akunhallinnan tiedoilla ei voi tehdä, eivät ole valittavissa."),
            ("ul", [
                "<b>Pikatarkastus</b> (1–3 min): akunhallinnan kuntoarvio, kennoryhmien jännitteet, lämpötilat ja elinkaaritiedot.",
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
                     "ja kuntona näytetään auton akunhallinnan oma arvio."),
        ],
    },
    {
        "id": "ajotestit", "otsikko": "Ajotesti ja täysi akkutesti",
        "osat": [
            ("p", "Ajotestissä mitataan ajon aikana akusta otettu energia ja varaustilan muutos. Energia luetaan "
                  "akunhallinnan elinkaaren energialaskureista, tai jos autossa niitä ei ole, se lasketaan akun "
                  "jännitteestä ja virrasta. Varaustila luetaan levossa ennen ajoa ja sen jälkeen. Täydessä "
                  "akkutestissä ajoa seuraa lataus täyteen, ja tulos yhdistetään kahdesta riippumattomasta mittauksesta."),
            ("ol", [
                "<b>Lataa akku täyteen</b> edellisenä päivänä. Ajo aloitetaan vähintään 80 %:n varauksesta.",
                "<b>Aloita mittaus</b> pysäköitynä ja pidä auto hereillä lepojakson ajan (15 min).",
                "<b>Aja tavalliseen tapaan.</b> Ajotestissä ajetaan enintään 10 %:n ja täydessä akkutestissä enintään 15 %:n varaukseen. Ohjelma ilmoittaa, kun tavoite on saavutettu.",
                "<b>Ajon voi jakaa useaan kertaan.</b> Kun pysäköit, valitse <b>Jatka myöhemmin</b> ja sulje ohjelma. Seuraavalla ajokerralla kytke sovitin ja valitse Mittaus-sivulla <b>Jatka</b>. Älä lataa autoa välillä.",
                "<b>Pysäköi lopuksi</b> ja anna akun levätä. Täydessä akkutestissä aloita sen jälkeen lataus täyteen kuten kapasiteettimittauksessa.",
            ]),
            ("ul", [
                "Jos autoa ladataan tauon aikana ja auto ilmoittaa latauslaskurinsa, ohjelma huomaa latauksen, ja asia merkitään raporttiin.",
                "Pika-ajotesti on lyhyt ajo, jolla tarkistetaan akunhallinnan arvio. Lyhyen ajon varaustilan muutos ei riitä tarkkaan kuntoprosenttiin, joten pika-ajotesti ei anna omaa kuntoa.",
            ]),
            ("note", "Älä käytä ohjelmaa ajon aikana. Aseta tietokone niin, ettei se liiku ajossa, ja noudata liikennesääntöjä.", PC),
            ("note", "Älä käytä sovellusta ajon aikana. Aseta puhelin telineeseen tai paikkaan, jossa se ei liiku ajossa, ja noudata liikennesääntöjä.", AND),
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
                  "40–80 %, akun lämpötila 10–30 °C ja kennojen lämpötilaero alle 2 °C. Jos ehto ei täyty, ohjelma "
                  "kertoo syyn. Kylmän akun voi lämmittää ajamalla tai esilämmittämällä auton."),
            ("p", "<b>Pikalataustesti.</b> Aloita alle 30 %:n varauksesta. Jos auto esilämmittää akun pikalatausta varten, "
                  "valitse pikalaturi auton navigaattorista. Anna latauksen jatkua vähintään 80 %:iin. Raporttiin tulee "
                  "latauskäyrä, huipputeho, latausaika 20 → 80 % ja kennoryhmien suurin jännite-ero latauksen aikana. "
                  "Latausteho riippuu myös laturista ja akun lämpötilasta."),
            ("p", "<b>Itsepurkaustesti.</b> Aloita illalla. Auto lepää 30 minuuttia, minkä jälkeen ohjelma lukee "
                  "kaikkien kennoryhmien jännitteet. Valitse <b>Jatka myöhemmin</b>, sulje ohjelma ja anna auton "
                  "seistä yön yli. Aamulla herätä auto, kytke sovitin ja valitse <b>Jatka</b>. Älä aja tai lataa autoa "
                  "seisonnan aikana. Testi vaatii, että akunhallinta ilmoittaa kennojännitteet 1 mV:n tarkkuudella."),
            ("p", "<b>LFP-akut</b> (esimerkiksi osa Tesla Model 3- ja Model Y -malleista sekä MG4 ja MG ZS EV 51 kWh): "
                  "LFP-kennon lepojännite muuttuu keskimmäisillä varaustiloilla hyvin vähän. Tee itsepurkaustesti heti "
                  "täyteen latauksen jälkeen, yli 90 %:n varauksessa. Muuten raportti kertoo, ettei tulosta voitu mitata "
                  "luotettavasti."),
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
                  "akunhallinnan tiedot, menetelmäkuvaus ja sanasto."),
            ("ul", [
                "<b>Akun kunto (SOH)</b> on nykyinen kapasiteetti prosentteina alkuperäisestä. Luokat: vähintään 90 % on erinomainen, 80–90 % hyvä ja alle 80 % heikentynyt. Raportti vertaa kuntoa auton merkin akkutakuun rajaan, joka on yleensä 70 %.",
                "<b>Kennoryhmien jännite-ero</b> levossa: alle 15 mV erinomainen, alle 30 mV hyvä ja alle 50 mV tyydyttävä. Suurempi ero tai yksittäinen poikkeava ryhmä kannattaa tarkistaa.",
                "Raja-arvot perustuvat käytettyjen sähköautojen laajaan akkutestiaineistoon (tyypillinen ero noin 8 mV, yli 50 mV vaatii selvittelyä, yli 100 mV viittaa vikaan) sekä akkujärjestelmien täyden latauksen ohjearvoihin (enintään 30 mV hyväksyttävä, vähintään 50 mV vaatii tasauslatauksen).",
                "<b>Jyrkkä alue ja LFP-akku</b>: alle 20 %:n varauksessa kennojännite muuttuu jyrkästi, joten ero on luonnostaan suurempi. LFP-akun jännite on keskivarauksella lähes tasainen, mutta nousee täyden ja laskee tyhjän lähellä hyvin jyrkästi, joten LFP-akun ero on luonnostaan suurempi myös täyteen ladattuna. Se on akkukemian ominaisuus eikä vika. Näillä alueilla rajat ovat alle 50 mV hyvä ja alle 100 mV tyydyttävä. LFP-akun keskivarauksella pieni ero ei yksin todista tasapainoa, joten luokaksi annetaan enintään hyvä.",
                "<b>Mittaustarkkuus</b> (±) kertoo, kuinka paljon mitattu kapasiteetti voi poiketa todellisesta. Se pienenee, kun lataus aloitetaan matalasta varauksesta ja lepojaksot pidetään täysimittaisina.",
                "<b>Vertailu ajomäärään</b> kertoo, onko kapasiteetin alenema keskimääräinen, pienempi vai suurempi kuin samalla ajomäärällä yleensä. Se tehdään malleille, joista on riittävä vertailuaineisto.",
            ]),
            ("p", "Raportissa kerrotaan tietojen alkuperä: tiedot luetaan auton omasta akunhallintajärjestelmästä, "
                  "eikä AKVERI muuta niitä. Pikatarkastuksen kunto ja kapasiteetti ovat auton akunhallinnan ilmoittamia. "
                  "Kapasiteettimittauksessa ja ajotesteissä tulos perustuu auton omiin jännite- ja virtamittauksiin, "
                  "varaustilaan ja energialaskureihin. "
                  "Raportti kuvaa akun tilaa mittaushetkellä, eikä se ole valmistajan lausunto."),
            ("p", "Jokaisen raportin tiedot voidaan todentaa. Kaikki mittauksen aikana vastaanotetut viestit "
                  "tallennetaan muuttamattomina, ja raporttiin merkitään niiden tarkiste. Mittauksen sivulla "
                  "<b>Tarkista raakadata</b> varmistaa, ettei aineistoa ole muutettu."),
            ("ul", [
                "<b>Tulosten alkuperä</b> kerrotaan jokaisen raportin etusivulla: tulokset on luettu auton akunhallinnasta, ja AKVERI on laskenut ja varmentanut ne. Mittauksen suorittaja ei voi muuttaa tuloksia.",
                "<b>Mittauksen suorittaja</b> (nimi tai yritys) kirjoitetaan mittausta aloitettaessa. Se näkyy raportissa ja akveri.fi:n tarkistussivulla, eikä sitä voi muuttaa raportin rekisteröinnin jälkeen.",
                "<b>Vastuunrajaus</b> on etusivun alareunassa: raportti kuvaa akun tilaa mittaushetkellä, se ei ole takuu, ja ohjelmiston toimittaja ei vastaa mittauksen suorittamisesta eikä tuloksiin perustuvista päätöksistä.",
                "<b>Testin numero</b> ja sivunumero muodossa <b>Sivu 3/14</b> ovat jokaisen sivun alareunassa, joten irrallinen sivu yhdistyy oikeaan raporttiin ja puuttuva sivu huomataan. Raakadatan tarkiste on teknisessä liitteessä.",
            ]),
        ],
    },
    {
        "id": "android", "otsikko": "AKVERI Android-puhelimessa", "alusta": PC,
        "osat": [
            ("p", "Android-sovelluksella koko mittauksen voi tehdä pelkällä puhelimella tai tabletilla. Sovelluksessa "
                  "on samat toiminnot, mittaukset ja raportit kuin tietokoneohjelmassa. Krediitit ostetaan sovelluksessa."),
            ("ul", [
                "USB-sovitin (EX) kytketään puhelimeen USB-C-sovittimella (OTG). Bluetooth-sovitin (MX+, LX) paritetaan puhelimen Bluetooth-asetuksista.",
                "Kapasiteettimittauksessa puhelimen on oltava laturissa koko mittauksen ajan.",
            ]),
        ],
    },
    {
        "id": "puhelin", "otsikko": "Puhelimen käyttö", "alusta": AND,
        "osat": [
            ("ol", [
                "<b>USB:</b> kytke OBDLink EX auton diagnostiikkaliittimeen ja USB-C-sovittimella (OTG) puhelimeen. Kun Android kysyy, saako AKVERI käyttää sovitinta, valitse <b>Salli</b>.",
                "<b>Bluetooth:</b> kytke OBDLink MX+ tai LX autoon ja muodosta pari puhelimen Bluetooth-asetuksista. Salli AKVERIlle lähellä olevien laitteiden käyttö, kun sovellus kysyy.",
                "Paina <b>Yleiskuva</b>-sivulla <b>Yhdistä autoon</b>.",
            ]),
            ("ul", [
                "AKVERI toimii taustalla, ja ilmoitusalueella näkyy merkintä <b>AKVERI on käynnissä</b>. Mittaus jatkuu, vaikka näyttö sammuu tai vaihdat toiseen sovellukseen.",
                "Kapasiteettimittaus kestää 8–14 tuntia, joten puhelimen on oltava laturissa. Bluetooth-sovittimen kanssa puhelimen voi pitää suoraan laturissa. Koska EX käyttää puhelimen USB-C-portin, tarvitaan sen kanssa OTG-sovitin, jossa on latausportti (USB-C-hubi, jossa lataus läpi eli PD).",
                "Raportit ja mittaustiedostot tallentuvat puhelimen <b>Lataukset/AKVERI</b>-kansioon, josta ne voi jakaa sähköpostilla tai viestillä.",
            ]),
            ("note", "Kaikki USB-C-sovittimet eivät välitä dataa ja latausvirtaa yhtä aikaa. Valitse OTG-tuettu sovitin, jossa on PD-latausportti. Jos EX ei näy, kokeile toista sovitinta tai kaapelia. Lyhyeen pikatarkastukseen riittää tavallinen OTG-sovitin."),
        ],
    },
    {
        "id": "yllapito", "otsikko": "Päivitys ja varmuuskopiot",
        "osat": [
            ("p", "<b>Päivitys:</b> uusi asennusohjelma ajetaan vanhan päälle. Autot, mittaukset, raportit, asetukset "
                  "ja krediitit säilyvät.", PC),
            ("p", "<b>Päivitys:</b> Google Play päivittää AKVERIn. Autot, mittaukset, raportit, asetukset ja krediitit "
                  "säilyvät.", AND),
            ("p", "<b>Mittaustiedostot:</b> jokainen valmis mittaus tallennetaan automaattisesti mittaustiedostona "
                  "(.akveri) ja PDF-raporttina kansioon Tiedostot/AKVERI/Mittaukset. Kansion voi vaihtaa Asetukset-sivulla. "
                  "Mittaustiedosto sisältää kaikki mittauksen tiedot ja raakadatan, ja sen voi avata millä tahansa "
                  "laitteella, jolle AKVERI on asennettu, kohdasta <b>Mittaukset → Avaa mittaustiedosto</b>. Myös "
                  "aiempien versioiden .akux-tiedostot avautuvat.", PC),
            ("p", "<b>Mittaustiedostot:</b> jokainen valmis mittaus tallennetaan automaattisesti mittaustiedostona "
                  "(.akveri) ja PDF-raporttina puhelimen Lataukset/AKVERI-kansioon. Mittaustiedosto sisältää kaikki "
                  "mittauksen tiedot ja raakadatan, ja sen voi avata millä tahansa laitteella, jolle AKVERI on "
                  "asennettu, kohdasta <b>Mittaukset → Avaa mittaustiedosto</b>. Myös aiempien versioiden "
                  ".akux-tiedostot avautuvat.", AND),
            ("p", "<b>Varmuuskopio:</b> ohjelma tekee varmuuskopion automaattisesti kerran viikossa ja säilyttää "
                  "viisi uusinta. Voit tehdä varmuuskopion myös itse <b>Asetukset</b>-sivulla ja tallentaa sen "
                  "esimerkiksi muistitikulle. Palautuksessa nykyiset tiedot siirretään ensin talteen, joten mitään ei menetetä.", PC),
            ("p", "<b>Varmuuskopio:</b> sovellus tekee varmuuskopion automaattisesti kerran viikossa ja säilyttää "
                  "viisi uusinta. Voit tehdä varmuuskopion myös itse <b>Asetukset</b>-sivulla ja jakaa sen esimerkiksi "
                  "omaan sähköpostiisi tai pilvitallennukseen. Palautuksessa nykyiset tiedot siirretään ensin talteen, "
                  "joten mitään ei menetetä.", AND),
            ("note", "Ota varmuuskopio ennen kuin poistat sovelluksen tai vaihdat puhelinta. Sovelluksen poistaminen poistaa "
                     "myös sen tiedot ja krediittitilin.", AND),
        ],
    },
    {
        "id": "ongelmat", "otsikko": "Ongelmatilanteet",
        "osat": [
            ("ul", [
                ("<b>Sovitinta ei löydy:</b> irrota ja kytke USB-kaapeli uudelleen ja paina Päivitä portit. Jos sovitin ei vieläkään näy, asenna FTDI:n VCP-ajuri valmistajan sivuilta (ftdichip.com).", PC),
                ("<b>Sovitinta ei löydy:</b> USB-sovittimessa irrota ja kytke OTG-sovitin uudelleen ja valitse Salli, kun Android kysyy lupaa. Bluetooth-sovittimessa tarkista, että sovitin on paritettu ja että AKVERIlla on lupa lähellä oleviin laitteisiin.", AND),
                "<b>Auto ei vastaa:</b> auto on lepotilassa. Teslassa herätä auto avaamalla ovi tai käynnistämällä ilmastointi. Muissa merkeissä kytke auto päälle (READY) tai virta päälle.",
                "<b>Akun tiedot puuttuvat yhteystestistä:</b> tarkista, että Auto-luettelosta on valittu oikea malli. Teslassa paina <b>Kartoita väylä</b>: jos liitännässä liikkuu vain muutama viesti, kuten nopeus ja virtatila, sovitin on kytketty jalkatilan liitäntään. Kytke se diagnostiikkaliittimeen välikaapelilla.",
                ("<b>Ohjelma ei käynnisty:</b> aja asennus uudelleen. Tiedot säilyvät.", PC),
                ("<b>Sovellus ei käynnisty:</b> sulje sovellus kokonaan ja avaa se uudelleen. Jos ongelma jatkuu, päivitä sovellus Google Playssa.", AND),
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
    ("Suojavara", "Akunhallinnan varaama energia, jota ei anneta käyttöön. Se suojaa akkua syväpurkaukselta."),
    ("Kennoryhmä", "Rinnan kytkettyjen kennojen ryhmä tai yksittäinen kenno, merkistä riippuen. Sähköauton akussa on tavallisesti 84–192 sarjaan kytkettyä ryhmää."),
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


def _alusta(alusta: str | None) -> str:
    return AND if alusta == "android" else PC


def osiot(alusta: str | None = None) -> list[dict]:
    """Ohjeen osiot alustalle suodatettuina: (laji, sisältö) ja listat merkkijonoina."""
    a = _alusta(alusta)
    out = []
    for sec in OHJE:
        if sec.get("alusta") not in (None, a):
            continue
        osat = []
        for osa in sec["osat"]:
            kind, body = osa[0], osa[1]
            if len(osa) > 2 and osa[2] != a:
                continue
            if isinstance(body, list):
                body = [x[0] if isinstance(x, tuple) else x for x in body
                        if not (isinstance(x, tuple) and x[1] != a)]
            osat.append((kind, body))
        out.append({"id": sec["id"], "otsikko": sec["otsikko"], "osat": osat})
    return out


def as_html(alusta: str | None = None) -> list[dict]:
    out = []
    for sec in osiot(alusta):
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


def build_pdf(path, settings=None, alusta=None):
    from . import kielet  # noqa: PLC0415  ohje ohjelman kielellä

    def _P(text, *a, **kw):
        return Paragraph(kielet.t_html(text), *a, **kw)
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
        c.drawString(18 * mm, 10 * mm, f"{NIMI} {VERSIO} · " + kielet.t("Käyttöohje"))
        c.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Sivu {d.page}")
        c.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=f"{NIMI} – käyttöohje", author=NIMI)
    E = [_P(f"{NIMI}", ST["h1"]), _P("Käyttöohje", ST["sub"]), Spacer(1, 4 * mm),
         _P(f"Versio {VERSIO}", ST["small"]), Spacer(1, 8 * mm)]
    E.append(_P("Sisältö", ST["h3"]))
    OSIOT = osiot(alusta)
    for i, sec in enumerate(OSIOT, 1):
        E.append(_P(f"{i}. {sec['otsikko']}", ST["body"]))
    E.append(_P(f"{len(OSIOT) + 1}. Sanasto", ST["body"]))
    E.append(PageBreak())
    for i, sec in enumerate(OSIOT, 1):
        block = [_P(f"{i}. {sec['otsikko']}", ST["h2"])]
        for kind, body in sec["osat"]:
            if kind == "p":
                block.append(_P(body, ST["body"]))
                block.append(Spacer(1, 2 * mm))
            elif kind == "note":
                t = Table([[_P(body, ST["smallink"])]], colWidths=[A4[0] - 36 * mm])
                t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                       ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
                block += [t, Spacer(1, 2 * mm)]
            else:
                items = [ListItem(_P(x, ST["body"]), leftIndent=14) for x in body]
                block.append(ListFlowable(items, bulletType="1" if kind == "ol" else "bullet",
                                          start="1" if kind == "ol" else None, bulletFontName="Inter",
                                          bulletFormat="%s." if kind == "ol" else None,
                                          bulletFontSize=9, leftIndent=14,
                                          bulletColor=INK if kind == "ol" else MUTED))
                block.append(Spacer(1, 2 * mm))
        E.append(KeepTogether(block[:3]))
        E += block[3:]
        E.append(Spacer(1, 5 * mm))
    E.append(_P(f"{len(OSIOT) + 1}. Sanasto", ST["h2"]))
    rows = [[_P(a, ST["cellb"]), _P(b, ST["cell"])] for a, b in SANASTO]
    t = Table(rows, colWidths=[48 * mm, A4[0] - 36 * mm - 48 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    E.append(t)
    doc.build(E, onFirstPage=footer, onLaterPages=footer)
    return path
