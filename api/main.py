import os, io, json, base64, logging, secrets, time, asyncio, sqlite3, hashlib, re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional, Any

import fitz
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Security, Depends, Request, Response
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
VERSION         = "2.7.0"
WHATSAPP_TOKEN      = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID   = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "nexmove_verify")
MESSENGER_TOKEN     = os.getenv("MESSENGER_TOKEN", "")
MESSENGER_VERIFY_TOKEN = os.getenv("MESSENGER_VERIFY_TOKEN", "nexmove_verify")

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

app = FastAPI(title="NexMove API", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=50)
    chat_id: str = Field(..., min_length=1)
    username: str = Field(default="utilisateur", max_length=100)
    text: str = Field(default="", max_length=4096)
    message_type: str = Field(default="text")
    document_file_id: Optional[str] = None
    callback_data: str = Field(default="", max_length=100)
    callback_id: str = Field(default="", max_length=100)
    message_id: str = Field(default="", max_length=40)

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
        con.execute("""CREATE TABLE IF NOT EXISTS candidatures (
            id TEXT PRIMARY KEY, user_id TEXT, cible TEXT, deadline TEXT,
            statut TEXT DEFAULT 'en_preparation', created_at TEXT)""")
        for ddl in ("ALTER TABLE candidatures ADD COLUMN deadline_iso TEXT DEFAULT ''",
                    "ALTER TABLE candidatures ADD COLUMN reminders_sent TEXT DEFAULT ''"):
            try:
                con.execute(ddl)
            except Exception:
                pass
        con.execute("""CREATE TABLE IF NOT EXISTS sources_offres (
            id TEXT PRIMARY KEY, titre TEXT, url TEXT, resume TEXT, date TEXT, created_at TEXT)""")
        con.commit(); con.close()
    def add_source(self, it) -> bool:
        oid = hashlib.sha1(str(it.get("url", "")).encode("utf-8", "ignore")).hexdigest()
        con = sqlite3.connect(self._path, timeout=10)
        try:
            if con.execute("SELECT 1 FROM sources_offres WHERE id=?", (oid,)).fetchone():
                return False
            con.execute("INSERT INTO sources_offres(id,titre,url,resume,date,created_at) VALUES(?,?,?,?,?,?)",
                        (oid, it.get("titre", ""), it.get("url", ""), it.get("resume", ""), it.get("date", ""),
                         datetime.now(timezone.utc).isoformat()))
            con.commit(); return True
        finally:
            con.close()
    def search_sources(self, keywords, limit=60):
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT titre,url,resume FROM sources_offres ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        kws = [str(k).lower() for k in keywords if k and len(str(k)) > 2]
        scored = []
        for (titre, url, resume) in rows:
            txt = (str(titre) + " " + str(resume)).lower()
            sc = sum(1 for k in kws if k in txt)
            if sc > 0:
                scored.append((sc, {"titre": titre, "url": url, "resume": resume}))
        scored.sort(key=lambda x: -x[0])
        return [d for _, d in scored[:8]]
    def add_candidature(self, user_id, cible, deadline="", deadline_iso=""):
        oid = hashlib.sha1(f"cand|{user_id}|{cible}".encode("utf-8", "ignore")).hexdigest()
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("""INSERT INTO candidatures(id,user_id,cible,deadline,deadline_iso,statut,created_at)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET deadline=excluded.deadline, deadline_iso=excluded.deadline_iso""",
                    (oid, str(user_id), cible, deadline, deadline_iso, "en_preparation", datetime.now(timezone.utc).isoformat()))
        con.commit(); con.close()
    def list_candidatures(self, user_id):
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("SELECT cible,deadline,statut FROM candidatures WHERE user_id=? ORDER BY created_at DESC",
                           (str(user_id),)).fetchall()
        con.close()
        return rows
    def all_candidatures(self):
        con = sqlite3.connect(self._path, timeout=10)
        rows = con.execute("""SELECT id,user_id,cible,deadline_iso,reminders_sent FROM candidatures
                              WHERE deadline_iso IS NOT NULL AND deadline_iso!=''""").fetchall()
        con.close()
        return rows
    def mark_reminder(self, cand_id, milestone):
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT reminders_sent FROM candidatures WHERE id=?", (cand_id,)).fetchone()
        parts = [p for p in ((row[0] or "").split(",") if row else []) if p]
        if str(milestone) not in parts:
            parts.append(str(milestone))
        con.execute("UPDATE candidatures SET reminders_sent=? WHERE id=?", (",".join(parts), cand_id))
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

class Cache:
    def __init__(self, path: str = "data/sessions.db"):
        self._path = path
        con = sqlite3.connect(self._path)
        con.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, expires REAL)")
        con.commit(); con.close()
    def get(self, key):
        con = sqlite3.connect(self._path, timeout=10)
        row = con.execute("SELECT v,expires FROM cache WHERE k=?", (key,)).fetchone()
        con.close()
        if row and row[1] > time.time():
            try:
                return json.loads(row[0])
            except Exception:
                return None
        return None
    def set(self, key, value, ttl: int = 21600):
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("INSERT INTO cache(k,v,expires) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, expires=excluded.expires",
                    (key, json.dumps(value, ensure_ascii=False), time.time() + ttl))
        con.commit(); con.close()

cache = Cache()

