#!/usr/bin/env node
// Tests RM2714 (repris pour la refonte RM2889, L6) — le cockpit s'EXÉCUTE, pas seulement : il compile.
//
// Avant la refonte, ce harnais évaluait le <script> inline entier dans un DOM minimal pour attraper les identifiants hors portée
// (ReferenceError à l'exécution, invisible aux tests purs). Le script inline a disparu : la page ne porte plus que le boot de thème
// (avant le premier paint) et charge `src/boot.js` en module. Ce que ce harnais vérifie désormais :
//   1. index.html n'a plus qu'UN bloc inline (theme-boot), qui s'évalue et pose data-theme ;
//   2. aucun handler inline (on*) ne subsiste dans la page — tout geste passe par une délégation posée par un contrôleur ;
//   3. TOUS les modules de src/ (sauf boot.js, qui touche le document) s'importent sous node nu : un import cassé, un export
//      manquant ou un accès au DOM à l'import = page morte au chargement ;
//   4. chaque import statique de boot.js pointe un fichier existant et un export existant.
// Lancer : node deploy/karl-agent/cockpit/test_cockpit_runtime.js
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const vm = require("vm"); const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
const walkExt = (d, ext) => fs.readdirSync(d, { withFileTypes: true }).flatMap(x => x.isDirectory() ? walkExt(path.join(d, x.name), ext) : (x.name.endsWith(ext) ? [path.join(d, x.name)] : []));

// 1. un seul inline : le boot de thème
const blocks = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].filter(b => b[1].trim());   // les <script src> externes n'ont pas de corps
assert.strictEqual(blocks.length, 1, "un seul <script> inline attendu (theme-boot)"); assert(/id="theme-boot"/.test(blocks[0][0]), "…et c'est le boot de thème");
const docEl = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
const sb = { window: {}, document: { documentElement: docEl }, localStorage: { getItem: () => null }, matchMedia: () => ({ matches: false, addEventListener() {} }) }; sb.window = sb;
vm.runInNewContext(blocks[0][1], sb); assert.strictEqual(docEl.attrs["data-theme"], "dark", "le thème est posé avant le premier paint (défaut historique : sombre)");
assert(/<script type="module" src="\/static\/src\/boot\.js"><\/script>/.test(html), "la page charge src/boot.js en module");
console.log("✓ index.html : un seul inline (theme-boot), qui s'évalue ; boot.js en module");
const metaV = /<meta name="karl-cockpit-version" content="([^"]+)">/.exec(html); assert(metaV, "la page porte sa version");

// 2. plus aucun handler inline
assert(!/\son(click|change|input|keydown|keyup|submit|toggle|load)="/.test(html), "plus aucun on* dans la page (RM2889 : délégation par data-action / data-cmd / data-link)");
console.log("✓ aucun handler inline dans la page");
// 2b. RM3012 : le style est compilé (src/styles/main.scss → cockpit.css) ; un build périmé est refusé sans exiger sass
{ const crypto = require("crypto"); const scss = walkExt(path.join(DIR, "src"), ".scss").sort(); const h = crypto.createHash("sha256");
  for (const f of scss) { h.update(path.relative(DIR, f)); h.update("\0"); h.update(fs.readFileSync(f)); h.update("\0"); }
  const css = fs.readFileSync(path.join(DIR, "cockpit.css"), "utf8"); const m = /empreinte des sources scss : ([0-9a-f]{16}) \((\d+) fichiers\)/.exec(css);
  assert(m, "cockpit.css doit porter l'empreinte de ses sources (npm run build:css)");
  assert.strictEqual(m[1], h.digest("hex").slice(0, 16), "cockpit.css est PÉRIMÉ par rapport à src/**/*.scss — relance `npm run build:css` (deploy/karl-agent/cockpit)");
  assert(!/<style>/.test(html) && /<link rel="stylesheet" href="\/static\/cockpit\.css">/.test(html), "la page charge cockpit.css, sans <style> inline");
  assert(scss.length >= 20 && fs.existsSync(path.join(DIR, "src/styles/main.scss")), "un fichier scss par module + tokens + base + main");
  console.log("✓ cockpit.css à jour (" + scss.length + " sources scss, empreinte " + m[1] + ")"); }

// 3. + 4. les modules s'importent ; boot.js référence des fichiers et des exports existants
const walk = (d) => walkExt(d, ".js");
(async () => {
  const files = walk(path.join(DIR, "src")).filter(f => path.basename(f) !== "boot.js");
  const mods = {};
  for (const f of files) { try { mods[f] = await import(f); } catch (e) { throw new Error(path.relative(DIR, f) + " ne s'importe pas : " + e.message); } }
  console.log("✓ " + files.length + " modules s'importent sous node nu (aucun accès au DOM à l'import, aucun import cassé)");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  let checked = 0;
  for (const m of boot.matchAll(/^import (?:\{([^}]*)\}|\* as (\w+)) from "\.\/([^"]+)";/gm)) {
    const file = path.join(DIR, "src", m[3]); assert(fs.existsSync(file), "boot.js importe un fichier absent : " + m[3]);
    if (m[1]) for (const name of m[1].split(",").map(s => s.trim().split(/\s+as\s+/)[0]).filter(Boolean)) { assert(name in mods[file], "boot.js importe « " + name + " » que " + m[3] + " n'exporte pas"); checked++; }
  }
  assert(checked > 60, "boot.js : imports nommés vérifiés (" + checked + ")");
  assert(!/\blegacy\(|\blexical\(/.test(boot), "boot.js ne lit plus rien du script inline (legacy / lexical ont disparu)");
  assert(/\(async function init\(\)/.test(boot) && /refreshCtl\.start\(\)/.test(boot) && /auth\.boot\(\)/.test(boot), "l'init vit dans boot.js : config, auth, premier tick");
  console.log("✓ boot.js : " + checked + " imports nommés résolus, aucun pont vers le script inline, init en place");
  const { VERSION } = await import(path.join(DIR, "src/core/version.js")); assert.strictEqual(metaV[1], VERSION, "la version de la page et celle du front coïncident"); assert(/version: VERSION/.test(boot), "karl.version exposé"); console.log("✓ version " + VERSION + " (L8)");
  console.log("OK — le cockpit s'exécute sans identifiant hors portée");
})().catch(e => { console.error("ÉCHEC :", e && e.stack ? e.stack : e); process.exit(1); });
