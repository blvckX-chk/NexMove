"""Le test d'orientation existe à deux endroits : le bot et la page web.

Ce fichier garantit que les deux ne divergent pas. C'est le vrai risque : quelqu'un
reformule une question dans `api/orientation.py`, oublie de régénérer le fichier web,
et deux personnes obtiennent deux résultats différents au même test.

Il vérifie aussi que la page web parle bien du même test que le bot (nombre de questions,
règle des 2 ou 3 lettres) et que le code transporté par le lien `/start ori_XXX` est validé
et non simplement recopié.
"""
import asyncio
import json
import pathlib
import subprocess
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
import orientation as ori  # noqa: E402

JS = RACINE / "web" / "orientation-data.js"
PAGE = RACINE / "web" / "orientation.html"
GEN = RACINE / "scripts" / "gen-orientation-web.py"


def _data() -> dict:
    """Extrait l'objet JSON de `window.ORIENTATION = {...};`."""
    txt = JS.read_text(encoding="utf-8")
    debut = txt.index("{", txt.index("window.ORIENTATION"))
    return json.loads(txt[debut:txt.rindex("}") + 1])


def test_fichier_genere_a_jour():
    """Si ce test échoue : python3 scripts/gen-orientation-web.py"""
    r = subprocess.run([sys.executable, str(GEN), "--verifier"],
                       capture_output=True, text=True, cwd=RACINE)
    assert r.returncode == 0, r.stdout + r.stderr


def test_memes_questions_que_le_bot():
    d = _data()
    assert len(d["questions"]) == len(ori.TEST_COMPLET)
    assert d["court"] == ori.TEST_COURT
    for web, (q, opts) in zip(d["questions"], ori.TEST_COMPLET):
        assert web["q"] == q
        assert [tuple(o) for o in web["opts"]] == [tuple(o) for o in opts]


def test_memes_metiers_et_lettres():
    d = _data()
    assert set(d["riasec"]) == set(ori.RIASEC)
    for lettre, (nom, desc) in ori.RIASEC.items():
        assert d["riasec"][lettre] == {"nom": nom, "desc": desc}
    for lettre, metiers in ori.METIERS.items():
        assert d["metiers"][lettre] == list(metiers)


def test_aucun_secret_ni_donnee_perso_dans_le_fichier_web():
    """Le fichier est servi publiquement : il ne doit contenir que le test."""
    d = _data()
    assert set(d) == {"riasec", "metiers", "questions", "court"}


def test_page_web_charge_les_donnees_generees():
    html = PAGE.read_text(encoding="utf-8")
    assert 'src="orientation-data.js"' in html
    # Le test est 100 % local : aucune question n'est recopiée dans la page.
    for q, _ in ori.TEST_COMPLET:
        assert q not in html


def test_page_web_ne_collecte_rien():
    """Promesse faite à l'utilisateur sur la page : rien n'est enregistré, aucun e-mail."""
    html = PAGE.read_text(encoding="utf-8")
    for interdit in ("<form", "type=\"email\"", "localStorage", "sessionStorage",
                     "fetch(", "XMLHttpRequest", "navigator.sendBeacon", "document.cookie"):
        assert interdit not in html, interdit


def test_page_web_renvoie_vers_le_bot_avec_le_code():
    html = PAGE.read_text(encoding="utf-8")
    assert "t.me/nex_move_bot" in html
    assert "?start=ori_" in html
    assert "wa.me/22962118761" in html


def test_vitrine_lie_la_page_du_test():
    index = (RACINE / "web" / "index.html").read_text(encoding="utf-8")
    assert 'href="orientation.html"' in index


def _main():
    sys.path.insert(0, str(RACINE / "api"))
    import os
    os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
    import importlib
    return importlib.import_module("main")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_code_du_lien_valide_et_jamais_recopie_tel_quel():
    f = _main()._orient_code_depuis_lien
    assert f("SA") == "SA"
    assert f("sa") == "SA"
    assert f("SAE") == "SAE"
    assert f("SSA") == "SA"             # doublons écrasés
    assert f("S") == ""                 # une seule dominante : on n'invente pas
    assert f("") == ""
    assert f("XYZ") == ""
    assert f("SAEIRC") == ""            # plus long que ce que la page produit : refusé
    # On rejette au lieu de filtrer : sinon « <script> » donnerait le code valide « SCR ».
    assert f("<script>") == ""
    assert f("S' OR 1=1") == ""
    assert f("Social") == ""
    assert f("SA; DROP TABLE") == ""


def test_regle_des_trois_lettres():
    """6 réponses -> 2 lettres ; 12 réponses -> 3 lettres (code Holland classique)."""
    court = [ori.TEST_COMPLET[i][1][0][0] for i in range(ori.TEST_COURT)]
    assert len(ori.score_test(court)) == 2
    longue = [ori.TEST_COMPLET[i][1][0][0] for i in range(len(ori.TEST_COMPLET))]
    assert len(ori.score_test(longue)) == 3


