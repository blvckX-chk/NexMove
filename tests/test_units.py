"""Tests unitaires des fonctions PURES de NexMove.
On importe main.py sans démarrer FastAPI (les modules sont importables comme un module).
Aucune requête réseau, aucun accès disque hors tmp — safe en CI."""
import os, sys, importlib, io, pathlib

# Rendre `api/` importable + neutraliser les vérifs d'API key au démarrage
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")

main = importlib.import_module("main")


# ------------------ Onboarding : validation des préférences ------------------
def test_valider_pref_objectif_ok():
    ok, _ = main.valider_pref("objectif", "travailler")
    assert ok is True

def test_valider_pref_objectif_ko_commande():
    ok, msg = main.valider_pref("objectif", "/hej")
    assert ok is False and "commande" in msg.lower()

def test_valider_pref_certifs_langue_taf_refuse():
    ok, _ = main.valider_pref("certifs_langue", "Taf")
    assert ok is False

def test_valider_pref_certifs_langue_ielts_accepte():
    ok, _ = main.valider_pref("certifs_langue", "IELTS 7")
    assert ok is True


# ------------------ Diplôme principal ------------------
def test_sort_formations_master_avant_licence():
    forms = [
        {"diplome": "Licence Gestion", "annee": "2018"},
        {"diplome": "Master ASI", "annee": "2021"},
    ]
    top = main._sort_formations(forms)[0]
    assert "master" in top["diplome"].lower()


# ------------------ Routeur d'intention langage naturel ------------------
def test_intent_formations():
    assert main._free_text_to_command("trouve moi des formations lasin", "x").startswith("/formations")

def test_intent_logement():
    assert main._free_text_to_command("je veux un logement à paris", "x").startswith("/logement")

def test_intent_visa():
    assert main._free_text_to_command("prendre rdv capago pour mon visa", "x") == "/visa"

def test_intent_recours():
    # Formulations sans "visa" (sinon /visa gagne, ce qui reste OK en pratique)
    assert main._free_text_to_command("faire un recours contre campus france", "x") == "/recours"
    assert main._free_text_to_command("j'ai eu un refus, que faire", "x") == "/recours"

def test_intent_parcoursup():
    assert main._free_text_to_command("comment ça marche parcoursup", "x") == "/parcoursup"

def test_intent_canada():
    assert main._free_text_to_command("comment aller au canada", "x") == "/canada"

def test_intent_conversation_libre():
    assert main._free_text_to_command("salut ça va", "x") == ""


# ------------------ Nationalité → pays local ------------------
def test_pays_from_nat_benin():
    assert main._pays_from_nat("béninoise") == "Bénin"

def test_pays_from_nat_cote_ivoire():
    assert main._pays_from_nat("ivoirienne") == "Côte d'Ivoire"

def test_pays_from_nat_inconnu():
    assert main._pays_from_nat("martienne") == ""


# ------------------ Feedback : signature d'offre ------------------
def test_offer_signal_type_present():
    sig = main._offer_signal({"type": "emploi", "titre": "Développeur Python Cloud"})
    assert sig.startswith("emploi|")

def test_offer_signal_stopwords_ignores():
    sig = main._offer_signal({"type": "bourse", "titre": "pour master en France"})
    assert "pour" not in sig and "master" not in sig  # filler et générique exclus


# ------------------ Parseur de pages « 1-3,5 » ------------------
def test_parse_pages_range_and_single():
    assert main._parse_pages("1-3,5", 10) == [0, 1, 2, 4]

def test_parse_pages_hors_bornes_ignore():
    assert main._parse_pages("99", 3) == []

def test_parse_pages_dedup():
    assert main._parse_pages("2,2,3", 5) == [1, 2]


# ------------------ RSS tolérant (feed mal formé) ------------------
def test_rss_regex_extrait_items_avec_ampersand_nu():
    feed = ("<rss><channel>"
            "<item><title>Bourse R&D & Innovation</title><link>https://x/1</link></item>"
            "<item><title><![CDATA[PhD in AI]]></title><link>https://x/2</link></item>"
            "</channel></rss>")
    items = main._rss_regex(feed)
    assert len(items) == 2
    assert items[0]["url"] == "https://x/1"

def test_rss_regex_page_html_renvoie_vide():
    assert main._rss_regex("<html><body>blocked</body></html>") == []


