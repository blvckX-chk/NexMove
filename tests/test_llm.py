"""Tests unitaires du module llm.py — sans réseau.
On teste les fonctions PURES (parse JSON, cosine) et la sélection de modèle par tier."""
import os, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
os.environ.setdefault("GEMINI_API_KEY", "")

import llm  # noqa: E402


# ------------------ Parse JSON tolérant ------------------
def test_llm_parse_json_direct():
    assert llm._llm_parse_json('{"a": 1}') == {"a": 1}

def test_llm_parse_json_fences_json():
    assert llm._llm_parse_json('```json\n{"a": 2}\n```') == {"a": 2}

def test_llm_parse_json_fences_generic():
    assert llm._llm_parse_json('```\n{"a": 3}\n```') == {"a": 3}


# ------------------ Cosine ------------------
def test_cosine_identique():
    assert round(llm._cosine([1, 2, 3], [1, 2, 3]), 6) == 1.0

def test_cosine_orthogonal():
    assert llm._cosine([1, 0], [0, 1]) == 0.0

def test_cosine_zero_vecteur():
    assert llm._cosine([], [1, 2]) == 0.0
    assert llm._cosine([0, 0], [1, 1]) == 0.0


# ------------------ Providers list & tier selection ------------------
def test_llm_providers_bien_formes():
    assert isinstance(llm._LLM_PROVIDERS, list) and len(llm._LLM_PROVIDERS) == 3
    for p in llm._LLM_PROVIDERS:
        assert set(("name", "url", "key", "model", "model_fast", "api", "max_ctx")).issubset(p)
    names = [p["name"] for p in llm._LLM_PROVIDERS]
    assert names == ["cerebras", "groq", "gemini"]   # ordre = priorité de bascule

def test_llm_fallback_status_contient_429():
    # 429 et 5xx transitoires -> bascule vers le fournisseur suivant
    assert 429 in llm._LLM_FALLBACK_STATUS
    for code in (500, 502, 503, 504):
        assert code in llm._LLM_FALLBACK_STATUS

def test_embeddings_available_sans_cle():
    # Sans GEMINI_API_KEY, on doit retomber en lexical (False)
    llm.GEMINI_API_KEY = ""   # patch local
    llm._embed_model_ok = None
    assert llm._embeddings_available() is False


# ------------------ Vision : garde-fou sans clé ni Pillow ------------------
import asyncio

def test_vision_sans_cle_renvoie_vide():
    llm.GEMINI_API_KEY = ""
    res = asyncio.run(llm.analyze_cv_image_vision(b"fake"))
    assert res == {}
