#!/usr/bin/env bash
# nexmove-named-tunnel.sh
# Lance le TUNNEL NOMMÉ Cloudflare (URL FIXE) vers l'API NexMove, avec auto-restart.
# Contrairement au tunnel rapide, l'URL ne change JAMAIS -> le webhook Telegram/WhatsApp
# est enregistré UNE SEULE FOIS (voir docs/DOMAINE-ET-TUNNEL.md), pas besoin de le refaire.
# Pré-requis : avoir créé le tunnel "nexmove" et son ~/.cloudflared/config.yml (voir le doc).
#
# Lancer détaché :  setsid nohup ~/infra/nexmove-src/scripts/nexmove-named-tunnel.sh >/tmp/nexmove-tunnel.log 2>&1 &
# Au boot :         (crontab -l 2>/dev/null; echo "@reboot ~/infra/nexmove-src/scripts/nexmove-named-tunnel.sh >/tmp/nexmove-tunnel.log 2>&1") | crontab -
set -uo pipefail

TUNNEL_NAME="${TUNNEL_NAME:-nexmove}"
CF_BIN="${CF_BIN:-cloudflared}"          # mets le chemin complet si "command not found" (which cloudflared)
API_PORT="${API_PORT:-8000}"

log() { echo "[nexmove-tunnel $(date -u +%H:%M:%S)] $*"; }

while true; do
  # attend que l'API locale réponde (utile au boot)
  for _ in $(seq 1 30); do
    curl -sf "http://localhost:${API_PORT}/health" >/dev/null 2>&1 && break
    sleep 2
  done
  log "démarrage du tunnel nommé '$TUNNEL_NAME' (URL fixe)…"
  "$CF_BIN" tunnel run "$TUNNEL_NAME"
  log "tunnel arrêté — relance dans 5 s"
  sleep 5
done
