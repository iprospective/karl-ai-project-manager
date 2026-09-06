#!/usr/bin/env node
// Tests de la pile /refresh migrée (RM2889) — porte RM2763 (composite unique : specs par période, hash par bloc, un seul en vol, rejoués,
// dispatch, briefs partial, worklog d'une autre session jeté, panne → pastille ko), RM2613 (cadence adaptative, pause en arrière-plan),
// RM2598 (questions sans réponse), RM2571 (« ⬆ MAJ dispo »), RM2889 (santé : le « tmux ok » a quitté l'en-tête).
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
function fakeEl(id) { const L = []; return { id, style: {}, className: "", title: "", textContent: "", addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; }, async fire(type) { for (const [t, f] of [...L]) if (t === type) await f({}); } }; }
const settle = () => new Promise(r => setTimeout(r, 0));
(async () => {
  const M = await import(path.join(DIR, "src/modules/refresh/refresh.js"));
  const { RefreshService } = await import(path.join(DIR, "src/modules/refresh/refresh.service.js"));
  const { mountRefresh } = await import(path.join(DIR, "src/modules/refresh/refresh.controller.js"));

  // — modèle —
  assert.strictEqual(M.pollDelay(true), 3000, "attention → 3 s"); assert.strictEqual(M.pollDelay(false), 7000, "calme → 7 s");
  const ps = M.pendStaleSet([{ rm_id: "1", kind: "live" }, { rm_id: "2", kind: "stale" }, { rm_id: 3, kind: "stale" }]); assert(!ps.has("1") && ps.has("2") && ps.has("3"), "RM2598 : ne garde que les stale, en chaîne"); assert.strictEqual(M.pendStaleSet([]).size, 0); assert.strictEqual(M.pendStaleSet(null).size, 0);
  assert(M.refreshDue("health", {}, [], 1000) && !M.refreshDue("health", { health: 1000 }, [], 5000) && M.refreshDue("health", { health: 1000 }, [], 16001) && M.refreshDue("health", { health: 1000 }, ["health"], 1001), "dû : jamais reçu, période dépassée, ou forcé");
  assert(M.refreshDue("sessions", { sessions: 1000 }, [], 1000), "période 0 : à chaque tick");
  let b = M.buildSpecs({ hashes: {}, at: {}, includes: [], now: 0, dashboardVisible: false, attached: null, worklogVisible: true, worklogSid: null });
  assert.deepStrictEqual(b.specs, ["sessions:", "health:", "pending:", "vault:", "envcheck:", "coreupdate:"], "1er tick : tous les blocs dus, sauf worklog (détaché) et dashboard (non visible)");
  b = M.buildSpecs({ hashes: { worklog: "w0" }, at: {}, includes: [], now: 0, dashboardVisible: true, attached: "2763", worklogVisible: true, worklogSid: null });
  assert(b.specs.includes("dashboard:") && b.specs[b.specs.length - 1] === "worklog:2763:" && b.worklogSid === "2763" && b.resetWorklogHash, "attaché + onglet visible : le worklog embarque ; autre session → hash oublié");
  b = M.buildSpecs({ hashes: { worklog: "w1" }, at: {}, includes: [], now: 0, attached: "2763", worklogVisible: true, worklogSid: "2763" }); assert(b.specs.includes("worklog:2763:w1") && !b.resetWorklogHash, "même session : le hash voyage");
  b = M.buildSpecs({ hashes: {}, at: {}, includes: [], now: 0, attached: "2763", worklogVisible: false, worklogSid: "2763" }); assert(!b.specs.some(s => s.startsWith("worklog")), "onglet replié : pas de worklog");
  const rc = { "42": { found: true, title: "riche", cwd: "/x" } }, ra = {}; M.seedBriefs({ 42: { found: true, title: "brief" }, 7: { found: true, title: "T7" } }, rc, ra, 123);
  assert(rc["42"].title === "riche" && rc["7"].partial && rc["7"].title === "T7" && ra["7"] === 123 && ra["42"] === undefined, "briefs semés en partial, jamais par-dessus une résolution riche"); M.seedBriefs({ 7: { found: true, title: "T7b" } }, rc, ra, 124); assert(rc["7"].title === "T7b", "un partial est remplacé par un partial plus frais");
  assert.deepStrictEqual(M.healthState({ sessions: 3, tmux: true }), { cls: "dot ok", title: "agent joignable · 3 session(s)", text: "" }, "RM2889 : plus de « tmux ok » dans l'en-tête"); assert.deepStrictEqual(M.healthKo("down"), { cls: "dot ko", title: "", text: "injoignable — down" });
  assert.deepStrictEqual(M.coreUpdateState({ available: false }), { on: false, text: "", title: "" }); const cu = M.coreUpdateState({ available: true, branch: "main", local: "abcdef0123", remote: "1234567890", stale: true, error: "offline" }); assert(cu.on && cu.text === "⬆ MAJ dispo" && /« main » : abcdef0 → 1234567 \(état périmé : offline\)/.test(cu.title), "RM2571 : de → vers, état périmé dit");
  assert(/branche : main\ninstallé : abcdef0\ndisponible : 1234567\nvérifié : hier\n/.test(M.coreUpdateText({ branch: "main", local: "abcdef0123", remote: "1234567890", checked_at: "hier" })) && /sudo \/zfs\/workspaces\/\.mmi-pm-core\/bin\/mmi-pm core update/.test(M.coreUpdateText({})), "appliquer reste un geste humain : la commande est dite");
  assert.strictEqual(M.versionMismatch("3.0.0", "3.0.0"), ""); assert.strictEqual(M.versionMismatch("?", "3.0.0"), ""); assert.strictEqual(M.versionMismatch(undefined, "3.0.0"), ""); assert(/serveur v3\.1\.0 ≠ front v3\.0\.0/.test(M.versionMismatch("3.1.0", "3.0.0")), "RM3000 : écart de version signalé");
  console.log("✓ modèle : périodes et specs (RM2763), cadence (RM2613), questions sans réponse (RM2598), briefs, santé (RM2889), MAJ core (RM2571), version (RM3000)");

  // — service —
  const calls = []; let resp = { blocks: {}, skipped: [], errors: {} }; let now = 100000;
  const repo = { async pull(specs) { calls.push(specs); if (resp instanceof Error) throw resp; return resp; }, async coreUpdate() { calls.push("core"); return { available: true, branch: "dev" }; } };
  const rcache = {}, rat = {}; const svc = new RefreshService({ repo, now: () => now, caches: { resolve: rcache, resolveAt: rat } });
  const got = { health: [], ko: [], sessions: [], worklog: [], dash: [], env: [], core: [] }; let att = null, wl = true, dv = false;
  const env = () => ({ attached: att, dashboardVisible: dv, worklogVisible: wl });
  const on = { health: (d) => got.health.push(d), healthKo: (m) => got.ko.push(m), sessions: (l) => { got.sessions.push(l); return { attention: 2, choice: 1 }; }, worklog: (d) => got.worklog.push(d), dashboard: (d) => got.dash.push(d), env: (k, d) => got.env.push([k, d]), coreupdate: (d) => got.core.push(d) };
  assert.deepStrictEqual(svc.specs([], env()), ["sessions:", "health:", "pending:", "vault:", "envcheck:", "coreupdate:"]);
  att = "2763"; assert.strictEqual(svc.specs([], env()).pop(), "worklog:2763:", "attaché : le worklog embarque");
  resp = { blocks: { sessions: { hash: "s1", data: { sessions: [{ rm_id: "2763" }], briefs: { 2763: { found: true, title: "T" } } } }, health: { hash: "h1", data: { sessions: 1 } }, worklog: { hash: "w1", data: { rm_id: "2763", found: true } }, pending: { hash: "p1", data: { entries: [{ rm_id: "2763", kind: "stale" }] } }, vault: { hash: "v1", data: { locked: 1 } }, coreupdate: { hash: "c1", data: { available: false } } }, skipped: [], errors: {} };
  await svc.fetch([], env, on);
  assert.strictEqual(calls.length, 1, "UNE requête composite"); assert(got.sessions.length === 1 && got.health.length === 1 && got.worklog.length === 1 && got.env.length === 1 && got.env[0][0] === "vault" && got.core.length === 1, "chaque bloc reçu dispatché");
  assert(rcache["2763"] && rcache["2763"].partial && rat["2763"] === now, "brief semé en partial"); assert(svc.stale.has("2763"), "pending → questions sans réponse recalculées"); assert.strictEqual(svc.hot, 3, "RM2613 : la cadence lit les compteurs rendus");
  assert.deepStrictEqual(svc.specs([], env()), ["sessions:s1"], "tick suivant avant les périodes : seul sessions repart, avec son hash"); assert(svc.specs(["health"], env()).includes("health:h1"), "un include force le bloc, avec son hash");
  now += 20000; assert(svc.specs([], env()).includes("health:h1") && svc.specs([], env()).includes("worklog:2763:w1") && !svc.specs([], env()).includes("pending:p1"), "15 s : health et worklog redus, pending (45 s) pas encore");
  resp = { blocks: {}, skipped: ["sessions"], errors: {} }; await svc.fetch([], env, on); assert.strictEqual(got.sessions.length, 1, "inchangé → pas de re-rendu");
  resp = { blocks: { worklog: { hash: "w2", data: { rm_id: "999", found: true } } }, skipped: [], errors: {} }; await svc.fetch(["worklog"], env, on); assert.strictEqual(got.worklog.length, 1, "worklog d'une session quittée entre-temps : jeté");
  resp = new Error("down"); await svc.fetch([], env, on); assert.deepStrictEqual(got.ko, ["down"], "panne → pastille ko"); assert.strictEqual(svc.inFlight, null);
  // un seul en vol : le second appel reçoit la même promesse et ses includes sont rejoués après
  let release; resp = { blocks: {}, skipped: [], errors: {} }; repo.pull = async (specs) => { calls.push(specs); await new Promise(r => { release = r; }); return resp; };
  calls.length = 0; const p1 = svc.fetch([], env, on), p2 = svc.fetch(["health"], env, on); assert.strictEqual(p1, p2, "le composite en vol est partagé"); assert.strictEqual(calls.length, 1); release(); await p1; await settle(); await settle();
  assert.strictEqual(calls.length, 2, "…et les includes arrivés pendant le vol sont rejoués après"); assert(calls[1].includes("health:h1")); release(); await settle();
  repo.pull = async (specs) => { calls.push(specs); return resp; }; att = null; svc.at = { sessions: now, health: now, pending: now, vault: now, envcheck: now, coreupdate: now }; await svc.fetch([], env, on); assert.strictEqual(calls.length, 3); assert.deepStrictEqual(calls[2], ["sessions:s1"], "toutes les périodes fraîches : seul le bloc sessions (période 0) repart, sans worklog (détaché)");
  console.log("✓ service : composite unique, hashs et périodes, dispatch, briefs, stale, cadence, rejoués, worklog étranger jeté, panne");

  // — contrôleur —
  const health = fakeEl("health"), healthtxt = fakeEl("healthtxt"), updbtn = fakeEl("updbtn"), verwarn = fakeEl("verwarn"); updbtn.style.display = "none";
  const timers = []; let hid = false; const alerts = []; const ev = []; const root = fakeEl("document");
  const svc2 = new RefreshService({ repo: { async pull(specs) { ev.push(["pull", specs]); return { blocks: { health: { hash: "h", data: { sessions: 2 } }, sessions: { hash: "s", data: { sessions: [{ rm_id: "1" }], briefs: {} } }, coreupdate: { hash: "c", data: { available: true, branch: "main", local: "aaaaaaa1", remote: "bbbbbbb2" } }, worklog: { hash: "w", data: { rm_id: "1" } }, dashboard: { hash: "d", data: { n: 1 } }, envcheck: { hash: "e", data: { ok: 1 } } } }; }, async coreUpdate() { ev.push("core"); return { available: false }; } }, now: () => 5000 });
  const ctr = mountRefresh({ health, healthtxt, updbtn, verwarn }, { version: "3.0.0", service: svc2, later: (fn, ms) => { timers.push([fn, ms]); return timers.length; }, hidden: () => hid, root, alert: (t) => alerts.push(t),
    attached: () => "1", worklogVisible: () => true, dashboardVisible: () => true, onSessions: (l) => { ev.push(["sessions", l.length]); return { attention: 1, choice: 0 }; }, onWorklog: (d) => ev.push(["worklog", d.rm_id]), onDashboard: (d) => ev.push(["dash", d.n]), onEnv: (k) => ev.push(["env", k]) });
  ctr.start(); await settle(); await settle();
  assert(ev.some(x => x[0] === "pull" && x[1].join() === "sessions:,health:,pending:,dashboard:,vault:,envcheck:,coreupdate:,worklog:1:") && ev.some(x => x[0] === "sessions" && x[1] === 1) && ev.some(x => x[0] === "worklog" && x[1] === "1") && ev.some(x => x[0] === "dash") && ev.some(x => x[0] === "env" && x[1] === "envcheck"), "premier tick : tous les blocs, chacun livré à son domaine");
  assert(health.className === "dot ok" && health.title === "agent joignable · 2 session(s)" && healthtxt.textContent === "" && updbtn.style.display === "" && updbtn.textContent === "⬆ MAJ dispo" && /aaaaaaa → bbbbbbb/.test(updbtn.title), "santé et MAJ peints");
  assert(timers.length === 1 && timers[0][1] === 3000, "RM2613 : une session attend → prochain tick dans 3 s"); assert.strictEqual(ctr.hot(), 1);
  hid = true; timers[0][0](); await settle(); assert.strictEqual(timers.length, 1, "onglet caché : le tick s'arrête"); hid = false; await root.fire("visibilitychange"); await settle(); await settle(); assert.strictEqual(timers.length, 2, "retour au premier plan : rattrapage immédiat, puis replanifié");
  ctr.start(); assert.strictEqual(root.listenerCount, 1, "start est idempotent");
  await updbtn.fire("click"); assert(alerts.length === 1 && /branche : main/.test(alerts[0]), "RM2571 : le clic dit la commande");
  ev.length = 0; await ctr.refreshCoreUpdate(true); assert(ev.includes("core") && updbtn.style.display === "none", "rafraîchissement forcé : sonde directe, bouton masqué si plus rien");
  ctr.renderHealthKo("hs"); assert(health.className === "dot ko" && healthtxt.textContent === "injoignable — hs");
  ctr.renderHealth({ sessions: 1, version: "3.0.0" }); assert(verwarn.style.display === "none"); ctr.renderHealth({ sessions: 1, version: "2.9.0" }); assert(verwarn.style.display === "" && /serveur v2\.9\.0 ≠ front v3\.0\.0/.test(verwarn.textContent), "RM3000 : l'écart de version s'affiche au pied de page");
  ev.length = 0; await ctr.refreshSessions(); assert(ev.some(x => x[0] === "pull" && x[1].some(s => s.startsWith("sessions:s"))), "rafraîchissement événementiel : le bloc sessions repart avec son hash");
  ctr.unmount(); assert.strictEqual(root.listenerCount + updbtn.listenerCount, 0, "unmount libère tout");
  console.log("✓ contrôleur : premier tick, dispatch, santé, MAJ core, cadence, pause/rattrapage, clic MAJ, sonde forcée");

  // — hôtes et ponts dans index.html —
  ["health", "healthtxt", "updbtn"].forEach(id => assert(html.includes('id="' + id + '"'), "hôte manquant : " + id));
  assert(!/id="updbtn"[^>]*\son\w+=/.test(html), "#updbtn ne porte plus de on*"); const nav = /<nav class="lnav">[\s\S]*?<\/nav>/.exec(html)[0]; assert(!/\son\w+=/.test(nav) && (nav.match(/data-panel="/g) || []).length === 6, "les onglets gauche : data-panel seul, plus de on*");
  { const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8"); assert(/refreshCtl\.start\(\);/.test(boot) && /layout\.restorePanel\(\)/.test(boot) && /refresh: refreshCtl,/.test(boot), "boot.js : premier tick depuis l'init, panneau restauré, l'attache rafraîchit par le contrôleur"); }
  assert(!/setInterval|refreshFetch\(|PANEL_LOADERS|renderHealth\(|renderCoreUpdate\(/.test(html.replace(/\/\/[^\n]*/g, "")), "plus aucun poller ni renderer de santé/MAJ dans le monolithe");
  const ctrl = fs.readFileSync(path.join(DIR, "src/modules/refresh/refresh.controller.js"), "utf8"); assert(/visibilitychange/.test(ctrl) && /hidden/.test(ctrl), "pollers gatés sur la visibilité (RM2613)");
  console.log("✓ hôtes sans on*, ponts en place, plus de poller dans le monolithe");
  console.log("\nTous les tests de la pile /refresh passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
