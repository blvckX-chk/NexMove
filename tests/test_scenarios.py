"""Harnais d'ÉVALUATION conversationnel (#7).
Rejoue des DIALOGUES-PIÈGES de bout en bout à travers process_text_message, avec LLM/IO
simulés, pour garantir qu'on ne régresse pas sur les carrefours et les flux critiques.
À lancer à chaque déploiement : c'est le filet qui permet d'itérer vite sans casser.
"""
import os, sys, asyncio, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
import importlib
main = importlib.import_module("main")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _mute_io(monkeypatch):
    """Neutralise les sorties réseau (admin, canaux, fichiers) pour tous les scénarios."""
    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main, "deliver_text", _noop)
    monkeypatch.setattr(main, "deliver_file", _noop)


def _sess(**kw):
    base = {"user_id": "u-scn", "channel": "whatsapp", "chat_id": "229", "username": "Test",
            "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}
    base.update(kw)
    return base


# ── Scénario 1 : un recruteur dépose une offre de bout en bout ──
def test_scn_recruteur_depot_complet():
    s = _sess()
    msg, s = _run(main.process_text_message(s, "je veux publier une offre"))
    assert s["etape"] == "RECRUIT"
    for rep in ["Développeur web", "ACME", "Cotonou", "CDI", "coder des sites web",
                "Licence info 2 ans", "à négocier", "rh@acme.bj", "30/11/2026"]:
        msg, s = _run(main.process_text_message(s, rep))
    assert s["etape"] == "ACTIF"
    assert "reçue" in msg.lower() or "merci" in msg.lower()


# ── Scénario 2 : une question en pleine création de CV n'est PAS stockée ──
def test_scn_cvbuild_question_non_stockee():
    s = _sess(etape="CVBUILD", cvbuild_step=1, cvbuild_data={"nom": "Ali"})
    msg, s = _run(main.process_text_message(s, "pourquoi tu demandes ça ?"))
    assert s["cvbuild_step"] == 1 and "formation" not in s.get("cvbuild_data", {})


# ── Scénario 3 : /annuler fait sortir d'un flux guidé ──
def test_scn_annuler_sort_du_flux():
    s = _sess(etape="RECRUIT", recruit_step=2, recruit_data={"titre": "X"})
    msg, s = _run(main.process_text_message(s, "/annuler"))
    assert s["etape"] != "RECRUIT" and "annul" in msg.lower()


# ── Scénario 4 : un lien YouTube n'est PAS audité comme une opportunité ──
def test_scn_lien_youtube_non_audite(monkeypatch):
    called = {"n": 0}
    async def _audit(session, url):
        called["n"] += 1
        return "audit", session
    monkeypatch.setattr(main, "audit_opportunity_link", _audit)
    s = _sess()
    _run(main.process_text_message(s, "regarde https://youtube.com/watch?v=abc"))
    assert called["n"] == 0


# ── Scénario 5 : un VRAI lien d'offre EST audité ──
def test_scn_lien_offre_audite(monkeypatch):
    called = {"n": 0}
    async def _audit(session, url):
        called["n"] += 1
        return "audit", session
    monkeypatch.setattr(main, "audit_opportunity_link", _audit)
    s = _sess()
    _run(main.process_text_message(s, "https://emploi.bj/offre/123"))
    assert called["n"] == 1


# ── Scénario 6 : question « version » → réponse déterministe (pas d'hallucination) ──
def test_scn_version_deterministe():
    s = _sess()
    msg, s = _run(main.process_text_message(s, "Version ?"))
    assert main.VERSION in msg


# ── Scénario 7 : la mémoire écarte les offres déjà vues (anti-répétition) ──
def test_scn_memoire_anti_repetition():
    s = _sess()
    main._mem_mark_seen(s, ["https://a.bj/1", "https://a.bj/2"])
    assert main._mem_seen(s) == {"https://a.bj/1", "https://a.bj/2"}
    # un 2e passage ne duplique pas
    main._mem_mark_seen(s, ["https://a.bj/1"])
    assert len(main._mem(s)["vus"]) == 2


# ── Scénario 8 : multimodal — détection d'une annonce dans un texte ──
def test_scn_multimodal_detecte_annonce():
    assert main._looks_like_opportunity(
        "Nous recrutons un comptable H/F en CDI à Cotonou. Profil : licence. Postuler avant le 30/11.") is True
    assert main._looks_like_opportunity("coucou tu fais quoi") is False


# ── Scénario 9 : boucle d'agent — 2e action hors whitelist jamais enchaînée ──
def test_scn_agent_whitelist_sure():
    # Les actions à état/confirmation ne sont pas dans la whitelist de chaînage.
    for risky in ("creercv", "publier", "supprimer", "premium", "veille", "mobilite"):
        assert risky not in main._CHAINABLE_ACTIONS
    # Les actions de conseil le sont.
    for safe in ("chances", "compatibilite", "commentpostuler"):
        assert safe in main._CHAINABLE_ACTIONS


# ── Scénario 10 : commande admin depuis un compte NON-admin → refusée ──
def test_scn_admin_cmd_refusee_non_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda s: False)
    s = _sess(user_id="pas-admin")
    msg, s = _run(main.process_text_message(s, "/stats"))
    assert "administrateur" in msg.lower() or "réservé" in msg.lower() or "reserve" in msg.lower()


