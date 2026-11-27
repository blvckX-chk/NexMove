"""Bannières de la vitrine : des programmes ouverts et à venir, de pays différents, en rotation.

Historique de la demande, parce qu'il explique la forme :

- 26/11/2026 — « les programmes à diffuser en bannière doivent être de différents pays,
  ceux à la une vont y passer jusqu'à expiration, ainsi de suite ». Première version
  (v4.19) : une seule vedette, collante jusqu'à sa date limite.
- 27/11/2026 — « la bannière ne défile pas encore avec les programmes actifs de
  différents pays » et « annoncer ceux qui viennent pour se préparer tôt ». Une vedette
  unique ne peut ni défiler ni annoncer. D'où la v4.21 : une ROTATION, où chaque
  programme reste jusqu'à sa date limite — la règle d'origine, appliquée à plusieurs
  programmes à la fois.

Ce que ces tests verrouillent, par ordre d'importance :

1. **La date affichée est celle qui est en base.** La phrase est assemblée par le code, pas
   rédigée par le modèle.
2. **Rien n'est public sans validation quand il vient du cron.** Le 27/11/2026, les
   agrégateurs donnaient la première soumission Campus France au 15 et au 20 novembre ;
   la page officielle disait le 1er décembre. Une URL réelle ne garantit pas une date
   juste.
3. **Chaque programme reste dans la rotation jusqu'à sa date limite, et pas un jour de plus.**
4. **Les pays alternent**, et ce qui est ouvert passe avant ce qui est annoncé.
5. **Un titre venu d'une page web ne peut pas injecter de HTML** dans la vitrine.
"""
import asyncio
import importlib
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


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Un magasin de bannières isolé par test."""
    monkeypatch.setenv("NEXMOVE_DB_PATH", str(tmp_path / "b.db"))
    if "db" in sys.modules:
        del sys.modules["db"]
    db = importlib.import_module("db")
    s = db.OppStore()
    s._ensure_bannieres()
    return s


HUI = "2026-12-01"


def _add(store, pays, titre, fin, url=None, debut=HUI, ouverture="", statut="publiee"):
    phrase = main._banniere_phrase(pays, titre, fin, ouverture)
    return store.banniere_add(pays, titre, phrase,
                              url or f"https://ex.test/{pays}/{titre}".replace(" ", "-"),
                              debut, fin, ouverture=ouverture, statut=statut)


def _ids(liste):
    return [b["id"] for b in liste]


# ── 1. L'invariant : la date affichée est celle qui est stockée ──────────────

@pytest.mark.parametrize("fin,attendu", [
    ("2027-03-11", "11 mars 2027"),
    ("2027-01-01", "1 janvier 2027"),
    ("2026-12-15", "15 décembre 2026"),
    ("2027-08-31", "31 août 2027"),
])
def test_la_phrase_porte_exactement_la_date_stockee(fin, attendu):
    """Si cette propriété tombe, tout le mécanisme d'expiration devient décoratif."""
    phrase = main._banniere_phrase("Canada", "Bourses d'excellence", fin)
    assert attendu in phrase, phrase


def test_une_annonce_porte_les_deux_dates():
    """Un programme à venir annonce sa fenêtre complète. La phrase reste vraie avant comme
    après l'ouverture : la même entrée sert d'annonce, puis de rappel."""
    phrase = main._banniere_phrase("Turquie", "Türkiye Bursları", "2027-02-20", "2027-01-10")
    assert "10 janvier 2027" in phrase and "20 février 2027" in phrase
    assert "Prépare" in phrase


def test_une_ouverture_apres_la_cloture_est_refusee():
    assert main._banniere_phrase("Turquie", "X", "2027-01-10", "2027-02-20") == ""


def test_une_ouverture_illisible_est_refusee():
    assert main._banniere_phrase("Turquie", "X", "2027-02-20", "janvier") == ""


def test_la_phrase_nomme_le_pays_et_le_programme():
    phrase = main._banniere_phrase("Maroc", "Bourses AMCI", "2027-02-20")
    assert "Maroc" in phrase and "AMCI" in phrase


