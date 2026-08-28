import os, io, json, base64, logging, secrets, time, asyncio, sqlite3, hashlib, re, math, shutil
import html as _htmlmod
import xml.etree.ElementTree as ET
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
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

# OCR optionnel (CV scannés / images). Nécessite le binaire tesseract-ocr + pytesseract.
# Import tolérant : si tesseract n'est pas installé, l'app démarre quand même (OCR désactivé).
# Pillow (utile pour l'OCR ET la compression PDF) importé indépendamment de tesseract.
try:
    from PIL import Image
except Exception:
    Image = None
try:
    import pytesseract
except Exception:
    pytesseract = None
_OCR_IMPORTED = bool(pytesseract and Image)

# Export Word (.docx) optionnel — python-docx est pur Python (aucune dépendance système).
try:
    from docx import Document as _DocxDocument
    from docx.shared import Pt as _DocxPt, RGBColor as _DocxRGB
    _DOCX_OK = True
except Exception:
    _DocxDocument = None
    _DOCX_OK = False

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "service": "forge-nex-api", "msg": record.getMessage(), "module": record.module})

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("forge-nex")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
# Modèles LLM configurables par env : les fournisseurs déprécient régulièrement leurs modèles,
# on peut donc les corriger sans toucher au code (juste .env + redémarrage).
GROQ_MODEL       = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_MODEL_FAST  = os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")
CEREBRAS_MODEL   = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
CEREBRAS_MODEL_FAST = os.getenv("CEREBRAS_MODEL_FAST", "gemma-4-31b")
GEMINI_MODEL     = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")   # gemini-2.0-flash déprécié
GEMINI_MODEL_FAST = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash-lite")
OCR_LANG        = os.getenv("OCR_LANG", "fra+eng")   # packs tesseract requis: tesseract-ocr-fra tesseract-ocr-eng
OCR_MAX_PAGES   = int(os.getenv("OCR_MAX_PAGES", "8"))
OCR_ZOOM        = float(os.getenv("OCR_ZOOM", "2.5")) # facteur de rendu (≈216 dpi) pour une meilleure reconnaissance

def _ocr_available() -> bool:
    """Vrai si pytesseract est importé ET le binaire tesseract est présent."""
    if not _OCR_IMPORTED:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
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
VERSION         = "2.34.0"
WHATSAPP_TOKEN      = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID   = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "nexmove_verify")
MESSENGER_TOKEN     = os.getenv("MESSENGER_TOKEN", "")
MESSENGER_VERIFY_TOKEN = os.getenv("MESSENGER_VERIFY_TOKEN", "nexmove_verify")
# --- Contact / support : où renvoyer les messages /contact ---
ADMIN_CHAT_ID       = os.getenv("ADMIN_CHAT_ID", "")   # ton chat_id Telegram (@userinfobot pour le trouver)
# Quotas journaliers des utilisateurs GRATUITS pour les options coûteuses (l'admin est illimité).
FREE_CV_DAILY       = int(os.getenv("FREE_CV_DAILY", "8"))       # analyses de CV / jour
FREE_GUIDE_DAILY    = int(os.getenv("FREE_GUIDE_DAILY", "12"))   # captures guidées (vision) / jour
CONTACT_EMAIL       = os.getenv("CONTACT_EMAIL", "")
CONTACT_WHATSAPP    = os.getenv("CONTACT_WHATSAPP", "")     # ex : +229XXXXXXXX
CONTACT_CALENDAR    = os.getenv("CONTACT_CALENDAR", "")     # lien Calendly / prise de RDV
# Sources d'emplois structurées (open data). arbeitnow = sans clé ; Adzuna = clés gratuites optionnelles.
ADZUNA_APP_ID   = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY  = os.getenv("ADZUNA_APP_KEY", "")
# Plusieurs pays possibles (séparés par des virgules) : ex "fr,ca,be". Doivent être supportés par Adzuna.
ADZUNA_COUNTRIES = [c.strip().lower() for c in os.getenv("ADZUNA_COUNTRY", "fr").split(",") if c.strip()][:4]
# Requêtes de secours si aucun mot-clé utilisateur n'est disponible.
ADZUNA_QUERIES  = [q.strip() for q in os.getenv("ADZUNA_QUERIES", "developpeur,data,ingenieur").split(",") if q.strip()]
# Veille : par défaut, la collecte NE lance PAS un appel LLM (osint Tavily) par utilisateur — sinon les
# quotas gratuits explosent (429) avec beaucoup de testeurs. Le digest s'appuie sur le pool de sources
# (RSS + Adzuna + EURAXESS + arbeitnow) matché par profil. L'osint complet reste dispo à la demande (/mobilite).
COLLECT_OSINT_PER_USER = os.getenv("COLLECT_OSINT_PER_USER", "0").lower() in ("1", "true", "yes", "on")

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

# Client HTTP unique et partagé (pool de connexions keep-alive) : évite un handshake TCP/TLS
# à chaque appel sortant (LLM, Tavily, Telegram, WhatsApp, Messenger). Le timeout est passé par requête.
# ── Client HTTP partagé extrait dans http_client.py (PR-B) ──
from http_client import http, shutdown_http  # noqa: F401

@app.on_event("shutdown")
async def _shutdown_http():
    await shutdown_http()

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

# ── IA (LLM + embeddings + vision) extraite dans llm.py (PR-B) ──
from llm import (call_groq, embed_text, semantic_scores, analyze_cv_image_vision,
                 analyze_screenshot_vision,
                 _embeddings_available, _LLM_PROVIDERS, GEMINI_API_KEY, GEMINI_MODEL,
                 GROQ_API_KEY, CEREBRAS_API_KEY)  # noqa: F401

# ── Persistance : 3 stores SQLite extraits dans db.py (PR-A du refactor) ──
from db import (SessionManager, OppStore, Cache, session_manager, opp_store, cache,  # noqa: F401
                profile_store, profile_quality, usage_store)


# (Embeddings/vision : voir llm.py — PR-B)

ETAPE_INSTRUCTIONS = {
    "WELCOME": "Accueille chaleureusement l'utilisateur. Présente NexMove en 2 phrases: agent IA pour préparer son prochain départ (études, emploi, bourses, mobilité internationale) adapté à son profil. Demande d'envoyer le CV (PDF, Word ou image).",
    "ATTENTE_CV": "L'utilisateur doit envoyer son CV (PDF, Word ou image). Rappelle-lui brièvement.",
    "CV_RECU": "Le CV a été analysé. L'utilisateur confirme les informations. Réponds Oui pour passer aux préférences.",
    "PREFERENCES": "Collecte des préférences (gérée par le code).",
    "CONFIRMATION": "Résume le profil complet et demande confirmation finale (Oui pour démarrer).",
    "ACTIF": "L'onboarding est terminé. Réponds DIRECTEMENT et utilement (tutoie, ne re-salue PAS). Oriente vers la bonne commande : /veille & /mobilite (opportunités), /campusfrance & /parcours (études en France, étape par étape), /ecoles (choisir une école), /logement, /entretien (prépa entretien Campus France/visa), /canada (immigration Canada selon le profil), /dossier <cible> (documents + CV + projet), /postuler <cible> (CV + lettre), /formations, /status."
}

REPONSES_POSITIVES = {"oui", "yes", "ok", "correct", "exacte", "c'est bon", "parfait", "valide", "confirme"}

def detecter_reponse_positive(text: str) -> bool:
    return any(r in text.lower().strip() for r in REPONSES_POSITIVES)

JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}

def _get_notif(session: dict) -> dict:
    """Préférences de notification de l'utilisateur (défaut : activées, quotidien)."""
    n = session.get("notif") or {}
    return {"enabled": n.get("enabled", True), "freq": n.get("freq", "quotidien"), "jour": n.get("jour", "lundi")}

# Persona partagée : conseiller d'orientation & mobilité internationale senior.
CONSEILLER_PERSONA = (
    "Tu es un conseiller d'orientation et en mobilité internationale SENIOR (15 ans d'expérience), "
    "bienveillant, direct et concret, qui connaît les réalités des candidats d'Afrique de l'Ouest "
    "francophone (Bénin, etc.). Tu personnalises selon le profil, tu es HONNÊTE sur la faisabilité, "
    "et tu donnes toujours des étapes actionnables.")

_NIVEAU_RANK = [
    (("doctorat", "phd", "ph.d", "doctorate"), 5),
    (("master", "ingénieur", "ingenieur", "msc", "mba", "m2", "m1", "dea", "dess", "magist"), 4),
    (("licence", "bachelor", "bsc", "l3", "maîtrise", "maitrise"), 3),
    (("bts", "dut", "deug", "dts", "l2", "l1"), 2),
    (("baccalauréat", "baccalaureat", "bac", "high school"), 1),
]

def _diplome_rank(f: dict):
    txt = f"{f.get('diplome','')} {f.get('domaine','')}".lower()
    lvl = 0
    for kws, r in _NIVEAU_RANK:
        if any(k in txt for k in kws):
            lvl = max(lvl, r)
    m = re.search(r"(19|20)\d{2}", str(f.get("annee", "")))
    return (lvl, int(m.group(0)) if m else 0)

def _sort_formations(formation):
    """Trie les formations du diplôme le PLUS ÉLEVÉ/récent au plus ancien (retour testeur :
    le bot retenait la licence au lieu du master)."""
    return sorted([f for f in (formation or []) if isinstance(f, dict)], key=_diplome_rank, reverse=True)

def _is_travail(objectif) -> bool:
    return any(k in str(objectif or "").lower() for k in ("travail", "emploi", "job", "poste", "stage"))

def _is_admin(session: dict) -> bool:
    """Vrai si la session est celle de l'administrateur (quotas illimités)."""
    if not ADMIN_CHAT_ID:
        return False
    return str(ADMIN_CHAT_ID) in (str(session.get("chat_id") or ""), str(session.get("user_id") or ""))

def _quota_check(session: dict, feature: str, limit: int) -> tuple[bool, int]:
    """(autorisé, restant). L'admin est toujours autorisé et n'est pas décompté."""
    if _is_admin(session) or limit <= 0:
        return True, 999
    used = usage_store.count(session.get("user_id"), feature)
    return used < limit, max(0, limit - used)

def _quota_bump(session: dict, feature: str) -> None:
    if not _is_admin(session):
        try:
            usage_store.bump(session.get("user_id"), feature)
        except Exception as e:
            logger.error(f"quota bump {feature}: {e}")

def _quota_exceeded_msg(feature_label: str) -> str:
    return (f"🚦 Tu as atteint ta *limite gratuite du jour* pour {feature_label}.\n\n"
            "Réessaie demain, ou tape /contact pour un accès étendu. "
            "_Cette limite protège le service et reste généreuse pour un usage normal._")

# Mots parasites d'un nom de fichier de CV (à ignorer pour deviner le nom du candidat).
_CV_FILENAME_NOISE = {"cv", "resume", "résumé", "resumé", "curriculum", "vitae", "final", "finale",
                      "copie", "copy", "doc", "document", "def", "version", "new", "nouveau",
                      "mon", "my", "the", "pdf", "docx", "word", "scan", "scanned", "photo",
                      "img", "image", "portfolio", "profil", "profile", "candidature", "maj"}

def _name_from_filename(filename: str) -> str:
    """Devine un nom à partir du nom de fichier du CV — repli quand l'OCR/LLM ne trouve pas le nom
    (ex. « CV_Judicael.pdf » -> « Judicael », « cv-jean-dupont.pdf » -> « Jean Dupont »)."""
    base = (filename or "").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    base = re.sub(r"[_\-.+]+", " ", base)
    base = re.sub(r"\d+", " ", base)
    mots = [m for m in base.split()
            if len(m) > 1 and m.lower() not in _CV_FILENAME_NOISE and re.search(r"[A-Za-zÀ-ÿ]", m)]
    if not mots:
        return ""
    return " ".join(m.capitalize() for m in mots[:3]).strip()

def _free_text_to_command(low: str, t: str) -> str:
    """Route un message libre (utilisateur actif) vers la bonne commande selon l'intention."""
    if any(k in low for k in ("formation", "certif", "cours en ligne", "me former", "se former")):
        return "/formations " + t
    if any(k in low for k in ("logement", "loger", "appartement", "crous", "résidence", "residence")):
        return "/logement " + t
    if "budget" in low or "coût de la vie" in low or "cout de la vie" in low:
        return "/budget " + t
    if any(k in low for k in ("école", "ecole", "universit", "quelle formation", "quel master", "programme d'étude")):
        return "/ecoles " + t
    if "parcoursup" in low or "parcours-sup" in low or "parcours sup" in low:
        return "/parcoursup"
    if "monmaster" in low or "mon master" in low or "mon-master" in low:
        return "/monmaster"
    if "ecandidat" in low or "e-candidat" in low or "candidature directe universit" in low:
        return "/ecandidat"
    if "dap" in low.split() or "demande d'admission" in low:
        return "/dap"
    if "visa" in low or "capago" in low or "vfs" in low or "consulat" in low or "consulaire" in low:
        return "/visa"
    if "recours" in low or "refus" in low or "contestation" in low or "appel" in low:
        return "/recours"
    if low in ("version", "quelle version", "c'est quelle version", "numero de version") or "version du bot" in low:
        return "/version"
    if any(k in low for k in ("contact", "contacter", "joindre", "rencontrer", "rendez-vous", "rendez vous", "rdv", "parler à quelqu'un", "parler a quelqu'un", "un humain", "un conseiller")):
        return "/contact" + ((" " + t) if len(t) > 15 else "")
    if "campus france" in low or "études en france" in low or "etudes en france" in low:
        return "/campusfrance"
    if "canada" in low or "québec" in low or "quebec" in low:
        return "/canada"
    if any(k in low for k in ("bourse", "opportunit", "offre d'emploi", "emploi", "poste", "stage", "recrut", "fellowship")):
        return "/mobilite " + t
    return ""

# Commandes que le routeur d'intention LLM peut déclencher à partir d'une phrase libre.
_VALID_INTENTS = {"veille", "mobilite", "formations", "ecoles", "logement", "entretien", "campusfrance",
                  "canada", "procedure", "budget", "eligibilite", "dossier", "postuler", "compresser",
                  "traduire", "status", "profil", "parcours", "aide", "fusionner", "enpdf", "decouper",
                  "parcoursup", "monmaster", "ecandidat", "dap", "visa", "recours",
                  "contact", "version", "rencontrer"}

def _progress_bar(done: int, total: int, taille: int = 8) -> str:
    total = max(total, 1)
    plein = round(taille * min(done, total) / total)
    return "▓" * plein + "░" * (taille - plein) + f" {min(done,total)}/{total}"

# Source unique de vérité de l'onboarding : champ -> (question, choix cliquables).
# L'ORDRE et l'INCLUSION des questions sont calculés dynamiquement (_build_pref_plan) selon
# les réponses déjà données — onboarding ADAPTATIF (ex. pas de nationalité/passeport ni de
# financement d'études pour un simple stage/job LOCAL).
PREF_FIELDS: dict[str, tuple[str, Optional[list]]] = {
    "objectif":            ("🎯 Quel est ton objectif principal ?\n(travailler / étudier / bourse / fellowship / tous)",
                            ["Travailler", "Étudier", "Bourse", "Fellowship", "Tous"]),
    "pays_cibles":         ("🌍 Quels pays ou régions vises-tu ?\n(ex : France, Canada… — ou ton *propre pays* pour des offres locales, ou « tous »)",
                            None),
    "nationalite":         ("🛂 Quelle est ta nationalité (pays du passeport) ?", None),
    "financement":         ("💰 Financement : bourse indispensable, tu peux auto-financer, ou peu importe ?",
                            ["Bourse indispensable", "Auto-financement", "Peu importe"]),
    "certifs_langue":      ("🗣️ Certifications de langue ?\n(IELTS/TOEFL/TCF/DELF + score, ou « aucune »)", None),
    "langues_opportunite": ("🌐 Langue des opportunités ? (français / anglais / les deux)",
                            ["Français", "Anglais", "Les deux"]),
    "niveau":              ("🎓 Ton niveau ? (étudiant / professionnel)",
                            ["Étudiant", "Professionnel"]),
    "mots_cles":           ("🔑 Des mots-clés à cibler ?\n(ex : cybersécurité, cloud, réseau — ou « aucun »)", None),
}
# Compat : quelques helpers/tests attendent encore ces noms (dérivés de la source ci-dessus).
PREF_QUESTIONS = [(f, q) for f, (q, _c) in PREF_FIELDS.items()]
PREF_CHOICES = {f: c for f, (_q, c) in PREF_FIELDS.items() if c}

_CONFIRM_KB = [("✅ Oui, c'est bon", "onb:oui"), ("🔄 Recommencer", "onb:non")]

# Indices d'une cible de mobilité internationale (=> nationalité/passeport + certifs pertinents).
_INTL_HINTS = ("france", "canada", "belg", "allemag", "suisse", "luxembourg", "pays-bas",
               "europe", "usa", "état-unis", "etats-unis", "états unis", "etats unis",
               "royaume", " uk", "angleterre", "étrang", "etrang", "international", "monde",
               "ailleurs", "expat", "dubai", "émirat", "emirat", "qatar", "maroc", "tunisie",
               "algér", "alger", "afrique du sud", "sénégal", "senegal", "côte d'ivoire",
               "cote d'ivoire", "abidjan", "portugal", "espagne", "italie", "chine", "japon",
               "australie", "turquie", "russie", "inde")

