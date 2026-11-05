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
    assert isinstance(llm._LLM_PROVIDERS, list) and len(llm._LLM_PROVIDERS) == 5
    for p in llm._LLM_PROVIDERS:
        assert set(("name", "url", "key", "model", "model_fast", "api", "max_ctx")).issubset(p)
    names = [p["name"] for p in llm._LLM_PROVIDERS]
    # ordre = priorité de bascule : gratuits d'abord, payants en dernier recours (openrouter puis tchavi)
    assert names == ["cerebras", "groq", "gemini", "openrouter", "tchavi"]

def test_vision_route_tchavi_dabord_puis_gemini(monkeypatch):
    import asyncio
    calls = []
    async def fake_tchavi(img, mime, q):
        calls.append("tchavi"); return "ANALYSE TCHAVI"
    async def fake_gemini(img, mime, q):
        calls.append("gemini"); return "ANALYSE GEMINI"
    monkeypatch.setattr(llm, "_vision_tchavi", fake_tchavi)
    monkeypatch.setattr(llm, "_vision_gemini", fake_gemini)
    # Tchavi répond -> on l'utilise, Gemini pas appelé.
    out = asyncio.run(llm.analyze_image_question(b"x", "image/png", "q"))
    assert out == "ANALYSE TCHAVI" and calls == ["tchavi"]
    # Tchavi vide (modèle sans vision / pas de clé) -> repli Gemini.
    calls.clear()
    async def empty_tchavi(img, mime, q):
        calls.append("tchavi"); return ""
    monkeypatch.setattr(llm, "_vision_tchavi", empty_tchavi)
    out2 = asyncio.run(llm.analyze_image_question(b"x", "image/png", "q"))
    assert out2 == "ANALYSE GEMINI" and calls == ["tchavi", "gemini"]

def test_tchavi_3_niveaux_de_modeles(monkeypatch):
    # Les 3 tiers Tchavi sont configurables séparément : fast / smart (model) / quality (generate).
    monkeypatch.setattr(llm, "TCHAVI_MODEL_FAST", "mini-fast")
    monkeypatch.setattr(llm, "TCHAVI_MODEL", "mid-smart")
    monkeypatch.setattr(llm, "TCHAVI_GENERATE_MODEL", "big-quality")
    # Le provider principal : fast -> model_fast, smart -> model (indépendants).
    tch = {"name": "tchavi", "model": llm.TCHAVI_MODEL, "model_fast": llm.TCHAVI_MODEL_FAST}
    model_fast = tch.get("model_fast", tch["model"])
    model_smart = tch["model"]
    assert model_fast == "mini-fast" and model_smart == "mid-smart"
    # Et le lead "quality" doit viser le modèle de rédaction, distinct.
    assert llm.TCHAVI_GENERATE_MODEL == "big-quality"

def test_llm_fallback_status_contient_429():
    # 429 et 5xx transitoires -> bascule vers le fournisseur suivant
    assert 429 in llm._LLM_FALLBACK_STATUS
    for code in (500, 502, 503, 504):
        assert code in llm._LLM_FALLBACK_STATUS

def test_tier_gating_premium_filtre_pour_gratuit(monkeypatch):
    # Compte gratuit : les fournisseurs PREMIUM (tchavi/openrouter + variantes -gen) sont retirés.
    assert llm._PREMIUM_PROVIDER_NAMES == {"tchavi", "openrouter", "tchavi-gen", "openrouter-gen"}
    # Par défaut (admin / appels internes) : premium autorisé.
    assert llm._premium_allowed() is True
    # Gratuit : on coupe le premium.
    llm.set_allow_premium(False)
    assert llm._premium_allowed() is False
    # Les noms premium doivent bien exister parmi les providers configurés (sinon le filtre est inutile).
    noms = {p["name"] for p in llm._LLM_PROVIDERS}
    assert {"tchavi", "openrouter"}.issubset(noms)
    # Payant/admin : premium réautorisé.
    llm.set_allow_premium(True)
    assert llm._premium_allowed() is True

