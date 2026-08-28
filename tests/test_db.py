"""Tests d'intégration légère du module db.py (SQLite in-memory-ish sur tmp)."""
import os, sys, importlib, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))

def _fresh_db(tmp_path, monkeypatch):
    """Ré-importe db avec un chemin de base temporaire (chaque test isolé)."""
    monkeypatch.setenv("NEXMOVE_DB_PATH", str(tmp_path / "t.db"))
    if "db" in sys.modules:
        del sys.modules["db"]
    return importlib.import_module("db")


def test_session_roundtrip(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    sm = db.SessionManager()
    assert sm.get("u1") is None
    sm.set("u1", {"user_id": "u1", "etape": "ACTIF", "onboarding_complete": True})
    got = sm.get("u1")
    assert got and got["etape"] == "ACTIF"
    assert sm.count() == 1
    active = sm.list_active()
    assert len(active) == 1 and active[0]["user_id"] == "u1"


def test_session_list_active_ignore_non_onboardes(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    sm = db.SessionManager()
    sm.set("u1", {"user_id": "u1", "onboarding_complete": True})
    sm.set("u2", {"user_id": "u2", "onboarding_complete": False})
    ids = [s["user_id"] for s in sm.list_active()]
    assert ids == ["u1"]


def test_opp_store_add_dedup_and_pending(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    store = db.OppStore()
    opp = {"titre": "PhD IA", "url": "https://x/1", "score_composite": 80}
    assert store.add("u1", opp) is True
    assert store.add("u1", opp) is False   # dédup par URL+user
    rows = store.pending("u1", 60)
    assert len(rows) == 1
    store.mark_notified([rows[0][0]])
    assert store.pending("u1", 60) == []


def test_opp_store_user_stats(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    store = db.OppStore()
    for i in range(3):
        store.add("u1", {"titre": f"o{i}", "url": f"https://x/{i}", "score_composite": 70})
    st = store.user_stats("u1")
    assert st["total"] == 3 and st["recent"] == 3


def test_opp_store_candidatures_and_reminders(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    store = db.OppStore()
    store.add_candidature("u1", "Bourse Eiffel", "15/03/2026", "2026-03-15")
    cands = store.list_candidatures("u1")
    assert cands and cands[0][0] == "Bourse Eiffel"
    (cid, uid, cible, diso, sent) = store.all_candidatures()[0]
    store.mark_reminder(cid, 7)
    store.mark_reminder(cid, 3)
    (_, _, _, _, sent2) = store.all_candidatures()[0]
    parts = sorted((sent2 or "").split(","))
    assert "3" in parts and "7" in parts


def test_feedback_delta_bounded(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    store = db.OppStore()
    store._ensure_feedback()
    sig = "emploi|cloud"
    for _ in range(10):    # 10x 👎 => raw score -10 * 8 = -80 => borné à -25
        store.add_feedback("u1", sig, -1)
    assert store.feedback_delta("u1", sig) == -25
    for _ in range(20):
        store.add_feedback("u1", sig, 1)   # revient à +10 => +25 max
    assert store.feedback_delta("u1", sig) == 25


def test_contacts_log(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    store = db.OppStore()
    store._ensure_contacts()
    cid1 = store.add_contact("u1", "aicha", "problème CV", True)
    cid2 = store.add_contact("u2", "koffi", "je veux un rdv", False)
    assert cid1 > 0 and cid2 > cid1
    rows = store.list_contacts(5)
    assert len(rows) == 2
    # le plus récent en premier
    assert rows[0][3] == "je veux un rdv" and rows[0][4] == 0


def test_cache_ttl(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    c = db.Cache()
    c.set("k", {"v": 42}, ttl=60)
    assert c.get("k") == {"v": 42}
    c.set("k2", "x", ttl=-1)   # expiré
    assert c.get("k2") is None


# ------------------ ProfileStore : persistance par identifiant + versions ------------------
def _profil_riche(nom="Judicael"):
    return {"profil": {"identite": {"nom": nom},
                       "formation": [{"diplome": "Master"}, {"diplome": "Licence"}],
                       "experience": [{"poste": "Dev"}],
                       "competences": {"techniques": ["python", "cloud"]},
                       "bilan": {"forces": ["x"]},
                       "preferences": {"objectif": "étudier", "pays_cibles": "France",
                                       "nationalite": "béninoise", "niveau": "professionnel"}}}

def test_profile_save_returns_stable_code(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    ps = db.ProfileStore()
    code1 = ps.save("u1", _profil_riche())
    code2 = ps.save("u1", _profil_riche())
    assert code1.startswith("NEX-") and code1 == code2          # code stable par utilisateur
    assert ps.code_for("u1") == code1

def test_profile_restore_on_new_user(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    ps = db.ProfileStore()
    code = ps.save("telegram-1", _profil_riche("Marie"))
    data = ps.restore(code, "whatsapp-9")                       # portage inter-canaux
    assert data and data["profil"]["identite"]["nom"] == "Marie"
    assert ps.code_for("whatsapp-9") == code

def test_profile_keeps_best_version(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    ps = db.ProfileStore()
    riche = _profil_riche()
    code = ps.save("u1", riche)
    pauvre = {"profil": {"identite": {"nom": "—"}, "preferences": {"objectif": "tous"}}}
    ps.save("u1", pauvre)                                       # version plus pauvre
    best = ps.best(code)
    assert best["profil"]["identite"]["nom"] == "Judicael"      # on garde la meilleure

def test_profile_quality_monotone(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    assert db.profile_quality(_profil_riche()) > db.profile_quality({"profil": {"preferences": {}}})

def test_profile_restore_inconnu_none(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    ps = db.ProfileStore()
    assert ps.restore("NEX-ZZZZZ", "u1") is None
