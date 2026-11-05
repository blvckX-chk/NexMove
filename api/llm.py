"""IA — routeur multi-fournisseurs (Cerebras → Groq → Gemini) + embeddings + vision.
Extrait de main.py (PR-B du refactor). Comportement STRICTEMENT identique :
- même liste de fournisseurs / modèles configurables via env
- même bascule sur quota/erreur, même parsing JSON tolérant
- mêmes embeddings (essai multi-modèles, cache 7j via db.cache)
- même analyse vision Gemini pour les CV en image
"""
from __future__ import annotations
import os, json, hashlib, base64, asyncio, math, logging, contextvars
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
# OpenRouter : 4e fournisseur, DERNIER RECOURS (pay-as-you-go). Dormant tant que la clé n'est pas fournie.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Tchavi (passerelle LLM OpenAI-compatible, à crédits). Fournisseur PREMIUM optionnel : dormant tant que
# la clé n'est pas fournie. Vérifie l'URL exacte dans ton tableau de bord Tchavi (section Clés API / doc).
TCHAVI_API_KEY  = os.getenv("TCHAVI_API_KEY", "")
TCHAVI_BASE_URL = os.getenv("TCHAVI_BASE_URL", "https://tchavi.com/api/v1").rstrip("/")
# 3 NIVEAUX de modèles Tchavi (le bon modèle pour la bonne tâche — pas tout sur le mini) :
#  - FAST    : routage/conversation (gros volume) -> petit modèle rapide & bon marché
#  - SMART   : raisonnement, sélection d'offres, anti-invention -> modèle intermédiaire
#  - QUALITY : rédaction CV/lettre/projet (le LIVRABLE montré) -> le modèle le PLUS costaud
# Par défaut, SMART retombe sur le mini et QUALITY/FAST retombent sur SMART : configure-les dans .env
# pour mettre un modèle fort sur la rédaction sans payer le premium sur le routage.
TCHAVI_MODEL          = os.getenv("TCHAVI_MODEL", "gpt-4o-mini")              # tier smart (raisonnement)
TCHAVI_MODEL_FAST     = os.getenv("TCHAVI_MODEL_FAST", TCHAVI_MODEL)          # tier fast (conversation)
TCHAVI_GENERATE_MODEL = os.getenv("TCHAVI_GENERATE_MODEL", TCHAVI_MODEL)      # tier quality (rédaction)
# Modèle VISION via Tchavi (lecture d'images/captures). DOIT supporter la vision (gpt-4o, claude, gemini…).
# Défaut = le modèle quality. Repli automatique sur Gemini si vide/échec -> jamais de panne.
TCHAVI_VISION_MODEL   = os.getenv("TCHAVI_VISION_MODEL", TCHAVI_GENERATE_MODEL)

# Gating par TIER : même LOGIQUE pour tous, mais les modèles PREMIUM (Tchavi/OpenRouter) sont réservés
# à l'admin et aux abonnés payants. Les comptes gratuits gardent tout le système mais sur modèles gratuits.
# Réglé par requête via set_allow_premium() ; défaut True (appels internes/admin).
_PREMIUM_PROVIDER_NAMES = {"tchavi", "openrouter", "tchavi-gen", "openrouter-gen"}
_ALLOW_PREMIUM = contextvars.ContextVar("allow_premium", default=True)

def set_allow_premium(allowed: bool) -> None:
    """À appeler au début du traitement d'un message : True pour admin/payant, False pour gratuit."""
    _ALLOW_PREMIUM.set(bool(allowed))

def _premium_allowed() -> bool:
    try:
        return _ALLOW_PREMIUM.get()
    except Exception:
        return True

