#!/usr/bin/env node
// Tests du cockpit (RM2283) — sans navigateur ni dépendance :
//   1. le <script> inline de index.html est syntaxiquement valide ;
//   2. computeGroups (fonction pure, extraite par ses marqueurs >>> <<<) :
//      groupement par client/projet, fallback resolveCache, « divers »,
//      compteurs d'états, tri attention > activité récente > alpha.
// Lancer : node deploy/karl-agent/cockpit/test_cockpit.js
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const vm = require("vm");

const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");

// — 1. syntaxe du script inline —
const m = /<script>([\s\S]*?)<\/script>/.exec(html);
assert(m, "bloc <script> introuvable dans index.html");
new vm.Script(m[1], { filename: "index.html<script>" });   // jette si erreur de syntaxe
console.log("✓ syntaxe du <script> inline");

// — 2. computeGroups —
const fm = />>> computeGroups[\s\S]*?(function computeGroups[\s\S]*?)\n\/\/ <<< computeGroups/.exec(html);
assert(fm, "marqueurs >>> computeGroups / <<< computeGroups introuvables");
const computeGroups = vm.runInNewContext("(" + fm[1] + ")");

// groupement : jonction directe, fallback /resolve, divers
const sessions = [
  { rm_id: "1", client: "acme", project: "shop", state: "working", created: 100 },
  { rm_id: "2", client: "acme", project: "shop", state: "idle", created: 200 },
  { rm_id: "3", state: "attention", created: 50 },              // via resolveCache
  { rm_id: "4", is_ticket: false, state: "working", created: 300 }, // non PM-tracké
];
const rcache = { "3": { found: true, client: "beta", project: "api" } };
const { keys, groups, counts } = computeGroups(sessions, rcache);

assert.deepStrictEqual(new Set(keys), new Set(["acme/shop", "beta/api", "divers"]), "clés de groupes");
assert.strictEqual(groups.get("acme/shop").length, 2, "2 sessions acme/shop");
assert.strictEqual(groups.get("beta/api")[0].rm_id, "3", "fallback resolveCache");
assert.strictEqual(groups.get("divers")[0].rm_id, "4", "non résolu → divers");
console.log("✓ groupement par client/projet (+ fallback, + divers)");

// compteurs d'états
assert.deepStrictEqual({ ...counts }, { total: 4, attention: 1, idle: 1, working: 2 }, "compteurs");
console.log("✓ compteurs total/attention/idle/working");

// tri : le groupe avec attention passe devant, même plus ancien
assert.strictEqual(keys[0], "beta/api", "groupe en attention en tête");
// puis activité récente : divers (created 300) avant acme/shop (200)
assert.strictEqual(keys[1], "divers", "activité récente ensuite");
assert.strictEqual(keys[2], "acme/shop", "le moins récent en dernier");
console.log("✓ tri attention > activité récente > alpha");

// tri alpha à égalité (pas d'attention, même created)
const eq = computeGroups([
  { rm_id: "10", client: "zeta", project: "z", state: "working", created: 10 },
  { rm_id: "11", client: "alpha", project: "a", state: "working", created: 10 },
], {});
assert.deepStrictEqual([...eq.keys], ["alpha/a", "zeta/z"], "alpha à égalité");
console.log("✓ tri alphabétique à égalité");

// aucune session
const empty = computeGroups([], {});
assert.deepStrictEqual([...empty.keys], [], "aucun groupe");
assert.strictEqual(empty.counts.total, 0, "total 0");
console.log("✓ liste vide");

// — 3. mdToHtml (RM2309) —
const fmd = />>> mdToHtml[\s\S]*?(function mdToHtml[\s\S]*?)\n\/\/ <<< mdToHtml/.exec(html);
assert(fmd, "marqueurs >>> mdToHtml / <<< mdToHtml introuvables");
const mdToHtml = vm.runInNewContext("(" + fmd[1] + ")");

// sécurité : tout HTML source est échappé, aucun lien javascript:
let h = mdToHtml('<script>alert(1)</script> et <img src=x onerror=y>');
assert(!/<script|<img/.test(h) && h.includes("&lt;script&gt;"), "XSS échappé");
h = mdToHtml("[clic](javascript:alert(1)) et [ok](https://ex.te/p)");
assert(!h.includes('href="javascript:'), "javascript: refusé");
assert(h.includes('href="https://ex.te/p"') && h.includes('rel="noopener"'), "https autorisé");
console.log("✓ mdToHtml : sûreté (échappement + whitelist de liens)");

// structure : titres, listes + cases, code, gras, tableau, citation, hr, frontmatter
h = mdToHtml("---\ntitle: X\n---\n# Titre\n\n## Sous *titre*\n\ntexte **fort** et `code`\n\n- [x] fait\n- [ ] à faire\n1. un\n\n> note\n\n---\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nlet x = '<b>'\n```");
for (const frag of ['<pre class="mdfm">title: X</pre>', "<h1>Titre</h1>", "<h2>Sous <i>titre</i></h2>",
  "<b>fort</b>", "<code>code</code>", "<li>☑ fait</li>", "<li>☐ à faire</li>", "<ol><li>un</li></ol>",
  "<blockquote>note</blockquote>", "<hr>", "<th>a</th>", "<td>2</td>", "<pre>let x = '&lt;b&gt;'</pre>"])
  assert(h.includes(frag), "fragment attendu : " + frag);
assert(h.startsWith('<div class="mdview">'), "wrapper mdview");
console.log("✓ mdToHtml : titres, listes/cases, code, tableau, citation, hr, frontmatter");

// paragraphes multilignes joints, texte simple sans balisage parasite
h = mdToHtml("ligne un\nligne deux\n\nautre para");
assert(h.includes("<p>ligne un ligne deux</p>") && h.includes("<p>autre para</p>"), "paragraphes");
console.log("✓ mdToHtml : paragraphes");

console.log("OK — tous les tests cockpit passent");
