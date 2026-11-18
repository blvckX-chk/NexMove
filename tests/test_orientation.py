"""Orientation professionnelle (v3.96) : détection, routage, conversation de conseil, test d'intérêts."""
import os, sys, asyncio, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
import importlib
main = importlib.import_module("main")
ori = importlib.import_module("orientation")


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
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main, "deliver_text", _noop)
    monkeypatch.setattr(main, "deliver_file", _noop)


@pytest.fixture
def llm(monkeypatch):
    """IA simulée : renvoie un conseil d'orientation JSON et garde la trace des appels."""
    calls = []

    async def fake(system, user, **kw):
        calls.append({"system": system, "user": user, **kw})
        if "CONSEILLER D'ORIENTATION" in system and kw.get("json_mode"):
            return {"reponse": "Avec ton bac D et ton goût pour la santé, regarde *soins infirmiers* ou *biologie médicale*. "
                               "Prochaine étape : dis-moi combien d'années d'études tu te vois faire.",
                    "memo": {"interets": ["santé"], "contraintes": ["études courtes"], "pistes": ["soins infirmiers"],
                             "niveau": "inventé par l'IA"}}
        return {"action": "", "argument": "", "message": "Réponse générique."}
    monkeypatch.setattr(main, "call_groq", fake)
    return calls


def _sess(**kw):
    base = {"user_id": "u-ori", "channel": "telegram", "chat_id": "1", "username": "T",
            "etape": "ACTIF", "profil": {}, "historique": [], "onboarding_complete": True}
    base.update(kw)
    return base


# ── Détection ──
@pytest.mark.parametrize("phrase", [
    "je ne sais pas quel métier choisir", "j'ai eu mon bac D, quelle filière choisir ?",
    "quelle formation après le bac pour devenir pilote", "je veux changer de carrière mais je sais pas vers quoi",
    "j'ai raté le concours de l'ENAM, je fais quoi ?", "c'est quoi les débouchés de la sociologie ?",
    "mon père veut que je fasse médecine mais moi j'aime le dessin", "faut-il faire un master ou travailler directement ?",
    "vaut mieux licence pro ou BTS ?", "l'école c'est pas pour moi, je veux un métier manuel",
    "aide moi à choisir entre droit et économie", "quel est le salaire d'un infirmier au Bénin",
    "comment devenir développeur sans diplôme", "mes parents n'ont pas les moyens pour l'université",
    "je suis comptable depuis 10 ans, je veux me reconvertir dans la data", "je veux entreprendre",
])
def test_orientation_detectee(phrase):
    assert main._free_text_to_command(phrase.lower(), phrase).startswith("/orientation ")


@pytest.mark.parametrize("phrase", [
    "je cherche un stage en informatique", "cherche moi une bourse en Allemagne", "je veux un emploi à Cotonou",
    "merci", "mes parents veulent que je rentre tôt", "c'est mieux le pdf ou word ?", "je travaille dans la vente",
])
def test_pas_orientation(phrase):
    assert not ori.is_orientation_query(phrase)


@pytest.mark.parametrize("phrase,interdit", [
    ("je m'appelle Koffi", "/recours"), ("rappelle-moi demain", "/recours"), ("je refuse de payer", "/recours"),
    ("j'appelle ça une arnaque", "/recours"), ("mon visage est rouge", "/visa"),
    ("j'ai fait un stage en banque, ça m'a pas plu", "/mobilite"),
])
def test_faux_positifs_corriges(phrase, interdit):
    assert not main._free_text_to_command(phrase.lower(), phrase).startswith(interdit)


def test_vrais_recours_et_visa_toujours_routes():
    assert main._free_text_to_command("on m'a refusé le visa, je peux contester ?", "x") in ("/visa", "/recours")
    assert main._free_text_to_command("faire un recours contre campus france", "x") == "/recours"
    assert main._free_text_to_command("combien de temps pour le visa", "x") == "/visa"


def test_test_orientation_detecte():
    assert main._free_text_to_command("test d'orientation", "test d'orientation") == "/testorientation"
    assert main._free_text_to_command("je veux faire un test pour savoir ce qui me va",
                                      "je veux faire un test pour savoir ce qui me va") == "/testorientation"


# ── Situation ──
def test_situation():
    assert ori.detect_situation("j'ai eu mon bac D") == {"serie": "D", "niveau": "bachelier"}
    s = ori.detect_situation("je suis comptable depuis 10 ans")
    assert s["niveau"] == "en poste" and s["experience_ans"] == 10 and s["poste"] == "comptable"
    assert ori.detect_situation("je suis en terminale")["niveau"] == "lycée"
    assert ori.detect_situation("je suis en terminale D")["serie"] == "D"
    assert ori.detect_situation("j'ai abandonné en L2")["niveau"] == "études interrompues"
    assert ori.detect_situation("bonjour") == {}


