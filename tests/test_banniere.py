"""Le bandeau de la vitrine ne doit jamais afficher une échéance passée — et il doit défiler.

Le défaut d'origine (26/11/2026) : le bandeau était écrit en dur et ne portait aucune date.
Il invitait depuis des semaines à « préparer son dossier Campus France » sans que rien ne
sache si la campagne était ouverte. Afficher une échéance après sa date ne fait pas
vieillir une page : ça fait rater une candidature.

Puis la demande du 27/11/2026 : « la bannière ne défile pas avec les programmes actifs de
différents pays » et « annoncer ceux qui viennent pour se préparer tôt ». D'où une rotation,
avec trois types d'entrées : ouvert, bientôt (ouverture officielle connue), à surveiller
(appel attendu, pas encore publié — et donc sans aucune date affichée).

Deux garanties sont testées, et elles traitent deux risques différents :

1. **Le visiteur** ne voit jamais une fenêtre fermée, et voit d'abord l'échéance ouverte la
   plus proche.
2. **Le propriétaire** apprend que la liste s'épuise par un échec de CI, et non par une page
   devenue muette.

La logique testée est celle réellement servie : le harnais l'extrait de `web/index.html` et
l'exécute dans Node.
"""
import json
import pathlib
import re
import shutil
import subprocess
from datetime import date

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
HARNESS = RACINE / "tests" / "js_banniere_harness.js"
INDEX = RACINE / "web" / "index.html"

# Veilles, jours de bascule et lendemains de chaque fenêtre, plus deux dates très
# postérieures pour vérifier qu'on retombe bien sur « aucun bandeau ».
DATES = [
    "2026-10-31", "2026-11-01", "2026-11-26", "2026-11-27", "2026-11-30", "2026-12-01",
    "2026-12-02", "2026-12-15", "2026-12-16", "2026-12-31",
    "2027-01-05", "2027-01-06", "2027-01-17", "2027-01-18", "2027-02-15", "2027-03-11",
    "2027-03-12", "2027-03-15", "2027-03-16", "2027-04-01", "2027-04-02", "2027-09-01",
    "2028-01-01",
]

MOIS = r"(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)"