GROQ_MODEL          = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_MODEL_FAST     = os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")
CEREBRAS_MODEL      = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
# gemma-4-31b n'existe pas chez Cerebras -> le niveau "fast" échouait. Défaut sur un vrai petit modèle.
CEREBRAS_MODEL_FAST = os.getenv("CEREBRAS_MODEL_FAST", "llama3.1-8b")
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_MODEL_FAST   = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash-lite")
# Modèle VISION dédié à la lecture de texte sur affiches/annonces stylisées (plus costaud par défaut :
# lit mieux le texte par-dessus un visuel). Surchargable via l'env si besoin de coût/latence.
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-pro")
OPENROUTER_MODEL      = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b")
OPENROUTER_MODEL_FAST = os.getenv("OPENROUTER_MODEL_FAST", "openai/gpt-oss-20b")
# Modèle PREMIUM optionnel pour la rédaction CV/lettre (tier="quality"). Ex : "anthropic/claude-3.5-sonnet".
OPENROUTER_GENERATE_MODEL = os.getenv("OPENROUTER_GENERATE_MODEL", OPENROUTER_MODEL)
# Fournisseur PRÉFÉRÉ pour le tier "smart" (conversation, sélection, conseils) : meilleur suivi du
# contexte et des consignes anti-invention. Par défaut Gemini (fort, long contexte, déjà configuré).
SMART_LEAD_PROVIDER = os.getenv("SMART_LEAD_PROVIDER", "gemini").strip().lower()

# Dernier fournisseur/modèle ayant répondu avec succès (pour tracer qui a RÉDIGÉ chaque livrable :
# A/B Tchavi premium vs modèles gratuits). Mis à jour par call_groq à chaque appel abouti.
LAST_PROVIDER = ""
LAST_MODEL = ""

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
    # DERNIER RECOURS (payant) : ne s'active que si OPENROUTER_API_KEY est défini -> le bot ne tombe jamais.
    {"name": "openrouter", "url": "https://openrouter.ai/api/v1/chat/completions",
     "key": OPENROUTER_API_KEY, "model": OPENROUTER_MODEL, "model_fast": OPENROUTER_MODEL_FAST,
     "api": "openai", "max_ctx": 120000},
    # Tchavi (premium, à crédits) : dormant sans clé. Dans le repli il passe EN DERNIER (coût maîtrisé) ;
    # mais sur le tier "quality" il passe en 1er (voir call_groq), et on peut le préférer pour le "smart"
    # via SMART_LEAD_PROVIDER=tchavi.
    {"name": "tchavi", "url": f"{TCHAVI_BASE_URL}/chat/completions",
     "key": TCHAVI_API_KEY, "model": TCHAVI_MODEL, "model_fast": TCHAVI_MODEL_FAST,
     "api": "openai", "max_ctx": 120000},
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
    tier="smart" (défaut) = haut de gamme (analyse, sélection) ;
    tier="quality" = passe par le modèle PREMIUM OpenRouter EN PREMIER (rédaction CV/lettre), sinon smart."""
    approx = (len(system_prompt) + len(user_prompt)) // 4 + max_tokens
    last = None
    tried = False
    providers = _LLM_PROVIDERS
    if tier == "quality":
        # Tier qualité (rédaction CV/lettre, projet d'études) : on met le(s) modèle(s) PREMIUM en 1er.
        # Tchavi d'abord s'il est configuré (c'est le choix explicite de l'utilisateur pour le premium),
        # puis OpenRouter, puis la chaîne standard en repli -> jamais de panne.
        lead = []
        if TCHAVI_API_KEY:
            lead.append({"name": "tchavi-gen", "url": f"{TCHAVI_BASE_URL}/chat/completions",
                         "key": TCHAVI_API_KEY, "model": TCHAVI_GENERATE_MODEL,
                         "model_fast": TCHAVI_GENERATE_MODEL, "api": "openai", "max_ctx": 120000})
        if OPENROUTER_API_KEY:
            lead.append({"name": "openrouter-gen", "url": "https://openrouter.ai/api/v1/chat/completions",
                         "key": OPENROUTER_API_KEY, "model": OPENROUTER_GENERATE_MODEL,
                         "model_fast": OPENROUTER_GENERATE_MODEL, "api": "openai", "max_ctx": 120000})
        providers = lead + _LLM_PROVIDERS
        tier = "smart"   # fallback = qualité standard
    elif tier == "smart" and SMART_LEAD_PROVIDER:
        # On met le fournisseur préféré en tête pour le conversationnel (meilleur contexte/anti-invention),
        # sans casser la chaîne de repli (tri stable : les autres gardent leur ordre).
        providers = sorted(_LLM_PROVIDERS, key=lambda p: p["name"] != SMART_LEAD_PROVIDER)
    # Compte gratuit : on retire les fournisseurs PREMIUM (même logique, modèles gratuits).
    if not _premium_allowed():
        providers = [p for p in providers if p["name"] not in _PREMIUM_PROVIDER_NAMES]
    for prov in providers:
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
                global LAST_PROVIDER, LAST_MODEL
                LAST_PROVIDER, LAST_MODEL = prov["name"], model
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


# ─────────────────────────────────────────────────────────────────────────────
# CONSENSUS MULTI-MODÈLES — uniquement pour la DÉFINITION DU PROFIL (rare -> coût OK).
#   • Abonnés payants (premium autorisé) : PANEL + JUGE — plusieurs modèles extraient
#     en parallèle, un modèle « juge » fusionne en UN profil fidèle (zéro invention).
#   • Comptes gratuits : VOTE DE COHÉRENCE — même extraction sur plusieurs modèles
#     gratuits, on garde les champs qui font consensus ; la confiance = taux d'accord.
# Dans les deux cas on GARDE une confiance/provenance par champ dans profil["_meta"],
# + un hash de la source pour ne PAS relancer le panel si le profil n'a pas changé.
# ─────────────────────────────────────────────────────────────────────────────

# Champs scalaires votés à la majorité (chemins imbriqués).
_PROFILE_SCALAR_PATHS = [
    ("identite", "nom"), ("identite", "email"), ("identite", "telephone"),
    ("identite", "localisation"), ("identite", "linkedin"), ("identite", "github"),
    ("niveau_global",), ("resume_profil",),
]
# Champs listes : union dédupliquée. Pour les listes de dicts, clé de dédup.
_PROFILE_LIST_DICT_KEYS = {
    "formation": ("diplome", "annee"),
    "experience": ("poste", "organisation"),
    "projets": ("nom",),
}


def profile_source_hash(text: str) -> str:
    """Empreinte courte et stable de la source (texte du CV / réponses) pour l'idempotence."""
    return hashlib.sha256((text or "").strip().encode("utf-8", "ignore")).hexdigest()[:16]


