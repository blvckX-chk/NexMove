#!/usr/bin/env bash
# nex-cron.sh — appelle un endpoint cron de l'API NexMove en LOCAL (clé lue depuis .env).
# Usage : nex-cron.sh <collect|notify|relances>
# L'API écoute sur 127.0.0.1:8000 (pas besoin du tunnel pour les tâches internes).
set -uo pipefail
ENV_FILE="${ENV_FILE:-/root/infra/forge-nex-api/.env}"
PORT="${API_PORT:-8000}"
EP="${1:-}"
case "$EP" in collect|notify|relances) ;; *) echo "usage: $0 <collect|notify|relances>"; exit 2;; esac
KEY="$(grep -E '^FORGE_NEX_API_KEY=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"' ")"
# En-tête attendu par l'API : X-Forge-Nex-Key (voir api_key_header dans main.py).
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://localhost:${PORT}/api/${EP}" -H "X-Forge-Nex-Key: ${KEY}")"
[ "$code" = "200" ] && exit 0 || { echo "nex-cron ${EP}: HTTP ${code}" >&2; exit 1; }
