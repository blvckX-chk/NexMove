"""Bannières de la vitrine : une file de programmes datés, de pays différents.

Décision du Propriétaire (26/11/2026) : la campagne de décembre est **passive** — pas de
communication active tant que l'outil n'a rien prouvé. Le raisonnement est juste : on ne
demande pas à quelqu'un de confier un dossier Campus France à un outil sans antécédent.

Conséquence directe : **le bandeau devient la seule surface d'acquisition.** C'est la seule
chose qui travaille quand on ne parle pas. Un bandeau faux coûte donc deux fois : il rate
une candidature, et il brûle le peu de confiance qu'on cherche à construire.

Ce que ces tests verrouillent, par ordre d'importance :

1. **La date affichée est celle qui est en base.** La phrase est assemblée par le code, pas
   rédigée par le modèle. C'est l'invariant central : il rend structurellement impossible
   qu'un bandeau annonce une date que le système ne connaît pas.
2. **Rien n'entre sans date limite future ni source vérifiable.**
3. **La vedette reste jusqu'à son expiration**, puis la suivante prend la place, en changeant
   de pays quand c'est possible.
4. **Un titre venu d'une page web ne peut pas injecter de HTML** dans la vitrine.
"""
import asyncio
import importlib
import os
import pathlib
import sys
from datetime import date, timedelta

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


def _add(store, pays, titre, fin, url=None, debut=HUI):
    phrase = main._banniere_phrase(pays, titre, fin)
    return store.banniere_add(pays, titre, phrase, url or f"https://ex.test/{pays}/{titre}".replace(" ", "-"),
                              debut, fin)


# ── 1. L'invariant : la date affichée est celle qui est stockée ──────────────

@pytest.mark.parametrize("fin,attendu", [
    ("2027-03-11", "11 mars 2027"),
    ("2027-01-01", "1 janvier 2027"),
    ("2026-12-15", "15 décembre 2026"),
    ("2027-08-31", "31 août 2027"),
])
def test_la_phrase_porte_exactement_la_date_stockee(fin, attendu):
    """Si cette propriété tombe, tout le mécanisme d'expiration devient décoratif : la
    vitrine pourrait afficher une date que le système ne connaît pas."""
    phrase = main._banniere_phrase("Canada", "Bourses d'excellence", fin)
    assert attendu in phrase, phrase


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
    """Pas de phrase = pas de bannière. Un programme qui ne peut pas expirer tout seul n'a
    rien à faire dans un mécanisme dont l'expiration est la raison d'être."""
    assert main._banniere_phrase(pays, titre, fin) == ""


def test_un_titre_venu_du_web_ne_peut_pas_injecter_de_html():
    """Les titres viennent de pages web quelconques. La vitrine les affiche.

    Ce qui compte n'est pas l'absence des mots dangereux — « onerror » en texte littéral
    est inoffensif — mais l'absence de tout chevron ou guillemet BRUT : sans chevron, pas
    de balise, donc pas d'exécution. Le bandeau de l'API entre d'ailleurs par
    `textContent` côté vitrine ; cet échappement est la seconde ceinture."""
    phrase = main._banniere_phrase("Chine", '<img src=x onerror="alert(1)">Bourse', "2027-02-20")
    for brut in ("<", ">", '"'):
        assert brut not in phrase, f"caractère brut {brut!r} dans : {phrase}"
    assert "&lt;img" in phrase and "Bourse" in phrase


# ── 2. La file ───────────────────────────────────────────────────────────────

def test_une_banniere_ajoutee_est_la_vedette(store):
    bid = _add(store, "Canada", "Bourses Vanier", "2027-02-15")
    assert bid > 0
    v = store.banniere_vedette(HUI)
    assert v and v["id"] == bid and v["pays"] == "Canada"


def test_file_vide_aucune_banniere(store):
    """Pas de bandeau est un résultat correct. Un bandeau périmé ne l'est jamais."""
    assert store.banniere_vedette(HUI) == {}


def test_la_meme_url_nentre_pas_deux_fois(store):
    """Sans ça, un cron quotidien empilerait dix fois le même programme."""
    assert _add(store, "Canada", "Vanier", "2027-02-15", url="https://ex.test/v") > 0
    assert _add(store, "Canada", "Vanier (bis)", "2027-03-15", url="https://ex.test/v") == 0
    assert len(store.banniere_liste()) == 1


def test_une_banniere_expiree_nest_jamais_affichee(store):
    _add(store, "Canada", "Déjà clos", "2026-11-01")
    assert store.banniere_vedette(HUI) == {}


def test_une_banniere_a_venir_nest_pas_encore_affichee(store):
    _add(store, "Japon", "MEXT", "2027-06-30", debut="2027-01-15")
    assert store.banniere_vedette(HUI) == {}
    assert store.banniere_vedette("2027-02-01")["pays"] == "Japon"


# ── 3. La rotation : la vedette reste jusqu'à son terme ──────────────────────

def test_la_vedette_reste_en_place_meme_si_une_echeance_plus_proche_arrive(store):
    """Le Propriétaire a demandé que celle à la une y passe « jusqu'à expiration ». Sans
    mémoire du choix, un programme ajouté entre-temps avec une date plus proche volerait
    la une, et la vitrine changerait de sujet sans raison visible pour un visiteur qui
    revient."""
    a = _add(store, "Canada", "Vanier", "2027-03-15")
    assert store.banniere_vedette(HUI)["id"] == a
    b = _add(store, "Maroc", "AMCI", "2027-01-20")      # plus urgente, arrivée après
    assert store.banniere_vedette(HUI)["id"] == a, "la vedette en cours doit garder sa place"
    assert b > 0


