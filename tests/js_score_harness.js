/* Harnais de test : exécute la fonction `score()` de web/orientation.html telle quelle.
 *
 * On ne recopie pas la fonction ici — on l'extrait de la page, sinon la copie dériverait
 * et le test ne vérifierait plus rien. Entrée : une séquence de lettres par ligne sur
 * stdin. Sortie : le code calculé, une ligne par entrée.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const racine = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(racine, "web", "orientation.html"), "utf8");
const data = fs.readFileSync(path.join(racine, "web", "orientation-data.js"), "utf8");

const m = html.match(/function score\(reps\) \{[\s\S]*?\n  \}/);
if (!m) { console.error("fonction score() introuvable dans orientation.html"); process.exit(2); }

const bac = { window: {} };
vm.createContext(bac);
vm.runInContext(data, bac);
vm.runInContext("var D = window.ORIENTATION;\n" + m[0] + "\nwindow.__score = score;", bac);

const lignes = fs.readFileSync(0, "utf8").split("\n").filter((l) => l.length);
console.log(lignes.map((l) => bac.window.__score(l.trim().split(""))).join("\n"));