@pytest.mark.parametrize("pays,titre,fin", [
    ("", "Programme", "2027-02-20"),
    ("Canada", "", "2027-02-20"),
    ("Canada", "Programme", ""),
    ("Canada", "Programme", "bientôt"),
    ("Canada", "Programme", "2027-13-45"),
])
def test_sans_date_lisible_il_ny_a_pas_de_phrase(pays, titre, fin):
    """Pas de phrase = pas de bannière. Un programme qui ne peut pas expirer seul n'a rien à
    faire dans un mécanisme dont l'expiration est la raison d'être."""
    assert main._banniere_phrase(pays, titre, fin) == ""


def test_un_titre_venu_du_web_ne_peut_pas_injecter_de_html():
    """Ce qui compte : aucun chevron ni guillemet BRUT. « onerror » en texte littéral est
    inoffensif. Le texte de l'API entre d'ailleurs par textContent côté vitrine ; cet
    échappement est la seconde ceinture."""
    phrase = main._banniere_phrase("Chine", '<img src=x onerror="alert(1)">Bourse', "2027-02-20")
    for brut in ("<", ">", '"'):
        assert brut not in phrase, f"caractère brut {brut!r} dans : {phrase}"
    assert "&lt;img" in phrase and "Bourse" in phrase


# ── 2. Validation : rien de public sans geste humain quand ça vient du cron ──

def test_un_programme_a_valider_nest_jamais_public(store):
    _add(store, "Égypte", "E-JUST", "2027-01-10", statut="a_valider")
    assert store.banniere_actives(HUI) == []
    assert store.banniere_vedette(HUI) == {}


def test_valider_rend_public(store):
    bid = _add(store, "Égypte", "E-JUST", "2027-01-10", statut="a_valider")
    assert store.banniere_valider(bid) is True
    assert _ids(store.banniere_actives(HUI)) == [bid]


def test_un_statut_inconnu_ne_publie_pas(store):
    """Dans le doute, on ne publie pas."""
    _add(store, "Égypte", "E-JUST", "2027-01-10", statut="publier-svp")
    assert store.banniere_actives(HUI) == []


def test_le_cron_depose_en_attente_de_validation(store, monkeypatch):
    """Le chemin réel du cron : ce qu'il trouve n'entre pas dans la rotation."""
    monkeypatch.setattr(main, "opp_store", store)
    monkeypatch.setattr(main, "BANNIERE_VALIDATION", True)

    async def _trouve(pays, today):
        return [{"pays": pays, "titre": f"Programme {pays}",
                 "texte": main._banniere_phrase(pays, f"Programme {pays}", "2027-02-15"),
                 "url": f"https://ex.test/{pays}", "debut": today.isoformat(),
                 "fin": "2027-02-15", "ouverture": ""}]

    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "_banniere_decouvrir", _trouve)
    monkeypatch.setattr(main, "_alert_admin", _noop)
    r = _run(main._banniere_rafraichir())
    assert r["ajoutees"] == 3 and r["a_valider"] is True
    assert all(b["statut"] == "a_valider" for b in store.banniere_liste())
    assert store.banniere_actives(HUI) == [], "rien ne doit être public avant validation"


def test_sans_validation_le_cron_publie_directement(store, monkeypatch):
    """Désactivable, pour qui accepte le risque des agrégateurs."""
    monkeypatch.setattr(main, "opp_store", store)
    monkeypatch.setattr(main, "BANNIERE_VALIDATION", False)

    async def _trouve(pays, today):
        return [{"pays": pays, "titre": "P", "texte": main._banniere_phrase(pays, "P", "2027-02-15"),
                 "url": f"https://ex.test/{pays}", "debut": today.isoformat(),
                 "fin": "2027-02-15", "ouverture": ""}]

    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "_banniere_decouvrir", _trouve)
    monkeypatch.setattr(main, "_alert_admin", _noop)
    _run(main._banniere_rafraichir())
    assert all(b["statut"] == "publiee" for b in store.banniere_liste())


# ── 3. La rotation ────────────────────────────────────────────────────────────

def test_file_vide_aucune_banniere(store):
    """Pas de bandeau est un résultat correct. Un bandeau périmé ne l'est jamais."""
    assert store.banniere_actives(HUI) == []


