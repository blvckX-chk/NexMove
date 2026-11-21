"""Sauvegarde et restauration (A-05) — cycle complet réellement exécuté.

Une sauvegarde qu'on n'a jamais restaurée n'est pas une sauvegarde. Ce test fabrique une
fausse production, la sauvegarde, la DÉTRUIT, restaure, et vérifie que les données sont
revenues. Il tourne en CI : si un jour le script casse, on l'apprend là, pas le jour du
sinistre.
"""
import json, os, shutil, sqlite3, subprocess, pathlib
import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
BACKUP = RACINE / "scripts" / "backup.sh"
RESTORE = RACINE / "scripts" / "restore.sh"
PHRASE = "phrase-de-test-pour-la-ci"

pytestmark = pytest.mark.skipif(not shutil.which("gpg"), reason="gpg absent")


def _env(prod, coffre):
    e = dict(os.environ)
    e.update({"NEXMOVE_DEPLOY_DIR": str(prod), "BACKUP_DIR": str(coffre),
              "NEXMOVE_BACKUP_PASSPHRASE": PHRASE,
              "NEXMOVE_BACKUP_PASS_FILE": str(coffre / "pass-inexistant")})
    return e


def _lancer(script, env, *args):
    r = subprocess.run(["bash", str(script), *args], capture_output=True, text=True, env=env, timeout=120)
    return r


@pytest.fixture
def prod(tmp_path):
    """Fausse production : base peuplée (en WAL) + .env + docker-compose.yml."""
    p = tmp_path / "prod"
    (p / "data").mkdir(parents=True)
    (p / ".env").write_text("FORGE_NEX_API_KEY=une-cle-longue-de-test-123456\nTELEGRAM_TOKEN=faux\n")
    (p / "docker-compose.yml").write_text("services: {api: {image: x}}\n")
    con = sqlite3.connect(p / "data" / "sessions.db")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE sessions(user_id TEXT PRIMARY KEY, data TEXT)")
    for i in range(25):
        con.execute("INSERT INTO sessions VALUES(?,?)",
                    (f"u{i}", json.dumps({"profil": {"nom": f"Testeur {i}"}})))
    con.commit(); con.close()
    return p


def test_cycle_complet_sauvegarde_puis_restauration(prod, tmp_path):
    coffre = tmp_path / "coffre"; coffre.mkdir()
    env = _env(prod, coffre)

    r = _lancer(BACKUP, env)
    assert r.returncode == 0, r.stderr
    assert "25 sessions" in r.stdout, r.stdout          # vérification intégrée à la sauvegarde
    archives = list(coffre.glob("nexmove-*.tar.gz.gpg"))
    assert len(archives) == 1

    # Sinistre : base corrompue et configuration perdue.
    (prod / "data" / "sessions.db").write_bytes(os.urandom(400))
    (prod / ".env").unlink()

    r = _lancer(RESTORE, env, "--oui")
    assert r.returncode == 0, r.stderr

    con = sqlite3.connect(prod / "data" / "sessions.db")
    assert con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 25
    data = json.loads(con.execute("SELECT data FROM sessions WHERE user_id='u7'").fetchone()[0])
    con.close()
    assert data["profil"]["nom"] == "Testeur 7"
    assert "FORGE_NEX_API_KEY" in (prod / ".env").read_text()
    assert any(d.name.startswith("avant-restauration") for d in prod.iterdir()), \
        "l'état précédent doit être conservé avant d'écraser"


def test_sans_phrase_secrete_rien_nest_ecrit(prod, tmp_path):
    """L'archive contient .env : jamais de sauvegarde en clair."""
    coffre = tmp_path / "coffre"; coffre.mkdir()
    env = dict(os.environ)
    env.update({"NEXMOVE_DEPLOY_DIR": str(prod), "BACKUP_DIR": str(coffre),
                "NEXMOVE_BACKUP_PASS_FILE": str(tmp_path / "absent")})
    env.pop("NEXMOVE_BACKUP_PASSPHRASE", None)
    r = _lancer(BACKUP, env)
    assert r.returncode != 0
    assert not list(coffre.iterdir()), "aucun fichier ne doit être écrit sans phrase secrète"


def test_archive_illisible_sans_la_phrase(prod, tmp_path):
    coffre = tmp_path / "coffre"; coffre.mkdir()
    assert _lancer(BACKUP, _env(prod, coffre)).returncode == 0
    archive = next(coffre.glob("*.gpg"))
    r = subprocess.run(["gpg", "--batch", "--passphrase", "mauvaise", "-d", str(archive)],
                       capture_output=True, timeout=60)
    assert r.returncode != 0, "l'archive se déchiffre avec une mauvaise phrase !"
    assert b"FORGE_NEX_API_KEY" not in r.stdout


def test_restauration_sans_oui_ne_touche_a_rien(prod, tmp_path):
    coffre = tmp_path / "coffre"; coffre.mkdir()
    env = _env(prod, coffre)
    assert _lancer(BACKUP, env).returncode == 0
    avant = (prod / "data" / "sessions.db").read_bytes()
    (prod / "data" / "sessions.db").write_bytes(b"x" * 50)   # état volontairement différent
    r = _lancer(RESTORE, env)                                 # sans --oui
    assert r.returncode == 0 and "RIEN n'a été modifié" in r.stdout
    assert (prod / "data" / "sessions.db").read_bytes() == b"x" * 50
    assert avant != b"x" * 50


def test_retention_supprime_les_vieilles_archives(prod, tmp_path):
    coffre = tmp_path / "coffre"; coffre.mkdir()
    env = _env(prod, coffre); env["BACKUP_KEEP"] = "2"
    for _ in range(3):
        assert _lancer(BACKUP, env).returncode == 0
        # horodatage à la seconde : on force des noms distincts
        import time; time.sleep(1.1)
    assert len(list(coffre.glob("nexmove-*.gpg"))) == 2
