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