# ── Scénario 11 : suppression de données → demande TOUJOURS confirmation ──
def test_scn_suppression_demande_confirmation():
    s = _sess(profil={"identite": {"nom": "Awa"}, "preferences": {"mots_cles": "data"}})
    msg, s = _run(main.process_text_message(s, "/supprimer"))
    assert s.get("awaiting_delete_confirm") is True          # on attend un OUI/NON
    assert s["profil"]["identite"]["nom"] == "Awa"            # rien n'est supprimé sans confirmation


# ── Scénario 12 : reconversion détectée À LA VALIDATION du profil ──
def test_scn_reconversion_a_la_validation(monkeypatch):
    async def _osint(*a, **k):
        return {"message": "offres", "opportunites": [], "visa_info": {}}
    async def _tav(q, n=6): return [{"title": "Coursera Finance", "url": "http://c/f", "content": "x"}]
    async def _llm(system, prompt, **k):
        return {"formations": [{"titre": "Initiation Finance", "organisme": "Coursera", "cout": "gratuit"}]}
    monkeypatch.setattr(main, "run_osint", _osint)
    monkeypatch.setattr(main, "tavily_search", _tav)
    monkeypatch.setattr(main, "call_groq", _llm)
    s = _sess(etape="CONFIRMATION", cv_parsed=True, onboarding_complete=False,
              profil={"formation": [{"domaine": "Informatique"}], "competences": {"techniques": ["Python"]},
                      "preferences": {"objectif": "travailler", "mots_cles": "finance"}})
    msg, s = _run(main.process_text_message(s, "oui c'est bon"))
    assert s.get("reconv_pending") is True and "reconversion" in msg.lower()
    # « de zéro » -> on oriente FORMATIONS, pas des offres de l'ancien métier.
    msg, s = _run(main.process_text_message(s, "je pars de zéro"))
    assert "formation" in msg.lower()


# ── Scénario 13 : réponse ambiguë à la confirmation → NE réinitialise PAS ──
def test_scn_confirmation_ambigue_ne_reset_pas():
    s = _sess(etape="CONFIRMATION",
              profil={"preferences": {"objectif": "emploi", "mots_cles": "finance"}})
    msg, s = _run(main.process_text_message(s, "Au Bénin"))
    assert s["profil"]["preferences"].get("mots_cles") == "finance"   # profil conservé
    assert "on reprend" not in msg.lower()


# ── Scénario 14 : re-ciblage en conversation → met à jour le profil + relance ──
def test_scn_reciblage_en_conversation(monkeypatch):
    async def _osint(*a, **k):
        return {"message": "offres marketing", "opportunites": [], "visa_info": {}}
    monkeypatch.setattr(main, "run_osint", _osint)
    monkeypatch.setattr(main, "_veille_gate", lambda s: (True, ""))
    monkeypatch.setattr(main, "_quota_bump", lambda s, f: None)
    s = _sess(profil={"preferences": {"objectif": "travailler", "mots_cles": "comptabilité"}})
    msg, s = _run(main.process_text_message(s, "finalement je préfère le marketing"))
    assert s["profil"]["preferences"]["mots_cles"] == "marketing" and "recentre" in msg.lower()


# ── Scénario 15 : message vide / emoji seul → réponse propre, pas de crash ──
def test_scn_message_vide_ou_emoji_pas_de_crash():
    for weird in ("", "   ", "🙂", "?", "a"):
        s = _sess()
        msg, s = _run(main.process_text_message(s, weird))
        assert isinstance(msg, str)   # toujours une réponse, jamais une exception


# ── Scénario v3.91 : conseiller qui fait relire le CV d'une candidate (retour terrain Telegram) ──
def _doc_tiers(s):
    main._remember_doc(s, "cv", "Prénom Candidate — Apprentie ingénieure en efficacité énergétique. "
                       "Licence 3 Sciences pour l'ingénieur. Expériences : technicienne maintenance CVC.",
                       caption="En tant que conseiller d'orientation senior, analyse moi ce CV que je lui fasse un retour",
                       summary="Analyse : CV bien structuré, ajouter des réalisations chiffrées.")
    return s

