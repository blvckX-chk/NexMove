"""Droit à l'effacement (RGPD art. 17) — v3.97.

Avant : /supprimer ne vidait que le blob de session. Le profil portable (/moncode), les
candidatures, les messages à l'équipe et les fichiers déposés survivaient, alors que la page
confidentialité promettait « elles sont alors effacées ».

Le test clé est `test_aucune_trace_dans_aucune_table` : il balaie TOUTES les tables et toutes
les colonnes texte de la base. C'est le seul moyen de garantir qu'une table ajoutée plus tard
sans être câblée à l'effacement fera échouer la CI au lieu de passer inaperçue.
"""
import os, sys, json, sqlite3, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")

UID = "user-a-effacer-42"
AUTRE = "user-temoin-99"


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Base neuve + stores repointés dessus, peuplés pour les deux utilisateurs."""
    import importlib
    path = str(tmp_path / "t.db")
    monkeypatch.setenv("NEXMOVE_DB_PATH", path)
    d = importlib.reload(importlib.import_module("db"))
    for s in (d.session_manager, d.opp_store, d.profile_store, d.usage_store,
              d.premium_store, d.credit_store, d.referral_store, d.cache,
              d.link_store, d.recruiter_offer_store):
        s._path = path
    d.opp_store._ensure_feedback(); d.opp_store._ensure_contacts()
    d.opp_store._ensure_broadcasts(); d.opp_store._ensure_misses()

    def peupler(uid):
        d.session_manager.set(uid, {"user_id": uid, "profil": {"identite": {"nom": "Awa"}},
                                    "historique": [{"role": "user", "content": "bonjour"}]})
        d.opp_store.add(uid, {"titre": "Stage data", "url": f"https://x.test/{uid}", "score": 80})
        d.opp_store.add_candidature(uid, "Bourse X")
        d.opp_store.add_feedback(uid, "sig-1", 1)
        d.opp_store.add_contact(uid, "awa", "j'ai un souci", False)
        d.opp_store.add_miss({"uid": uid, "canal": "telegram", "kind": "x", "etape": "ACTIF",
                              "text": "message incompris"})
        d.usage_store.bump(uid, "cv")
        code = d.profile_store.save(uid, {"identite": {"nom": "Awa", "email": "awa@x.test"}})
        d.referral_store.code_for(uid)
        d.recruiter_offer_store.add({"id": uid, "channel": "telegram", "chat_id": "1", "name": "Awa"},
                                    {"titre": "Dev", "entreprise": "ACME"})
        pc = d.premium_store.create_codes("premium", 30, 1, batch="t")[0]
        d.premium_store.redeem(pc, uid)
        cc = d.credit_store.create_codes(5, 1, batch="t")[0]
        d.credit_store.redeem(cc, uid)
        return code, pc, cc

    code, pc, cc = peupler(UID)
    code_autre, _, _ = peupler(AUTRE)
    d.referral_store.attribute(UID, AUTRE)        # UID a été parrainé par AUTRE
    d.referral_store.attribute(AUTRE, UID)        # et UID a parrainé AUTRE
    d._test = {"path": path, "code": code, "code_autre": code_autre, "pc": pc, "cc": cc}
    return d


def _colonnes_texte(path):
    con = sqlite3.connect(path)
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    out = []
    for t in tables:
        for c in con.execute(f"PRAGMA table_info({t})"):
            out.append((t, c[1]))
    con.close()
    return out


def test_aucune_trace_dans_aucune_table(db):
    """Balaie toute la base : après effacement, l'identifiant n'apparaît NULLE PART.

    Une nouvelle table contenant des données personnelles et non câblée à l'effacement
    fera échouer ce test — c'est précisément son rôle.
    """
    path = db._test["path"]
    avant = [(t, c) for t, c in _colonnes_texte(path)
             if sqlite3.connect(path).execute(
                 f"SELECT 1 FROM {t} WHERE CAST({c} AS TEXT) LIKE ? LIMIT 1", (f"%{UID}%",)).fetchone()]
    assert avant, "le jeu de test doit contenir des données de cet utilisateur"

    db.delete_user_data(UID)

    con = sqlite3.connect(path)
    restes = []
    for t, c in _colonnes_texte(path):
        row = con.execute(f"SELECT 1 FROM {t} WHERE CAST({c} AS TEXT) LIKE ? LIMIT 1",
                          (f"%{UID}%",)).fetchone()
        if row:
            restes.append(f"{t}.{c}")
    con.close()
    assert not restes, f"données encore présentes après effacement : {restes}"


def test_le_cv_nest_plus_restaurable_par_son_code(db):
    """Le trou le plus grave : le profil portable (/moncode) survivait à la suppression."""
    code = db._test["code"]
    assert db.profile_store.best(code), "le profil doit exister avant"
    db.delete_user_data(UID)
    assert not db.profile_store.best(code), "le profil portable existe encore"
    # Le vrai scénario : quelqu'un retape /moi <code> pour récupérer le CV.
    assert not db.profile_store.restore(code, "nouveau-user"), \
        "le CV est encore restaurable via /moi <code> après une suppression !"


def test_les_donnees_des_autres_sont_intactes(db):
    db.delete_user_data(UID)
    assert db.session_manager.get(AUTRE), "la session d'un autre utilisateur a été supprimée"
    assert db.profile_store.best(db._test["code_autre"]), "le profil d'un autre a été supprimé"
    con = sqlite3.connect(db._test["path"])
    n = con.execute("SELECT COUNT(*) FROM offres WHERE user_id=?", (AUTRE,)).fetchone()[0]
    con.close()
    assert n == 1


def test_codes_promo_restent_utilises_mais_anonymes(db):
    """Anti-fraude : un code déjà consommé ne doit pas redevenir réutilisable."""
    db.delete_user_data(UID)
    con = sqlite3.connect(db._test["path"])
    for table, code in (("premium_codes", db._test["pc"]), ("credit_codes", db._test["cc"])):
        statut, used_by = con.execute(
            f"SELECT status, used_by FROM {table} WHERE code=?", (code,)).fetchone()
        assert statut == "used", f"{table} : le code est redevenu réutilisable"
        assert used_by == "", f"{table} : l'identifiant est encore là"
    con.close()


def test_parrainage_des_autres_preserve(db):
    db.delete_user_data(UID)
    con = sqlite3.connect(db._test["path"])
    rows = con.execute("SELECT referred_user, referrer_user FROM referrals").fetchall()
    con.close()
    assert (AUTRE, "") in rows, "le parrainage reçu par un autre utilisateur a été perdu"
    assert not any(UID in (a, b) for a, b in rows)


def test_detail_retourne_pour_preuve(db):
    detail = db.delete_user_data(UID)
    for attendu in ("sessions", "offres", "candidatures", "contacts", "profiles"):
        assert detail.get(attendu), f"{attendu} absent du détail : {detail}"


def test_user_id_vide_refuse(db):
    """Un identifiant vide effacerait des lignes au hasard : on refuse."""
    with pytest.raises(ValueError):
        db.delete_user_data("")


def test_second_appel_ne_casse_pas(db):
    db.delete_user_data(UID)
    assert db.delete_user_data(UID) == {}


def test_parcours_complet_supprimer_confirmer(db, monkeypatch, tmp_path):
    """Bout en bout : /supprimer confirmer efface vraiment, et le bot ne ment pas si ça échoue."""
    import asyncio, importlib
    main = importlib.reload(importlib.import_module("main"))
    for s in (main.session_manager, main.opp_store, main.profile_store, main.cache):
        s._path = db._test["path"]
    monkeypatch.setattr(main, "delete_user_data", db.delete_user_data)
    monkeypatch.setattr(main, "_tool_clear", lambda uid: None)

    sess = {"user_id": UID, "chat_id": "1", "username": "Awa", "etape": "ACTIF",
            "profil": {"identite": {"nom": "Awa"}}, "historique": [], "onboarding_complete": True}
    msg, sess = asyncio.run(main.process_text_message(sess, "/supprimer confirmer"))
    assert "fait" in msg.lower()
    assert not sess.get("profil")
    assert not db.profile_store.restore(db._test["code"], "autre"), "le CV survit au parcours réel"


def test_echec_de_suppression_nest_pas_annonce_comme_reussi(db, monkeypatch):
    """Si l'effacement échoue, le bot doit le DIRE — jamais prétendre que c'est fait."""
    import asyncio, importlib
    main = importlib.reload(importlib.import_module("main"))
    def boom(_uid):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(main, "delete_user_data", boom)
    sess = {"user_id": UID, "chat_id": "1", "username": "Awa", "etape": "ACTIF",
            "profil": {"identite": {"nom": "Awa"}}, "historique": [], "onboarding_complete": True}
    msg, sess = asyncio.run(main.process_text_message(sess, "/supprimer confirmer"))
    assert "pas" in msg.lower() and "effac" in msg.lower()
    assert sess.get("profil"), "le profil a été vidé alors que la suppression a échoué"
