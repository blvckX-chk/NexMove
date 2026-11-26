"""Aucun nom de personne réelle dans le dépôt, et aucun nom complet dans un exemple montré.

Le défaut constaté : le bot disait à TOUS ses utilisateurs
« Une erreur ? Écris-la simplement, ex. « mon nom c'est <prénom nom> » »
avec le nom d'une vraie utilisatrice, et le dépôt est public. Le nom était là depuis
la v3.59 — personne ne l'avait vu, parce que personne ne cherchait.

Ce fichier ne peut évidemment pas lister les vraies personnes. Il interdit la FORME :
un prénom et un nom accolés dans un exemple destiné à être lu par quelqu'un. Un exemple
n'a jamais besoin d'un nom complet — « ton nom exact » dit la même chose sans risque.
"""
import pathlib
import re

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent

# Un nom complet présenté comme exemple : « mon nom c'est X Y », « nom : X Y », « je m'appelle X Y ».
_NOM_EXEMPLE_RE = re.compile(
    r"(nom\s+c'est|nom\s*:\s*|je\s+m'appelle|appelle[- ]moi|prénom\s*:\s*)\s*"
    r"([A-ZÀ-Ý][a-zà-ÿ]{2,}\s+[A-ZÀ-Ý][a-zà-ÿ]{2,})")

# Placeholders admis : reconnaissables comme tels par n'importe quel lecteur francophone.
_PLACEHOLDERS = {"marie dupont", "jean dupont", "dupont marie", "nom exemple", "prenom nom"}


def _fichiers_livres():
    """Ce qui part en production ou se lit publiquement. Les tests sont contrôlés à part."""
    for p in sorted((RACINE / "api").glob("*.py")):
        yield p
    for p in sorted((RACINE / "web").glob("*.html")):
        yield p


@pytest.mark.parametrize("chemin", list(_fichiers_livres()), ids=lambda p: p.name)
def test_aucun_nom_complet_en_exemple(chemin):
    txt = chemin.read_text(encoding="utf-8")
    trouves = [m.group(2) for m in _NOM_EXEMPLE_RE.finditer(txt)
               if m.group(2).lower() not in _PLACEHOLDERS]
    assert not trouves, (
        f"{chemin.name} : nom complet utilisé en exemple → {trouves}. "
        "Un exemple n'a pas besoin d'un nom de personne : écris « ton nom exact ». "
        "Le dépôt est public, et un vrai nom s'y retrouve pour toujours.")


def test_les_tests_eux_memes_nutilisent_quun_placeholder():
    """Une donnée de test finit toujours par être lue par quelqu'un."""
    mauvais = []
    for p in sorted((RACINE / "tests").glob("*.py")):
        if p.name == pathlib.Path(__file__).name:
            continue
        for m in _NOM_EXEMPLE_RE.finditer(p.read_text(encoding="utf-8")):
            if m.group(2).lower() not in _PLACEHOLDERS:
                mauvais.append(f"{p.name} → {m.group(2)}")
    assert not mauvais, (
        "Noms non-placeholder dans les tests : " + " · ".join(mauvais)
        + ". Utilise « Marie Dupont », qui ne désigne personne.")


def test_aucune_adresse_ni_numero_personnel_en_exemple():
    """Les coordonnées de l'équipe sont publiques et voulues ; celles d'un utilisateur, non."""
    perso = re.compile(r"\b[\w.+-]+@(?:gmail|yahoo|hotmail|outlook|icloud)\.[a-z]{2,}\b", re.I)
    for chemin in _fichiers_livres():
        txt = chemin.read_text(encoding="utf-8")
        trouves = [a for a in perso.findall(txt) if "exemple" not in a.lower() and "toi@" not in a.lower()]
        assert not trouves, f"{chemin.name} : adresse personnelle en clair → {trouves}"