def _vise_international(prefs: dict) -> bool:
    """L'utilisateur vise-t-il (aussi) l'étranger ? Si les pays ne sont pas encore connus,
    on renvoie True (on ne prive pas l'utilisateur d'une question tant qu'on ne sait pas)."""
    pays = str(prefs.get("pays_cibles", "")).lower().strip()
    if not pays:
        return True
    if any(k in pays for k in ("tous", "peu importe", "partout", "n'importe", "monde")):
        return True
    return any(h in pays for h in _INTL_HINTS)

def _build_pref_plan(prefs: dict) -> list[str]:
    """Liste ORDONNÉE des questions d'onboarding à poser, selon les réponses déjà données.
    Recalculée à chaque étape : la nationalité (passeport) et le financement d'études ne sont
    demandés QUE s'ils ont du sens (mobilité internationale / parcours d'études-bourse)."""
    objectif = str(prefs.get("objectif", "")).lower()
    etudes  = any(k in objectif for k in ("étud", "etud", "bourse", "fellowship", "master",
                                          "doctorat", "licence", "tous", "tout"))
    travail = _is_travail(objectif)
    plan = ["objectif", "pays_cibles"]
    # Nationalité : mobilité internationale, études/immigration, ou objectif indéterminé.
    if etudes or (travail and _vise_international(prefs)) or not (travail or etudes):
        plan.append("nationalite")
    # Financement d'études : pas pertinent pour un simple job.
    if etudes or not travail:
        plan.append("financement")
    # Certifs de langue : surtout pour l'international (admission, visa).
    if etudes or _vise_international(prefs):
        plan.append("certifs_langue")
    plan += ["langues_opportunite", "niveau", "mots_cles"]
    return plan

def _ask_pref(session: dict, field: str) -> str:
    """Renvoie l'intitulé de la question `field` et arme les boutons de choix (si fermée)."""
    q, choix = PREF_FIELDS[field]
    session["pref_current"] = field
    session["_kb_options"] = [(c, "pref:" + c) for c in choix] if choix else None
    return q

def _pref_question(session: dict, idx: int) -> str:
    """Compat : première question du plan (utilisé au (re)démarrage de l'onboarding)."""
    return _ask_pref(session, "objectif")

def valider_pref(field: str, value: str) -> tuple[bool, str]:
    """Vérifie la cohérence d'une réponse d'onboarding.
    Retourne (valide, indice). L'indice est affiché quand la réponse est incohérente."""
    v = (value or "").strip()
    low = v.lower()
    if not v or low.startswith("/"):
        return False, "Réponds directement à la question (pas une commande)."
    if len(v) < 2:
        return False, "Réponse trop courte, précise un peu."
    if field == "objectif":
        if any(k in low for k in ("travail", "étud", "etud", "bourse", "fellowship", "tous", "tout", "stage", "emploi", "job", "master", "doctorat")):
            return True, ""
        return False, "Choisis parmi : travailler / étudier / bourse / fellowship / tous."
    if field == "financement":
        if any(k in low for k in ("bourse", "auto", "finance", "peu importe", "propre", "moyen", "fonds", "économie", "economie", "parent", "épargne", "epargne")):
            return True, ""
        return False, "Réponds : bourse indispensable / auto-financement / peu importe."
    if field == "certifs_langue":
        if any(k in low for k in ("ielts", "toefl", "tcf", "tef", "delf", "dalf", "cambridge", "goethe", "duolingo", "linguaskill", "aucun", "non", "rien", "sans", "pas de", "pas encore")) or any(c.isdigit() for c in low):
            return True, ""
        return False, "Indique un test réel (IELTS, TOEFL, TCF, DELF… avec le score) ou « aucune »."
    if field == "langues_opportunite":
        if any(k in low for k in ("franç", "franc", "anglais", "english", "deux", "both", "tous", "toutes", "peu importe")) or low in ("fr", "en"):
            return True, ""
        return False, "Réponds : français / anglais / les deux."
    if field == "niveau":
        if any(k in low for k in ("étud", "etud", "pro", "licence", "master", "bac", "doctorat", "phd", "travaill", "junior", "senior", "débutant", "debutant", "confirmé", "confirme", "diplôm", "diplom")):
            return True, ""
        return False, "Réponds : étudiant ou professionnel (ou ton dernier diplôme : licence, master…)."
    # Champs libres (nationalite, pays_cibles, mots_cles) : on accepte tout texte non-commande.
    return True, ""

AIDE_TXT = ("🧭 *NexMove — que veux-tu faire ?*\n\n"
            "🔎 *Trouver des opportunités*\n"
            "/veille · /mobilite <pays ou domaine>\n\n"
            "🇫🇷 *Étudier en France (accompagnement pas à pas)*\n"
            "/campusfrance · /parcours · /ecoles <domaine> · /logement <ville> · /entretien\n"
            "🧭 Bloqué sur une plateforme ? /guide — envoie une *capture d'écran*, je te guide.\n\n"
            "🌍 *Autres destinations*\n"
            "/canada · /procedure <pays> (Belgique, Allemagne, Suisse, Luxembourg, Pays-Bas…)\n"
            "/eligibilite <cible> · /budget <ville>\n\n"
            "📄 *Candidater*\n"
            "/dossier <cible> (documents + CV + projet) · /postuler <cible> (CV + lettre)\n"
            "/formations <domaine> (te distinguer)\n\n"
            "🛠️ *Outils PDF & docs*\n"
            "/compresser <Ko> · /fusionner · /enpdf (images→PDF) · /decouper <pages> · /traduire <texte>\n\n"
            "📊 *Mon espace*\n"
            "/profil · /moncode (sauvegarde) · /moi <code> (restaurer) · /status · /rappels · /digest · /supprimer\n"
            "/contact (nous joindre / rencontrer un conseiller) · /version\n\n"
            "💡 Nouveau ? Tape /tuto. Sinon commence par /veille ou /campusfrance.")

TUTO_TXT = ("📖 *Guide NexMove*\n\n"
            "*1. Ton profil* — envoie ton *CV (PDF, Word ou image)*. Je l'analyse, puis je te pose quelques questions "
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
            "Prêt ? Envoie ton *CV (PDF, Word ou image)* pour démarrer. 🚀")

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
# Action concrète + commande d'aide pour l'étape en cours (accompagnement actif)
CF_STAGE_HELP = [
    "Crée ton compte sur etudesenfrance.diplomatie.gouv.fr. Pas sûr de tes choix ? Tape /ecoles <domaine>.",
    "Remplis tes vœux et ton projet d'études. /ecoles pour cibler, /dossier <programme> pour rédiger le projet.",
    "Règle les frais Campus France (montant selon ton pays).",
    "Prépare l'entretien Campus France / Institut Français : tape /entretien.",
    "Relance et suis les réponses des établissements. /status pour le suivi.",
    "Accepte la meilleure offre et confirme ton inscription.",
    "Dépose ta demande de visa (entretien Capago/VFS) : tape /entretien visa.",
    "Organise ton arrivée : /logement <ville>, puis billet et assurance.",
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
            + (f"• Type de poste : {prefs.get('type_emploi')}\n" if prefs.get('type_emploi') else "")
            + f"• Mots-clés : {prefs.get('mots_cles','—')}\n\n"
            "Tout est correct ? Réponds *Oui* pour lancer, ou *Non* pour recommencer.")