def _available_provider_names(premium: bool) -> list:
    out = []
    for p in _LLM_PROVIDERS:
        if not p.get("key"):
            continue
        if not premium and p["name"] in _PREMIUM_PROVIDER_NAMES:
            continue
        out.append(p["name"])
    return out


def _dig(d, path):
    v = d
    for k in path:
        v = v.get(k) if isinstance(v, dict) else None
    return v


def _norm_val(v) -> str:
    return " ".join(str(v if v is not None else "").lower().split())


def _is_empty(v) -> bool:
    return v in (None, "", [], {}) or (isinstance(v, str) and not v.strip())


def _completeness(profil: dict) -> int:
    """Nombre de champs utiles remplis — sert à choisir la base la plus riche."""
    score = 0
    ident = profil.get("identite") or {}
    score += sum(1 for k in ("nom", "email", "telephone", "localisation") if not _is_empty(ident.get(k)))
    score += len(profil.get("formation") or [])
    score += len(profil.get("experience") or [])
    for vals in (profil.get("competences") or {}).values():
        score += len(vals or []) if isinstance(vals, list) else 0
    if not _is_empty(profil.get("resume_profil")):
        score += 2
    return score


def _vote_scalar(cands: list, path):
    """Majorité sur un champ scalaire ; renvoie (valeur_gagnante, confiance 0-1)."""
    from collections import Counter
    vals = [_dig(c, path) for c in cands]
    vals = [v for v in vals if not _is_empty(v)]
    if not vals:
        return None, 0.0
    counts = Counter(_norm_val(v) for v in vals)
    top_norm, n = counts.most_common(1)[0]
    winner = next(v for v in vals if _norm_val(v) == top_norm)
    return winner, round(n / len(cands), 2)


