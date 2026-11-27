"""Page « Comment ça marche » : montrer l'outil au travail avant de demander confiance.

Pourquoi cette page existe. Le Propriétaire l'a dit le 27/11/2026, et c'est le bon
raisonnement : on ne demande pas à quelqu'un de confier un dossier Campus France à un outil
qui n'a encore rien prouvé. La campagne de décembre commence donc par présenter l'outil, et
cette page est ce qu'elle montre. Elle doit convaincre sans mentir.

Ce que ces tests verrouillent :

1. **La page reste atteignable.** Une page de confiance que personne ne trouve ne sert à rien.
2. **La date de l'offre ne peut pas dériver.** Elle vient de `data-fin`, qui doit rester égal à
   `LANCEMENT_FIN` côté serveur, et le bloc s'efface tout seul après. Annoncer une offre
   terminée sur une page qui parle d'honnêteté serait le pire endroit pour ce défaut.
3. **Le message d'arnaque affiché est bien celui du produit.** C'est l'argument de confiance le
   plus fort de la page : s'il dérive de ce que le bot dit vraiment, la page devient une
   promesse creuse.
4. **Le balisage FAQ correspond au texte visible.** Un balisage qui promet autre chose que la
   page est une tromperie pour le moteur de recherche comme pour le lecteur.
5. **Aucune opportunité nommée avec une date.** Une page de démonstration n'invente pas de
   bourse : la règle « jamais de date ni d'URL inventée » vaut ici comme ailleurs.
"""
import html as htmlmod
import json
import os
import pathlib
import re
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "api"))
os.environ.setdefault("FORGE_NEX_API_KEY", "test-key")
import main  # noqa: E402

PAGE = RACINE / "web" / "comment-ca-marche.html"
INDEX = RACINE / "web" / "index.html"
SITEMAP = RACINE / "web" / "sitemap.xml"


@pytest.fixture(scope="module")
def html():
    return PAGE.read_text(encoding="utf-8")


# ── 1. Atteignable ───────────────────────────────────────────────────────────

def test_la_page_existe():
    assert PAGE.exists()


def test_elle_est_liee_depuis_l_accueil(html):
    """Deux entrées : le hero (là où se décide la confiance) et le pied de page."""
    index = INDEX.read_text(encoding="utf-8")
    assert index.count("comment-ca-marche.html") >= 2, (
        "la page doit être atteignable depuis le hero ET le pied de page de l'accueil")


def test_elle_est_dans_le_sitemap():
    assert "comment-ca-marche.html" in SITEMAP.read_text(encoding="utf-8")


def test_elle_ramene_vers_l_accueil(html):
    """« Un moyen de revenir depuis chaque page » : sinon c'est un cul-de-sac."""
    assert 'href="index.html"' in html


def test_elle_est_indexable(html):
    """Page intemporelle et utile en recherche : on l'indexe, contrairement à une page
    de campagne datée."""
    assert "index,follow" in html
    assert 'rel="canonical"' in html and "comment-ca-marche.html" in html


# ── 2. La date de l'offre ne peut pas dériver ────────────────────────────────

def test_le_bloc_offre_porte_sa_date(html):
    m = re.search(r'id="offre"\s+data-fin="(\d{4}-\d{2}-\d{2})"', html)
    assert m, "le bloc d'offre doit porter data-fin=\"AAAA-MM-JJ\""


def test_la_date_de_la_page_est_celle_du_serveur(html):
    """L'invariant : une page qui annonce une gratuité jusqu'à une date doit annoncer LA
    date que le code applique. Deux sources finissent toujours par divergler."""
    m = re.search(r'id="offre"\s+data-fin="(\d{4}-\d{2}-\d{2})"', html)
    assert m and m.group(1) == main.LANCEMENT_FIN, (
        f"la page annonce {m.group(1) if m else '?'} et le code applique "
        f"{main.LANCEMENT_FIN} — mets web/comment-ca-marche.html à jour")


def test_le_bloc_offre_sait_s_effacer(html):
    """Après la date, la page ne doit plus parler de gratuité illimitée."""
    assert "isoLocal(new Date()) > fin" in html, "l'expiration doit être testée au chargement"
    assert "/offres" in html, "après l'offre, il faut renvoyer vers les formules"


