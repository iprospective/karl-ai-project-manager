#!/usr/bin/env node
// Tests de la sonde mémoire (RM3007) — core/probe (normalisation, fuite = un compteur qui grimpe sans redescendre, rendus/min, sonde à
// horloge injectée), core/dom (module d'un montage lu dans la pile, rendus, nœuds, ventilation), module memory (préférences, courbe,
// lignes, ViewModel, vue sans on*, contrôleur : démarrage/arrêt persistés, cadence, export, démontage) et le câblage de la page.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
function fakeEl(id) { const L = []; let inner = ""; const self = { id, tagName: "DIV", style: {}, textContent: "", kids: {}, get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, querySelector(sel) { return self.kids[sel] || null; }, querySelectorAll() { return { length: (inner.match(/<[a-z]/g) || []).length }; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, target) { for (const [t, f] of [...L]) if (t === type) await f({ target, preventDefault() {}, stopPropagation() {} }); await new Promise(r => setTimeout(r, 0)); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n, value: "", tagName: "BUTTON" }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await new Promise(r => setTimeout(r, 0)); return n; } }; return self; }
const mem = () => { const d = {}; return { getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); }, removeItem: (k) => { delete d[k]; }, d }; };
(async () => {
  const P = await import(path.join(DIR, "src/core/probe.js"));
  const D = await import(path.join(DIR, "src/core/dom.js"));
  const M = await import(path.join(DIR, "src/modules/memory/memory.js"));
  const VM = await import(path.join(DIR, "src/modules/memory/MemoryViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/memory/Memory.view.js"));
  const { mountMemory } = await import(path.join(DIR, "src/modules/memory/memory.controller.js"));

  // — core/probe —
  assert.strictEqual(P.storeModule("ticket.resolve"), "ticket"); assert.strictEqual(P.storeModule("session.registry"), "sessions"); assert.strictEqual(P.storeModule("mail"), "mail");
  const s0 = P.normalize({ dom: { sessions: { mounted: 2, nodes: 40, pending: 3, renders: 9 } }, stores: [{ name: "session.registry", entries: 5, subscribers: 1 }, { name: "ticket.resolve", entries: 7, subscribers: 2 }], heap: 12345 }, 1000);
  assert.deepStrictEqual(s0.modules.sessions, { mounted: 2, nodes: 40, pending: 3, renders: 9, entries: 5, subscribers: 1 }, "DOM et stores fusionnés par module"); assert.strictEqual(s0.modules.ticket.entries, 7); assert.strictEqual(s0.total.nodes, 40); assert.strictEqual(s0.heap, 12345);
  const mk = (i, nodesA, pendB) => ({ t: i * 1000, modules: { a: { nodes: nodesA, pending: 1, entries: 0, subscribers: 0, renders: i * 3 }, b: { nodes: 10, pending: pendB, entries: 0, subscribers: 0, renders: 0 } }, total: {} });
  const grimpe = [0, 1, 2, 3, 4, 5].map(i => mk(i, 100 + i * 10, 2));
  assert.deepStrictEqual(P.detectLeaks(grimpe), [{ module: "a", counter: "nodes", from: 100, to: 150 }], "a.nodes grimpe sans redescendre → alerte ; b stable → rien");
  const redescend = [0, 1, 2, 3, 4, 5].map(i => mk(i, i === 4 ? 90 : 100 + i * 10, 2)); assert.deepStrictEqual(P.detectLeaks(redescend), [], "une baisse dans la fenêtre = pas une fuite");
  const petit = [0, 1, 2, 3, 4, 5].map(i => mk(i, 100 + i, 2)); assert.deepStrictEqual(P.detectLeaks(petit), [], "hausse de 5 sur 100 (< 20 %) : pas une fuite");
  assert.deepStrictEqual(P.detectLeaks(grimpe.slice(0, 3)), [], "pas assez d'échantillons → rien"); assert.strictEqual(P.detectLeaks([0, 1, 2, 3, 4, 5].map(i => mk(i, 100, 2 + i * 2)))[0].counter, "pending", "les écouteurs retenus sont surveillés aussi");
  assert.strictEqual(P.rendersPerMin(mk(0), mk(1), "a"), 180, "3 rendus en 1 s = 180/min"); assert.strictEqual(P.rendersPerMin(null, mk(1), "a"), 0);
  let t = 0, nodes = 20; const timers = []; const pr = P.createProbe({ sample: () => ({ dom: { x: { mounted: 1, nodes, pending: 1, renders: t } }, stores: [] }), now: () => t * 1000, later: (fn, ms) => { timers.push([fn, ms]); return timers.length; }, clear: (id) => { timers[id - 1] = null; }, capacity: 4 });
  assert(!pr.on && pr.latest === null, "désactivée : rien"); const seen = []; const off = pr.subscribe(s => seen.push(s.t));
  pr.start(5000); assert(pr.on && pr.interval === 5000 && timers[0][1] === 5000 && pr.history.length === 1, "start : minuterie posée + premier échantillon immédiat");
  for (t = 1; t < 6; t++) { nodes += 10; timers[0][0](); }
  assert.strictEqual(pr.history.length, 4, "historique borné (capacity)"); assert.deepStrictEqual(pr.series("x", "nodes"), [40, 50, 60, 70]); assert.deepStrictEqual(pr.modules(), ["x"]); assert.strictEqual(seen.length, 6, "abonné notifié à chaque échantillon");
  assert.strictEqual(pr.rate("x"), 60); off(); pr.tick(); assert.strictEqual(seen.length, 6, "désabonnement");
  const j = pr.toJSON(); assert(j.samples === 4 && Array.isArray(j.history) && Array.isArray(j.alerts) && j.interval === 5000, "export JSON");
  pr.stop(); assert(!pr.on && timers[0] === null, "stop : minuterie retirée"); pr.reset(); assert.strictEqual(pr.history.length, 0);
  const ko = P.createProbe({ sample: () => { throw new Error("boum"); }, now: () => 1, later: () => 1, clear: () => {} }); assert.strictEqual(ko.tick().error, "boum", "un échantillonneur qui casse ne casse pas la sonde");
  assert.throws(() => P.createProbe({}), /sample\(\) est requis/);
  console.log("✓ core/probe : normalisation par module, fuite = grimpe sans redescendre, rendus/min, sonde à horloge injectée, export, coût nul désactivée");

  // — core/dom : module d'un montage, rendus, nœuds, ventilation —
  assert.strictEqual(D.moduleFromStack("Error\n    at mount (file:///x/src/core/dom.js:40:3)\n    at mountJournal (file:///x/src/modules/journal/journal.controller.js:18:20)\n    at file:///x/src/boot.js:200:1"), "journal");
  assert.strictEqual(D.moduleFromStack("Error\n    at mount (file:///x/src/core/dom.js:40:3)\n    at file:///x/src/boot.js:200:1"), "boot"); assert.strictEqual(D.moduleFromStack(""), "autre");
  const host = fakeEl("h"); const before = D.domStatsByModule(); const hd = D.mount(host, "<b>a</b><i>b</i>", { module: "demo" });
  hd.update("<b>a</b>"); hd.track(() => {}); const by = D.domStatsByModule().demo;
  assert.deepStrictEqual(by, { mounted: 1, pending: 1, nodes: 1, renders: 2 }, "ventilé : 1 montage, 1 libération retenue, 1 nœud, 2 rendus"); assert.strictEqual(hd.module, "demo"); assert(!("demo" in before));
  hd.unmount(); assert(!("demo" in D.domStatsByModule()), "démonté → sort de la ventilation"); assert.deepStrictEqual(Object.keys(D.domStats()), ["mounted", "pending"], "domStats() garde sa forme");
  console.log("✓ core/dom : module lu dans la pile (ou nommé), rendus et nœuds par montage, ventilation par module");

  // — modèle —
  const st = mem(); assert(!M.readOn(st) && M.readInterval(st) === 10); M.writeOn(st, true); M.writeInterval(st, 30); assert(M.readOn(st) && M.readInterval(st) === 30 && st.d.karlProbe === "1"); M.writeOn(st, false); assert(!M.readOn(st) && !("karlProbe" in st.d)); M.writeInterval(st, 7); assert.strictEqual(M.readInterval(st), 10, "cadence inconnue → défaut");
  assert.strictEqual(M.sparkline([1]), ""); assert.strictEqual(M.sparkline([0, 10], 100, 24), "0.0,22.0 100.0,2.0", "polyline : min en bas, max en haut"); assert.strictEqual(M.sparkline([5, 5, 5], 100, 24).split(" ").length, 3);
  assert.strictEqual(M.trend([1, 2, 3]), "↗"); assert.strictEqual(M.trend([3, 2, 1]), "↘"); assert.strictEqual(M.trend([2, 2]), "→"); assert.strictEqual(M.trend([]), "→");
  assert.strictEqual(M.fmtHeap(null), ""); assert.strictEqual(M.fmtHeap(3 * 1024 * 1024), "3.0 Mo"); assert.strictEqual(M.fmtHeap(2048), "2 ko");
  const pr2 = P.createProbe({ sample: () => ({ dom: { x: { mounted: 1, nodes, pending: 1, renders: t } }, stores: [] }), now: () => t * 1000, later: (fn, ms) => { timers.push([fn, ms]); return timers.length; }, clear: (id) => { timers[id - 1] = null; }, capacity: 12 });
  t = 0; nodes = 20; pr2.start(5000); for (t = 1; t < 7; t++) { nodes += 10; timers[timers.length - 1][0](); }
  const rows = M.rowsFor(pr2); assert(rows.length === 1 && rows[0].module === "x" && rows[0].nodes === 80 && rows[0].trend === "↗" && rows[0].spark && rows[0].rate === 60, JSON.stringify(rows));
  assert.deepStrictEqual(rows[0].leaks, ["nodes 30→80"], "la fuite détectée est portée par la ligne");
  console.log("✓ modèle : préférences persistées, courbe, tendance, lignes par module avec fuite");

  // — ViewModel + vue —
  const vm = new VM.MemoryViewModel({ probe: pr2, on: pr2.on, interval: 5 });
  assert(vm.intervals.find(i => i.value === 5).selected && vm.rows.length === 1 && vm.alerts.length === 1 && vm.samples === 7 && /active — un échantillon toutes les 5 s, 7 retenu\(s\)/.test(vm.stateText) && vm.total.nodes === 80, vm.stateText);
  const off2 = new VM.MemoryViewModel({ probe: P.createProbe({ sample: () => ({}), later: () => 1, clear: () => {} }), on: false, interval: 10 }); assert(/désactivée — coût nul/.test(off2.stateText) && off2.rows.length === 0 && off2.total === null);
  const pv = String(V.Panel(vm)); assert(/🧠 Mémoire par module/.test(pv) && /data-action="toggle"/.test(pv) && /■ arrêter/.test(pv) && /data-action="export"/.test(pv) && /<option value="5" selected>/.test(pv) && /grimpe sans redescendre/.test(pv) && /class="mp-leak"/.test(pv) && /<polyline points="/.test(pv) && /7 échantillon\(s\)/.test(pv) && !/\son[a-z]+=/.test(pv), "panneau : barre, alerte, tableau, courbe, pied, aucun on*");
  const pv0 = String(V.Panel(off2)); assert(/▶ démarrer/.test(pv0) && /sonde désactivée — démarre-la/.test(pv0));
  const xssProbe = P.createProbe({ sample: () => ({ dom: { "<img src=x>": { mounted: 1, nodes: 1, pending: 0, renders: 1 } } }), later: () => 1, clear: () => {} }); xssProbe.tick();
  assert(!/<img src=x>/.test(String(V.Table(new VM.MemoryViewModel({ probe: xssProbe, on: true, interval: 10 })))), "nom de module échappé");
  const sb = String(V.SettingsBlock(vm)); assert(/🧠 Sonde mémoire/.test(sb) && /type="checkbox" data-action="toggle" checked/.test(sb) && /data-cmd="panel" data-arg="memory"/.test(sb) && !/\son[a-z]+=/.test(sb), sb);
  console.log("✓ ViewModel et vue : état, cadence, alertes, tableau, échappement, bloc des réglages, aucun on*");

  // — contrôleur —
  pr2.stop(); pr.stop(); pr.reset(); const st2 = mem(); const ev = []; const card = fakeEl("memorycard"), sett = fakeEl("probecard"); const dl = [];
  const ctr = mountMemory({ card, settings: sett }, { probe: pr, storage: st2, notify: (m, e) => ev.push(["toast", m, !!e]), help: (t2) => ev.push(["help", t2]), download: (n, txt) => dl.push([n, txt]) });
  assert(!pr.on && card.innerHTML === "" && /Sonde mémoire/.test(sett.innerHTML), "préférence absente : sonde éteinte, panneau non rendu tant qu'il est caché, bloc des réglages rendu");
  ctr.setVisible(true); assert(/sonde désactivée/.test(card.innerHTML), "visible : rendu");
  await card.click("toggle"); assert(pr.on && st2.d.karlProbe === "1" && pr.interval === 10000 && ev.some(x => x[0] === "toast" && /démarrée \(toutes les 10 s\)/.test(x[1])) && /■ arrêter/.test(card.innerHTML) && /checked/.test(sett.innerHTML), "toggle : démarre, persiste, re-rend les deux hôtes");
  const n0 = pr.history.length; await card.click("tick"); assert.strictEqual(pr.history.length, n0 + 1, "⟳ maintenant");
  await sett.fire("change", { dataset: { action: "interval" }, value: "30", closest() { return this; } }); assert(pr.interval === 30000 && st2.d.karlProbeInterval === "30" && ctr.interval() === 30, "cadence changée depuis les réglages, sonde relancée");
  await card.click("export"); assert(dl.length === 1 && /^karl-memoire-.*\.json$/.test(dl[0][0]) && JSON.parse(dl[0][1]).samples >= 1 && ev.some(x => /exporté/.test(x[1])), "export JSON via download prêté");
  await card.click("reset"); assert.strictEqual(pr.history.length, 0); await card.click("help"); assert(ev.some(x => x[0] === "help" && x[1] === "reglages"));
  await sett.fire("change", { dataset: { action: "toggle" }, tagName: "INPUT", type: "checkbox", closest() { return this; } }); assert(!pr.on && !("karlProbe" in st2.d), "la case des réglages arrête et oublie la préférence");
  ctr.setVisible(false); ctr.unmount(); assert.strictEqual(card.listenerCount + sett.listenerCount, 0, "unmount libère tout");
  const st3 = mem(); st3.setItem("karlProbe", "1"); st3.setItem("karlProbeInterval", "5"); const pr3 = P.createProbe({ sample: () => ({}), later: (fn, ms) => { timers.push([fn, ms]); return timers.length; }, clear: () => {} });
  const c3 = mountMemory({ card: fakeEl("c"), settings: null }, { probe: pr3, storage: st3 }); assert(pr3.on && pr3.interval === 5000, "préférence posée → la sonde démarre au montage, à la cadence mémorisée"); c3.unmount();
  console.log("✓ contrôleur : démarrage/arrêt persistés, cadence, échantillon, export, aide, démarrage automatique, démontage");

  // — page et câblage —
  assert(/<div class="cpanel" id="cp-memory" style="display:none">/.test(html) && /<div class="card" id="memorycard"><\/div>/.test(html) && /<div class="card" id="probecard"><\/div>/.test(html), "index.html : panneau central + bloc des réglages");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  assert(/const probe = createProbe\(\{ sample: \(\) => \(\{ dom: domStatsByModule\(\), stores: storeStats\(\)/.test(boot) && /mountMemory\(\{ card: byId\("memorycard"\), settings: byId\("probecard"\) \}/.test(boot) && /memory:\s+\{ label: "mémoire"/.test(boot) && /probe: probe\.latest/.test(boot) && /modules: domStatsByModule\(\)/.test(boot), "boot : sonde, montage, panneau, karl.stats()");
  const center = fs.readFileSync(path.join(DIR, "src/modules/center/center.controller.js"), "utf8"); const E = await import(path.join(DIR, "src/core/entities.js")); assert(E.entity("memory").panel && E.iconOf("memory") === "🧠" && /entity\(t\.kind\)/.test(center), "le centre rouvre l'onglet mémoire par le registre des types (RM3002)");
  assert(/\.mp-table\b/.test(fs.readFileSync(path.join(DIR, "cockpit.css"), "utf8")), "style compilé");
  console.log("✓ page : panneau, bloc des réglages, boot, centre, style");
  console.log("\nTous les tests de la sonde mémoire passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