def _union_list(cands: list, field: str):
    """Union dédupliquée d'un champ liste ; confiance = fraction de candidats non vides."""
    dict_key = _PROFILE_LIST_DICT_KEYS.get(field)
    seen, merged = set(), []
    non_empty = 0
    for c in cands:
        lst = c.get(field)
        if not isinstance(lst, list) or not lst:
            continue
        non_empty += 1
        for item in lst:
            if isinstance(item, dict) and dict_key:
                sig = tuple(_norm_val(item.get(k)) for k in dict_key)
            else:
                sig = _norm_val(item) if not isinstance(item, (dict, list)) else _norm_val(json.dumps(item, sort_keys=True))
            if sig in seen:
                continue
            seen.add(sig)
            merged.append(item)
    return merged, round(non_empty / len(cands), 2) if cands else 0.0


def _vote_merge_profiles(cands: list):
    """VOTE DE COHÉRENCE (gratuit). Renvoie (profil_fusionné, confidence_map)."""
    base = dict(max(cands, key=_completeness))   # copie de la version la plus complète
    conf = {}
    # Scalaires : la majorité corrige la base.
    for path in _PROFILE_SCALAR_PATHS:
        val, c = _vote_scalar(cands, path)
        key = ".".join(path)
        if val is not None:
            tgt = base
            for k in path[:-1]:
                tgt = tgt.setdefault(k, {})
                if not isinstance(tgt, dict):
                    break
            else:
                tgt[path[-1]] = val
            conf[key] = c
    # Listes simples et de dicts : union.
    for field in ("formation", "experience", "projets", "certifications"):
        merged, c = _union_list(cands, field)
        if merged:
            base[field] = merged
            conf[field] = c
    # langues (dans identite) + compétences (dict de listes).
    lang, lc = _union_list([{"langues": (c.get("identite") or {}).get("langues")} for c in cands], "langues")
    if lang:
        base.setdefault("identite", {})["langues"] = lang
        conf["identite.langues"] = lc
    comp_keys = set()
    for c in cands:
        comp_keys.update((c.get("competences") or {}).keys())
    if comp_keys:
        base.setdefault("competences", {})
        for ck in comp_keys:
            merged, c = _union_list([{ck: (cc.get("competences") or {}).get(ck)} for cc in cands], ck)
            if merged:
                base["competences"][ck] = merged
                conf[f"competences.{ck}"] = c
    return base, conf


_JUDGE_SYSTEM = (
    "Tu es un JUGE d'extractions de CV. On te donne PLUSIEURS extractions JSON du MÊME document, "
    "faites par des modèles différents. Fusionne-les en UN SEUL profil, le plus fidèle et complet. "
    "RÈGLES STRICTES : n'invente AUCUNE information qui n'apparaît dans aucune extraction ; "
    "si les extractions se contredisent, garde la valeur la plus fréquente / la plus plausible ; "
    "pour les listes (formation, expérience, compétences, langues), fais l'UNION sans doublons ; "
    "identite.nom = le vrai nom de la personne, jamais un titre de modèle de CV. "
    "Réponds en JSON STRICT : {\"profil\": {<le profil fusionné, même schéma que les extractions>}, "
    "\"confidence\": {\"<champ>\": <0.0-1.0 = accord entre extractions>}}."
)


