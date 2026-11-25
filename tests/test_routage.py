"""Mesure du routage en langage naturel.

Pourquoi ce fichier existe : le bot route le langage libre avec 218 mots-clés répartis
dans une cascade de 21 branches, et **personne ne savait si ça marchait**. Il n'y avait
aucun chiffre. On ne peut pas améliorer ce qu'on ne mesure pas, et sans mesure chaque
ajout de mot-clé est un pari.

Ce que ça fait :
  - rejoue `tests/jeu_routage.jsonl` à travers la couche déterministe (`_free_text_to_command`) ;
  - imprime le score et la liste des ratés, pour savoir quoi corriger ;
  - **échoue sous un plancher** : le score ne peut donc que monter, jamais redescendre.

Ce que ça ne fait PAS : appeler l'IA. On mesure ici ce qui est gratuit, instantané et
sous notre contrôle. Chaque cas que le déterministe rate part chez le modèle — donc ce
score est aussi une mesure de coût et de latence.

Lancer seul, avec le détail :
    python3 -m pytest tests/test_routage.py -q -s
"""
import json
import os
import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
import main  # noqa: E402

JEU = RACINE / "tests" / "jeu_routage.jsonl"

# Plancher : la part des cas que la couche déterministe doit router correctement.
# On le relève à chaque gain réel — jamais l'inverse : baisser ce nombre pour faire
# passer la CI, c'est se mentir.
#
# ATTENTION À CE QUE CE CHIFFRE VEUT DIRE. Les cas du lot 1 ont été corrigés après
# avoir été écrits : 55 % → 100 %, mais c'est du surapprentissage, pas de la
# compréhension. Le lot 2, écrit ENSUITE sans regarder le routeur, a donné **70 %**
# à la première mesure : voilà le vrai niveau de généralisation.
#
# Le seul score honnête vient de cas que l'auteur du routeur n'a pas écrits.
# D'où la consigne : chaque message vu dans `/misses` devient une ligne du jeu,
# marquée "source": "terrain". Ce sont ces lignes-là qui mesurent quelque chose.
PLANCHER = 0.95

# Un faux routage est pire qu'une absence de routage : dans un cas la personne reçoit
# une réponse hors sujet, dans l'autre le conseiller prend le relais et s'en sort.
PLANCHER_FAUX = 0.10


def _cas() -> list:
    cas = []
    for ligne in JEU.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        d = json.loads(ligne)
        if "msg" in d:
            cas.append(d)
    return cas


def _route(msg: str):
    """Ce que la couche déterministe fait du message, réduit à la commande."""
    cmd = main._free_text_to_command(msg.lower(), msg)
    return cmd.split()[0] if cmd else None


def _evalue():
    bons, faux, muets = [], [], []
    for c in _cas():
        got = _route(c["msg"])
        attendu = c["attendu"]
        if (got in attendu) if attendu else (got is None):
            bons.append(c)
        elif got is None:
            muets.append((c, got))
        else:
            faux.append((c, got))
    return bons, faux, muets


def test_le_jeu_est_lisible_et_fourni():
    cas = _cas()
    assert len(cas) >= 40, "le jeu d'évaluation doit rester représentatif"
    for c in cas:
        assert isinstance(c.get("attendu"), list), c
        assert c.get("source") in ("terrain", "écrit"), c
        for cmd in c["attendu"]:
            assert cmd.startswith("/"), c


def test_score_du_routage_deterministe(capsys):
    bons, faux, muets = _evalue()
    total = len(bons) + len(faux) + len(muets)
    score = len(bons) / total
    with capsys.disabled():
        print(f"\n┌─ Routage déterministe : {len(bons)}/{total} = {score:.0%} "
              f"(plancher {PLANCHER:.0%})")
        print(f"│  {len(faux)} mal routés · {len(muets)} non routés (partent à l'IA)")
        for c, got in faux:
            print(f"│  ✗ FAUX  « {c['msg'][:46]} » → {got}, attendu {c['attendu']}")
        for c, _ in muets:
            print(f"│  · muet  « {c['msg'][:46]} » attendu {c['attendu']}")
        print("└─ chaque ligne ci-dessus est un mot-clé à ajouter ou un cas à traiter\n")
    assert score >= PLANCHER, (
        f"routage déterministe à {score:.0%}, sous le plancher de {PLANCHER:.0%}. "
        "Corrige le routage — ne baisse pas le plancher.")