def test_scn_conseiller_cv_tiers_conseils_sans_questionnaire(monkeypatch):
    vus = {}
    async def _fake_gen(system, user, **k):
        vus["system"], vus["user"] = system, user
        return "Voici 5 conseils concrets pour améliorer son CV."
    monkeypatch.setattr(main, "_gen_text", _fake_gen)
    s = _doc_tiers(_sess(channel="telegram"))
    assert s["last_doc"]["owner"] == "tiers"
    msg, s = _run(main.process_text_message(
        s, "Conseils pour améliorer le CV de manière générale. Pas besoin de me proposer des options"))
    assert s.get("etape") != "CVBUILD"                          # plus de questionnaire lancé à tort
    assert "conseils concrets" in msg
    assert "AUTRE personne" in vus["system"]                    # rôle conseiller -> 3e personne
    assert "efficacité énergétique" in vus["user"]              # réponse ANCRÉE sur le document
    assert s["profil"]["profil_plus"].get("no_menu") is True    # « pas besoin d'options » retenu

def test_scn_reference_au_cv_analyse_sort_du_questionnaire(monkeypatch):
    async def _fake_gen(system, user, **k):
        return "Oui, je parle du CV que je viens d'analyser."
    monkeypatch.setattr(main, "_gen_text", _fake_gen)
    s = _doc_tiers(_sess(channel="telegram", etape="CVBUILD", cvbuild_step=1, cvbuild_data={}))
    msg, s = _run(main.process_text_message(s, "Le CV que tu as analysé ?"))
    assert s["etape"] != "CVBUILD"
    assert "CV que je viens d'analyser" in msg

def test_scn_questionnaire_ne_piege_plus(monkeypatch):
    s = _sess(channel="telegram", etape="CVBUILD", cvbuild_step=0, cvbuild_data={})
    msg, s = _run(main.process_text_message(s, "Ketsia Mensah"))          # vrai nom -> accepté
    assert s["cvbuild_data"].get("nom") == "Ketsia Mensah" and s["cvbuild_step"] == 1
    msg, s = _run(main.process_text_message(s, "Il est sur le CV envoyé"))   # pas un diplôme
    assert "formation" not in s["cvbuild_data"] and s["etape"] == "CVBUILD"
    assert "pas sûr" in msg
    msg, s = _run(main.process_text_message(s, "Je veux les codes valide"))  # 2e incohérence -> on sort
    assert s["etape"] != "CVBUILD"
    assert "pause" in msg

def test_scn_ameliorer_cv_sans_document_demande_le_cv():
    s = _sess(channel="telegram", onboarding_complete=False, etape="ATTENTE_CV")
    msg, s = _run(main.process_text_message(s, "je veux des conseils pour améliorer mon CV"))
    assert s.get("etape") != "CVBUILD"
    assert "Envoie-moi le CV" in msg

def test_scn_creer_cv_reste_route():
    s = _sess(channel="telegram", onboarding_complete=False, etape="ATTENTE_CV")
    msg, s = _run(main.process_text_message(s, "je veux créer mon CV"))
    assert s.get("etape") == "CVBUILD"


# ── v3.91 : réparation de conversation et sortie naturelle des questionnaires ──
def test_scn_non_je_voulais_des_conseils(monkeypatch):
    async def _fake_gen(system, user, **k):
        return "Voici mes conseils pour son CV."
    monkeypatch.setattr(main, "_gen_text", _fake_gen)
    s = _doc_tiers(_sess(channel="telegram", etape="CVBUILD", cvbuild_step=0, cvbuild_data={}))
    msg, s = _run(main.process_text_message(s, "Non, je voulais des conseils pour le CV, pas en créer un"))
    assert s["etape"] != "CVBUILD" and "conseils pour son CV" in msg

def test_scn_tu_ne_comprends_pas_repare(monkeypatch):
    async def _fake_gen(system, user, **k):
        assert "mal comprise" in system
        return "Je suis parti sur une mauvaise piste : tu voulais un avis sur le CV, c'est bien ça ?"
    monkeypatch.setattr(main, "_gen_text", _fake_gen)
    s = _sess(channel="telegram", etape="CVBUILD", cvbuild_step=2, cvbuild_data={"nom": "X"})
    msg, s = _run(main.process_text_message(s, "tu ne comprends pas"))
    assert s["etape"] != "CVBUILD" and "mauvaise piste" in msg

def test_scn_laisse_tomber_sort_sans_annuler():
    s = _sess(channel="telegram", etape="CVBUILD", cvbuild_step=1, cvbuild_data={"nom": "X"})
    msg, s = _run(main.process_text_message(s, "laisse tomber"))
    assert s["etape"] != "CVBUILD" and "/annuler" not in msg

def test_scn_repair_remainder_v391():
    assert main._repair_remainder("Non, je voulais des conseils pour le CV") == "des conseils pour le CV"
    assert main._repair_remainder("c'est pas ce que j'ai demandé") == ""
    assert main._REPAIR_RE.match("tu ne comprends pas")
    assert not main._REPAIR_RE.match("non")                     # « non » seul reste une réponse
    assert not main._REPAIR_RE.match("je voudrais une bourse")   # pas une correction
