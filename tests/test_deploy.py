"""Le chemin de DÉPLOIEMENT est-il complet ? (audit N-03)

Panne réelle en v3.96 : `api/orientation.py` était bien dans le dépôt et tous les tests
passaient, mais ni le Dockerfile ni `scripts/deploy.sh` ne le recopiaient. L'API démarrait
en local et plantait en production sur `ModuleNotFoundError`.

La CI de l'époque construisait l'image depuis `api/` en direct — elle ne testait donc PAS
ce que `deploy.sh` synchronise réellement. Ces tests comblent ce trou, sans Docker et en
moins d'une seconde.
"""
import ast, os, pathlib, shutil, subprocess
import pytest


def _docker_dispo() -> bool:
    """Le binaire ne suffit pas : il faut un démon joignable (sinon on saute le test)."""
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False

RACINE = pathlib.Path(__file__).resolve().parent.parent
API = RACINE / "api"
DEPLOY = RACINE / "scripts" / "deploy.sh"


def _modules_locaux() -> set:
    return {p.stem for p in API.glob("*.py")}


def _imports_locaux(fichier: pathlib.Path, locaux: set) -> set:
    """Modules du projet importés par ce fichier (ignore la bibliothèque standard et pip)."""
    out = set()
    for n in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
        noms = []
        if isinstance(n, ast.Import):
            noms = [a.name.split(".")[0] for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            noms = [n.module.split(".")[0]]
        out |= {m for m in noms if m in locaux}
    return out


@pytest.fixture
def synchronise(tmp_path):
    """Rejoue la copie de deploy.sh dans un faux dossier de production."""
    prod = tmp_path / "prod"
    prod.mkdir()
    (prod / ".env").write_text("FORGE_NEX_API_KEY=une-cle-de-test-bien-assez-longue\n")
    (prod / "docker-compose.yml").write_text("services: {api: {build: .}}\n")
    env = dict(os.environ)
    env.update({"NEXMOVE_SKIP_GIT": "1", "NEXMOVE_SKIP_BUILD": "1",
                "NEXMOVE_DEPLOY_DIR": str(prod)})
    r = subprocess.run(["bash", str(DEPLOY)], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr or r.stdout
    return prod


def test_deploy_copie_tous_les_modules_python(synchronise):
    """Tout module de api/ doit arriver dans le dossier de production."""
    attendus = {p.name for p in API.glob("*.py")}
    arrives = {p.name for p in synchronise.glob("*.py")}
    assert attendus == arrives, f"modules non synchronisés : {sorted(attendus - arrives)}"


def test_aucun_import_local_ne_manque_apres_deploiement(synchronise):
    """LE test de la panne v3.96 : un module importé mais non copié = API morte au démarrage."""
    locaux = _modules_locaux()
    manquants = []
    for f in sorted(synchronise.glob("*.py")):
        for m in _imports_locaux(f, locaux):
            if not (synchronise / f"{m}.py").exists():
                manquants.append(f"{f.name} importe '{m}' — absent du déploiement")
    assert not manquants, "; ".join(manquants)


def test_deploy_copie_le_necessaire_au_build(synchronise):
    for f in ("Dockerfile", "requirements.txt"):
        assert (synchronise / f).exists(), f"{f} n'est pas synchronisé : build impossible"


def test_deploy_ne_copie_jamais_les_secrets_ni_les_donnees(synchronise):
    """Garde-fou inverse : deploy.sh ne doit JAMAIS écraser .env ni data/ en production."""
    assert (synchronise / ".env").read_text().startswith("FORGE_NEX_API_KEY=une-cle-de-test"), \
        "deploy.sh a écrasé le .env de production !"
    assert not (synchronise / ".env.example").exists()


def test_le_dockerfile_embarque_tous_les_modules(synchronise):
    """Le Dockerfile doit copier chaque module : c'est l'autre moitié de la panne v3.96."""
    contenu = (synchronise / "Dockerfile").read_text()
    lignes_copy = [l for l in contenu.splitlines() if l.strip().upper().startswith("COPY")]
    assert lignes_copy, "aucune instruction COPY dans le Dockerfile"
    # Soit un glob *.py (robuste), soit la liste exhaustive des modules.
    if not any("*.py" in l for l in lignes_copy):
        copies = " ".join(lignes_copy)
        oublies = [p.name for p in API.glob("*.py") if p.name not in copies]
        assert not oublies, (f"le Dockerfile liste les modules un par un et oublie : {oublies}. "
                             "Préfère `COPY *.py .`")


@pytest.mark.skipif(not _docker_dispo(), reason="démon Docker indisponible")
def test_image_construite_depuis_le_deploiement_demarre(synchronise):
    """Preuve finale : l'image bâtie sur les fichiers SYNCHRONISÉS importe bien l'app.

    On n'allume pas le serveur : on demande juste à Python d'importer `main`, ce qui
    reproduit exactement le `ModuleNotFoundError` de la v3.96.
    """
    tag = "nexmove-deploy-test"
    b = subprocess.run(["docker", "build", "-q", "-t", tag, str(synchronise)],
                       capture_output=True, text=True, timeout=900)
    assert b.returncode == 0, b.stderr[-2000:]
    try:
        r = subprocess.run(["docker", "run", "--rm", "-e", "FORGE_NEX_API_KEY=ci-test-key",
                            tag, "python", "-c", "import main; print(main.VERSION)"],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
        assert r.stdout.strip(), "aucune version renvoyée"
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, timeout=120)