ETAPE_INSTRUCTIONS = {
    "WELCOME": "Accueille chaleureusement l'utilisateur. Présente NexMove en 2 phrases: agent IA pour préparer son prochain départ (études, emploi, bourses, mobilité internationale) adapté à son profil. Demande d'envoyer le CV en PDF.",
    "ATTENTE_CV": "L'utilisateur doit envoyer son CV en PDF. Rappelle-lui brièvement.",
    "CV_RECU": "Le CV a été analysé. L'utilisateur confirme les informations. Réponds Oui pour passer aux préférences.",
    "PREFERENCES": "Collecte des préférences (gérée par le code).",
    "CONFIRMATION": "Résume le profil complet et demande confirmation finale (Oui pour démarrer).",
    "ACTIF": "L'onboarding est terminé. Réponds DIRECTEMENT et utilement à la demande (tutoie, ne re-salue PAS l'utilisateur). Selon son besoin, oriente vers : /veille (chercher des opportunités), /campusfrance (études en France), /dossier <cible> (documents + CV + projet d'études), /postuler <cible> (CV + lettre), /status (suivi)."
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

AIDE_TXT = ("🧭 *NexMove — que veux-tu faire ?*\n\n"
            "🔎 *Trouver des opportunités*\n"
            "/veille · /mobilite <pays ou domaine>\n\n"
            "🇫🇷 *Étudier en France*\n"
            "/campusfrance (procédure) · /parcours (ton suivi étape par étape)\n\n"
            "📄 *Candidater*\n"
            "/dossier <cible> (documents + CV + projet) · /postuler <cible> (CV + lettre)\n"
            "/formations <domaine> (te distinguer)\n\n"
            "📊 *Mon espace*\n"
            "/profil · /status · /supprimer\n\n"
            "💡 Nouveau ? Tape /tuto. Sinon commence par /veille ou /campusfrance.")

TUTO_TXT = ("📖 *Guide NexMove*\n\n"
            "*1. Ton profil* — envoie ton *CV en PDF*. Je l'analyse, puis je te pose quelques questions "
            "(objectif, pays, financement, langue…).\n\n"
            "*2. Trouver des opportunités*\n"
            "• /veille — je cherche des offres RÉELLES adaptées à ton profil.\n"
            "• /mobilite <pays ou domaine> — recherche ciblée (ex : /mobilite France bourse master).\n\n"
            "*3. Études en France* 🇫🇷\n"
            "• /campusfrance — la procédure, les bourses (Eiffel…) et les documents.\n"
            "• /parcours — suis ton avancement étape par étape jusqu'au départ (/etape pour valider une étape).\n"
            "• /formations <domaine> — des formations/certifs pour te démarquer.\n\n"
            "*4. Candidater*\n"
            "• /dossier <cible> — la *liste des documents requis* + je génère ton *CV* et ton *projet d'études*.\n"
            "• /postuler <cible> — juste le *CV adapté* + la *lettre de motivation*.\n\n"
            "*5. Suivi* — /status, et je te notifie automatiquement des nouvelles opportunités.\n\n"
            "Prêt ? Envoie ton *CV en PDF* pour démarrer. 🚀")

CF_STAGES = [
    "Créer ton compte « Études en France » (EEF)",
    "Choisir tes formations et remplir ton dossier (projet d'études)",
    "Payer les frais Campus France",
    "Passer l'entretien Campus France",
    "Recevoir les réponses des établissements",
    "Accepter une offre et confirmer ton inscription",
    "Demander ton visa étudiant",
    "Préparer ton départ (logement, billet, assurance)",
]

def _push(session, role, content):
    h = session.get("historique", [])
    h.append({"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()})
    session["historique"] = h[-30:]

def _md_clean(s):
    s = str(s or "")
    for c in ("*", "_", "`", "[", "]"):
        s = s.replace(c, "")
    return s.strip()

def _type_label(typ):
    tp = str(typ or "").lower()
    if "bourse" in tp or "scholarship" in tp:
        return "🎓 BOURSE"
    if "fellowship" in tp:
        return "🔬 FELLOWSHIP"
    if any(k in tp for k in ("formation", "étude", "etude", "master", "licence", "programme", "doctorat", "phd", "universit")):
        return "📚 FORMATION"
    if any(k in tp for k in ("emploi", "job", "poste", "stage", "cdi", "cdd")):
        return "💼 EMPLOI"
    return "🌍 OPPORTUNITÉ"

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
        msg = ("👋 *Bienvenue sur NexMove !*\n"
               "_Ton agent IA pour préparer ton prochain départ : études, emploi, bourses et mobilité internationale._\n\n"
               "Voici comment ça marche :\n"
               "1️⃣ Envoie-moi ton *CV en PDF* — j'analyse ton profil.\n"
               "2️⃣ Je te pose quelques questions (objectif, pays, financement…).\n"
               "3️⃣ Ensuite : /veille (trouver), /campusfrance (études en France), /postuler (CV + lettre).\n\n"
               "📄 *Pour commencer, envoie ton CV en PDF.*  (ou tape /tuto pour le guide)")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/aide") or low.startswith("/help"):
        _push(session, "user", t); _push(session, "assistant", AIDE_TXT); session["derniere_activite"] = now
        return AIDE_TXT, session

    if low.startswith("/tuto") or low.startswith("/guide"):
        _push(session, "user", t); _push(session, "assistant", TUTO_TXT); session["derniere_activite"] = now
        return TUTO_TXT, session

    if low.startswith("/campusfrance") or low.startswith("/campus"):
        try:
            grounded = await tavily_search(
                "Campus France Études en France procédure calendrier 2026 2027 bourse Eiffel dossier étudiant international", 6)
            profil = session.get("profil", {}) or {}
            comp = (profil.get("competences", {}).get("techniques", []))[:4]
            sources = "\n".join(
                f"- {s.get('title','')} | {s.get('url','')} | {(s.get('content','') or '')[:200]}"
                for s in grounded[:6]) if grounded else "(pas de résultat web — appuie-toi sur ta connaissance générale)"
            system = ("Tu es conseiller Campus France. Explique clairement la procédure 'Études en France' pour un "
                      "étudiant africain francophone. Base les dates/étapes sur les résultats web fournis, sans inventer. JSON uniquement.")
            prompt = f"""RÉSULTATS WEB:
{sources}
PROFIL: compétences={comp}
DATE DU JOUR: {datetime.now(timezone.utc).date().isoformat()}. Donne le calendrier de la campagne EN COURS ou À VENIR (jamais une échéance déjà passée).
Explique la procédure Études en France (inscription, étapes, bourses, documents, calendrier).
JSON: {{"etapes":["..."],"bourses":["nom + portail"],"documents":["..."],"deadline":"","conseil":""}}"""
            r = await call_groq(system, prompt, temperature=0.1, max_tokens=1300)
            etapes, bourses, docs = r.get("etapes", []), r.get("bourses", []), r.get("documents", [])
            msg = "🇫🇷 *Campus France — Études en France*\n━━━━━━━━━━━━━━━━━━\n\n"
            if r.get("deadline"):
                msg += f"📅 *Calendrier :* {_md_clean(r['deadline'])}\n\n"
            if etapes:
                msg += "*Étapes :*\n" + "\n".join(f"{i}. {_md_clean(e)}" for i, e in enumerate(etapes[:6], 1)) + "\n\n"
            if bourses:
                msg += "🎓 *Bourses :*\n" + "\n".join(f"• {_md_clean(b)}" for b in bourses[:5]) + "\n\n"
            if docs:
                msg += "📎 *Documents à préparer :*\n" + "\n".join(f"• {_md_clean(d)}" for d in docs[:8]) + "\n\n"
            if r.get("conseil"):
                msg += f"💡 {_md_clean(r['conseil'])}\n\n"
            msg += "🌐 _Vérifie toujours les dates sur campusfrance.org._\n"
            msg += "✍️ Prêt à candidater ? Tape : /postuler Bourse Eiffel master <ton domaine>"
        except Exception as e:
            logger.error(f"campusfrance: {e}")
            msg = "😕 Impossible de récupérer les infos Campus France pour l'instant, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/parcours"):
        stage = int(session.get("cf_stage", 0) or 0)
        lines = []
        for i, st in enumerate(CF_STAGES):
            if i < stage:
                lines.append(f"✅ {st}")
            elif i == stage:
                lines.append(f"▶️ *{st}*")
            else:
                lines.append(f"⬜ {st}")
        pos = min(stage + 1, len(CF_STAGES))
        msg = ("🇫🇷 *Ton parcours Campus France*\n━━━━━━━━━━━━━━━━━━\n\n" + "\n".join(lines) +
               f"\n\nÉtape {pos}/{len(CF_STAGES)}. Tape /etape quand tu as terminé l'étape en cours.\n"
               "/campusfrance pour les détails · /dossier <cible> pour préparer les documents.")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/etape"):
        stage = int(session.get("cf_stage", 0) or 0)
        if stage < len(CF_STAGES):
            done = CF_STAGES[stage]
            stage += 1
            session["cf_stage"] = stage
            if stage >= len(CF_STAGES):
                msg = f"🎉 Étape validée : {done}\n\nTon parcours Campus France est *complet* ! Bon départ ✈️"
            else:
                msg = (f"✅ Étape validée : {done}\n\n▶️ Prochaine étape : *{CF_STAGES[stage]}*\n\n"
                       "/parcours pour voir l'ensemble.")
        else:
            msg = "Ton parcours est déjà complet 🎉. /parcours pour revoir."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/formations") or low.startswith("/formation"):
        profil = session.get("profil", {}) or {}
        prefs = profil.get("preferences", {}) or {}
        parts = t.split(maxsplit=1)
        domaine = parts[1].strip() if len(parts) > 1 else (
            prefs.get("mots_cles") or " ".join((profil.get("competences", {}).get("techniques", []))[:3]) or "informatique")
        try:
            grounded = await tavily_search(
                f"meilleures formations certifications en ligne {domaine} {prefs.get('objectif','')} pour se distinguer", 6)
            sources = "\n".join(
                f"- {s.get('title','')} | {s.get('url','')} | {(s.get('content','') or '')[:180]}"
                for s in grounded[:6]) if grounded else "(pas de résultat web)"
            system = ("Tu es conseiller en développement de carrière. Recommande des formations/certifications RÉELLES "
                      "(Coursera, edX, OpenClassrooms, Google, AWS, Cisco, (ISC)²...) qui aident à se distinguer. "
                      "Base-toi sur les sources web, garde les URL exactes. JSON uniquement.")
            prompt = f"""DOMAINE: {domaine}
PROFIL: compétences={(profil.get('competences', {}).get('techniques', []))[:8]}
SOURCES WEB:
{sources}
Recommande 3 à 5 formations/certifications pour renforcer ce profil et se démarquer. PRIORISE les formations GRATUITES (place-les en premier).
JSON: {{"formations":[{{"titre":"","organisme":"","type":"MOOC|certification|diplôme","url":"","duree":"","cout":"gratuit|payant","raison":""}}],"conseil":""}}"""
            r = await call_groq(system, prompt, temperature=0.2, max_tokens=1300)
            forms = r.get("formations", [])
            forms = sorted(forms, key=lambda f: 0 if "gratuit" in str(f.get("cout", "")).lower() else 1)
            msg = f"🎓 *Formations pour te distinguer — {_md_clean(domaine)[:40]}*\n━━━━━━━━━━━━━━━━━━\n\n"
            for i, f in enumerate(forms[:5], 1):
                titre = _md_clean(f.get("titre", ""))[:60]
                org = _md_clean(f.get("organisme", ""))
                url = str(f.get("url", "")).replace("*", "").replace("`", "")
                cout = _md_clean(f.get("cout", ""))
                duree = _md_clean(f.get("duree", ""))
                msg += f"{i}. 📘 *{titre}*\n   🏫 {org}"
                if duree:
                    msg += f" · ⏱️ {duree}"
                if cout:
                    msg += f" · 💶 {cout}"
                msg += "\n"
                if url:
                    msg += f"   🔗 {url}\n"
                if f.get("raison"):
                    msg += f"   💬 {_md_clean(f.get('raison', ''))}\n"
                msg += "\n"
            if r.get("conseil"):
                msg += f"💡 {_md_clean(r['conseil'])}\n\n"
            if not forms:
                msg = f"Aucune formation trouvée pour « {_md_clean(domaine)} ». Précise un domaine : /formations data science"
            else:
                msg += "🌐 _Vérifie les infos sur les sites officiels._"
        except Exception as e:
            logger.error(f"formations: {e}")
            msg = "😕 La recherche de formations a échoué, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

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
                ok_cv = await deliver_file(session,f"CV_{nom}.pdf", cv_buf.getvalue(), f"📄 CV adapté — {cible_desc[:60]}")
                ok_lm = await deliver_file(session,f"LM_{nom}.pdf", lm_buf.getvalue(), f"✉️ Lettre de motivation — {cible_desc[:60]}")
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

    if low.startswith("/dossier"):
        parts = t.split(maxsplit=1)
        cible_desc = parts[1].strip() if len(parts) > 1 else ""
        profil = session.get("profil", {}) or {}
        if not profil.get("identite"):
            msg = "📄 Fais d'abord /start puis envoie ton CV en PDF."
        elif not cible_desc:
            msg = ("🗂️ Indique la cible du dossier :\n/dossier <bourse ou programme>\n\n"
                   "Ex : /dossier Bourse Eiffel master cybersécurité\n"
                   "Ex : /dossier Master Université de Montréal")
        else:
            try:
                grounded = await tavily_search(f"{cible_desc} documents requis dossier candidature éligibilité deadline 2026", 6)
                sources = "\n".join(
                    f"- {s.get('title','')} | {s.get('url','')} | {(s.get('content','') or '')[:200]}"
                    for s in grounded[:6]) if grounded else "(pas de résultat web)"
                ident = profil.get("identite", {})
                comp = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))[:8]
                system = ("Tu es conseiller en candidatures internationales (Campus France, bourses). "
                          "Base-toi sur les sources web pour les exigences RÉELLES, sans inventer. "
                          "Rédige aussi un projet d'études / lettre de motivation adapté. JSON uniquement.")
                prompt = f"""CIBLE: {cible_desc}
CANDIDAT: {ident.get('nom','')}, résumé: {profil.get('resume_profil','')}, compétences: {comp}
SOURCES WEB:
{sources}
DATE DU JOUR: {datetime.now(timezone.utc).date().isoformat()}. Si l'édition de la campagne est passée, indique la PROCHAINE échéance — jamais une date déjà passée.
Donne la liste EXHAUSTIVE des documents requis, ce qui est à traduire/légaliser, la deadline si connue,
des conseils, et une lettre/projet d'études (corps 250-320 mots, paragraphes séparés par une ligne vide).
Donne aussi la deadline au format ISO (deadline_iso: "AAAA-MM-JJ") si une date précise et À VENIR est connue, sinon "".
JSON: {{"documents":["..."],"a_traduire":["..."],"deadline":"","deadline_iso":"","conseils":["..."],"objet":"","corps":""}}"""
                r = await call_groq(system, prompt, temperature=0.2, max_tokens=1700)
                docs = r.get("documents", [])
                msg = f"🗂️ *Dossier — {_md_clean(cible_desc)}*\n━━━━━━━━━━━━━━━━━━\n\n"
                if r.get("deadline"):
                    msg += f"📅 *Deadline :* {_md_clean(r['deadline'])}\n\n"
                if docs:
                    msg += "📎 *Documents nécessaires :*\n" + "\n".join(f"⬜ {_md_clean(d)}" for d in docs[:12]) + "\n\n"
                if r.get("a_traduire"):
                    msg += "🌐 *À traduire / légaliser :*\n" + "\n".join(f"• {_md_clean(x)}" for x in r["a_traduire"][:6]) + "\n\n"
                if r.get("conseils"):
                    msg += "💡 *Conseils :*\n" + "\n".join(f"• {_md_clean(c)}" for c in r["conseils"][:5]) + "\n\n"
                competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))
                cv_buf = build_cv_pdf(profil, cible_desc[:40], profil.get("resume_profil", ""), competences)
                lm_buf = build_letter_pdf(profil, r.get("objet") or f"Projet d'études — {cible_desc}", r.get("corps", ""))
                nom = _slug(ident.get("nom", "candidat"))
                chat_id = session.get("chat_id")
                await deliver_file(session,f"CV_{nom}.pdf", cv_buf.getvalue(), "📄 CV")
                await deliver_file(session,f"Projet_{nom}.pdf", lm_buf.getvalue(), "✍️ Lettre / projet d'études")
                opp_store.add_candidature(session.get("user_id"), cible_desc, r.get("deadline", ""), r.get("deadline_iso", ""))
                msg += ("📄 CV + lettre/projet d'études envoyés. Dossier ajouté à ton suivi (/status).\n"
                        "⚠️ _Vérifie les exigences exactes sur le site officiel._")
            except Exception as e:
                logger.error(f"dossier: {e}")
                msg = "😕 La préparation du dossier a échoué, réessaie."
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
        if session.get("onboarding_complete"):
            msg = ("📊 *Ton statut NexMove*\nProfil : ✅ actif\n"
                   f"Objectif : {prefs.get('objectif','—')} · Pays : {prefs.get('pays_cibles','—')}\n\n")
            cands = opp_store.list_candidatures(session.get("user_id"))
            if cands:
                msg += "🗂️ *Tes dossiers :*\n"
                for (cible, deadline, statut) in cands[:8]:
                    d = f" · 📅 {_md_clean(deadline)}" if deadline else ""
                    msg += f"• {_md_clean(cible)[:55]} — _{statut}_{d}\n"
                msg += "\n"
            else:
                msg += "🗂️ Aucun dossier en cours. Lance /dossier <cible> pour en préparer un.\n\n"
            msg += "Utilise /veille pour explorer, /campusfrance pour Études en France."
        else:
            msg = f"📊 Onboarding en cours (étape : {session.get('etape','WELCOME')}). Fais /start."
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
    system = f"""Tu es NexMove, agent IA chaleureux qui aide à préparer son prochain départ (études, emploi, bourses, mobilité internationale).
ETAPE: {etape}
PROFIL: {profil_str}
INSTRUCTIONS: {ETAPE_INSTRUCTIONS.get(etape, ETAPE_INSTRUCTIONS["ACTIF"])}
REGLES: francais, TUTOIE l'utilisateur, ton amical et encourageant, ne le re-salue PAS en pleine conversation, max 120 mots, propose une action utile (ex: /veille, /campusfrance, /dossier, /postuler), ne redemande jamais le CV si etape=ACTIF.
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

async def _tg(method, payload):
    if not TELEGRAM_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}", json=payload)
        if r.status_code != 200:
            logger.error(f"tg {method} {r.status_code}: {r.text[:150]}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"tg {method}: {e}")
        return False

async def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": str(chat_id), "text": (text or "")[:4000], "parse_mode": "Markdown", "disable_web_page_preview": True}
    if keyboard:
        payload["reply_markup"] = keyboard
    return await _tg("sendMessage", payload)

async def _send_telegram_message(chat_id, text):
    return await send_message(chat_id, text)

async def edit_message(chat_id, message_id, text, keyboard=None):
    try:
        mid = int(message_id)
    except Exception:
        return await send_message(chat_id, text, keyboard)
    payload = {"chat_id": str(chat_id), "message_id": mid, "text": (text or "")[:4000], "parse_mode": "Markdown", "disable_web_page_preview": True}
    if keyboard:
        payload["reply_markup"] = keyboard
    return await _tg("editMessageText", payload)

async def answer_callback(cb_id, text=""):
    return await _tg("answerCallbackQuery", {"callback_query_id": str(cb_id), "text": text[:180]})

def _btn(text, data):
    return {"text": text, "callback_data": data}

def _kb(rows):
    return {"inline_keyboard": rows}

def get_menu(session, key):
    if key == "find":
        return ("🔎 *Trouver des opportunités*", [
            ("🔔 Ma veille", "act:veille"),
            ("🌍 Recherche ciblée", "act:mobilite_help"),
            ("⬅️ Retour", "m:root")])
    if key == "cf":
        opts = [("🇫🇷 Campus France", "act:parcours")]
        try:
            for (cible, dl, st) in (opp_store.list_candidatures(session.get("user_id")) or [])[:4]:
                opts.append((("🗂️ " + str(cible))[:20], "act:status"))
        except Exception:
            pass
        opts.append(("➕ Nouvelle candid.", "act:dossier_help"))
        opts.append(("⬅️ Retour", "m:root"))
        return ("🗂️ *Tes procédures de candidature*", opts)
    if key == "apply":
        return ("📄 *Candidater*", [
            ("🗂️ Dossier complet", "act:dossier_help"),
            ("✉️ CV + lettre", "act:postuler_help"),
            ("🎓 Formations", "act:formations"),
            ("⬅️ Retour", "m:root")])
    if key == "space":
        return ("📊 *Mon espace*", [
            ("👤 Mon profil", "act:profil"),
            ("📊 Mon suivi", "act:status"),
            ("🗑️ Effacer données", "act:supprimer"),
            ("⬅️ Retour", "m:root")])
    return ("🧭 *NexMove* — que veux-tu faire ?", [
        ("🔎 Trouver", "m:find"), ("🇫🇷 Procédures", "m:cf"),
        ("📄 Candidater", "m:apply"), ("🎓 Formations", "act:formations"),
        ("📊 Mon espace", "m:space"), ("❓ Aide", "act:aide")])

def _tg_keyboard(options):
    rows, cur = [], []
    for (lbl, aid) in options:
        cur.append(_btn(lbl, aid))
        if len(cur) == 2:
            rows.append(cur); cur = []
    if cur:
        rows.append(cur)
    return _kb(rows)

# ---------- WhatsApp Cloud API ----------
async def wa_send(payload):
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID):
        return False
    try:
        async with httpx.AsyncClient(timeout=25.0) as c:
            r = await c.post(f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages",
                             headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, json=payload)
        if r.status_code != 200:
            logger.error(f"wa {r.status_code}: {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"wa send: {e}")
        return False

async def wa_text(to, text):
    return await wa_send({"messaging_product": "whatsapp", "to": str(to), "type": "text",
                          "text": {"body": (text or "")[:4000], "preview_url": True}})

async def wa_menu(to, title, options):
    opts = [(l[:20], a) for (l, a) in options][:10]
    if len(opts) <= 3:
        inter = {"type": "button", "body": {"text": (title or "Menu")[:1000]},
                 "action": {"buttons": [{"type": "reply", "reply": {"id": a[:200], "title": l}} for (l, a) in opts]}}
    else:
        inter = {"type": "list", "body": {"text": (title or "Menu")[:1000]},
                 "action": {"button": "Choisir", "sections": [{"title": "Options",
                            "rows": [{"id": a[:200], "title": l} for (l, a) in opts]}]}}
    return await wa_send({"messaging_product": "whatsapp", "to": str(to), "type": "interactive", "interactive": inter})

async def wa_document(to, filename, data, caption=""):
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID):
        return False
    try:
        async with httpx.AsyncClient(timeout=45.0) as c:
            up = await c.post(f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/media",
                              headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
                              data={"messaging_product": "whatsapp", "type": "application/pdf"},
                              files={"file": (filename, data, "application/pdf")})
            if up.status_code != 200:
                logger.error(f"wa media {up.status_code}: {up.text[:200]}")
                return False
            mid = up.json().get("id")
        return await wa_send({"messaging_product": "whatsapp", "to": str(to), "type": "document",
                              "document": {"id": mid, "filename": filename, "caption": (caption or "")[:900]}})
    except Exception as e:
        logger.error(f"wa doc: {e}")
        return False

async def wa_get_media(media_id):
    if not WHATSAPP_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            meta = await c.get(f"https://graph.facebook.com/v21.0/{media_id}",
                               headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
            url = meta.json().get("url")
            if not url:
                return None
            r = await c.get(url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        return r.content if r.status_code == 200 else None
    except Exception as e:
        logger.error(f"wa get_media: {e}")
        return None

# ---------- Messenger (Facebook Page) ----------
async def fb_send(payload):
    if not MESSENGER_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=25.0) as c:
            r = await c.post("https://graph.facebook.com/v21.0/me/messages",
                             params={"access_token": MESSENGER_TOKEN}, json=payload)
        if r.status_code != 200:
            logger.error(f"fb {r.status_code}: {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"fb send: {e}")
        return False

async def fb_text(to, text):
    return await fb_send({"recipient": {"id": str(to)}, "message": {"text": (text or "")[:1900]}})

async def fb_menu(to, text, options):
    qrs = [{"content_type": "text", "title": l[:20], "payload": a[:900]} for (l, a) in options[:13]]
    return await fb_send({"recipient": {"id": str(to)}, "message": {"text": (text or "Menu")[:640], "quick_replies": qrs}})

async def fb_document(to, filename, data, caption=""):
    if not MESSENGER_TOKEN:
        return False
    try:
        if caption:
            await fb_text(to, caption)
        async with httpx.AsyncClient(timeout=45.0) as c:
            r = await c.post("https://graph.facebook.com/v21.0/me/messages", params={"access_token": MESSENGER_TOKEN},
                             data={"recipient": json.dumps({"id": str(to)}),
                                   "message": json.dumps({"attachment": {"type": "file", "payload": {"is_reusable": False}}})},
                             files={"filedata": (filename, data, "application/pdf")})
        return r.status_code == 200
    except Exception as e:
        logger.error(f"fb doc: {e}")
        return False

# ---------- Couche canal (dispatch) ----------
async def deliver_menu(session, title, options):
    ch = session.get("channel", "telegram"); to = session.get("chat_id")
    if ch == "whatsapp":
        return await wa_menu(to, title, options)
    if ch == "messenger":
        return await fb_menu(to, title, options)
    return await send_message(to, title, _tg_keyboard(options))

async def deliver_text(session, text, with_menu=False):
    ch = session.get("channel", "telegram"); to = session.get("chat_id")
    if ch == "whatsapp":
        await wa_text(to, text)
        if with_menu:
            await wa_menu(to, "👉 Que veux-tu faire ?", get_menu(session, "root")[1])
        return True
    if ch == "messenger":
        if with_menu:
            return await fb_menu(to, text, get_menu(session, "root")[1])
        return await fb_text(to, text)
    kb = _tg_keyboard(get_menu(session, "root")[1]) if with_menu else None
    return await send_message(to, text, kb)

async def deliver_file(session, filename, data, caption=""):
    ch = session.get("channel", "telegram"); to = session.get("chat_id")
    if ch == "whatsapp":
        return await wa_document(to, filename, data, caption)
    if ch == "messenger":
        return await fb_document(to, filename, data, caption)
    return await _send_telegram_document(to, filename, data, caption)

_ACT_CMD = {"veille": "/veille", "parcours": "/parcours", "etape": "/etape", "profil": "/profil",
            "status": "/status", "campusfrance": "/campusfrance", "aide": "/aide",
            "formations": "/formations", "supprimer": "/supprimer"}
_ACT_HELP = {
    "mobilite_help": "🌍 Écris : /mobilite <pays ou domaine>\nEx : /mobilite Canada cybersécurité",
    "dossier_help": "🗂️ Écris : /dossier <bourse ou programme>\nEx : /dossier Bourse Eiffel master cybersécurité",
    "postuler_help": "✉️ Écris : /postuler <poste ou bourse>\nEx : /postuler Analyste SOC chez Orange",
}

async def handle_action(session, data):
    if data.startswith("m:"):
        title, opts = get_menu(session, data[2:])
        await deliver_menu(session, title, opts)
        return session
    if data.startswith("act:"):
        act = data[4:]
        if act in _ACT_HELP:
            await deliver_text(session, _ACT_HELP[act], with_menu=True)
            return session
        cmd = _ACT_CMD.get(act)
        if cmd:
            msg, session = await process_text_message(session, cmd)
            await deliver_text(session, msg, with_menu=True)
            return session
    title, opts = get_menu(session, "root")
    await deliver_menu(session, title, opts)
    return session

async def process_cv(session, pdf_bytes, filename="cv.pdf"):
    if not pdf_bytes or len(pdf_bytes) > 20 * 1024 * 1024:
        await deliver_text(session, "❌ PDF illisible ou trop lourd (max 20 Mo).")
        return
    try:
        cv_text = extract_text_pdf(pdf_bytes)
    except Exception:
        cv_text = ""
    if not cv_text or len(cv_text.strip()) < 50:
        await deliver_text(session, "❌ PDF vide ou scanné sans OCR.\n\nEnvoie un PDF avec texte sélectionnable (Word/LibreOffice).")
        return
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
    _push(session, "assistant", message)
    session_manager.set(session.get("user_id"), session)
    logger.info(f"[cv] {session.get('channel')} {nom} -> CV_RECU")
    await deliver_text(session, message)

def _extract_incoming(channel, raw):
    text, callback, doc = None, None, None
    if channel == "whatsapp":
        t = raw.get("type")
        if t == "text":
            text = raw.get("text", {}).get("body", "")
        elif t == "interactive":
            inter = raw.get("interactive", {})
            br = inter.get("button_reply") or inter.get("list_reply") or {}
            callback = br.get("id")
        elif t == "document":
            d = raw.get("document", {})
            doc = {"id": d.get("id"), "filename": d.get("filename", "cv.pdf")}
        elif t == "button":
            callback = raw.get("button", {}).get("payload")
    elif channel == "messenger":
        pb = raw.get("postback"); msg = raw.get("message")
        if pb:
            callback = pb.get("payload")
        elif msg:
            if msg.get("quick_reply"):
                callback = msg["quick_reply"].get("payload")
            elif msg.get("attachments"):
                for a in msg["attachments"]:
                    if a.get("type") == "file":
                        doc = {"url": a.get("payload", {}).get("url"), "filename": "cv.pdf"}
                        break
                if not doc:
                    text = ""
            elif "text" in msg:
                text = msg.get("text", "")
    return text, callback, doc

async def _download_doc(channel, doc):
    if channel == "whatsapp":
        return await wa_get_media(doc.get("id"))
    if channel == "messenger":
        url = doc.get("url")
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
                r = await c.get(url)
            return r.content if r.status_code == 200 else None
        except Exception:
            return None
    return None

async def route_incoming(channel, user_id, chat_id, username, raw):
    session = session_manager.get(user_id) or session_manager.create_default(user_id, chat_id, username)
    session["channel"] = channel
    session["chat_id"] = chat_id
    if username and username != "utilisateur":
        session["username"] = username
    text, callback, doc = _extract_incoming(channel, raw)
    if doc:
        pdf = await _download_doc(channel, doc)
        await process_cv(session, pdf, doc.get("filename", "cv.pdf"))
        return
    if callback:
        session = await handle_action(session, callback)
        session_manager.set(user_id, session)
        return
    if text is not None:
        if not check_rate_limit(user_id):
            await deliver_text(session, "⚠️ Trop de messages. Attends une minute.")
            return
        msg, session = await process_text_message(session, text)
        session_manager.set(user_id, session)
        await deliver_text(session, msg, with_menu=session.get("onboarding_complete"))

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
    session = session_manager.get(uid) or session_manager.create_default(uid, request.chat_id, request.username)
    session["channel"] = "telegram"
    session["chat_id"] = request.chat_id
    session["username"] = request.username
    if request.callback_data:
        if request.callback_id:
            await answer_callback(request.callback_id)
        session = await handle_action(session, request.callback_data)
        session_manager.set(uid, session)
        return {"ok": True}
    if not check_rate_limit(uid):
        await deliver_text(session, "⚠️ Trop de messages. Attends 1 minute.")
        return {"ok": True}
    logger.info(f"[chat] tg user={uid} text={request.text[:50]!r}")
    message, session = await process_text_message(session, request.text)
    session_manager.set(uid, session)
    await deliver_text(session, message, with_menu=session.get("onboarding_complete"))
    return {"ok": True}

@app.post("/api/chat-cv")
async def chat_cv(file: UploadFile = File(...), user_id: str = Form("unknown"), chat_id: str = Form("0"), username: str = Form("utilisateur"), _auth: bool = Depends(verify_api_key)):
    session = session_manager.get(user_id) or session_manager.create_default(user_id, chat_id, username)
    session["channel"] = "telegram"
    session["chat_id"] = chat_id
    session["username"] = username
    if not (file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")):
        await deliver_text(session, "❌ Envoie ton CV en PDF.")
        return {"ok": True}
    pdf_bytes = await file.read()
    await process_cv(session, pdf_bytes, file.filename or "cv.pdf")
    return {"ok": True}

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
    ck = "tav:" + hashlib.sha1(f"{query}|{max_results}".encode("utf-8", "ignore")).hexdigest()
    cached = cache.get(ck)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post("https://api.tavily.com/search", json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": False,
            })
        if r.status_code != 200:
            logger.error(f"Tavily {r.status_code}: {r.text[:200]}")
            return []
        results = r.json().get("results", []) or []
        cache.set(ck, results, 21600)
        return results
    except Exception as e:
        logger.error(f"Tavily erreur: {e}")
        return []

# Flux RSS de bourses / opportunités (sources réelles, sans clé API)
SOURCE_FEEDS = [
    "https://www.scholars4dev.com/feed/",
    "https://opportunitydesk.org/feed/",
    "https://www.opportunitiesforafricans.com/feed/",
]

async def fetch_rss(url: str) -> list:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "NexMoveBot/1.0"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        items = []
        for it in root.iter("item"):
            titre = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = re.sub("<[^>]+>", " ", (it.findtext("description") or ""))
            desc = re.sub(r"\s+", " ", desc).strip()[:300]
            pub = (it.findtext("pubDate") or "").strip()
            if titre and link:
                items.append({"titre": titre, "url": link, "resume": desc, "date": pub})
        return items[:30]
    except Exception as e:
        logger.error(f"RSS {url}: {e}")
        return []

async def ingest_feeds() -> int:
    total = 0
    for url in SOURCE_FEEDS:
        for it in await fetch_rss(url):
            if opp_store.add_source(it):
                total += 1
    return total

def _domain(url):
    d = re.sub(r"^https?://(www\.)?", "", str(url or "")).split("/")[0]
    return d[:40]

async def run_osint(profil: dict, cible: str = "") -> dict:
    profil = profil or {}
    prefs = profil.get("preferences", {}) or {}
    nationalite = prefs.get("nationalite") or "béninoise"
    financement = prefs.get("financement") or "non précisé"
    pays_cibles = prefs.get("pays_cibles") or ""
    objectif = prefs.get("objectif") or "tous"
    resume = profil.get("resume_profil", "")
    formations = [f.get("diplome", "") for f in (profil.get("formation") or []) if f.get("diplome")][:3]
    experiences = [f"{e.get('poste','')} ({e.get('organisation','')})" for e in (profil.get("experience") or []) if e.get("poste")][:3]
    competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))[:8]
    mots = prefs.get("mots_cles") or ""
    if mots and mots.lower() not in ("tous", "aucun", "aucune", "-", ""):
        domaine = mots
    else:
        last_poste = (profil.get("experience") or [{}])[0].get("poste", "")
        domaine = last_poste or (resume[:60]) or (formations[0] if formations else "") or "opportunités internationales"
    cible = (cible or "").strip() or f"{domaine} {pays_cibles}".strip() or "opportunités internationales"
    cible_lower = cible.lower()
    pays_detecte = next((p for p in VISA_DB if p != "default" and (p in cible_lower or p in pays_cibles.lower())), None)
    visa_info = VISA_DB.get(pays_detecte, VISA_DB["default"])
    today = datetime.now(timezone.utc).date().isoformat()
    profil_txt = (f"résumé: {resume[:200]} | formations: {', '.join(formations) or '—'} | "
                  f"expériences: {', '.join(experiences) or '—'} | compétences: {competences} | "
                  f"objectif: {objectif} | financement: {financement} | nationalité: {nationalite}")

    grounded = []
    if TAVILY_API_KEY:
        type_mot = {"étudier": "bourse", "etudier": "bourse", "bourse": "bourse",
                    "fellowship": "fellowship", "travailler": "emploi"}.get(objectif, "bourse OR emploi OR formation")
        zone = pays_detecte or pays_cibles or ""
        query = f"{type_mot} {domaine} {zone} 2026 candidature".strip()
        grounded = await tavily_search(query, 8)

    if grounded:
        sources_txt = "\n".join(f"[{i}] {s.get('title','')} — {(s.get('content','') or '')[:200]}"
                                for i, s in enumerate(grounded[:8]))
        system = ("Tu es expert en orientation et mobilité internationale. On te fournit des RÉSULTATS WEB numérotés. "
                  "Choisis UNIQUEMENT ceux vraiment PERTINENTS pour le PARCOURS RÉEL du candidat (respecte une éventuelle "
                  "reconversion : cible son domaine ACTUEL/visé, pas ses anciens diplômes). Réponds avec l'INDEX du résultat "
                  "(jamais d'URL inventée). Ignore le hors-sujet. JSON uniquement.")
        prompt = f"""PROFIL CANDIDAT: {profil_txt}