def _sequences() -> list:
    """Séquences de réponses à comparer entre les deux implémentations.

    Les quatre « une seule option à chaque question », des égalités fabriquées pour
    éprouver le départage par ordre d'apparition, et 300 séquences tirées au hasard
    (graine fixe : un échec doit être reproductible).
    """
    import random
    seqs = []
    for opt in range(4):
        for n in (ori.TEST_COURT, len(ori.TEST_COMPLET)):
            seqs.append("".join(ori.TEST_COMPLET[i][1][opt][0] for i in range(n)))
    seqs += ["RI", "IR", "RIAS", "RRII", "IIRR", "RIASEC", "RIASECRIASEC",
             "SSAARRIIEECC", "RIASECRIASE", "AAABBB".replace("B", "S")]
    rnd = random.Random(20261123)
    lettres = list(ori.RIASEC)
    for _ in range(300):
        n = rnd.choice([ori.TEST_COURT, 7, 9, 10, 11, len(ori.TEST_COMPLET)])
        seqs.append("".join(rnd.choice(lettres) for _ in range(n)))
    return seqs


def test_web_et_bot_notent_identiquement():
    """Le vrai risque : deux implémentations du même barème qui divergent en silence.

    On exécute la fonction `score()` extraite de la page (pas une copie) sur les mêmes
    séquences que `ori.score_test`, égalités comprises.
    """
    import shutil
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        import pytest
        pytest.skip("node absent : comparaison web/bot non exécutée")
    seqs = _sequences()
    r = subprocess.run([node, str(RACINE / "tests" / "js_score_harness.js")],
                       input="\n".join(seqs), capture_output=True, text=True, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    web = r.stdout.strip().split("\n")
    assert len(web) == len(seqs)
    for seq, attendu_web in zip(seqs, web):
        assert ori.score_test(list(seq)) == attendu_web, f"divergence sur {seq}"


# ── Le relais : le bot reprend le résultat du web, sans refaire le test ──

def _sess():
    return {"user_id": "u-web-ori", "channel": "telegram", "chat_id": "42", "username": "Test",
            "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}


def test_start_ori_reprend_le_resultat_sans_refaire_le_test():
    m = _main()
    msg, s = _run(m.process_text_message(_sess(), "/start ori_SA"))
    assert s["profil"]["profil_plus"]["orientation"]["riasec"] == "SA"
    assert "Social" in msg and "Artistique" in msg
    assert "orient_test" not in s                      # on ne relance pas le questionnaire
    assert "1 / 6" not in msg and "1/6" not in msg
    assert "/testorientation long" in msg              # pour gagner la 3e dominante
    assert m._orient_active(s)                          # le conseiller sait qu'on parle orientation


def test_start_ori_trois_lettres_ne_propose_pas_la_version_longue():
    m = _main()
    msg, s = _run(m.process_text_message(_sess(), "/start ori_SAE"))
    assert s["profil"]["profil_plus"]["orientation"]["riasec"] == "SAE"
    assert "/testorientation long" not in msg


def test_start_ori_invalide_retombe_sur_l_accueil_sans_inventer_de_profil():
    m = _main()
    for mauvais in ("/start ori_X", "/start ori_S", "/start ori_", "/start ori_<script>"):
        msg, s = _run(m.process_text_message(_sess(), mauvais))
        assert "Bienvenue sur NexMove" in msg
        assert not (s["profil"].get("profil_plus") or {}).get("orientation", {}).get("riasec")
        assert "Ton profil" not in msg and "dominante" not in msg


def test_apres_le_relais_la_suite_reste_en_orientation(monkeypatch):
    """Le piège : `/start` remet la session en « j'attends ton CV ».

    Quelqu'un qui arrive du test d'orientation est souvent lycéen et n'a pas de CV.
    Sa phrase suivante doit aller au conseiller d'orientation, pas à une demande de CV.
    """
    m = _main()

    async def _conseil(system, user, **k):
        return "[conseiller]"
    monkeypatch.setattr(m, "_gen_text", _conseil)

    _, s = _run(m.process_text_message(_sess(), "/start ori_SA"))
    msg, s = _run(m.process_text_message(s, "je suis en terminale D"))
    assert "envoie ton CV" not in msg and "envoie ton *CV*" not in msg
    assert "[conseiller]" in msg


def test_start_ori_marque_la_source_sans_ecraser_une_source_existante():
    m = _main()
    _, s = _run(m.process_text_message(_sess(), "/start ori_SA"))
    assert s["source"] == "web_test_orientation"
    sess = _sess(); sess["source"] = "src_affiche"
    _, s2 = _run(m.process_text_message(sess, "/start ori_SA"))
    assert s2["source"] == "src_affiche"