# ------------------ PDF : merge / split / images->PDF / compress ------------------
def _mkpdf(text: str, pages: int) -> bytes:
    import fitz
    d = fitz.open()
    for _ in range(pages):
        p = d.new_page()
        p.insert_text((72, 72), text)
    b = d.tobytes()
    d.close()
    return b

def test_merge_pdfs(tmp_path):
    a = tmp_path / "a.pdf"; a.write_bytes(_mkpdf("A", 2))
    b = tmp_path / "b.pdf"; b.write_bytes(_mkpdf("B", 3))
    out = main.merge_pdfs([str(a), str(b)])
    import fitz
    doc = fitz.open("pdf", out)
    try:
        assert doc.page_count == 5
    finally:
        doc.close()

def test_split_pdf_ranges():
    src = _mkpdf("C", 6)
    out = main.split_pdf(src, "1-2,5")
    import fitz
    doc = fitz.open("pdf", out)
    try:
        assert doc.page_count == 3
    finally:
        doc.close()

def test_compress_pdf_valid_output():
    src = _mkpdf("D", 3)
    data, kb = main.compress_pdf(src, 2000)
    assert data[:5] == b"%PDF-"      # PDF valide
    assert isinstance(kb, int) and kb >= 0    # taille en Ko (peut être 0 pour un mini-PDF)
    assert len(data) > 200            # non vide

def test_extract_text_docx_roundtrip():
    if not main._DocxDocument:
        return  # python-docx absent : skip silencieux
    from docx import Document
    d = Document()
    d.add_paragraph("Hello NexMove")
    d.add_paragraph("Deuxième ligne")
    buf = io.BytesIO(); d.save(buf)
    txt = main.extract_text_docx(buf.getvalue())
    assert "Hello NexMove" in txt and "Deuxième ligne" in txt


# ------------------ MIME helper ------------------
def test_mime_for_pdf_docx_default():
    assert main._mime_for("cv.pdf") == "application/pdf"
    assert "word" in main._mime_for("cv.docx")
    assert main._mime_for("cv.xyz") == "application/octet-stream"


# ------------------ Barre de progression ------------------
def test_progress_bar_shape():
    assert main._progress_bar(3, 8, 8) == "▓▓▓░░░░░ 3/8"
    assert main._progress_bar(0, 5, 5).startswith("░")
    assert main._progress_bar(10, 5, 5).startswith("▓▓▓▓▓")  # borné


# ------------------ Onboarding ADAPTATIF (plan de questions selon les réponses) ------------------
def test_plan_stage_local_sans_nationalite_ni_financement():
    """Un stage/job visant le propre pays : pas de question nationalité/passeport ni financement d'études."""
    plan = main._build_pref_plan({"objectif": "travailler", "pays_cibles": "Bénin"})
    assert "nationalite" not in plan
    assert "financement" not in plan
    assert "certifs_langue" not in plan   # non pertinent pour un job local
    assert plan[0] == "objectif" and "mots_cles" in plan

def test_plan_travail_international_demande_nationalite():
    plan = main._build_pref_plan({"objectif": "travailler", "pays_cibles": "Canada"})
    assert "nationalite" in plan and "certifs_langue" in plan
    assert "financement" not in plan   # un job, pas des études

def test_plan_etudes_demande_tout():
    plan = main._build_pref_plan({"objectif": "étudier", "pays_cibles": "France"})
    for champ in ("objectif", "pays_cibles", "nationalite", "financement", "certifs_langue"):
        assert champ in plan

def test_plan_objectif_inconnu_avant_pays_reste_prudent():
    """Tant que les pays ne sont pas connus, on garde la nationalité (on ne prive pas l'utilisateur)."""
    plan = main._build_pref_plan({"objectif": "travailler"})
    assert "nationalite" in plan   # _vise_international -> True par défaut

def test_vise_international():
    assert main._vise_international({"pays_cibles": "France"}) is True
    assert main._vise_international({"pays_cibles": "tous"}) is True
    assert main._vise_international({"pays_cibles": "Bénin"}) is False
    assert main._vise_international({}) is True   # inconnu -> prudent


# ------------------ Repli : deviner le nom depuis le nom de fichier du CV ------------------
def test_name_from_filename_underscore():
    assert main._name_from_filename("CV_Judicael.pdf") == "Judicael"

def test_name_from_filename_tirets():
    assert main._name_from_filename("cv-jean-dupont.pdf") == "Jean Dupont"

def test_name_from_filename_bruit_seul_donne_vide():
    assert main._name_from_filename("cv.pdf") == ""
    assert main._name_from_filename("mon_cv_final.pdf") == ""

