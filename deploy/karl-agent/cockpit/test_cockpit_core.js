#!/usr/bin/env node
// Tests des modules core/ du cockpit (RM2889, lot L0) — sans navigateur.
//
// Le test le plus important est le premier : il compare le module DÉPLACÉ à la
// fonction restée dans index.html, sur un jeu d'entrées piégeuses. Tant que la
// cohabitation dure, les deux DOIVENT rendre le même octet — c'est ce qui
// garantit qu'un déplacement n'est pas une réécriture déguisée (§ 15.7).
//
// Lancer : node deploy/karl-agent/cockpit/test_cockpit_core.js
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const vm = require("vm");

const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");

// Extrait une fonction de premier niveau en équilibrant ses accolades : la
// forme d'écriture (une ligne ou vingt) ne doit pas décider du test.
function fromIndex(name) {
  const start = html.search(new RegExp(`^function ${name}\\(`, "m"));
  assert(start >= 0, `${name} introuvable dans index.html`);
  let depth = 0, seen = false, end = start;
  for (let i = start; i < html.length; i++) {
    const c = html[i];
    if (c === "{") { depth++; seen = true; }
    else if (c === "}") { depth--; if (seen && depth === 0) { end = i + 1; break; } }
  }
  return vm.runInNewContext("(" + html.slice(start, end) + ")");
}

const CAS = ["", null, undefined, "simple", "<b>gras</b>", 'guillemet "double"',
  "apostrophe 'simple'", "antislash \\ et \\\\", "& esperluette", "a<b>&\"'c\\d",
  "accentué : é à ù ç", "émoji 🙂", 0, 42, "  espaces  ", "<script>alert(1)</script>"];

(async () => {
  const H = await import(path.join(DIR, "src/core/html.js"));
  const E = await import(path.join(DIR, "src/core/endpoints.js"));

  // — 1. le déplacement n'a rien changé —
  for (const name of ["esc", "jarg"]) {
    const legacy = fromIndex(name);
    for (const v of CAS) {
      assert.strictEqual(H[name](v), legacy(v),
        `${name}(${JSON.stringify(v)}) diverge entre index.html et core/html.js`);
    }
  }
  console.log(`✓ esc et jarg identiques à index.html sur ${CAS.length} cas`);

  // — 2. jarg protège bien un handler inline en guillemets doubles —
  //      (le piège documenté : JSON.stringify refermerait l'attribut)
  const arg = H.jarg('il a dit "bonjour" et c\'est tout');
  assert(!arg.slice(1, -1).includes('"'), "jarg laisse passer un guillemet double");
  assert(arg.startsWith("'") && arg.endsWith("'"), "jarg doit rendre des simples");
  console.log("✓ jarg ne peut pas refermer un attribut HTML");

  // — 3. html : échappe par défaut, raw() seul fait exception —
  assert.strictEqual(String(H.html`<p>${"<b>"}</p>`), "<p>&lt;b&gt;</p>");
  assert.strictEqual(String(H.html`${H.raw("<i>ok</i>")}`), "<i>ok</i>");
  assert.strictEqual(String(H.html`${null}${undefined}${false}`), "");
  assert.strictEqual(String(H.html`${[1, 2]}`), "12");
  assert.strictEqual(String(H.html`${[H.html`<li>${"<x>"}</li>`]}`), "<li>&lt;x&gt;</li>");
  assert(H.isSafe(H.html`x`) && H.isSafe(H.raw("x")) && !H.isSafe("x"));
  console.log("✓ html : échappement par défaut, raw() et tableaux");

  // — 4. attrs : omission des valeurs vides, échappement des valeurs —
  assert.strictEqual(String(H.attrs({ id: "a", hidden: true, x: null, y: false })), 'id="a" hidden');
  assert.strictEqual(String(H.attrs({ t: 'a"b' })), 't="a&quot;b"');
  console.log("✓ attrs : omission et échappement");

  // — 5. endpoints : la table couvre la carte, et reste injective —
  const tsv = fs.readFileSync(path.join(DIR, "MIGRATION-ROUTES.tsv"), "utf8")
    .trim().split("\n").slice(1).map(l => l.split("\t"));
  const currents = new Set(Object.values(E.ROUTES).map(r => r.current));
  for (const [cur] of tsv) {
    assert(currents.has(cur), `route ${cur} absente de core/endpoints.js`);
  }
  assert.strictEqual(Object.keys(E.ROUTES).length, tsv.length,
    "endpoints.js et MIGRATION-ROUTES.tsv ont divergé — régénérer");
  assert.strictEqual(E.route("auth.login"), "/auth/login");
  assert.strictEqual(E.targetRoute("auth.login"), "/api/auth/login");
  assert.throws(() => E.route("nexistepas"), /route inconnue/);
  console.log(`✓ endpoints : ${tsv.length} routes, nommage injectif`);

  console.log("\nTous les tests core/ passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
