import os, io, json, base64, logging, secrets, time, asyncio, sqlite3, hashlib
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
def _read_telegram_token():
    tok = os.getenv("TELEGRAM_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if tok:
        return tok.strip()
    for _p in ("data/telegram_token.txt", "/app/data/telegram_token.txt", "telegram_token.txt"):
        try:
            with open(_p) as _f:
                _v = _f.read().strip()
                if _v:
                    return _v
        except Exception:
            pass
    return ""

TELEGRAM_TOKEN  = _read_telegram_token()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY", "")

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
    def list_active(self) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT data FROM sessions").fetchall()
        con.close()
        out = []
        for (d,) in rows:
            try:
                s = json.loads(d)
                if s.get("onboarding_complete"):
                    out.append(s)
            except Exception:
                pass
        return out
    def create_default(self, user_id: str, chat_id: str, username: str) -> dict:
        return {"user_id": str(user_id), "chat_id": str(chat_id), "username": username, "etape": "WELCOME", "profil": {}, "historique": [], "cv_parsed": False, "cv_file_id": None, "onboarding_complete": False, "created_at": datetime.now(timezone.utc).isoformat()}

session_manager = SessionManager()

class OppStore:
    def __init__(self, path: str = "data/sessions.db"):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("""CREATE TABLE IF NOT EXISTS offres (
            id TEXT PRIMARY KEY, user_id TEXT, titre TEXT, organisation TEXT, type TEXT,
            url TEXT, pays TEXT, financement TEXT, deadline TEXT, score INTEGER, raison TEXT,
            statut TEXT DEFAULT 'nouvelle', notified INTEGER DEFAULT 0, created_at TEXT)""")
        con.commit(); con.close()
    def add(self, user_id, opp) -> bool:
        url = opp.get("url") or opp.get("portail_officiel") or (str(opp.get("titre", "")) + str(opp.get("organisation", "")))
        oid = hashlib.sha1(f"{user_id}|{url}".encode("utf-8", "ignore")).hexdigest()
        con = sqlite3.connect(self._path, timeout=10)
        try:
            if con.execute("SELECT 1 FROM offres WHERE id=?", (oid,)).fetchone():
                return False
            con.execute("""INSERT INTO offres(id,user_id,titre,organisation,type,url,pays,financement,deadline,score,raison,statut,notified,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (oid, str(user_id), opp.get("titre", ""), opp.get("organisation", ""), opp.get("type", ""),
                         url, opp.get("pays", ""), opp.get("financement", ""), opp.get("deadline", ""),
                         int(opp.get("score_composite", 0) or 0), opp.get("raison", ""), "nouvelle", 0,
                         datetime.now(timezone.utc).isoformat()))
            con.commit(); return True
        finally:
            con.close()
    def pending(self, user_id, min_score: int = 60) -> list:
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("""SELECT id,titre,organisation,type,url,financement,deadline,score,raison
                              FROM offres WHERE user_id=? AND notified=0 AND score>=? ORDER BY score DESC""",
                           (str(user_id), min_score)).fetchall()
        con.close()
        return rows
    def mark_notified(self, ids: list):
        if not ids:
            return
        con = sqlite3.connect(self._path, timeout=10)
        con.executemany("UPDATE offres SET notified=1 WHERE id=?", [(i,) for i in ids])
        con.commit(); con.close()
    def count_pending(self, min_score: int = 60) -> int:
        con = sqlite3.connect(self._path, timeout=10)
        n = con.execute("SELECT COUNT(*) FROM offres WHERE notified=0 AND score>=?", (min_score,)).fetchone()[0]
        con.close()
        return int(n)

opp_store = OppStore()

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
            "/postuler <poste ou bourse> — CV + lettre de motivation\n"
            "/veille — chercher de nouvelles opportunités maintenant\n"
            "/status — état de tes candidatures\n"
            "/aide — cette aide\n"
            "/supprimer — effacer mes données")

def _push(session, role, content):
    h = session.get("historique", [])
    h.append({"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()})
    session["historique"] = h[-30:]

def _md_clean(s):
    s = str(s or "")
    for c in ("*", "_", "`", "[", "]"):
        s = s.replace(c, "")
    return s.strip()

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

    if low.startswith("/postuler") or low.startswith("/candidature"):
        parts = t.split(maxsplit=1)
        cible_desc = parts[1].strip() if len(parts) > 1 else ""
        profil = session.get("profil", {}) or {}
        if not profil.get("identite"):
            msg = "📄 Je dois d'abord connaître ton profil. Fais /start puis envoie ton CV en PDF."
        elif not cible_desc:
            msg = ("✍️ Indique la cible :\n/postuler <poste ou bourse>\n\n"
                   "Ex : /postuler Analyste SOC chez Orange\n"
                   "Ex : /postuler Bourse DAAD master cybersécurité")
        else:
            try:
                type_cible = "bourse" if any(k in cible_desc.lower() for k in ("bourse", "scholarship", "master", "phd", "doctorat", "fellowship", "etude", "étude")) else "emploi"
                pack = await generate_pack(profil, cible_desc, type_cible)
                competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))
                cv_buf = build_cv_pdf(profil, pack.get("titre_poste") or cible_desc, pack.get("resume_professionnel", ""), competences)
                lm_buf = build_letter_pdf(profil, pack.get("lettre_objet") or f"Candidature — {cible_desc}", pack.get("lettre_corps", ""))
                nom = _slug(profil.get("identite", {}).get("nom", "candidat"))
                chat_id = session.get("chat_id")
                ok_cv = await _send_telegram_document(chat_id, f"CV_{nom}.pdf", cv_buf.getvalue(), f"📄 CV adapté — {cible_desc[:60]}")
                ok_lm = await _send_telegram_document(chat_id, f"LM_{nom}.pdf", lm_buf.getvalue(), f"✉️ Lettre de motivation — {cible_desc[:60]}")
                if ok_cv and ok_lm:
                    msg = (f"✅ CV adapté + lettre de motivation générés pour : *{_md_clean(cible_desc)}*.\n\n"
                           "⚠️ Relis et personnalise (dates, détails concrets, ton) avant d'envoyer.")
                elif ok_cv or ok_lm:
                    msg = "⚠️ Un seul document a pu être envoyé. Réessaie dans un instant."
                else:
                    msg = "😕 Documents générés mais l'envoi Telegram a échoué (variable TELEGRAM_BOT_TOKEN manquante côté API ?)."
            except Exception as e:
                logger.error(f"Erreur postuler: {e}")
                msg = "😕 La génération des documents a échoué, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/veille"):
        if not session.get("onboarding_complete"):
            msg = "Termine d'abord ton profil avec /start (puis envoie ton CV)."
        else:
            try:
                res = await run_osint(session.get("profil", {}) or {}, "")
                new = 0
                for opp in res.get("opportunites", []):
                    if opp_store.add(session.get("user_id"), opp):
                        new += 1
                msg = res.get("message") or "Aucune opportunité trouvée pour l'instant."
                msg += f"\n\n🆕 {new} nouvelle(s) opportunité(s) ajoutée(s) à ta veille."
            except Exception as e:
                logger.error(f"Erreur veille: {e}")
                msg = "😕 La veille a échoué, réessaie dans un instant."
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

def _xml(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _slug(s):
    s = "".join(c for c in str(s or "candidat") if c.isalnum() or c in " -_")
    return (s.strip().replace(" ", "_")[:40]) or "candidat"

def build_letter_pdf(profil: dict, objet: str, corps: str) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    ident = profil.get("identite", {})
    s_head = ParagraphStyle("lh", fontSize=11, fontName="Helvetica-Bold", spaceAfter=2)
    s_small = ParagraphStyle("lsm", fontSize=9.5, textColor=GRIS, spaceAfter=1)
    s_objet = ParagraphStyle("lo", fontSize=10.5, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=10)
    s_body = ParagraphStyle("lb", fontSize=10.5, fontName="Helvetica", spaceAfter=8, leading=15, alignment=TA_JUSTIFY)
    els = []
    els.append(Paragraph(_xml(ident.get("nom", "Candidat")), s_head))
    for c in [ident.get("email"), ident.get("telephone"), ident.get("localisation")]:
        if c:
            els.append(Paragraph(_xml(c), s_small))
    els.append(Spacer(1, 10))
    els.append(Paragraph(datetime.now(timezone.utc).strftime("%d/%m/%Y"), s_small))
    els.append(Paragraph(f"<b>Objet :</b> {_xml(objet)}", s_objet))
    for para in (corps or "").split("\n\n"):
        para = para.strip()
        if para:
            els.append(Paragraph(_xml(para.replace("\n", " ")), s_body))
    els.append(Spacer(1, 12))
    els.append(Paragraph("Cordialement,", s_body))
    els.append(Paragraph(_xml(ident.get("nom", "")), s_head))
    doc.build(els)
    return buf

async def _send_telegram_document(chat_id, filename, pdf_bytes, caption=""):
    if not TELEGRAM_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
                data={"chat_id": str(chat_id), "caption": (caption or "")[:1000]},
                files={"document": (filename, pdf_bytes, "application/pdf")},
            )
        return r.status_code == 200
    except Exception as e:
        logger.error(f"sendDocument erreur: {e}")
        return False

async def _send_telegram_message(chat_id, text):
    if not TELEGRAM_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": str(chat_id), "text": (text or "")[:4000], "parse_mode": "Markdown"},
            )
        return r.status_code == 200
    except Exception as e:
        logger.error(f"sendMessage erreur: {e}")
        return False

async def generate_pack(profil: dict, cible_desc: str, type_cible: str = "emploi") -> dict:
    ident = profil.get("identite", {})
    competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))[:12]
    resume = profil.get("resume_profil", "")
    if type_cible == "bourse":
        consigne = ("Rédige un CV adapté ET une lettre de motivation académique (statement of purpose) pour cette bourse/programme. "
                    "La lettre met en avant le projet d'études, la motivation, l'adéquation au programme et l'impact visé.")
    else:
        consigne = ("Rédige un CV adapté ET une lettre de motivation professionnelle ciblée pour ce poste. "
                    "Structure : accroche, adéquation profil/poste, valeur ajoutée, conclusion.")
    system = "Tu es expert en recrutement et candidatures internationales. Français impeccable, concret, sans clichés. JSON uniquement."
    prompt = f"""{consigne}
CANDIDAT: {ident.get('nom','')}
RÉSUMÉ: {resume}
COMPÉTENCES: {competences}
CIBLE: {cible_desc}
La lettre (lettre_corps) fait 250-320 mots, paragraphes séparés par une ligne vide, sans en-tête ni signature.
JSON: {{"titre_poste":"","resume_professionnel":"","competences_mises_en_avant":[],"lettre_objet":"","lettre_corps":""}}"""
    return await call_groq(system, prompt, temperature=0.4, max_tokens=1200)

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
    type_cible = "bourse" if str(offre.get("type", "")).lower() in ("bourse", "fellowship", "scholarship") else "emploi"
    cible_desc = f"{titre} — {entreprise}"
    pack = await generate_pack(profil, cible_desc, type_cible)
    competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))
    cv_buf = build_cv_pdf(profil, pack.get("titre_poste") or titre, pack.get("resume_professionnel", ""), competences)
    lm_buf = build_letter_pdf(profil, pack.get("lettre_objet") or f"Candidature — {cible_desc}", pack.get("lettre_corps", ""))
    nom = _slug(profil.get("identite", {}).get("nom", "candidat"))
    return {"success": True, "user_id": request.user_id,
            "cv_pdf_base64": pdf_to_b64(cv_buf), "cv_filename": f"CV_{nom}.pdf",
            "lettre_pdf_base64": pdf_to_b64(lm_buf), "lettre_filename": f"LM_{nom}.pdf",
            "generated_at": datetime.now(timezone.utc).isoformat()}

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

async def tavily_search(query: str, max_results: int = 7) -> list:
    if not TAVILY_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post("https://api.tavily.com/search", json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
            })
        if r.status_code != 200:
            logger.error(f"Tavily {r.status_code}: {r.text[:200]}")
            return []
        return r.json().get("results", []) or []
    except Exception as e:
        logger.error(f"Tavily erreur: {e}")
        return []

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

    # --- Grounding web réel (Tavily) si la clé est configurée ---
    grounded = []
    if TAVILY_API_KEY:
        type_mot = {"étudier": "bourse", "etudier": "bourse", "bourse": "bourse",
                    "fellowship": "fellowship", "travailler": "emploi"}.get(objectif, "bourse OR emploi OR fellowship")
        zone = pays_detecte or pays_cibles or ""
        query = f"{type_mot} {cible} {zone} 2026 candidature éligibilité".strip()
        grounded = await tavily_search(query, 7)

    if grounded:
        sources_txt = "\n".join(
            f"- TITRE: {s.get('title','')} | URL: {s.get('url','')} | EXTRAIT: {(s.get('content','') or '')[:220]}"
            for s in grounded[:7]
        )
        system = ("Tu es expert en mobilité internationale. On te fournit des RÉSULTATS WEB RÉELS. "
                  "Sélectionne et score UNIQUEMENT parmi eux. Reprends les URL EXACTEMENT telles que fournies, "
                  "n'invente RIEN (ni offre, ni URL). Ignore un résultat qui n'est pas une vraie opportunité. JSON uniquement.")
        prompt = f"""PROFIL: compétences={competences}, nationalité={nationalite}, financement={financement}, objectif={objectif}
CIBLE: {cible} · PAYS: {pays_detecte or pays_cibles or 'indifférent'}
RÉSULTATS WEB (source de vérité — garde les URL telles quelles):
{sources_txt}
Sélectionne les 3 à 5 plus pertinents pour ce profil. Reprends l'URL exacte de chaque source retenue.
JSON: {{"opportunites":[{{"titre":"","organisation":"","type":"emploi|bourse|fellowship","url":"","pays":"","financement":"total|partiel|aucun","deadline":"","confiance":"haute|moyenne|faible","score_composite":0,"recommandation":"PRIORITAIRE|INTERESSANT|RISQUE","raison":""}}],"conseil_principal":""}}"""
        result = await call_groq(system, prompt, temperature=0.1, max_tokens=1700)
        footer = "🌐 _Sources web réelles (Tavily) — vérifie l'éligibilité et la deadline sur chaque lien._"
    else:
        system = ("Tu es expert en mobilité internationale et bourses pour ressortissants africains. "
                  "RÈGLES STRICTES : ne cite QUE des organismes/programmes RÉELS et vérifiables "
                  "(DAAD, Campus France, Erasmus Mundus, Chevening, Commonwealth, AUF, Mastercard Foundation, "
                  "Mitacs, Fulbright, INRS, universités reconnues, grandes entreprises). "
                  "N'INVENTE JAMAIS d'URL : donne seulement le PORTAIL OFFICIEL en clair (ex : campusfrance.org). "
                  "Si tu n'es pas certain, mets confiance='faible'. Priorise selon le financement. JSON uniquement.")
        prompt = f"""Propose des opportunités de mobilité RÉELLES.
CIBLE: {cible}
PAYS: {pays_detecte or pays_cibles or 'Non précisé'}
OBJECTIF: {objectif}
PROFIL: compétences={competences}, nationalité={nationalite}, financement={financement}
VISA: facilité={visa_info['facilite']}/100, délai={visa_info['delai']}j
Donne 3 à 5 opportunités concrètes, du plus pertinent au moins pertinent.
JSON: {{"opportunites":[{{"titre":"","organisation":"","type":"emploi|bourse|fellowship","portail_officiel":"","pays":"","financement":"total|partiel|aucun","deadline":"","confiance":"haute|moyenne|faible","score_composite":0,"recommandation":"PRIORITAIRE|INTERESSANT|RISQUE","raison":""}}],"conseil_principal":""}}"""
        result = await call_groq(system, prompt, temperature=0.15, max_tokens=1600)
        footer = "⚠️ _Pistes générées par IA — à vérifier sur les sites officiels avant de postuler._"

    opps = result.get("opportunites", [])
    titre_aff = _md_clean(cible)[:40]
    conf_emoji = {"haute": "🟢", "moyenne": "🟡", "faible": "🔴"}
    msg = f"🌍 *Forge NEX OSINT — {titre_aff}*\n━━━━━━━━━━━━━━━━━━\n"
    if pays_detecte:
        msg += f"🗺️ Visa {pays_detecte} : {visa_info['facilite']}/100, ~{visa_info['delai']}j\n\n"
    for i, opp in enumerate(opps[:5], 1):
        score = opp.get("score_composite", 0)
        emoji = "🔥" if score >= 75 else "✅" if score >= 55 else "⚠️"
        conf = conf_emoji.get(str(opp.get("confiance", "")).lower(), "")
        titre = _md_clean(opp.get("titre", ""))[:60]
        orga = _md_clean(opp.get("organisation", ""))
        lien = str(opp.get("url", "") or opp.get("portail_officiel", "")).replace("*", "").replace("`", "").strip()
        deadline = _md_clean(opp.get("deadline", ""))
        raison = _md_clean(opp.get("raison", ""))
        msg += f"{i}. {emoji} *{titre}*\n"
        msg += f"   🏢 {orga} · 📊 {score}/100 {conf}\n"
        if lien:
            msg += f"   🔗 {lien}\n"
        if deadline:
            msg += f"   📅 {deadline}\n"
        if raison:
            msg += f"   💬 {raison}\n"
        msg += "\n"
    if result.get("conseil_principal"):
        msg += f"💡 *Conseil :* {_md_clean(result['conseil_principal'])}\n\n"
    if not opps:
        msg += "Aucune opportunité trouvée. Reformule avec un pays et un domaine (ex : /mobilite Canada cybersécurité).\n\n"
    msg += footer
    return {"message": msg, "opportunites": opps, "visa_info": visa_info, "grounded": bool(grounded)}

@app.post("/api/osint")
async def osint_mobilite(request: MobilityRequest, _auth: bool = Depends(verify_api_key)):
    logger.info(f"[osint] user={request.user_id} cible={request.cible}")
    session = session_manager.get(request.user_id)
    profil = session.get("profil", {}) if session else {}
    res = await run_osint(profil, request.cible)
    return {**res, "chat_id": request.chat_id}

@app.post("/api/collect")
async def collect(_auth: bool = Depends(verify_api_key)):
    users = session_manager.list_active()
    total_new = 0
    for s in users[:50]:
        try:
            res = await run_osint(s.get("profil", {}) or {}, "")
            for opp in res.get("opportunites", []):
                if opp_store.add(s.get("user_id"), opp):
                    total_new += 1
        except Exception as e:
            logger.error(f"[collect] user={s.get('user_id')}: {e}")
    logger.info(f"[collect] users={len(users)} nouvelles={total_new}")
    return {"ok": True, "users_actifs": len(users), "offres_collectees": total_new}

@app.post("/api/score")
async def score(_auth: bool = Depends(verify_api_key)):
    # Le scoring est realise pendant la collecte (run_osint). Ici : resume.
    return {"ok": True, "en_attente_notif": opp_store.count_pending()}

@app.post("/api/notify")
async def notify(_auth: bool = Depends(verify_api_key)):
    users = session_manager.list_active()
    notified = 0
    for s in users[:50]:
        chat_id = s.get("chat_id")
        rows = opp_store.pending(s.get("user_id"), 60)
        if not rows or not chat_id:
            continue
        lignes, ids = [], []
        for (oid, titre, orga, typ, url, fin, deadline, sc, raison) in rows[:5]:
            ids.append(oid)
            em = "🔥" if sc >= 75 else "✅"
            ligne = f"{em} *{_md_clean(titre)[:60]}*\n   🏢 {_md_clean(orga)} · 📊 {sc}/100"
            if url:
                ligne += "\n   🔗 " + str(url).replace("*", "").replace("`", "")
            if deadline:
                ligne += "\n   📅 " + _md_clean(deadline)
            lignes.append(ligne)
        msg = ("🔔 *Nouvelles opportunités pour toi*\n━━━━━━━━━━━━━━━━━━\n\n"
               + "\n\n".join(lignes)
               + "\n\n_Utilise /postuler <titre> pour générer CV + lettre._")
        if await _send_telegram_message(chat_id, msg):
            opp_store.mark_notified(ids)
            notified += 1
    logger.info(f"[notify] users_notifies={notified}")
    return {"ok": True, "users_notifies": notified}

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
