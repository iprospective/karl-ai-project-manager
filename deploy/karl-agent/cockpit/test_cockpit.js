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

// — 3. tqMatch (RM2315) : recherche mots-clés dans la file « à tester » —
const fq = />>> tqMatch[\s\S]*?(function tqMatch[\s\S]*?)\n\/\/ <<< tqMatch/.exec(html);
assert(fq, "marqueurs >>> tqMatch / <<< tqMatch introuvables");
const tqMatch = vm.runInNewContext("(" + fq[1] + ")");

const entry = {
  rm_id: "2302", title: "Améliorations ergonomiques design cockpit",
  client: "iprospective", project: "pm-ai-agents", status: "a_tester_demandeur",
  branch: "2302-ameliorations-ergonomiques-desogn-cockpit",
  env: "ai-project-management-rm2302", tags: ["cockpit", "ux"],
};
assert(tqMatch(entry, ""), "requête vide → tout passe");
assert(tqMatch(entry, "   "), "requête blanche → tout passe");
assert(tqMatch(entry, "2302"), "match sur l'id nu");
assert(tqMatch(entry, "RM2302"), "match sur l'id préfixé RM");
assert(tqMatch(entry, "COCKPIT"), "insensible à la casse");
assert(tqMatch(entry, "ameliorations"), "insensible aux accents (améliorations)");
assert(tqMatch(entry, "cockpit ergonomiques"), "multi-mots = ET (les deux présents)");
assert(!tqMatch(entry, "cockpit prestashop"), "multi-mots = ET (un mot absent → rejet)");
assert(tqMatch(entry, "pm-ai-agents"), "match sur client/projet");
assert(tqMatch(entry, "desogn"), "match sur la branche");
assert(tqMatch(entry, "ux"), "match sur un tag");
assert(!tqMatch({ rm_id: "7", title: null, tags: null }, "cockpit"), "champs nuls → pas de crash, rejet");
console.log("✓ tqMatch (RM2315) : mots-clés, casse/accents, ET multi-mots");

// — 4. nextAttentionId (RM2302) —
const fa = />>> nextAttentionId[\s\S]*?(function nextAttentionId[\s\S]*?)\n\/\/ <<< nextAttentionId/.exec(html);
assert(fa, "marqueurs >>> nextAttentionId / <<< nextAttentionId introuvables");
const nextAttentionId = vm.runInNewContext("(" + fa[1] + ")");

const flat = [
  { rm_id: "1", state: "working" },
  { rm_id: "2", state: "attention" },
  { rm_id: "3", state: "idle" },
  { rm_id: "4", state: "attention" },
];
assert.strictEqual(nextAttentionId([], null), null, "liste vide → null");
assert.strictEqual(nextAttentionId([{ rm_id: "1", state: "idle" }], null), null, "aucune attention → null");
assert.strictEqual(nextAttentionId(flat, null), "2", "rien d'attaché → première attention");
assert.strictEqual(nextAttentionId(flat, "1"), "2", "attaché hors attention → première attention");
assert.strictEqual(nextAttentionId(flat, "2"), "4", "attaché sur la 1re attention → la suivante");
assert.strictEqual(nextAttentionId(flat, "4"), "2", "dernière attention → cycle vers la première");
console.log("✓ nextAttentionId (RM2302) : cycle sur les sessions en attention");

console.log("OK — tous les tests cockpit passent");
