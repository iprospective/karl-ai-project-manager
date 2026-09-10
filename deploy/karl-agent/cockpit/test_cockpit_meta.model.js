#!/usr/bin/env node
// Tests de l'encart ℹ — MODÈLE et DÉPÔT (RM3021, scindé de test_cockpit_meta.js) : tickets d'une session (RM2673), journal découpé (RM2797),
// cval/formats (RM2714), une requête par projet et workspace par ticket (TicketMetaRepository).
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { settle, fakeElement, JOURNAL, S, U, R } = require("./test_cockpit_meta.helpers.js");
(async () => {
  const M = await import(path.join(DIR, "src/modules/meta/ticketMeta.js"));
  const { TicketMetaRepository } = await import(path.join(DIR, "src/modules/meta/TicketMetaRepository.js"));

  // — RM2673 : les tickets d'une session, toutes sources —
  const REG = { branches: ["2673-ergonomie-pm", "sans-ticket"], worktrees: ["/w/appli/envs/appli-rm2605"] };
  const WL = { todo: [{ ref: "RM2661" }], waiting: [{ ref: "RM2663" }], done: [{ ref: "RM2673" }], unknown: [{ ref: "chantier-libre" }] };
  assert.deepStrictEqual(M.ticketsOfSession("2673", REG, null), ["2673", "2605"]); assert.deepStrictEqual(M.ticketsOfSession("calymix", null, WL), ["2661", "2663", "2673"]);
  assert.deepStrictEqual(M.ticketsOfSession("2673", REG, WL), ["2673", "2605", "2661", "2663"]); assert.deepStrictEqual(M.ticketsOfSession("calymix", null, null), []);
  assert.deepStrictEqual(M.ticketsOfSession("calymix", null, { todo: [{ ref: "libre" }] }), []); assert.deepStrictEqual(M.ticketsOfSession("calymix", null, { mep: [{ ref: "RM2860" }] }), ["2860"], "RM2860 : « mep » compris");
  // — RM2797 : journal structuré ; RM2714 : cval ; formats —
  const ent = M.logEntries(JOURNAL); assert.strictEqual(ent.length, 2); assert.strictEqual(ent[0].ts, "2026-08-22T20:04"); assert.strictEqual(ent[0].title, "report → Redmine"); assert(ent[1].body.includes("détail sur deux lignes") && !ent[0].body.includes("##"));
  assert.deepEqual(M.logEntries(""), []); assert.deepEqual(M.logEntries(null), []); assert.strictEqual(M.logEntries("juste du texte\nsans en-tête").length, 1); assert.strictEqual(M.logEntries("## titre sans horodatage")[0].title, "titre sans horodatage"); assert.strictEqual(M.logEntries("## titre sans horodatage")[0].ts, "");
  for (const v of ["null", "~", "None", null]) assert.strictEqual(M.cval(v), ""); assert.strictEqual(M.cval("  x  "), "x");
  assert.strictEqual(M.fmtTokens(1234567), "1.2 M"); assert.strictEqual(M.fmtTokens(1500), "2 k"); assert.strictEqual(M.fmtTokens(null), "—"); assert.strictEqual(M.fmtMin(75), "1 h 15"); assert.strictEqual(M.fmtMin(9), "9 min"); assert.strictEqual(M.tmuxName("42"), "karl-RM42"); assert.strictEqual(M.tmuxName("slug"), "karl-slug");
  assert.strictEqual(M.facetOf("conso"), "conso"); assert.strictEqual(M.facetOf("zzz"), "detail"); assert.deepStrictEqual(M.FACETS.map(f => f[0]), ["detail", "desc", "log", "conso", "workspace"]);
  console.log("✓ modèle (RM2673/2797/2714) : tickets d'une session sans doublon, journal découpé, valeurs YAML nulles filtrées");

  const A = await import(path.join(DIR, "src/core/api.js")); let calls = []; const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => { calls.push(String(url)); return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => (/workspace-status/.test(url) ? { is_git: true, branch: "b", clean: false, dirty: 2, ahead: 1 } : { name: "Boutique" }), text: async () => "{}" }; };
  const repo = new TicketMetaRepository(); let loaded = 0;
  assert.strictEqual(repo.projectCard("acme", "shop", () => loaded++), null, "première demande : en vol"); assert.strictEqual(repo.projectCard("acme", "shop"), null, "…redemandée pendant le vol : pas de second appel");
  await settle(); assert.strictEqual(loaded, 1); assert.deepStrictEqual(repo.projectCard("acme", "shop"), { name: "Boutique" }); assert.strictEqual(calls.filter(u => /\/project\//.test(u)).length, 1, "UNE requête par projet");
  assert.strictEqual(repo.workspace("42"), undefined); assert.strictEqual(await repo.refreshWorkspace("slug"), null, "slug : pas de ticket, pas de requête"); const ws = await repo.refreshWorkspace("42"); assert(ws.is_git && repo.workspace("42") === ws);
  globalThis.fetch = realFetch;
  console.log("✓ client/projet (RM2614/2714) : situé sans attendre le réseau, une requête par projet, workspace par ticket");
  console.log("\nTous les tests du modèle de l'encart passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
