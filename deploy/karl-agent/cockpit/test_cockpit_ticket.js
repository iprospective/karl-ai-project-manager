#!/usr/bin/env node
// Tests du modèle ticket migré (RM2889) — porte sinceLabel (RM2630), RM2611, mcBanner (RM2384), ticketBusySessions (RM2818),
// et vérifie la logique du dépôt : péremption, dédup en vol (RM2763), verrous.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
(async () => {
  const F = await import(path.join(DIR, "src/models/tickets/ticketFormat.js"));
  const { MergeBanner } = await import(path.join(DIR, "src/views/tickets/MergeBanner.view.js"));
  const { TicketRepository, RESOLVE_TTL_MS } = await import(path.join(DIR, "src/models/tickets/TicketRepository.js"));
  const A = await import(path.join(DIR, "src/core/api.js"));
  const t0 = Date.parse("2026-08-11T12:00");
  assert.strictEqual(F.sinceLabel("2026-08-11T12:00", t0), "à l'instant"); assert.strictEqual(F.sinceLabel("2026-08-11T11:43", t0), "il y a 17 min"); assert.strictEqual(F.sinceLabel("2026-08-11T09:00", t0), "il y a 3 h");
  assert.strictEqual(F.sinceLabel("2026-08-09T12:00", t0), "il y a 2 j"); assert.strictEqual(F.sinceLabel("2026-08-11 11:00", t0), "il y a 1 h"); assert.strictEqual(F.sinceLabel("", t0), ""); assert.strictEqual(F.sinceLabel("pas une date", t0), "");
  assert.strictEqual(F.modelWindow("claude-x", { context_window: 1000000 }, 50000), 1000000); assert.strictEqual(F.modelWindow("claude-x", null, 868000), 1000000); assert.strictEqual(F.modelWindow("claude-opus-4-8", null, 5000), 200000); assert.strictEqual(F.modelWindow("gpt-x", null, 5000), null);
  assert.strictEqual(F.ctxPct(100000, 200000), 50); assert.strictEqual(F.ctxPct(868000, 1000000), 87); assert.strictEqual(F.ctxPct(1000, null), null);
  const tp = F.throughput(600000, 3.0, 0, 3600000); assert(tp && tp.tpm === 10000 && Math.abs(tp.uph - 3.0) < 1e-9); assert.strictEqual(F.throughput(100, 1, 0, 10000), null);
  assert.strictEqual(F.fmtUsd(0.1234), "$0.123"); assert.strictEqual(F.fmtUsd(12.345), "$12.35"); assert.strictEqual(F.fmtRate(null), "?"); assert.strictEqual(F.fmtWin(1000000), "1M"); assert.strictEqual(F.fmtWin(200000), "200k");
  console.log("✓ format (RM2630/RM2611) : âge de version, fenêtre par modèle, % contexte, débit, montants");
  const b = (mc) => String(MergeBanner(mc));
  assert.strictEqual(b(null), ""); assert.strictEqual(b({}), "");
  const bOk = b({ verdict: { level: "ok", headline: "Branche à jour, merge propre" } }); assert(/class="mcbanner mc-ok"/.test(bOk) && /✅/.test(bOk) && /Branche à jour/.test(bOk) && !/mc-advice/.test(bOk));
  const bBlock = b({ mr_url: "https://gitlab.x/mr/1", verdict: { level: "block", headline: "Conflit de merge avec dev (2 fichier(s))", detail: "CHANGELOG.md, src/app.py", advice: "merge dev dans la branche, résous, pousse" } });
  assert(/class="mcbanner mc-block"/.test(bBlock) && /⛔/.test(bBlock) && /mc-advice[^>]*>→ /.test(bBlock) && /CHANGELOG.md/.test(bBlock) && /href="https:\/\/gitlab\.x\/mr\/1"/.test(bBlock));
  const bXss = b({ verdict: { level: "warn", headline: "en retard <b>x</b>" } }); assert(/&lt;b&gt;/.test(bXss) && !/<b>/.test(bXss)); const bUnk = b({ verdict: {} }); assert(/mc-unknown/.test(bUnk) && /❔/.test(bUnk));
  console.log("✓ bannière git (RM2384) : niveaux, remédiation, lien MR, échappement");
  const P = { handled: [{ sid: "2700", alive: true, state: "working", disposition: "", title: "en cours" }, { sid: "cockpit", alive: true, state: "idle", disposition: "termine", title: "fini" }, { sid: "vieille", alive: false, state: "ghost", disposition: "", title: "hier" }, { sid: "parke", alive: true, state: "idle", disposition: "parke", title: "parké" }] };
  const bs = F.ticketBusySessions(P); assert.deepStrictEqual(bs.alive.map(s => s.sid), ["2700", "parke"]); assert.deepStrictEqual(bs.stopped.map(s => s.sid), ["vieille"]);
  const vide = (p) => { const r = F.ticketBusySessions(p); return !r.alive.length && !r.stopped.length; }; assert(vide(null) && vide({}) && vide({ handled: [] }));
  assert.deepStrictEqual(F.ticketBusySessions({ handled: [{ sid: "x", alive: true, state: "attention", disposition: "termine" }] }).alive.map(s => s.sid), ["x"], "state prime sur la marque");
  assert.strictEqual(F.effDisposition("idle", ""), "a_traiter"); assert.strictEqual(F.effDisposition("working", "termine"), null);
  console.log("✓ sessions occupées (RM2818) : terminé ne compte pas, parké si, éteintes à part");
  // — le dépôt : caches partagés, péremption, dédup en vol, verrous —
  let now = 1000; const caches = { resolve: {}, resolveAt: {}, mc: {}, usage: {}, ts: {} }; const calls = [];
  A.configureApi({ fetch: async (p) => { calls.push(p); await new Promise(r => setTimeout(r, 2)); const body = p.startsWith("/resolve") ? { found: true, title: "T" + p.slice(-1) } : p.startsWith("/mergecheck") ? { verdict: { level: "ok" } } : p.startsWith("/usage") ? { usage: { turns: 1 }, engine: "claude" } : { handled: [] };
    return { ok: true, status: 200, statusText: "", headers: { get: () => "application/json" }, json: async () => body, text: async () => "" }; } });
  const repo = new TicketRepository({ caches, now: () => now });
  assert(repo.stale("1"), "jamais résolu → périmé");
  const titles = []; const [r1, r2] = await Promise.all([repo.ensureResolved("1", false, (rm, r) => titles.push(r.title)), repo.ensureResolved("1")]);
  assert.strictEqual(calls.filter(p => p === "/resolve/1").length, 1, "deux appelants en vol → UNE requête (RM2763)"); assert.strictEqual(r1, r2); assert.deepStrictEqual(titles, ["T1"]); assert.strictEqual(caches.resolve["1"].title, "T1", "le cache partagé est rempli");
  assert(!repo.stale("1")); await repo.ensureResolved("1"); assert.strictEqual(calls.filter(p => p === "/resolve/1").length, 1, "cache entier servi sans requête");
  caches.resolve["2"] = { partial: true, title: "brief" }; await repo.ensureResolved("2"); assert.strictEqual(calls.filter(p => p === "/resolve/2").length, 1, "une entrée partielle (brief) déclenche la résolution riche");
  now += RESOLVE_TTL_MS + 1; assert(repo.stale("1"), "au-delà du TTL → périmé");
  let after = 0; const changed = await repo.revalidate("1", () => after++); assert.strictEqual(changed, false, "même contenu → after() n'est pas appelé"); assert.strictEqual(after, 0);
  caches.resolve["1"] = { found: true, title: "ancien" }; now += RESOLVE_TTL_MS + 1; await repo.revalidate("1", () => after++); assert.strictEqual(after, 1, "contenu changé → after()");
  assert.strictEqual(await repo.revalidate("1", () => after++), undefined, "frais → aucune révalidation");
  const [m1, m2] = await Promise.all([repo.ensureMergecheck("1"), repo.ensureMergecheck("1")]); assert.deepStrictEqual(m1, { verdict: { level: "ok" } }); assert.strictEqual(m2, undefined, "verrou in-flight : le second appel rend undefined, comme avant"); assert(repo.mcFresh("1")); assert.strictEqual(caches.mc["1"].mc.verdict.level, "ok");
  await repo.ensureUsage("1"); assert(repo.usageFresh("1") && !repo.usageInFlight("1")); assert.strictEqual(caches.usage["1"].meta.engine, "claude");
  await repo.ensureTicketSessions("1"); assert.deepStrictEqual(caches.ts["1"], { handled: [] }); await repo.ensureTicketSessions("1"); assert.strictEqual(calls.filter(p => p.startsWith("/ticket-sessions")).length, 1, "servi du cache sans force");
  A.configureApi({ fetch: async () => { throw new Error("réseau"); } }); await repo.ensureResolved("9", true); assert.strictEqual(caches.resolve["9"], null, "échec → null en cache, pas d'exception");
  console.log("✓ dépôt ticket : caches partagés, TTL, dédup en vol, révalidation, verrous, échec toléré");
  console.log("\nTous les tests du modèle ticket passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