def test_la_date_nest_ecrite_quune_seule_fois(html):
    """La phrase affichée est construite depuis data-fin. Si la date était aussi écrite en
    dur dans la prose, les deux dériveraient — c'est exactement le défaut corrigé en v4.18."""
    fin = main.LANCEMENT_FIN
    annee, mois = fin[:4], int(fin[5:7])
    nom_mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                "août", "septembre", "octobre", "novembre", "décembre"][mois - 1]
    # La prose ne doit pas contenir « mars 2027 » en dur.
    assert f"{nom_mois} {annee}" not in html, (
        f"« {nom_mois} {annee} » est écrit en dur : la date doit venir de data-fin")


def test_sans_javascript_la_phrase_reste_juste(html):
    """Dégradation : sans JS la date n'est pas injectée, la phrase doit rester vraie."""
    assert 'id="offreQuand">En ce moment<' in html, (
        "le texte de repli doit être valable sans date (« En ce moment »)")


# ── 3. Fidélité au produit ───────────────────────────────────────────────────

def test_le_message_d_arnaque_est_celui_du_bot(html):
    """La scène 3 est l'argument de confiance le plus fort de la page. Si elle dérive de ce
    que le bot répond vraiment, la page promet ce que le produit ne tient pas."""
    import orientation as ori
    reel = ori.MESSAGE_ARNAQUE
    # La phrase pivot, celle qui porte toute la règle, doit être reprise mot pour mot.
    pivot = ("ne te demandent JAMAIS "
             "d'argent pour t'obtenir un emploi, un visa ou une admission")
    assert pivot in reel, "le message du bot a changé : vérifie la page"
    assert pivot in html, "la page doit citer la règle telle que le bot l'énonce"
    for guichet in ("Campus France", "TLS", "VFS", "Capago"):
        assert guichet in html, f"« {guichet} » fait partie de la réponse réelle"


def test_la_page_annonce_le_stockage_europeen(html):
    assert "Union européenne" in html


def test_la_page_ne_promet_aucune_garantie(html):
    """Le produit refuse de garantir un visa ; la page doit le dire, pas l'esquiver."""
    assert "personne ne peut le garantir" in html.lower()


def test_la_page_dit_ce_qu_elle_ne_sait_pas(html):
    """Les durées de conservation chez les fournisseurs d'IA sont inconnues. On le dit."""
    assert "nous ne le savons pas" in html


# ── 4. Balisage conforme au visible ──────────────────────────────────────────

def test_le_balisage_faq_correspond_aux_questions_visibles(html):
    blocs = [b for b in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        if "FAQPage" in b]
    assert blocs, "balisage FAQPage absent"
    data = json.loads(blocs[0])
    questions = [q["name"] for q in data["mainEntity"]]
    def propre(t):
        # La source contient des entités littérales (&nbsp;) : il faut les décoder avant de
        # comparer, sinon le test échoue sur une différence que personne ne voit à l'écran.
        return re.sub(r"\s+", " ", htmlmod.unescape(t)).strip()

    visibles = [propre(s) for s in re.findall(r"<summary>(.*?)</summary>", html, re.S)]
    assert len(questions) == len(visibles), (
        f"{len(questions)} questions balisées pour {len(visibles)} visibles")
    for q, v in zip(questions, visibles):
        assert propre(q) == v, f"balisage « {q} » ≠ visible « {v} »"


# ── 5. Rien d'inventé, rien d'interdit ───────────────────────────────────────

def test_aucune_date_dechance_inventee(html):
    """Une page de démonstration n'invente pas de bourse avec une date limite. Les scènes
    montrent le comportement, elles ne nomment aucun programme daté."""
    for motif in (r"\b\d{1,2}\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+20\d{2}\b",
                  r"\bdate limite\s*:\s*\d"):
        trouve = re.findall(motif, html, re.I)
        assert not trouve, f"date d'échéance en dur dans la page : {trouve}"


def test_pas_d_italique(html):
    """Charte : jamais d'italique dans l'interface."""
    assert "<em>" not in html and "<i>" not in html


def test_les_cibles_tactiles_respectent_le_seuil(html):
    """44 px : les questions de la FAQ sont des zones cliquables."""
    assert "min-height:44px" in html


def test_le_mouvement_respecte_le_choix_de_l_utilisateur(html):
    assert "prefers-reduced-motion" in html


def test_les_arrivees_nutilisent_pas_un_ecouteur_de_defilement(html):
    """Un écouteur de défilement non bridé tourne à chaque image et pénalise les téléphones."""
    assert "IntersectionObserver" in html
    assert "addEventListener('scroll'" not in html
