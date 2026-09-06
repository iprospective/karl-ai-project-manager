#!/usr/bin/env node
// Tests du journal du cockpit (RM3011) — core/log (tampon, sévérités/catégories, abonnés, remontée par lots sans boucle, capture globale),
// module journal (fusion serveur + front, filtres, badge, service persisté et relu par since, vue sans on*, contrôleur : suivi visible
// seulement, copie, purge, badge d'en-tête) et le câblage de la page (bouton d'en-tête, panneau central, centre).
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
function fakeEl(id) { const L = []; let inner = ""; const self = { id, style: {}, textContent: "", scrollTop: 0, scrollHeight: 999, kids: {}, get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, querySelector(sel) { return self.kids[sel] || null; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, target) { for (const [t, f] of [...L]) if (t === type) await f({ target, preventDefault() {}, stopPropagation() {} }); await new Promise(r => setTimeout(r, 0)); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n, value: "" }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await new Promise(r => setTimeout(r, 0)); return n; } }; return self; }
(async () => {
  const L = await import(path.join(DIR, "src/core/log.js"));
  const M = await import(path.join(DIR, "src/modules/journal/journal.js"));
  const { JournalService } = await import(path.join(DIR, "src/modules/journal/journal.service.js"));
  const VM = await import(path.join(DIR, "src/modules/journal/JournalViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/journal/Journal.view.js"));
  const { mountJournal } = await import(path.join(DIR, "src/modules/journal/journal.controller.js"));

  // — core/log —
  const sent = []; const timers = []; let t = 1000;
  const log = L.createLog({ capacity: 3, now: () => new Date(t++), remote: async (r) => { sent.push(r); if (r.message === "ko") throw new Error("réseau"); }, later: (fn) => { timers.push(fn); return timers.length; }, version: "3.0.0", ua: "node" });
  const got = []; const off = log.subscribe(r => got.push(r.level + ":" + r.msg));
  log.info("api", "un"); log.warn("tmux", "deux", { rm_id: "42" }); log.error("zzz", "trois"); log.debug("front", "quatre");
  assert.deepStrictEqual(got, ["info:un", "warn:deux", "error:trois", "debug:quatre"], "les abonnés voient chaque entrée");
  assert.deepStrictEqual(log.entries().map(e => e.msg), ["deux", "trois", "quatre"], "tampon circulaire (capacité 3)"); assert(log.entries()[1].cat === "front" && log.entries()[1].bad_category === "zzz", "catégorie inconnue → front, signalée");
  assert.strictEqual(log.pending(), 2, "warn et error attendent la remontée, info/debug non"); assert.strictEqual(timers.length, 1, "un seul lot programmé"); await timers[0]();
  assert.deepStrictEqual(sent.map(s => [s.category, s.level, s.message, s.fields.rm_id, s.fields.version]), [["tmux", "warn", "deux", "42", "3.0.0"], ["front", "error", "trois", undefined, "3.0.0"]], "remontée par lots : catégorie, sévérité, message, champs + version");
  off(); log.error("front", "ko"); await timers[1](); assert(log.failures() === 1 && got.length === 4, "un échec réseau est compté, jamais journalisé (pas de boucle), désabonnement respecté");
  const win = { L: [], addEventListener(t2, f) { this.L.push([t2, f]); }, removeEventListener(t2, f) { this.L = this.L.filter(([a, b]) => !(a === t2 && b === f)); } };
  const un = L.installGlobalCapture(log, win); win.L.find(([k]) => k === "error")[1]({ message: "x is not a function", filename: "a.js", lineno: 7, error: Object.assign(new TypeError("x is not a function"), { stack: "TypeError: x\n    at f (a.js:7)\n    at g (b.js:1)\n    at h" }) });
  win.L.find(([k]) => k === "unhandledrejection")[1]({ reason: new Error("refusé") });
  const last2 = log.entries().slice(-2); assert(last2[0].level === "error" && last2[0].cat === "front" && last2[0].file === "a.js" && /at f \(a\.js:7\) ← at g/.test(last2[0].trace) && /promesse rejetée : refusé/.test(last2[1].msg), "capture globale : exceptions et promesses rejetées"); un(); assert.strictEqual(win.L.length, 0);
  assert(/^Error: e @ /.test(L.errorBrief(new Error("e"))) && L.errorBrief("txt") === "txt" && L.errorBrief(null) === "", "errorBrief");
  console.log("✓ core/log : tampon, abonnés, sévérités/catégories, remontée par lots sans boucle, capture globale");

  // — modèle —
  const srv = [{ ts: "2026-09-06T10:00:01.000+02:00", level: "info", cat: "api", msg: "GET /x", status: 200 }, { ts: "2026-09-06T10:00:03.000+02:00", level: "error", cat: "sets", msg: "RuntimeError", trace: "t" }];
  const fr = [{ id: 1, src: "front", ts: "2026-09-06T10:00:02.000+02:00", level: "warn", cat: "front", msg: "lent" }, { id: 2, src: "front", ts: "2026-09-06T10:00:03.000+02:00", level: "debug", cat: "front", msg: "d" }];
  const merged = M.mergeEntries(srv, fr); assert.deepStrictEqual(merged.map(e => e.msg), ["GET /x", "lent", "RuntimeError", "d"], "fusion triée par horodatage, serveur d'abord à égalité"); assert.strictEqual(M.mergeEntries(srv, srv.map(s => Object.assign({ src: "server" }, s))).length, 2, "dédoublonnée");
  assert.deepStrictEqual(M.filterEntries(merged, { level: "warn" }).map(e => e.msg), ["lent", "RuntimeError"]); assert.deepStrictEqual(M.filterEntries(merged, { cats: new Set(["sets"]) }).map(e => e.msg), ["RuntimeError"]); assert.deepStrictEqual(M.filterEntries(merged, { q: "status" }).map(e => e.msg), ["GET /x"], "recherche dans les champs"); assert.strictEqual(M.filterEntries(merged, { cats: new Set() }).length, 4, "ensemble vide = toutes");
  assert.strictEqual(M.fieldsText(srv[0]), "status=200"); assert.strictEqual(M.fieldsText({ a: { b: 1 }, id: 1 }), 'a={"b":1}'); assert.strictEqual(M.badgeCount(fr, 0), 1, "badge : warn/error du front"); assert.strictEqual(M.badgeCount(fr, 1), 0, "…depuis le dernier vu"); assert.strictEqual(M.fmtTs("2026-09-06T10:00:01.000+02:00"), "10:00:01"); assert.strictEqual(M.dayOf("2026-09-06T10:00:01.000+02:00"), "2026-09-06");
  console.log("✓ modèle : fusion, filtres, champs, badge");

  // — service —
  const store = { d: {}, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); } };
  const calls = []; let resp = { entries: srv, categories: ["api", "sets", "front"], stats: { written: 9, level: "info", path: "/p" } };
  const repo = { async tail(p) { calls.push(p); if (resp instanceof Error) throw resp; return resp; } };
  const log2 = L.createLog({ now: () => new Date("2026-09-06T10:00:05.000+02:00") }); let fronts = 0;
  const svc = new JournalService({ repo, storage: store, log: log2 }); svc.onFront = () => fronts++;
  assert(svc.level === "info" && svc.cats.size === 0, "défauts : info, toutes catégories"); svc.setLevel("warn"); svc.toggleCat("api"); svc.toggleCat("sets"); svc.toggleCat("api"); assert(store.d.karlJournalLevel === "warn" && store.d.karlJournalCats === "sets", "filtres persistés"); assert.strictEqual(new JournalService({ repo, storage: store }).level, "warn", "…et relus");
  await svc.load(true); assert(calls[0].since === null && svc.server.length === 2 && svc.since === srv[1].ts && svc.categories.length === 3 && svc.stats.written === 9, "première lecture : tout, since mémorisé");
  resp = { entries: [{ ts: "2026-09-06T10:00:09.000+02:00", level: "warn", cat: "sets", msg: "nouveau" }] }; await svc.load(false); assert(calls[1].since === srv[1].ts && svc.server.length === 3, "relecture incrémentale par since");
  log2.error("front", "boum"); assert.strictEqual(fronts, 1, "le service est prévenu d'une entrée du front"); assert.deepStrictEqual(svc.entries().map(e => e.msg), ["RuntimeError", "nouveau"], "filtres : warn+ et catégorie sets"); svc.clearCats(); svc.setLevel("debug"); assert(svc.entries().some(e => e.msg === "boum"));
  assert.strictEqual(svc.badge(), 1, "badge : l'erreur front non vue"); svc.markSeen(); assert.strictEqual(svc.badge(), 0); resp = new Error("down"); await svc.load(false); assert.strictEqual(svc.error, "down", "panne serveur : dite, le front reste"); svc.clearFront(); assert.strictEqual(log2.entries().length, 0); svc.dispose();
  console.log("✓ service : filtres persistés, lecture puis relecture par since, front en direct, badge, panne");

  // — ViewModel + vue —
  const vm = new VM.JournalViewModel({ entries: merged, level: "info", cats: new Set(["sets"]), categories: ["api", "sets", "front"], q: "x", paused: true, error: null, stats: { written: 3, level: "info", path: "/logs/karl-agent.jsonl" } });
  assert(vm.rows.length === 4 && vm.rows[0].day === "2026-09-06" && vm.rows[1].day === "" && vm.rows[0].time === "10:00:01" && vm.rows[0].src === "srv" && vm.rows[1].src === "front" && vm.rows[2].cls === "jl-error" && vm.rows[0].fields === "status=200" && vm.errors === 1 && vm.warns === 1 && /3 écrit\(s\)/.test(vm.statsText) && /^2026-09-06T10:00:01.000\+02:00 info api GET \/x · status=200\n/.test(vm.plain));
  let h = String(V.Panel(vm));
  assert(/📜 Journal/.test(h) && /4 entrée\(s\)/.test(h) && /1 erreur\(s\)/.test(h) && /<select data-action="level">/.test(h) && /<option value="info" selected>/.test(h) && /data-action="cat-all"/.test(h) && /class="chip on" data-action="cat" data-cat="sets"/.test(h) && /data-action="q" placeholder="[^"]*" value="x"/.test(h) && /data-action="pause"[^>]*>▶ suivre</.test(h) && /data-action="copy"/.test(h) && /data-action="clear-front"/.test(h) && /data-action="reload"/.test(h) && /class="jl-day">2026-09-06</.test(h) && /class="jl-row jl-error"/.test(h) && /class="jl-fields">status=200</.test(h) && /3 écrit\(s\)/.test(h) && !/onclick|onchange/.test(h), "panneau : barre, lignes, stats, aucun on*");
  h = String(V.Rows(new VM.JournalViewModel({ entries: [], error: "down" }))); assert(/journal serveur injoignable : down/.test(h)); h = String(V.Rows(new VM.JournalViewModel({ entries: [] }))); assert(/rien à afficher/.test(h));
  console.log("✓ ViewModel et vue : lignes, jours, sévérités, barre de filtres, états vides");

  // — contrôleur —
  const card = fakeEl("journalcard"), badge = fakeEl("ln-journal"), list = fakeEl("list"); card.kids['[data-role="list"]'] = list;
  const ev = []; const tm = []; const log3 = L.createLog({ now: () => new Date("2026-09-06T11:00:00.000+02:00") }); resp = { entries: srv, categories: ["api", "sets", "front"], stats: { written: 1 } }; calls.length = 0;
  const svc3 = new JournalService({ repo, storage: { getItem: () => null, setItem() {} }, log: log3 });
  const ctr = mountJournal({ card, badge }, { service: svc3, log: log3, notify: (m, e) => ev.push(["toast", m, !!e]), clipboard: { writeText: async (txt) => ev.push(["clip", txt]) }, later: (fn, ms) => { tm.push([fn, ms]); return tm.length; }, clear: (id) => ev.push(["clear", id]) });
  assert(badge.style.display === "none", "badge masqué au départ");
  log3.error("front", "plantage"); assert(badge.textContent === "1" && badge.style.display === "", "panneau fermé : une erreur du front allume le badge");
  ctr.setVisible(true); await new Promise(r => setTimeout(r, 0)); assert(badge.style.display === "none" && calls.length === 1 && /📜 Journal/.test(card.innerHTML) && /plantage/.test(card.innerHTML) && /GET \/x/.test(card.innerHTML), "ouvert : badge éteint, serveur relu, front + serveur affichés"); assert(tm.some(x => x[1] === 5000), "suivi programmé");
  log3.warn("front", "encore"); assert(/encore/.test(list.innerHTML) && badge.style.display === "none", "ouvert : une entrée du front s'affiche sans allumer le badge");
  await card.click("pause"); assert(svc3.paused && /▶ suivre/.test(card.innerHTML)); log3.info("front", "pendant la pause"); assert(!/pendant la pause/.test(list.innerHTML), "en pause : rien ne bouge"); await card.click("pause"); assert(/pendant la pause/.test(card.innerHTML));
  await card.fire("change", { dataset: { action: "level" }, value: "error", closest: (s) => s === "[data-action]" ? { dataset: { action: "level" }, value: "error" } : null }); assert(svc3.level === "error" && /RuntimeError/.test(card.innerHTML) && !/GET \/x/.test(card.innerHTML), "sévérité minimale appliquée");
  await card.click("cat", { cat: "front" }); assert(svc3.cats.has("front") && !/RuntimeError/.test(card.innerHTML) && /plantage/.test(card.innerHTML), "catégorie filtrée"); await card.click("cat-all"); assert(!svc3.cats.size);
  ev.length = 0; await card.click("copy"); assert(ev.some(x => x[0] === "clip" && /RuntimeError/.test(x[1])) && ev.some(x => x[0] === "toast" && /journal copié/.test(x[1])), "copie du journal affiché");
  await card.click("clear-front"); assert(log3.entries().length === 0 && !/plantage/.test(card.innerHTML), "purge du journal du navigateur");
  calls.length = 0; await card.click("reload"); assert(calls.length === 1 && calls[0].since === null, "⟳ relit tout");
  const n0 = tm.length; ctr.setVisible(false); assert(ev.some(x => x[0] === "clear"), "fermé : le suivi s'arrête"); const tick = tm.find(x => x[1] === 5000)[0]; calls.length = 0; await tick(); assert.strictEqual(calls.length, 0, "un tick après fermeture ne relit pas");
  ctr.unmount(); assert.strictEqual(card.listenerCount, 0);
  console.log("✓ contrôleur : badge, ouverture/fermeture, suivi, pause, filtres, copie, purge, relecture");

  // — page et câblage —
  assert(/id="journalbtn" data-cmd="panel" data-arg="journal"/.test(html) && /id="ln-journal"/.test(html) && /id="cp-journal"/.test(html) && /id="journalcard"/.test(html), "bouton d'en-tête avec badge, panneau central");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  assert(/const log = createLog\(\{ remote: \(rec\) => post\(route\("log\.write"\), rec\)/.test(boot) && /installGlobalCapture\(log, window\)/.test(boot) && /log\.error\("front", label \+ " en erreur"/.test(boot) && /journal:\s+\{ label: "journal"/.test(boot) && /mountJournal\(\{ card: byId\("journalcard"\), badge: byId\("ln-journal"\) \}/.test(boot) && /version: VERSION, log, journal \}/.test(boot), "boot.js : journal créé avant tout montage, capture globale, safe() y écrit, panneau enregistré, karl.log exposé");
  assert(/case "journal": return openPanel/.test(fs.readFileSync(path.join(DIR, "src/modules/center/center.controller.js"), "utf8")), "le centre rouvre l'onglet journal");
  assert(/\.jl-row/.test(fs.readFileSync(path.join(DIR, "cockpit.css"), "utf8")), "le style du module est compilé");
  console.log("✓ page : bouton, panneau, boot, centre, style");
  console.log("\nTous les tests du journal passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
