"""Käyttöohje. Sama sisältö näytetään ohjelman Ohjeet-sivulla ja ladattavana PDF:nä."""
from __future__ import annotations

OHJE = [
    {
        "id": "aloitus", "otsikko": "Aloitus",
        "osat": [
            ("p", "Akux mittaa Tesla Model 3:n ja Model Y:n ajoakun kunnon ja kapasiteetin ja tekee tuloksista "
                  "raportin, jonka voi antaa ostajalle, asiakkaalle tai pitää itsellä. Ohjelma lukee tiedot "
                  "auton akunhallinnasta OBDLink-sovittimella."),
            ("ol", [
                "Avaa <b>Asetukset</b> ja täytä yrityksen tiedot, mittaajan nimi ja logo. Tiedot näkyvät jokaisessa raportissa.",
                "Kytke OBDLink-sovitin auton OBD-liitäntään ja USB-kaapelilla tietokoneeseen.",
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
            ("p", "Eurooppalaisessa Model 3:ssa ja Model Y:ssä OBD-liitäntä on kuljettajan jalkatilassa ohjauspyörän "
                  "vasemmalla puolella. Jos autossa ei ole liitäntää jalkatilassa, käytä Teslan "
                  "diagnostiikkaliittimeen sopivaa välikaapelia."),
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
                "<b>Alkuperäinen kapasiteetti</b> kannattaa syöttää käsin vain, jos auto ei ilmoita sitä itse.",
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
        "id": "raportti", "otsikko": "Raportti ja tulosten tulkinta",
        "osat": [
            ("p", "Raportin ensimmäisellä sivulla on yhteenveto, tärkeimmät tunnusluvut ja arviot luokkineen. "
                  "Seuraavilla sivuilla ovat mittauksen yksityiskohdat, kennoryhmien jännitteet, akunhallinnan tiedot, "
                  "menetelmäkuvaus ja sanasto."),
            ("ul", [
                "<b>Akun kunto (SOH)</b> on nykyinen kapasiteetti prosentteina alkuperäisestä. Vähintään 90 % on erinomainen, 85–90 % hyvä, 80–85 % tyydyttävä ja 70–80 % heikentynyt.",
                "<b>Kennoryhmien jännite-ero</b> levossa: alle 15 mV erinomainen, alle 30 mV hyvä ja alle 50 mV tyydyttävä. Suurempi ero tai yksittäinen poikkeava ryhmä kannattaa tarkistaa.",
                "<b>Epävarmuus</b> kertoo, kuinka paljon mitattu kapasiteetti voi poiketa todellisesta. Se pienenee, kun lataus aloitetaan matalasta varauksesta ja lepojaksot pidetään täysimittaisina.",
                "<b>Vertailu ajomäärään</b> kertoo, onko kapasiteetin alenema keskimääräinen, pienempi vai suurempi kuin samalla ajomäärällä yleensä.",
            ]),
            ("p", "Raportissa kerrotaan tietojen alkuperä: tiedot luetaan auton omasta akunhallintajärjestelmästä, "
                  "eikä Akux muuta niitä. Pikatarkastuksen kunto ja kapasiteetti ovat auton omia arvioita. "
                  "Kapasiteettimittauksessa Akux laskee tuloksen auton omien jännite- ja virta-antureiden mittauksista. "
                  "Raportti kuvaa akun tilaa mittaushetkellä, eikä se ole valmistajan lausunto."),
            ("p", "Jokaisen raportin tiedot voidaan todentaa. Kaikki mittauksen aikana vastaanotetut viestit "
                  "tallennetaan muuttamattomina, ja raporttiin merkitään niiden tarkiste. Mittauksen sivulla "
                  "<b>Tarkista raakadata</b> varmistaa, ettei aineistoa ole muutettu."),
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
        "id": "android", "otsikko": "Akux Android-puhelimessa",
        "osat": [
            ("p", "Android-sovelluksella koko mittauksen voi tehdä pelkällä puhelimella tai tabletilla. Sovelluksessa "
                  "on samat toiminnot, mittaukset ja raportit kuin tietokoneohjelmassa."),
            ("ol", [
                "Kytke OBDLink EX auton OBD-liitäntään ja USB-C-sovittimella (OTG) puhelimeen.",
                "Kun Android kysyy, saako Akux käyttää sovitinta, valitse <b>Salli</b>. Voit valita, että Akux avautuu aina, kun sovitin kytketään.",
                "Paina <b>Yleiskuva</b>-sivulla <b>Yhdistä autoon</b> ja jatka kuten tietokoneella.",
            ]),
            ("ul", [
                "Akux toimii taustalla, ja ilmoitusalueella näkyy merkintä <b>Akux on käynnissä</b>. Mittaus jatkuu, vaikka näyttö sammuu tai vaihdat toiseen sovellukseen.",
                "Pidä puhelin laturissa pitkän kapasiteettimittauksen ajan. Auton USB-liitäntä käy hyvin.",
                "Raportit ja varmuuskopiot tallentuvat avattaessa puhelimen <b>Lataukset/Akux</b>-kansioon, josta ne voi jakaa sähköpostilla tai viestillä.",
                "Sovellus päivitetään asentamalla uusi versio vanhan päälle. Tiedot säilyvät.",
            ]),
            ("note", "Kaikki USB-C-sovittimet eivät välitä virtaa ja dataa oikein. Käytä OTG-tuettua sovitinta. Jos sovitin ei näy, kokeile toista sovitinta tai kaapelia."),
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
                  "<b>Ylläpito</b>-sivulta. Windowsissa ladataan ja ajetaan Akux-asennus-x.y.z.exe, Androidissa "
                  "asennetaan Akux-x.y.z.apk vanhan päälle. Autot, mittaukset, raportit ja asetukset säilyvät."),
            ("p", "<b>Mittaustiedostot:</b> jokainen valmis mittaus tallennetaan automaattisesti mittaustiedostona "
                  "(.akux) ja PDF-raporttina. Windowsissa oletuskansio on Tiedostot/Akux/Mittaukset, Androidissa "
                  "Lataukset/Akux. Kansion voi vaihtaa asetuksista. Mittaustiedosto sisältää kaikki mittauksen tiedot "
                  "ja raakadatan, ja sen voi avata missä tahansa Akux-versiossa ja millä tahansa laitteella kohdasta "
                  "<b>Mittaukset → Avaa mittaustiedosto</b>."),
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
                "<b>Jokin tieto ei näy yhteystestissä:</b> odota minuutti. Jos tieto ei ilmesty, kyseinen liitäntä ei välitä sitä, ja tarvitaan Teslan diagnostiikkaliittimeen kytkettävä välikaapeli.",
                "<b>Puhelin ei saa yhteyttä:</b> tarkista, että puhelin ja tietokone ovat samassa verkossa ja että Windowsin palomuuri sallii yhteyden.",
                "<b>Ohjelma ei käynnisty:</b> aja asennus uudelleen. Tiedot säilyvät.",
            ]),
        ],
    },
]

SANASTO = [
    ("Akun kunto (SOH)", "Akun nykyinen kapasiteetti prosentteina alkuperäisestä kapasiteetista."),
    ("Kapasiteetti", "Energiamäärä, jonka täysi akku sisältää, kilowattitunteina (kWh)."),
    ("Käytettävä energia", "Kapasiteetti vähennettynä puskurilla. Tämä energia on ajossa käytettävissä."),
    ("Puskuri", "Akunhallinnan varaama energia, jota ei näytetä käyttäjälle ja joka suojaa akkua syväpurkaukselta."),
    ("Kennoryhmä", "Rinnan kytkettyjen kennojen ryhmä. Model 3:n ja Model Y:n akussa on 96 tai 106 sarjaan kytkettyä ryhmää."),
    ("Jännite-ero", "Suurimman ja pienimmän kennoryhmän jännitteen ero. Pieni ero kertoo tasaisesti varautuneesta akusta."),
    ("Lepojännite", "Kennon jännite, kun akusta ei ole hetkeen otettu eikä siihen ole ladattu virtaa."),
    ("Akunhallinta (BMS)", "Akun ohjausjärjestelmä, joka valvoo kennoja ja laskee akun varaustilan ja energian."),
    ("Varaustila", "Akun varaus prosentteina. Raportissa käytetään kennoryhmien keskiarvoa, joka sisältää puskurin."),
    ("Sisäinen resistanssi", "Akun sisäinen vastus. Siinä syntyy latauksessa lämpöä, joka ei varastoidu akkuun."),
    ("Epävarmuus", "Arvio siitä, kuinka paljon mitattu tulos voi poiketa todellisesta arvosta."),
    ("Tarkiste", "Raakadatasta laskettu tunniste, jonka avulla voidaan todentaa, ettei aineistoa ole muutettu."),
]


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
