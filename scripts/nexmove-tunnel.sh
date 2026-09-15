#!/usr/bin/env bash
# nexmove-tunnel.sh
# Lance un tunnel Cloudflare rapide vers l'API NexMove ET réenregistre automatiquement
# le webhook Telegram sur la nouvelle URL (qui change à chaque redémarrage du tunnel rapide).
# Pensé pour tourner en service systemd (voir nexmove-tunnel.service) — auto-réparation.
set -euo pipefail

ENV_FILE="${ENV_FILE:-$HOME/infra/forge-nex-api/.env}"
API_PORT="${API_PORT:-8000}"
LOG="${LOG:-/tmp/nexmove-cf.log}"

_val() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs || true; }
TOKEN="$(_val TELEGRAM_TOKEN)"
SECRET="$(_val TELEGRAM_WEBHOOK_SECRET)"

if [ -z "$TOKEN" ]; then
  echo "[nexmove-tunnel] TELEGRAM_TOKEN introuvable dans $ENV_FILE" >&2
  exit 1
fi

# (re)démarre cloudflared en tâche de fond, journalise sa sortie
pkill -f "cloudflared tunnel --url" 2>/dev/null || true
: > "$LOG"
cloudflared tunnel --url "http://localhost:${API_PORT}" >"$LOG" 2>&1 &
CF_PID=$!

# attend l'apparition de l'URL publique (jusqu'à ~90 s)
URL=""
for _ in $(seq 1 45); do
  URL="$(grep -oiE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
  [ -n "$URL" ] && break
  sleep 2
done

if [ -z "$URL" ]; then
  echo "[nexmove-tunnel] aucune URL cloudflared après 90 s — voir $LOG" >&2
  kill "$CF_PID" 2>/dev/null || true
  exit 1
fi
echo "[nexmove-tunnel] tunnel prêt : $URL"

# enregistre le webhook Telegram sur la nouvelle URL
resp="$(curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -d url="${URL}/webhook/telegram" \
  -d secret_token="${SECRET}" \
  -d allowed_updates='["message","edited_message","callback_query"]' \
  -d drop_pending_updates=true || true)"
echo "[nexmove-tunnel] setWebhook: $resp"

# garde cloudflared au premier plan : si le tunnel meurt, systemd relance le script (et réenregistre)
wait "$CF_PID"