def test_la_meme_url_nentre_pas_deux_fois(store):
    """Sans ça, un cron empilerait dix fois le même programme."""
    assert _add(store, "Canada", "Vanier", "2027-02-15", url="https://ex.test/v") > 0
    assert _add(store, "Canada", "Vanier (bis)", "2027-03-15", url="https://ex.test/v") == 0
    assert len(store.banniere_liste()) == 1


def test_un_programme_reste_dans_la_rotation_jusqu_a_sa_date_limite(store):
    """La règle du 26/11 — « à la une jusqu'à expiration » — vaut pour chaque programme."""
    bid = _add(store, "Canada", "Vanier", "2026-12-10")
    assert bid in _ids(store.banniere_actives("2026-12-01"))
    assert bid in _ids(store.banniere_actives("2026-12-10")), "le dernier jour compte"
    assert bid not in _ids(store.banniere_actives("2026-12-11")), "et pas un jour de plus"


def test_un_programme_plus_urgent_rejoint_la_rotation_sans_en_chasser(store):
    """Dans l'ancien modèle à vedette unique, il fallait choisir. Dans une rotation, un
    nouveau programme s'ajoute : personne ne perd sa place avant sa date limite."""
    a = _add(store, "Canada", "Vanier", "2027-03-15")
    b = _add(store, "Maroc", "AMCI", "2027-01-20")
    ids = _ids(store.banniere_actives(HUI))
    assert a in ids and b in ids
    assert ids.index(b) < ids.index(a), "l'échéance la plus proche passe en tête"


def test_les_pays_alternent_dans_la_rotation(store):
    """« Des programmes de différents pays » : deux bandeaux français de suite donneraient
    l'impression d'un outil qui ne connaît que la France."""
    _add(store, "France", "A", "2026-12-10")
    _add(store, "France", "B", "2026-12-12")
    _add(store, "Turquie", "C", "2027-02-10")
    pays = [b["pays"] for b in store.banniere_actives(HUI)]
    assert pays == ["France", "Turquie", "France"], pays


def test_sil_ny_a_quun_pays_on_laffiche_quand_meme(store):
    """La variété est une préférence, pas une condition."""
    _add(store, "France", "A", "2026-12-10")
    _add(store, "France", "B", "2027-01-05")
    assert len(store.banniere_actives(HUI)) == 2


def test_une_banniere_expiree_nest_jamais_affichee(store):
    _add(store, "Canada", "Déjà clos", "2026-11-01")
    assert store.banniere_actives(HUI) == []


def test_ce_qui_est_ouvert_passe_avant_ce_qui_est_annonce(store):
    venir = _add(store, "Turquie", "Türkiye Bursları", "2027-02-20", ouverture="2027-01-10")
    ouvert = _add(store, "Maroc", "AMCI", "2027-03-01")
    actives = store.banniere_actives(HUI)
    assert _ids(actives) == [ouvert, venir]
    assert actives[0]["etat"] == "ouvert" and actives[1]["etat"] == "bientot"


def test_une_annonce_trop_lointaine_attend_son_tour(store):
    """Annoncer six mois à l'avance n'aide personne et encombre la rotation : on annonce
    dans un horizon de 60 jours."""
    bid = _add(store, "Japon", "MEXT", "2027-06-30", ouverture="2027-04-15")
    assert bid not in _ids(store.banniere_actives(HUI))
    assert bid in _ids(store.banniere_actives("2027-03-01"))


def test_une_annonce_devient_un_programme_ouvert_le_jour_venu(store):
    bid = _add(store, "Turquie", "Türkiye Bursları", "2027-02-20", ouverture="2027-01-10")
    assert store.banniere_actives("2027-01-09")[0]["etat"] == "bientot"
    assert store.banniere_actives("2027-01-10")[0]["etat"] == "ouvert"
    assert store.banniere_actives("2027-01-10")[0]["id"] == bid


def test_la_rotation_est_plafonnee(store):
    for i in range(10):
        _add(store, f"Pays{i}", f"P{i}", "2027-02-01")
    assert len(store.banniere_actives(HUI)) == 6


def test_retirer_sort_de_la_rotation(store):
    a = _add(store, "Canada", "Vanier", "2027-02-15")
    b = _add(store, "Maroc", "AMCI", "2027-03-20")
    assert store.banniere_retirer(a) is True
    assert _ids(store.banniere_actives(HUI)) == [b]


