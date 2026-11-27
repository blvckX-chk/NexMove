"""Mesure de la campagne : chaque lien vers le bot dit d'où vient la personne.

Constat du 27/11/2026, en préparant la campagne de décembre : `/start src_…` et `/srcstats`
existaient depuis longtemps, mais **aucun lien de la vitrine ne portait de code de source**.
Après la campagne, on n'aurait pas pu dire combien de personnes étaient venues par le site,
ni par quel bouton — et donc pas décider de ce qu'il faut refaire en janvier.

Ce que ces tests verrouillent :

1. Aucun lien vers le bot, sur aucune page, sans code de source.
2. Chaque emplacement a son propre code : deux boutons identiques (le hero et la fin de page)
   doivent pouvoir être comparés.
3. Les codes respectent ce que Telegram accepte dans un lien profond, sinon le paramètre est
   ignoré en silence.
4. Le bot enregistre bien la source reçue — sinon tout le reste est décoratif.
"""
import asyncio
import os
import pathlib
import re
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
import main  # noqa: E402

WEB = RACINE / "web"
LIEN_BOT = re.compile(r'href="https://t\.me/nex_move_bot(\?[^"]*)?"')
# Telegram : paramètre start de 1 à 64 caractères parmi A-Z a-z 0-9 _ -
CODE_OK = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _pages():
    return sorted(WEB.glob("*.html"))


def test_aucun_lien_vers_le_bot_sans_code_de_source():
    sans = []
    for page in _pages():
        for m in LIEN_BOT.finditer(page.read_text(encoding="utf-8")):
            if not (m.group(1) or "").startswith("?start="):
                sans.append(page.name)
    assert not sans, f"liens vers le bot sans ?start= : {sans}"


def test_les_codes_sont_acceptes_par_telegram_et_suivent_la_convention():
    for page in _pages():
        for m in LIEN_BOT.finditer(page.read_text(encoding="utf-8")):
            code = (m.group(1) or "")[len("?start="):]
            assert CODE_OK.match(code), f"{page.name} : code illisible par Telegram « {code} »"
            assert code.startswith(("src_", "ori_")), f"{page.name} : « {code} » hors convention"


def test_chaque_emplacement_de_l_accueil_a_son_propre_code():
    """Le hero et la fin de page portent le même bouton : sans codes distincts, on ne saurait
    pas lequel des deux fait venir les gens."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    # On lit chaque balise <a> entière : l'ordre des attributs n'a pas à compter.
    balises = re.findall(r'<a\b[^>]*\bjs-start\b[^>]*>', html)
    assert balises, "aucun bouton .js-start trouvé"
    codes = []
    for b in balises:
        m = re.search(r'data-src="([^"]+)"', b)
        assert m, f"bouton .js-start sans data-src : {b[:90]}"
        codes.append(m.group(1))
    assert len(codes) == len(set(codes)), f"codes en double : {codes}"


def test_le_script_reecrit_les_liens_avec_leur_code():
    """Le href est réécrit au chargement (pour suivre data-bot) : la réécriture doit garder
    le code, sinon on retombe sur des liens anonymes."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "url + '?start=' + encodeURIComponent(src)" in html


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _mute(monkeypatch):
    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "send_message", _noop)
    monkeypatch.setattr(main, "_alert_admin", _noop)


@pytest.mark.parametrize("code", ["src_tous_webhero", "src_dec_fb_0312", "src_dec_wa_1212"])
def test_le_bot_enregistre_la_source(code):
    s = {"user_id": f"u-{code}", "channel": "telegram", "chat_id": f"u-{code}",
         "etape": "ACCUEIL", "profil": {}, "historique": []}
    _, s = _run(main.process_text_message(s, f"/start {code}"))
    assert s.get("source") == code


def test_la_premiere_source_n_est_pas_ecrasee():
    """Quelqu'un venu par un post puis revenu par la vitrine reste attribué au post : c'est
    lui qui l'a fait venir la première fois."""
    s = {"user_id": "u-x", "channel": "telegram", "chat_id": "u-x",
         "etape": "ACCUEIL", "profil": {}, "historique": []}
    _, s = _run(main.process_text_message(s, "/start src_dec_fb_0312"))
    _, s = _run(main.process_text_message(s, "/start src_tous_webhero"))
    assert s.get("source") == "src_dec_fb_0312"
