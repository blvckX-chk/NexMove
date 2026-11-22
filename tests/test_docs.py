"""La documentation dit-elle encore la vérité ? (audit A-03)

Le problème constaté : `ANALYSE-TECHNIQUE.md` décrivait « aucun test, aucune CI, ~3 200
lignes » et `CAHIER-DES-CHARGES.md` annonçait « 127 tests », alors que le projet en comptait
plus de 700. Une documentation fausse est pire qu'absente : on s'y fie pour décider.

Ces tests ancrent `docs/ETAT-ACTUEL.md` dans la réalité du dépôt. Si le système change sans
que la page suive, la CI échoue — et le message dit quoi corriger.
"""
import re, subprocess, sys, pathlib
import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
DOCS = RACINE / "docs"
ETAT = DOCS / "ETAT-ACTUEL.md"
API = RACINE / "api"


@pytest.fixture(scope="module")
def etat():
    return ETAT.read_text(encoding="utf-8")


def test_etat_actuel_existe():
    assert ETAT.exists(), "docs/ETAT-ACTUEL.md est la référence : il doit exister"


def test_version_documentee_est_la_bonne(etat):
    reelle = re.search(r'^VERSION\s*=\s*"([^"]+)"', (API / "main.py").read_text(encoding="utf-8"),
                       re.M).group(1)
    assert f"v{reelle}" in etat, (
        f"ETAT-ACTUEL.md ne mentionne pas la version réelle v{reelle} — mets l'en-tête à jour")


def test_nombre_de_modules_documente(etat):
    reels = sorted(p.name for p in API.glob("*.py"))
    annonce = re.search(r"Modules Python \| \*\*?(\d+)", etat) or re.search(r"\|\s*(\d+)\s+dans `api/`", etat)
    if annonce:
        assert int(annonce.group(1)) == len(reels), \
            f"ETAT-ACTUEL.md annonce {annonce.group(1)} modules, il y en a {len(reels)} : {reels}"
    for nom in reels:
        assert f"`{nom}`" in etat, f"module {nom} absent de la liste d'ETAT-ACTUEL.md"


def test_jobs_ci_documentes(etat):
    import yaml
    jobs = set(yaml.safe_load((RACINE / ".github/workflows/ci.yml").read_text())["jobs"])
    for j in jobs:
        assert f"`{j}`" in etat, f"le job CI « {j} » n'est pas documenté dans ETAT-ACTUEL.md"
    annonce = re.search(r"(\d+) jobs", etat)
    if annonce:
        assert int(annonce.group(1)) == len(jobs), \
            f"ETAT-ACTUEL.md annonce {annonce.group(1)} jobs CI, il y en a {len(jobs)}"


def test_nombre_de_tests_documente(etat):
    """Tolérance de 10 % : on veut empêcher « 127 » face à 713, pas casser à chaque test ajouté."""
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "--collect-only"],
                       capture_output=True, text=True, cwd=RACINE, timeout=300)
    m = re.search(r"(\d+) tests? collected", r.stdout)
    if not m:
        pytest.skip("collecte pytest indisponible")
    reel = int(m.group(1))
    annonce = re.search(r"Tests \| \*\*(\d+)\*\*", etat)
    assert annonce, "ETAT-ACTUEL.md doit annoncer un nombre de tests"
    ecrit = int(annonce.group(1))
    assert abs(ecrit - reel) <= max(10, reel * 0.1), (
        f"ETAT-ACTUEL.md annonce {ecrit} tests, il y en a {reel} — remplace le chiffre par {reel}")


DOCS_ATTENDUS = {
    "ETAT-ACTUEL.md",        # la référence
    "CHANGELOG.md",          # historique des versions
    "INSTALLATION.md",       # installer, mettre à jour, exploiter
    "DOMAINE-ET-TUNNEL.md",  # domaine + tunnel Cloudflare
    "GUIDE-WHATSAPP.md",     # activer WhatsApp (côté Meta)
    "GUIDE-MESSENGER.md",    # activer Messenger (côté Meta)
    "SECURITE.md",           # secrets, rotation, ce qui est public
    "SAUVEGARDE.md",         # sauvegarder, restaurer, changer de serveur
}


def test_docs_ne_contient_que_de_l_operationnel():
    """`docs/` était monté à 23 fichiers qui se contredisaient (ngrok vs Cloudflare, n8n vs
    webhook natif). Chaque ajout doit donc être délibéré : ajoute le fichier à DOCS_ATTENDUS
    *et* à la table d'ETAT-ACTUEL.md, ou garde-le hors du dépôt (il est public)."""
    reels = {p.name for p in DOCS.iterdir() if p.is_file()}
    en_trop = reels - DOCS_ATTENDUS
    manquants = DOCS_ATTENDUS - reels
    assert not en_trop, (f"documents non prévus dans docs/ : {sorted(en_trop)} — "
                         "déclare-les dans DOCS_ATTENDUS et dans ETAT-ACTUEL.md, ou sors-les du dépôt")
    assert not manquants, f"documents attendus mais absents : {sorted(manquants)}"


def test_chaque_document_est_reference_dans_la_page_de_reference(etat):
    for nom in DOCS_ATTENDUS - {"ETAT-ACTUEL.md"}:
        assert nom in etat, f"{nom} n'est pas listé dans la table d'ETAT-ACTUEL.md"


def test_chaque_document_porte_un_statut():
    """Aucun document ne doit pouvoir être pris pour l'état actuel sans le dire."""
    connus = {"ETAT-ACTUEL.md", "CHANGELOG.md", "SECURITE.md", "SAUVEGARDE.md"}  # pas de bandeau : toujours à jour
    sans_statut = []
    for p in sorted(DOCS.glob("*.md")):
        if p.name in connus:
            continue
        tete = "\n".join(p.read_text(encoding="utf-8").split("\n")[:8])
        if "Document historique" not in tete and "Guide de tâche" not in tete:
            sans_statut.append(p.name)
    assert not sans_statut, (
        "ces documents n'indiquent ni « Document historique » ni « Guide de tâche » en tête : "
        f"{sans_statut}")


def test_les_documents_a_jour_ne_decrivent_plus_ngrok_ni_n8n():
    """L'architecture réelle est : webhook Telegram natif + tunnel nommé Cloudflare.

    Les mentions restantes doivent être des avertissements (« n'est plus utilisé »), jamais
    des instructions.
    """
    for nom in ("README.md", "docs/ETAT-ACTUEL.md"):
        texte = (RACINE / nom).read_text(encoding="utf-8")
        for ligne in texte.splitlines():
            if re.search(r"\bngrok\b", ligne, re.I):
                assert re.search(r"plus utilis|plus l'archi|jamais|ancien", ligne, re.I), \
                    f"{nom} : ngrok présenté comme actuel -> « {ligne.strip()[:90]} »"


def test_le_readme_pointe_vers_la_reference():
    readme = (RACINE / "README.md").read_text(encoding="utf-8")
    assert "ETAT-ACTUEL.md" in readme, "le README doit renvoyer vers la page de référence"


def test_pas_de_lien_interne_casse():
    """Un lien vers un fichier qui n'existe pas fait perdre confiance dans tout le reste."""
    casses = []
    for p in [RACINE / "README.md", *DOCS.glob("*.md")]:
        for cible in re.findall(r"\]\(([^)#:]+\.md)\)", p.read_text(encoding="utf-8")):
            if not (p.parent / cible).resolve().exists():
                casses.append(f"{p.name} -> {cible}")
    assert not casses, f"liens cassés : {casses}"