async def _judge_merge_profiles(cands: list, max_tokens: int):
    """PANEL + JUGE (payant). Renvoie (profil_fusionné, confidence_map) ou (None, None) si échec."""
    payload = "\n\n".join(f"Extraction {i+1} :\n{json.dumps(c, ensure_ascii=False)}" for i, c in enumerate(cands))
    try:
        out = await call_groq(_JUDGE_SYSTEM, payload, temperature=0.0,
                              max_tokens=max(max_tokens, 2500), tier="smart")
    except Exception as e:
        logger.warning(f"[consensus] juge échec: {e}")
        return None, None
    if not isinstance(out, dict):
        return None, None
    profil = out.get("profil") if isinstance(out.get("profil"), dict) else out
    conf = out.get("confidence") if isinstance(out.get("confidence"), dict) else {}
    if not isinstance(profil, dict) or not profil:
        return None, None
    return profil, conf


async def _extract_on(name: str, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int):
    """Extraction forcée sur UN fournisseur nommé (sans repli). dict ou None."""
    prov = next((p for p in _LLM_PROVIDERS if p["name"] == name and p.get("key")), None)
    if not prov:
        return None
    try:
        if prov["api"] == "gemini":
            raw = await _llm_gemini(prov, system_prompt, user_prompt, temperature, max_tokens, True)
        else:
            raw = await _llm_openai(prov, prov["model"], system_prompt, user_prompt, temperature, max_tokens, True)
        d = _llm_parse_json(raw)
        return d if isinstance(d, dict) and d else None
    except Exception as e:
        logger.warning(f"[consensus] {name} échec: {e}")
        return None