def test_tier_gating_vision_tchavi_bloquee_pour_gratuit(monkeypatch):
    import asyncio
    # Même avec une clé Tchavi, un compte gratuit ne passe PAS par la vision premium (repli Gemini).
    monkeypatch.setattr(llm, "TCHAVI_API_KEY", "fake-key")
    monkeypatch.setattr(llm, "TCHAVI_VISION_MODEL", "gpt-4o")
    llm.set_allow_premium(False)
    out = asyncio.run(llm._vision_tchavi(b"x", "image/png", "q"))
    assert out == ""   # bloqué -> chaîne retombe sur Gemini gratuit
    llm.set_allow_premium(True)  # reset pour les autres tests

def test_embeddings_available_sans_cle():
    # Sans GEMINI_API_KEY, on doit retomber en lexical (False)
    llm.GEMINI_API_KEY = ""   # patch local
    llm._embed_model_ok = None
    assert llm._embeddings_available() is False


# ------------------ Consensus multi-modèles (profils) ------------------
def test_source_hash_stable_et_tolerant():
    assert llm.profile_source_hash("  abc \n") == llm.profile_source_hash("abc")
    assert llm.profile_source_hash("a") != llm.profile_source_hash("b")
    assert isinstance(llm.profile_source_hash(""), str) and len(llm.profile_source_hash("x")) == 16

def test_available_providers_respecte_le_tier(monkeypatch):
    # Tous avec clé : gratuit exclut tchavi/openrouter, premium les garde.
    fake = [{"name": n, "key": "k"} for n in ("cerebras", "groq", "gemini", "openrouter", "tchavi")]
    monkeypatch.setattr(llm, "_LLM_PROVIDERS", fake)
    assert llm._available_provider_names(premium=False) == ["cerebras", "groq", "gemini"]
    assert llm._available_provider_names(premium=True) == ["cerebras", "groq", "gemini", "openrouter", "tchavi"]
    # Sans clé -> non listé.
    fake2 = [{"name": "cerebras", "key": ""}, {"name": "groq", "key": "k"}]
    monkeypatch.setattr(llm, "_LLM_PROVIDERS", fake2)
    assert llm._available_provider_names(premium=False) == ["groq"]

def test_vote_merge_majorite_scalaires_et_union_listes():
    c1 = {"identite": {"nom": "Awa Diop", "email": "awa@x.com", "langues": ["fr"]},
          "competences": {"techniques": ["python", "sql"]},
          "formation": [{"diplome": "Licence", "annee": "2020"}], "niveau_global": "junior", "resume_profil": "A"}
    c2 = {"identite": {"nom": "Awa Diop", "email": "awa@x.com", "langues": ["fr", "en"]},
          "competences": {"techniques": ["python"]},
          "formation": [{"diplome": "Licence", "annee": "2020"}, {"diplome": "Master", "annee": "2022"}],
          "niveau_global": "junior", "resume_profil": "B"}
    c3 = {"identite": {"nom": "Awa DIOP", "email": "autre@x.com", "langues": ["en"]},
          "competences": {"techniques": ["java"]},
          "formation": [{"diplome": "Master", "annee": "2022"}], "niveau_global": "mid", "resume_profil": "C"}
    merged, conf = llm._vote_merge_profiles([c1, c2, c3])
    # nom : 3/3 d'accord (normalisé) -> confiance 1.0
    assert merged["identite"]["nom"] in ("Awa Diop", "Awa DIOP")
    assert conf["identite.nom"] == 1.0
    # email : 2/3 awa@x.com -> gagne, confiance ~0.67
    assert merged["identite"]["email"] == "awa@x.com" and conf["identite.email"] == round(2/3, 2)
    # niveau_global : 2/3 junior
    assert merged["niveau_global"] == "junior"
    # langues : union fr+en
    assert set(merged["identite"]["langues"]) == {"fr", "en"}
    # compétences techniques : union python/sql/java
    assert set(merged["competences"]["techniques"]) == {"python", "sql", "java"}
    # formation : union dédupliquée sur (diplome, annee) -> Licence 2020 + Master 2022
    annees = sorted(f["annee"] for f in merged["formation"])
    assert annees == ["2020", "2022"]

