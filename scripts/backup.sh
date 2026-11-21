#!/usr/bin/env bash
# Sauvegarde CHIFFRÉE de NexMove : base SQLite + .env + docker-compose.yml.
#
# Pourquoi ce script existe : l'archive contient .env, donc TOUS les secrets de production
# (jetons Telegram/Meta, clés IA, clé API). Elle n'est JAMAIS écrite en clair : sans phrase
# secrète, le script refuse de s'exécuter plutôt que de produire un fichier lisible par
# quiconque met la main dessus.
#
# La base est copiée avec l'API `backup()` de Python (pas `cp`) : copie COHÉRENTE même
# pendant que le bot écrit, et compatible WAL. Un `cp` d'une base active donne une
# sauvegarde parfois corrompue — c'est le piège classique.
#
# Chaque archive est VÉRIFIÉE après création (déchiffrement + intégrité SQLite + comptage).
# Une sauvegarde non vérifiée n'est pas une sauvegarde.
#
# Usage :
#   NEXMOVE_BACKUP_PASSPHRASE='…'  ./scripts/backup.sh
#   (ou phrase secrète dans ~/.nexmove-backup-pass, chmod 600)
#
# Variables : NEXMOVE_DEPLOY_DIR (dossier de prod)  BACKUP_DIR (défaut ~/nexmove-backups)
#             BACKUP_KEEP (nombre d'archives conservées, défaut 14)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/nexmove-backups}"
KEEP="${BACKUP_KEEP:-14}"
PASS_FILE="${NEXMOVE_BACKUP_PASS_FILE:-$HOME/.nexmove-backup-pass}"

# ── Phrase secrète (obligatoire) ──────────────────────────────────────────────────────────
PASS="${NEXMOVE_BACKUP_PASSPHRASE:-}"
if [ -z "$PASS" ] && [ -f "$PASS_FILE" ]; then
  PASS="$(head -n1 "$PASS_FILE")"
fi
if [ -z "$PASS" ]; then
  echo "❌ Aucune phrase secrète. L'archive contiendrait tes secrets en clair : j'arrête." >&2
  echo "   Crée-la une fois pour toutes :" >&2
  echo "     python3 -c \"import secrets;print(secrets.token_urlsafe(24))\" > $PASS_FILE" >&2
  echo "     chmod 600 $PASS_FILE" >&2
  echo "   ⚠️  Note-la AUSSI ailleurs (gestionnaire de mots de passe) : sans elle," >&2
  echo "       les sauvegardes sont irrécupérables." >&2
  exit 1
fi
command -v gpg >/dev/null || { echo "❌ gpg absent : apt-get install -y gnupg" >&2; exit 1; }

# ── Dossier de production (même logique que deploy.sh) ────────────────────────────────────
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
DEPLOY_DIR="${NEXMOVE_DEPLOY_DIR:-}"
if [ -z "$DEPLOY_DIR" ]; then
  for cand in "$ROOT/../forge-nex-api" "/root/infra/forge-nex-api" "$ROOT/api" "$ROOT"; do
    if [ -f "$cand/.env" ]; then DEPLOY_DIR="$(cd "$cand" && pwd)"; break; fi
  done
fi
[ -n "$DEPLOY_DIR" ] || { echo "❌ Dossier de production introuvable (NEXMOVE_DEPLOY_DIR=…)." >&2; exit 1; }

DB="$DEPLOY_DIR/data/sessions.db"
STAMP="$(date -u '+%Y%m%d-%H%M%S')"
OUT="$BACKUP_DIR/nexmove-$STAMP.tar.gz.gpg"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"

echo "➤ 1/4  Copie cohérente de la base…"
if [ -f "$DB" ]; then
  mkdir -p "$TMP/paquet/data"
  python3 - "$DB" "$TMP/paquet/data/sessions.db" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
d = sqlite3.connect(dst)
with d:
    s.backup(d)          # instantané cohérent, même sous écriture concurrente (WAL)
s.close(); d.close()
PY
  echo "   ✓ sessions.db ($(du -h "$TMP/paquet/data/sessions.db" | cut -f1))"
else
  echo "   ⚠️  $DB absent (première installation ?) — on sauvegarde quand même la config."
  mkdir -p "$TMP/paquet/data"
fi

echo "➤ 2/4  Ajout de la configuration…"
for f in .env docker-compose.yml; do
  [ -f "$DEPLOY_DIR/$f" ] && cp "$DEPLOY_DIR/$f" "$TMP/paquet/$f" && echo "   ✓ $f"
done
# Fichiers déposés par les utilisateurs : volumineux et reconstituables -> exclus volontairement.
{ echo "sauvegarde NexMove"; echo "date_utc=$STAMP"; echo "source=$DEPLOY_DIR";
  echo "version_repo=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo inconnue)"; } > "$TMP/paquet/MANIFESTE.txt"

echo "➤ 3/4  Archivage et chiffrement…"
tar -C "$TMP/paquet" -czf "$TMP/paquet.tar.gz" .
printf '%s' "$PASS" | gpg --batch --quiet --yes --passphrase-fd 0 \
  --symmetric --cipher-algo AES256 -o "$OUT" "$TMP/paquet.tar.gz"
chmod 600 "$OUT"

echo "➤ 4/4  Vérification (on rouvre l'archive et on teste la base)…"
VTMP="$TMP/verif"; mkdir -p "$VTMP"
printf '%s' "$PASS" | gpg --batch --quiet --yes --passphrase-fd 0 -d "$OUT" | tar -C "$VTMP" -xzf -
if [ -f "$VTMP/data/sessions.db" ]; then
  python3 - "$VTMP/data/sessions.db" <<'PY' || { echo "❌ Archive illisible — supprimée." >&2; exit 1; }
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
    raise SystemExit("intégrité SQLite KO")
tables = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
n = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] if "sessions" in tables else 0
con.close()
print(f"   ✓ base saine · {len(tables)} tables · {n} sessions")
PY
else
  echo "   ✓ archive lisible (pas encore de base)"
fi

# ── Rétention ─────────────────────────────────────────────────────────────────────────────
ls -1t "$BACKUP_DIR"/nexmove-*.tar.gz.gpg 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f "$old"; echo "   · ancienne sauvegarde supprimée : $(basename "$old")"
done

echo
echo "✅ Sauvegarde vérifiée : $OUT  ($(du -h "$OUT" | cut -f1))"
echo "   Conservées : $(ls -1 "$BACKUP_DIR"/nexmove-*.tar.gz.gpg 2>/dev/null | wc -l) / $KEEP"
echo
echo "⚠️  Une sauvegarde qui reste sur le serveur ne protège PAS d'une perte du serveur."
echo "   Copie-la ailleurs, par exemple :  scp $OUT ton-pc:~/sauvegardes-nexmove/"
