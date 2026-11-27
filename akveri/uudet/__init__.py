"""Uusien merkkien kyselyalustat, joita ohjelma ei vielä käytä.

Tiedot ovat tiedostossa akveri/data/uudet/alustat.json. Tämä paketti muuntaa ne samaan muotoon kuin nykyiset
kyselyalustat (hkmc, leaf, meb, mg): kyselyt, vastausten purku ja vastausten tuottaminen testejä varten.
Liittäminen ohjelmaan tehdään vasta, kun alustasta on mittaustiedosto oikeasta autosta.
"""
from .moottori import Alusta, alustat, hae  # noqa: F401
