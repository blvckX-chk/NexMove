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
python3 tools/build_print.py                        # QR + coordonnées (contact.json) -> gabarits imprimés
node tools/shot.js "$B/hero.html" out/HERO_v2.png 1080 1080
DSF=1 node tools/shot.js "$B/og.html" out/og.png 1200 630
# Set de campagne de décembre 2026 — 5 posts. Textes vérifiés le 27/11/2026 :
# - POST_02 remplacé : l'ancien disait « places limitées » (faux, le programme est ouvert à tous
#   jusqu'au 1er mars 2027) et promettait « un code Premium offert » (périmé : /testeur ouvre tout).
# - Aucun chiffre, aucun témoignage, aucune rareté inventés (règle de brand/README.md).
post POST_01_constat.png  "Le constat" \
  "Tu postules partout.|*Personne* ne répond." \
  "NexMove lit ton CV, trouve de vraies opportunités et note chacune selon ton profil. Tu sais où postuler, et pourquoi." "01 / 05"
post POST_02_testeurs.png "Programme testeurs · ouvert à tous" \
  "Tout est ouvert|jusqu'au *1er mars*." \
  "Jusqu'au 1er mars 2027 : analyse de CV, lettres, préparation d'entretien, recherche d'offres, sans quota ni carte bancaire. En échange, une seule chose : dire quand ça ne marche pas. Tape /testeur." "02 / 05"
post POST_03_score.png    "Comment ça marche" \
  "Ton CV, noté|*offre par offre*." \
  "Pour chaque offre : un score expliqué, tes points forts et ce qu'il reste à renforcer. Puis la lettre et le CV adaptés, prêts à envoyer." "03 / 05"
post POST_04_regarde.png  "Avant de te lancer" \
  "Regarde-le|*travailler*." \
  "Trois vraies conversations, de bout en bout : quand tu ne sais pas par où commencer, quand tu envoies ton CV, quand on te demande de l'argent. Puis décide. Tout est sur le site, page « Comment ça marche »." "04 / 05"
post POST_05_visa.png     "À faire circuler" \
  "Un visa|ne s'achète *pas*." \
  "Un vrai employeur, une vraie école, une vraie ambassade ne te demandent jamais d'argent pour un emploi, un visa ou une admission. Les seuls frais se paient au guichet officiel, avec un reçu à ton nom." "05 / 05"
# Versions PDF à texte vectoriel des visuels réseaux (importables et MODIFIABLES dans Canva)
mkdir -p out/pdf
mm(){ python3 -c "print(round($1*25.4/96,2))"; }
node tools/print.js "$B/hero.html" out/pdf/HERO_v2 $(mm 1080) $(mm 1080) >/dev/null
node tools/print.js "$B/og.html" out/pdf/og $(mm 1200) $(mm 630) >/dev/null
postpdf(){ node tools/print.js "$B/post.html?k=$(enc "$2")&t=$(enc "$3")&b=$(enc "$4")&n=$(enc "$5")" "out/pdf/$1" $(mm 1080) $(mm 1350) >/dev/null; }
postpdf POST_01_constat  "Le constat" "Tu postules partout.|*Personne* ne répond." "NexMove lit ton CV, trouve de vraies opportunités et note chacune selon ton profil. Tu sais où postuler, et pourquoi." "01 / 05"
postpdf POST_02_testeurs "Programme testeurs · ouvert à tous" "Tout est ouvert|jusqu'au *1er mars*." "Jusqu'au 1er mars 2027 : analyse de CV, lettres, préparation d'entretien, recherche d'offres, sans quota ni carte bancaire. En échange, une seule chose : dire quand ça ne marche pas. Tape /testeur." "02 / 05"
postpdf POST_03_score    "Comment ça marche" "Ton CV, noté|*offre par offre*." "Pour chaque offre : un score expliqué, tes points forts et ce qu'il reste à renforcer. Puis la lettre et le CV adaptés, prêts à envoyer." "03 / 05"
postpdf POST_04_regarde  "Avant de te lancer" "Regarde-le|*travailler*." "Trois vraies conversations, de bout en bout : quand tu ne sais pas par où commencer, quand tu envoies ton CV, quand on te demande de l'argent. Puis décide. Tout est sur le site, page « Comment ça marche »." "04 / 05"
postpdf POST_05_visa     "À faire circuler" "Un visa|ne s'achète *pas*." "Un vrai employeur, une vraie école, une vraie ambassade ne te demandent jamais d'argent pour un emploi, un visa ou une admission. Les seuls frais se paient au guichet officiel, avec un reçu à ton nom." "05 / 05"
# Supports imprimés (PDF prêt à imprimer + aperçus 300 DPI)
node tools/print.js "$B/affiche-a4.html" out/affiche-a4 216 303
node tools/print.js "$B/carte-visite.html" out/carte-visite 91 61 .card
if [ -f assets/mark.png ]; then
  cp out/og.png ../web/og.png && echo "web/og.png mis à jour"
  TRANSPARENT=1 DSF=1 node tools/shot.js "$B/icon.html" out/icon-1000.png 1000 1000
  python3 tools/make_icons.py
else
  echo "⚠️  assets/mark.png absent : og.png et icônes de la vitrine NON remplacés"
fi
