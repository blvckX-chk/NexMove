"""Le bandeau de la vitrine ne doit jamais afficher une échéance passée.

Le défaut d'origine (constaté le 26/11/2026) : le bandeau était écrit en dur et ne
portait aucune date. Il invitait depuis des semaines à « préparer son dossier Campus
France » sans que rien, dans le système, ne sache si la campagne était encore ouverte.
Afficher une échéance après sa date ne fait pas vieillir une page : ça fait rater une
candidature à quelqu'un.

Deux garanties sont testées ici, et elles traitent deux risques différents :

1. **Le visiteur** ne voit jamais une fenêtre fermée — c'est le rôle de
   `choisirCampagne`, vérifiée sur les veilles et lendemains de chaque bascule.
2. **Le propriétaire** apprend que la liste s'épuise par un échec de CI, et non par
   une page devenue muette. Un mécanisme qui se tait quand il n'a plus rien à dire
   est un mécanisme dont on oublie l'existence.

Les dates de la liste viennent des pages officielles de Campus France Bénin ; ce
fichier ne les revérifie pas (il faudrait le réseau), il vérifie leur *cohérence* et
leur *fraîcheur*.
"""
import json
import pathlib
import shutil
import subprocess
from datetime import date, timedelta

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
HARNESS = RACINE / "tests" / "js_banniere_harness.js"
INDEX = RACINE / "web" / "index.html"

# Veilles, jours de bascule et lendemains de chaque fenêtre, plus deux dates très
# postérieures pour vérifier qu'on retombe bien sur « aucun bandeau ».
DATES = [
    "2026-10-31", "2026-11-01", "2026-11-26", "2026-11-30", "2026-12-01",
    "2026-12-02", "2026-12-15", "2026-12-16", "2026-12-31",
    "2027-01-17", "2027-01-18", "2027-02-15", "2027-03-11", "2027-03-12",
    "2027-03-15", "2027-03-16", "2027-04-01", "2027-04-02", "2027-09-01",
    "2028-01-01",
]


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


# ── 1. Ce que voit le visiteur ───────────────────────────────────────────────

def test_aucune_campagne_ne_s_affiche_hors_de_sa_fenetre(res):
    fenetres = {c["id"]: (c["du"], c["au"]) for c in res["campagnes"]}
    for jour, choix in res["choix"].items():
        if choix is None:
            continue
        du, au = fenetres[choix["id"]]
        assert du <= jour <= au, (
            f"le {jour}, le bandeau montrerait « {choix['id'] } » "
            f"dont la fenêtre est {du} → {au}")


def test_quand_aucune_fenetre_n_est_ouverte_il_n_y_a_pas_de_bandeau(res):
    """Pas de bandeau est un résultat correct. Un bandeau périmé ne l'est jamais."""
    fenetres = [(c["du"], c["au"]) for c in res["campagnes"]]
    for jour, choix in res["choix"].items():
        ouverte = any(du <= jour <= au for du, au in fenetres)
        if not ouverte:
            assert choix is None, f"le {jour} aucune campagne n'est ouverte, pourtant {choix}"


def test_c_est_l_echeance_la_plus_proche_qui_gagne(res):
    """Les fenêtres se chevauchent : entretiens jusqu'au 15 mars, vœux jusqu'au 11.
    La date couperet doit passer devant la période qui dure, quel que soit l'ordre
    dans lequel les lignes sont écrites."""
    fenetres = {c["id"]: (c["du"], c["au"]) for c in res["campagnes"]}
    for jour, choix in res["choix"].items():
        ouvertes = [i for i, (du, au) in fenetres.items() if du <= jour <= au]
        if not ouvertes:
            continue
        attendu = min(ouvertes, key=lambda i: fenetres[i][1])
        assert choix and choix["id"] == attendu, (
            f"le {jour}, parmi {ouvertes}, il faut montrer « {attendu} » "
            f"(échéance {fenetres[attendu][1]})")


def test_le_chevauchement_parcoursup_est_bien_celui_qu_on_attend(res):
    """Cas concret, écrit en clair pour qu'une régression se lise sans réfléchir :
    le 15 février 2027, entretiens Campus France et vœux Parcoursup sont tous deux
    ouverts, et c'est Parcoursup (11 mars) qu'il faut annoncer."""
    assert res["choix"]["2027-02-15"]["id"] == "parcoursup-voeux"
    assert res["choix"]["2026-11-26"]["id"] == "cf-soumission-1"


def test_le_compte_a_rebours_est_juste(res):
    """« Plus que 5 jours » doit être vrai. Un compteur faux est pire qu'absent."""
    assert res["choix"]["2026-11-26"]["jours"] == 5   # jusqu'au 1er décembre
    assert res["choix"]["2026-12-01"]["jours"] == 0   # dernier jour
    assert res["choix"]["2027-03-11"]["jours"] == 0


def test_la_date_du_visiteur_est_locale_et_non_utc(res):
    """Au Bénin (UTC+1), une date calculée en UTC fait expirer le bandeau une heure
    trop tôt chaque soir. Testé à 00h30 locale, où UTC est encore la veille."""
    assert res["iso_local_minuit"] == "2027-01-15"


# ── 2. Ce qu'apprend le propriétaire ─────────────────────────────────────────

def test_les_fenetres_sont_coherentes(res):
    ids = [c["id"] for c in res["campagnes"]]
    assert len(ids) == len(set(ids)), f"deux campagnes portent le même id : {ids}"
    for c in res["campagnes"]:
        assert c["du"] <= c["au"], f"« {c['id']} » commence après sa fin"
        assert c["txt"].strip(), f"« {c['id'] } » n'a pas de texte"


def test_la_liste_des_campagnes_n_est_pas_epuisee(res):
    """Le jour où la dernière fenêtre est passée, la vitrine n'a plus de bandeau.
    Ce n'est pas faux, mais c'est muet — et un mécanisme muet s'oublie. La CI le dit."""
    fin = max(c["au"] for c in res["campagnes"])
    assert fin >= date.today().isoformat(), (
        f"toutes les campagnes du bandeau sont passées (la dernière finissait le {fin}).\n"
        "Ajoute les prochaines échéances dans CAMPAGNES (web/index.html), relevées sur "
        "benin.campusfrance.org — ou retire la liste si la campagne est terminée.")


def test_il_reste_de_la_marge_avant_que_le_bandeau_ne_se_taise(res):
    """Trois semaines d'avance : de quoi relever les dates officielles sans courir.
    Échouer en avance est le seul moyen d'être prévenu AVANT que la vitrine se taise."""
    fin = max(c["au"] for c in res["campagnes"])
    marge = (date.fromisoformat(fin) - date.today()).days
    assert marge >= 21, (
        f"il ne reste que {marge} jour(s) de campagnes dans le bandeau (fin : {fin}).\n"
        "Relève les prochaines échéances sur benin.campusfrance.org et complète "
        "CAMPAGNES dans web/index.html.")


def test_le_html_ne_contient_aucune_echeance_ecrite_en_dur(res):
    """La garantie de fond : si le texte du bandeau revenait dans le HTML statique,
    tout le mécanisme ci-dessus deviendrait décoratif."""
    html = INDEX.read_text(encoding="utf-8")
    bloc = html.split('id="annonce"', 1)[1].split("</div>", 1)[0]
    for mot in ("Campus France", "Parcoursup", "décembre", "mars", "avril"):
        assert mot not in bloc, (
            f"« {mot} » est écrit en dur dans le bandeau : il survivrait à sa date. "
            "Le texte doit venir de CAMPAGNES.")
