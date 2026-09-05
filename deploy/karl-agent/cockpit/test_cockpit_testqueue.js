#!/usr/bin/env node
// Tests de la file « à tester » migrée (RM2889) — porte tqMatch (RM2315) ; filtres, tri, gestes d'env (RM2588).
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
function fakeElement() { const L = []; let inner = ""; const sub = {}; return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, sub,
  querySelector(sel) { if (sel === "#tq-list") return sub.list || (sub.list = { innerHTML: "" }); if (sel === "#tq-count") return sub.count || (sub.count = { textContent: "" }); return null; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, sel, n) { for (const [t, f] of [...L]) if (t === type) await f({ target: { closest: s => s === sel ? n : null } }); } }; }
(async () => {
  const M = await import(path.join(DIR, "src/models/testqueue/testQueue.js"));
  const { TestQueueViewModel } = await import(path.join(DIR, "src/viewmodels/testqueue/TestQueueViewModel.js"));
  const { TestQueuePanel } = await import(path.join(DIR, "src/views/testqueue/TestQueue.view.js"));
  const { TestQueueService } = await import(path.join(DIR, "src/services/testqueue.service.js"));
  const { mountTestQueue } = await import(path.join(DIR, "src/controllers/testqueue.controller.js"));
  const entry = { rm_id: "2302", title: "Améliorations ergonomiques design cockpit", client: "iprospective", project: "pm-ai-agents", status: "a_tester_demandeur", branch: "2302-ameliorations-ergonomiques-desogn-cockpit", env: "ai-project-management-rm2302", tags: ["cockpit", "ux"] };
  assert(M.tqMatch(entry, "") && M.tqMatch(entry, "   ") && M.tqMatch(entry, "2302") && M.tqMatch(entry, "RM2302") && M.tqMatch(entry, "COCKPIT") && M.tqMatch(entry, "ameliorations") && M.tqMatch(entry, "cockpit ergonomiques"));
  assert(!M.tqMatch(entry, "cockpit prestashop") && M.tqMatch(entry, "pm-ai-agents") && M.tqMatch(entry, "desogn") && M.tqMatch(entry, "ux") && !M.tqMatch({ rm_id: "7", title: null, tags: null }, "cockpit"));
  const Q = [{ rm_id: "3", client: "a", project: "x", status: "a_tester_dev", updated: "2026-09-03", deployable: true, title: "c" }, { rm_id: "1", client: "b", project: "y", status: "a_tester_demandeur", updated: "2026-09-01", title: "a", env: "e", env_live: false, env_reason: "arrêté" }, { rm_id: "2", client: "a", project: "x", status: "a_tester_demandeur", updated: "2026-09-02", title: "b", cockpit_testable: true, env_live: true, test_url: "https://t/", cockpit_host: "t" }];
  assert.deepStrictEqual(M.sortQueue(Q, "oldest").map(e => e.rm_id), ["1", "2", "3"]); assert.deepStrictEqual(M.sortQueue(Q, "newest").map(e => e.rm_id), ["3", "2", "1"]); assert.deepStrictEqual(M.sortQueue(Q, "rm-desc").map(e => e.rm_id), ["3", "2", "1"]); assert.deepStrictEqual(M.sortQueue(Q, "project").map(e => e.rm_id), ["2", "3", "1"]);
  assert.deepStrictEqual(M.filterQueue(Q, { project: "a/x" }).map(e => e.rm_id), ["3", "2"]); assert.deepStrictEqual(M.filterQueue(Q, { status: "a_tester_dev" }).map(e => e.rm_id), ["3"]); assert.deepStrictEqual(M.filterQueue(Q, { deployable: true }).map(e => e.rm_id), ["3"]); assert.deepStrictEqual(M.projectsOf(Q), ["a/x", "b/y"]);
  assert.deepStrictEqual(M.envActions(Q[2]).map(a => a.action), ["cockpit-teardown"], "instance en ligne → démonter"); assert.deepStrictEqual(M.envActions({ cockpit_testable: true, env: "x" }).map(a => a.action), ["cockpit-create", "cockpit-teardown"], "cockpit_testable EN PREMIER, même avec un env (RM2588)");
  assert.deepStrictEqual(M.envActions(Q[1]).map(a => a.action), ["deploy"]); assert.deepStrictEqual(M.envActions(Q[0]).map(a => a.action), ["deploy"]); assert.deepStrictEqual(M.envActions({ env: "e", env_live: true }).map(a => a.action), ["teardown"]); assert.strictEqual(M.envActions({}).map(a => a.action)[0], null, "hors layout : indisponible, pas de bouton");
  assert.deepStrictEqual(M.envLink(Q[2]), { href: "https://t/", label: "t", live: true }); assert.deepStrictEqual(M.envLink({ test_host: "h", env_live: true }), { href: "http://h/", label: "h", live: true }); assert.strictEqual(M.envLink(Q[1]), null); assert.deepStrictEqual(M.envLink({ test_host: "h", env_reason: "down" }), { warn: "down", label: "h" });
  console.log("✓ modèle (RM2315/2588) : mots-clés, filtres, tris, gestes d'env dans le bon ordre, liens");
  const vm = new TestQueueViewModel({ all: Q, loaded: true }, { filters: { sort: "oldest" }, pin: (k, id) => (id === "2" ? "📌" : "") });
  assert.strictEqual(vm.count, "(3)"); assert.strictEqual(new TestQueueViewModel({ all: Q }, { filters: { status: "a_tester_dev" } }).count, "(1/3)"); assert.strictEqual(new TestQueueViewModel({ all: [] }, {}).emptyText, "rien à tester 🎉"); assert.strictEqual(new TestQueueViewModel({ all: Q }, { filters: { q: "zzz" } }).emptyText, "aucun résultat avec ces filtres");
  const h = String(TestQueuePanel(vm));
  assert(/data-action="review" data-rm="1"/.test(h) && /data-action="verdict" data-kind="valider" data-rm="1"/.test(h) && /data-action="cockpit-teardown" data-rm="2"/.test(h) && /data-action="deploy" data-rm="1"/.test(h));
  assert(/<a href="https:\/\/t\/" target="_blank">t ↗<\/a> <span title="instance de test en ligne"/.test(h) && /pill warn">demandeur/.test(h) && /📌/.test(h) && !/onclick=|onchange=|oninput=/.test(h));
  assert(/<option value="a\/x">a\/x<\/option>/.test(h) && /data-filter="q"/.test(h) && /data-action="refresh"/.test(h)); assert(/chargement…/.test(String(TestQueuePanel(vm, { loading: true }))));
  console.log("✓ vue : liste, liens, gestes en data-action, filtres, chargement");
  const el = fakeElement(); const ev = []; const runs = [];
  const svc = new TestQueueService({ async list() { ev.push("list"); return Q; } }, async (name, args) => { runs.push([name, args]); return { ok: name !== "env-session-teardown", rc: name === "env-session-teardown" ? 1 : 0, stdout: "out", stderr: "err" }; });
  const tq = mountTestQueue(el, { service: svc, notify: (m, e) => ev.push(["toast", m, !!e]), confirm: () => true, capture: (t, o) => ev.push(["capture", t]), resolveRefresh: (rm) => ev.push(["resolve", rm]), openReview: (rm) => ev.push(["review", rm]), verdict: (rm, k) => ev.push(["verdict", rm, k]), afterLoad: () => ev.push("afterLoad"), pin: () => "" });
  assert(/rien à tester/.test(el.innerHTML)); await tq.load(); assert.deepStrictEqual(ev.slice(0, 2), ["list", "afterLoad"]); assert.strictEqual(tq.size(), 3); assert(tq.loaded()); assert.strictEqual(tq.entry("2").cockpit_host, "t"); assert.strictEqual(tq.entry("9"), undefined);
  await el.fire("change", "[data-filter]", { dataset: { filter: "status" }, value: "a_tester_dev" }); assert(/data-rm="3"/.test(el.innerHTML) && !/data-rm="1"/.test(el.innerHTML), "le filtre de statut restreint la liste");
  await el.fire("input", "[data-filter]", { dataset: { filter: "q" }, value: "zzz" }); assert(/aucun résultat/.test(el.sub.list.innerHTML), "la saisie repeint la liste seule, pas l'input");
  await el.fire("click", "[data-action]", { dataset: { action: "clear" } }); assert.strictEqual(tq.filters.q, "");
  await el.fire("click", "[data-action]", { dataset: { action: "review", rm: "3" } }); assert.deepStrictEqual(ev.pop(), ["review", "3"]); await el.fire("click", "[data-action]", { dataset: { action: "verdict", rm: "3", kind: "mep" } }); assert.deepStrictEqual(ev.pop(), ["verdict", "3", "mep"]);
  const btn = { dataset: { action: "cockpit-create", rm: "2" }, disabled: false, textContent: "x" }; await el.fire("click", "[data-action]", btn); assert.deepStrictEqual(runs.pop(), ["cockpit-test-env", { action: "create", rm_id: "2" }]); assert(ev.some(x => x[0] === "toast" && /Instance de test RM2 prête/.test(x[1])) && ev.some(x => x[0] === "capture") && ev.some(x => x[0] === "resolve" && x[1] === "2"));
  await el.fire("click", "[data-action]", { dataset: { action: "deploy", rm: "1" }, disabled: false, textContent: "" }); assert.deepStrictEqual(runs.pop(), ["env-session-create", { action: "create", rm_id: "1", db_clone: true }], "confirm → clone dédié");
  await el.fire("click", "[data-action]", { dataset: { action: "teardown", rm: "1" }, disabled: false, textContent: "" }); assert.deepStrictEqual(runs.pop()[0], "env-session-teardown"); assert(ev.some(x => x[0] === "toast" && /Échec \(rc=1\)/.test(x[1])) && ev.some(x => x[0] === "capture" && /ÉCHEC/.test(x[1])), "un échec se dit et sa sortie s'affiche");
  tq.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur : chargement, filtres, saisie sans perdre l'input, revue/verdict prêtés, gestes d'env, échec dit");
  console.log("\nTous les tests de la file à tester passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