async def build_profile_consensus(system_prompt: str, user_prompt: str, *, source_text: str = "",
                                  temperature: float = 0.1, max_tokens: int = 3500):
    """Construit un profil par CONSENSUS multi-modèles (voir en-tête de section).
    Renvoie un profil dict enrichi de profil["_meta"] = {method, confidence, providers,
    source_hash, built_at}. Repli propre sur une extraction simple si < 2 modèles dispos
    ou en cas d'échec -> jamais de panne. Respecte le gating tier (premium filtré pour le gratuit)."""
    premium = _premium_allowed()
    names = _available_provider_names(premium)
    meta = {"method": "single", "confidence": {}, "providers": names[:1],
            "source_hash": profile_source_hash(source_text or user_prompt)}

    def _finish(profil, method, conf, provs):
        if isinstance(profil, dict) and profil:
            meta.update(method=method, confidence=conf or {}, providers=provs)
            profil["_meta"] = meta
        return profil

    if len(names) < 2:
        profil = await call_groq(system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens)
        return _finish(profil if isinstance(profil, dict) else {}, "single", {}, names[:1])

    panel = names[:3]
    results = await asyncio.gather(
        *[_extract_on(n, system_prompt, user_prompt, temperature, max_tokens) for n in panel],
        return_exceptions=True)
    cands = [(n, r) for n, r in zip(panel, results) if isinstance(r, dict) and r]
    if not cands:
        # tous les modèles forcés ont échoué -> extraction standard avec repli interne
        profil = await call_groq(system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens)
        return _finish(profil if isinstance(profil, dict) else {}, "single", {}, [])
    if len(cands) == 1:
        return _finish(cands[0][1], "single", {}, [cands[0][0]])

    cand_profiles = [c[1] for c in cands]
    provs = [c[0] for c in cands]
    if premium:
        merged, conf = await _judge_merge_profiles(cand_profiles, max_tokens)
        if merged:
            return _finish(merged, "panel+judge", conf, provs)
        merged, conf = _vote_merge_profiles(cand_profiles)   # repli si le juge échoue
        return _finish(merged, "vote(fallback)", conf, provs)
    merged, conf = _vote_merge_profiles(cand_profiles)
    return _finish(merged, "vote", conf, provs)


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
async def analyze_cv_image_vision(img_bytes: bytes, mime: str = "image/jpeg", max_tokens: int = 3500) -> dict:
    """Analyse d'un CV en IMAGE via Gemini vision : renvoie le JSON du profil directement.
    Repli sur OCR géré par l'appelant (dans process_cv)."""
    if not (GEMINI_API_KEY and _PILImage):
        return {}
    system = ("Tu es expert en analyse de CV. Sur cette IMAGE de CV, extrais toutes les informations. "
              "Si ce n'est PAS un CV, mets \"est_cv\": false. Ajoute un \"bilan\" court (forces, axes, pistes). "
              "identite.nom = le VRAI nom de la personne (prénom + nom, l'en-tête le plus visible) — JAMAIS "
              "un nom de modèle/template ou de style (« CV Moderne », « Français Simple Moderne », « Bleu »), "
              "ni un titre de document, ni un intitulé de poste. Si tu n'es pas sûr du nom réel, laisse-le vide. "
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
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": int(max_tokens), "responseMimeType": "application/json"},
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


# Prompt VISION structuré : lit l'image et répond de façon PRÉSENTABLE (contexte -> réponse -> suite).
_VISION_SYSTEM = (
    "Tu es NexMove, assistant mobilité/emploi pour des francophones d'Afrique de l'Ouest. "
    "On te donne une IMAGE (souvent une capture : conversation, annonce, document, e-mail, écran…) et une "
    "QUESTION. Lis attentivement l'image, puis réponds en français, en TUTOYANT, de façon PRÉSENTABLE et courte, "
    "dans cet ordre exact :\n"
    "• *Contexte* : 1 phrase sur ce que montre l'image (de quoi il s'agit).\n"
    "• *Réponse* : réponds précisément à la question, en t'appuyant sur ce qui est visible (2-4 phrases).\n"
    "• *Et après* : 1 action concrète suivante (facultatif, seulement si utile).\n"
    "N'invente rien : si une info n'est pas visible, dis-le. Si l'image est illisible, dis-le et demande une "
    "capture plus nette. Pas de JSON, pas de Markdown lourd (juste ces 3 puces)."
)

async def _vision_tchavi(img_bytes: bytes, mime: str, question: str) -> str:
    """Analyse d'image via Tchavi (format OpenAI image_url). '' si pas de clé / modèle sans vision / échec
    / compte gratuit (les comptes gratuits passent par la vision gratuite Gemini)."""
    if not (TCHAVI_API_KEY and TCHAVI_VISION_MODEL) or not _premium_allowed():
        return ""
    data_uri = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
    payload = {"model": TCHAVI_VISION_MODEL,
               "messages": [{"role": "system", "content": _VISION_SYSTEM},
                            {"role": "user", "content": [
                                {"type": "text", "text": (question or "Analyse cette image.")[:500]},
                                {"type": "image_url", "image_url": {"url": data_uri}}]}],
               "temperature": 0.3, "max_tokens": 900}
    try:
        r = await http().post(f"{TCHAVI_BASE_URL}/chat/completions",
                              headers={"Authorization": f"Bearer {TCHAVI_API_KEY}"}, json=payload, timeout=45.0)
        if r.status_code != 200:
            logger.warning(f"[img-q] tchavi {TCHAVI_VISION_MODEL} {r.status_code}: {r.text[:150]}")
            return ""
        txt = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        return txt.strip()
    except Exception as e:
        logger.warning(f"[img-q] tchavi {e}")
        return ""

async def _vision_gemini(img_bytes: bytes, mime: str, question: str) -> str:
    """Repli : analyse d'image via Gemini (inline_data). '' si indisponible."""
    if not GEMINI_API_KEY:
        return ""
    sys_q = _VISION_SYSTEM + (f"\n\nQUESTION : {question[:400]}" if question else "")
    payload = {"contents": [{"parts": [
        {"text": sys_q},
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(img_bytes).decode()}}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 900}}
    for model in (GEMINI_VISION_MODEL, GEMINI_MODEL):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = await http().post(url, json=payload, timeout=45.0)
            if r.status_code != 200:
                logger.warning(f"[img-q] gemini {model} {r.status_code}: {r.text[:150]}")
                continue
            cands = r.json().get("candidates") or []
            if cands:
                txt = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()
                if txt:
                    return txt
        except Exception as e:
            logger.warning(f"[img-q] gemini {model} {e}")
    return ""

async def analyze_image_question(img_bytes: bytes, mime: str = "image/jpeg", question: str = "") -> str:
    """Analyse GÉNÉRALE d'une image/capture à la demande (vision) : lit le contenu et répond à la QUESTION,
    de façon présentable. Route par TCHAVI EN PREMIER (modèle premium), repli GEMINI -> jamais de panne."""
    rep = await _vision_tchavi(img_bytes, mime, question)
    if rep:
        logger.info("[img-q] analysé via tchavi")
        return rep
    rep = await _vision_gemini(img_bytes, mime, question)
    if rep:
        logger.info("[img-q] analysé via gemini (repli)")
    return rep


async def extract_text_vision(img_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Transcrit TOUT le texte visible d'une image (affiche/annonce stylisée, flyer, bannière…)
    via la vision — là où l'OCR classique (tesseract) échoue sur les visuels graphiques.
    Renvoie le texte brut, ou '' si indisponible. Sert au multimodal : lire une annonce prise en photo.
    N.B. : n'utilise PAS PIL (envoi direct des octets à Gemini) -> pas de dépendance à _PILImage."""
    if not (GEMINI_API_KEY and img_bytes):
        return ""
    system = ("Transcris FIDÈLEMENT tout le texte visible sur cette image (affiche, annonce, flyer, "
              "capture). Rends UNIQUEMENT le texte, dans l'ordre de lecture, sans commentaire ni mise en "
              "forme. N'invente rien ; si une zone est illisible, ignore-la. Inclus les URL et contacts visibles.")
    payload = {
        "contents": [{"parts": [
            {"text": system},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(img_bytes).decode()}},
        ]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 900},
    }
    # Modèle costaud d'abord (lit mieux les affiches stylisées), repli sur le modèle standard.
    for model in (GEMINI_VISION_MODEL, GEMINI_MODEL):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = await http().post(url, json=payload, timeout=45.0)
            if r.status_code != 200:
                logger.warning(f"[ocr-vision] {model} {r.status_code}: {r.text[:150]}")
                continue
            cands = r.json().get("candidates") or []
            txt = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip() if cands else ""
            logger.info(f"[ocr-vision] {model} -> {len(txt)} caractères lus")
            if txt:
                return txt
        except Exception as e:
            logger.warning(f"[ocr-vision] {model} {e}")
    return ""


async def transcribe_audio(audio_bytes: bytes, mime: str = "audio/ogg") -> str:
    """Transcrit un message vocal (Telegram/WhatsApp) en texte via Gemini. Renvoie '' si échec.
    Permet aux utilisateurs qui préfèrent parler d'utiliser le bot naturellement."""
    if not (GEMINI_API_KEY and audio_bytes):
        return ""
    payload = {
        "contents": [{"parts": [
            {"text": ("Transcris fidèlement ce message vocal en TEXTE. Rends UNIQUEMENT la transcription, "
                      "sans commentaire ni guillemets. Si c'est du français, garde le français.")},
            {"inline_data": {"mime_type": mime or "audio/ogg", "data": base64.b64encode(audio_bytes).decode()}},
        ]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 500},
    }
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_FAST}:generateContent?key={GEMINI_API_KEY}"
        r = await http().post(url, json=payload, timeout=45.0)
        if r.status_code != 200:
            logger.warning(f"[transcribe] {r.status_code}: {r.text[:150]}")
            return ""
        cands = r.json().get("candidates") or []
        if not cands:
            return ""
        return "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()
    except Exception as e:
        logger.warning(f"[transcribe] {e}")
        return ""
