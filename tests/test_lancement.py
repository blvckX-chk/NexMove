"""Offre de lancement : tout est gratuit jusqu'au 1er mars, contre un retour.

Décision du Propriétaire (26/11/2026) : les formules et les packs restent affichés
avec leurs prix — on n'efface pas le modèle économique — mais pendant le lancement
tout est ouvert à qui accepte d'être testeur. Ce que la gratuité achète, ce n'est pas
du volume : c'est du retour de terrain, la seule chose qui ait jamais trouvé un défaut
dans ce produit.

**Ce que ces tests verrouillent avant tout, c'est la fin de l'offre.** Une promotion
qui ne sait pas s'arrêter se transforme en produit gratuit par oubli : il suffit que
personne ne pense à retirer une ligne au bon moment. Ici l'échéance est une date, et
le 1er mars l'offre tombe toute seule, quotas compris, sans qu'on touche au code.

C'est la même leçon que le bandeau Campus France, appliquée au tarif : une information
datée doit porter sa date, pas attendre qu'on se souvienne d'elle.
"""
import asyncio
import os
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
import main  # noqa: E402


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
    monkeypatch.setattr(main, "send_message", _noop)
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main, "deliver_text", _noop)


def _sess(**kw):
    base = {"user_id": "u-lanc", "channel": "telegram", "chat_id": "u-lanc", "username": "Visiteuse",
            "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}
    base.update(kw)
    return base


@pytest.fixture
def passe(monkeypatch):
    """Simule l'après-offre en déplaçant l'échéance dans le passé — on teste le vrai
    chemin de code, celui qui s'exécutera le 2 mars sans qu'on y touche."""
    monkeypatch.setattr(main, "LANCEMENT_FIN", "2026-01-01")


# ── 1. La fenêtre ────────────────────────────────────────────────────────────

def test_l_offre_court_jusqu_au_1er_mars_inclus():
    assert main._lancement_actif(date(2026, 11, 26)) is True
    assert main._lancement_actif(date(2027, 2, 28)) is True
    assert main._lancement_actif(date(2027, 3, 1)) is True     # le dernier jour compte
    assert main._lancement_actif(date(2027, 3, 2)) is False


def test_le_compte_a_rebours_est_juste():
    assert main._lancement_jours(date(2027, 3, 1)) == 0
    assert main._lancement_jours(date(2027, 2, 1)) == 28
    assert main._lancement_jours(date(2027, 3, 5)) < 0


def test_une_date_illisible_retombe_sur_le_tarif_normal(monkeypatch):
    """Si quelqu'un saisit n'importe quoi dans LANCEMENT_FIN, le risque à éviter est
    une gratuité perpétuelle. On refuse l'offre, on ne l'ouvre pas."""
    monkeypatch.setattr(main, "LANCEMENT_FIN", "pas une date")
    assert main._lancement_actif(date(2026, 11, 26)) is False
    inscrit, raison = main._rejoindre_testeur(_sess())
    assert inscrit is False and raison == "fermee"


# ── 2. L'adhésion ────────────────────────────────────────────────────────────

def test_accepter_rend_testeur_jusqu_a_la_fin_de_l_offre():
    s = _sess()
    inscrit, raison = main._rejoindre_testeur(s)
    assert inscrit is True and raison == "ok"
    assert s["premium_tier"] == main._TIER_TESTEUR
    assert s["premium_until"][:10] == main.LANCEMENT_FIN
    assert main._est_testeur(s) is True
    assert main._is_premium(s) is True


def test_le_testeur_na_plus_de_quota_pendant_l_offre():
    s = _sess()
    main._rejoindre_testeur(s)
    for feature in ("cv", "guide", "sim", "score", "apply", "link", "veille", "voice"):
        ok, _ = main._quota_check(s, feature, 1)
        assert ok is True, feature


def test_l_echeance_inclut_le_1er_mars_en_entier():
    """« Jusqu'au 1er mars » veut dire le 1er mars au soir, pas le 28 février à minuit."""
    s = _sess()
    main._rejoindre_testeur(s)
    fin = datetime.fromisoformat(s["premium_until"])
    assert fin.date() == date.fromisoformat(main.LANCEMENT_FIN)
    assert (fin.hour, fin.minute) == (23, 59)


def test_un_abonnement_plus_long_nest_jamais_degrade():
    """Quelqu'un qui a payé six mois de Pro ne doit pas devenir « testeur jusqu'au
    1er mars » pour avoir tapé une commande. Le défaut serait silencieux et coûteux."""
    loin = (datetime.now(timezone.utc) + timedelta(days=200)).isoformat()
    s = _sess(premium_tier="pro", premium_until=loin)
    inscrit, raison = main._rejoindre_testeur(s)
    assert inscrit is False and raison == "deja_mieux"
    assert s["premium_tier"] == "pro"
    assert s["premium_until"] == loin


def test_sinscrire_deux_fois_ne_casse_rien():
    s = _sess()
    main._rejoindre_testeur(s)
    avant = s["premium_until"]
    inscrit, raison = main._rejoindre_testeur(s)
    assert inscrit is False and raison == "deja_testeur"
    assert s["premium_until"] == avant


def test_apres_le_1er_mars_on_ne_peut_plus_sinscrire(passe):
    inscrit, raison = main._rejoindre_testeur(_sess())
    assert inscrit is False and raison == "fermee"


def test_le_statut_testeur_expire_de_lui_meme():
    """Le mécanisme d'expiration est celui des abonnements, déjà en place : rien de
    nouveau à surveiller. Une fois la date passée, la personne redevient « free »
    et les quotas gratuits la concernent de nouveau."""
    hier = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    s = _sess(premium_tier=main._TIER_TESTEUR, premium_until=hier)
    assert main._user_tier(s) == "free"
    assert main._est_testeur(s) is False
    ok, reste = main._quota_check(s, "cv", 1)
    assert ok is True and reste == 1      # premier usage autorisé, mais décompté


# ── 3. Ce que la personne lit ────────────────────────────────────────────────

def test_offres_annonce_la_gratuite_et_sa_date():
    msg, _ = _run(main.process_text_message(_sess(), "/offres"))
    assert "gratuit" in msg.lower()
    assert "mars" in msg.lower(), "une gratuité sans date est une promesse ouverte"
    assert "/testeur" in msg


def test_offres_garde_les_formules_affichees_pendant_le_lancement():
    """« On garde les packs » : le modèle économique reste visible, c'est la gratuité
    qui est datée — pas l'inverse."""
    msg, _ = _run(main.process_text_message(_sess(), "/offres"))
    for mot in ("Premium", "Pro", "crédit"):
        assert mot in msg, f"« {mot} » doit rester affiché"


def test_apres_l_offre_offres_redevient_une_page_de_tarifs(passe):
    """Aucune intervention le 2 mars : le même code, un jour plus tard, ne parle plus
    de gratuité."""
    msg, _ = _run(main.process_text_message(_sess(), "/offres"))
    assert "/testeur" not in msg
    assert "gratuit jusqu" not in msg.lower()
    assert "Premium" in msg and "crédit" in msg


def test_un_testeur_ne_se_voit_pas_proposer_d_acheter():
    s = _sess()
    main._rejoindre_testeur(s)
    msg, _ = _run(main.process_text_message(s, "/offres"))
    assert "rien à acheter" in msg.lower()


def test_la_commande_testeur_explique_ce_qu_on_attend():
    """Un testeur à qui on ne dit pas quoi faire ne teste rien : c'est le défaut
    constaté avant la v4.17. La contrepartie doit être dite, et rester minuscule."""
    msg, s = _run(main.process_text_message(_sess(), "/testeur"))
    assert "testeur" in msg.lower()
    assert "mars" in msg.lower()
    assert "/mission" in msg
    assert s["premium_tier"] == main._TIER_TESTEUR


def test_apres_l_offre_la_commande_testeur_le_dit_franchement(passe):
    msg, s = _run(main.process_text_message(_sess(), "/testeur"))
    assert "terminée" in msg.lower()
    assert s.get("premium_tier") != main._TIER_TESTEUR


# ── 4. Le langage humain ─────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "je veux être testeur",
    "je veux etre testeur",
    "ok pour être testeur",
    "j'accepte d'être testeur",
    "je suis d'accord pour tester",
    "je veux tester",
    "d'accord pour tester",
])
def test_accepter_en_francais_mene_a_la_commande(phrase):
    assert main._free_text_to_command(phrase.lower(), phrase) == "/testeur", phrase


@pytest.mark.parametrize("phrase", [
    "j'accepte",                      # accepte quoi ? une étape, les CGU, un rendez-vous
    "d'accord",
    "oui",
    "je veux un test d'orientation",  # c'est /testorientation, pas le programme testeur
    "je veux passer le test",
    # « testeur » est aussi un métier : ces phrases parlent de carrière, pas du programme.
    "je veux être testeur de logiciels",
    "je veux devenir testeur de jeux vidéo",
    "je veux être testeur QA",
    # Sans précision, le métier est la lecture la plus courante : laissé à /orientation.
    "comment devenir testeur ?",
])
def test_on_ne_devine_pas_une_adhesion(phrase):
    """Mieux vaut ne pas comprendre que comprendre à tort : inscrire quelqu'un qui
    répondait « oui » à autre chose, c'est changer son statut sans son accord."""
    assert main._free_text_to_command(phrase.lower(), phrase) != "/testeur", phrase