def test_vote_merge_base_est_la_plus_complete():
    riche = {"identite": {"nom": "X", "email": "x@x.com", "telephone": "90"},
             "formation": [{"diplome": "A"}], "experience": [{"poste": "Dev"}],
             "competences": {"techniques": ["py"]}, "resume_profil": "long"}
    pauvre = {"identite": {"nom": "X"}}
    merged, _ = llm._vote_merge_profiles([pauvre, riche])
    assert merged["experience"] == [{"poste": "Dev"}]   # vient de la version riche

def test_build_consensus_single_si_un_seul_provider(monkeypatch):
    import asyncio
    monkeypatch.setattr(llm, "_LLM_PROVIDERS", [{"name": "groq", "key": "k"}])
    async def fake_call(sys, usr, **kw):
        return {"identite": {"nom": "Solo"}}
    monkeypatch.setattr(llm, "call_groq", fake_call)
    out = asyncio.run(llm.build_profile_consensus("s", "u", source_text="cv"))
    assert out["identite"]["nom"] == "Solo"
    assert out["_meta"]["method"] == "single" and "source_hash" in out["_meta"]

def test_build_consensus_vote_pour_gratuit(monkeypatch):
    import asyncio
    monkeypatch.setattr(llm, "_LLM_PROVIDERS",
                        [{"name": n, "key": "k", "api": "openai", "model": n} for n in ("cerebras", "groq", "gemini")])
    llm.set_allow_premium(False)
    async def fake_extract(name, s, u, t, m):
        return {"cerebras": {"identite": {"nom": "Awa"}, "competences": {"techniques": ["python"]}},
                "groq": {"identite": {"nom": "Awa"}, "competences": {"techniques": ["sql"]}},
                "gemini": {"identite": {"nom": "Awa"}, "competences": {"techniques": ["python"]}}}[name]
    monkeypatch.setattr(llm, "_extract_on", fake_extract)
    out = asyncio.run(llm.build_profile_consensus("s", "u", source_text="cv"))
    assert out["_meta"]["method"] == "vote"
    assert out["identite"]["nom"] == "Awa" and out["_meta"]["confidence"]["identite.nom"] == 1.0
    assert set(out["competences"]["techniques"]) == {"python", "sql"}
    llm.set_allow_premium(True)

def test_build_consensus_panel_juge_pour_payant(monkeypatch):
    import asyncio
    monkeypatch.setattr(llm, "_LLM_PROVIDERS",
                        [{"name": n, "key": "k", "api": "openai", "model": n} for n in ("gemini", "tchavi")])
    llm.set_allow_premium(True)
    async def fake_extract(name, s, u, t, m):
        return {"identite": {"nom": name}}
    async def fake_judge(cands, max_tokens):
        return {"identite": {"nom": "Fusion"}}, {"identite.nom": 0.9}
    monkeypatch.setattr(llm, "_extract_on", fake_extract)
    monkeypatch.setattr(llm, "_judge_merge_profiles", fake_judge)
    out = asyncio.run(llm.build_profile_consensus("s", "u", source_text="cv"))
    assert out["_meta"]["method"] == "panel+judge"
    assert out["identite"]["nom"] == "Fusion" and out["_meta"]["confidence"]["identite.nom"] == 0.9

def test_build_consensus_repli_vote_si_juge_echoue(monkeypatch):
    import asyncio
    monkeypatch.setattr(llm, "_LLM_PROVIDERS",
                        [{"name": n, "key": "k", "api": "openai", "model": n} for n in ("gemini", "tchavi")])
    llm.set_allow_premium(True)
    async def fake_extract(name, s, u, t, m):
        return {"identite": {"nom": "Awa"}}
    async def fake_judge(cands, max_tokens):
        return None, None
    monkeypatch.setattr(llm, "_extract_on", fake_extract)
    monkeypatch.setattr(llm, "_judge_merge_profiles", fake_judge)
    out = asyncio.run(llm.build_profile_consensus("s", "u", source_text="cv"))
    assert out["_meta"]["method"] == "vote(fallback)" and out["identite"]["nom"] == "Awa"
    llm.set_allow_premium(True)


# ------------------ Vision : garde-fou sans clé ni Pillow ------------------
import asyncio

def test_vision_sans_cle_renvoie_vide():
    llm.GEMINI_API_KEY = ""
    res = asyncio.run(llm.analyze_cv_image_vision(b"fake"))
    assert res == {}