def test_peu_de_faux_routages():
    """Un message envoyé à la mauvaise commande coûte plus cher qu'un message non routé."""
    bons, faux, muets = _evalue()
    total = len(bons) + len(faux) + len(muets)
    part = len(faux) / total
    assert part <= PLANCHER_FAUX, (
        f"{part:.0%} de faux routages (plafond {PLANCHER_FAUX:.0%}) : "
        + " · ".join(f"« {c['msg'][:40]} » → {got}" for c, got in faux))


def test_une_salutation_ne_declenche_jamais_de_commande():
    for msg in ("bonjour", "salut", "merci", "ok", "bonne journée", "cc"):
        assert _route(msg) is None, msg


@pytest.mark.parametrize("msg", [
    "je galère depuis 2 ans",
    "stp trouve moi quelque chose",
])
def test_les_messages_vagues_vont_au_conseiller(msg):
    """Trop vague pour une commande : c'est au conseiller de demander quoi, pas à un mot-clé."""
    assert _route(msg) is None


# ── Collisions de vocabulaire déjà payées une fois ──

@pytest.mark.parametrize("msg,interdit", [
    ("joindre deux pdf en un seul", "/contact"),      # « joindre » = assembler, pas prendre contact
    ("mon dossier fait 8 mo c'est trop", "/dossier"),  # « dossier » = fichier, pas candidature
    ("je suis où dans mon dossier", "/dossier"),       # la question porte sur l'avancement
    ("mon emploi du temps est chargé", "/mobilite"),   # « emploi » ≠ recherche d'emploi
    ("j'ai fait un stage en banque l'an dernier", "/mobilite"),  # récit passé, pas une demande
])
def test_collisions_de_vocabulaire(msg, interdit):
    assert _route(msg) != interdit, f"« {msg} » repart vers {interdit}"


def test_un_bonjour_nest_pas_un_rate():
    """Sinon le journal se noie sous les salutations et ne mesure plus rien."""
    for m in ("bonjour", "Bonsoir", "merci", "Merci beaucoup", "ok", "d'accord",
              "ça marche", "oui", "non", "super", "à plus", "bye", "👍"):
        assert main._ACQUIT_RE.match(m), m
    for m in ("je cherche un stage", "merci de m'aider à trouver du travail",
              "ok mais comment je fais pour le visa", "bonjour je veux un emploi"):
        assert not main._ACQUIT_RE.match(m), m


def test_un_message_sans_action_est_journalise():
    """LE défaut corrigé : un raté n'était enregistré que si le modèle ne renvoyait RIEN.

    Ça n'arrive presque jamais, donc le journal restait vide et le jeu d'évaluation
    n'avait aucune source de terrain. On journalise maintenant tout message de fond
    auquel aucune action n'a répondu.
    """
    import asyncio
    main._ROUTE_MISSES.clear()
    avant = dict(main._ROUTAGE_VU)

    async def _conv(system, user, **k):
        return {"action": "", "argument": "", "message": "Dis-m'en un peu plus."}
    vrai = main.call_groq
    main.call_groq = _conv
    sess = {"user_id": "u-mes", "channel": "telegram", "chat_id": "u-mes", "etape": "ACTIF",
            "profil": {}, "historique": [], "onboarding_complete": True}
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main.process_text_message(sess, "wesh c'est quoi ce truc deh"))
    finally:
        loop.close()
        main.call_groq = vrai
    assert main._ROUTAGE_VU["vu"] > avant["vu"], "le message de fond doit être compté"
    assert any(r["kind"] == "sans_route" for r in main._ROUTE_MISSES), main._ROUTE_MISSES