def test_retirer_ne_supprime_pas(store):
    """On garde la trace de ce qui a été affiché publiquement."""
    a = _add(store, "Canada", "Vanier", "2027-02-15")
    store.banniere_retirer(a)
    assert store.banniere_liste() == []
    assert len(store.banniere_liste(inclure_retirees=True)) == 1


def test_les_pays_en_file_comptent_aussi_ceux_a_valider(store):
    """Sinon le cron reproposerait chaque jour un pays qui attend déjà une validation."""
    _add(store, "Canada", "Vanier", "2027-02-15")
    _add(store, "Égypte", "E-JUST", "2027-01-10", statut="a_valider")
    _add(store, "Chine", "CSC déjà clos", "2026-10-01")
    assert set(store.banniere_pays_en_file(HUI)) == {"Canada", "Égypte"}


def test_la_purge_marque_les_expirees(store):
    _add(store, "Canada", "Vanier", "2026-10-01")
    _add(store, "Maroc", "AMCI", "2027-03-20")
    assert store.banniere_purge(HUI) == 1
    assert [b["pays"] for b in store.banniere_liste()] == ["Maroc"]


def test_une_base_v419_se_migre_sans_perte(tmp_path, monkeypatch):
    """La table existe déjà en production, sans les colonnes ouverture et statut. Les
    bannières déjà présentes doivent rester publiques après la mise à jour."""
    import sqlite3
    chemin = tmp_path / "ancienne.db"
    con = sqlite3.connect(chemin)
    con.execute("""CREATE TABLE bannieres (id INTEGER PRIMARY KEY AUTOINCREMENT,
        pays TEXT NOT NULL, titre TEXT NOT NULL, texte TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
        debut TEXT NOT NULL, fin TEXT NOT NULL, vedette INTEGER DEFAULT 0,
        retiree INTEGER DEFAULT 0, origine TEXT DEFAULT 'cron', created_at TEXT)""")
    con.execute("INSERT INTO bannieres(pays,titre,texte,url,debut,fin) VALUES"
                "('Canada','Vanier','Canada · Vanier','https://ex.test/v','2026-11-20','2027-02-15')")
    con.commit(); con.close()
    monkeypatch.setenv("NEXMOVE_DB_PATH", str(chemin))
    if "db" in sys.modules:
        del sys.modules["db"]
    db = importlib.import_module("db")
    s = db.OppStore()
    s._ensure_bannieres()
    s._ensure_bannieres()          # deux fois : la migration doit être idempotente
    actives = s.banniere_actives(HUI)
    assert len(actives) == 1 and actives[0]["statut"] == "publiee"


# ── 4. L'API publique ─────────────────────────────────────────────────────────

class _Rep:
    def __init__(self):
        self.headers = {}


def test_l_api_renvoie_la_liste_et_les_champs_de_compatibilite(store, monkeypatch):
    """La vitrine 4.20 lit un seul programme à la racine ; la 4.21 lit `items`. L'API et la
    vitrine ne sont pas déployées au même moment : les deux ordres doivent marcher."""
    monkeypatch.setattr(main, "opp_store", store)
    import datetime as _dt
    hui = _dt.datetime.now(_dt.timezone.utc).date()
    fin = (hui + _dt.timedelta(days=40)).isoformat()
    _add(store, "Maroc", "AMCI", fin, debut=hui.isoformat())
    r = _run(main.api_banniere(_Rep()))
    assert r["items"] and r["items"][0]["pays"] == "Maroc"
    assert r["texte"] == r["items"][0]["texte"] and r["fin"] == fin
    assert r["items"][0]["etat"] == "ouvert"


def test_l_api_renvoie_un_objet_vide_quand_rien_n_est_ouvert(store, monkeypatch):
    monkeypatch.setattr(main, "opp_store", store)
    assert _run(main.api_banniere(_Rep())) == {}


# ── 5. Ce que l'admin peut faire depuis Telegram ─────────────────────────────

@pytest.fixture
def admin(monkeypatch, store):
    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "send_message", _noop)
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main, "_ADMIN_IDS", {"admin-1"})
    monkeypatch.setattr(main, "opp_store", store)
    return {"user_id": "admin-1", "channel": "telegram", "chat_id": "admin-1",
            "username": "Admin", "etape": "ACTIF", "profil": {}, "historique": [],
            "onboarding_complete": True}


