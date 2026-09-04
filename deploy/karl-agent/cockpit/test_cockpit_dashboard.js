#!/usr/bin/env node
// Tests du tableau de bord migré (RM2889, L4) — porte RM2697/RM2698 de test_cockpit.js.
// Lancer : node deploy/karl-agent/cockpit/test_cockpit_dashboard.js
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
function fakeElement() {
  const L = []; let inner = "";
  return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true,
    addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
    get listenerCount() { return L.length; },
    async click(action, arg) { const n = { dataset: { action, arg } }; for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => s === "[data-action]" ? n : null }, stopPropagation() {} }); },
    async change(filter, value) { const n = { dataset: { filter }, value }; for (const [t, f] of [...L]) if (t === "change") await f({ target: { closest: s => s === "[data-filter]" ? n : null } }); } };
}
(async () => {
  const { attentionRows } = await import(path.join(DIR, "src/models/dashboard/attention.js"));
  const { DashboardViewModel } = await import(path.join(DIR, "src/viewmodels/dashboard/DashboardViewModel.js"));
  const { Dashboard, Attention, Alerts } = await import(path.join(DIR, "src/views/dashboard/Dashboard.view.js"));
  const { mountDashboard } = await import(path.join(DIR, "src/controllers/dashboard.controller.js"));
  const OV = { projects: [{ client: "acme", project: "shop", counts: {},
    tickets: [{ rm_id: "10", status: "a_tester_demandeur", title: "livré", bucket: "waiting" }, { rm_id: "11", status: "en_cours", title: "en cours", bucket: "active" }, { rm_id: "12", status: "a_mep", title: "à déployer", bucket: "waiting" }],
    mrs: [{ iid: "9", ref: "RM11", url: "https://x/9", alive: false }], requests: [{ text: "une demande" }], sessions: [{ sid: "70", alive: true, title: "S70" }] }] };
  const SESS = { "70": { state: "idle", client: "acme", project: "shop", title: "S70" }, "71": { state: "attention", client: "acme", project: "shop", title: "S71" } };
  const rows = attentionRows(OV, SESS, { stale: [] });
  assert.deepStrictEqual(rows.map(r => r.kind), ["question", "test", "mr", "mep", "idle", "request"], "l'ordre suit le COÛT de l'attente");
  assert.strictEqual(rows[0].verb, "réponds"); assert.strictEqual(rows[1].rm_id, "10"); assert(rows[2].text.includes("session éteinte"));
  assert(/1 ticket\(s\) en cours/.test(rows[4].text));
  const stale = attentionRows({ projects: [] }, { "80": { client: "a", project: "b", title: "S" } }, { stale: ["80"] });
  assert.strictEqual(stale.length === 1 && stale[0].icon, "🕓", "question laissée sans réponse : signalée");
  assert.strictEqual(attentionRows(OV, SESS, { client: "autre" }).length, 0); assert.strictEqual(attentionRows(OV, SESS, { project: "shop" }).length, rows.length);
  assert.deepStrictEqual(attentionRows(null, null, {}), []);
  assert.strictEqual(attentionRows({ projects: [{ client: "a", project: "b", tickets: [], mrs: [], requests: [], sessions: [{ sid: "9", alive: true }] }] }, {}, {}).length, 0);
  const parAge = attentionRows({ projects: [{ client: "a", project: "b", mrs: [], requests: [], sessions: [], tickets: [{ rm_id: "2", status: "a_tester_demandeur", title: "récent", updated: "2026-08-17" }, { rm_id: "1", status: "a_tester_demandeur", title: "vieux", updated: "2026-06-01" }] }] }, {}, {});
  assert.deepStrictEqual(parAge.map(r => r.rm_id), ["1", "2"], "le plus ancien d'abord");
  assert(/^RM70$/.test(attentionRows({ projects: [] }, { "70": { state: "attention" } }, {})[0].text), "sans titre, le nom tmux");
  console.log("✓ modèle (RM2697) : tri par nature d'attente, filtres, ancienneté, données absentes");

  const mk = (ov, al, ctx) => new DashboardViewModel({ overview: ov || { projects: [] }, alerts: al || { alerts: [] } }, ctx || {});
  const vm = mk(OV, null, { sessions: SESS, stale: [] });
  assert.deepStrictEqual(vm.clients, ["acme"]); assert.deepStrictEqual(vm.projects, ["shop"]); assert.strictEqual(vm.counts.test, 1);
  assert.deepStrictEqual(vm.sections().map(s => [s.kind, s.rows[0].action]), [["question", "attach"], ["test", "review"], ["mr", "open"], ["mep", "review"], ["idle", "attach"], ["request", null]]);
  const many = { projects: [{ client: "a", project: "b", mrs: [], requests: [], sessions: [], tickets: Array.from({ length: 40 }, (_, i) => ({ rm_id: String(1000 + i), status: "a_tester_demandeur", title: "t", updated: "2026-08-" + String(10 + (i % 20)).padStart(2, "0") })) }] };
  const sm = mk(many).sections()[0];
  assert.strictEqual(sm.rows.length, 5); assert.strictEqual(sm.more, 35); assert.strictEqual(sm.total, 40);
  const AL = { total: 30, hidden: 18, alerts: [{ kind: "verdict", key: "t:4", age_days: 48.2, rm_id: "4", client: "acme", project: "shop", label: "livré, attend ton verdict", title: "un titre" }, { kind: "mr", key: "m:r:9", age_days: 29, iid: "9", url: "https://x/9", client: "acme", project: "shop", label: "MR ouverte, pas mergée" }] };
  assert.deepStrictEqual(mk(null, AL).alerts().map(a => a.age), [48, 29]); assert.strictEqual(mk(null, AL).alertTotal, 30);
  assert(!mk().hasContent && mk(null, AL).hasContent);
  console.log("✓ ViewModel : filtres, sections plafonnées à 5 avec le reste annoncé, alertes datées");

  const dh = String(Attention(vm));
  assert(/dash-sec/.test(dh) && /une session attend ta réponse/.test(dh));
  assert(/data-action="attach" data-arg="71"/.test(dh), "une session s'attache en un clic");
  assert(/data-action="review" data-arg="10"/.test(dh), "un ticket ouvre sa fiche");
  assert(/data-action="open" data-arg="https:\/\/x\/9"/.test(dh), "une MR s'ouvre sur la forge");
  assert(!/onclick=/.test(dh), "zéro handler inline");
  assert(/rien n’attend de toi/.test(String(Attention(mk()))));
  const dhMany = String(Attention(mk(many)));
  assert.strictEqual((dhMany.match(/dash-row/g) || []).length, 5); assert(/… et 35 autre/.test(dhMany)); assert(/dash-chip[^>]*>🧪 40</.test(dhMany)); assert(/\(40\)/.test(dhMany));
  assert(/2026-06-01/.test(String(Attention(mk({ projects: [{ client: "a", project: "b", mrs: [], requests: [], sessions: [], tickets: [{ rm_id: "1", status: "a_tester_demandeur", updated: "2026-06-01" }] }] })))));
  const xss = String(Attention(mk({ projects: [{ client: "<img src=x>", project: "p", mrs: [], requests: [{ text: "<script>" }], sessions: [], tickets: [] }] })));
  assert(!/<img|<script>/.test(xss), "client et texte échappés");
  assert.strictEqual(String(Alerts(mk())), "", "rien à signaler ⇒ RIEN d'affiché");
  const ah = String(Alerts(mk(null, AL)));
  assert(/⚠ dérives \(30\)/.test(ah) && /48 j/.test(ah) && /29 j/.test(ah) && /… et 18 dérive/.test(ah));
  assert(/data-action="snooze" data-arg="t:4"/.test(ah) && /⏳ 7 j/.test(ah) && /data-action="review" data-arg="4"/.test(ah) && /href="https:\/\/x\/9"/.test(ah));
  assert(!/<img|<script>|<b>t/.test(String(Alerts(mk(null, { alerts: [{ kind: "mr", key: "<b>k", age_days: 1, client: "<img src=x>", project: "p", label: "<script>", title: "<b>t" }] })))));
  const full = String(Dashboard(mk(OV, AL, { sessions: SESS })));
  assert(full.indexOf("dash-alerts") < full.indexOf("dash-sum"), "la dérive s'affiche avant l'état");
  assert(/data-filter="client"/.test(full) && /<option value="acme">acme<\/option>/.test(full) && /<option value="" selected>tous<\/option>/.test(full));
  console.log("✓ vues (RM2697/RM2698) : lignes, plafond, alertes avant l'état, filtres, échappement");

  const el = fakeElement(); const ev = []; let vis = true;
  const svc = { overview: OV, alerts: AL, async reload() { ev.push("reload"); return this; }, setBlock(d) { ev.push(["block", d]); this.overview = d.overview; this.alerts = d.alerts; }, async snooze(k) { ev.push(["snooze", k]); return { ok: true, message: "reporté" }; } };
  const h = mountDashboard(el, { service: svc, visible: () => vis, sessions: () => SESS, stale: () => [], pull: () => ev.push("pull"),
    attach: s => ev.push(["attach", s]), openReview: r => ev.push(["review", r]), open: u => ev.push(["open", u]), notify: m => ev.push(["toast", m]), shown: (on, has) => ev.push(["shown", on, has]) });
  await h.refresh(); assert.strictEqual(ev.pop(), "pull", "sans force, on passe par la pile /refresh");
  await h.refresh(true); assert.deepStrictEqual(ev.slice(-2), ["reload", ["shown", true, true]]); assert(/Ce qui requiert ton attention/.test(el.innerHTML));
  await el.click("attach", "71"); assert.deepStrictEqual(ev.pop(), ["attach", "71"]);
  await el.click("review", "10"); assert.deepStrictEqual(ev.pop(), ["review", "10"]);
  await el.click("snooze", "t:4"); assert.deepStrictEqual(ev.filter(x => x[0] === "snooze" || x[0] === "toast").map(x => x[1]), ["t:4", "reporté"]);
  await el.change("client", "autre"); assert.strictEqual(h.filter.client, "autre"); assert(/rien n’attend de toi/.test(el.innerHTML), "filtre appliqué au rendu");
  h.setBlock({ overview: { projects: [] }, alerts: { alerts: [] } }); assert.deepStrictEqual(ev.pop(), ["shown", true, false], "bloc /refresh → rendu, indice réaffiché");
  vis = false; h.render(); assert.deepStrictEqual(ev.pop(), ["shown", false, false], "invisible : masqué, pas rendu");
  await h.refresh(true); assert.notStrictEqual(ev[ev.length - 1], "reload", "invisible : aucun recalcul");
  h.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur : pile /refresh vs recalcul, gestes, filtre, bloc poussé, visibilité, démontage");
  console.log("\nTous les tests du tableau de bord passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
