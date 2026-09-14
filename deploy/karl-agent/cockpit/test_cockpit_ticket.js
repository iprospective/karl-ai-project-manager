#!/usr/bin/env node
// Tests du modèle ticket migré (RM2889) — porte sinceLabel (RM2630), RM2611, mcBanner (RM2384), ticketBusySessions (RM2818),
// et vérifie la logique du dépôt : péremption, dédup en vol (RM2763), verrous.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
(async () => {
  const F = await import(path.join(DIR, "src/modules/ticket/ticketFormat.js"));
  const KS = await import(path.join(DIR, "src/core/store.js")); const mkStore = (name, obj) => { const s = new KS.Store(name, { ttl: 1e9, max: 1000 }); Object.entries(obj || {}).forEach(([k, v]) => s.set(k, v)); return s; };   // RM3005
  const { MergeBanner } = await import(path.join(DIR, "src/modules/ticket/MergeBanner.view.js"));
  const { TicketRepository, RESOLVE_TTL_MS } = await import(path.join(DIR, "src/modules/ticket/TicketRepository.js"));
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
  // — le dépôt : stores nommés (RM3005), fraîcheur douce, dédup en vol, verrous —
  let now = 1000; KS.resetStores(); const S = KS.appStores({ now: () => now }); const calls = [];
  A.configureApi({ fetch: async (p) => { calls.push(p); await new Promise(r => setTimeout(r, 2)); const body = p.startsWith("/api/ticket/resolve") ? { found: true, title: "T" + p.slice(-1) } : p.startsWith("/api/ticket/mergecheck") ? { verdict: { level: "ok" } } : p.startsWith("/api/ticket/usage") ? { usage: { turns: 1 }, engine: "claude" } : { handled: [] };
    return { ok: true, status: 200, statusText: "", headers: { get: () => "application/json" }, json: async () => body, text: async () => "" }; } });
  const repo = new TicketRepository({ stores: S, now: () => now });
  assert(repo.stale("1"), "jamais résolu → périmé");
  const titles = []; const [r1, r2] = await Promise.all([repo.ensureResolved("1", false, (rm, r) => titles.push(r.title)), repo.ensureResolved("1")]);
  assert.strictEqual(calls.filter(p => p === "/api/ticket/resolve/1").length, 1, "deux appelants en vol → UNE requête (RM2763)"); assert.strictEqual(r1, r2); assert.deepStrictEqual(titles, ["T1"]); assert.strictEqual(S.resolve.get("1").title, "T1", "le cache partagé est rempli");
  assert(!repo.stale("1")); await repo.ensureResolved("1"); assert.strictEqual(calls.filter(p => p === "/api/ticket/resolve/1").length, 1, "cache entier servi sans requête");
  S.resolve.set("2", { partial: true, title: "brief" }); await repo.ensureResolved("2"); assert.strictEqual(calls.filter(p => p === "/api/ticket/resolve/2").length, 1, "une entrée partielle (brief) déclenche la résolution riche");
  now += RESOLVE_TTL_MS + 1; assert(repo.stale("1"), "au-delà du TTL → périmé");
  let after = 0; const changed = await repo.revalidate("1", () => after++); assert.strictEqual(changed, false, "même contenu → after() n'est pas appelé"); assert.strictEqual(after, 0);
  S.resolve.set("1", { found: true, title: "ancien" }); now += RESOLVE_TTL_MS + 1; await repo.revalidate("1", () => after++); assert.strictEqual(after, 1, "contenu changé → after()");
  assert.strictEqual(await repo.revalidate("1", () => after++), undefined, "frais → aucune révalidation");
  const [m1, m2] = await Promise.all([repo.ensureMergecheck("1"), repo.ensureMergecheck("1")]); assert.deepStrictEqual(m1, { verdict: { level: "ok" } }); assert.strictEqual(m2, undefined, "verrou in-flight : le second appel rend undefined, comme avant"); assert(repo.mcFresh("1")); assert.strictEqual(S.mc.get("1").mc.verdict.level, "ok");
  await repo.ensureUsage("1"); assert(repo.usageFresh("1") && !repo.usageInFlight("1")); assert.strictEqual(S.usage.get("1").meta.engine, "claude");
  await repo.ensureTicketSessions("1"); assert.deepStrictEqual(S.ts.get("1"), { handled: [] }); await repo.ensureTicketSessions("1"); assert.strictEqual(calls.filter(p => p.startsWith("/api/test-queue/ticket-sessions")).length, 1, "servi du cache sans force");

  A.configureApi({ fetch: async () => { throw new Error("réseau"); } }); await repo.ensureResolved("9", true); assert.strictEqual(S.resolve.get("9"), null, "échec → null en cache, pas d'exception");
  assert(S.resolve.stats().entries >= 2 && S.resolve.max === 500 && S.resolve.name === "ticket.resolve", "RM3005 : le dépôt range tout dans les stores nommés, bornés");

  // — RM3140 : une VUE qui affiche N tickets ne doit pas coûter N requêtes —
  // La garde est celle que le ticket demande explicitement : le nombre de requêtes ne croît PAS
  // avec le nombre de tickets affichés. Sans elle, la régression reviendrait sans bruit (le
  // symptôme n'est visible qu'à l'onglet réseau du navigateur).
  KS.resetStores();
  const S2 = KS.appStores({ now: () => now }); const appels = [];
  A.configureApi({ fetch: async (p) => { appels.push(p);
    const ids = decodeURIComponent((p.split("ids=")[1] || "")).split(",").filter(Boolean);
    const tickets = {}; ids.forEach(id => { tickets[id] = { found: true, rm_id: id, title: "T" + id, status: "en_cours" }; });
    return { ok: true, status: 200, statusText: "", headers: { get: () => "application/json" }, json: async () => ({ tickets }), text: async () => "" }; } });
  // `defer` injecté : le test vide la file quand il veut, sans dépendre d'une minuterie réelle.
  let vidange = null; const repoB = new TicketRepository({ stores: S2, now: () => now, defer: (fn) => { vidange = fn; return 1; } });
  const vingt = Array.from({ length: 20 }, (_, i) => String(100 + i));
  const attente = repoB.ensureBriefs(vingt);
  repoB.ensureBriefs(vingt.slice(0, 5));      // une seconde vue se peint dans le même tour
  assert.strictEqual(appels.length, 0, "rien ne part avant la vidange : la file groupe le tour");
  vidange(); await attente;
  assert.strictEqual(appels.length, 1, "vingt tickets affichés, UNE requête (RM3140)");
  const envoyes = decodeURIComponent(appels[0].split("ids=")[1]).split(",");
  assert.strictEqual(envoyes.length, 20, "et les vingt y sont, une seule fois chacun");
  assert.strictEqual(new Set(envoyes).size, 20, "sans doublon, même quand deux vues demandent les mêmes");
  assert.strictEqual(S2.resolve.get("100").title, "T100", "le store est semé pour toute la liste");
  assert.strictEqual(S2.resolve.get("100").partial, true, "…en PARTIEL : un brief n'est pas une fiche");
  await repoB.ensureBriefs(vingt);
  assert.strictEqual(appels.length, 1, "ce qui est déjà là n'est jamais redemandé");
  S2.resolve.set("777", { found: true, title: "riche" });
  await repoB.ensureBriefs(["777"]);
  assert.strictEqual(appels.length, 1, "et une résolution RICHE n'est pas écrasée par un brief");
  // un lot qui échoue ne doit pas se redemander en boucle au rendu suivant
  A.configureApi({ fetch: async () => { throw new Error("réseau"); } });
  const ko = repoB.ensureBriefs(["900", "901"]); vidange(); await ko;
  assert.deepStrictEqual(S2.resolve.get("900"), { found: false, rm_id: "900", partial: true }, "échec → « inconnu », affichable");
  const encore = repoB.ensureBriefs(["900"]);
  assert.strictEqual(vidange && encore instanceof Promise, true);
  console.log("✓ résolution en lot (RM3140) : une liste = une requête, semée en partiel, sans boucle sur échec");

  console.log("✓ dépôt ticket : stores nommés (RM3005), fraîcheur douce, dédup en vol, révalidation, verrous, échec toléré");
  console.log("\nTous les tests du modèle ticket passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
