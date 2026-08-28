"""IA — routeur multi-fournisseurs (Cerebras → Groq → Gemini) + embeddings + vision.
Extrait de main.py (PR-B du refactor). Comportement STRICTEMENT identique :
- même liste de fournisseurs / modèles configurables via env
- même bascule sur quota/erreur, même parsing JSON tolérant
- mêmes embeddings (essai multi-modèles, cache 7j via db.cache)
- même analyse vision Gemini pour les CV en image
"""
from __future__ import annotations
import os, json, hashlib, base64, asyncio, math, logging
from typing import Any, Optional

from fastapi import HTTPException

from http_client import http
from db import cache

logger = logging.getLogger("forge-nex")

# ── Clés & modèles (configurables par env — voir .env.example) ──
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
GROQ_URL           = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_API_KEY   = os.getenv("CEREBRAS_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")

GROQ_MODEL          = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_MODEL_FAST     = os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")
CEREBRAS_MODEL      = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
CEREBRAS_MODEL_FAST = os.getenv("CEREBRAS_MODEL_FAST", "gemma-4-31b")
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_MODEL_FAST   = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash-lite")

# Pillow (utilisé par la vision) — import tolérant
try:
    from PIL import Image as _PILImage
except Exception:
    _PILImage = None


# ── Fournisseurs LLM : Cerebras → Groq → Gemini (bascule auto) ──
_LLM_PROVIDERS = [
    {"name": "cerebras", "url": "https://api.cerebras.ai/v1/chat/completions",
     "key": CEREBRAS_API_KEY, "model": CEREBRAS_MODEL, "model_fast": CEREBRAS_MODEL_FAST,
     "api": "openai", "max_ctx": 8192},
    {"name": "groq", "url": GROQ_URL, "key": GROQ_API_KEY,
     "model": GROQ_MODEL, "model_fast": GROQ_MODEL_FAST,
     "api": "openai", "max_ctx": 32000},
    {"name": "gemini", "url": f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
     "key": GEMINI_API_KEY, "model": GEMINI_MODEL, "model_fast": GEMINI_MODEL_FAST,
     "api": "gemini", "max_ctx": 1000000},
]
_LLM_FALLBACK_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


class _LLMFallback(Exception):
    pass


def _llm_parse_json(raw):
    """Parse JSON avec repli sur les fences ```json ... ```."""
    try:
        return json.loads(raw)
    except Exception:
        c = (raw or "").strip()
        if c.startswith("```"):
            c = c.lstrip("`")
            if c[:4].lower() == "json":
                c = c[4:]
            c = c.strip("`").strip()
        return json.loads(c)


