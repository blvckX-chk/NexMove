#!/usr/bin/env bash
# deploy.sh — déploie la dernière version de NexMove sur le VPS.
# Usage : depuis le dossier du projet -> ./scripts/deploy.sh
# Fait : git pull (main) -> rebuild Docker -> vérifie la santé de l'API.
set -euo pipefail

# Se placer à la racine du projet (dossier parent de scripts/)
cd "$(dirname "$0")/.."

BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-https://api-nexmove.blvckunlimited.space/health}"

echo "➤ 1/3  Mise à jour du code (origin/$BRANCH)…"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
echo "   version déployée : $(git rev-parse --short HEAD)"

echo "➤ 2/3  Reconstruction et redémarrage des conteneurs…"
docker compose up -d --build

echo "➤ 3/3  Vérification de la santé de l'API…"
ok=0
for i in 1 2 3 4 5 6; do
  sleep 5
  if curl -fsS "$HEALTH_URL" >/tmp/nex_health.json 2>/dev/null; then
    ok=1
    break
  fi
  echo "   (tentative $i : pas encore prêt…)"
done

if [ "$ok" = "1" ]; then
  echo "✅ Déploiement terminé. Réponse /health :"
  cat /tmp/nex_health.json; echo
  if grep -q '"whatsapp_configured":[[:space:]]*true' /tmp/nex_health.json; then
    echo "   WhatsApp : configuré ✓"
  fi
else
  echo "⚠️  L'API ne répond pas encore sur $HEALTH_URL."
  echo "   Regarde les logs :  docker compose logs --tail=50 api"
  exit 1
fi