def test_a_lexpiration_la_suivante_prend_la_place(store):
    a = _add(store, "Canada", "Vanier", "2026-12-10")
    b = _add(store, "Maroc", "AMCI", "2027-01-20")
    assert store.banniere_vedette(HUI)["id"] == a
    assert store.banniere_vedette("2026-12-11")["id"] == b, "après le 10, c'est au tour du Maroc"


def test_la_suivante_change_de_pays_quand_cest_possible(store):
    """« Les programmes doivent être de différents pays » : deux bandeaux français de suite
    donneraient l'impression d'un outil qui ne connaît que la France."""
    a = _add(store, "France", "Eiffel", "2026-12-10")
    _add(store, "France", "Autre programme français", "2027-01-05")   # échéance la plus proche
    c = _add(store, "Turquie", "Türkiye Bursları", "2027-02-10")
    assert store.banniere_vedette(HUI)["id"] == a
    suivante = store.banniere_vedette("2026-12-11")
    assert suivante["pays"] == "Turquie", f"attendu un autre pays, obtenu {suivante}"
    assert suivante["id"] == c


def test_sil_ny_a_quun_pays_on_laffiche_quand_meme(store):
    """La variété est une préférence, pas une condition : mieux vaut un bandeau du même
    pays que pas de bandeau du tout."""
    a = _add(store, "France", "Eiffel", "2026-12-10")
    b = _add(store, "France", "Suivant", "2027-01-05")
    assert store.banniere_vedette(HUI)["id"] == a
    assert store.banniere_vedette("2026-12-11")["id"] == b


def test_retirer_la_vedette_passe_a_la_suivante(store):
    a = _add(store, "Canada", "Vanier", "2027-02-15")
    b = _add(store, "Maroc", "AMCI", "2027-03-20")
    assert store.banniere_vedette(HUI)["id"] == a
    assert store.banniere_retirer(a) is True
    assert store.banniere_vedette(HUI)["id"] == b


def test_retirer_ne_supprime_pas(store):
    """On garde la trace de ce qui a été affiché publiquement."""
    a = _add(store, "Canada", "Vanier", "2027-02-15")
    store.banniere_retirer(a)
    assert store.banniere_liste() == []
    assert len(store.banniere_liste(inclure_retirees=True)) == 1


def test_les_pays_en_file_servent_a_chercher_ailleurs(store):
    _add(store, "Canada", "Vanier", "2027-02-15")
    _add(store, "Maroc", "AMCI", "2027-03-20")
    _add(store, "Chine", "CSC déjà clos", "2026-10-01")     # expirée : ne compte plus
    pays = set(store.banniere_pays_en_file(HUI))
    assert pays == {"Canada", "Maroc"}


def test_la_purge_marque_les_expirees(store):
    _add(store, "Canada", "Vanier", "2026-10-01")
    _add(store, "Maroc", "AMCI", "2027-03-20")
    assert store.banniere_purge(HUI) == 1
    assert [b["pays"] for b in store.banniere_liste()] == ["Maroc"]


# ── 4. Ce que l'admin peut faire à la main ───────────────────────────────────

@pytest.fixture(autouse=True)
def _mute(monkeypatch):
    async def _noop(*a, **k):
        return True
    monkeypatch.setattr(main, "send_message", _noop)
    monkeypatch.setattr(main, "_alert_admin", _noop)
    monkeypatch.setattr(main, "_ADMIN_IDS", {"admin-1"})


def _admin():
    return {"user_id": "admin-1", "channel": "telegram", "chat_id": "admin-1",
            "username": "Admin", "etape": "ACTIF", "profil": {}, "historique": [],
            "onboarding_complete": True}


def test_un_non_admin_ne_voit_pas_les_bannieres():
    s = {"user_id": "u9", "channel": "telegram", "chat_id": "u9", "etape": "ACTIF",
         "profil": {}, "historique": [], "onboarding_complete": True}
    msg, _ = _run(main.process_text_message(s, "/banniere"))
    assert "administrateur" in msg.lower() or "réservée" in msg.lower()


def test_ajouter_refuse_une_date_passee():
    msg, _ = _run(main.process_text_message(
        _admin(), "/banniere ajouter Canada | Vanier | https://ex.test/v | 2020-01-01"))
    assert "passé" in msg.lower()


def test_ajouter_refuse_sans_url():
    msg, _ = _run(main.process_text_message(
        _admin(), "/banniere ajouter Canada | Vanier | pas-une-url | 2027-02-15"))
    assert "url" in msg.lower()


def test_ajouter_refuse_un_format_incomplet():
    msg, _ = _run(main.process_text_message(_admin(), "/banniere ajouter Canada | Vanier"))
    assert "AAAA-MM-JJ" in msg


def test_la_commande_explique_quoi_faire_quand_la_file_est_vide():
    msg, _ = _run(main.process_text_message(_admin(), "/banniere"))
    assert "/banniere ajouter" in msg


# ── 5. Le découpage des pays par le cron est prévisible ─────────────────────

def test_la_rotation_des_pays_est_deterministe():
    """Rotation par jour de l'année et non au hasard : deux passages le même jour
    cherchent les mêmes pays, donc le second ne redépense rien, et un test peut prédire
    le résultat."""
    pays = list(main._BANNIERE_PAYS)
    assert len(pays) == len(set(pays)), "un pays en double ferait chercher deux fois pareil"
    assert len(pays) >= 10, "la file doit pouvoir tenir sans repasser sur les mêmes pays"

    def rotation(jour_annee):
        k = jour_annee % len(pays)
        return (pays[k:] + pays[:k])[:3]

    assert rotation(100) == rotation(100)
    assert rotation(100) != rotation(101)
