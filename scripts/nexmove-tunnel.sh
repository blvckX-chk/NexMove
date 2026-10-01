#!/usr/bin/env bash
# nexmove-tunnel.sh
# Tunnel Cloudflare rapide vers l'API NexMove + réenregistrement AUTOMATIQUE du webhook Telegram.
# Boucle en continu (auto-restart si le tunnel meurt) -> pas besoin de systemd/sudo.
# À lancer détaché :  setsid nohup ~/infra/nexmove-src/scripts/nexmove-tunnel.sh >/tmp/nexmove-tunnel.log 2>&1 &
# et au boot :        (crontab -l; echo "@reboot ~/infra/nexmove-src/scripts/nexmove-tunnel.sh >/tmp/nexmove-tunnel.log 2>&1") | crontab -
set -uo pipefail

ENV_FILE="${ENV_FILE:-$HOME/infra/forge-nex-api/.env}"
API_PORT="${API_PORT:-8000}"
CF_BIN="${CF_BIN:-cloudflared}"          # mets le chemin complet si "command not found" (which cloudflared)
LOG="${LOG:-/tmp/nexmove-cf.log}"

_val() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs || true; }

log() { echo "[nexmove-tunnel $(date -u +%H:%M:%S)] $*"; }

while true; do
  TOKEN="$(_val TELEGRAM_TOKEN)"
  SECRET="$(_val TELEGRAM_WEBHOOK_SECRET)"
  if [ -z "$TOKEN" ]; then log "TELEGRAM_TOKEN introuvable ($ENV_FILE)"; sleep 15; continue; fi

  # attend que l'API réponde (utile au boot, avant le tunnel)
  for _ in $(seq 1 30); do
    curl -sf "http://localhost:${API_PORT}/health" >/dev/null 2>&1 && break
    sleep 2
  done

  # (re)démarre cloudflared, capture sa sortie
  pkill -f "tunnel --url http://localhost:${API_PORT}" 2>/dev/null || true
  : > "$LOG"
  "$CF_BIN" tunnel --url "http://localhost:${API_PORT}" >"$LOG" 2>&1 &
  CF_PID=$!

  # récupère l'URL publique (jusqu'à ~90 s)
  URL=""
  for _ in $(seq 1 45); do
    URL="$(grep -oiE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
    [ -n "$URL" ] && break
    kill -0 "$CF_PID" 2>/dev/null || break
    sleep 2
  done

  if [ -z "$URL" ]; then
    log "aucune URL cloudflared — relance dans 10 s (voir $LOG)"
    kill "$CF_PID" 2>/dev/null || true
    sleep 10; continue
  fi
  log "tunnel prêt : $URL"

  # enregistre le webhook Telegram sur la nouvelle URL
  resp="$(curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook" \
    -d url="${URL}/webhook/telegram" \
    -d secret_token="${SECRET}" \
    -d allowed_updates='["message","edited_message","callback_query"]' \
    -d drop_pending_updates=true || true)"
  log "setWebhook: $resp"

  # tant que le tunnel vit, on attend ; s'il meurt, la boucle relance et réenregistre
  wait "$CF_PID" 2>/dev/null || true
  log "tunnel arrêté — relance dans 5 s"
  sleep 5
done