async def process_text_message(session: dict, text: str) -> tuple[str, dict]:
    t = (text or "").strip()
    low = t.lower()
    now = datetime.now(timezone.utc).isoformat()

    if low.startswith("/start"):
        session["etape"] = "ATTENTE_CV"; session["profil"] = {}; session["historique"] = []
        session["cv_parsed"] = False; session["cv_file_id"] = None
        session["onboarding_complete"] = False; session["pref_current"] = None
        msg = ("👋 *Bienvenue sur NexMove !*\n"
               "_Ton agent IA pour préparer ton prochain départ : études, emploi, bourses et mobilité internationale._\n\n"
               "Voici comment ça marche :\n"
               "1️⃣ Envoie-moi ton *CV (PDF, Word ou image)* — j'analyse ton profil.\n"
               "2️⃣ Je te pose quelques questions (objectif, pays, financement…).\n"
               "3️⃣ Ensuite : /veille (trouver), /campusfrance (études en France), /postuler (CV + lettre).\n\n"
               "📄 *Pour commencer, envoie ton CV (PDF, Word ou image).*  (ou tape /tuto pour le guide)")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/aide") or low.startswith("/help") or low.startswith("/menu"):
        _push(session, "user", t); _push(session, "assistant", AIDE_TXT); session["derniere_activite"] = now
        session["_show_menu"] = True
        return AIDE_TXT, session

    if low.startswith("/tuto"):
        _push(session, "user", t); _push(session, "assistant", TUTO_TXT); session["derniere_activite"] = now
        return TUTO_TXT, session

    if low.startswith("/guide"):
        # Mode guidage par capture d'écran (vision) : l'utilisateur envoie des captures, on l'oriente.
        session["guide_mode"] = True
        session["tool_mode"] = None
        # Contexte optionnel : /guide campus france -> aide ciblée
        parts = t.split(maxsplit=1)
        session["guide_context"] = parts[1].strip() if len(parts) > 1 else ""
        msg = ("🧭 *Mode guidage activé.*\n\n"
               "Envoie-moi une *capture d'écran* de là où tu es bloqué·e (Campus France / Études en France, "
               "Parcoursup, Mon Master, eCandidat, un formulaire, un e-mail d'admission…) et je te dis "
               "*quoi faire à cette étape précise*.\n\n"
               "_Tape /annuler pour quitter le mode guidage._")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

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
            msg += "🌐 _Vérifie toujours les dates sur campusfrance.org._\n\n"
            msg += ("✍️ *Je t'accompagne pas à pas :*\n"
                    "• /ecoles <domaine> — trouver les bonnes écoles\n"
                    "• /parcours — suivre tes étapes jusqu'au départ ✈️\n"
                    "• /entretien — préparer l'entretien Campus France / visa\n"
                    "• /logement <ville> — te loger sans arnaque\n"
                    "• /dossier <programme> — monter le dossier (CV + projet)")
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
        hint = CF_STAGE_HELP[stage] if stage < len(CF_STAGE_HELP) else ""
        msg = ("🇫🇷 *Ton parcours Campus France*\n━━━━━━━━━━━━━━━━━━\n\n" + "\n".join(lines) +
               f"\n\nÉtape {pos}/{len(CF_STAGES)}")
        if hint:
            msg += f"\n👉 *Maintenant :* {hint}"
        msg += "\n\nTape /etape quand tu as terminé l'étape en cours."
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

    if low.startswith("/ecoles") or low.startswith("/écoles") or low.startswith("/ecole"):
        profil = session.get("profil", {}) or {}
        prefs = profil.get("preferences", {}) or {}
        parts = t.split(maxsplit=1)
        domaine = parts[1].strip() if len(parts) > 1 else (prefs.get("mots_cles") or (profil.get("formation") or [{}])[0].get("domaine", "") or "ton domaine")
        pays = prefs.get("pays_cibles") or "France"
        if not profil.get("identite"):
            msg = "📄 Fais d'abord /start puis envoie ton CV — je cible ensuite les écoles adaptées."
        else:
            try:
                msg = await conseil_grounded(profil,
                    f"🏫 *Écoles & programmes — {_md_clean(domaine)}*",
                    f"meilleures écoles universités programmes {domaine} {pays} admission candidature 2026 étudiant international",
                    "Recommande 4 à 6 écoles/programmes RÉELS et ADAPTÉS au profil (niveau, domaine, budget/bourse), du plus accessible au plus sélectif, avec pour chacun comment et quand postuler.",
                    cta="Ensuite : /dossier <programme> (préparer le dossier) · /logement <ville> · /entretien.")
            except Exception as e:
                logger.error(f"ecoles: {e}"); msg = "😕 Recherche d'écoles indisponible, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/logement"):
        profil = session.get("profil", {}) or {}
        parts = t.split(maxsplit=1)
        ville = parts[1].strip() if len(parts) > 1 else ((profil.get("preferences", {}) or {}).get("pays_cibles") or "France")
        try:
            msg = await conseil_grounded(profil,
                f"🏠 *Logement étudiant — {_md_clean(ville)}*",
                f"logement étudiant {ville} CROUS résidence universitaire garant Visale plateforme fiable budget arnaque 2026",
                "Explique concrètement comment trouver un logement étudiant abordable et ÉVITER LES ARNAQUES : CROUS/résidences, plateformes fiables, dispositif garant Visale, budget réaliste, pièces à préparer, délais.",
                cta="🔎 Commence tôt, les logements partent vite. /entretien pour la suite.")
        except Exception as e:
            logger.error(f"logement: {e}"); msg = "😕 Conseils logement indisponibles, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/entretien"):
        profil = session.get("profil", {}) or {}
        parts = t.split(maxsplit=1)
        sujet = parts[1].strip() if len(parts) > 1 else "Campus France et visa"
        try:
            msg = await conseil_grounded(profil,
                f"🎤 *Préparation entretien — {_md_clean(sujet)}*",
                f"questions entretien {sujet} Campus France Institut Français entretien visa étudiant conseils réponses 2026",
                "Prépare l'utilisateur à l'entretien (Campus France/Institut Français et/ou entretien visa type Capago/VFS). Donne 5 à 7 QUESTIONS TYPES avec, pour chacune, une PISTE de réponse ADAPTÉE à son profil, plus les erreurs à éviter et la posture attendue (projet cohérent, financement, retour au pays).",
                cta="Cible si besoin : /entretien visa Capago · /entretien Campus France.")
        except Exception as e:
            logger.error(f"entretien: {e}"); msg = "😕 Prépa entretien indisponible, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/canada"):
        profil = session.get("profil", {}) or {}
        prefs = profil.get("preferences", {}) or {}
        if not profil.get("identite"):
            msg = "📄 Fais d'abord /start puis envoie ton CV — je détermine ensuite la meilleure voie Canada pour toi."
        else:
            try:
                msg = await conseil_grounded(profil,
                    "🇨🇦 *Immigration Canada — voies adaptées à ton profil*",
                    f"immigration Canada IRCC permis d'études PGWP Entrée express catégories prioritaires rondes fondées catégories francophones santé métiers spécialisés STIM transports éducation agriculture PEQ Arrima Québec {prefs.get('objectif','')} {prefs.get('niveau','')} 2026 conditions",
                    ("Détermine la ou les VOIES canadiennes les plus adaptées à CE profil et explique-les par étapes : "
                     "permis d'études (attestation provinciale/PAL, preuve de fonds à jour) si étudiant ; PGWP puis Entrée "
                     "express / RP si diplômé/travailleur ; PEQ/Arrima Québec si visé Québec (avantage francophone). "
                     "IMPORTANT — Entrée express : mentionne les *rondes fondées sur les catégories* d'IRCC (invitations "
                     "à CRS plus BAS pour ces catégories prioritaires) et dis si le profil est éligible : francophones "
                     "hors Québec (NCLC 7+ en français), santé, métiers spécialisés, STIM, transports, éducation, "
                     "agriculture. Sois HONNÊTE sur les conditions (fonds, langue, points CRS, expérience canadienne)."),
                    cta="Ensuite : /dossier <programme canadien> · /entretien visa · /logement <ville>.")
            except Exception as e:
                logger.error(f"canada: {e}"); msg = "😕 Conseils Canada indisponibles, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/compresser") or low.startswith("/compress") or low.startswith("/alleger"):
        target = 2000  # Ko par défaut (~2 Mo)
        for p in t.split()[1:]:
            d = re.sub(r"[^0-9]", "", p)
            if d:
                target = int(d)
                if target < 50:      # l'utilisateur a probablement donné des Mo
                    target *= 1024
                target = max(100, min(20000, target))
        session["compress_target"] = target
        msg = (f"🗜️ *Compression PDF* — cible ≈ {target} Ko.\n\n"
               "Envoie-moi maintenant le *PDF* à alléger (CV, relevé, passeport scanné…). "
               "Je te renvoie une version plus légère pour tes soumissions en ligne.\n"
               "_Astuce : /compresser 500 pour viser 500 Ko._")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/fusionner") or low.startswith("/fusion"):
        _tool_clear(session.get("user_id")); session["tool_mode"] = "merge"
        msg = ("📎 *Fusion de PDF.*\nEnvoie les PDF à assembler un par un (dans l'ordre voulu), "
               "puis tape */terminer*.\n_/annuler pour arrêter._")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/enpdf") or low.startswith("/img2pdf") or low.startswith("/imagepdf"):
        _tool_clear(session.get("user_id")); session["tool_mode"] = "img2pdf"
        msg = ("🖼️➡️📄 *Images en PDF.*\nEnvoie tes images *en fichier* (📎 Fichier, pas Photo), une par une, "
               "puis */terminer*.\n_/annuler pour arrêter._")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/decouper") or low.startswith("/découper") or low.startswith("/split"):
        parts = t.split(maxsplit=1)
        spec = parts[1].strip() if len(parts) > 1 else ""
        if not spec:
            msg = "✂️ Indique les pages à garder : */decouper 1-3,5*\nPuis envoie le PDF."
        else:
            _tool_clear(session.get("user_id")); session["tool_mode"] = "split"; session["split_spec"] = spec
            msg = f"✂️ *Découpe.* Envoie maintenant le *PDF* — je garde les pages *{spec}*."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/terminer") or low.startswith("/fini") or low.startswith("/generer") or low.startswith("/générer"):
        mode = session.get("tool_mode")
        files = _tool_files(session.get("user_id"))
        if mode not in ("merge", "img2pdf"):
            msg = "Rien à générer. Lance /fusionner (PDF) ou /enpdf (images) d'abord."
        elif not files:
            msg = "📎 Aucun fichier reçu. Envoie au moins un fichier avant /terminer."
        else:
            try:
                if mode == "merge":
                    data = await asyncio.to_thread(merge_pdfs, files); cap = "📎 PDF fusionné"
                else:
                    data = await asyncio.to_thread(images_to_pdf, files); cap = "📄 PDF créé depuis tes images"
                await deliver_file(session, "NexMove_document.pdf", data, f"{cap} ({len(files)} fichier·s)")
                msg = "✅ C'est prêt ! Trop lourd pour une soumission ? Tape /compresser."
            except Exception as e:
                logger.error(f"[tool {mode}] {e}"); msg = "😕 Génération impossible, réessaie."
            _tool_clear(session.get("user_id")); session["tool_mode"] = None
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/annuler") or low.startswith("/cancel"):
        _tool_clear(session.get("user_id"))
        session["tool_mode"] = None; session.pop("split_spec", None); session.pop("compress_target", None)
        session["guide_mode"] = False; session.pop("guide_context", None)
        msg = "🚫 Opération annulée."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/budget") or low.startswith("/cout") or low.startswith("/coût"):
        profil = session.get("profil", {}) or {}
        parts = t.split(maxsplit=1)
        ville = parts[1].strip() if len(parts) > 1 else ((profil.get("preferences", {}) or {}).get("pays_cibles") or "France")
        try:
            msg = await conseil_grounded(profil,
                f"💶 *Budget & coût de la vie — {_md_clean(ville)}*",
                f"coût de la vie étudiant {ville} loyer transport nourriture budget mensuel preuve de ressources visa 2026",
                "Donne un budget mensuel étudiant réaliste (loyer, nourriture, transport, santé, divers) en euros — et l'ordre de grandeur en FCFA — puis rappelle le montant de RESSOURCES à justifier pour le visa/Campus France si connu.",
                cta="Ensuite : /eligibilite <programme> · /compresser (justificatifs).")
        except Exception as e:
            logger.error(f"budget: {e}"); msg = "😕 Estimation budget indisponible, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/eligibilite") or low.startswith("/éligibilité") or low.startswith("/eligible"):
        profil = session.get("profil", {}) or {}
        parts = t.split(maxsplit=1)
        cible = parts[1].strip() if len(parts) > 1 else ""
        if not profil.get("identite"):
            msg = "📄 Fais d'abord /start puis envoie ton CV — je compare ensuite ton profil aux exigences."
        elif not cible:
            msg = "🎯 Précise la cible : */eligibilite <programme ou bourse>*\nEx : /eligibilite Bourse Eiffel master."
        else:
            try:
                msg = await conseil_grounded(profil,
                    f"🎯 *Éligibilité — {_md_clean(cible)}*",
                    f"{cible} conditions éligibilité critères admission prérequis dossier requis 2026",
                    "Compare HONNÊTEMENT le profil aux exigences réelles : dis s'il est éligible / limite / non éligible, liste précisément ce qui MANQUE et comment le combler. Pas de faux espoirs.",
                    cta="Prêt ? /dossier <cible> pour monter le dossier.")
            except Exception as e:
                logger.error(f"eligibilite: {e}"); msg = "😕 Vérification indisponible, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/traduire") or low.startswith("/translate") or low.startswith("/traduction"):
        parts = t.split(maxsplit=1)
        texte = parts[1].strip() if len(parts) > 1 else ""
        if not texte:
            msg = ("🌐 *Traduction (informative).*\nColle le texte à traduire : */traduire <texte>*\n\n"
                   "⚠️ Pour un DOSSIER officiel (diplômes, actes de naissance…), les institutions exigent une "
                   "*traduction assermentée* (traducteur agréé). Ma traduction sert à COMPRENDRE, pas à soumettre.")
        else:
            try:
                r = await call_groq(
                    "Tu es traducteur professionnel. Traduis fidèlement : si le texte est en anglais traduis en français, sinon en anglais. Conserve le sens exact. JSON uniquement.",
                    f'Texte: """{texte[:3000]}"""\nJSON: {{"traduction":"","langue_source":"","langue_cible":""}}',
                    temperature=0.1, max_tokens=1300)
                msg = (f"🌐 *Traduction* ({r.get('langue_source','?')} → {r.get('langue_cible','?')})\n\n"
                       f"{r.get('traduction','')}\n\n⚠️ _Informatif. Un dossier officiel exige un traducteur assermenté._")
            except Exception as e:
                logger.error(f"traduire: {e}"); msg = "😕 Traduction indisponible, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/procedure") or low.startswith("/procédure") or low.startswith("/pays"):
        profil = session.get("profil", {}) or {}
        parts = t.split(maxsplit=1)
        pays = parts[1].strip() if len(parts) > 1 else ""
        if not pays:
            msg = ("🌍 *Procédures par pays.*\nÉcris : */procedure <pays>*\n"
                   "Ex : /procedure Belgique · /procedure Allemagne · /procedure Suisse · /procedure Luxembourg · /procedure Pays-Bas.\n\n"
                   "🇫🇷 France : /campusfrance  ·  🇨🇦 Canada : /canada")
        elif not profil.get("identite"):
            msg = "📄 Fais d'abord /start puis envoie ton CV — je route selon ton profil."
        else:
            try:
                msg = await conseil_grounded(profil,
                    f"🌍 *{_md_clean(pays)} — études & immigration (selon ton profil)*",
                    f"{pays} étudier travailler immigration étudiant permis visa bourse programme officiel procédure {(profil.get('preferences', {}) or {}).get('objectif','')} 2026",
                    f"Explique la ou les VOIES OFFICIELLES adaptées à CE profil pour {pays} (études : université + permis étudiant + preuve de fonds ; travail : permis/visa et programmes officiels). Étapes concrètes, conditions honnêtes, organismes RÉELS.",
                    cta="Ensuite : /ecoles · /budget <ville> · /dossier <programme> · /entretien.")
            except Exception as e:
                logger.error(f"procedure: {e}"); msg = "😕 Infos pays indisponibles, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    # --- Procédures françaises PARALLÈLES à Campus France (grosse demande du terrain) ---
    _FR_PROCS = {
        "parcoursup":   ("🎓 *Parcoursup — 1ʳᵉ année Licence/BUT/BTS/CPGE en France*",
                         "Parcoursup 2026 candidature calendrier étudiant international vœux formations sélectives non sélectives dossier",
                         "Explique CLAIREMENT Parcoursup pour un étudiant international : qui est concerné (bac étranger), calendrier de la campagne EN COURS (inscription, vœux, réponses), types de formations, dossier (bulletins, lettre de motivation par vœu, projet), lien avec Études en France quand nécessaire.",
                         "Ensuite : /ecoles <domaine> · /dossier Parcoursup <formation> · /entretien."),
        "monmaster":    ("📘 *MonMaster — candidatures Master en France*",
                         "MonMaster 2026 candidature master université France calendrier étudiant international dossier lettre projet",
                         "Explique la plateforme MonMaster pour candidater en M1 : calendrier RÉEL en cours, nombre de vœux, critères, différences avec Études en France (Campus France reste souvent obligatoire pour les étudiants hors UE), pièces à préparer.",
                         "Ensuite : /ecoles master <domaine> · /dossier MonMaster <mention> · /campusfrance."),
        "ecandidat":    ("🧾 *eCandidat — candidatures directes université (procédure parallèle)*",
                         "eCandidat 2026 procédure université France candidature directe étudiant international dossier",
                         "Explique eCandidat : quelles universités l'utilisent, quand cette voie remplace/complète Campus France (procédure blanche vs procédure Études en France), calendrier propre à chaque université, dossier type.",
                         "Ensuite : /ecoles <domaine> · /dossier eCandidat <université> · /campusfrance."),
        "dap":          ("📜 *DAP — Demande d'Admission Préalable (1ʳᵉ année licence hors UE)*",
                         "DAP demande admission préalable Campus France 2026 calendrier hors UE licence université France dossier",
                         "Explique la DAP (obligatoire pour candidater en L1 hors UE via Études en France) : qui est concerné, calendrier, épreuves de langue (TCF-DAP/DELF B2), pièces, différences avec Parcoursup.",
                         "Ensuite : /campusfrance · /dossier DAP · /entretien."),
        "visa":         ("🛂 *Visa étudiant France — phase consulaire (VFS/Capago)*",
                         "visa étudiant France VFS Capago 2026 rendez-vous dépôt pièces preuves ressources OFII validation",
                         "Détaille la phase CONSULAIRE APRÈS Campus France : prise de rendez-vous VFS/Capago, pièces à préparer, preuve de ressources (montant à jour), délais, retrait du visa, validation OFII à l'arrivée.",
                         "Ensuite : /budget <ville> · /logement <ville> · /entretien visa."),
        "recours":      ("⚖️ *Recours — refus Campus France ou refus de visa*",
                         "recours refus Campus France refus visa étudiant France 2026 procédure appel commission délais",
                         "Explique HONNÊTEMENT les recours possibles : recours gracieux auprès de Campus France, recours contentieux, refus de visa (Commission de recours contre les décisions de refus de visa d'entrée en France), délais impératifs, pièces à joindre. Reste réaliste sur les chances.",
                         "En parallèle : /procedure Belgique · /procedure Allemagne · /canada."),
    }
    _MATCH_PROC = [(k, k.replace("-", "")) for k in _FR_PROCS] + [
        ("parcoursup", "parcours-sup"), ("monmaster", "mon-master"),
    ]
    _cmd_proc = None
    for k, alias in _MATCH_PROC:
        if low.startswith("/" + alias):
            _cmd_proc = k; break
    if _cmd_proc:
        titre, query, consigne, cta = _FR_PROCS[_cmd_proc]
        profil = session.get("profil", {}) or {}
        if not profil.get("identite"):
            msg = f"📄 Fais d'abord /start puis envoie ton CV — j'adapte ensuite {_cmd_proc} à ton profil."
        else:
            try:
                msg = await conseil_grounded(profil, titre, query, consigne, cta=cta)
            except Exception as e:
                logger.error(f"{_cmd_proc}: {e}"); msg = f"😕 Infos {_cmd_proc} indisponibles, réessaie."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/version") or low.startswith("/about"):
        prov = ", ".join([p["name"] for p in _LLM_PROVIDERS if p["key"]]) or "aucun"
        flags = []
        if _ocr_available(): flags.append("OCR")
        if _DOCX_OK: flags.append("Word")
        if _embeddings_available(): flags.append("Sémantique")
        if GEMINI_API_KEY: flags.append("Vision")
        if ADZUNA_APP_ID and ADZUNA_APP_KEY: flags.append("Adzuna")
        msg = (f"🧭 *NexMove — version {VERSION}*\n"
               f"🤖 IA : {prov}\n"
               f"🧩 Modules : {' · '.join(flags) or 'base'}\n"
               f"📚 {len(SOURCE_FEEDS)} sources de veille · 6 procédures FR parallèles (Parcoursup, MonMaster, eCandidat, DAP, Visa, Recours).\n\n"
               "Un souci ? Une idée ? → /contact")
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/contact") or low.startswith("/support") or low.startswith("/rencontrer") or low.startswith("/rdv"):
        parts = t.split(maxsplit=1)
        message_user = parts[1].strip() if len(parts) > 1 else ""
        # Bloc "comment nous joindre" — toujours affiché
        contacts = []
        if CONTACT_WHATSAPP: contacts.append(f"📱 WhatsApp : {CONTACT_WHATSAPP}")
        if CONTACT_EMAIL:    contacts.append(f"✉️ Email : {CONTACT_EMAIL}")
        if CONTACT_CALENDAR: contacts.append(f"📅 Prendre rendez-vous : {CONTACT_CALENDAR}")
        contact_bloc = "\n".join(contacts) if contacts else "_(canaux directs non configurés — utilise /contact <ton message>)_"
        if not message_user:
            msg = ("💬 *Nous contacter*\n" + contact_bloc + "\n\n"
                   "Ou écris ici : */contact ton message* — je le transmets à l'équipe.\n"
                   "Envie d'échanger avec un conseiller ? */rencontrer <disponibilités>*.")
            _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
            return msg, session
        # Forward vers l'admin Telegram si configuré
        ok = False
        if ADMIN_CHAT_ID and TELEGRAM_TOKEN:
            uid = session.get("user_id"); uname = session.get("username", "utilisateur")
            forward = (f"📨 *Nouveau contact NexMove*\n"
                       f"👤 @{_md_clean(uname)} (`{uid}`)\n"
                       f"🕒 {datetime.now(timezone.utc).strftime('%d/%m %H:%M UTC')}\n\n"
                       f"{_md_clean(message_user)[:2000]}")
            try:
                ok = await send_message(ADMIN_CHAT_ID, forward)
            except Exception as e:
                logger.error(f"[contact] forward: {e}")
        try:
            opp_store.add_contact(session.get("user_id"), session.get("username"), message_user, ok)
        except Exception as e:
            logger.warning(f"[contact] log: {e}")
        if ok:
            msg = f"✅ Merci, ton message a été transmis à l'équipe. Nous te recontactons vite.\n\n{contact_bloc}"
        else:
            msg = ("📝 Message bien noté (enregistré, l'équipe le verra). Pour être recontacté rapidement, joins-nous directement :\n\n"
                   + contact_bloc)
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/contacts_log") or low.startswith("/contacts-log") or low.startswith("/messages_log"):
        # Historique des /contact — RÉSERVÉ à l'admin
        if not ADMIN_CHAT_ID or str(session.get("chat_id") or "") != str(ADMIN_CHAT_ID):
            msg = "🔒 Commande réservée à l'administrateur."
        else:
            rows = opp_store.list_contacts(20)
            if not rows:
                msg = "📭 Aucun message /contact enregistré."
            else:
                lignes = []
                for (cid, uid, uname, txt, fwd, dt) in rows:
                    when = str(dt)[5:16].replace("T", " ")
                    flag = "📨" if fwd else "📥"
                    ex = _md_clean(str(txt))[:120]
                    lignes.append(f"{flag} #{cid} · {when} · @{_md_clean(str(uname) or 'x')} (`{uid}`)\n   {ex}")
                msg = "📇 *20 derniers messages /contact*\n\n" + "\n\n".join(lignes)
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
            msg = "Aucun profil pour l'instant. Fais /start puis envoie ton CV (PDF, Word ou image)."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/moncode"):
        code = session.get("recovery_code") or profile_store.code_for(session.get("user_id"))
        if not code and session.get("onboarding_complete"):
            try:
                code = profile_store.save(session.get("user_id"), session)
                session["recovery_code"] = code
            except Exception as e:
                logger.error(f"moncode save: {e}")
        if code:
            msg = (f"🔐 *Ton code de récupération :* `{code}`\n\n"
                   f"Depuis un autre appareil ou WhatsApp, tape */moi {code}* pour retrouver ce profil.\n"
                   "_Je garde toujours ta version la plus complète._")
        else:
            msg = "Tu n'as pas encore de profil enregistré. Envoie ton *CV (PDF, Word ou image)* pour démarrer."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/moi"):
        parts = t.split(maxsplit=1)
        code = parts[1].strip().upper() if len(parts) > 1 else ""
        if not code:
            msg = "Donne ton code après la commande : */moi NEX-XXXXX* (reçu à la fin de ton profil, ou via /moncode)."
        else:
            data = profile_store.restore(code, session.get("user_id"))
            if not data:
                msg = f"❌ Aucun profil trouvé pour le code *{_md_clean(code)}*. Vérifie-le (format NEX-XXXXX) ou refais /start."
            else:
                profil = data.get("profil") or {}
                session["profil"] = profil
                session["etape"] = "ACTIF"; session["onboarding_complete"] = True
                session["cv_parsed"] = True; session["recovery_code"] = code
                nom = (profil.get("identite") or {}).get("nom") or "—"
                msg = (f"✅ *Profil restauré* ({_md_clean(code)}) — content de te revoir, {_md_clean(nom)} !\n\n"
                       + _resume_prefs(profil.get("preferences", {}) or {})
                       + "\n\nTape /veille pour tes opportunités, ou /menu.")
                session["_show_menu"] = True
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/supprimer"):
        cleared = {"user_id": session.get("user_id"), "chat_id": session.get("chat_id"),
                   "username": session.get("username"), "etape": "WELCOME", "profil": {},
                   "historique": [], "cv_parsed": False, "cv_file_id": None,
                   "onboarding_complete": False, "pref_current": None, "derniere_activite": now}
        msg = "🗑️ Tes données ont été effacées. Fais /start pour recommencer."
        cleared["historique"] = [{"role": "assistant", "content": msg, "ts": now}]
        return msg, cleared

    if low.startswith("/mobilite") or low.startswith("/mobilité"):
        parts = t.split(maxsplit=1)
        cible = parts[1].strip() if len(parts) > 1 else ""
        try:
            seen = set(session.get("seen_urls", []))
            res = await run_osint(session.get("profil", {}) or {}, cible, session.get("user_id"), exclude_urls=seen)
            msg = res.get("message") or "Aucune opportunité trouvée pour le moment."
            opps = res.get("opportunites", [])
            for o in opps:
                u = o.get("url") or o.get("portail_officiel")
                if u:
                    seen.add(u)
            session["seen_urls"] = list(seen)[-60:]
            _attach_feedback(session, opps)
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
            msg = "📄 Je dois d'abord connaître ton profil. Fais /start puis envoie ton CV (PDF, Word ou image)."
        elif not cible_desc:
            msg = ("✍️ Indique la cible :\n/postuler <poste ou bourse>\n\n"
                   "Ex : /postuler Analyste SOC chez Orange\n"
                   "Ex : /postuler Bourse DAAD master cybersécurité")
        else:
            try:
                type_cible = "bourse" if any(k in cible_desc.lower() for k in ("bourse", "scholarship", "master", "phd", "doctorat", "fellowship", "etude", "étude")) else "emploi"
                pack = await generate_pack(profil, cible_desc, type_cible)
                competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))
                cv_buf = await asyncio.to_thread(build_cv_pdf, profil, pack.get("titre_poste") or cible_desc, pack.get("resume_professionnel", ""), competences)
                lm_buf = await asyncio.to_thread(build_letter_pdf, profil, pack.get("lettre_objet") or f"Candidature — {cible_desc}", pack.get("lettre_corps", ""))
                nom = _slug(profil.get("identite", {}).get("nom", "candidat"))
                chat_id = session.get("chat_id")
                ok_cv = await deliver_file(session,f"CV_{nom}.pdf", cv_buf.getvalue(), f"📄 CV adapté — {cible_desc[:60]}")
                ok_lm = await deliver_file(session,f"LM_{nom}.pdf", lm_buf.getvalue(), f"✉️ Lettre de motivation — {cible_desc[:60]}")
                if _DOCX_OK:
                    try:
                        cv_dx = await asyncio.to_thread(build_cv_docx, profil, pack.get("titre_poste") or cible_desc, pack.get("resume_professionnel", ""), competences)
                        lm_dx = await asyncio.to_thread(build_letter_docx, profil, pack.get("lettre_objet") or f"Candidature — {cible_desc}", pack.get("lettre_corps", ""))
                        await deliver_file(session, f"CV_{nom}.docx", cv_dx.getvalue(), "📝 Version Word (modifiable)")
                        await deliver_file(session, f"LM_{nom}.docx", lm_dx.getvalue(), "📝 Version Word (modifiable)")
                    except Exception as de:
                        logger.warning(f"[docx] postuler: {de}")
                if ok_cv and ok_lm:
                    msg = (f"✅ CV adapté + lettre de motivation générés pour : *{_md_clean(cible_desc)}*.\n"
                           "📄 PDF (à envoyer) + 📝 Word (à personnaliser).\n\n"
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
            msg = "📄 Fais d'abord /start puis envoie ton CV (PDF, Word ou image)."
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
                cv_buf = await asyncio.to_thread(build_cv_pdf, profil, cible_desc[:40], profil.get("resume_profil", ""), competences)
                lm_buf = await asyncio.to_thread(build_letter_pdf, profil, r.get("objet") or f"Projet d'études — {cible_desc}", r.get("corps", ""))
                nom = _slug(ident.get("nom", "candidat"))
                chat_id = session.get("chat_id")
                await deliver_file(session,f"CV_{nom}.pdf", cv_buf.getvalue(), "📄 CV")
                await deliver_file(session,f"Projet_{nom}.pdf", lm_buf.getvalue(), "✍️ Lettre / projet d'études")
                if _DOCX_OK:
                    try:
                        cv_dx = await asyncio.to_thread(build_cv_docx, profil, cible_desc[:40], profil.get("resume_profil", ""), competences)
                        pr_dx = await asyncio.to_thread(build_letter_docx, profil, r.get("objet") or f"Projet d'études — {cible_desc}", r.get("corps", ""))
                        await deliver_file(session, f"CV_{nom}.docx", cv_dx.getvalue(), "📝 CV Word (modifiable)")
                        await deliver_file(session, f"Projet_{nom}.docx", pr_dx.getvalue(), "📝 Projet Word (modifiable)")
                    except Exception as de:
                        logger.warning(f"[docx] dossier: {de}")
                opp_store.add_candidature(session.get("user_id"), cible_desc, r.get("deadline", ""), r.get("deadline_iso", ""))
                msg += ("📄 CV + lettre/projet d'études envoyés (PDF + 📝 Word modifiable). Dossier ajouté à ton suivi (/status).\n"
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
                res = await run_osint(session.get("profil", {}) or {}, "", session.get("user_id"))
                new = 0
                for opp in res.get("opportunites", []):
                    if opp_store.add(session.get("user_id"), opp):
                        new += 1
                msg = res.get("message") or "Aucune opportunité trouvée pour l'instant."
                msg += f"\n\n🆕 {new} nouvelle(s) opportunité(s) ajoutée(s) à ta veille."
                _attach_feedback(session, res.get("opportunites", []))
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
            # 🏅 Progression (gamification)
            st = opp_store.user_stats(session.get("user_id"))
            cf = int(session.get("cf_stage", 0) or 0)
            msg += ("🏅 *Ta progression*\n"
                    f"• Opportunités trouvées : *{st['total']}*"
                    + (f"  ( +{st['recent']} cette semaine 🔥)" if st['recent'] else "") + "\n"
                    f"• Dossiers suivis : *{len(cands)}*\n"
                    f"• Campus France : {_progress_bar(cf, len(CF_STAGES))}\n\n")
            msg += "Continue : /veille · /parcours · /campusfrance · /ecoles · /canada."
        else:
            msg = f"📊 Onboarding en cours (étape : {session.get('etape','WELCOME')}). Fais /start."
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/rappels") or low.startswith("/notifications"):
        n = _get_notif(session)
        sp = t.split(maxsplit=1)
        arg = sp[1].strip().lower() if len(sp) > 1 else ""
        if arg in ("on", "oui", "activer", "active", "1"):
            n["enabled"] = True; msg = "🔔 Notifications *activées*."
        elif arg in ("off", "non", "desactiver", "désactiver", "stop", "0"):
            n["enabled"] = False
            msg = "🔕 Notifications d'opportunités *désactivées*.\n_(Les rappels de deadline de tes dossiers restent actifs.)_"
        else:
            etat = "activées 🔔" if n["enabled"] else "désactivées 🔕"
            freq = "quotidien" if n["freq"] == "quotidien" else f"hebdo (chaque {n['jour']})"
            msg = (f"⚙️ *Tes notifications*\nÉtat : {etat}\nFréquence : {freq}\n\n"
                   "Modifier :\n• /rappels on · /rappels off\n• /digest quotidien · /digest hebdo <jour>")
        session["notif"] = n
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    if low.startswith("/digest"):
        n = _get_notif(session)
        parts = low.split()
        if len(parts) >= 2 and parts[1] in ("quotidien", "quotidienne", "jour", "daily"):
            n["freq"] = "quotidien"; msg = "🗓️ Digest *quotidien* activé."
        elif len(parts) >= 2 and parts[1] in ("hebdo", "hebdomadaire", "semaine", "weekly"):
            jour = next((p for p in parts[2:] if p in JOURS), "lundi")
            n["freq"] = "hebdo"; n["jour"] = jour
            msg = f"🗓️ Digest *hebdomadaire* activé (chaque *{jour}*)."
        else:
            msg = ("🗓️ *Fréquence du digest*\n• /digest quotidien\n• /digest hebdo <jour>\n\nEx : /digest hebdo lundi")
        n["enabled"] = True
        session["notif"] = n
        _push(session, "user", t); _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    etape = session.get("etape", "WELCOME")

    if etape == "CV_RECU" and detecter_reponse_positive(t):
        session["etape"] = "PREFERENCES"
        q = _ask_pref(session, "objectif")
        _push(session, "user", t); _push(session, "assistant", q); session["derniere_activite"] = now
        return q, session

    if etape == "PREFERENCES":
        profil = session.get("profil", {}) or {}
        prefs = profil.get("preferences", {}) or {}
        # 1) Enregistrer la réponse à la question EN COURS (si valide).
        field = session.get("pref_current")
        if field:
            ok, indice = valider_pref(field, t)
            if not ok:
                _push(session, "user", t)
                q = f"🤔 {indice}\n\n{_ask_pref(session, field)}"
                _push(session, "assistant", q); session["derniere_activite"] = now
                return q, session
            prefs[field] = t
            profil["preferences"] = prefs; session["profil"] = profil
        _push(session, "user", t)
        # 2) Prochaine question du plan ADAPTATIF (recalculé selon les réponses déjà données).
        plan = _build_pref_plan(prefs)
        nxt = next((f for f in plan if not prefs.get(f)), None)
        if nxt:
            q = _ask_pref(session, nxt)
            _push(session, "assistant", q); session["derniere_activite"] = now
            return q, session
        session["pref_current"] = None
        # Question conditionnelle : type de poste (seulement si l'objectif est de travailler)
        if _is_travail(prefs.get("objectif")) and not prefs.get("type_emploi"):
            session["etape"] = "PREF_TYPE_EMPLOI"
            q = "💼 Type de poste recherché ?\n(temps plein / temps partiel / télétravail / alternance / peu importe)"
            session["_kb_options"] = [(c, "pref:" + c) for c in ["Temps plein", "Temps partiel", "Télétravail", "Alternance", "Peu importe"]]
            _push(session, "assistant", q); session["derniere_activite"] = now
            return q, session
        session["etape"] = "CONFIRMATION"
        session["_kb_options"] = _CONFIRM_KB
        resume = _resume_prefs(prefs)
        _push(session, "assistant", resume); session["derniere_activite"] = now
        return resume, session

    if etape == "PREF_TYPE_EMPLOI":
        profil = session.get("profil", {}) or {}
        prefs = profil.get("preferences", {}) or {}
        if t.strip().lower().startswith("/") or len(t.strip()) < 2:
            _push(session, "user", t)
            q = "🤔 Réponds à la question (sans commande).\n💼 Type de poste ? (temps plein / temps partiel / télétravail / alternance / peu importe)"
            session["_kb_options"] = [(c, "pref:" + c) for c in ["Temps plein", "Temps partiel", "Télétravail", "Alternance", "Peu importe"]]
            _push(session, "assistant", q); session["derniere_activite"] = now
            return q, session
        prefs["type_emploi"] = t.strip()
        profil["preferences"] = prefs; session["profil"] = profil
        session["etape"] = "CONFIRMATION"
        session["_kb_options"] = _CONFIRM_KB
        _push(session, "user", t)
        resume = _resume_prefs(prefs)
        _push(session, "assistant", resume); session["derniere_activite"] = now
        return resume, session

    if etape == "CONFIRMATION":
        _push(session, "user", t)
        if detecter_reponse_positive(t):
            session["etape"] = "ACTIF"; session["onboarding_complete"] = True
            # Persistance du profil par identifiant : code de récupération stable (inter-canaux).
            try:
                session["recovery_code"] = profile_store.save(session.get("user_id"), session)
            except Exception as e:
                logger.error(f"profile save: {e}")
            msg = "🎉 *Profil validé !* Voici déjà des pistes pour toi :\n"
            # Première veille AUTOMATIQUE : de la valeur immédiate (levier de rétention).
            try:
                res = await run_osint(session.get("profil", {}) or {}, "", session.get("user_id"))
                top = res.get("opportunites", [])[:3]
                for o in res.get("opportunites", []):
                    opp_store.add(session.get("user_id"), o)
                if top:
                    for i, o in enumerate(top, 1):
                        msg += f"\n{i}. {_type_label(o.get('type',''))} *{_md_clean(o.get('titre',''))[:55]}*"
                        lien = str(o.get("url", "") or o.get("portail_officiel", "")).replace("*", "").replace("`", "")
                        if lien:
                            msg += f"\n   🔗 {lien}"
                    _attach_feedback(session, top)
                else:
                    msg += "\nJe scrute déjà le web — tape /veille dans un instant."
            except Exception as e:
                logger.error(f"auto-veille: {e}")
                msg += "\nTape /veille pour tes premières opportunités."
            # Intention forte captée AVANT la fin de l'onboarding : on la relance maintenant.
            # La commande reste stockée côté serveur (session["pending_intent"]) ; le bouton
            # ne porte qu'un jeton court (contrainte Telegram : callback_data <= 64 octets).
            pending = session.get("pending_intent", "")
            if pending:
                label = pending.split()[0].lstrip("/").capitalize()
                msg += f"\n\n📌 Tu m'avais demandé quelque chose au début — clique ci-dessous pour que je m'en occupe (ou tape *{pending.split()[0]}*)."
                session["_kb_options"] = [("▶️ " + label, "act:pending")]
            code = session.get("recovery_code")
            if code:
                msg += (f"\n\n🔐 *Ton code de récupération :* `{code}`\n"
                        "_Garde-le : tape /moi <code> depuis WhatsApp ou un autre appareil pour retrouver ton profil._")
            msg += ("\n\n▶️ *La suite :* /veille (plus d'offres) · /campusfrance (études en France) · "
                    "/ecoles · /canada · /menu.\n_Je t'enverrai chaque jour les meilleures offres liées à ton profil._")
            session["_show_menu"] = True   # menu affiché UNE fois, à la fin de l'onboarding
        else:
            session["etape"] = "PREFERENCES"
            # On repart de zéro : vider les réponses pour re-parcourir le plan adaptatif.
            profil = session.get("profil", {}) or {}
            profil["preferences"] = {}; session["profil"] = profil
            msg = "Pas de souci, on reprend.\n\n" + _ask_pref(session, "objectif")
        _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    # Pas encore onboardé : réponse déterministe (pas de LLM bavard qui re-salue / vouvoie / redemande le CV)
    if not session.get("onboarding_complete"):
        _push(session, "user", t)
        # Intention forte exprimée AVANT la fin de l'onboarding : on ne la perd pas, on la
        # mémorise pour la déclencher automatiquement une fois le profil prêt.
        intent_cmd = _free_text_to_command(low, t)
        if intent_cmd and len(t) > 3:
            session["pending_intent"] = intent_cmd
            msg = ("📌 Noté — *je m'en occupe dès que ton profil est prêt*.\n\n"
                   "Envoie-moi d'abord ton *CV (PDF, Word ou image)* pour que je personnalise mes réponses. "
                   "Besoin d'un guide ? Tape /tuto.")
        else:
            msg = ("📄 Pour démarrer, envoie-moi ton *CV (PDF, Word ou image)* — j'analyse ton profil et je te fais un bilan "
                   "d'orientation. Besoin d'un guide ? Tape /tuto.")
        _push(session, "assistant", msg); session["derniere_activite"] = now
        return msg, session

    # Utilisateur actif — langage 100 % naturel : d'abord les mots-clés (instantané), sinon le LLM
    # décide en UN appel s'il faut lancer une ACTION ou répondre en conversation.
    cmd = _free_text_to_command(low, t)
    if cmd:
        return await process_text_message(session, cmd)

    profil_str = json.dumps(session.get("profil", {}), ensure_ascii=False)[:800]
    system = f"""Tu es NexMove. {CONSEILLER_PERSONA}
PROFIL: {profil_str}
L'utilisateur écrit librement. Deux cas :
1) Il veut une ACTION → renvoie la commande + son argument (champ "action" + "argument").
2) C'est une conversation (salutation, question ouverte, remerciement) → réponds toi-même (champ "message"), sans action.
COMMANDES: veille (offres adaptées) · mobilite <domaine/pays> (offres/bourses/emplois ciblés, LOCAUX ou à l'étranger) · formations <domaine> · ecoles <domaine> · logement <ville> · entretien <type> · campusfrance · canada · procedure <pays> · budget <ville> · eligibilite <cible> · dossier <cible> · postuler <cible> · compresser · traduire <texte> · status · profil · parcours · aide.
REGLES du "message": français, TUTOIE (jamais « vous » ni « Bonjour »), ne redemande jamais le CV, max 100 mots.
JSON: {{"action":"<commande ou vide>","argument":"<texte ou vide>","message":"<réponse si pas d'action>"}}"""
    try:
        r = await call_groq(system, t, temperature=0.3, max_tokens=380)
    except Exception as e:
        logger.error(f"Erreur LLM: {e}")
        r = {}
    action = str(r.get("action", "") or "").strip().lower().lstrip("/")
    if action in _VALID_INTENTS:
        arg = str(r.get("argument", "") or "").strip()
        return await process_text_message(session, "/" + action + ((" " + arg) if arg else ""))
    message = (r.get("message") or "Je suis là pour t'aider — dis-moi ce que tu cherches (offres, école, logement, entretien, dossier…).").strip()
    _push(session, "user", t); _push(session, "assistant", message)
    session["derniere_activite"] = now
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

def _ocr_pdf(pdf_bytes: bytes) -> str:
    """OCR de secours pour PDF scannés/images : rend chaque page en image puis tesseract."""
    if not _ocr_available():
        return ""
    parts = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        mat = fitz.Matrix(OCR_ZOOM, OCR_ZOOM)
        for i, page in enumerate(doc):
            if i >= OCR_MAX_PAGES:
                break
            try:
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                txt = pytesseract.image_to_string(img, lang=OCR_LANG)
                if txt and txt.strip():
                    parts.append(txt.strip())
            except Exception as pe:
                logger.warning(f"[ocr] page {i} échouée: {pe}")
        doc.close()
    except Exception as e:
        logger.warning(f"[ocr] échec global: {e}")
        return ""
    out = "\n".join(parts).strip()
    if out:
        logger.info(f"[ocr] {len(out)} caractères extraits (lang={OCR_LANG})")
    return out

def extract_text_pdf(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(p.get_text("text") for p in doc if p.get_text("text").strip())
        doc.close()
        text = text.strip()
    except Exception as e:
        raise HTTPException(422, f"Lecture PDF impossible: {e}")
    # PDF scanné / image : le texte embarqué est vide ou trop court -> bascule OCR
    if len(text) < 50:
        ocr_text = _ocr_pdf(pdf_bytes)
        if len(ocr_text) > len(text):
            return ocr_text
    return text

def extract_text_docx(data: bytes) -> str:
    """Extraction texte d'un .docx (python-docx)."""
    if not _DocxDocument:
        raise HTTPException(422, "Lecture DOCX indisponible sur ce serveur.")
    try:
        d = _DocxDocument(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs if p.text and p.text.strip()]
        for tbl in d.tables:
            for row in tbl.rows:
                for cell in row.cells:
                    if cell.text and cell.text.strip():
                        parts.append(cell.text)
        return "\n".join(parts).strip()
    except Exception as e:
        raise HTTPException(422, f"Lecture DOCX impossible: {e}")

def extract_text_image(img_bytes: bytes) -> str:
    """OCR d'une image (JPG/PNG/HEIC…) via tesseract."""
    if not _ocr_available():
        return ""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        txt = pytesseract.image_to_string(img, lang=OCR_LANG)
        return (txt or "").strip()
    except Exception as e:
        logger.warning(f"[img-ocr] {e}")
        return ""

# (analyze_cv_image_vision : voir llm.py — PR-B)

def pdf_to_b64(buf: io.BytesIO) -> str:
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def _parse_pages(spec: str, n: int) -> list:
    """« 1-3,5,8 » (1-indexé) -> indices 0-indexés valides et ordonnés."""
    out = []
    for part in str(spec or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                a = int(a); b = int(b)
            except Exception:
                continue
            for p in range(min(a, b), max(a, b) + 1):
                if 1 <= p <= n:
                    out.append(p - 1)
        else:
            try:
                p = int(part)
                if 1 <= p <= n:
                    out.append(p - 1)
            except Exception:
                continue
    seen = set(); res = []
    for i in out:
        if i not in seen:
            seen.add(i); res.append(i)
    return res

def merge_pdfs(paths: list) -> bytes:
    out = fitz.open()
    for p in paths:
        try:
            src = fitz.open(p); out.insert_pdf(src); src.close()
        except Exception as e:
            logger.warning(f"[merge] {p}: {e}")
    data = out.tobytes(garbage=4, deflate=True); out.close()
    return data

def images_to_pdf(paths: list) -> bytes:
    out = fitz.open()
    for p in paths:
        try:
            im = fitz.open(p)
            pdfbytes = im.convert_to_pdf(); im.close()
            src = fitz.open("pdf", pdfbytes); out.insert_pdf(src); src.close()
        except Exception as e:
            logger.warning(f"[img2pdf] {p}: {e}")
    data = out.tobytes(garbage=4, deflate=True); out.close()
    return data

def split_pdf(pdf_bytes: bytes, spec: str) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    idx = _parse_pages(spec, doc.page_count)
    out = fitz.open()
    for i in idx:
        out.insert_pdf(doc, from_page=i, to_page=i)
    data = out.tobytes(garbage=4, deflate=True); out.close(); doc.close()
    return data

# --- Tampon de fichiers sur disque (fusion PDF / images->PDF), volume ./data persistant ---
_TOOL_DIR = "data/tmp"

def _tool_dir(uid) -> str:
    return os.path.join(_TOOL_DIR, hashlib.sha1(str(uid).encode()).hexdigest()[:16])

def _tool_add_file(uid, data: bytes, ext: str) -> int:
    d = _tool_dir(uid); os.makedirs(d, exist_ok=True)
    n = len(os.listdir(d))
    if n >= 15:
        return -1
    with open(os.path.join(d, f"{n:02d}.{ext}"), "wb") as f:
        f.write(data)
    return n + 1

def _tool_files(uid) -> list:
    d = _tool_dir(uid)
    return [os.path.join(d, f) for f in sorted(os.listdir(d))] if os.path.isdir(d) else []

def _tool_clear(uid):
    shutil.rmtree(_tool_dir(uid), ignore_errors=True)

def compress_pdf(pdf_bytes: bytes, target_kb: int = 2000) -> tuple:
    """Compresse un PDF sous ~target_kb. 1) reconstruction lossless (nettoyage/deflate).
    2) si toujours trop lourd et Pillow dispo, rendu des pages en JPEG à DPI décroissant.
    Renvoie (bytes, taille_ko_finale)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        best = doc.tobytes(garbage=4, deflate=True, clean=True, deflate_images=True, deflate_fonts=True)
    except Exception:
        best = pdf_bytes
    target = max(50, target_kb) * 1024
    if len(best) <= target or Image is None:
        doc.close()
        return best, len(best) // 1024
    for dpi, q in ((150, 75), (120, 70), (96, 65), (72, 55)):
        try:
            nd = fitz.open()
            for page in doc:
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                b = io.BytesIO(); img.save(b, format="JPEG", quality=q, optimize=True)
                npage = nd.new_page(width=page.rect.width, height=page.rect.height)
                npage.insert_image(page.rect, stream=b.getvalue())
            cand = nd.tobytes(garbage=4, deflate=True)
            nd.close()
            if len(cand) < len(best):
                best = cand
            if len(best) <= target:
                break
        except Exception as e:
            logger.warning(f"[compress] dpi={dpi}: {e}")
            break
    doc.close()
    return best, len(best) // 1024

BLEU = HexColor("#1a237e")
GRIS = HexColor("#546e7a")

def build_cv_pdf(profil: dict, titre: str, resume: str, competences: list) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8*cm, rightMargin=1.8*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    s_nom = ParagraphStyle("n", fontSize=19, leading=23, textColor=BLEU, fontName="Helvetica-Bold", spaceBefore=0, spaceAfter=5)
    s_sous = ParagraphStyle("s", fontSize=11, leading=14, textColor=GRIS, fontName="Helvetica-Oblique", spaceAfter=6)
    s_sec = ParagraphStyle("se", fontSize=11, textColor=BLEU, fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)
    s_body = ParagraphStyle("b", fontSize=9.5, fontName="Helvetica", spaceAfter=3, leading=13)
    s_bullet = ParagraphStyle("bu", fontSize=9.5, fontName="Helvetica", spaceAfter=2, leftIndent=12)
    identite = profil.get("identite", {})
    formation = profil.get("formation", [])
    experience = profil.get("experience", [])
    els = []
    els.append(Paragraph(_xml(identite.get("nom", "Candidat")), s_nom))
    if titre:
        els.append(Paragraph(_xml(titre), s_sous))
    contacts = [x for x in [identite.get("email"), identite.get("telephone"), identite.get("localisation")] if x]
    if contacts:
        els.append(Paragraph(_xml(" · ".join(contacts)), s_body))
    els.append(HRFlowable(width="100%", thickness=1.5, color=BLEU, spaceBefore=6, spaceAfter=10))
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

# ---------- Export Word (.docx) : versions modifiables du CV et de la lettre ----------
_BLEU_RGB = (0x1a, 0x23, 0x7e)
_GRIS_RGB = (0x54, 0x6e, 0x7a)

def build_cv_docx(profil: dict, titre: str, resume: str, competences: list) -> io.BytesIO:
    d = _DocxDocument()
    ident = profil.get("identite", {})
    p = d.add_paragraph(); r = p.add_run(ident.get("nom", "Candidat") or "Candidat")
    r.bold = True; r.font.size = _DocxPt(19); r.font.color.rgb = _DocxRGB(*_BLEU_RGB)
    if titre:
        p = d.add_paragraph(); r = p.add_run(titre); r.italic = True
        r.font.size = _DocxPt(11); r.font.color.rgb = _DocxRGB(*_GRIS_RGB)
    contacts = [x for x in [ident.get("email"), ident.get("telephone"), ident.get("localisation")] if x]
    if contacts:
        d.add_paragraph(" · ".join(contacts))
    def section(t):
        p = d.add_paragraph(); r = p.add_run(t.upper())
        r.bold = True; r.font.size = _DocxPt(11); r.font.color.rgb = _DocxRGB(*_BLEU_RGB)
    if resume:
        section("Profil"); d.add_paragraph(resume)
    if competences:
        section("Compétences"); d.add_paragraph(" · ".join(competences[:16]))
    exp = profil.get("experience", [])
    if exp:
        section("Expérience")
        for e in exp[:5]:
            p = d.add_paragraph(); r = p.add_run(f"{e.get('poste','')} — {e.get('organisation','')}"); r.bold = True
            for m in (e.get("missions", []) or [])[:4]:
                d.add_paragraph(str(m), style="List Bullet")
    form = profil.get("formation", [])
    if form:
        section("Formation")
        for f in form[:4]:
            p = d.add_paragraph(); r = p.add_run(f"{f.get('diplome','')} — {f.get('etablissement','')}"); r.bold = True
    buf = io.BytesIO(); d.save(buf); return buf

def build_letter_docx(profil: dict, objet: str, corps: str) -> io.BytesIO:
    d = _DocxDocument()
    ident = profil.get("identite", {})
    p = d.add_paragraph(); r = p.add_run(ident.get("nom", "Candidat") or "Candidat"); r.bold = True
    for c in [ident.get("email"), ident.get("telephone"), ident.get("localisation")]:
        if c:
            d.add_paragraph(str(c))
    d.add_paragraph("")
    d.add_paragraph(datetime.now(timezone.utc).strftime("%d/%m/%Y"))
    p = d.add_paragraph(); r = p.add_run(f"Objet : {objet}"); r.bold = True
    for para in (corps or "").split("\n\n"):
        para = para.strip()
        if para:
            d.add_paragraph(para.replace("\n", " "))
    d.add_paragraph("")
    d.add_paragraph("Cordialement,")
    p = d.add_paragraph(); r = p.add_run(ident.get("nom", "") or ""); r.bold = True
    buf = io.BytesIO(); d.save(buf); return buf

# ── Canaux (Telegram/WhatsApp/Messenger) extraits dans channels.py (PR-C) ──
from channels import (
    TELEGRAM_TOKEN, WHATSAPP_TOKEN, WHATSAPP_PHONE_ID, MESSENGER_TOKEN,
    _mime_for, send_message, edit_message, answer_callback, _send_telegram_document,
    _tg_keyboard, wa_text, wa_menu, wa_document, wa_get_media,
    fb_text, fb_menu, fb_document,
)  # noqa: F401

def get_menu(session, key):
    if key == "find":
        return ("🔎 *Trouver des opportunités*", [
            ("🔔 Ma veille", "act:veille"),
            ("🌍 Recherche ciblée", "act:mobilite_help"),
            ("⬅️ Retour", "m:root")])
    if key == "cf":
        opts = [
            ("🇫🇷 Campus France", "act:campusfrance"),
            ("🗺️ Mon parcours", "act:parcours"),
            ("🎓 Parcoursup", "act:parcoursup"),
            ("📘 MonMaster", "act:monmaster"),
            ("🧾 eCandidat", "act:ecandidat"),
            ("📜 DAP (L1 hors UE)", "act:dap"),
            ("🛂 Visa (Capago/VFS)", "act:visa"),
            ("⚖️ Recours refus", "act:recours"),
            ("🏫 Trouver une école", "act:ecoles"),
            ("🏠 Logement", "act:logement"),
            ("🎤 Prépa entretien", "act:entretien"),
            ("🇨🇦 Canada", "act:canada"),
            ("🌍 Autres pays", "act:procedure"),
            ("💶 Budget", "act:budget"),
        ]
        try:
            for (cible, dl, st) in (opp_store.list_candidatures(session.get("user_id")) or [])[:2]:
                opts.append((("🗂️ " + str(cible))[:20], "act:status"))
        except Exception:
            pass
        opts.append(("⬅️ Retour", "m:root"))
        return ("🗂️ *Procédures & accompagnement*", opts)
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
            ("🗜️ Compresser un PDF", "act:compresser"),
            ("💬 Nous contacter", "act:contact"),
            ("ℹ️ Version", "act:version"),
            ("🗑️ Effacer données", "act:supprimer"),
            ("⬅️ Retour", "m:root")])
    return ("🧭 *NexMove* — que veux-tu faire ?", [
        ("🔎 Trouver", "m:find"), ("🇫🇷 Procédures", "m:cf"),
        ("📄 Candidater", "m:apply"), ("🎓 Formations", "act:formations"),
        ("📊 Mon espace", "m:space"), ("❓ Aide", "act:aide")])

# (WhatsApp/Messenger + _tg_keyboard -> channels.py, PR-C)

# ---------- Couche canal (dispatch) ----------
async def deliver_menu(session, title, options):
    ch = session.get("channel", "telegram"); to = session.get("chat_id")
    if ch == "whatsapp":
        return await wa_menu(to, title, options)
    if ch == "messenger":
        return await fb_menu(to, title, options)
    return await send_message(to, title, _tg_keyboard(options))

async def deliver_text(session, text, with_menu=False, options=None):
    # `options` = boutons attachés à CE message (confirmation, choix d'onboarding…), prioritaires sur le menu.
    ch = session.get("channel", "telegram"); to = session.get("chat_id")
    if ch == "whatsapp":
        if options:
            return await wa_menu(to, text, options)
        await wa_text(to, text)
        if with_menu:
            await wa_menu(to, "👉 Que veux-tu faire ?", get_menu(session, "root")[1])
        return True
    if ch == "messenger":
        if options:
            return await fb_menu(to, text, options)
        if with_menu:
            return await fb_menu(to, text, get_menu(session, "root")[1])
        return await fb_text(to, text)
    kb = _tg_keyboard(options) if options else (_tg_keyboard(get_menu(session, "root")[1]) if with_menu else None)
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
            "formations": "/formations", "supprimer": "/supprimer",
            "ecoles": "/ecoles", "logement": "/logement", "entretien": "/entretien", "canada": "/canada",
            "compresser": "/compresser", "procedure": "/procedure", "budget": "/budget",
            "parcoursup": "/parcoursup", "monmaster": "/monmaster", "ecandidat": "/ecandidat",
            "dap": "/dap", "visa": "/visa", "recours": "/recours",
            "contact": "/contact", "version": "/version", "rencontrer": "/rencontrer"}
_ACT_HELP = {
    "mobilite_help": "🌍 Écris : /mobilite <pays ou domaine>\nEx : /mobilite Canada cybersécurité",
    "dossier_help": "🗂️ Écris : /dossier <bourse ou programme>\nEx : /dossier Bourse Eiffel master cybersécurité",
    "postuler_help": "✉️ Écris : /postuler <poste ou bourse>\nEx : /postuler Analyste SOC chez Orange",
}

async def handle_action(session, data, callback_id=None):
    if data.startswith("fb:"):
        # feedback offre : fb:u:<i> (👍) / fb:d:<i> (👎)
        try:
            _, v, idx = data.split(":", 2)
            i = int(idx)
        except Exception:
            v, i = "", -1
        offers = session.get("last_offers", []) or []
        if 0 <= i < len(offers):
            vote = 1 if v == "u" else -1
            opp_store.add_feedback(session.get("user_id"), offers[i].get("sig", ""), vote)
            if callback_id:
                await answer_callback(callback_id, "👍 Noté, merci !" if vote > 0 else "👎 Compris, j'en tiendrai compte.")
        elif callback_id:
            await answer_callback(callback_id)
        return session
    if callback_id:
        await answer_callback(callback_id)
    # Confirmation / choix d'onboarding cliquables : on rejoue la réponse comme si elle était tapée
    if data.startswith(("onb:", "pref:")):
        val = data.split(":", 1)[1]
        txt = "/start" if val == "reset" else val
        msg, session = await process_text_message(session, txt)
        opts = session.pop("_kb_options", None)
        show = session.pop("_show_menu", False)
        fb = session.pop("_feedback_kb", None)
        await deliver_text(session, msg, with_menu=show, options=opts)
        if fb:
            await deliver_menu(session, "📊 Ces offres te correspondent ? 👍 utile · 👎 hors sujet", fb)
        return session
    if data.startswith("m:"):
        title, opts = get_menu(session, data[2:])
        await deliver_menu(session, title, opts)
        return session
    if data.startswith("act:"):
        act = data[4:]
        if act == "pending":
            # Rejoue l'intention forte captée pendant l'onboarding (commande stockée côté serveur).
            cmd = session.pop("pending_intent", "") or "/veille"
            msg, session = await process_text_message(session, cmd)
            await deliver_text(session, msg, with_menu=True)
            return session
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

async def _process_guide_screenshot(session, img_bytes, filename="capture.jpg"):
    """Mode /guide : analyse une capture d'écran (vision Gemini) et renvoie un guidage concret."""
    if not img_bytes or len(img_bytes) > 20 * 1024 * 1024:
        await deliver_text(session, "❌ Capture illisible ou trop lourde (max 20 Mo). Reprends une capture nette.")
        return
    fn = (filename or "capture").lower()
    is_image = fn.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")) or (img_bytes[:3] in (b"\xff\xd8\xff", b"\x89PN"))
    if not is_image:
        await deliver_text(session, "📸 Envoie une *capture d'écran* (image JPG/PNG) de l'écran où tu es bloqué·e. "
                                    "_Tape /annuler pour quitter le mode guidage._")
        return
    # Quota gratuit (option coûteuse : vision) — admin illimité.
    ok, _ = _quota_check(session, "guide", FREE_GUIDE_DAILY)
    if not ok:
        await deliver_text(session, _quota_exceeded_msg("le guidage par capture d'écran"))
        return
    mime = "image/png" if fn.endswith(".png") else ("image/webp" if fn.endswith(".webp") else "image/jpeg")
    try:
        guidance = await analyze_screenshot_vision(img_bytes, mime, session.get("guide_context", ""))
    except Exception as e:
        logger.error(f"[guide] {e}"); guidance = ""
    if not guidance:
        await deliver_text(session, "😕 Je n'arrive pas à lire cette capture (ou le service vision est momentanément "
                                    "indisponible). Reprends une capture *nette*, ou réessaie dans un instant.")
        return
    _quota_bump(session, "guide")
    session["derniere_activite"] = datetime.now(timezone.utc).isoformat()
    _push(session, "assistant", guidance)
    logger.info(f"[guide] {session.get('channel')} capture analysée")
    await deliver_text(session, "🧭 " + guidance + "\n\n_Envoie la capture suivante, ou tape /annuler pour quitter._")


async def process_cv(session, pdf_bytes, filename="cv.pdf"):
    uid = session.get("user_id")
    # Mode /guide : la capture d'écran est analysée par la vision (pas comme un CV).
    if session.get("guide_mode"):
        await _process_guide_screenshot(session, pdf_bytes, filename)
        return
    # Boîte à outils PDF : fusion / images->PDF (tampon) ou découpe (immédiat)
    mode = session.get("tool_mode")
    if mode in ("merge", "img2pdf"):
        ext = "pdf" if (filename or "").lower().endswith(".pdf") else ((filename or "img").rsplit(".", 1)[-1].lower() or "jpg")
        n = await asyncio.to_thread(_tool_add_file, uid, pdf_bytes, ext)
        if n < 0:
            await deliver_text(session, "⚠️ Limite atteinte (15 fichiers). Tape /terminer pour générer, ou /annuler.")
        else:
            quoi = "PDF" if mode == "merge" else "image"
            await deliver_text(session, f"📎 {quoi} n°{n} ajouté. Envoie le suivant, ou tape /terminer pour générer le PDF.")
        return
    if mode == "split":
        spec = session.pop("split_spec", "")
        session["tool_mode"] = None
        session_manager.set(uid, session)
        try:
            data = await asyncio.to_thread(split_pdf, pdf_bytes, spec)
            ok = data and len(data) > 100
        except Exception as e:
            logger.error(f"[split] {e}"); ok = False
        if ok:
            await deliver_file(session, f"{_slug((filename or 'document').rsplit('.',1)[0])}_pages_{spec.replace(',', '_')}.pdf", data, f"✂️ Pages {spec}")
        else:
            await deliver_text(session, "😕 Découpe impossible (vérifie les numéros de pages).")
        return
    # Mode compression : l'utilisateur a demandé /compresser puis envoie un PDF
    target_kb = session.pop("compress_target", 0)
    if target_kb:
        session_manager.set(session.get("user_id"), session)   # on retire le flag
        if not pdf_bytes or len(pdf_bytes) > 25 * 1024 * 1024:
            await deliver_text(session, "❌ PDF illisible ou trop lourd (max 25 Mo).")
            return
        orig_kb = len(pdf_bytes) // 1024
        try:
            data, kb = await asyncio.to_thread(compress_pdf, pdf_bytes, target_kb)
        except Exception as e:
            logger.error(f"[compress] {e}")
            await deliver_text(session, "😕 Compression impossible sur ce fichier.")
            return
        base = _slug((filename or "document").rsplit(".", 1)[0])
        await deliver_file(session, f"{base}_compresse.pdf", data, f"🗜️ {orig_kb} Ko → {kb} Ko")
        note = "" if kb <= target_kb else f"\n⚠️ Je n'ai pas pu descendre sous {target_kb} Ko sans trop dégrader la qualité. Relance avec une cible plus haute si besoin."
        await deliver_text(session, f"✅ PDF allégé : *{orig_kb} Ko → {kb} Ko*.{note}")
        logger.info(f"[compress] {session.get('channel')} {orig_kb}->{kb} Ko (cible {target_kb})")
        return
    if not pdf_bytes or len(pdf_bytes) > 20 * 1024 * 1024:
        await deliver_text(session, "❌ Fichier illisible ou trop lourd (max 20 Mo).")
        return
    # Quota gratuit : l'analyse de CV (LLM/vision) est coûteuse ; l'admin est illimité.
    ok, _ = _quota_check(session, "cv", FREE_CV_DAILY)
    if not ok:
        await deliver_text(session, _quota_exceeded_msg("l'analyse de CV"))
        return
    fn = (filename or "cv").lower()
    is_pdf = fn.endswith(".pdf") or pdf_bytes[:4] == b"%PDF"
    is_docx = fn.endswith((".docx", ".dotx"))
    is_image = fn.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")) or pdf_bytes[:3] in (b"\xff\xd8\xff", b"\x89PN")
    profil_from_vision = None
    cv_text = ""
    try:
        if is_pdf:
            cv_text = await asyncio.to_thread(extract_text_pdf, pdf_bytes)
        elif is_docx:
            cv_text = await asyncio.to_thread(extract_text_docx, pdf_bytes)
        elif is_image:
            # 1) Vision Gemini (le mieux sur photos) — renvoie DIRECTEMENT le JSON profil
            mime = "image/png" if fn.endswith(".png") else ("image/webp" if fn.endswith(".webp") else "image/jpeg")
            profil_from_vision = await analyze_cv_image_vision(pdf_bytes, mime)
            if not profil_from_vision:
                # 2) Repli OCR
                cv_text = await asyncio.to_thread(extract_text_image, pdf_bytes)
        else:
            await deliver_text(session, "❌ Format non supporté. Envoie ton CV en *PDF*, *DOCX* ou *image* (JPG/PNG).")
            return
    except HTTPException as he:
        await deliver_text(session, f"❌ {he.detail}")
        return
    except Exception as e:
        logger.error(f"[cv] extraction {fn}: {e}")
        cv_text = ""
    if profil_from_vision is None and (not cv_text or len(cv_text.strip()) < 50):
        if is_image and not _ocr_available():
            await deliver_text(session, "❌ Image reçue mais l'OCR n'est pas disponible.\n\nEnvoie plutôt ton CV (PDF, Word ou image) ou DOCX.")
        elif is_image:
            await deliver_text(session, "❌ Je n'arrive pas à lire cette image. Prends une photo *plus nette* (bonne lumière, cadrée sur le CV), ou envoie un PDF/DOCX.")
        elif is_docx:
            await deliver_text(session, "❌ Le DOCX semble vide.\n\nRenvoie-le, ou exporte en PDF depuis Word.")
        elif not _ocr_available():
            await deliver_text(session, "❌ Ce PDF semble scanné (image) et l'OCR n'est pas disponible.\n\nEnvoie un PDF avec texte sélectionnable (Word/LibreOffice).")
        else:
            await deliver_text(session, "❌ Impossible de lire ce PDF, même après OCR.\n\nVérifie que le document est lisible (bonne qualité) ou envoie un PDF avec texte sélectionnable.")
        return
    system = ("Tu es expert en analyse de CV ET " + CONSEILLER_PERSONA + " D'abord détermine si le document EST "
              "un CV/résumé professionnel (identité + parcours/formation/expérience/compétences). Si ce n'est PAS "
              "un CV (facture, article, cours, lettre, relevé, capture, texte quelconque), mets \"est_cv\": false "
              "et laisse les autres champs vides. Sinon, remplis aussi un \"bilan\" d'orientation bref et "
              "personnalisé (forces réelles, axes à renforcer, 2-3 pistes réalistes de destinations/programmes "
              "adaptées au profil). Réponds en JSON uniquement.")
    prompt = f"""Analyse ce document:
{{"est_cv":true,"raison_rejet":"","identite":{{"nom":"","email":"","telephone":"","localisation":"","linkedin":"","github":"","langues":[]}},"formation":[{{"diplome":"","domaine":"","etablissement":"","ville":"","pays":"","annee":""}}],"competences":{{"techniques":[],"securite":[],"outils":[],"frameworks":[],"soft_skills":[]}},"experience":[{{"poste":"","organisation":"","type":"","duree":"","date_debut":"","date_fin":"","localisation":"","missions":[]}}],"projets":[{{"nom":"","description":"","technologies":[],"url":""}}],"certifications":[],"preferences":{{"types_opportunite":["emploi","bourse","fellowship"],"niveau":"professionnel","langues_opportunite":["fr","en"],"delai_min_jours":14,"mots_cles":[],"geographie":[]}},"bilan":{{"forces":["..."],"axes":["..."],"pistes":["..."]}},"niveau_global":"junior|mid|senior","resume_profil":""}}
Document: {cv_text[:6000]}"""
    if profil_from_vision:
        profil = profil_from_vision   # analyse vision directe (image) : pas de deuxième appel LLM
    else:
        try:
            profil = await call_groq(system, prompt, temperature=0.1, max_tokens=2500)
        except Exception as e:
            logger.error(f"[cv] analyse LLM échouée: {e}")
            await deliver_text(session, "⏳ Le service d'analyse est momentanément indisponible. Renvoie ton CV dans une minute — je m'en occupe dès que possible.")
            return
    if not isinstance(profil, dict) or not profil:
        await deliver_text(session, "😕 Je n'ai pas réussi à lire ce CV. Renvoie-le (PDF avec texte sélectionnable) ou réessaie dans un instant.")
        return
    # Rejet des documents qui ne sont pas des CV (retour testeurs)
    ident = profil.get("identite", {}) or {}
    a_du_contenu = bool(profil.get("formation") or profil.get("experience") or
                        any((profil.get("competences", {}) or {}).values()))
    if profil.get("est_cv") is False or not (ident.get("nom") or a_du_contenu):
        raison = profil.get("raison_rejet") or "il ne ressemble pas à un CV"
        await deliver_text(session, f"❌ Ce document n'a pas été accepté : {raison}.\n\nEnvoie ton *CV* (formation, expériences, compétences) en PDF pour démarrer.")
        logger.info(f"[cv] {session.get('channel')} document rejeté (non-CV)")
        return
    # Diplôme principal en premier (le plus élevé/récent) — sinon le bot retenait la licence au lieu du master
    profil["formation"] = _sort_formations(profil.get("formation"))
    nom = (profil.get("identite", {}).get("nom") or "").strip()
    if not nom or nom.upper() in ("N/A", "NA", "-", "—"):
        # Repli : deviner le nom depuis le nom de fichier du CV (ex. « CV_Judicael.pdf »).
        devine = _name_from_filename(filename)
        nom = devine or "—"
        if devine:
            profil.setdefault("identite", {})["nom"] = devine   # persister pour lettres/dossiers
    forms = profil.get("formation", []) or []
    if forms:
        lignes_f = []
        for f in forms[:3]:
            dip = (f.get("diplome", "") or "").strip()
            etab = (f.get("etablissement", "") or "").strip()
            an = (f.get("annee", "") or "").strip()
            ligne = dip + (f" — {etab}" if etab else "") + (f" ({an})" if an else "")
            if ligne.strip():
                lignes_f.append("   • " + _md_clean(ligne))
        formation_txt = "\n".join(lignes_f) if lignes_f else "   • _non précisé_"
        if len(forms) > 3:
            formation_txt += f"\n   • _(+{len(forms) - 3} autre·s)_"
    else:
        formation_txt = "   • _Aucune formation détectée dans ton CV — dis-le-moi si c'est une erreur._"
    skills = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))[:5]
    message = f"✅ *CV analysé avec succès !*\n\n👤 *Nom :* {nom}\n🎓 *Formations détectées :*\n{formation_txt}\n💻 *Compétences :* {', '.join(skills)}\n"
    bilan = profil.get("bilan", {}) or {}
    if bilan.get("forces"):
        message += "\n💪 *Tes atouts :* " + _md_clean(", ".join(bilan["forces"][:3])) + "\n"
    if bilan.get("axes"):
        message += "📈 *À renforcer :* " + _md_clean(", ".join(bilan["axes"][:3])) + "\n"
    if bilan.get("pistes"):
        message += "🎯 *Pistes réalistes pour toi :*\n" + "\n".join(f"• {_md_clean(p)}" for p in bilan["pistes"][:3]) + "\n"
    message += "\nCes informations sont-elles correctes ? Confirme ci-dessous 👇 (ou réponds *Oui*)."
    session["etape"] = "CV_RECU"
    session["profil"] = profil
    session["cv_parsed"] = True
    _quota_bump(session, "cv")   # analyse réussie -> décompte le quota (admin exclu)
    session["derniere_activite"] = datetime.now(timezone.utc).isoformat()
    _push(session, "assistant", message)
    session_manager.set(session.get("user_id"), session)
    logger.info(f"[cv] {session.get('channel')} {nom} -> CV_RECU")
    await deliver_text(session, message, options=[("✅ C'est correct", "onb:oui"), ("🔄 Recommencer", "onb:reset")])

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
        elif t == "image":
            # Photo directe (WhatsApp) — traitée comme un CV en image via vision Gemini
            im = raw.get("image", {})
            ext = ".png" if "png" in (im.get("mime_type") or "") else ".jpg"
            doc = {"id": im.get("id"), "filename": f"cv{ext}"}
        elif t == "button":
            callback = raw.get("button", {}).get("payload")
        elif t in ("audio", "voice", "video", "sticker"):
            text = "__wa_unsupported__"   # message poli renvoyé plus bas
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
            r = await http().get(url, timeout=30.0, follow_redirects=True)
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
        if text == "__wa_unsupported__":
            await deliver_text(session, "🎙️ Je ne traite pas encore les messages audio/vidéo/sticker. Écris-moi en *texte* ou envoie ton CV en *PDF/Word/image*.")
            return
        if not check_rate_limit(user_id):
            await deliver_text(session, "⚠️ Trop de messages. Attends une minute.")
            return
        msg, session = await process_text_message(session, text)
        show_menu = session.pop("_show_menu", False)
        kb_options = session.pop("_kb_options", None)
        fb_kb = session.pop("_feedback_kb", None)
        session_manager.set(user_id, session)
        await deliver_text(session, msg, with_menu=show_menu, options=kb_options)
        if fb_kb:
            await deliver_menu(session, "📊 Ces offres te correspondent ? 👍 utile · 👎 hors sujet", fb_kb)

def _profil_txt_court(profil: dict) -> str:
    prefs = (profil.get("preferences", {}) or {})
    dom = prefs.get("mots_cles") or (profil.get("resume_profil", "")[:60])
    dip = (profil.get("formation") or [{}])[0].get("diplome", "")
    return (f"diplôme={dip}, domaine={dom}, objectif={prefs.get('objectif','')}, "
            f"pays visés={prefs.get('pays_cibles','')}, niveau={prefs.get('niveau','')}, "
            f"financement={prefs.get('financement','')}, type poste={prefs.get('type_emploi','')}")

async def conseil_grounded(profil: dict, titre_aff: str, tavily_query: str, consigne: str, cta: str = "") -> str:
    """Conseil personnalisé façon conseiller senior, ancré sur le web (Tavily) — réutilisé par
    /ecoles, /logement, /entretien, /canada. Liens réels uniquement, jamais d'échéance passée."""
    grounded = await tavily_search(tavily_query, 6)
    sources = "\n".join(f"- {s.get('title','')} | {s.get('url','')} | {(s.get('content','') or '')[:180]}"
                        for s in grounded[:6]) if grounded else "(pas de résultat web — n'utilise que des organismes/plateformes RÉELS et connus, sans inventer d'URL)"
    system = (CONSEILLER_PERSONA + " " + consigne +
              " Ne cite QUE des organismes, plateformes ou écoles RÉELS (jamais d'URL inventée). JSON uniquement.")
    prompt = f"""PROFIL: {_profil_txt_court(profil)}
SOURCES WEB:
{sources}
DATE DU JOUR: {datetime.now(timezone.utc).date().isoformat()} — n'indique jamais une échéance déjà passée.
JSON: {{"intro":"","points":[{{"titre":"","detail":"","lien":""}}],"checklist":["..."],"conseil":""}}"""
    r = await call_groq(system, prompt, temperature=0.2, max_tokens=1400)
    msg = f"{titre_aff}\n━━━━━━━━━━━━━━━━━━\n"
    if r.get("intro"):
        msg += _md_clean(r["intro"]) + "\n\n"
    for p in (r.get("points") or [])[:6]:
        ti = _md_clean(p.get("titre", ""))
        if not ti:
            continue
        msg += f"• *{ti}*"
        if p.get("detail"):
            msg += f" — {_md_clean(p['detail'])}"
        lien = str(p.get("lien", "") or "").replace("*", "").replace("`", "").strip()
        if lien:
            msg += f"\n  🔗 {lien}"
        msg += "\n"
    if r.get("checklist"):
        msg += "\n📋 *À préparer :*\n" + "\n".join(f"⬜ {_md_clean(c)}" for c in r["checklist"][:6]) + "\n"
    if r.get("conseil"):
        msg += f"\n💡 {_md_clean(r['conseil'])}\n"
    if cta:
        msg += "\n" + cta
    return msg

async def generate_pack(profil: dict, cible_desc: str, type_cible: str = "emploi") -> dict:
    ident = profil.get("identite", {})
    competences = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))[:12]
    resume = profil.get("resume_profil", "")
    # Ancrer la lettre dans le vécu réel du candidat (expériences + formations) pour éviter le texte générique.
    exp_lignes = []
    for e in (profil.get("experience", []) or [])[:4]:
        poste = e.get("poste", ""); org = e.get("organisation", "")
        missions = "; ".join((e.get("missions", []) or [])[:2])
        exp_lignes.append(f"- {poste} @ {org} : {missions}".strip())
    form_lignes = []
    for f in (profil.get("formation", []) or [])[:3]:
        form_lignes.append(f"- {f.get('diplome','')} ({f.get('domaine','')}), {f.get('etablissement','')}".strip())
    experiences_txt = "\n".join(exp_lignes) or "(aucune expérience renseignée)"
    formations_txt = "\n".join(form_lignes) or "(aucune formation renseignée)"
    if type_cible == "bourse":
        consigne = ("Rédige un CV adapté ET une lettre de motivation académique (statement of purpose) pour cette bourse/programme. "
                    "La lettre met en avant le projet d'études, la motivation, l'adéquation au programme et l'impact visé au retour.")
    else:
        consigne = ("Rédige un CV adapté ET une lettre de motivation professionnelle ciblée pour ce poste. "
                    "Structure : accroche, adéquation profil/poste, valeur ajoutée, conclusion.")
    system = ("Tu es expert en recrutement et candidatures internationales. Français impeccable et NATUREL, comme "
              "écrit par la personne elle-même. INTERDIT : les tournures d'IA et clichés (« je suis convaincu que », "
              "« correspond parfaitement à mes aspirations », « dynamique et motivé », « c'est avec un grand "
              "intérêt », « fort de mon expérience »). Appuie CHAQUE argument sur un fait CONCRET du profil "
              "(expérience, mission, diplôme, compétence réels ci-dessous) — jamais de généralités. JSON uniquement.")
    prompt = f"""{consigne}
CANDIDAT: {ident.get('nom','')}
RÉSUMÉ: {resume}
FORMATIONS:
{formations_txt}
EXPÉRIENCES:
{experiences_txt}
COMPÉTENCES: {competences}
CIBLE: {cible_desc}

Contraintes lettre (lettre_corps) : 220-300 mots, 3-4 paragraphes séparés par une ligne vide, sans en-tête ni
signature. Cite au moins deux éléments concrets tirés des EXPÉRIENCES/FORMATIONS ci-dessus. Ton sobre et
professionnel, phrases variées, pas de superlatifs creux.
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
        session = await handle_action(session, request.callback_data, request.callback_id)
        session_manager.set(uid, session)
        return {"ok": True}
    if not check_rate_limit(uid):
        await deliver_text(session, "⚠️ Trop de messages. Attends 1 minute.")
        return {"ok": True}
    logger.info(f"[chat] tg user={uid} text={request.text[:50]!r}")
    message, session = await process_text_message(session, request.text)
    show_menu = session.pop("_show_menu", False)
    kb_options = session.pop("_kb_options", None)
    fb_kb = session.pop("_feedback_kb", None)
    session_manager.set(uid, session)
    await deliver_text(session, message, with_menu=show_menu, options=kb_options)
    if fb_kb:
        await deliver_menu(session, "📊 Ces offres te correspondent ? 👍 utile · 👎 hors sujet", fb_kb)
    return {"ok": True}

@app.post("/api/chat-cv")
async def chat_cv(file: UploadFile = File(...), user_id: str = Form("unknown"), chat_id: str = Form("0"), username: str = Form("utilisateur"), _auth: bool = Depends(verify_api_key)):
    session = session_manager.get(user_id) or session_manager.create_default(user_id, chat_id, username)
    session["channel"] = "telegram"
    session["chat_id"] = chat_id
    session["username"] = username
    fn = (file.filename or "").lower()
    ct = (file.content_type or "").lower()
    is_pdf = ct == "application/pdf" or fn.endswith(".pdf")
    is_img = ct.startswith("image/") or fn.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic"))
    is_docx = "word" in ct or fn.endswith((".docx", ".dotx"))
    if session.get("tool_mode") == "img2pdf":
        if not (is_img or is_pdf):
            await deliver_text(session, "🖼️ Envoie une *image* (en fichier/document), ou /annuler.")
            return {"ok": True}
    elif not (is_pdf or is_img or is_docx):
        await deliver_text(session, "❌ Format non supporté. Envoie ton CV en *PDF*, *DOCX* ou *image* (JPG/PNG).")
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
    cv_text = await asyncio.to_thread(extract_text_pdf, pdf_bytes)
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
    cv_buf = await asyncio.to_thread(build_cv_pdf, profil, pack.get("titre_poste") or titre, pack.get("resume_professionnel", ""), competences)
    lm_buf = await asyncio.to_thread(build_letter_pdf, profil, pack.get("lettre_objet") or f"Candidature — {cible_desc}", pack.get("lettre_corps", ""))
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
        r = await http().post("https://api.tavily.com/search", json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": False,
        }, timeout=25.0)
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
# ── Catalogue de sources STRUCTURÉ (scope: local/intl/both, type: bourse/emploi/fellowship/ong) ──
# `active_env` (optionnel) : la source n'est active que si la variable d'env correspondante est vraie.
SOURCE_CATALOG = [
    {"url": "https://www.scholars4dev.com/feed/",              "type": "bourse",     "scope": "intl"},
    {"url": "https://opportunitydesk.org/feed/",               "type": "bourse",     "scope": "both"},
    {"url": "https://www.opportunitiesforafricans.com/feed/",  "type": "bourse",     "scope": "both"},
    {"url": "https://afterschoolafrica.com/feed/",             "type": "bourse",     "scope": "both"},
    {"url": "https://www.opportunitiesforyouth.org/feed/",     "type": "fellowship", "scope": "both"},
    {"url": "https://youthop.com/feed/",                       "type": "fellowship", "scope": "both"},
    {"url": "https://mladiinfo.eu/feed/",                      "type": "bourse",     "scope": "intl"},
    # Humanitaire / ONG (emplois & consultances) — activable via ENABLE_RELIEFWEB=1
    {"url": "https://reliefweb.int/jobs/rss.xml",              "type": "ong",        "scope": "both",
     "active_env": "ENABLE_RELIEFWEB"},
]


def _source_active(s: dict) -> bool:
    env = s.get("active_env")
    return True if not env else str(os.getenv(env, "")).strip().lower() in ("1", "true", "yes", "on", "oui")


# Flux RSS supplémentaires ajoutables sans toucher au code (URLs séparées par des virgules ; scope 'both').
for _u in (u.strip() for u in os.getenv("SOURCE_FEEDS_EXTRA", "").split(",") if u.strip()):
    SOURCE_CATALOG.append({"url": _u, "type": "bourse", "scope": "both"})

_SOURCE_META = {s["url"]: s for s in SOURCE_CATALOG}
# Liste plate des feeds ACTIFS (rétro-compat : ingest_feeds itère dessus).
SOURCE_FEEDS = [s["url"] for s in SOURCE_CATALOG if _source_active(s)]


def _sources_for_profile(prefs: dict) -> list[str]:
    """Sélection ADAPTATIVE des sources selon le profil : un objectif purement LOCAL
    n'inonde pas l'utilisateur de sources uniquement internationales, et inversement."""
    local_only = _is_travail(prefs.get("objectif")) and not _vise_international(prefs)
    out = []
    for s in SOURCE_CATALOG:
        if not _source_active(s):
            continue
        if local_only and s["scope"] == "intl":
            continue          # visée locale : on écarte les sources 100 % internationales
        out.append(s["url"])
    return out
# EURAXESS : flux RSS explicite (facultatif) d'une recherche filtrée.
EURAXESS_RSS = os.getenv("EURAXESS_RSS", "")
# EURAXESS API : endpoint de recherche ({q} = requête). Vide -> on tente des endpoints candidats.
# Pour le fixer précisément : ouvrir euraxess.ec.europa.eu/jobs/search, F12 > Network > taper un mot,
# copier l'URL de la requête qui renvoie du JSON et remplacer le mot par {q}.
EURAXESS_API = os.getenv("EURAXESS_API", "")
# EURAXESS rend ses résultats en HTML (recherche à facettes Drupal) : on lit la page et on
# extrait les liens d'offres. Le mot-clé va dans la facette keywords.
_EURAXESS_CANDIDATES = [
    "https://euraxess.ec.europa.eu/jobs/search?f[0]=keywords:{q}",
    "https://euraxess.ec.europa.eu/jobs/search?keywords={q}",
]
_euraxess_working = None  # mémorise le template qui a répondu (évite de re-sonder)

# Certains sites (EURAXESS, afterschoolafrica, youthop…) renvoient une page de blocage aux bots :
# on se présente avec un User-Agent de navigateur.
_BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"

def _rss_regex(text: str) -> list:
    """Extraction RSS tolérante (feeds WordPress mal formés : & nus, CDATA). Renvoie [] si pas d'items."""
    def _tag(block, tag):
        m = re.search(rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", block, re.S | re.I)
        return m.group(1) if m else ""
    out = []
    for block in re.findall(r"<item[ >].*?</item>", text, re.S | re.I):
        titre = _htmlmod.unescape(re.sub(r"<[^>]+>", " ", _tag(block, "title"))).strip()
        link = _htmlmod.unescape(_tag(block, "link")).strip()
        desc = _htmlmod.unescape(re.sub(r"<[^>]+>", " ", _tag(block, "description"))).strip()[:300]
        if titre and link:
            out.append({"titre": titre, "url": link, "resume": desc, "date": ""})
    return out

async def fetch_rss(url: str) -> list:
    try:
        r = await http().get(url, headers={"User-Agent": _BROWSER_UA}, timeout=15.0, follow_redirects=True)
        if r.status_code != 200:
            return []
        items = []
        try:
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                titre = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                desc = re.sub("<[^>]+>", " ", (it.findtext("description") or ""))
                desc = re.sub(r"\s+", " ", desc).strip()[:300]
                pub = (it.findtext("pubDate") or "").strip()
                if titre and link:
                    items.append({"titre": titre, "url": link, "resume": desc, "date": pub})
        except Exception:
            items = _rss_regex(r.text)   # feed mal formé -> parseur tolérant
        return items[:30]
    except Exception as e:
        logger.warning(f"RSS {url}: {e}")
        return []

async def ingest_feeds() -> int:
    total = 0
    for url in SOURCE_FEEDS:
        meta = _SOURCE_META.get(url, {})
        for it in await fetch_rss(url):
            it.setdefault("type", meta.get("type", "bourse"))   # type/scope hérités de la source
            it.setdefault("scope", meta.get("scope", "both"))
            if opp_store.add_source(it):
                total += 1
    return total

# ---------- Sources d'emplois structurées (APIs open data) ----------
async def fetch_arbeitnow() -> list:
    """Job board ouvert (EU/tech, sans clé API). https://www.arbeitnow.com/api/job-board-api"""
    try:
        r = await http().get("https://www.arbeitnow.com/api/job-board-api",
                             headers={"User-Agent": _BROWSER_UA}, timeout=15.0, follow_redirects=True)
        if r.status_code != 200:
            return []
        out = []
        for j in (r.json().get("data") or [])[:40]:
            titre = (j.get("title") or "").strip()
            url = (j.get("url") or "").strip()
            comp = (j.get("company_name") or "").strip()
            desc = re.sub("<[^>]+>", " ", j.get("description") or "")
            desc = re.sub(r"\s+", " ", desc).strip()[:300]
            tags = ", ".join((j.get("tags") or [])[:5])
            if titre and url:
                out.append({"titre": f"{titre} — {comp}" if comp else titre, "url": url,
                            "resume": (desc or tags)[:300], "type": "emploi", "date": ""})
        return out
    except Exception as e:
        logger.error(f"arbeitnow: {e}")
        return []

async def fetch_adzuna(query: str, country: str = "fr") -> list:
    """API emploi Adzuna (clés gratuites). Ne fait rien si non configurée."""
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        return []
    try:
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        r = await http().get(url, params={"app_id": ADZUNA_APP_ID, "app_key": ADZUNA_APP_KEY,
                                          "results_per_page": 20, "what": query, "content-type": "application/json"},
                             timeout=15.0, follow_redirects=True)
        if r.status_code != 200:
            logger.warning(f"adzuna {r.status_code}: {r.text[:120]}")
            return []
        out = []
        for j in (r.json().get("results") or [])[:20]:
            titre = (j.get("title") or "").strip()
            link = (j.get("redirect_url") or "").strip()
            comp = ((j.get("company") or {}).get("display_name") or "").strip()
            desc = re.sub(r"\s+", " ", j.get("description") or "").strip()[:300]
            if titre and link:
                out.append({"titre": f"{titre} — {comp}" if comp else titre, "url": link,
                            "resume": desc, "type": "emploi", "date": (j.get("created") or "")[:10]})
        return out
    except Exception as e:
        logger.error(f"adzuna: {e}")
        return []

def _euraxess_pick(item: dict):
    """Extrait titre/url/description d'un item EURAXESS quel que soit le nom des champs."""
    def first(keys):
        for k in keys:
            v = item.get(k)
            if isinstance(v, dict):
                v = v.get("value") or v.get("uri") or v.get("href")
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    titre = first(["title", "name", "jobTitle", "label", "offerTitle"])
    url = first(["url", "link", "jobUrl", "detailUrl", "path", "alias", "self", "href"])
    desc = first(["description", "summary", "teaser", "body", "abstract", "content"])
    return titre, url, desc

def _euraxess_items(payload):
    """Retrouve la liste d'items dans une réponse JSON EURAXESS (formes variées)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("results", "hits", "data", "jobs", "items", "content", "offers", "rows"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
        emb = payload.get("_embedded")
        if isinstance(emb, dict):
            for v in emb.values():
                if isinstance(v, list):
                    return v
    return []

async def fetch_euraxess(query: str) -> list:
    """Recherche EURAXESS (chercheurs/PhD/postdoc). Endpoint configurable ou auto-sondé, parse JSON ou XML."""
    global _euraxess_working
    if EURAXESS_API:
        templates = [EURAXESS_API]
    elif _euraxess_working:
        templates = [_euraxess_working]
    else:
        templates = _EURAXESS_CANDIDATES
    for tmpl in [t for t in templates if t]:
        url = tmpl.replace("{q}", quote(query)).replace("{query}", quote(query))
        try:
            r = await http().get(url, headers={"User-Agent": _BROWSER_UA,
                                               "Accept": "text/html,application/xhtml+xml,application/json"},
                                 timeout=15.0, follow_redirects=True)
            if r.status_code != 200:
                continue
            out = []
            body = r.text.lstrip()
            ct = r.headers.get("content-type", "").lower()
            if "json" in ct or body[:1] in "{[":
                for it in _euraxess_items(r.json())[:25]:
                    if not isinstance(it, dict):
                        continue
                    titre, u, desc = _euraxess_pick(it)
                    if titre and u:
                        if u.startswith("/"):
                            u = "https://euraxess.ec.europa.eu" + u
                        out.append({"titre": titre, "url": u,
                                    "resume": re.sub(r"<[^>]+>", " ", desc)[:300], "type": "fellowship", "date": ""})
            elif body[:5].lower().startswith("<?xml") or "<rss" in body[:200].lower():
                for it in ET.fromstring(r.content).iter("item"):
                    titre = (it.findtext("title") or "").strip()
                    link = (it.findtext("link") or "").strip()
                    if titre and link:
                        out.append({"titre": titre, "url": link,
                                    "resume": re.sub(r"<[^>]+>", " ", (it.findtext("description") or ""))[:300],
                                    "type": "fellowship", "date": ""})
            else:
                # HTML : offres = liens /jobs/<id numérique>. Une carte a souvent 2 liens (image + titre) :
                # on garde, par offre, l'intitulé le plus long (le vrai titre).
                best = {}
                for m in re.finditer(r'<a\s+[^>]*href="(/jobs/\d+)"[^>]*>(.*?)</a>', r.text, re.S | re.I):
                    href = m.group(1)
                    titre = _htmlmod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip())
                    if len(titre) >= 6 and (href not in best or len(titre) > len(best[href])):
                        best[href] = titre
                for href, titre in list(best.items())[:25]:
                    out.append({"titre": titre[:150], "url": "https://euraxess.ec.europa.eu" + href,
                                "resume": "", "type": "fellowship", "date": ""})
            if out:
                _euraxess_working = tmpl
                return out
        except Exception as e:
            logger.warning(f"[euraxess] {tmpl[:60]}: {e}")
    return []

async def ingest_euraxess() -> int:
    """EURAXESS via API (requêtes adaptées aux mots-clés des utilisateurs) + flux RSS explicite éventuel."""
    total = 0
    queries = _collect_user_queries(6)
    if queries:
        # 1ère requête = découverte de l'endpoint ; si rien ne répond, on n'insiste pas.
        first = await fetch_euraxess(queries[0])
        if first:
            for it in first:
                if opp_store.add_source(it):
                    total += 1
            for q in queries[1:]:
                for it in await fetch_euraxess(q):
                    if opp_store.add_source(it):
                        total += 1
    if EURAXESS_RSS:
        for it in await fetch_rss(EURAXESS_RSS):
            it["type"] = "fellowship"
            if opp_store.add_source(it):
                total += 1
    return total

def _collect_user_queries(limit: int = 8) -> list:
    """Construit les requêtes Adzuna à partir des VRAIS mots-clés des utilisateurs actifs
    (les plus fréquents d'abord) ; repli sur ADZUNA_QUERIES si aucun."""
    from collections import Counter
    c = Counter()
    for s in session_manager.list_active():
        prefs = (s.get("profil", {}) or {}).get("preferences", {}) or {}
        for champ in ("mots_cles", "objectif"):
            for m in re.split(r"[,/;]| et ", str(prefs.get(champ, ""))):
                m = m.strip().lower()
                if len(m) > 2 and m not in ("tous", "aucun", "aucune", "travailler", "etudier", "étudier"):
                    c[m] += 1
        for comp in (s.get("profil", {}) or {}).get("competences", {}).get("techniques", [])[:3]:
            comp = str(comp).strip().lower()
            if len(comp) > 2:
                c[comp] += 1
    qs = [w for w, _ in c.most_common(limit)]
    return qs or ADZUNA_QUERIES

async def ingest_structured() -> int:
    """Ingère les offres d'emploi structurées (arbeitnow + Adzuna si configuré + EURAXESS) dans le pool."""
    total = 0
    for it in await fetch_arbeitnow():
        if opp_store.add_source(it):
            total += 1
    if ADZUNA_APP_ID and ADZUNA_APP_KEY:
        queries = _collect_user_queries()          # requêtes adaptées aux mots-clés réels
        for country in (ADZUNA_COUNTRIES or ["fr"]):
            for q in queries:
                for it in await fetch_adzuna(q, country):
                    if opp_store.add_source(it):
                        total += 1
    total += await ingest_euraxess()
    return total

def _domain(url):
    d = re.sub(r"^https?://(www\.)?", "", str(url or "")).split("/")[0]
    return d[:40]

# Nationalité -> pays (pour proposer aussi des opportunités LOCALES, pas seulement à l'étranger)
_NAT_PAYS = {
    "béninoise": "Bénin", "beninoise": "Bénin", "ivoirienne": "Côte d'Ivoire", "sénégalaise": "Sénégal",
    "senegalaise": "Sénégal", "togolaise": "Togo", "burkinabé": "Burkina Faso", "burkinabe": "Burkina Faso",
    "malienne": "Mali", "nigérienne": "Niger", "nigerienne": "Niger", "nigériane": "Nigéria",
    "camerounaise": "Cameroun", "guinéenne": "Guinée", "guineenne": "Guinée", "gabonaise": "Gabon",
    "congolaise": "Congo", "tchadienne": "Tchad", "centrafricaine": "Centrafrique", "marocaine": "Maroc",
    "tunisienne": "Tunisie", "algérienne": "Algérie", "algerienne": "Algérie",
}

def _pays_from_nat(nat: str) -> str:
    n = str(nat or "").strip().lower()
    if n in _NAT_PAYS:
        return _NAT_PAYS[n]
    for k, v in _NAT_PAYS.items():
        if k in n or v.lower() in n:
            return v
    return ""

_STOP_SIG = {"pour", "avec", "dans", "les", "des", "une", "chez", "sur", "the", "and",
             "for", "master", "bourse", "offre", "emploi", "stage", "junior", "senior"}

def _offer_signal(opp, domaine="") -> str:
    """Signature apprenante d'une offre : type + 1er mot-clé significatif (pour agréger le feedback)."""
    typ = str(opp.get("type", "") or "opp").lower().strip()[:12]
    base = f"{opp.get('titre','')} {domaine}".lower()
    toks = [w for w in re.findall(r"[a-zàâçéèêëîïôûùüÿñ]{4,}", base) if w not in _STOP_SIG]
    return f"{typ}|{toks[0] if toks else 'general'}"

def _attach_feedback(session, opps):
    """Prépare les boutons 👍/👎 pour les offres affichées et mémorise leur signature."""
    lo, kb = [], []
    for i, o in enumerate((opps or [])[:5]):
        lo.append({"sig": _offer_signal(o), "titre": (o.get("titre") or "")[:40]})
        kb.append((f"👍 {i+1}", f"fb:u:{i}"))
        kb.append((f"👎 {i+1}", f"fb:d:{i}"))
    if lo:
        session["last_offers"] = lo
        session["_feedback_kb"] = kb

async def run_osint(profil: dict, cible: str = "", user_id: str = "", exclude_urls=None) -> dict:
    profil = profil or {}
    exclude_urls = exclude_urls or set()
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
    mots_list = [m.strip() for m in re.split(r"[,/;]| et ", mots) if m.strip()] if mots and mots.lower() not in ("tous", "aucun", "aucune", "-", "") else []
    if mots_list:
        domaine = mots
    else:
        last_poste = (profil.get("experience") or [{}])[0].get("poste", "")
        domaine = last_poste or (resume[:60]) or (formations[0] if formations else "") or "opportunités"
    type_emploi = prefs.get("type_emploi") or ""
    cible = (cible or "").strip() or f"{domaine} {pays_cibles}".strip() or "opportunités"
    cible_lower = cible.lower()
    pays_detecte = next((p for p in VISA_DB if p != "default" and (p in cible_lower or p in pays_cibles.lower())), None)
    visa_info = VISA_DB.get(pays_detecte, VISA_DB["default"])
    # Champ élargi : proposer aussi des opportunités LOCALES (pas seulement à l'étranger)
    local_pays = _pays_from_nat(nationalite)
    _pc_low = (pays_cibles or "").lower()
    _pc_vide = (not pays_cibles) or _pc_low in ("tous", "local", "sur place", "mon pays", "")
    veut_local = _pc_vide or "afrique" in _pc_low or (local_pays and local_pays.lower() in (_pc_low + " " + cible_lower))
    today = datetime.now(timezone.utc).date().isoformat()
    profil_txt = (f"résumé: {resume[:200]} | formations: {', '.join(formations) or '—'} | "
                  f"expériences: {', '.join(experiences) or '—'} | compétences: {competences} | "
                  f"objectif: {objectif} | financement: {financement} | nationalité: {nationalite}")

    grounded = []
    if TAVILY_API_KEY:
        type_mot = {"étudier": "bourse", "etudier": "bourse", "bourse": "bourse",
                    "fellowship": "fellowship", "travailler": "emploi"}.get(objectif, "bourse OR emploi OR formation")
        if pays_detecte:
            zone = pays_detecte
        elif not _pc_vide:
            zone = pays_cibles
        else:
            zone = local_pays if veut_local else ""
        domaine_q = " OR ".join(mots_list) if len(mots_list) > 1 else domaine
        query = f"{type_mot} {domaine_q} {type_emploi} {zone} 2026 candidature".strip()
        grounded = await tavily_search(query, 10)

    if grounded:
        # Tri sémantique : les sources dont le SENS est le plus proche du profil passent en tête
        sims = await semantic_scores(profil_txt, grounded, lambda s: f"{s.get('title','')} {(s.get('content','') or '')[:300]}")
        if sims:
            for s, sim in zip(grounded, sims):
                s["_sim"] = sim
            grounded = sorted(grounded, key=lambda s: s.get("_sim", 0.0), reverse=True)
        grounded = grounded[:8]
        sources_txt = "\n".join(f"[{i}] {s.get('title','')} — {(s.get('content','') or '')[:200]}"
                                for i, s in enumerate(grounded))
        system = ("Tu es expert en orientation, emploi et mobilité (LOCALE ou internationale). On te fournit des "
                  "RÉSULTATS WEB numérotés. Choisis UNIQUEMENT ceux vraiment PERTINENTS pour le PARCOURS RÉEL du "
                  "candidat (respecte une éventuelle reconversion : cible son domaine ACTUEL/visé, pas ses anciens "
                  "diplômes). Réponds avec l'INDEX du résultat (jamais d'URL inventée). Ignore le hors-sujet. JSON uniquement.")
        diversite = (f"MOTS-CLÉS À COUVRIR (varie les résultats entre ces thèmes, pas tous sur le même) : {', '.join(mots_list)}.\n"
                     if len(mots_list) > 1 else "")
        type_emploi_txt = f"TYPE DE POSTE souhaité : {type_emploi}.\n" if type_emploi else ""
        local_txt = (f"IMPORTANT : inclus AUSSI des opportunités LOCALES au {local_pays} (emplois, formations comme "
                     f"l'ASIN, bourses locales), pas seulement à l'étranger.\n" if veut_local and local_pays else "")
        prompt = f"""PROFIL CANDIDAT: {profil_txt}
DOMAINE VISÉ: {domaine} · PAYS: {pays_detecte or pays_cibles or (local_pays + ' (local) + international' if local_pays else 'indifférent')}
{diversite}{type_emploi_txt}{local_txt}DATE DU JOUR: {today}. Exclus les deadlines passées.
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
                o["_sim"] = src.get("_sim")
                clean.append(o)
        # Mélange du score LLM avec la similarité sémantique + feedback appris de l'utilisateur
        for o in clean:
            sim = o.get("_sim")
            if isinstance(sim, (int, float)):
                base = o.get("score_composite") or 0
                o["score_composite"] = int(round(0.6 * base + 0.4 * sim * 100))
            if user_id:
                d = opp_store.feedback_delta(user_id, _offer_signal(o, domaine))
                if d:
                    o["score_composite"] = max(0, min(100, (o.get("score_composite") or 0) + d))
        clean.sort(key=lambda o: o.get("score_composite", 0), reverse=True)
        result["opportunites"] = clean
        footer = "🌐 _Sources web réelles — vérifie l'éligibilité et la deadline sur chaque lien._"
    else:
        system = ("Tu es expert en orientation, emploi et mobilité (LOCALE ou internationale) pour ressortissants "
                  "africains. Respecte le PARCOURS RÉEL (reconversion incluse) : cible le domaine actuel/visé. "
                  "Ne cite QUE des organismes RÉELS — locaux (agences, universités, entreprises, programmes du pays) "
                  "ET internationaux (DAAD, Campus France, Erasmus Mundus, Chevening, AUF, Mastercard Foundation…). "
                  "N'invente jamais d'URL (portail officiel en clair). JSON uniquement.")
        local_txt = (f"Inclus AUSSI des opportunités LOCALES au {local_pays} (emplois, formations locales, bourses "
                     f"nationales), pas seulement à l'étranger.\n" if veut_local and local_pays else "")
        prompt = f"""PROFIL CANDIDAT: {profil_txt}
DOMAINE VISÉ: {domaine} · PAYS: {pays_detecte or pays_cibles or (local_pays + ' + international' if local_pays else 'Non précisé')}
{local_txt}DATE DU JOUR: {today}. Uniquement des opportunités ouvertes ou à venir.
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
    if exclude_urls:   # anti-doublons entre deux /mobilite d'affilée
        opps = [o for o in opps if str(o.get("url", "") or o.get("portail_officiel", "")) not in exclude_urls]
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
    res = await run_osint(profil, request.cible, request.user_id)
    return {**res, "chat_id": request.chat_id}

@app.post("/api/collect")
async def collect(_auth: bool = Depends(verify_api_key)):
    ingested = await ingest_feeds() + await ingest_structured()
    users = session_manager.list_active()
    sem = asyncio.Semaphore(3)
    async def _one(s):
        async with sem:
            n = 0
            profil = s.get("profil", {}) or {}
            prefs = profil.get("preferences", {}) or {}
            if COLLECT_OSINT_PER_USER:
                try:
                    res = await run_osint(profil, "", s.get("user_id"))
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
                # Filtrage adaptatif : privilégie le périmètre visé (local si job local, sinon intl).
                prefer = None if _vise_international(prefs) else ("local" if _is_travail(prefs.get("objectif")) else None)
                srcs = opp_store.search_sources(kws, prefer_scope=prefer)
                comps = (profil.get("competences", {}).get("techniques", []) + profil.get("competences", {}).get("securite", []))[:8]
                profil_txt = (f"{profil.get('resume_profil','')} | objectif: {prefs.get('objectif','')} | "
                              f"domaine: {prefs.get('mots_cles','')} | pays: {prefs.get('pays_cibles','')} | compétences: {comps}")
                sims = await semantic_scores(profil_txt, srcs, lambda x: f"{x.get('titre','')} {(x.get('resume') or '')[:300]}") if srcs else None
                for i, src in enumerate(srcs):
                    if sims:
                        sim = sims[i]
                        if sim < 0.5:   # trop éloigné du profil → on n'inonde pas l'utilisateur
                            continue
                        score = int(round(45 + sim * 55))
                    else:
                        score = 62
                    styp = src.get("type", "bourse")
                    orga = "Offre d'emploi" if styp == "emploi" else "Source vérifiée"
                    opp = {"titre": src["titre"], "organisation": orga, "type": styp,
                           "url": src["url"], "raison": (src.get("resume") or "")[:150], "score_composite": score}
                    delta = opp_store.feedback_delta(s.get("user_id"), _offer_signal(opp))
                    if delta <= -20:      # l'utilisateur a rejeté ce type d'offres à répétition
                        continue
                    opp["score_composite"] = max(0, min(100, score + delta))
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
    weekday_today = datetime.now(timezone.utc).weekday()
    for s in users[:50]:
        chat_id = s.get("chat_id")
        n = _get_notif(s)
        if not n["enabled"]:
            continue
        if n["freq"] == "hebdo" and weekday_today != JOURS.get(n["jour"], 0):
            continue  # digest hebdomadaire : seulement le jour choisi
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
        st = opp_store.user_stats(s.get("user_id"))
        entete = f"🔔 *Tes meilleures offres du jour* ({len(rows)} sélectionnées pour ton profil)\n"
        if st["recent"]:
            entete += f"📈 {st['recent']} nouvelles cette semaine · {st['total']} au total dans ta veille\n"
        msg = (entete + "━━━━━━━━━━━━━━━━━━\n\n"
               + "\n\n".join(lignes)
               + "\n\n_/postuler <titre> pour ton CV + lettre · 👍/👎 pour affiner._")
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
    return {"status": "ok", "version": VERSION, "service": "nexmove-api", "llm_providers": [p["name"] for p in _LLM_PROVIDERS if p["key"]], "tavily_configured": bool(TAVILY_API_KEY), "telegram_configured": bool(TELEGRAM_TOKEN), "whatsapp_configured": bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_ID), "messenger_configured": bool(MESSENGER_TOKEN), "ocr_configured": _ocr_available(), "docx_configured": _DOCX_OK, "semantic_matching": _embeddings_available(), "adzuna_configured": bool(ADZUNA_APP_ID and ADZUNA_APP_KEY), "adzuna_countries": ADZUNA_COUNTRIES, "euraxess_configured": bool(EURAXESS_RSS or EURAXESS_API), "rss_feeds": len(SOURCE_FEEDS), "sessions_stored": session_manager.count(), "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/")
async def root():
    return {"service": f"NexMove API v{VERSION}", "endpoints": ["POST /api/chat", "POST /api/chat-cv", "POST /api/parse-cv", "POST /api/generate-documents", "POST /api/osint", "POST /api/collect", "POST /api/score", "POST /api/notify", "GET /api/session/{user_id}", "GET /health"]}