DOMAINE VISÉ: {domaine} · PAYS: {pays_detecte or pays_cibles or 'indifférent'}
DATE DU JOUR: {today}. Exclus les deadlines passées.
RÉSULTATS WEB (choisis par INDEX):
{sources_txt}
Sélectionne 3 à 5 résultats PERTINENTS pour CE profil. Donne l'index de chacun.
JSON: {{"opportunites":[{{"index":0,"type":"emploi|bourse|fellowship|formation","financement":"total|partiel|aucun","deadline":"","deadline_iso":"","confiance":"haute|moyenne|faible","score_composite":0,"raison":"pourquoi ça matche CE profil"}}],"conseil_principal":""}}"""
        result = await call_groq(system, prompt, temperature=0.1, max_tokens=1500)
        clean = []
        for o in result.get("opportunites", []):
            try:
                idx = int(o.get("index", -1))
            except Exception:
                idx = -1
            if 0 <= idx < len(grounded):
                src = grounded[idx]
                o["titre"] = src.get("title", "")
                o["url"] = src.get("url", "")
                o["organisation"] = _domain(src.get("url", ""))
                clean.append(o)
        result["opportunites"] = clean
        footer = "🌐 _Sources web réelles — vérifie l'éligibilité et la deadline sur chaque lien._"
    else:
        system = ("Tu es expert en orientation et mobilité internationale pour ressortissants africains. "
                  "Respecte le PARCOURS RÉEL (reconversion incluse) : cible le domaine actuel/visé. "
                  "Ne cite QUE des organismes RÉELS (DAAD, Campus France, Erasmus Mundus, Chevening, AUF, "
                  "Mastercard Foundation, Mitacs...). N'invente jamais d'URL (portail officiel en clair). JSON uniquement.")
        prompt = f"""PROFIL CANDIDAT: {profil_txt}
