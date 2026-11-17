#!/usr/bin/env bash
# Génère tout le set visuel NexMove dans brand/out/ (et l'og.png de la vitrine).
# Prérequis : node + playwright. Le vrai logo doit être dans brand/assets/mark.png
# (sinon un emplacement « MARQUE N » est rendu à la place — jamais de faux logo).
set -euo pipefail
cd "$(dirname "$0")/.."            # -> brand/
PORT=${PORT:-8799}
python3 -m http.server "$PORT" >/dev/null 2>&1 &
SRV=$!; trap 'kill $SRV 2>/dev/null' EXIT; sleep 1
B="http://localhost:$PORT/templates"
enc(){ python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$1"; }
post(){ # $1 sortie  $2 kicker  $3 titre  $4 texte  $5 folio
  node tools/shot.js "$B/post.html?k=$(enc "$2")&t=$(enc "$3")&b=$(enc "$4")&n=$(enc "$5")" "out/$1" 1080 1350
}
mkdir -p out
node tools/shot.js "$B/hero.html" out/HERO_v2.png 1080 1080
DSF=1 node tools/shot.js "$B/og.html" out/og.png 1200 630
post POST_01_constat.png  "Le constat" \
  "Tu postules partout.|*Personne* ne répond." \
  "NexMove lit ton CV, trouve de vraies opportunités et note chacune selon ton profil. Tu sais où postuler, et pourquoi." "01 / 03"
post POST_02_testeurs.png "Programme testeurs · places limitées" \
  "Deviens testeur.|Gagne un accès *Premium*." \
  "Utilise le bot à fond, signale ce qui coince avec /bug, et reçois un code Premium offert." "02 / 03"
post POST_03_score.png    "Comment ça marche" \
  "Ton CV, noté|*offre par offre*." \
  "Pour chaque offre : un score expliqué, tes points forts et ce qu'il reste à renforcer. Puis la lettre et le CV adaptés, prêts à envoyer." "03 / 03"
if [ -f assets/mark.png ]; then cp out/og.png ../web/og.png && echo "web/og.png mis à jour"; else echo "⚠️  assets/mark.png absent : web/og.png NON remplacé"; fi