def test_un_non_admin_ne_voit_pas_les_bannieres():
    s = {"user_id": "u9", "channel": "telegram", "chat_id": "u9", "etape": "ACTIF",
         "profil": {}, "historique": [], "onboarding_complete": True}
    msg, _ = _run(main.process_text_message(s, "/banniere"))
    assert "administrateur" in msg.lower() or "réservée" in msg.lower()


def test_ajouter_refuse_une_date_passee(admin):
    msg, _ = _run(main.process_text_message(
        admin, "/banniere ajouter Canada | Vanier | https://ex.test/v | 2020-01-01"))
    assert "passé" in msg.lower()


def test_ajouter_refuse_sans_url(admin):
    msg, _ = _run(main.process_text_message(
        admin, "/banniere ajouter Canada | Vanier | pas-une-url | 2027-02-15"))
    assert "url" in msg.lower()


def test_ajouter_refuse_un_format_incomplet(admin):
    msg, _ = _run(main.process_text_message(admin, "/banniere ajouter Canada | Vanier"))
    assert "AAAA-MM-JJ" in msg


def test_ajouter_avec_ouverture_publie_une_annonce(admin, store):
    msg, _ = _run(main.process_text_message(
        admin, "/banniere ajouter Turquie | Türkiye Bursları | https://ex.test/tb | 2027-02-20 | 2027-01-10"))
    assert "publiée" in msg
    b = store.banniere_liste()[0]
    assert b["ouverture"] == "2027-01-10" and b["statut"] == "publiee"


def test_ce_que_l_admin_ajoute_est_publie_directement(admin, store):
    """Le Propriétaire vérifie une source mieux qu'un cron."""
    _run(main.process_text_message(
        admin, "/banniere ajouter Maroc | AMCI | https://ex.test/amci | 2027-03-01"))
    assert store.banniere_liste()[0]["statut"] == "publiee"


def test_valider_depuis_telegram(admin, store):
    bid = _add(store, "Égypte", "E-JUST", "2027-01-10", statut="a_valider")
    msg, _ = _run(main.process_text_message(admin, f"/banniere valider {bid}"))
    assert "publiée" in msg
    assert store.banniere_liste()[0]["statut"] == "publiee"


def test_rafraichir_dit_ce_qui_a_ete_cherche_meme_quand_rien_n_est_trouve(admin, monkeypatch):
    """C'était le manque du 27/11 : une file vide ne disait pas si le cron avait tourné."""
    async def _rien(pays, today):
        return []
    monkeypatch.setattr(main, "_banniere_decouvrir", _rien)
    msg, _ = _run(main.process_text_message(admin, "/banniere rafraichir"))
    assert "rien de vérifiable" in msg.lower()
    assert any(p in msg for p in main._BANNIERE_PAYS), "il faut nommer les pays cherchés"


def test_la_liste_distingue_ce_qui_attend_une_validation(admin, store):
    _add(store, "Égypte", "E-JUST", "2027-01-10", statut="a_valider")
    msg, _ = _run(main.process_text_message(admin, "/banniere"))
    assert "à valider" in msg


def test_la_commande_explique_quoi_faire_quand_la_file_est_vide(admin):
    msg, _ = _run(main.process_text_message(admin, "/banniere"))
    assert "/banniere rafraichir" in msg and "/banniere ajouter" in msg


# ── 6. Le découpage des pays par le cron est prévisible ─────────────────────

def test_la_rotation_des_pays_est_deterministe():
    """Par jour de l'année et non au hasard : deux passages le même jour cherchent les
    mêmes pays, donc le second ne redépense rien, et un test peut prédire le résultat."""
    pays = list(main._BANNIERE_PAYS)
    assert len(pays) == len(set(pays)), "un pays en double ferait chercher deux fois pareil"
    assert len(pays) >= 10

    def rotation(jour_annee):
        k = jour_annee % len(pays)
        return (pays[k:] + pays[:k])[:3]

    assert rotation(100) == rotation(100)
    assert rotation(100) != rotation(101)