# ── Test d'intérêts ──
def test_test_equilibre_et_scoring():
    for L in ori.RIASEC:
        assert sum(1 for _q, o in ori.TEST_QUESTIONS for l, _ in o if l == L) == 4
    assert ori.score_test(["S", "A", "S", "A", "I", "R"]) == "SA"
    assert ori.score_test(["I", "S", "S", "I"]) == "IS"     # égalité : la première citée gagne
    assert ori.parse_test_answer("2", 0) == "A"
    assert ori.parse_test_answer("b", 0) == "A"
    assert ori.parse_test_answer("dessiner", 0) == "A"
    assert ori.parse_test_answer("bof", 0) is None


def test_parcours_test_complet(llm):
    s = _sess()
    msg, s = _run(main.process_text_message(s, "/testorientation"))
    assert "1/6" in msg and s["orient_test"]["qi"] == 0 and len(s["_kb_options"]) == 4
    for rep in ["3", "4", "2", "3", "4", "1"]:
        msg, s = _run(main.process_text_message(s, rep))
    assert "orient_test" not in s
    code = s["profil"]["profil_plus"]["orientation"]["riasec"]
    assert len(code) == 2 and "Ton profil d'intérêts" in msg
    assert "Familles de métiers" in msg


def test_test_reponse_invalide_courte_redemande(llm):
    s = _sess()
    _, s = _run(main.process_text_message(s, "/testorientation"))
    msg, s = _run(main.process_text_message(s, "bof"))
    assert "1, 2, 3 ou 4" in msg and s["orient_test"]["qi"] == 0


def test_autre_demande_fait_sortir_du_test(llm):
    s = _sess()
    _, s = _run(main.process_text_message(s, "/testorientation"))
    _, s = _run(main.process_text_message(s, "en fait je voudrais plutôt des offres de stage à Cotonou"))
    assert "orient_test" not in s


def test_bouton_du_test(llm, monkeypatch):
    s = _sess()
    _, s = _run(main.process_text_message(s, "/testorientation"))
    s = _run(main.handle_action(s, "ori:0:2"))
    assert s["orient_test"]["qi"] == 1 and s["orient_test"]["answers"] == ["A"]
    s = _run(main.handle_action(s, "ori:0:3"))          # clic périmé : ignoré
    assert s["orient_test"]["qi"] == 1


def test_annuler_arrete_le_test(llm):
    s = _sess()
    _, s = _run(main.process_text_message(s, "/testorientation"))
    msg, s = _run(main.process_text_message(s, "/annuler"))
    assert "orient_test" not in s


# ── Conversation de conseil ──
def test_conseil_memorise_sans_inventer(llm):
    s = _sess()
    msg, s = _run(main.process_text_message(s, "j'ai eu mon bac D, quelle filière choisir ?"))
    assert "soins infirmiers" in msg
    memo = s["profil"]["profil_plus"]["orientation"]
    assert memo["serie"] == "D" and memo["niveau"] == "bachelier"   # le déterministe prime sur l'IA
    assert "santé" in memo["interets"] and "soins infirmiers" in memo["pistes"]
    assert main._orient_active(s)
    sysmsg = next(c["system"] for c in llm if c.get("json_mode") and "CONSEILLER D'ORIENTATION" in c["system"])
    assert "aucun chiffre inventé" in sysmsg


def test_suite_de_conversation_reste_en_orientation(llm):
    s = _sess()
    _, s = _run(main.process_text_message(s, "je ne sais pas quel métier choisir"))
    n = len(llm)
    msg, s = _run(main.process_text_message(s, "et ça dure combien de temps les études ?"))
    assert "CONSEILLER D'ORIENTATION" in llm[n]["system"]   # pas le chat générique
    assert "bac D" in llm[n]["system"] or "CE QUE TU SAIS" in llm[n]["user"]


def test_suite_formation_reste_en_orientation(llm):
    s = _sess()
    _, s = _run(main.process_text_message(s, "je ne sais pas quel métier choisir"))
    assert main._orient_followup(s, "et la formation pour infirmier ?", "et la formation pour infirmier ?")
    assert not main._orient_followup(s, "cherche moi des formations en data", "cherche moi des formations en data")
    assert not main._orient_followup(s, "merci", "merci")


def test_lyceen_sans_cv_pas_de_relance_cv(llm):
    s = _sess(etape="ATTENTE_CV", onboarding_complete=False)
    msg, s = _run(main.process_text_message(s, "je suis en terminale D et je ne sais pas quoi faire après le bac"))
    assert "Envoie ton CV" not in msg and "soins infirmiers" in msg


def test_orientation_vide_invite_et_propose_le_test(llm):
    s = _sess()
    msg, s = _run(main.process_text_message(s, "/orientation"))
    assert "trouver ta voie" in msg and s["_kb_options"][0][1] == "act:ori_test"


def test_memoire_dans_le_contexte_general(llm):
    s = _sess()
    _, s = _run(main.process_text_message(s, "j'ai eu mon bac D, quelle filière choisir ?"))
    ctx = main._conversation_context(s)
    assert "Orientation" in ctx and "bac D" in ctx
