#!/usr/bin/env node
// Tests RM3138 — l'invariant de la colonne de gauche.
//
// Le bug : une balise fermante orpheline refermait `.lbody` juste avant
// `#lp-mail`, qui se retrouvait DEHORS. `switchPanel` commence par
// `if (!h.lbody.querySelector("#lp-" + name)) name = "running"` — la garde qui
// protège d'un nom inconnu — et retombait donc sur « running » : cliquer
// « 📧 emails » ne faisait rien. Le navigateur corrige l'imbrication en silence,
// la page s'affichait normalement, et RIEN ne signalait l'erreur.
//
// Ce qui est protégé ici :
//   1. tout bouton `data-panel="X"` a son `#lp-X`, et ce panneau est DANS
//      `.lbody` — la seule chose que `switchPanel` sache regarder ;
//   2. aucun `.lpanel` ne traîne hors de `.lbody` : `.lpanel { display:none }`
//      est global, un panneau égaré resterait invisible pour toujours ;
//   3. l'imbrication des `<div>` de la colonne est équilibrée — c'est la cause,
//      et elle se mesure, elle ne s'inspecte pas à l'œil.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert");
const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");

// Les commentaires peuvent contenir des balises citées (celui de RM3138 en cite) :
// les retirer AVANT de compter, sinon la garde se piège elle-même.
const propre = html.replace(/<!--[\s\S]*?-->/g, (m) => "\n".repeat((m.match(/\n/g) || []).length));
const lignes = propre.split("\n");

// — la tranche exacte de .lbody, par comptage —
const debut = lignes.findIndex(l => /<div class="lbody"/.test(l));
assert(debut >= 0, "`.lbody` introuvable dans index.html");
let prof = 0, fin = -1;
for (let i = debut; i < lignes.length; i++) {
  prof += (lignes[i].match(/<div\b/g) || []).length - (lignes[i].match(/<\/div>/g) || []).length;
  if (prof === 0) { fin = i; break; }
  assert(prof > 0, `imbrication négative ligne ${i + 1} : une balise fermante en trop dans .lbody`);
}
assert(fin > debut, "`.lbody` ne se referme jamais : imbrication cassée");
const dansLbody = lignes.slice(debut, fin + 1).join("\n");
const idsDedans = [...dansLbody.matchAll(/<div class="lpanel" id="lp-([a-z-]+)"/g)].map(m => m[1]);

// — 1. chaque bouton a son panneau, DANS .lbody —
const boutons = [...propre.matchAll(/data-panel="([a-z-]+)"/g)].map(m => m[1]);
assert(boutons.length >= 6, `attendu au moins 6 boutons de panneau, vus ${boutons.length}`);
for (const b of boutons) {
  assert(idsDedans.includes(b),
    `RM3138 : le bouton « ${b} » n'a pas de #lp-${b} DANS .lbody — switchPanel retombera sur « running » et le clic ne fera rien`);
}
console.log(`✓ ${boutons.length} boutons de panneau, chacun avec son #lp-… dans .lbody`);

// — 2. aucun panneau égaré hors de .lbody —
const tous = [...propre.matchAll(/<div class="lpanel" id="lp-([a-z-]+)"/g)].map(m => m[1]);
const dehors = tous.filter(id => !idsDedans.includes(id));
assert.deepStrictEqual(dehors, [],
  `RM3138 : panneau(x) hors de .lbody : ${dehors.join(", ")} — « .lpanel { display:none } » est global, ils resteraient invisibles`);
console.log(`✓ les ${tous.length} .lpanel vivent tous dans .lbody`);

// — 3. le cas précis qui a cassé : emails —
assert(idsDedans.includes("mail"), "le panneau emails doit être dans .lbody");
assert(/data-panel="mail"/.test(propre), "le bouton emails doit exister");
console.log("✓ emails (RM3138) : bouton et panneau, du bon côté de .lbody");

// — 4. la colonne gauche entière est équilibrée —
const gauche = propre.slice(propre.indexOf('<section class="left"'));
const finSection = gauche.indexOf("</section>");
assert(finSection > 0, "`<section class=\"left\">` ne se referme pas");
const bloc = gauche.slice(0, finSection);
const ouv = (bloc.match(/<div\b/g) || []).length, fer = (bloc.match(/<\/div>/g) || []).length;
assert.strictEqual(ouv, fer,
  `colonne gauche déséquilibrée : ${ouv} <div> pour ${fer} fermetures — une balise en trop mange la fermeture de la section`);
console.log(`✓ colonne gauche équilibrée (${ouv} div ouverts, autant fermés)`);
