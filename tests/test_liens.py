"""Vérification des liens produits par l'IA (v4.06).

Le modèle reçoit des sources web et doit en reprendre les URL. Rien ne l'y obligeait : la
seule protection était une phrase dans l'invite (« jamais d'URL inventée »), ce qui n'est pas
un garde-fou. Un lien plausible mais mort, envoyé à quelqu'un qui cherche une bourse, est la
panne la plus coûteuse pour un produit qui promet « de vraies opportunités ».
"""
import os, sys, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
import importlib
main = importlib.import_module("main")

SOURCES = [
    {"title": "Bourses du gouvernement", "url": "https://exemple-officiel.bj/bourses/2026"},
    {"title": "Programme X", "url": "https://autre-source.org/programme"},
]


def test_url_exacte_dune_source_est_gardee():
    assert main._lien_verifie("https://exemple-officiel.bj/bourses/2026", SOURCES) == \
        "https://exemple-officiel.bj/bourses/2026"


def test_chemin_invente_sur_un_domaine_reel_est_ramene_a_la_racine():
    """Le cas vicieux : le domaine existe, le chemin est inventé. On ne devine pas, on raccourcit."""
    assert main._lien_verifie("https://exemple-officiel.bj/bourses/inventee-2027", SOURCES) == \
        "https://exemple-officiel.bj"


def test_domaine_totalement_invente_est_supprime():
    assert main._lien_verifie("https://bourse-geniale-2026.com/postuler", SOURCES) == ""


def test_domaine_officiel_connu_accepte_sans_source():
    """Campus France n'est pas dans les sources mais c'est un organisme réel : racine seulement."""
    assert main._lien_verifie("https://www.campusfrance.org/fr/bourse-excellence-2026", SOURCES) == \
        "https://campusfrance.org"


@pytest.mark.parametrize("mauvais", [
    "", "   ", "pas une url", "campusfrance.org", "javascript:alert(1)",
    "ftp://exemple-officiel.bj/fichier", "data:text/html,<script>",
])
def test_entrees_non_http_refusees(mauvais):
    assert main._lien_verifie(mauvais, SOURCES) == ""


def test_ponctuation_collee_par_le_modele_est_nettoyee():
    assert main._lien_verifie("https://autre-source.org/programme.", SOURCES) == \
        "https://autre-source.org/programme"


def test_sans_aucune_source_seuls_les_domaines_officiels_passent():
    assert main._lien_verifie("https://coursera.org/learn/python", []) == "https://coursera.org"
    assert main._lien_verifie("https://formation-miracle.xyz/cours", []) == ""


def test_le_conseil_survit_meme_si_le_lien_est_retire():
    """Retirer un lien douteux ne doit pas faire perdre le contenu utile."""
    assert main._lien_verifie("https://invente.xyz/x", SOURCES) == ""   # lien écarté
    # la fonction ne touche qu'au lien : rien d'autre n'est supprimé côté appelant
    assert main._lien_verifie("https://autre-source.org/programme", SOURCES)


def test_domaines_des_sources_tolere_les_entrees_abimees():
    assert main._domaines_des_sources(None) == set()
    assert main._domaines_des_sources([{}, {"url": ""}, None, {"url": "https://a.bj/x"}]) == {"a.bj"}


# ── Observabilité de la cascade IA (audit A-10) ──
def test_stats_llm_comptent_succes_latence_et_bascules(monkeypatch):
    import importlib, asyncio
    llm = importlib.import_module("llm")
    llm.reset_llm_stats()

    appels = {"n": 0}

    async def faux_openai(prov, model, sysp, usr, temp, maxt, jsonm):
        appels["n"] += 1
        if prov["name"] == "a":
            raise llm._LLMFallback("429 rate limit")      # le 1er bascule
        return '{"ok": true}'                             # le 2e répond

    monkeypatch.setattr(llm, "_LLM_PROVIDERS", [
        {"name": "a", "url": "x", "key": "k", "model": "m", "model_fast": "m", "api": "openai", "max_ctx": 100000},
        {"name": "b", "url": "y", "key": "k", "model": "m", "model_fast": "m", "api": "openai", "max_ctx": 100000},
    ])
    monkeypatch.setattr(llm, "_llm_openai", faux_openai)
    monkeypatch.setattr(llm, "_premium_allowed", lambda: True)
    monkeypatch.setattr(llm, "SMART_LEAD_PROVIDER", "")

    res = asyncio.run(llm.call_groq("sys", "user", json_mode=True))
    assert res == {"ok": True}

    st = {f["fournisseur"]: f for f in llm.llm_stats()["fournisseurs"]}
    assert st["a"]["bascules"] >= 1 and st["a"]["ok"] == 0, "la bascule doit être comptée"
    assert st["b"]["ok"] == 1 and st["b"]["taux_ok"] == 100
    assert st["b"]["latence_moy_ms"] >= 0 and st["b"]["derniere_ok"], "la latence doit être mesurée"
    assert "429" in st["a"]["dernier_echec"], "la cause de la bascule doit être retenue"


def test_json_illisible_est_compte_et_fait_basculer(monkeypatch):
    import importlib, asyncio
    llm = importlib.import_module("llm")
    llm.reset_llm_stats()

    async def faux(prov, model, sysp, usr, temp, maxt, jsonm):
        return "pas du json" if prov["name"] == "a" else '{"ok": 1}'

    monkeypatch.setattr(llm, "_LLM_PROVIDERS", [
        {"name": "a", "url": "x", "key": "k", "model": "m", "model_fast": "m", "api": "openai", "max_ctx": 100000},
        {"name": "b", "url": "y", "key": "k", "model": "m", "model_fast": "m", "api": "openai", "max_ctx": 100000},
    ])
    monkeypatch.setattr(llm, "_llm_openai", faux)
    monkeypatch.setattr(llm, "_premium_allowed", lambda: True)
    monkeypatch.setattr(llm, "SMART_LEAD_PROVIDER", "")

    assert asyncio.run(llm.call_groq("s", "u", json_mode=True)) == {"ok": 1}
    st = {f["fournisseur"]: f for f in llm.llm_stats()["fournisseurs"]}
    assert st["a"]["json_invalide"] == 1, "un JSON illisible doit être compté comme échec du fournisseur"
    assert st["b"]["ok"] == 1, "et on doit avoir basculé sur le suivant"
