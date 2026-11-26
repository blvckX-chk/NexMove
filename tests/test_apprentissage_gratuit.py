"""Diffusion gratuite pour l'apprentissage et les métiers manuels.

Le raisonnement : les offres du secteur informel — coiffure, couture, mécanique, soudure,
menuiserie, restauration, agriculture — ne sont publiées **nulle part** en ligne. Elles
circulent de bouche à oreille. Aucun agrégateur ne les trouvera jamais ; il faut être
l'endroit où elles se publient.

NexMove avait déjà cette machinerie (`/publier` → validation → diffusion ciblée), mais elle
était payante en crédits. Un patron de salon à Calavi ne paiera jamais des crédits pour
chercher un apprenti : le canal qui résolvait le problème était fermé à ceux qui en ont besoin.

Le verrou réel n'était d'ailleurs pas le débit, mais **la phrase d'accueil** : « la diffusion
est payante » en tête du questionnaire fait abandonner avant la première question. Une
exonération ne sert à rien si personne n'arrive au bout.
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


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _offre(titre, contrat="CDD", profil=""):
    return {"titre": titre, "contrat": contrat, "profil_recherche": profil}


# ── Ce qui doit être gratuit ──

@pytest.mark.parametrize("offre", [
    _offre("Recherche apprenti coiffeur", "apprentissage"),
    _offre("Salon cherche une tresseuse", profil="expérience tresses"),
    _offre("Atelier de couture cherche une aide", profil="couture"),
    _offre("Mécanicien auto", "CDI", "mécanique 2 ans"),
    _offre("Aide-cuisinier restaurant", profil="cuisine"),
    _offre("Soudeur", "journalier", "soudure"),
    _offre("Ouvrier agricole maraîchage", "saison", "agriculture"),
    _offre("Menuisier ébéniste", "CDI"),
    _offre("Plombier", "CDD"),
    _offre("Maçon carreleur", "chantier"),
    _offre("Pâtissier boulanger", "CDI"),
    _offre("Esthéticienne", "CDD"),
    _offre("Électricien bâtiment", "CDI"),
    _offre("Frigoriste froid et climatisation", "CDI"),
])
def test_les_metiers_manuels_sont_gratuits(offre):
    assert main._offre_apprentissage(offre) is True, offre["titre"]
    assert main._diffusion_cost(200, False, offre) == 0


def test_un_contrat_d_apprentissage_est_gratuit_meme_hors_metier_manuel():
    """Un vrai contrat d'apprentissage est exactement ce qu'on veut encourager, tech comprise."""
    o = _offre("Développeur web", "contrat d'apprentissage", "licence info")
    assert main._offre_apprentissage(o) is True
    assert main._diffusion_cost(200, False, o) == 0


# ── Ce qui doit rester payant ──

@pytest.mark.parametrize("offre", [
    _offre("Développeur Python senior", "CDI", "5 ans Python"),
    _offre("Comptable", "CDI", "licence compta"),
    _offre("Chargé de communication", "CDD", "master com"),
    _offre("Directeur financier", "CDI", "MBA"),
    _offre("Assistant de direction", "CDI", "BTS"),
    _offre("Juriste d'entreprise", "CDI", "master droit"),
])
def test_les_postes_qualifies_restent_payants(offre):
    assert main._offre_apprentissage(offre) is False, offre["titre"]
    assert main._diffusion_cost(200, False, offre) > 0


def test_le_bareme_historique_est_inchange_sans_offre():
    """L'ancien appel `_diffusion_cost(n, tous)` doit continuer à chiffrer comme avant."""
    assert main._diffusion_cost(120, False) > 0
    assert main._diffusion_cost(120, True) > main._diffusion_cost(120, False)


def test_l_exoneration_est_desactivable(monkeypatch):
    """Si le modèle économique change, une variable d'environnement suffit."""
    monkeypatch.setattr(main, "APPRENTISSAGE_GRATUIT", False)
    o = _offre("Recherche apprenti coiffeur", "apprentissage")
    assert main._offre_apprentissage(o) is False
    assert main._diffusion_cost(200, False, o) > 0


# ── Le verrou réel : ce que le recruteur LIT ──

def test_l_accueil_annonce_la_gratuite_avant_de_parler_de_credits():
    """« La diffusion est payante » en tête faisait abandonner un patron de salon."""
    ligne = main._recruit_price_line()
    assert "ratuit" in ligne, ligne
    assert ligne.index("ratuit") < ligne.lower().index("crédit"), (
        "la gratuité doit être annoncée AVANT les crédits, sinon elle n'est jamais lue")
    for metier in ("coiffure", "couture", "mécanique", "soudure"):
        assert metier in ligne.lower(), f"« {metier} » doit être cité : c'est le public visé"


def test_le_depot_dune_offre_dapprentissage_confirme_la_gratuite(monkeypatch):
    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main.recruiter_offer_store, "add", lambda rec, data: 42)
    sess = {"user_id": "r1", "channel": "telegram", "chat_id": "r1", "username": "Salon",
            "etape": "RECRUIT", "historique": [], "profil": {},
            "recruit_data": {"titre": "Recherche apprenti coiffeur", "contrat": "apprentissage",
                             "profil_recherche": "motivé", "entreprise": "Salon du coin"}}
    msg, _ = _run(main._recruit_finish(sess))
    assert "gratuitement" in msg.lower()
    assert "crédit" not in msg.lower(), "ne pas parler de crédits à qui n'en a pas besoin"
    # « rien à acheter » est rassurant ; « achète un pack » serait une demande de paiement.
    assert "achète" not in msg.lower() and "paiement" not in msg.lower()
    assert "rien à acheter" in msg.lower()


def test_le_depot_dune_offre_qualifiee_parle_toujours_de_credits(monkeypatch):
    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main.recruiter_offer_store, "add", lambda rec, data: 43)
    sess = {"user_id": "r2", "channel": "telegram", "chat_id": "r2", "username": "Boîte",
            "etape": "RECRUIT", "historique": [], "profil": {},
            "recruit_data": {"titre": "Développeur Python senior", "contrat": "CDI",
                             "profil_recherche": "5 ans", "entreprise": "Tech SA"}}
    msg, _ = _run(main._recruit_finish(sess))
    assert "crédit" in msg.lower()
