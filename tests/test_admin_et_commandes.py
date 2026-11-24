"""Trois défauts constatés sur une vraie conversation Telegram du compte admin.

1. `/admin` n'existait pas. C'est pourtant le mot qu'on tape en premier pour chercher
   le panneau. La commande tombait jusqu'à l'orchestrateur IA, qui répondait poliment
   à côté : « la commande /admin n'est pas reconnue, dis-moi ce dont tu as besoin ».
2. Le refus d'une commande admin disait « 🔒 réservée à l'administrateur » sans dire
   pourquoi — inutilisable quand on EST l'administrateur et qu'on ne comprend pas.
3. Le bot a redemandé une précision deux fois de suite alors que la personne avait
   répondu entre les deux.
"""
import os
import sys
import asyncio
import pathlib

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
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main, "deliver_text", _noop)
    monkeypatch.setattr(main, "deliver_file", _noop)


def _sess(**kw):
    base = {"user_id": "99", "channel": "telegram", "chat_id": "99", "username": "T",
            "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}
    base.update(kw)
    return base


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(main, "_ADMIN_IDS", {"99"})
    return _sess()


@pytest.fixture
def pas_admin(monkeypatch):
    monkeypatch.setattr(main, "_ADMIN_IDS", {"autre-compte"})
    return _sess()


# ── 1. /admin existe et sert de sommaire ──

def test_admin_donne_le_sommaire_des_commandes(admin):
    msg, _ = _run(main.process_text_message(admin, "/admin"))
    assert "Panneau admin" in msg
    for cmd in ("/stats", "/codes", "/gencodes", "/retours", "/annonces", "/misses", "/ia", "/id"):
        assert cmd in msg, cmd
    assert "n'est pas reconnue" not in msg


def test_admin_a_des_alias(admin):
    for alias in ("/adminhelp", "/console"):
        msg, _ = _run(main.process_text_message(admin, alias))
        assert "Panneau admin" in msg


# ── 2. Le refus dit POURQUOI ──

def test_refus_admin_donne_l_identifiant_et_la_cause(pas_admin):
    msg, _ = _run(main.process_text_message(pas_admin, "/admin"))
    assert "99" in msg                      # l'identifiant vu par le serveur
    assert "ADMIN_CHAT_ID" in msg           # où le corriger
    assert "/id" in msg


def test_refus_admin_quand_aucun_admin_configure(monkeypatch):
    monkeypatch.setattr(main, "_ADMIN_IDS", set())
    msg, _ = _run(main.process_text_message(_sess(), "/stats"))
    assert "Aucun administrateur n'est configuré" in msg


def test_refus_admin_explique_le_blocage_meta(monkeypatch):
    monkeypatch.setattr(main, "_ADMIN_IDS", {"229"})
    monkeypatch.setattr(main, "META_APP_SECRET", "")
    msg, _ = _run(main.process_text_message(_sess(channel="whatsapp", chat_id="229"), "/codes"))
    assert "META_APP_SECRET" in msg
    assert "signés" in msg or "signé" in msg


def test_toutes_les_commandes_admin_utilisent_le_refus_explicite():
    """Aucun handler ne doit garder l'ancien refus muet."""
    src = (RACINE / "api" / "main.py").read_text(encoding="utf-8")
    assert '"🔒 Commande réservée à l\'administrateur."' not in src


# ── 3. Commande inconnue : réponse déterministe, jamais l'IA ──

def test_commande_inconnue_le_dit(pas_admin, monkeypatch):
    async def _boom(*a, **k):
        raise AssertionError("l'IA ne doit pas être appelée pour une commande inconnue")
    monkeypatch.setattr(main, "call_groq", _boom)
    msg, _ = _run(main.process_text_message(pas_admin, "/nimportequoi"))
    assert "/nimportequoi" in msg
    assert "n'existe pas" in msg
    assert "/aide" in msg


def test_commande_inconnue_propose_la_plus_proche(pas_admin):
    msg, _ = _run(main.process_text_message(pas_admin, "/orientatio"))
    assert "/orientation" in msg
    msg, _ = _run(main.process_text_message(pas_admin, "/compreser"))
    assert "/compresser" in msg


def test_commande_inconnue_ne_propose_pas_l_admin_aux_autres(pas_admin, admin):
    msg, _ = _run(main.process_text_message(pas_admin, "/adminn"))
    assert "/admin" not in msg
    msg, _ = _run(main.process_text_message(admin, "/statz"))
    assert "/stats" in msg


def test_les_vraies_commandes_ne_tombent_pas_dans_l_inconnu(admin):
    for cmd in ("/aide", "/outils", "/version", "/id", "/admin", "/codes", "/testorientation"):
        msg, _ = _run(main.process_text_message(admin, cmd))
        assert "n'existe pas" not in msg, cmd


def test_un_lien_colle_nest_pas_pris_pour_une_commande(pas_admin, monkeypatch):
    """Un message qui commence par « / » mais contient une URL part au traitement normal."""
    assert main._commande_inconnue("/truc", pas_admin)
    # la garde elle-même : le handler ne doit pas se déclencher sur une URL
    assert main._URL_RE.search("/voir https://exemple.org/offre")


# ── 4. Deux demandes de précision d'affilée : on arrête ──

def test_deuxieme_relance_consecutive_bloquee():
    s = {}
    q1 = "Peux-tu préciser ce que tu cherches avec « Codes validea » ? Un code promo, un accès ?"
    q2 = "Peux-tu préciser de quels codes il s'agit ? Des codes d'accès, ton compte, ou autre ?"
    assert main._relance_en_boucle(q1, s) is False
    assert main._relance_en_boucle(q2, s) is True


def test_une_vraie_question_de_cadrage_passe():
    s = {}
    for q in ("Dans quelle ville cherches-tu un logement ?",
              "Tu vises plutôt une licence ou un master ?",
              "Quel est ton domaine : informatique, santé, commerce ?"):
        assert main._relance_en_boucle(q, s) is False


def test_le_compteur_repart_quand_on_avance():
    s = {}
    main._relance_en_boucle("Peux-tu préciser de quels codes il s'agit ?", s)
    assert s["relance_suite"] == 1
    main._relance_en_boucle("Voici 3 bourses correspondant à ton profil.", s)
    assert s["relance_suite"] == 0
    assert main._relance_en_boucle("Peux-tu préciser ta demande ?", s) is False


# ── 5. Le cas exact de la capture, de bout en bout ──

def test_parcours_de_la_capture_compte_admin(admin, monkeypatch):
    """Compte admin reconnu : /admin répond, et « Codes valides » liste les codes."""
    async def _ia(*a, **k):
        raise AssertionError("aucun de ces deux messages ne doit atteindre l'IA")
    monkeypatch.setattr(main, "call_groq", _ia)
    msg, s = _run(main.process_text_message(admin, "/admin"))
    assert "Panneau admin" in msg
    msg, s = _run(main.process_text_message(s, "Codes valides"))
    assert "VALIDES" in msg.upper()
