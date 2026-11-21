#!/usr/bin/env bash
# deploy.sh — déploie la dernière version de NexMove sur le VPS.
#
# Modèle de déploiement de ce VPS :
#   - le CODE est suivi par git dans ce repo (ex. ~/infra/nexmove-src)
#   - le DÉPLOIEMENT tourne dans un dossier séparé qui garde .env + data/ (ex. ~/infra/forge-nex-api)
# Le script met à jour le code (git pull), COPIE les fichiers de code vers le dossier de
# déploiement (sans toucher à .env ni data/), puis rebuild le conteneur là-bas.
#
# Déploiement « en place » : si ce repo contient lui-même .env + data/ dans api/, il build ici.
#
# Variables optionnelles :
#   NEXMOVE_DEPLOY_DIR=/chemin   -> force le dossier de déploiement
#   DEPLOY_BRANCH=main
#   HEALTH_URL=https://api-nexmove.blvckunlimited.space/health
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
SRC_API="$ROOT/api"
BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-https://api-nexmove.blvckunlimited.space/health}"

# Fichiers de code à synchroniser (ceux que le Dockerfile COPIE) — JAMAIS .env ni data/.
# TOUS les modules Python (*.py) sont pris automatiquement : un nouveau module (ex. orientation.py)
# n'a plus besoin d'être ajouté à la main ici — l'oubli cassait le démarrage de l'API.
CODE_FILES=(requirements.txt Dockerfile)
for _py in "$SRC_API"/*.py; do
  [ -f "$_py" ] && CODE_FILES+=("$(basename "$_py")")
done

# Deux interrupteurs, pour que la CI puisse rejouer EXACTEMENT ce déploiement sans toucher
# à git ni à un vrai serveur (c'est ce chemin-là qui avait cassé la prod en v3.96) :
#   NEXMOVE_SKIP_GIT=1    -> ne met pas le dépôt à jour (on teste le code déjà présent)
#   NEXMOVE_SKIP_BUILD=1  -> s'arrête après la copie, sans lancer Docker
SKIP_GIT="${NEXMOVE_SKIP_GIT:-0}"
SKIP_BUILD="${NEXMOVE_SKIP_BUILD:-0}"

if [ "$SKIP_GIT" = "1" ]; then
  echo "➤ 1/4  Mise à jour du code IGNORÉE (NEXMOVE_SKIP_GIT=1)."
else
  echo "➤ 1/4  Mise à jour du code (origin/$BRANCH)…"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
  echo "   version du repo : $(git rev-parse --short HEAD)"
fi

echo "➤ 2/4  Choix du dossier de déploiement…"
DEPLOY_DIR="${NEXMOVE_DEPLOY_DIR:-}"
if [ -z "$DEPLOY_DIR" ]; then
  for cand in "$ROOT/../forge-nex-api" "/root/infra/forge-nex-api" "$ROOT"; do
    if [ -f "$cand/docker-compose.yml" ] && [ -f "$cand/.env" ]; then DEPLOY_DIR="$(cd "$cand" && pwd)"; break; fi
    if [ -f "$cand/api/docker-compose.yml" ] && [ -f "$cand/api/.env" ]; then DEPLOY_DIR="$(cd "$cand/api" && pwd)"; break; fi
  done
fi
if [ -z "$DEPLOY_DIR" ]; then
  echo "⚠️  Impossible de trouver un dossier de déploiement contenant .env."
  echo "   Indique-le : NEXMOVE_DEPLOY_DIR=/root/infra/forge-nex-api ./scripts/deploy.sh"
  exit 1
fi
echo "   déploiement vers : $DEPLOY_DIR  (conserve .env + data/)"

if [ "$DEPLOY_DIR" != "$SRC_API" ]; then
  echo "➤ 3/4  Copie du code mis à jour…"
  for f in "${CODE_FILES[@]}"; do
    if [ -f "$SRC_API/$f" ]; then
      cp -f "$SRC_API/$f" "$DEPLOY_DIR/$f"
      echo "   ✓ $f"
    fi
  done
else
  echo "➤ 3/4  Déploiement en place (le repo contient .env)."
fi

if [ "$SKIP_BUILD" = "1" ]; then
  echo "➤ 4/4  Build IGNORÉ (NEXMOVE_SKIP_BUILD=1) · fichiers synchronisés dans $DEPLOY_DIR"
  exit 0
fi

echo "➤ 4/4  Reconstruction et redémarrage du conteneur…"
unset COMPOSE_FILE || true
( cd "$DEPLOY_DIR" && docker compose -f docker-compose.yml up -d --build )

echo "   Vérification de la santé de l'API…"
ok=0
for i in 1 2 3 4 5 6; do
  sleep 5
  if curl -fsS "$HEALTH_URL" >/tmp/nex_health.json 2>/dev/null; then ok=1; break; fi
  echo "   (tentative $i : pas encore prêt…)"
done

if [ "$ok" = "1" ]; then
  echo "✅ Déploiement terminé. Réponse /health :"
  cat /tmp/nex_health.json; echo
  grep -q '"whatsapp_configured":[[:space:]]*true' /tmp/nex_health.json && echo "   WhatsApp : configuré ✓" || true
else
  echo "⚠️  L'API ne répond pas encore sur $HEALTH_URL."
  echo "   Logs :  (cd $DEPLOY_DIR && docker compose logs --tail=50)"
  exit 1
fi