async def _llm_openai(prov, model, system_prompt, user_prompt, temperature, max_tokens, json_mode):
    payload = {"model": model,
               "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
               "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = await http().post(prov["url"], headers={"Authorization": f"Bearer {prov['key']}"}, json=payload, timeout=28.0)
    if r.status_code in _LLM_FALLBACK_STATUS:
        raise _LLMFallback(f"{prov['name']} {r.status_code}")
    if r.status_code != 200:
        raise RuntimeError(f"{prov['name']} {r.status_code}: {r.text[:150]}")
    return r.json()["choices"][0]["message"]["content"]


async def _llm_gemini(prov, system_prompt, user_prompt, temperature, max_tokens, json_mode):
    gen = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    payload = {"contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}], "generationConfig": gen}
    r = await http().post(f"{prov['url']}?key={prov['key']}", json=payload, timeout=28.0)
    if r.status_code in _LLM_FALLBACK_STATUS:
        raise _LLMFallback(f"gemini {r.status_code}")
    if r.status_code != 200:
        raise RuntimeError(f"gemini {r.status_code}: {r.text[:150]}")
    cands = r.json().get("candidates") or []
    if not cands:
        raise _LLMFallback("gemini vide")
    return "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))


async def call_groq(system_prompt: str, user_prompt: str, temperature: float = 0.2,
                    max_tokens: int = 1000, json_mode: bool = True, retries: int = 2,
                    tier: str = "smart") -> Any:
    """Routeur LLM multi-fournisseurs. tier="fast" = petit modèle (conversation) ;
    tier="smart" (défaut) = 70B / haut de gamme (analyse, sélection, rédaction)."""
    approx = (len(system_prompt) + len(user_prompt)) // 4 + max_tokens
    last = None
    tried = False
    for prov in _LLM_PROVIDERS:
        if not prov["key"]:
            continue
        if approx > prov["max_ctx"] * 0.95:
            continue
        tried = True
        model = prov.get("model_fast", prov["model"]) if tier == "fast" else prov["model"]
        for attempt in range(max(1, min(retries, 2))):
            try:
                if prov["api"] == "gemini":
                    raw = await _llm_gemini(prov, system_prompt, user_prompt, temperature, max_tokens, json_mode)
                else:
                    raw = await _llm_openai(prov, model, system_prompt, user_prompt, temperature, max_tokens, json_mode)
                logger.info(f"[llm] via {prov['name']} ({model})")
                return _llm_parse_json(raw) if json_mode else raw
            except _LLMFallback as f:
                last = f
                if attempt < 1:
                    await asyncio.sleep(1.0)
                else:
                    logger.warning(f"[llm] bascule {prov['name']}: {f}")
            except Exception as e:
                last = e
                logger.error(f"[llm] {prov['name']} erreur: {e}")
                break
    if not tried:
        raise HTTPException(500, "Aucun fournisseur LLM configuré (clés manquantes).")
    logger.error(f"[llm] tous indisponibles: {last}")
    raise HTTPException(503, "Service IA temporairement surchargé. Réessaie dans un instant.")


# ── Embeddings (matching sémantique) ──
# Selon la clé Gemini, tous les modèles ne sont pas dispos : on essaie, on retient celui qui répond.
EMBED_MODELS = [m.strip() for m in os.getenv(
    "EMBED_MODELS", "gemini-embedding-001,text-embedding-004,embedding-001"
).split(",") if m.strip()]
_embed_model_ok = None   # None = pas testé ; str = modèle OK ; False = aucun (repli lexical)


def _embeddings_available() -> bool:
    return bool(GEMINI_API_KEY) and _embed_model_ok is not False


async def embed_text(text: str):
    global _embed_model_ok
    text = (text or "").strip()
    if not text or not GEMINI_API_KEY or _embed_model_ok is False:
        return None
    key = "emb:" + hashlib.sha1(text[:2000].encode("utf-8", "ignore")).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    models = [_embed_model_ok] if _embed_model_ok else list(EMBED_MODELS)
    all_404 = True
    for model in [m for m in models if m]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={GEMINI_API_KEY}"
            r = await http().post(url, json={"model": f"models/{model}", "content": {"parts": [{"text": text[:2000]}]}}, timeout=20.0)
        except Exception as e:
            logger.warning(f"[embed] {e}")
            return None
        if r.status_code == 404:
            continue   # modèle indispo pour cette clé → candidat suivant
        all_404 = False
        if r.status_code != 200:
            return None
        vec = (r.json().get("embedding") or {}).get("values")
        if vec:
            _embed_model_ok = model
            cache.set(key, vec, 7 * 24 * 3600)
        return vec
    if all_404:
        _embed_model_ok = False
        logger.warning("[embed] aucun modèle d'embeddings dispo pour cette clé -> matching lexical (mots-clés)")
    return None


def _cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def semantic_scores(profil_txt: str, items: list, text_of) -> Optional[list]:
    """Renvoie une liste de similarités [0..1] alignée sur `items`, ou None si indisponible.
    `text_of(item)` fournit le texte représentatif ; embeddings calculés en parallèle et mis en cache."""
    if not items or not _embeddings_available():
        return None
    pv = await embed_text(profil_txt)
    if not pv:
        return None
    vecs = await asyncio.gather(*[embed_text(text_of(it) or "") for it in items])
    return [_cosine(pv, v) if v else 0.0 for v in vecs]


# ── Analyse vision (CV en image, Gemini multimodal) ──
async def analyze_cv_image_vision(img_bytes: bytes, mime: str = "image/jpeg") -> dict:
    """Analyse d'un CV en IMAGE via Gemini vision : renvoie le JSON du profil directement.
    Repli sur OCR géré par l'appelant (dans process_cv)."""
    if not (GEMINI_API_KEY and _PILImage):
        return {}
    system = ("Tu es expert en analyse de CV. Sur cette IMAGE de CV, extrais toutes les informations. "
              "Si ce n'est PAS un CV, mets \"est_cv\": false. Ajoute un \"bilan\" court (forces, axes, pistes). "
              "Réponds en JSON strict, uniquement le JSON.")
    schema = ('{"est_cv":true,"raison_rejet":"","identite":{"nom":"","email":"","telephone":"","localisation":"","linkedin":"","github":"","langues":[]},'
              '"formation":[{"diplome":"","domaine":"","etablissement":"","ville":"","pays":"","annee":""}],'
              '"competences":{"techniques":[],"securite":[],"outils":[],"frameworks":[],"soft_skills":[]},'
              '"experience":[{"poste":"","organisation":"","type":"","duree":"","date_debut":"","date_fin":"","localisation":"","missions":[]}],'
              '"projets":[{"nom":"","description":"","technologies":[],"url":""}],"certifications":[],'
              '"preferences":{"types_opportunite":["emploi","bourse","fellowship"],"niveau":"professionnel","langues_opportunite":["fr","en"],"delai_min_jours":14,"mots_cles":[],"geographie":[]},'
              '"bilan":{"forces":["..."],"axes":["..."],"pistes":["..."]},"niveau_global":"junior|mid|senior","resume_profil":""}')
    payload = {
        "contents": [{"parts": [
            {"text": system + "\nSchéma attendu : " + schema},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(img_bytes).decode()}},
        ]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2500, "responseMimeType": "application/json"},
    }
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        r = await http().post(url, json=payload, timeout=45.0)
        if r.status_code != 200:
            logger.warning(f"[vision] {r.status_code}: {r.text[:150]}")
            return {}
        cands = r.json().get("candidates") or []
        if not cands:
            return {}
        raw = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
        return _llm_parse_json(raw) or {}
    except Exception as e:
        logger.warning(f"[vision] {e}")
        return {}


async def analyze_screenshot_vision(img_bytes: bytes, mime: str = "image/jpeg", context: str = "") -> str:
    """Mode /guide : analyse une CAPTURE D'ÉCRAN d'une plateforme (Campus France, Parcoursup,
    Études en France, un formulaire, un mail…) et renvoie un texte de guidage concret (étapes)."""
    if not (GEMINI_API_KEY and _PILImage):
        return ""
    system = (
        "Tu es NexMove, un conseiller en mobilité/orientation qui aide des francophones d'Afrique de "
        "l'Ouest (Bénin…) à s'inscrire sur des plateformes (Campus France « Études en France », Parcoursup, "
        "Mon Master, eCandidat, DAP, portails de visa, formulaires, e-mails d'admission…). "
        "À partir de la CAPTURE D'ÉCRAN, fais 3 choses, en français, en TUTOYANT, sans blabla :\n"
        "1) Identifie la plateforme/l'écran et OÙ en est l'utilisateur.\n"
        "2) Explique QUOI FAIRE MAINTENANT, étape par étape (clics, champs à remplir, pièces à joindre).\n"
        "3) Signale les pièges/erreurs visibles et le point de vigilance suivant.\n"
        "Si l'image est illisible ou hors sujet, dis-le et demande une capture plus nette. "
        "Réponds en texte court et actionnable (pas de JSON, pas de Markdown lourd)."
    )
    if context:
        system += f"\nContexte fourni par l'utilisateur : {context[:300]}"
    payload = {
        "contents": [{"parts": [
            {"text": system},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(img_bytes).decode()}},
        ]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 900},
    }
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        r = await http().post(url, json=payload, timeout=45.0)
        if r.status_code != 200:
            logger.warning(f"[guide-vision] {r.status_code}: {r.text[:150]}")
            return ""
        cands = r.json().get("candidates") or []
        if not cands:
            return ""
        return "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()
    except Exception as e:
        logger.warning(f"[guide-vision] {e}")
        return ""
