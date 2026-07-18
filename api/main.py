import os, io, json, base64, logging, secrets, time, asyncio, sqlite3
from datetime import datetime, timezone
from typing import Optional, Any

import fitz
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Security, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field, validator
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_JUSTIFY

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "service": "forge-nex-api", "msg": record.getMessage(), "module": record.module})

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("forge-nex")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL      = "llama-3.3-70b-versatile"
GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"
FORGE_NEX_API_KEY = os.getenv("FORGE_NEX_API_KEY", "")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

_rate_store: dict[str, list[float]] = {}

def check_rate_limit(user_id: str, max_calls: int = 20, window_sec: int = 60) -> bool:
    now = time.time()
    calls = [t for t in _rate_store.get(user_id, []) if now - t < window_sec]
    if len(calls) >= max_calls:
        return False
    calls.append(now)
    _rate_store[user_id] = calls
    return True

api_key_header = APIKeyHeader(name="X-Forge-Nex-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not FORGE_NEX_API_KEY:
        logger.warning("FORGE_NEX_API_KEY non configurée — mode dev")
        return True
    if not api_key or not secrets.compare_digest(api_key, FORGE_NEX_API_KEY):
        raise HTTPException(status_code=401, detail="Clé API invalide")
    return True

app = FastAPI(title="Forge NEX API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=50)
    chat_id: str = Field(..., min_length=1)
    username: str = Field(default="utilisateur", max_length=100)
    text: str = Field(default="", max_length=4096)
    message_type: str = Field(default="text")
    document_file_id: Optional[str] = None

    @validator('user_id', 'chat_id')
    def sanitize_ids(cls, v):
        return str(v).strip()[:50]

class GenerateDocumentsRequest(BaseModel):
    user_id: str
    offre_id: str
    profil: dict
    offre: dict

class MobilityRequest(BaseModel):
    user_id: str
    chat_id: str
    cible: str = Field(default="opportunites internationales informatique")
    contraintes: dict = Field(default={})

async def call_groq(system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 1000, json_mode: bool = True, retries: int = 3) -> Any:
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY manquante")
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    last_error = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(GROQ_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, json=payload)
            if r.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code != 200:
                raise HTTPException(502, f"Groq erreur {r.status_code}")
            raw = r.json()["choices"][0]["message"]["content"]
            if json_mode:
                try:
                    return json.loads(raw)
                except:
                    return json.loads(raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip())
            return raw
        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
    raise HTTPException(502, f"Groq indisponible: {last_error}")

class SessionManager:
    def __init__(self, path: str = "data/sessions.db"):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE IF NOT EXISTS sessions (user_id TEXT PRIMARY KEY, data TEXT)")
        con.commit(); con.close()
    def get(self, user_id: str) -> Optional[dict]:
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT data FROM sessions WHERE user_id=?", (str(user_id),)).fetchone()
        con.close()
        return json.loads(row[0]) if row else None
    def set(self, user_id: str, session: dict):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("INSERT INTO sessions(user_id, data) VALUES(?, ?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
                    (str(user_id), json.dumps(session, ensure_ascii=False)))
        con.commit(); con.close()
    def count(self) -> int:
        con = sqlite3.connect(self._path, timeout=10)
        n = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        con.close()
        return int(n)
    def create_default(self, user_id: str, chat_id: str, username: str) -> dict:
        return {"user_id": str(user_id), "chat_id": str(chat_id), "username": username, "etape": "WELCOME", "profil": {}, "historique": [], "cv_parsed": False, "cv_file_id": None, "onboarding_complete": False, "created_at": datetime.now(timezone.utc).isoformat()}

session_manager = SessionManager()

ETAPE_INSTRUCTIONS = {
    "WELCOME": "Accueille chaleureusement l'utilisateur. Présente Forge NEX en 2 phrases: agent IA qui trouve des opportunités (emploi, bourses, fellowships, mobilité internationale) adaptées à son profil. Demande d'envoyer le CV en PDF.",
    "ATTENTE_CV": "L'utilisateur doit envoyer son CV en PDF. Rappelle-lui brièvement.",
    "CV_RECU": "Le CV a été analysé. L'utilisateur confirme les informations. Réponds Oui pour passer aux préférences.",
    "PREFERENCES": "Collecte des préférences (gérée par le code).",
    "CONFIRMATION": "Résume le profil complet et demande confirmation finale (Oui pour démarrer).",
    "ACTIF": "L'onboarding est terminé. Commandes: /mobilite [pays/domaine], /status, /profil, /aide. Réponds aux demandes de l'utilisateur de façon utile et concise."
}

REPONSES_POSITIVES = {"oui", "yes", "ok", "correct", "exacte", "c'est bon", "parfait", "valide", "confirme"}

def detecter_reponse_positive(text: str) -> bool:
    return any(r in text.lower().strip() for r in REPONSES_POSITIVES)

PREF_QUESTIONS = [
    ("objectif", "🎯 Quel est ton objectif principal ?\n(travailler / étudier / bourse / fellowship / tous)"),
    ("nationalite", "🛂 Quelle est ta nationalité (pays du passeport) ?"),
    ("pays_cibles", "🌍 Quels pays ou régions vises-tu ?\n(ex : France, Canada, Europe francophone, ou « tous »)"),
    ("financement", "💰 Financement : bourse indispensable, tu peux auto-financer, ou peu importe ?"),
    ("certifs_langue", "🗣️ Certifications de langue ?\n(IELTS/TOEFL/TCF/DELF + score, ou « aucune »)"),
    ("langues_opportunite", "🌐 Langue des opportunités ? (français / anglais / les deux)"),
    ("niveau", "🎓 Ton niveau ? (étudiant / professionnel)"),
    ("mots_cles", "🔑 Des mots-clés à cibler ?\n(ex : cybersécurité, cloud, réseau — ou « aucun »)"),
]

AIDE_TXT = ("🤖 *Forge NEX — commandes*\n"
            "/start — (re)démarrer l'onboarding\n"
            "/profil — voir ton profil\n"
            "/mobilite <pays ou domaine> — analyse mobilité\n"
            "/status — état de tes candidatures\n"
            "/aide — cette aide\n"
            "/supprimer — effacer mes données")

def _push(session, role, content):
    h = session.get("historique", [])
    h.append({"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()})
    session["historique"] = h[-30:]

def _resume_prefs(prefs):
    return ("📋 *Récapitulatif de ton profil de recherche :*\n"
            f"• Objectif : {prefs.get('objectif','—')}\n"
            f"• Nationalité : {prefs.get('nationalite','—')}\n"
            f"• Pays cibles : {prefs.get('pays_cibles','—')}\n"
            f"• Financement : {prefs.get('financement','—')}\n"
            f"• Certifs langue : {prefs.get('certifs_langue','—')}\n"
            f"• Langue des offres : {prefs.get('langues_opportunite','—')}\n"
            f"• Niveau : {prefs.get('niveau','—')}\n"
            f"• Mots-clés : {prefs.get('mots_cles','—')}\n\n"
            "Tout est correct ? Réponds *Oui* pour lancer, ou *Non* pour recommencer.")

async def process_text_message(session: dict, text: str) -> tuple[str, dict]:
    t = (text or "").strip()
    low = t.lower()
    now = datetime.now(timezone.utc).isoformat()

    if low.startswith("/start"):
        session["etape"] = "ATTENTE_CV"; session["profil"] = {}; session["historique"] = []
        session["cv_parsed"] = False; session["cv_file_id"] = None
        session["onboarding_complete"] = False; session["pref_index"] = 0
        msg = ("👋 *Bienvenue sur Forge NEX !*\nJe t'aide à trouver emplois, bourses, fellowships et "
               "opportunités de mobilité adaptés à ton profil.\n\n📄 Pour commencer, envoie-moi ton *CV en PDF*.")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/aide") or low.startswith("/help"):
        _push(session, "user", t); _push(session, "assistant", AIDE_TXT); session["derniere_activite"] = now
        return AIDE_TXT, session

    if low.startswith("/profil"):
        profil = session.get("profil", {}) or {}
        if profil:
            ident = profil.get("identite", {})
            msg = f"👤 *Ton profil*\nNom : {ident.get('nom','—')}\nÉtape : {session.get('etape','—')}\n\n" + _resume_prefs(profil.get("preferences", {}) or {})
        else:
            msg = "Aucun profil pour l'instant. Fais /start puis envoie ton CV en PDF."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/supprimer"):
        cleared = {"user_id": session.get("user_id"), "chat_id": session.get("chat_id"),
                   "username": session.get("username"), "etape": "WELCOME", "profil": {},
                   "historique": [], "cv_parsed": False, "cv_file_id": None,
                   "onboarding_complete": False, "pref_index": 0, "derniere_activite": now}
        msg = "🗑️ Tes données ont été effacées. Fais /start pour recommencer."
        cleared["historique"] = [{"role": "assistant", "content": msg, "ts": now}]
        return msg, cleared

    if low.startswith("/mobilite") or low.startswith("/mobilité"):
        parts = t.split(maxsplit=1)
        cible = parts[1].strip() if len(parts) > 1 else ""
        try:
            res = await run_osint(session.get("profil", {}) or {}, cible)
            msg = res.get("message") or "Aucune opportunité trouvée pour le moment."
        except Exception as e:
            logger.error(f"Erreur mobilite: {e}")
            msg = "😕 L'analyse mobilité a échoué, réessaie dans un instant."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/status"):
        prefs = (session.get("profil", {}) or {}).get("preferences", {}) or {}
        etape = session.get("etape", "WELCOME")
        if session.get("onboarding_complete"):
            msg = ("📊 *Statut*\nProfil : ✅ complété et actif\n"
                   f"Objectif : {prefs.get('objectif','—')} · Pays : {prefs.get('pays_cibles','—')}\n\n"
                   "Le suivi détaillé des candidatures arrive bientôt. Utilise /mobilite pour explorer.")
        else:
            msg = f"📊 *Statut*\nOnboarding en cours (étape : {etape}).\nFais /start pour (re)commencer."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    etape = session.get("etape", "WELCOME")

    if etape == "CV_RECU" and detecter_reponse_positive(t):
        session["etape"] = "PREFERENCES"; session["pref_index"] = 0
        q = PREF_QUESTIONS[0][1]
        _push(session, "user", t); _push(session, "assistant", q); session["derniere_activite"] = now
        return q, session

    if etape == "PREFERENCES":
        idx = session.get("pref_index", 0)
        profil = session.get("profil", {}) or {}
        prefs = profil.get("preferences", {}) or {}
        if 0 <= idx < len(PREF_QUESTIONS):
            prefs[PREF_QUESTIONS[idx][0]] = t
            profil["preferences"] = prefs; session["profil"] = profil
        idx += 1; session["pref_index"] = idx
        _push(session, "user", t)
        if idx < len(PREF_QUESTIONS):
            q = PREF_QUESTIONS[idx][1]
            _push(session, "assistant", q); session["derniere_activite"] = now
            return q, session
        session["etape"] = "CONFIRMATION"
        resume = _resume_prefs(prefs)
        _push(session, "assistant", resume); session["derniere_activite"] = now
        return resume, session

    if etape == "CONFIRMATION":
        _push(session, "user", t)
        if detecter_reponse_positive(t):
            session["etape"] = "ACTIF"; session["onboarding_complete"] = True
            msg = ("🎉 *Profil validé !* Je vais chercher des opportunités adaptées.\n\n"
                   "Commandes : /mobilite <pays/domaine>, /status, /profil, /aide.")
        else:
            session["etape"] = "PREFERENCES"; session["pref_index"] = 0
            msg = "Pas de souci, on reprend.\n\n" + PREF_QUESTIONS[0][1]
        _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    historique = session.get("historique", [])
    historique.append({"role": "user", "content": t})
    profil_str = json.dumps(session.get("profil", {}), ensure_ascii=False)[:800]
    system = f"""Tu es Forge NEX Assistant, agent IA de recherche d'opportunités (emploi, bourses, fellowships, mobilité).
ETAPE: {etape}
PROFIL: {profil_str}
INSTRUCTIONS: {ETAPE_INSTRUCTIONS.get(etape, ETAPE_INSTRUCTIONS["ACTIF"])}
REGLES: francais, max 120 mots, chaleureux, ne redemande jamais le CV si etape=ACTIF.
JSON: {{"message":"..."}}"""
    try:
        llm = await call_groq(system, t, temperature=0.3, max_tokens=350)
        message = llm.get("message", "Je suis là pour t'aider.")
    except Exception as e:
        logger.error(f"Erreur LLM: {e}")
        message = "Désolé, souci technique. Reformule ta demande."
    historique.append({"role": "assistant", "content": message, "ts": now})
    session["historique"] = historique[-30:]; session["derniere_activite"] = now
    return message, session

def session_to_sheets_row(session: dict) -> dict:
    return {
        "user_id": str(session.get("user_id", "")),
        "chat_id": str(session.get("chat_id", "")),
        "username": session.get("username", ""),
        "etape": session.get("etape", "WELCOME"),
        "profil": json.dumps(session.get("profil", {}), ensure_ascii=False),
        "historique": json.dumps(session.get("historique", []), ensure_ascii=False),
        "cv_file_id": session.get("cv_file_id", "") or "",
        "cv_parsed": str(session.get("cv_parsed", False)).lower(),
        "onboarding_complete": str(session.get("onboarding_complete", False)).lower(),
        "derniere_activite": session.get("derniere_activite", datetime.now(timezone.utc).isoformat())
    }

def extract_text_pdf(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(p.get_text("text") for p in doc if p.get_text("text").strip())
        doc.close()
        return text.strip()
    except Exception as e:
        raise HTTPException(422, f"Lecture PDF impossible: {e}")

def pdf_to_b64(buf: io.BytesIO) -> str:
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

BLEU = HexColor("#1a237e")
GRIS = HexColor("#546e7a")

def build_cv_pdf(profil: dict, titre: str, resume: str, competences: list) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8*cm, rightMargin=1.8*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    s_nom = ParagraphStyle("n", fontSize=20, textColor=BLEU, fontName="Helvetica-Bold", spaceAfter=2)
    s_sous = ParagraphStyle("s", fontSize=11, textColor=GRIS, fontName="Helvetica-Oblique", spaceAfter=8)
    s_sec = ParagraphStyle("se", fontSize=11, textColor=BLEU, fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)
    s_body = ParagraphStyle("b", fontSize=9.5, fontName="Helvetica", spaceAfter=3, leading=13)
    s_bullet = ParagraphStyle("bu", fontSize=9.5, fontName="Helvetica", spaceAfter=2, leftIndent=12)
    identite = profil.get("identite", {})
    formation = profil.get("formation", [])
    experience = profil.get("experience", [])
    els = []
    els.append(Paragraph(identite.get("nom", "Candidat"), s_nom))
    els.append(Paragraph(titre, s_sous))
    contacts = [x for x in [identite.get("email"), identite.get("telephone"), identite.get("localisation")] if x]
    if contacts:
        els.append(Paragraph(" · ".join(contacts), s_body))
    els.append(HRFlowable(width="100%", thickness=2, color=BLEU, spaceAfter=8))
    if resume:
        els.append(Paragraph("PROFIL", s_sec))
        els.append(Paragraph(resume, s_body))
    if competences:
        els.append(Paragraph("COMPÉTENCES", s_sec))
        els.append(Paragraph(" · ".join(competences[:16]), s_body))
    if experience:
        els.append(Paragraph("EXPÉRIENCE", s_sec))
        for exp in experience[:4]:
            els.append(Paragraph(f"<b>{exp.get('poste','')}</b> — {exp.get('organisation','')}", s_body))
            for m in exp.get("missions", [])[:4]:
                els.append(Paragraph(f"• {m}", s_bullet))
            els.append(Spacer(1, 4))
    if formation:
        els.append(Paragraph("FORMATION", s_sec))
        for f in formation[:3]:
            els.append(Paragraph(f"<b>{f.get('diplome','')}</b> — {f.get('etablissement','')}", s_body))
    doc.build(els)
    return buf

@app.post("/api/chat")
async def chat(request: ChatRequest, _auth: bool = Depends(verify_api_key)):
    uid = request.user_id
    logger.info(f"[chat] user={uid} text={request.text[:50]!r}")
    if not check_rate_limit(uid):
        return {"message": "⚠️ Trop de messages. Attends 1 minute.", "chat_id": request.chat_id, "session_row": {}}
    session = session_manager.get(uid) or session_manager.create_default(uid, request.chat_id, request.username)
    session["chat_id"] = request.chat_id
    session["username"] = request.username
    message, session = await process_text_message(session, request.text)
    session_manager.set(uid, session)
    return {"message": message, "chat_id": request.chat_id, "session_row": session_to_sheets_row(session), "etape": session["etape"], "onboarding_complete": session["onboarding_complete"]}

@app.post("/api/chat-cv")
async def chat_cv(file: UploadFile = File(...), user_id: str = Form("unknown"), chat_id: str = Form("0"), username: str = Form("utilisateur"), _auth: bool = Depends(verify_api_key)):
    logger.info(f"[chat-cv] user={user_id} file={file.filename}")
    if not (file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")):
        raise HTTPException(415, "PDF requis.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, "Max 20MB.")
    cv_text = extract_text_pdf(pdf_bytes)
    session = session_manager.get(user_id) or session_manager.create_default(user_id, chat_id, username)
    if not cv_text or len(cv_text.strip()) < 50:
        return {"success": False, "message": "❌ PDF vide ou scanné sans OCR.\n\nEnvoie un PDF avec texte sélectionnable (généré depuis Word ou LibreOffice).", "chat_id": chat_id, "session_row": session_to_sheets_row(session)}
    system = "Tu es expert en analyse de CV. Extrais toutes les informations. JSON uniquement."
    prompt = f"""Analyse ce CV:
{{"identite":{{"nom":"","email":"","telephone":"","localisation":"","linkedin":"","github":"","langues":[]}},"formation":[{{"diplome":"","domaine":"","etablissement":"","ville":"","pays":"","annee":""}}],"competences":{{"techniques":[],"securite":[],"outils":[],"frameworks":[],"soft_skills":[]}},"experience":[{{"poste":"","organisation":"","type":"","duree":"","date_debut":"","date_fin":"","localisation":"","missions":[]}}],"projets":[{{"nom":"","description":"","technologies":[],"url":""}}],"certifications":[],"preferences":{{"types_opportunite":["emploi","bourse","fellowship"],"niveau":"professionnel","langues_opportunite":["fr","en"],"delai_min_jours":14,"mots_cles":[],"geographie":[]}},"niveau_global":"junior|mid|senior","resume_profil":""}}
CV: {cv_text[:6000]}"""
    profil = await call_groq(system, prompt, temperature=0.1, max_tokens=2500)
    nom = profil.get("identite", {}).get("nom", "N/A")
    diplome = profil.get("formation", [{}])[0].get("diplome", "N/A") if profil.get("formation") else "N/A"
    skills = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))[:5]
    message = f"✅ *CV analysé avec succès !*\n\n👤 *Nom :* {nom}\n🎓 *Formation :* {diplome}\n💻 *Compétences :* {', '.join(skills)}\n\nCes informations sont-elles correctes ? Réponds *Oui* pour continuer."
    session["etape"] = "CV_RECU"
    session["profil"] = profil
    session["cv_parsed"] = True
    session["derniere_activite"] = datetime.now(timezone.utc).isoformat()
    historique = session.get("historique", [])
    historique.append({"role": "assistant", "content": message, "ts": datetime.now(timezone.utc).isoformat()})
    session["historique"] = historique[-30:]
    session_manager.set(user_id, session)
    logger.info(f"[chat-cv] OK — {nom} → CV_RECU")
    return {"success": True, "message": message, "chat_id": chat_id, "profil": profil, "session_row": session_to_sheets_row(session), "parsed_at": datetime.now(timezone.utc).isoformat()}

@app.post("/api/parse-cv")
async def parse_cv(file: UploadFile = File(...), user_id: str = Form("unknown"), _auth: bool = Depends(verify_api_key)):
    logger.info(f"[parse-cv] user={user_id}")
    if not (file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")):
        raise HTTPException(415, "PDF requis.")
    pdf_bytes = await file.read()
    cv_text = extract_text_pdf(pdf_bytes)
    if not cv_text.strip():
        raise HTTPException(422, "PDF vide ou scanné sans OCR.")
    system = "Tu es expert en analyse de CV. JSON uniquement."
    prompt = f"""Analyse ce CV:
{{"identite":{{"nom":"","email":"","telephone":"","localisation":"","linkedin":"","langues":[]}},"formation":[{{"diplome":"","domaine":"","etablissement":"","annee":""}}],"competences":{{"techniques":[],"securite":[],"outils":[],"soft_skills":[]}},"experience":[{{"poste":"","organisation":"","duree":"","missions":[]}}],"certifications":[],"preferences":{{"types_opportunite":["emploi","bourse"],"niveau":"professionnel","langues_opportunite":["fr","en"],"delai_min_jours":14,"mots_cles":[],"geographie":[]}},"niveau_global":"junior|mid|senior","resume_profil":""}}
CV: {cv_text[:6000]}"""
    profil = await call_groq(system, prompt, temperature=0.1, max_tokens=2500)
    return {"success": True, "user_id": user_id, "profil": profil, "parsed_at": datetime.now(timezone.utc).isoformat()}

@app.post("/api/generate-documents")
async def generate_documents(request: GenerateDocumentsRequest, _auth: bool = Depends(verify_api_key)):
    logger.info(f"[generate-documents] user={request.user_id}")
    profil, offre = request.profil, request.offre
    titre = offre.get("title", offre.get("titre", "Poste"))
    entreprise = offre.get("company", offre.get("entreprise", "Organisation"))
    cv_data = await call_groq("Tu adaptes un CV pour une offre. ATS-friendly. JSON uniquement.",
        f'PROFIL: {json.dumps(profil, ensure_ascii=False)[:2000]}\nOFFRE: Titre={titre}, Entreprise={entreprise}\nJSON: {{"titre_poste":"","resume_professionnel":"","competences_mises_en_avant":[]}}',
        temperature=0.2, max_tokens=800)
    competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))
    cv_buf = build_cv_pdf(profil, cv_data.get("titre_poste", titre), cv_data.get("resume_professionnel", ""), competences)
    nom = profil.get("identite", {}).get("nom", "candidat").replace(" ", "_")
    return {"success": True, "user_id": request.user_id, "cv_pdf_base64": pdf_to_b64(cv_buf), "cv_filename": f"CV_{nom}_{titre[:20].replace(' ','_')}.pdf", "generated_at": datetime.now(timezone.utc).isoformat()}

VISA_DB = {
    "france":{"facilite":58,"delai":21,"refus_pct":30,"cout_usd":80,"type":"schengen"},
    "allemagne":{"facilite":52,"delai":30,"refus_pct":36,"cout_usd":80,"type":"schengen"},
    "luxembourg":{"facilite":50,"delai":30,"refus_pct":37,"cout_usd":80,"type":"schengen"},
    "canada":{"facilite":50,"delai":60,"refus_pct":28,"cout_usd":150,"type":"canada_visa"},
    "usa":{"facilite":38,"delai":120,"refus_pct":42,"cout_usd":185,"type":"j1_b1b2"},
    "bresil":{"facilite":65,"delai":15,"refus_pct":15,"cout_usd":0,"type":"sans_visa_90j"},
    "maroc":{"facilite":72,"delai":7,"refus_pct":10,"cout_usd":0,"type":"sans_visa_30j"},
    "nigeria":{"facilite":90,"delai":3,"refus_pct":2,"cout_usd":0,"type":"cedeao"},
    "georgie":{"facilite":88,"delai":0,"refus_pct":2,"cout_usd":0,"type":"sans_visa_365j"},
    "turquie":{"facilite":70,"delai":3,"refus_pct":12,"cout_usd":35,"type":"evisa"},
    "default":{"facilite":50,"delai":60,"refus_pct":30,"cout_usd":100,"type":"inconnu"}
}

async def run_osint(profil: dict, cible: str = "") -> dict:
    profil = profil or {}
    prefs = profil.get("preferences", {}) or {}
    competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))[:5]
    nationalite = prefs.get("nationalite") or "béninoise"
    financement = prefs.get("financement") or "non précisé"
    pays_cibles = prefs.get("pays_cibles") or ""
    objectif = prefs.get("objectif") or "tous"
    cible = (cible or "").strip() or (pays_cibles + " " + " ".join(competences)).strip() or "opportunités internationales"
    cible_lower = cible.lower()
    pays_detecte = next((p for p in VISA_DB if p != "default" and (p in cible_lower or p in pays_cibles.lower())), None)
    visa_info = VISA_DB.get(pays_detecte, VISA_DB["default"])
    system = "Tu es expert en mobilité internationale pour ressortissants africains. Propose des opportunités RÉELLES et actionnables (bourses, emplois, fellowships). JSON uniquement."
    prompt = f"""Analyse les opportunités de mobilité.
CIBLE: {cible}
PAYS: {pays_detecte or pays_cibles or 'Non précisé'}
OBJECTIF: {objectif}
PROFIL: compétences={competences}, nationalité={nationalite}, financement={financement}
VISA: facilité={visa_info['facilite']}/100, délai={visa_info['delai']}j, coût=${visa_info['cout_usd']}
JSON: {{"opportunites":[{{"titre":"","organisation":"","type":"emploi|bourse|fellowship","url":"","pays":"","financement":"total|partiel","score_composite":0,"recommandation":"PRIORITAIRE|INTERESSANT|RISQUE","raison":""}}],"conseil_principal":""}}"""
    result = await call_groq(system, prompt, temperature=0.2, max_tokens=1500)
    opps = result.get("opportunites", [])
    titre_aff = cible if len(cible) <= 40 else cible[:40] + "…"
    msg = f"🌍 *Forge NEX OSINT — {titre_aff}*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if pays_detecte:
        msg += f"🗺️ Visa {pays_detecte}: {visa_info['facilite']}/100, ~{visa_info['delai']}j\n\n"
    for i, opp in enumerate(opps[:5], 1):
        score = opp.get("score_composite", 0)
        emoji = "🔥" if score >= 75 else "✅" if score >= 55 else "⚠️"
        msg += f"{i}\\. {emoji} *{opp.get('titre','')[:50]}*\n   🏢 {opp.get('organisation','')} \\| 📊 {score}/100\n   💬 {opp.get('raison','')}\n\n"
    if result.get("conseil_principal"):
        msg += f"💡 *Conseil:* {result['conseil_principal']}"
    if not opps:
        msg += "Aucune opportunité précise trouvée. Reformule avec un pays ou un domaine (ex : /mobilite Canada cybersécurité)."
    return {"message": msg, "opportunites": opps, "visa_info": visa_info}

@app.post("/api/osint")
async def osint_mobilite(request: MobilityRequest, _auth: bool = Depends(verify_api_key)):
    logger.info(f"[osint] user={request.user_id} cible={request.cible}")
    session = session_manager.get(request.user_id)
    profil = session.get("profil", {}) if session else {}
    res = await run_osint(profil, request.cible)
    return {**res, "chat_id": request.chat_id}

@app.get("/api/session/{user_id}")
async def get_session(user_id: str, _auth: bool = Depends(verify_api_key)):
    session = session_manager.get(user_id)
    if not session:
        return {"found": False, "session": None}
    return {"found": True, "session": session_to_sheets_row(session)}

@app.post("/api/session/{user_id}")
async def set_session(user_id: str, session_data: dict, _auth: bool = Depends(verify_api_key)):
    session_manager.set(user_id, session_data)
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "service": "forge-nex-api", "groq_configured": bool(GROQ_API_KEY), "api_key_configured": bool(FORGE_NEX_API_KEY), "sessions_stored": session_manager.count(), "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/")
async def root():
    return {"service": "Forge NEX API v2.0", "endpoints": ["POST /api/chat", "POST /api/chat-cv", "POST /api/parse-cv", "POST /api/generate-documents", "POST /api/osint", "GET /api/session/{user_id}", "GET /health"]}