def test_name_from_filename_chiffres_ignores():
    assert main._name_from_filename("CV_Marie_2026_v2.pdf") == "Marie"


# ------------------ Flux d'onboarding adaptatif (bout en bout, hors réseau) ------------------
import asyncio as _asyncio

def _run(coro):
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def test_flux_onboarding_stage_local_ne_demande_jamais_nationalite():
    """Après CV, objectif=travailler + pays=Bénin : la question nationalité ne doit JAMAIS apparaître."""
    session = {"user_id": "t-local", "etape": "CV_RECU", "profil": {}, "historique": [],
               "onboarding_complete": False}
    questions = []
    # 1) confirme le CV -> passe en PREFERENCES, pose 'objectif'
    q, session = _run(main.process_text_message(session, "oui"))
    questions.append(q)
    # 2) répond aux questions jusqu'à sortir de PREFERENCES (garde-fou 12 tours)
    reponses = {"objectif": "travailler", "pays_cibles": "Bénin", "langues_opportunite": "français",
                "niveau": "professionnel", "mots_cles": "cybersécurité"}
    for _ in range(12):
        if session.get("etape") != "PREFERENCES":
            break
        champ = session.get("pref_current")
        rep = reponses.get(champ, "peu importe")
        q, session = _run(main.process_text_message(session, rep))
        questions.append(q)
    joined = "\n".join(questions).lower()
    assert "nationalité" not in joined and "passeport" not in joined
    assert session.get("etape") in ("PREF_TYPE_EMPLOI", "CONFIRMATION")

def test_flux_intention_dormante_captee_avant_cv():
    """Une intention forte tapée avant l'envoi du CV est mémorisée (pending_intent)."""
    session = {"user_id": "t-intent", "etape": "ATTENTE_CV", "profil": {}, "historique": [],
               "onboarding_complete": False}
    msg, session = _run(main.process_text_message(session, "je cherche une bourse de master au Canada"))
    assert session.get("pending_intent", "").startswith("/")
    assert "prêt" in msg.lower() or "noté" in msg.lower()


# ------------------ Commandes /moi et /moncode (chemins sans écriture DB) ------------------
def test_cmd_moi_code_inconnu():
    session = {"user_id": "t-moi", "etape": "ACTIF", "profil": {}, "historique": [],
               "onboarding_complete": True}
    msg, session = _run(main.process_text_message(session, "/moi NEX-ZZZZZ"))
    assert "aucun profil" in msg.lower()

def test_cmd_moi_sans_code_guide():
    session = {"user_id": "t-moi2", "etape": "ACTIF", "profil": {}, "historique": [],
               "onboarding_complete": True}
    msg, session = _run(main.process_text_message(session, "/moi"))
    assert "nex-" in msg.lower()

def test_cmd_moncode_sans_profil():
    session = {"user_id": "t-code", "etape": "WELCOME", "profil": {}, "historique": [],
               "onboarding_complete": False}
    msg, session = _run(main.process_text_message(session, "/moncode"))
    assert "pas encore" in msg.lower()


# ------------------ Quotas : admin illimité + garde gratuite ------------------
def test_quota_admin_illimite(monkeypatch):
    monkeypatch.setattr(main, "_ADMIN_IDS", {"42"})
    sess = {"user_id": "u1", "chat_id": "42"}
    assert main._is_admin(sess) is True
    ok, restant = main._quota_check(sess, "cv", 1)
    assert ok is True and restant == 999          # admin jamais bloqué

def test_quota_non_admin_sous_limite(monkeypatch):
    monkeypatch.setattr(main, "_ADMIN_IDS", {"42"})
    sess = {"user_id": "quota-fresh-user-xyz", "chat_id": "7"}
    assert main._is_admin(sess) is False
    ok, restant = main._quota_check(sess, "feature-inexistante-xyz", 5)
    assert ok is True and restant == 5            # rien consommé encore

