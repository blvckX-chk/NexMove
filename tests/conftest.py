"""Isolation des tests : la base SQLite (quotas, sessions, offres…) doit être
JETABLE et repartir de zéro à chaque session de test. Sinon les compteurs de
quota (usage_store) persistent sur data/sessions.db et font échouer, selon
l'ordre d'exécution, les tests qui supposent une limite gratuite encore dispo.

On fixe NEXMOVE_DB_PATH AVANT l'import de api.db (les singletons capturent le
chemin à l'import), vers un fichier temporaire propre."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="nexmove-tests-")
os.environ["NEXMOVE_DB_PATH"] = os.path.join(_tmp, "test_sessions.db")