def test_le_meme_message_nest_pas_journalise_deux_fois():
    """Quelqu'un qui répète sa phrase ne doit pas remplir le journal à lui seul."""
    import asyncio
    main._ROUTE_MISSES.clear()

    async def _conv(system, user, **k):
        return {"action": "", "argument": "", "message": "Dis-m'en un peu plus."}
    vrai = main.call_groq
    main.call_groq = _conv
    sess = {"user_id": "u-rep", "channel": "telegram", "chat_id": "u-rep", "etape": "ACTIF",
            "profil": {}, "historique": [], "onboarding_complete": True}
    loop = asyncio.new_event_loop()
    try:
        for _ in range(3):
            _, sess = loop.run_until_complete(
                main.process_text_message(sess, "abeg quoi faire maintenant deh"))
    finally:
        loop.close()
        main.call_groq = vrai
    repetes = [r for r in main._ROUTE_MISSES if "abeg quoi faire" in r["text"]]
    assert len(repetes) == 1, f"journalisé {len(repetes)} fois au lieu d'une"


def test_les_compteurs_survivent_a_un_worker_froid():
    """L'API tourne avec 2 workers uvicorn.

    En mémoire, chaque worker ne voyait que la moitié du trafic et `/misses` affichait
    l'un ou l'autre au hasard ; tout repartait à zéro à chaque déploiement. Un taux de
    compréhension qui dépend du worker qui répond ne vaut rien. Les compteurs vivent
    donc en base, partagée par les deux.
    """
    from db import opp_store
    opp_store.reset_counters(["routage_vu", "routage_sans_route", "routage_acquit"])
    main._ROUTAGE_VU.update({"vu": 0, "sans_route": 0, "acquit": 0})
    for _ in range(5):
        main._note_routage("vu")
    main._note_routage("sans_route")
    main._note_routage("acquit")
    # Le worker redémarre (ou c'est l'autre worker qui répond) : la mémoire est vide.
    main._ROUTAGE_VU.update({"vu": 0, "sans_route": 0, "acquit": 0})
    tot = main._routage_totaux()
    assert tot == {"vu": 5, "sans_route": 1, "acquit": 1}, tot


def test_remise_a_zero_garde_le_journal():
    """`/misses reset` remet les compteurs à zéro mais garde les messages : c'est eux
    qui alimentent le jeu d'évaluation."""
    import asyncio
    from db import opp_store
    main._ADMIN_IDS = {"99"}
    main._note_routage("vu")
    main._ROUTE_MISSES.append({"ts": "2026-11-25T09:00:00+00:00", "uid": "u", "canal": "telegram",
                               "kind": "sans_route", "etape": "ACTIF", "text": "un message à garder"})
    opp_store.add_miss(main._ROUTE_MISSES[-1])
    sess = {"user_id": "99", "channel": "telegram", "chat_id": "99", "etape": "ACTIF",
            "profil": {}, "historique": [], "onboarding_complete": True}
    loop = asyncio.new_event_loop()
    try:
        msg, _ = loop.run_until_complete(main.process_text_message(sess, "/misses reset"))
    finally:
        loop.close()
    assert "remis à zéro" in msg
    assert main._routage_totaux()["vu"] == 0
    assert any("un message à garder" in (r.get("text") or "")
               for r in main._misses_recent(40)), "le journal ne doit pas être effacé"


def test_export_des_rates_au_format_du_jeu():
    """`/misses jeu` doit produire des lignes directement collables dans le jeu.

    Sans ce pont, personne ne reporte les ratés du terrain, et le jeu ne contient que
    des cas écrits par celui qui code le routeur — qui mesurent sa mémoire, pas la
    compréhension du bot.
    """
    import asyncio
    import json as _json
    main._ADMIN_IDS = {"99"}
    main._ROUTE_MISSES.append({
        "ts": "2026-11-25T08:10:00+00:00", "uid": "u1", "canal": "telegram",
        "kind": "nlu_fallback", "etape": "ACTIF",
        "text": "je veux un travail qui paye bien mais sans trop d'études"})
    sess = {"user_id": "99", "channel": "telegram", "chat_id": "99", "etape": "ACTIF",
            "profil": {}, "historique": [], "onboarding_complete": True}
    loop = asyncio.new_event_loop()
    try:
        msg, _ = loop.run_until_complete(main.process_text_message(sess, "/misses jeu"))
    finally:
        loop.close()
    lignes = [l for l in msg.split("\n") if l.startswith("{")]
    assert lignes, msg
    for l in lignes:
        d = _json.loads(l)                       # chaque ligne est du JSON valide
        assert d["source"] == "terrain"
        assert d["attendu"] == []                # à remplir à la main, jamais deviné
