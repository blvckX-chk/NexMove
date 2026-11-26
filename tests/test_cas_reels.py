"""Situations réelles du terrain béninois et ouest-africain.

Les cas d'évaluation précédents portaient sur le routage : quelle commande pour quelle
phrase. Ceux-ci portent sur des SITUATIONS — celles qu'un conseiller d'orientation
rencontre vraiment ici, et où se tromper coûte autre chose qu'une mauvaise réponse.

Le plus important est le premier : l'escroquerie à l'avance de frais. Elle est partout
dans ce marché (« paie et je te garantis le visa »), et un conseiller qui parle de départ
à l'étranger sans jamais en parler échoue au moment où il sert le plus. Comme la détresse,
c'est déterministe : jamais confié au modèle.
"""
import asyncio
import os
import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
import main  # noqa: E402
import orientation as ori  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _mute(monkeypatch):
    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main, "deliver_text", _noop)
    monkeypatch.setattr(main, "send_message", _noop)


def _sess(**kw):
    base = {"user_id": "u-cas", "channel": "telegram", "chat_id": "u-cas", "username": "T",
            "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}
    base.update(kw)
    return base


# ── CAS 1 · « Paie et je te garantis le visa » ────────────────────────────────────────────
# Le plus fréquent, et celui qui ruine des familles entières.

@pytest.mark.parametrize("message", [
    "un gars me demande 150 000 F pour me faire le visa canada",
    "on me demande de l'argent pour avoir un emploi en france",
    "le monsieur me réclame 80 000 francs pour le dossier",
    "je dois verser 50000 fcfa avant qu'il envoie le contrat",
    "il dit que le visa est garanti à 100%",
    "emploi garanti sans entretien au canada",
    "j'ai un contact à l'ambassade qui peut arranger ça",
])
def test_une_arnaque_declenche_une_alerte(message):
    assert ori.detecte_arnaque(message) is True, message


@pytest.mark.parametrize("message", [
    "quelqu'un vend des faux diplômes, ça vaut le coup ?",
    "acheter un visa schengen c'est possible ?",
    "je pense passer par la libye pour aller en europe",
])
def test_une_voie_illegale_declenche_une_alerte(message):
    """Y compris la route et la mer : des gens y meurent chaque semaine."""
    assert ori.detecte_arnaque(message) is True, message


@pytest.mark.parametrize("message", [
    "combien coûtent les frais Campus France",
    "je dois payer les frais de scolarité en janvier",
    "le rendez-vous TLS Contact coûte combien",
    "j'ai payé mon loyer 40000 f ce mois",
    "la caution du logement est de 100000 francs",
    "le timbre fiscal pour le passeport",
    "mon employeur me demande mon diplôme",
    "je cherche un emploi au canada",
])
def test_les_frais_officiels_ne_declenchent_rien(message):
    """Les frais légitimes existent vraiment : crier au loup les rendrait suspects."""
    assert ori.detecte_arnaque(message) is False, message


def test_l_alerte_donne_la_regle_qui_protege():
    msg, _ = _run(main.process_text_message(_sess(), "on me demande 200 000 F pour le visa"))
    assert "JAMAIS" in msg, "la règle doit être énoncée sans ambiguïté"
    assert "reçu" in msg.lower() or "guichet" in msg.lower(), "il faut dire où payer légitimement"
    assert "Campus France" in msg, "il faut nommer les guichets officiels"
    assert "?" in msg or "Dis-moi" in msg, "il faut proposer la suite, pas seulement avertir"


def test_l_alerte_sort_des_questionnaires_en_cours():
    """Comme la détresse : une alerte ne peut pas attendre la fin d'un test d'orientation."""
    s = _sess(orient_test={"qi": 2, "answers": ["R", "I"], "complet": False})
    msg, s = _run(main.process_text_message(s, "on me demande 100 000 F pour le visa"))
    assert "arnaque" in msg.lower()
    assert "orient_test" not in s


def test_l_alerte_ne_passe_jamais_par_le_modele(monkeypatch):
    async def _interdit(*a, **k):
        raise AssertionError("une alerte arnaque ne doit jamais dépendre du modèle")
    monkeypatch.setattr(main, "call_groq", _interdit)
    msg, _ = _run(main.process_text_message(_sess(), "je dois payer 300000 f pour avoir le contrat"))
    assert "arnaque" in msg.lower()


# ── CAS 2 · Le bac en poche, zéro argent ──────────────────────────────────────────────────

def test_la_contrainte_d_argent_est_reconnue_comme_orientation():
    """« mes parents peuvent pas payer » n'est pas une recherche d'emploi : c'est un arbitrage."""
    for m in ("j'ai eu mon bac mais mes parents n'ont pas les moyens pour l'université",
              "pas les moyens de payer une école privée"):
        cmd = main._free_text_to_command(m.lower(), m)
        assert cmd.startswith("/orientation"), f"« {m} » → {cmd}"


# ── CAS 3 · Le diplôme qui ne sert pas ────────────────────────────────────────────────────

def test_le_diplome_sans_debouche_part_en_orientation():
    for m in ("j'ai une licence en géographie depuis 3 ans et je ne trouve rien",
              "mon diplôme ne sert à rien ici"):
        cmd = main._free_text_to_command(m.lower(), m)
        assert cmd.startswith(("/orientation", "/mobilite")), f"« {m} » → {cmd}"


# ── CAS 4 · Le visa refusé ────────────────────────────────────────────────────────────────

def test_un_refus_de_visa_mene_au_recours():
    for m in ("on m'a refusé le visa france",
              "mon visa a été refusé qu'est-ce que je fais",
              "j'ai eu un refus pour mon admission"):
        cmd = main._free_text_to_command(m.lower(), m)
        assert cmd.startswith("/recours"), f"« {m} » → {cmd}"


# ── CAS 5 · Le CV vide ────────────────────────────────────────────────────────────────────

def test_sans_experience_on_propose_de_creer_un_cv():
    for m in ("je n'ai pas de cv", "j'ai jamais travaillé et j'ai pas de cv"):
        cmd = main._free_text_to_command(m.lower(), m)
        assert cmd.startswith("/creercv"), f"« {m} » → {cmd}"


# ── CAS 6 · Le téléphone pour seul outil ──────────────────────────────────────────────────

def test_une_photo_de_document_trouve_son_outil():
    """Beaucoup n'ont pas d'ordinateur : le CV est une photo, pas un PDF."""
    for m, attendu in (("je veux lire ce qui est écrit sur la photo", "/extraire"),
                       ("mettre mes photos en pdf", "/enpdf"),
                       ("mon pdf est trop lourd", "/compresser")):
        cmd = main._free_text_to_command(m.lower(), m)
        assert cmd.startswith(attendu), f"« {m} » → {cmd}"


# ── CAS 7 · La détresse derrière la question scolaire ─────────────────────────────────────

def test_la_detresse_passe_avant_tout():
    s = _sess(orient_test={"qi": 1, "answers": ["R"], "complet": False})
    msg, s = _run(main.process_text_message(s, "j'ai envie de mourir"))
    assert "pas la bonne personne" in msg.lower()
    assert "orient_test" not in s, "un questionnaire ne doit pas retenir quelqu'un qui va mal"


def test_la_detresse_ne_se_declenche_pas_sur_une_figure_de_style():
    for m in ("ce formulaire me tue", "je meurs de faim", "c'est trop mortel ce site"):
        assert ori.detecte_detresse(m) is False, m


# ── CAS 8 · Les mineurs ───────────────────────────────────────────────────────────────────

def test_le_niveau_college_est_reconnu():
    """La politique de confidentialité assume ce public : encore faut-il le détecter."""
    assert ori.detect_situation("je suis en 3eme").get("niveau") == "collège / BEPC"
    assert ori.detect_situation("je suis en terminale D").get("niveau") == "lycée"
    assert ori.detect_situation("je suis en terminale D").get("serie") == "D"
