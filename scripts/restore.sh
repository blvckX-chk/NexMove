#!/usr/bin/env bash
# Restaure une sauvegarde NexMove produite par scripts/backup.sh.
#
# Garde-fous :
#  - l'archive est d'abord déchiffrée et VÉRIFIÉE dans un dossier temporaire ;
#  - l'état actuel est mis de côté AVANT tout écrasement (on peut revenir en arrière) ;
#  - rien n'est touché sans confirmation explicite (ou --oui) ;
#  - le conteneur doit être arrêté : restaurer sous une base ouverte la corromprait.
#
# Usage :
#   ./scripts/restore.sh                      # inspecte la dernière sauvegarde (rien n'est écrit)
#   ./scripts/restore.sh <archive.gpg> --oui  # restaure pour de vrai
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/nexmove-backups}"
PASS_FILE="${NEXMOVE_BACKUP_PASS_FILE:-$HOME/.nexmove-backup-pass}"
ARCHIVE=""; CONFIRME=0
for a in "$@"; do
  case "$a" in
    --oui|--yes|-y) CONFIRME=1 ;;
    *) ARCHIVE="$a" ;;
  esac
done
[ -n "$ARCHIVE" ] || ARCHIVE="$(ls -1t "$BACKUP_DIR"/nexmove-*.tar.gz.gpg 2>/dev/null | head -1 || true)"
[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || { echo "❌ Aucune archive trouvée dans $BACKUP_DIR" >&2; exit 1; }

PASS="${NEXMOVE_BACKUP_PASSPHRASE:-}"
[ -z "$PASS" ] && [ -f "$PASS_FILE" ] && PASS="$(head -n1 "$PASS_FILE")"
[ -n "$PASS" ] || { echo "❌ Phrase secrète introuvable (NEXMOVE_BACKUP_PASSPHRASE ou $PASS_FILE)." >&2; exit 1; }

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
DEPLOY_DIR="${NEXMOVE_DEPLOY_DIR:-}"
if [ -z "$DEPLOY_DIR" ]; then
  for cand in "$ROOT/../forge-nex-api" "/root/infra/forge-nex-api" "$ROOT/api" "$ROOT"; do
    if [ -f "$cand/.env" ] || [ -f "$cand/docker-compose.yml" ]; then DEPLOY_DIR="$(cd "$cand" && pwd)"; break; fi
  done
fi
[ -n "$DEPLOY_DIR" ] || { echo "❌ Dossier de production introuvable (NEXMOVE_DEPLOY_DIR=…)." >&2; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
echo "➤ Lecture de $(basename "$ARCHIVE")…"
printf '%s' "$PASS" | gpg --batch --quiet --yes --passphrase-fd 0 -d "$ARCHIVE" | tar -C "$TMP" -xzf -
[ -f "$TMP/MANIFESTE.txt" ] && sed 's/^/   /' "$TMP/MANIFESTE.txt"

if [ -f "$TMP/data/sessions.db" ]; then
  python3 - "$TMP/data/sessions.db" <<'PY' || { echo "❌ Base invalide : restauration refusée." >&2; exit 1; }
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
    raise SystemExit("intégrité SQLite KO")
n = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
print(f"   ✓ base saine · {n} sessions")
con.close()
PY
fi

if [ "$CONFIRME" != "1" ]; then
  echo
  echo "ℹ️  Inspection seulement — RIEN n'a été modifié."
  echo "   Pour restaurer vraiment :"
  echo "     cd $DEPLOY_DIR && docker compose down"
  echo "     $0 \"$ARCHIVE\" --oui"
  exit 0
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^forge-nex-api$'; then
  echo "❌ Le conteneur forge-nex-api tourne encore. Arrête-le d'abord :" >&2
  echo "   cd $DEPLOY_DIR && docker compose down" >&2
  exit 1
fi

SAFE="$DEPLOY_DIR/avant-restauration-$(date -u '+%Y%m%d-%H%M%S')"
mkdir -p "$SAFE"
for f in data .env docker-compose.yml; do
  [ -e "$DEPLOY_DIR/$f" ] && cp -a "$DEPLOY_DIR/$f" "$SAFE/" || true
done
echo "➤ État actuel mis de côté dans : $SAFE"

mkdir -p "$DEPLOY_DIR/data"
[ -f "$TMP/data/sessions.db" ] && cp -f "$TMP/data/sessions.db" "$DEPLOY_DIR/data/sessions.db"
# Les journaux WAL de l'ancienne base n'ont plus de sens face à la base restaurée.
rm -f "$DEPLOY_DIR/data/sessions.db-wal" "$DEPLOY_DIR/data/sessions.db-shm"
for f in .env docker-compose.yml; do
  [ -f "$TMP/$f" ] && cp -f "$TMP/$f" "$DEPLOY_DIR/$f"
done

echo
echo "✅ Restauration terminée dans $DEPLOY_DIR"
echo "   Redémarre :  cd $DEPLOY_DIR && docker compose up -d"
echo "   Si quelque chose cloche, l'état précédent est intact dans $SAFE"
