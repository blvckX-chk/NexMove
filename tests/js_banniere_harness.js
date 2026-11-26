// Extrait la logique de bandeau de web/index.html et l'exécute sur les dates
// passées en argument. On évalue le code RÉELLEMENT servi au visiteur : une
// réimplémentation en Python testerait une copie, et une copie peut rester juste
// pendant que l'original dérive.
//
// Sortie : un objet JSON { campagnes: [...], choix: { "AAAA-MM-JJ": {...}|null } }
'use strict';
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');

function bloc(re, nom) {
  const m = html.match(re);
  if (!m) {
    console.error('INTROUVABLE dans web/index.html : ' + nom);
    process.exit(2);
  }
  return m[0];
}

const src = [
  bloc(/var CAMPAGNES = \[[\s\S]*?\n {4}\];/, 'var CAMPAGNES'),
  bloc(/function isoLocal\(d\)\{[\s\S]*?\n {4}\}/, 'function isoLocal'),
  bloc(/function choisirCampagne\(liste, iso\)\{[\s\S]*?\n {4}\}/, 'function choisirCampagne'),
  bloc(/function joursRestants\(iso, fin\)\{[\s\S]*?\n {4}\}/, 'function joursRestants'),
].join('\n');

const dates = process.argv.slice(2);

// Tout se passe dans l'eval : les déclarations qu'il crée ne sont pas visibles
// du code analysé à l'extérieur.
const prog = src + `
;(function(){
  var out = { campagnes: [], choix: {} };
  for (var i = 0; i < CAMPAGNES.length; i++) {
    var c = CAMPAGNES[i];
    out.campagnes.push({ id: c.id, du: c.du, au: c.au, txt: c.txt, pill: c.pill || null });
  }
  var dates = ${JSON.stringify(dates)};
  for (var j = 0; j < dates.length; j++) {
    var d = dates[j], k = choisirCampagne(CAMPAGNES, d);
    out.choix[d] = k ? { id: k.id, jours: joursRestants(d, k.au) } : null;
  }
  // isoLocal doit rendre la date LOCALE, pas la date UTC.
  out.iso_local_minuit = isoLocal(new Date(2027, 0, 15, 0, 30, 0));
  return JSON.stringify(out);
})()`;

console.log(eval(prog));
