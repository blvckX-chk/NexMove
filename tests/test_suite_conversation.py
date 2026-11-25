"""Défauts observés sur une vraie conversation WhatsApp du 25 novembre 2026.

C'est le premier fichier de tests entièrement écrit à partir de messages réels plutôt
que de cas imaginés. Les quatre défauts :

1. Après cinq formations en hacking, « il y a des certificats à la fin ? » a relancé une
   recherche AVEC LA QUESTION comme requête. Résultat affiché comme une réponse : des
   certifications Google Analytics et HubSpot Marketing.
2. « est-ce qu'il reste des programmes ouverts au Canada auxquels je peux postuler ? »
   partait en /postuler avec une cible vide, parce que le mot « postuler » suffisait.
3. « tout ce qui peut me faire voyager » n'avait aucune route.
4. La synthèse de /formations vouvoyait, alors que tout le reste du bot tutoie.
"""
import os
import sys
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
import main  # noqa: E402


def _route(msg: str):
    cmd = main._free_text_to_command(msg.lower(), msg)
    return cmd.split()[0] if cmd else None


LISTE = {"last_liste": {"type": "formations", "sujet": "formation gratuite en hacking",
                        "titres": ["Hack The Box Academy", "TryHackMe Intro"], "ts": "2026-11-25"}}


# ── 1. Une question posée juste après une liste porte sur CETTE liste ──

@pytest.mark.parametrize("msg", [
    "il y a des certificats à la fin ?",          # la phrase exacte observée
    "c'est vraiment gratuit ?",
    "et pour les débutants ?",
    "combien de temps ça prend ?",
    "lequel tu me conseilles ?",
    "ça se fait en ligne ?",
])
def test_question_apres_une_liste_est_une_suite(msg):
    assert main._refers_to_prior_list(msg.lower(), dict(LISTE)) is True, msg


@pytest.mark.parametrize("msg", [
    "cherche moi plutôt des formations en comptabilité",
    "donne moi des offres d'emploi à cotonou",
    "trouve des bourses pour le canada",
    "montre moi autre chose",
])
def test_une_vraie_nouvelle_recherche_nest_pas_une_suite(msg):
    assert main._refers_to_prior_list(msg.lower(), dict(LISTE)) is False, msg


def test_sans_liste_precedente_rien_ne_se_declenche():
    """Le mécanisme ne doit pas s'activer au premier message de la conversation."""
    assert main._refers_to_prior_list("il y a des certificats à la fin ?", {}) is False


def test_une_phrase_longue_reintroduit_son_sujet():
    long = ("je voudrais savoir si tu peux me trouver un stage en logistique à lomé "
            "pour le mois de janvier prochain s'il te plaît")
    assert main._refers_to_prior_list(long, dict(LISTE)) is False


# ── 2. « postuler » dans une subordonnée ne demande pas de candidater ──

def test_question_sur_ce_qui_existe_ne_part_pas_en_postuler():
    msg = ("est ce quil reste des programmes ouvert au canada pour les informaticiens "
           "auquel j epeux toujours postuler ?")
    assert _route(msg) == "/canada", _route(msg)


@pytest.mark.parametrize("msg", [
    "y a-t-il encore des bourses auxquelles je peux postuler ?",
    "quels sont les programmes ouverts où postuler ?",
    "est-ce que c'est encore ouvert pour postuler ?",
])
def test_autres_questions_de_disponibilite(msg):
    assert _route(msg) != "/postuler", f"« {msg} » part encore en /postuler"


@pytest.mark.parametrize("msg,cible", [
    ("postuler à Campus France", "Campus France"),
    ("je veux postuler chez Orange", "Orange"),
    ("candidater au master de Dakar", "master de Dakar"),
])
def test_une_vraie_demande_de_candidature_marche_toujours(msg, cible):
    cmd = main._free_text_to_command(msg.lower(), msg)
    assert cmd.startswith("/postuler"), cmd
    assert cible.lower() in cmd.lower(), cmd


# ── 3. L'envie de partir est une intention de mobilité ──

@pytest.mark.parametrize("msg", [
    "tout ce qui peux me faire voyager",
    "je veux partir d'ici",
    "je veux quitter le pays",
    "je veux aller à l'étranger",
    "je voudrais m'expatrier",
])
def test_envie_de_partir_route_vers_la_mobilite(msg):
    assert _route(msg) == "/mobilite", msg


def test_voyager_sans_intention_ne_route_pas():
    """« mon frère voyage beaucoup » n'est pas une demande."""
    assert _route("mon frère voyage beaucoup") != "/mobilite"


# ── 4. Le bot tutoie, y compris dans les synthèses générées ──

def test_le_conseil_vouvoyant_est_converti():
    reel = ("Commencez par les certifications gratuites listées ci-dessus pour enrichir "
            "rapidement votre CV. Une fois ces bases acquises, vous pourrez envisager "
            "des certifications payantes.")
    out = main._tutoie(reel)
    assert "vous" not in out.lower()
    assert "votre" not in out.lower()
    assert out.startswith("Commence "), out          # la majuscule est gardée
    assert "ton CV" in out and "tu pourras" in out


def test_un_texte_deja_tutoye_nest_pas_touche():
    t = "Vise d'abord les parcours gratuits, tu gagneras du temps."
    assert main._tutoie(t) == t


def test_un_vouvoiement_non_convertible_nest_pas_massacre():
    """Un ton formel se pardonne ; une conjugaison cassée non.

    Si une seule forme résiste, on rend le texte d'origine plutôt qu'un mélange des deux.
    """
    t = "Veuillez nous contacter par l'intermédiaire de votre conseiller référent."
    assert main._tutoie(t) == t


def test_le_tutoiement_est_applique_aux_syntheses():
    """La règle est dans le code, pas seulement dans l'invite — une invite n'est pas un garde-fou."""
    src = (RACINE / "api" / "main.py").read_text(encoding="utf-8")
    assert src.count("_tutoie(r['conseil'])") >= 3, "une synthèse échappe encore au garde-fou"
