"""Programme testeurs : palier, retours spontanés, rapport terrain.

Le constat qui a tout déclenché : le meilleur retour d'une testeuse est arrivé dans le
WhatsApp PERSONNEL du propriétaire, jamais dans `/retours`.

    « ce que j'ai testé marche bien mais je vais encore essayer d'autres choses »
    « en fait ça facilite vraiment tout ! »

Personne ne tape `/avis`. Tout le monde dit « ça marche pas » au bot — et le bot essayait
de router la phrase. Ces tests verrouillent la correction.
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


@pytest.fixture(autouse=True)
def _mute(monkeypatch):
    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "send_message", _noop)
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main, "deliver_text", _noop)
    monkeypatch.setattr(main, "_ADMIN_IDS", {"admin-99"})


def _sess(**kw):
    base = {"user_id": "u-test", "channel": "telegram", "chat_id": "u-test", "username": "Testeuse",
            "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}
    base.update(kw)
    return base


def _testeur():
    from datetime import datetime, timedelta, timezone
    return _sess(premium_tier=main._TIER_TESTEUR,
                 premium_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat())


# ── 1. Le palier testeur ──

def test_le_testeur_a_le_confort_du_premium():
    s = _testeur()
    assert main._user_tier(s) == "testeur"
    assert main._est_testeur(s) is True
    assert main._is_premium(s) is True              # pas de quota, pas de filigrane
    ok, _ = main._quota_check(s, "cv", 1)
    assert ok is True


def test_un_gratuit_nest_pas_testeur():
    s = _sess()
    assert main._user_tier(s) == "free"
    assert main._est_testeur(s) is False


def test_un_premium_ordinaire_nest_pas_testeur():
    from datetime import datetime, timedelta, timezone
    s = _sess(premium_tier="premium",
              premium_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
    assert main._user_tier(s) == "premium"
    assert main._est_testeur(s) is False


def test_un_code_testeur_peut_etre_genere():
    s = _sess(user_id="admin-99", chat_id="admin-99")
    msg, _ = _run(main.process_text_message(s, "/gencodes testeur 60 2"))
    assert "codes testeur" in msg.lower() or "✅" in msg


# ── 2. Un retour dit en français est entendu ──

@pytest.mark.parametrize("phrase", [
    "ça marche pas", "ça bug", "j'ai pas compris", "c'est bizarre",
    "ça n'a rien à voir", "c'est pas clair", "pourquoi tu me dis ça",
])
def test_les_plaintes_sont_reconnues(phrase):
    assert main._retour_spontane(phrase) == "négatif", phrase


@pytest.mark.parametrize("phrase", [
    "ce que j'ai testé marche bien",           # la phrase exacte d'Hermione
    "en fait ça facilite vraiment tout !",     # la phrase exacte d'Hermione
    "oui oui même très intéressant",
    "c'est super",
])
def test_les_compliments_sont_reconnus(phrase):
    assert main._retour_spontane(phrase) == "positif", phrase


@pytest.mark.parametrize("phrase", [
    "je cherche un stage",
    "comment je fais pour le visa",
    "c'est quoi campus france",
    "bonjour",
    "trouve moi une formation qui marche bien pour l'emploi",
    "donne moi des offres qui marchent bien",
])
def test_une_vraie_demande_nest_pas_prise_pour_un_retour(phrase):
    assert main._retour_spontane(phrase) == "", phrase


def test_un_retour_negatif_est_enregistre_avec_ce_qui_precede(monkeypatch):
    """« ça marche pas » ne dit rien sans la réponse qui précède."""
    enregistres = []
    monkeypatch.setattr(main.opp_store, "add_contact",
                        lambda uid, un, txt, fwd: enregistres.append(txt))
    s = _sess(historique=[{"role": "assistant", "content": "🎓 Formations · 1. Hack The Box"}])
    msg, _ = _run(main.process_text_message(s, "ça marche pas"))
    assert "Merci de me le dire" in msg
    assert "qu'est-ce que tu attendais" in msg.lower()
    assert enregistres, "le retour doit être enregistré"
    assert "[RETOUR-NÉGATIF]" in enregistres[0]
    assert "Hack The Box" in enregistres[0], "le contexte manque"


def test_un_retour_positif_demande_ce_qui_pourrait_etre_mieux():
    msg, _ = _run(main.process_text_message(_sess(), "en fait ça facilite vraiment tout !"))
    assert "merci" in msg.lower()
    assert "meilleure" in msg.lower() or "mieux" in msg.lower()


def test_le_retour_ne_coupe_pas_un_flux_guide():
    """Pendant le test d'orientation, « c'est bizarre » ne doit pas sortir du questionnaire."""
    s = _sess(orient_test={"qi": 2, "answers": ["R", "I"], "complet": False})
    msg, _ = _run(main.process_text_message(s, "c'est bizarre"))
    assert "Merci de me le dire" not in msg


def test_la_precision_apres_un_pouce_bas_est_captee(monkeypatch):
    enregistres = []
    monkeypatch.setattr(main.opp_store, "add_contact",
                        lambda uid, un, txt, fwd: enregistres.append(txt))
    s = _sess(attente_precision_retour="formations")
    msg, s = _run(main.process_text_message(s, "les formations proposées sont toutes en anglais"))
    assert "exactement ce qu'il fallait" in msg.lower()
    assert "attente_precision_retour" not in s
    assert any("anglais" in e for e in enregistres), enregistres


# ── 3. Les boutons 👍/👎 ──

def test_les_boutons_ne_sont_poses_que_pour_un_testeur():
    s = _sess()
    main._boutons_avis(s, "formations")
    assert not s.get("_kb_options"), "pas de sondage permanent pour tout le monde"
    st = _testeur()
    main._boutons_avis(st, "formations")
    assert ("👍 Utile", "act:av_formations_ok") in st["_kb_options"]
    assert ("👎 À côté", "act:av_formations_ko") in st["_kb_options"]


# ── 4. La mission ──

def test_la_mission_liste_cinq_taches_et_coche_ce_qui_est_fait():
    s = _testeur()
    s["cv_parsed"] = True
    msg, s = _run(main.process_text_message(s, "/mission"))
    assert msg.count("⬜") + msg.count("✅") == 5
    assert "✅" in msg, "l'envoi du CV doit être coché"
    assert "1/5" in msg
    assert "cv" in (s.get("missions_faites") or [])


def test_la_mission_marche_aussi_sans_code_testeur():
    msg, _ = _run(main.process_text_message(_sess(), "/mission"))
    assert "mission" in msg.lower()
    assert "pas de code testeur" in msg.lower()


# ── 5. Le rapport terrain ──

def test_le_rapport_contient_les_sections_utiles():
    r = main._rapport_testeurs(1)
    for titre in ("Compréhension du langage naturel", "Messages sans route",
                  "Ce qui n'a pas marché", "Bugs signalés", "Activité des testeurs"):
        assert titre in r, titre


def test_le_rapport_sort_les_rates_au_format_du_jeu():
    """Les lignes doivent être collables telles quelles, sans recopie."""
    import json
    main._ROUTE_MISSES.clear()
    from datetime import datetime, timezone
    main.opp_store.add_miss({"ts": datetime.now(timezone.utc).isoformat(), "uid": "u",
                             "canal": "telegram", "kind": "sans_route", "etape": "ACTIF",
                             "text": "abeg trouve moi quelque chose deh"})
    r = main._rapport_testeurs(1)
    lignes = [x for x in r.split("\n") if x.startswith('{"msg"')]
    assert lignes, r[:600]
    for ligne in lignes:
        d = json.loads(ligne)                 # du JSON valide, pas du texte qui y ressemble
        assert d["source"] == "terrain"
        assert d["attendu"] == []


def test_le_rapport_est_reserve_a_l_admin():
    msg, _ = _run(main.process_text_message(_sess(), "/rapport"))
    assert "réservée à l'administrateur" in msg


def test_le_rapport_est_envoye_en_fichier(monkeypatch):
    recu = {}

    async def _fichier(sess, nom, data, caption=""):
        recu["nom"] = nom
        recu["texte"] = data.decode("utf-8")
        return True
    monkeypatch.setattr(main, "deliver_file", _fichier)
    s = _sess(user_id="admin-99", chat_id="admin-99")
    msg, _ = _run(main.process_text_message(s, "/rapport semaine"))
    assert "Rapport envoyé" in msg
    assert recu["nom"].endswith("-7j.md")
    assert recu["texte"].startswith("# NexMove · rapport terrain")


def test_le_cron_connait_le_rapport_et_les_rappels():
    sh = (RACINE / "scripts" / "nex-cron.sh").read_text(encoding="utf-8")
    for ep in ("rapport", "rapport-hebdo", "rappel-testeurs"):
        assert ep in sh, ep
    assert "crontab" in sh, "les lignes crontab doivent être documentées dans le script"
