"""Sources d'opportunités LOCALES (Bénin) et lecture des listes sans flux RSS.

L'angle mort du produit : les 16 sources historiques sont **toutes internationales**.
Quelqu'un qui cherchait du travail à Cotonou recevait des bourses pour l'Europe — c'est
exactement ce qu'un testeur a constaté le 25/11 (trois postes Python à Cotonou proposés
à quelqu'un qui avait écrit « tout ce qui peut me faire voyager »).

La plupart des sites d'emploi ouest-africains n'ont pas de flux RSS. Ceux dont la liste est
rendue par le serveur restent lisibles ; ceux qui la construisent en JavaScript ne le sont
pas, et on ne les déclare pas en prétendant le contraire.

Aucun test ici ne touche au réseau : la CI doit rester déterministe.
"""
import asyncio
import os
import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
import main  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Extrait réel de la page de liste, réduit : deux offres, une catégorie, une pagination.
_PAGE = """
<html><body>
<nav><a href="/offres/">Toutes les offres</a><a href="/diffuser-une-offre/">Diffuser</a></nav>
<a href="/offres/categorie/informatique">Informatique</a>
<a href="/offres/?page=2">2</a>
<article><a href="/offres/isao-propose-50-bourses-partielles-de-scolarite-pour-la-rentree-2026-2027/">
  ISAO propose 50 bourses partielles de scolarité pour la rentrée universitaire 2026-2027</a></article>
<article><a href="/offres/goodwork-telecom-recrute-des-commerciaux-terrain-fibre-optique/">
  Goodwork Telecom recrute des commerciaux terrain pour la fibre optique dans 05 villes</a></article>
<article><a href="/offres/isao-propose-50-bourses-partielles-de-scolarite-pour-la-rentree-2026-2027/">
  ISAO propose 50 bourses partielles de scolarité pour la rentrée universitaire 2026-2027</a></article>
</body></html>
"""

_MOTIF = r"/offres/[a-z0-9][a-z0-9-]{12,}/?$"


class _Rep:
    def __init__(self, text, code=200):
        self.status_code = code
        self.text = text


@pytest.fixture
def _page(monkeypatch):
    class _Client:
        async def get(self, url, **k):
            return _Rep(_PAGE)
    monkeypatch.setattr(main, "http", lambda: _Client())


def test_les_offres_sont_extraites_de_la_liste(_page):
    items = _run(main.fetch_html_listing("https://jobsbenin.org/offres/", _MOTIF))
    assert len(items) == 2, [i["titre"] for i in items]
    assert any("50 bourses" in i["titre"] for i in items)
    assert any("Goodwork" in i["titre"] for i in items)


def test_les_url_sont_absolues(_page):
    for it in _run(main.fetch_html_listing("https://jobsbenin.org/offres/", _MOTIF)):
        assert it["url"].startswith("https://jobsbenin.org/offres/"), it["url"]


def test_categories_et_pagination_sont_ecartees(_page):
    """Un lien de catégorie n'est pas une offre : il n'a pas de titre d'offre."""
    urls = [i["url"] for i in _run(main.fetch_html_listing("https://jobsbenin.org/offres/", _MOTIF))]
    assert not any("categorie" in u for u in urls)
    assert not any("page=" in u for u in urls)
    assert not any(u.rstrip("/").endswith("/offres") for u in urls)


def test_un_doublon_nest_compte_quune_fois(_page):
    items = _run(main.fetch_html_listing("https://jobsbenin.org/offres/", _MOTIF))
    assert len({i["url"] for i in items}) == len(items)


def test_une_page_en_erreur_ne_casse_rien(monkeypatch):
    class _Client:
        async def get(self, url, **k):
            return _Rep("", 503)
    monkeypatch.setattr(main, "http", lambda: _Client())
    assert _run(main.fetch_html_listing("https://exemple.org/offres/", _MOTIF)) == []


def test_un_reseau_qui_tombe_ne_casse_rien(monkeypatch):
    class _Client:
        async def get(self, url, **k):
            raise OSError("réseau indisponible")
    monkeypatch.setattr(main, "http", lambda: _Client())
    assert _run(main.fetch_html_listing("https://exemple.org/offres/", _MOTIF)) == []


def test_l_item_a_la_forme_attendue_par_le_stockage(_page):
    """Même forme que fetch_rss, sinon `opp_store.add_source` casse."""
    for it in _run(main.fetch_html_listing("https://jobsbenin.org/offres/", _MOTIF)):
        assert set(it) == {"titre", "url", "resume", "date"}


# ── Le catalogue lui-même ──

def test_le_catalogue_contient_des_sources_locales():
    """Sans source locale, un jeune de Cotonou ne reçoit que des bourses pour l'Europe."""
    locales = [s for s in main.SOURCE_CATALOG if s.get("scope") == "local"]
    assert locales, "aucune source locale : c'est l'angle mort corrigé en v4.16"
    assert any("jobsbenin" in s["url"] for s in locales)
    assert any("novojob.com/benin" in s["url"] for s in locales)


def test_toute_source_html_declare_son_motif():
    """Sans motif, `ingest_feeds` lèverait une KeyError en production."""
    for s in main.SOURCE_CATALOG:
        if s.get("kind") == "html":
            assert s.get("motif"), f"{s['url']} : source html sans motif"


def test_le_catalogue_est_bien_forme():
    for s in main.SOURCE_CATALOG:
        assert s["url"].startswith("https://"), s
        assert s["type"] in ("bourse", "emploi", "fellowship", "ong"), s
        assert s["scope"] in ("local", "intl", "both"), s


def test_une_source_locale_nest_jamais_ecartee_pour_un_objectif_local():
    """La règle existante écarte les sources 100 % internationales ; pas les locales."""
    urls = main._sources_for_profile({"objectif": "travailler"})
    assert any("jobsbenin" in u for u in urls)


def test_les_sources_locales_restent_la_pour_un_objectif_international():
    """Volontairement : jobsbenin.org publie AUSSI du service civique en France et des
    stages à l'étranger. L'écarter ferait perdre de vraies opportunités de mobilité."""
    urls = main._sources_for_profile({"objectif": "étudier", "pays_cibles": "France"})
    assert any("jobsbenin" in u for u in urls)


def test_les_sites_en_javascript_ne_sont_pas_declares():
    """emploisbenin.bj et jobbenin.com construisent leur liste en JS : leur HTML ne contient
    aucun lien d'offre. Les déclarer reviendrait à annoncer des sources muettes."""
    urls = " ".join(s["url"] for s in main.SOURCE_CATALOG)
    for domaine in ("emploisbenin.bj", "jobbenin.com"):
        assert domaine not in urls, (
            f"{domaine} rend ses offres en JavaScript : aucun lecteur côté serveur ne les voit")