def _harness():
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        pytest.skip("node absent : logique de bandeau non exécutée")
    r = subprocess.run([node, str(HARNESS), *DATES],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"harnais en échec :\n{r.stderr}"
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def res():
    return _harness()


def _fen(res):
    return {c["id"]: c for c in res["campagnes"]}


# ── 1. Ce que voit le visiteur ───────────────────────────────────────────────

def test_aucune_campagne_ne_s_affiche_hors_de_sa_fenetre(res):
    fen = _fen(res)
    for jour, ids in res["ordre"].items():
        for i in ids:
            c = fen[i]
            assert c["du"] <= jour <= c["au"], (
                f"le {jour}, la rotation contiendrait « {i} » dont la fenêtre est "
                f"{c['du']} → {c['au']}")


def test_quand_aucune_fenetre_n_est_ouverte_il_n_y_a_pas_de_bandeau(res):
    """Pas de bandeau est un résultat correct. Un bandeau périmé ne l'est jamais."""
    fen = _fen(res)
    for jour, choix in res["choix"].items():
        ouverte = any(c["du"] <= jour <= c["au"] for c in fen.values())
        if not ouverte:
            assert choix is None and res["ordre"][jour] == [], jour


def test_tout_ce_qui_est_actif_defile(res):
    """La rotation montre tout ce qui est actif — c'est la demande : « défiler »."""
    fen = _fen(res)
    for jour, ids in res["ordre"].items():
        attendus = {i for i, c in fen.items() if c["du"] <= jour <= c["au"]}
        assert set(ids) == attendus, f"le {jour} : {ids} au lieu de {sorted(attendus)}"


def test_le_premier_affiche_est_l_echeance_ouverte_la_plus_proche(res):
    """Les fenêtres se chevauchent : entretiens jusqu'au 15 mars, vœux jusqu'au 11. La date
    couperet doit passer devant la période qui dure, quel que soit l'ordre d'écriture."""
    fen = _fen(res)
    for jour, choix in res["choix"].items():
        ouverts = [i for i, c in fen.items() if c["du"] <= jour <= c["au"] and c["type"] == "ouvert"]
        if not ouverts:
            continue
        attendu = min(ouverts, key=lambda i: fen[i]["au"])
        assert choix and choix["id"] == attendu, (
            f"le {jour}, parmi {ouverts}, il faut d'abord « {attendu} » "
            f"(échéance {fen[attendu]['au']})")


def test_les_cas_concrets(res):
    """Écrits en clair pour qu'une régression se lise sans réfléchir."""
    assert res["choix"]["2026-11-26"]["id"] == "cf-soumission-1"
    assert res["choix"]["2027-02-15"]["id"] == "parcoursup-voeux"
    # Le 16 décembre : entretiens ouverts, Parcoursup annoncé, Türkiye à surveiller.
    assert res["ordre"]["2026-12-16"][0] == "cf-entretien"
    assert set(res["ordre"]["2026-12-16"]) == {"cf-entretien", "parcoursup-annonce", "tb-surveiller"}


def test_une_annonce_cede_la_place_au_programme_le_jour_de_l_ouverture(res):
    assert "parcoursup-annonce" in res["ordre"]["2027-01-17"]
    assert "parcoursup-annonce" not in res["ordre"]["2027-01-18"]
    assert "parcoursup-voeux" in res["ordre"]["2027-01-18"]


def test_ce_qui_est_a_surveiller_disparait_a_sa_date_de_revision(res):
    """Si l'appel n'est toujours pas publié, l'entrée disparaît au lieu de devenir fausse."""
    assert "tb-surveiller" in res["ordre"]["2027-01-05"]
    assert "tb-surveiller" not in res["ordre"]["2027-01-06"]


def test_les_pays_alternent(res):
    """Glouton : le premier restant d'un autre pays, sinon le premier tout court."""
    assert res["entrelace"] == ["a", "c", "b", "d"]


def test_le_compte_a_rebours_est_juste(res):
    """« Plus que 5 jours » doit être vrai. Un compteur faux est pire qu'absent."""
    assert res["choix"]["2026-11-26"]["jours"] == 5   # jusqu'au 1er décembre
    assert res["choix"]["2026-12-01"]["jours"] == 0   # dernier jour
    assert res["choix"]["2027-03-11"]["jours"] == 0


def test_la_date_du_visiteur_est_locale_et_non_utc(res):
    """Au Bénin (UTC+1), une date calculée en UTC fait expirer le bandeau une heure trop tôt
    chaque soir. Testé à 00h30 locale, où UTC est encore la veille."""
    assert res["iso_local_minuit"] == "2027-01-15"


# ── 2. Cohérence du relevé ───────────────────────────────────────────────────

def test_les_fenetres_sont_coherentes(res):
    ids = [c["id"] for c in res["campagnes"]]
    assert len(ids) == len(set(ids)), f"deux campagnes portent le même id : {ids}"
    for c in res["campagnes"]:
        assert c["du"] <= c["au"], f"« {c['id']} » commence après sa fin"
        assert c["txt"].strip(), f"« {c['id']} » n'a pas de texte"
        assert c["pays"], f"« {c['id']} » n'a pas de pays : la rotation alterne par pays"
        assert c["type"] in ("ouvert", "bientot", "surveiller"), c["id"]


def test_une_annonce_s_arrete_avant_l_ouverture(res):
    """Le jour de l'ouverture, c'est l'entrée « ouvert » qui prend le relais : l'annonce ne
    doit pas dire « bientôt » d'une chose déjà ouverte."""
    for c in res["campagnes"]:
        if c["type"] == "bientot":
            assert c["ouvre"], f"« {c['id']} » est une annonce sans date d'ouverture"
            assert c["ouvre"] > c["au"], f"« {c['id']} » annonce encore après son ouverture"


def test_ce_qui_est_a_surveiller_n_annonce_aucune_date(res):
    """Un appel pas encore publié n'a pas de date officielle. Écrire « ouvre le 10 janvier »
    d'après les années précédentes, ce serait inventer une échéance."""
    for c in res["campagnes"]:
        if c["type"] == "surveiller":
            assert not re.search(r"\b\d{1,2}(er)?\s+" + MOIS, c["txt"], re.I), (
                f"« {c['id']} » annonce une date alors que l'appel n'est pas publié")
            assert not re.search(r"\d{4}-\d{2}-\d{2}", c["txt"])


# ── 3. Ce qu'apprend le propriétaire ─────────────────────────────────────────

def test_la_liste_des_campagnes_n_est_pas_epuisee(res):
    """Le jour où la dernière fenêtre est passée, la vitrine n'a plus de bandeau. Ce n'est pas
    faux, mais c'est muet — et un mécanisme muet s'oublie. La CI le dit."""
    fin = max(c["au"] for c in res["campagnes"])
    assert fin >= date.today().isoformat(), (
        f"toutes les campagnes du bandeau sont passées (la dernière finissait le {fin}).\n"
        "Ajoute les prochaines échéances dans CAMPAGNES (web/index.html), relevées sur la "
        "page officielle de l'organisme — ou par `/banniere ajouter` côté bot.")


def test_il_reste_de_la_marge_avant_que_le_bandeau_ne_se_taise(res):
    """Trois semaines d'avance : de quoi relever les dates officielles sans courir."""
    fin = max(c["au"] for c in res["campagnes"])
    marge = (date.fromisoformat(fin) - date.today()).days
    assert marge >= 21, (
        f"il ne reste que {marge} jour(s) de campagnes dans le bandeau (fin : {fin}).\n"
        "Relève les prochaines échéances sur la page officielle et complète CAMPAGNES "
        "dans web/index.html.")


def test_le_html_ne_contient_aucune_echeance_ecrite_en_dur(res):
    """Si le texte du bandeau revenait dans le HTML statique, tout le mécanisme deviendrait
    décoratif."""
    html = INDEX.read_text(encoding="utf-8")
    bloc = html.split('id="annonce"', 1)[1].split("</div>", 1)[0]
    for mot in ("Campus France", "Parcoursup", "Türkiye", "décembre", "mars", "avril"):
        assert mot not in bloc, (
            f"« {mot} » est écrit en dur dans le bandeau : il survivrait à sa date.")


# ── 4. Accessibilité de la rotation ──────────────────────────────────────────

def test_la_rotation_est_accessible():
    """Un contenu qui change seul doit pouvoir être arrêté (WCAG 2.2.2) et ne pas être
    annoncé en boucle aux lecteurs d'écran."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="annonceSuivant"' in html and 'aria-label="Programme suivant"' in html
    assert 'aria-live="off"' in html, "la rotation automatique ne doit pas être annoncée"
    assert "mouseenter" in html and "focusin" in html, "pause au survol et au focus"
    assert "prefers-reduced-motion: reduce" in html, "pas de rotation automatique si demandé"
    assert ".annonce-suivant{" in html and "height:44px" in html.split(".annonce-suivant{", 1)[1][:400]


def test_le_texte_de_l_api_n_entre_jamais_en_html():
    """Le texte de l'API vient d'un titre de page web : textContent, jamais innerHTML."""
    html = INDEX.read_text(encoding="utf-8")
    assert "html: false" in html and "c.html === false" in html
    assert "txt.textContent = c.txt" in html