DOMAINE VISÉ: {domaine} · PAYS: {pays_detecte or pays_cibles or 'Non précisé'}
DATE DU JOUR: {today}. Uniquement des opportunités ouvertes ou à venir.
Donne 3 à 5 opportunités RÉELLES adaptées à CE profil.
JSON: {{"opportunites":[{{"titre":"","organisation":"","type":"emploi|bourse|fellowship|formation","portail_officiel":"","financement":"total|partiel|aucun","deadline":"","deadline_iso":"","confiance":"haute|moyenne|faible","score_composite":0,"raison":""}}],"conseil_principal":""}}"""
        result = await call_groq(system, prompt, temperature=0.15, max_tokens=1500)
        footer = "⚠️ _Pistes générées par IA — à vérifier sur les sites officiels._"

    opps = result.get("opportunites", [])
    _today_d = datetime.now(timezone.utc).date()
    def _open(o):
        di = str(o.get("deadline_iso", "") or "")[:10]
        if not di:
            return True
        try:
            return datetime.strptime(di, "%Y-%m-%d").date() >= _today_d
        except Exception:
            return True
    opps = [o for o in opps if _open(o)]
    titre_aff = _md_clean(domaine)[:40]
    conf_emoji = {"haute": "🟢", "moyenne": "🟡", "faible": "🔴"}
    msg = f"🌍 *NexMove — {titre_aff}*\n━━━━━━━━━━━━━━━━━━\n"
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
        msg += f"{i}. {_type_label(opp.get('type',''))}  {emoji}\n   *{titre}*\n"
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
        msg += "Aucune opportunité pertinente trouvée. Précise un domaine : /mobilite <pays> <domaine>.\n\n"
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
    ingested = await ingest_feeds()
    users = session_manager.list_active()
    sem = asyncio.Semaphore(5)
    async def _one(s):
        async with sem:
            n = 0
            profil = s.get("profil", {}) or {}
            prefs = profil.get("preferences", {}) or {}
            try:
                res = await run_osint(profil, "")
                for opp in res.get("opportunites", []):
                    if opp_store.add(s.get("user_id"), opp):
                        n += 1
            except Exception as e:
                logger.error(f"[collect] osint user={s.get('user_id')}: {e}")
            try:
                kws = []
                for key in ("mots_cles", "objectif", "pays_cibles"):
                    kws += str(prefs.get(key, "")).replace(",", " ").split()
                kws += (profil.get("competences", {}).get("techniques", []))[:6]
                for src in opp_store.search_sources(kws):
                    opp = {"titre": src["titre"], "organisation": "Source vérifiée", "type": "bourse",
                           "url": src["url"], "raison": (src.get("resume") or "")[:150], "score_composite": 62}
                    if opp_store.add(s.get("user_id"), opp):
                        n += 1
            except Exception as e:
                logger.error(f"[collect] sources user={s.get('user_id')}: {e}")
            return n
    counts = await asyncio.gather(*[_one(s) for s in users[:100]])
    total_new = sum(counts)
    logger.info(f"[collect] users={len(users)} sources_ingerees={ingested} nouvelles={total_new}")
    return {"ok": True, "users_actifs": len(users), "sources_ingerees": ingested, "offres_collectees": total_new}

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
            ligne = f"{_type_label(typ)}  {em}\n   *{_md_clean(titre)[:60]}*\n   🏢 {_md_clean(orga)} · 📊 {sc}/100"
            if url:
                ligne += "\n   🔗 " + str(url).replace("*", "").replace("`", "")
            if deadline:
                ligne += "\n   📅 " + _md_clean(deadline)
            lignes.append(ligne)
        msg = ("🔔 *Nouvelles opportunités pour toi*\n━━━━━━━━━━━━━━━━━━\n\n"
               + "\n\n".join(lignes)
               + "\n\n_Utilise /postuler <titre> pour générer CV + lettre._")
        if await deliver_text(s, msg):
            opp_store.mark_notified(ids)
            notified += 1
    # rappels de deadline (J-14 / J-7 / J-3 / J-1)
    today = datetime.now(timezone.utc).date()
    rappels = 0
    for (cid, uid, cible, diso, sent) in opp_store.all_candidatures():
        try:
            d = datetime.strptime(str(diso)[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        days = (d - today).days
        if days < 0 or days > 14:
            continue
        applicable = next((m for m in (1, 3, 7, 14) if days <= m), None)
        if applicable is None or str(applicable) in [p for p in (sent or "").split(",") if p]:
            continue
        s2 = session_manager.get(uid)
        chat2 = s2.get("chat_id") if s2 else None
        if not chat2:
            continue
        rmsg = (f"⏰ *Rappel deadline — J-{days}*\n🗂️ {_md_clean(cible)[:70]}\n📅 {diso}\n\n"
                "Finalise ton dossier ! /dossier pour régénérer, /status pour suivre.")
        if s2 and await deliver_text(s2, rmsg):
            opp_store.mark_reminder(cid, applicable)
            rappels += 1
    logger.info(f"[notify] users_notifies={notified} rappels={rappels}")
    return {"ok": True, "users_notifies": notified, "rappels_deadline": rappels}

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

@app.get("/webhook/whatsapp")
async def wa_verify(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(403, "verify failed")

@app.post("/webhook/whatsapp")
async def wa_webhook(request: Request):
    try:
        body = await request.json()
        for entry in body.get("entry", []):
            for ch in entry.get("changes", []):
                val = ch.get("value", {})
                names = {c.get("wa_id"): (c.get("profile", {}) or {}).get("name", "utilisateur") for c in val.get("contacts", [])}
                for m in val.get("messages", []):
                    frm = m.get("from")
                    if frm:
                        await route_incoming("whatsapp", frm, frm, names.get(frm, "utilisateur"), m)
    except Exception as e:
        logger.error(f"wa webhook: {e}")
    return {"ok": True}

@app.get("/webhook/messenger")
async def fb_verify(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == MESSENGER_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(403, "verify failed")

@app.post("/webhook/messenger")
async def fb_webhook(request: Request):
    try:
        body = await request.json()
        for entry in body.get("entry", []):
            for ev in entry.get("messaging", []):
                psid = (ev.get("sender", {}) or {}).get("id")
                if psid:
                    await route_incoming("messenger", psid, psid, "utilisateur", ev)
    except Exception as e:
        logger.error(f"fb webhook: {e}")
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION, "service": "nexmove-api", "groq_configured": bool(GROQ_API_KEY), "tavily_configured": bool(TAVILY_API_KEY), "telegram_configured": bool(TELEGRAM_TOKEN), "whatsapp_configured": bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_ID), "messenger_configured": bool(MESSENGER_TOKEN), "sessions_stored": session_manager.count(), "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/")
async def root():
    return {"service": f"NexMove API v{VERSION}", "endpoints": ["POST /api/chat", "POST /api/chat-cv", "POST /api/parse-cv", "POST /api/generate-documents", "POST /api/osint", "POST /api/collect", "POST /api/score", "POST /api/notify", "GET /api/session/{user_id}", "GET /health"]}
