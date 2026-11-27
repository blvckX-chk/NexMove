// Extrait la logique de bandeau de web/index.html et l'exécute sur les dates passées en
// argument. On évalue le code RÉELLEMENT servi au visiteur : une réimplémentation en Python
// testerait une copie, et une copie peut rester juste pendant que l'original dérive.
//
// Sortie : { campagnes: [...], choix: { "AAAA-MM-JJ": {...}|null },
//            ordre: { "AAAA-MM-JJ": [ids dans l'ordre d'affichage] }, iso_local_minuit }
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

// Chaque fonction est extraite jusqu'à sa ligne de fermeture « }» indentée de 4 espaces.
function fonction(nom, params) {
  const re = new RegExp('function ' + nom + '\\(' + params + '\\)\\{[\\s\\S]*?\\n {4}\\}');
  return bloc(re, 'function ' + nom);
}

const src = [
  bloc(/var CAMPAGNES = \[[\s\S]*?\n {4}\];/, 'var CAMPAGNES'),
  fonction('isoLocal', 'd'),
  fonction('joursRestants', 'iso, fin'),
  bloc(/var RANG = \{[^\n]*\};/, 'var RANG'),
  fonction('typeDe', 'c'),
  fonction('cleTri', 'c'),
  fonction('entrelacer', 'items'),
  fonction('campagnesActives', 'liste, iso'),
  fonction('choisirCampagne', 'liste, iso'),
].join('\n');

const dates = process.argv.slice(2);

// Tout se passe dans l'eval : les déclarations qu'il crée ne sont pas visibles du code
// analysé à l'extérieur.
const prog = src + `
;(function(){
  var out = { campagnes: [], choix: {}, ordre: {} };
  for (var i = 0; i < CAMPAGNES.length; i++) {
    var c = CAMPAGNES[i];
    out.campagnes.push({ id: c.id, pays: c.pays || null, type: c.type || 'ouvert',
                         du: c.du, au: c.au, ouvre: c.ouvre || null,
                         txt: c.txt, pill: c.pill || null });
  }
  var dates = ${JSON.stringify(dates)};
  for (var j = 0; j < dates.length; j++) {
    var d = dates[j], k = choisirCampagne(CAMPAGNES, d);
    out.choix[d] = k ? { id: k.id, jours: joursRestants(d, k.au) } : null;
    out.ordre[d] = campagnesActives(CAMPAGNES, d).map(function(x){ return x.id; });
  }
  // isoLocal doit rendre la date LOCALE, pas la date UTC.
  out.iso_local_minuit = isoLocal(new Date(2027, 0, 15, 0, 30, 0));
  // L'alternance des pays, testée sur une liste construite pour l'éprouver.
  out.entrelace = entrelacer([
    {id:'a', pays:'France'}, {id:'b', pays:'France'}, {id:'c', pays:'Turquie'}, {id:'d', pays:'France'}
  ]).map(function(x){ return x.id; });
  return JSON.stringify(out);
})()`;

console.log(eval(prog));