def test_quota_limit_zero_desactive(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", "")
    ok, _ = main._quota_check({"user_id": "u9", "chat_id": "9"}, "cv", 0)
    assert ok is True                             # limite 0 => pas de quota


# ------------------ Mode /guide (guidage par capture d'écran) ------------------
def test_cmd_guide_active_le_mode():
    session = {"user_id": "g1", "etape": "ACTIF", "profil": {}, "historique": [],
               "onboarding_complete": True}
    msg, session = _run(main.process_text_message(session, "/guide"))
    assert session.get("guide_mode") is True
    assert "guidage" in msg.lower() and "capture" in msg.lower()

def test_cmd_guide_avec_contexte():
    session = {"user_id": "g2", "etape": "ACTIF", "profil": {}, "historique": [],
               "onboarding_complete": True}
    msg, session = _run(main.process_text_message(session, "/guide campus france"))
    assert session.get("guide_context") == "campus france"

def test_cmd_annuler_quitte_guide():
    session = {"user_id": "g3", "etape": "ACTIF", "guide_mode": True, "profil": {},
               "historique": [], "onboarding_complete": True}
    msg, session = _run(main.process_text_message(session, "/annuler"))
    assert session.get("guide_mode") is False

def test_guide_screenshot_non_image_demande_capture(monkeypatch):
    envois = []
    async def _fake_deliver(session, text, **kw):
        envois.append(text)
    monkeypatch.setattr(main, "deliver_text", _fake_deliver)
    session = {"user_id": "g4", "channel": "telegram", "guide_mode": True, "historique": []}
    _run(main._process_guide_screenshot(session, b"%PDF-1.4 not an image", "doc.pdf"))
    assert any("capture" in m.lower() for m in envois)

def test_guide_screenshot_image_appelle_vision_et_decompte(monkeypatch):
    envois = []
    async def _fake_deliver(session, text, **kw):
        envois.append(text)
    async def _fake_vision(img, mime="image/jpeg", context=""):
        return "1) Tu es sur Études en France. 2) Clique sur « Je candidate »."
    monkeypatch.setattr(main, "deliver_text", _fake_deliver)
    monkeypatch.setattr(main, "analyze_screenshot_vision", _fake_vision)
    # Quota découplé de la vraie base (le singleton usage_store écrit sur data/sessions.db).
    monkeypatch.setattr(main, "_quota_check", lambda s, f, l: (True, 5))
    monkeypatch.setattr(main, "_quota_bump", lambda s, f: None)
    session = {"user_id": "g5", "channel": "telegram", "guide_mode": True, "historique": []}
    _run(main._process_guide_screenshot(session, b"\xff\xd8\xff\xe0 jpeg-bytes", "cap.jpg"))
    assert any("Études en France" in m for m in envois)


def test_guide_screenshot_vide_garde_fou(monkeypatch):
    envois = []
    async def _fake_deliver(session, text, **kw):
        envois.append(text)
    monkeypatch.setattr(main, "deliver_text", _fake_deliver)
    session = {"user_id": "g6", "channel": "telegram", "guide_mode": True, "historique": []}
    _run(main._process_guide_screenshot(session, None, "cap.jpg"))
    assert any("illisible" in m.lower() for m in envois)


# ------------------ Catalogue de sources + sélection adaptative (D2) ------------------
def test_catalog_integrite():
    for s in main.SOURCE_CATALOG:
        assert s["scope"] in ("local", "intl", "both")
        assert s["type"] in ("bourse", "emploi", "fellowship", "ong")
        assert s["url"].startswith("http")

def test_source_active_flag(monkeypatch):
    monkeypatch.delenv("ENABLE_RELIEFWEB", raising=False)
    assert main._source_active({"url": "x"}) is True                     # pas de flag -> actif
    assert main._source_active({"url": "x", "active_env": "ENABLE_RELIEFWEB"}) is False
    monkeypatch.setenv("ENABLE_RELIEFWEB", "1")
    assert main._source_active({"url": "x", "active_env": "ENABLE_RELIEFWEB"}) is True

def test_sources_for_profile_local_exclut_intl():
    urls = main._sources_for_profile({"objectif": "travailler", "pays_cibles": "Bénin"})
    assert "https://www.scholars4dev.com/feed/" not in urls   # intl exclu pour un job local
    assert "https://opportunitydesk.org/feed/" in urls        # 'both' conservé

def test_sources_for_profile_intl_garde_tout():
    urls = main._sources_for_profile({"objectif": "étudier", "pays_cibles": "France"})
    assert "https://www.scholars4dev.com/feed/" in urls       # intl gardé pour études à l'étranger


# ------------------ IRCC Entrée express : parsing des rondes temps réel (D4c) ------------------
_IRCC_SAMPLE = {"rounds": [
    {"drawNumber": "339", "drawDate": "2026-08-25", "drawName": "Healthcare and social services occupations (Version 1)",
     "drawSize": "1,500", "drawCRS": "463"},
    {"drawNumber": "338", "drawDate": "2026-08-12", "drawName": "French language proficiency (Version 1)",
     "drawSize": "2,500", "drawCRS": "470"},
    {"drawNumber": "337", "drawDate": "2026-08-06", "drawName": "General",
     "drawSize": "3,000", "drawCRS": "518"},
]}

def test_parse_ee_rounds_extrait_categories():
    rounds = main._parse_ee_rounds(_IRCC_SAMPLE, limit=6)
    assert len(rounds) == 3
    assert rounds[0]["categorie"].startswith("Healthcare")
    assert rounds[0]["crs"] == "463" and rounds[0]["invitations"] == "1,500"

def test_parse_ee_rounds_tolerant_vide():
    assert main._parse_ee_rounds({}, limit=6) == []
    assert main._parse_ee_rounds({"rounds": [None, 42]}, limit=6) == []

def test_format_ircc_rounds_lisible():
    txt = main._format_ircc_rounds(main._parse_ee_rounds(_IRCC_SAMPLE))
    assert "Healthcare" in txt and "CRS 463" in txt and "1,500 invitations" in txt
    assert txt.count("•") == 3

def test_format_ircc_rounds_vide():
    assert main._format_ircc_rounds([]) == ""


def test_fetch_ircc_rounds_cache_hit(monkeypatch):
    # Cache déjà peuplé -> pas d'appel réseau, on renvoie la valeur en cache.
    sample = main._parse_ee_rounds(_IRCC_SAMPLE, limit=12)
    monkeypatch.setattr(main.cache, "get", lambda k: sample)
    rounds = _run(main.fetch_ircc_rounds(2))
    assert len(rounds) == 2 and rounds[0]["categorie"].startswith("Healthcare")


# ------------------ /simulation : coach d'entretien interactif (extra) ------------------
def test_sim_type_key():
    assert main._sim_type_key("visa étudiant") == "visa"
    assert main._sim_type_key("emploi dev") == "emploi"
    assert main._sim_type_key("") == "campus"
    assert main._sim_type_key("campus france") == "campus"

def test_sim_fallback_question_bornee():
    session = {"sim_type": "visa", "sim_count": 99}
    q = main._sim_fallback_q(session)
    assert isinstance(q, str) and len(q) > 5     # index borné, pas d'IndexError

def test_cmd_simulation_exige_onboarding():
    session = {"user_id": "s0", "etape": "WELCOME", "profil": {}, "historique": [],
               "onboarding_complete": False}
    msg, session = _run(main.process_text_message(session, "/simulation"))
    assert "cv" in msg.lower() and not session.get("sim_mode")

def test_flux_simulation_complet(monkeypatch):
    # LLM stubbé : questions/feedback déterministes, aucun réseau.
    async def _fake_groq(system, prompt, temperature=0.2, max_tokens=1000, json_mode=True, **kw):
        if not json_mode:
            return "Bilan : bon projet, travaille les chiffres."
        return {"feedback": "Bien.", "question": "Question suivante ?"}
    monkeypatch.setattr(main, "call_groq", _fake_groq)
    monkeypatch.setattr(main, "SIM_MAX_Q", 3)
    session = {"user_id": "s1", "etape": "ACTIF", "profil": {"identite": {"nom": "X"}},
               "historique": [], "onboarding_complete": True}
    main._apply_premium(session, "premium", 30)   # premium => /simulation illimité (pas de quota)
    msg, session = _run(main.process_text_message(session, "/simulation campus france"))
    assert session.get("sim_mode") is True and "❓" in msg
    # 3 réponses -> à la 3e, bilan + fin de simulation
    for i in range(3):
        msg, session = _run(main.process_text_message(session, f"réponse {i}"))
    assert session.get("sim_mode") is False
    assert "bilan" in msg.lower()

def test_cmd_annuler_quitte_simulation():
    session = {"user_id": "s2", "etape": "ACTIF", "sim_mode": True, "profil": {},
               "historique": [], "onboarding_complete": True}
    msg, session = _run(main.process_text_message(session, "/annuler"))
    assert session.get("sim_mode") is False


# ------------------ Alertes mots-clés personnalisées (extra) ------------------
def test_alertes_match():
    assert main._alertes_match({"titre": "Bourse Master Cybersécurité", "raison": ""}, ["cybersécurité"]) == "cybersécurité"
    assert main._alertes_match({"titre": "Stage Data", "raison": "cloud AWS"}, ["cloud"]) == "cloud"
    assert main._alertes_match({"titre": "Offre RH"}, ["data", "cloud"]) == ""
    assert main._alertes_match({"titre": "x"}, []) == ""

def test_cmd_alerte_ajout_liste_suppr():
    session = {"user_id": "a1", "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}
    msg, session = _run(main.process_text_message(session, "/alerte cybersécurité"))
    assert "ajoutée" in msg.lower() and session["alertes"] == ["cybersécurité"]
    # doublon
    msg, session = _run(main.process_text_message(session, "/alerte cybersécurité"))
    assert "déjà" in msg.lower() and session["alertes"] == ["cybersécurité"]
    # liste
    msg, session = _run(main.process_text_message(session, "/alerte"))
    assert "cybersécurité" in msg.lower()
    # suppression
    msg, session = _run(main.process_text_message(session, "/alerte off cybersécurité"))
    assert session["alertes"] == []

def test_cmd_alerte_trop_courte():
    session = {"user_id": "a2", "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}
    msg, session = _run(main.process_text_message(session, "/alerte x"))
    assert "2 lettres" in msg and not session.get("alertes")

def test_cmd_alerte_cap_premium_10():
    # Premium : plafond à 10 alertes.
    session = {"user_id": "a3", "etape": "ACTIF", "profil": {}, "historique": [],
               "onboarding_complete": True, "alertes": [f"kw{i}" for i in range(10)]}
    main._apply_premium(session, "premium", 30)
    msg, session = _run(main.process_text_message(session, "/alerte onzieme"))
    assert "limite atteinte" in msg.lower() and len(session["alertes"]) == 10

def test_cmd_alerte_cap_free_1():
    # Gratuit : plafond à 1 alerte, message d'upsell.
    session = {"user_id": "a4", "chat_id": "7", "etape": "ACTIF", "profil": {}, "historique": [],
               "onboarding_complete": True, "alertes": ["cybersécurité"]}
    msg, session = _run(main.process_text_message(session, "/alerte cloud"))
    assert "limite atteinte" in msg.lower() and len(session["alertes"]) == 1


# ------------------ Feuille de route visuelle PNG (extra) ------------------
def test_render_timeline_png_valide():
    if not main._PIL_OK:
        return  # Pillow absent : skip
    png = main.render_timeline_png(main.CF_STAGES, 2, "Test", [("Master X", "2026-09-01", "en_preparation")])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"     # signature PNG
    assert len(png) > 1000

def test_render_timeline_png_sans_deadlines():
    if not main._PIL_OK:
        return
    png = main.render_timeline_png(["Étape 1", "Étape 2"], 0, "Court")
    assert png[:4] == b"\x89PNG"

def test_tl_wrap_coupe():
    lines = main._tl_wrap("un deux trois quatre cinq six sept huit", n=12)
    assert all(len(l) <= 12 for l in lines) and len(lines) >= 2

def test_cmd_timeline_exige_onboarding():
    session = {"user_id": "tl0", "etape": "WELCOME", "profil": {}, "historique": [],
               "onboarding_complete": False}
    msg, session = _run(main.process_text_message(session, "/timeline"))
    assert "profil" in msg.lower() or "cv" in msg.lower()

def test_cmd_timeline_genere_png(monkeypatch):
    envois = []
    async def _fake_deliver_file(session, name, data, caption=""):
        envois.append((name, data))
        return True
    monkeypatch.setattr(main, "deliver_file", _fake_deliver_file)
    session = {"user_id": "tl1", "channel": "telegram", "etape": "ACTIF",
               "profil": {"identite": {"nom": "Judicael"}}, "historique": [],
               "onboarding_complete": True, "cf_stage": 3}
    msg, session = _run(main.process_text_message(session, "/timeline"))
    if main._PIL_OK:
        assert envois and envois[0][0].endswith(".png")
        assert envois[0][1][:4] == b"\x89PNG"


# ------------------ Accueil moins rigide + parcours sans CV (extra) ------------------
def test_pitch_question_detecte():
    assert main._is_pitch_question("à quoi tu sers")
    assert main._is_pitch_question("explique moi à quoi tu sers")
    assert main._is_pitch_question("bonjour")
    assert main._is_pitch_question("c'est quoi ce bot")
    assert not main._is_pitch_question("trouve moi un stage")

def test_wants_no_cv_detecte():
    assert main._wants_no_cv("je n'ai pas de cv")
    assert main._wants_no_cv("je veux créer un cv")
    assert main._wants_no_cv("pas encore de cv")
    assert not main._wants_no_cv("voici mon cv")

def test_accueil_repond_avant_de_demander_cv():
    """« à quoi tu sers » AVANT l'onboarding -> on explique, on ne renvoie pas juste « envoie ton CV »."""
    session = {"user_id": "p1", "etape": "ATTENTE_CV", "profil": {}, "historique": [],
               "onboarding_complete": False}
    msg, session = _run(main.process_text_message(session, "explique moi à quoi tu sers"))
    assert "opportunités" in msg.lower() or "orientation" in msg.lower()
    assert "NexMove" in msg

def test_message_accueil_mentionne_creercv():
    session = {"user_id": "p2", "etape": "ATTENTE_CV", "profil": {}, "historique": [],
               "onboarding_complete": False}
    msg, session = _run(main.process_text_message(session, "je ne sais pas trop"))
    assert "/creercv" in msg

def test_flux_creercv_complet(monkeypatch):
    # LLM + génération PDF + livraison stubbés (hors réseau/rendu).
    async def _fake_groq(system, prompt, temperature=0.2, max_tokens=1000, json_mode=True, **kw):
        return {"est_cv": True, "identite": {"nom": "Judicael Doe"},
                "formation": [{"diplome": "Licence Informatique", "etablissement": "UAC"}],
                "experience": [], "competences": {"techniques": ["python", "réseaux"]},
                "resume_profil": "Étudiant en informatique."}
    envois = []
    async def _fake_deliver_file(session, name, data, caption=""):
        envois.append(name); return True
    monkeypatch.setattr(main, "call_groq", _fake_groq)
    monkeypatch.setattr(main, "deliver_file", _fake_deliver_file)
    monkeypatch.setattr(main, "_quota_bump", lambda s, f: None)
    session = {"user_id": "cvb1", "channel": "telegram", "etape": "ATTENTE_CV", "profil": {},
               "historique": [], "onboarding_complete": False}
    # Déclenche via « je n'ai pas de cv »
    msg, session = _run(main.process_text_message(session, "je n'ai pas de cv"))
    assert session["etape"] == "CVBUILD" and "prénom" in msg.lower()
    for rep in ["Judicael Doe", "Licence info UAC 2024", "aucune", "python, réseaux", "français natif"]:
        msg, session = _run(main.process_text_message(session, rep))
    # Fin : profil créé, CV livré, on passe en CV_RECU
    assert session["etape"] == "CV_RECU"
    assert session["profil"]["identite"]["nom"] == "Judicael Doe"
    assert any(n.endswith(".pdf") for n in envois)

def test_creercv_annulable():
    session = {"user_id": "cvb2", "etape": "CVBUILD", "cvbuild_step": 1, "cvbuild_data": {"nom": "X"},
               "historique": [], "onboarding_complete": False}
    msg, session = _run(main.process_text_message(session, "/annuler"))
    assert session["etape"] == "ATTENTE_CV"


# ------------------ Abonnement premium : tiers, quotas, activation (extra) ------------------
def test_apply_premium_et_tier():
    s = {"user_id": "prem1", "chat_id": "9"}
    exp = main._apply_premium(s, "premium", 30)
    assert s["premium_tier"] == "premium" and s["premium_until"] == exp
    assert main._user_tier(s) == "premium" and main._is_premium(s)

def test_premium_expire_retombe_en_free():
    from datetime import datetime, timezone, timedelta
    s = {"user_id": "prem2", "chat_id": "9",
         "premium_tier": "premium",
         "premium_until": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
    assert main._user_tier(s) == "free" and not main._is_premium(s)

def test_premium_prolonge_sur_temps_restant():
    from datetime import datetime, timezone
    s = {"user_id": "prem3"}
    exp1 = main._apply_premium(s, "premium", 30)
    exp2 = main._apply_premium(s, "premium", 30)   # empile
    d1 = datetime.fromisoformat(exp1); d2 = datetime.fromisoformat(exp2)
    assert (d2 - d1).days >= 29

def test_quota_premium_illimite(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", "")
    s = {"user_id": "prem4", "chat_id": "7"}
    main._apply_premium(s, "premium", 30)
    ok, restant = main._quota_check(s, "cv", 1)
    assert ok and restant == 999          # premium jamais bloqué

def test_cmd_premium_active_un_code(monkeypatch):
    # Redeem stubbé pour ne pas toucher la vraie base premium.
    monkeypatch.setattr(main.premium_store, "redeem", lambda code, uid: {"ok": True, "tier": "premium", "days": 30})
    monkeypatch.setattr(main.session_manager, "set", lambda uid, s: None)
    s = {"user_id": "prem5", "channel": "telegram", "etape": "ACTIF", "profil": {},
         "historique": [], "onboarding_complete": True}
    msg, s = _run(main.process_text_message(s, "/premium PRM-ABCDEFGH"))
    assert "activé" in msg.lower() and main._is_premium(s)

def test_cmd_premium_code_invalide(monkeypatch):
    monkeypatch.setattr(main.premium_store, "redeem", lambda code, uid: {"ok": False, "reason": "introuvable"})
    s = {"user_id": "prem6", "channel": "telegram", "etape": "ACTIF", "profil": {},
         "historique": [], "onboarding_complete": True}
    msg, s = _run(main.process_text_message(s, "/premium PRM-XXXX"))
    assert "impossible" in msg.lower() and not main._is_premium(s)

def test_cmd_gencodes_reserve_admin(monkeypatch):
    monkeypatch.setattr(main, "_ADMIN_IDS", {"42"})
    s = {"user_id": "u", "chat_id": "7", "historique": [], "onboarding_complete": True}
    msg, s = _run(main.process_text_message(s, "/gencodes premium 30 5"))
    assert "administrateur" in msg.lower()

def test_cmd_monabo_free():
    s = {"user_id": "prem7", "chat_id": "7", "historique": [], "onboarding_complete": True}
    msg, s = _run(main.process_text_message(s, "/monabo"))
    assert "gratuit" in msg.lower()


# ------------------ Admin multiple + /id (setup admin) ------------------
def test_is_admin_multi(monkeypatch):
    monkeypatch.setattr(main, "_ADMIN_IDS", {"42", "22990000000"})
    assert main._is_admin({"chat_id": "42", "user_id": "x"})
    assert main._is_admin({"chat_id": "z", "user_id": "22990000000"})   # numéro WhatsApp
    assert not main._is_admin({"chat_id": "7", "user_id": "8"})

def test_cmd_id_donne_identifiants():
    s = {"user_id": "u9", "chat_id": "12345", "channel": "telegram", "historique": []}
    msg, s = _run(main.process_text_message(s, "/id"))
    assert "12345" in msg and "chat_id" in msg


# ------------------ Sources locales enrichies (Bénin/UEMOA) ------------------
def test_local_sources_txt_benin():
    txt = main._local_sources_txt("Bénin")
    assert "emploibenin.com" in txt and "jobbenin.com" in txt and "offresdemplois.bj" in txt
    assert "Jooble" in txt   # sources régionales incluses

def test_local_sources_txt_pays_inconnu_garde_regional():
    txt = main._local_sources_txt("Atlantide")
    assert "Jooble" in txt or "Talent2Africa" in txt   # régional toujours présent

def test_local_sources_extra_env(monkeypatch):
    monkeypatch.setenv("LOCAL_SOURCES_EXTRA_BENIN", "monsupersite.bj,autre.bj")
    txt = main._local_sources_txt("Bénin")
    assert "monsupersite.bj" in txt and "autre.bj" in txt


# ------------------ Robustesse chat_id (bug "chat not found" sur CV) ------------------
def test_chatid_fallback_logic():
    # Simule la logique défensive de /api/chat-cv : chat_id "0" ne doit pas écraser un bon chat_id.
    def resolve(incoming, stored, uid):
        session = {"chat_id": stored} if stored else {}
        if incoming and str(incoming) not in ("0", "", "None"):
            session["chat_id"] = str(incoming)
        elif not session.get("chat_id") or str(session.get("chat_id")) in ("0", "", "None"):
            session["chat_id"] = str(uid)
        return session["chat_id"]
    assert resolve("0", "514773914", "514773914") == "514773914"   # ne pas écraser le bon
    assert resolve("", None, "514773914") == "514773914"           # repli sur user_id
    assert resolve("999", "111", "111") == "999"                   # un chat_id valide gagne
    assert resolve("0", None, "42") == "42"                        # "0" + rien -> user_id


# ------------------ _valid_id : rejet des identifiants bidon (bug n8n "undefined") ------------------
def test_valid_id():
    assert main._valid_id("514773914")
    assert not main._valid_id("undefined")
    assert not main._valid_id("null")
    assert not main._valid_id("0")
    assert not main._valid_id("")
    assert not main._valid_id(None)
