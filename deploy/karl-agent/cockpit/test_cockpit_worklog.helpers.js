// test_cockpit_worklog.helpers — faux DOM, échappement de référence et fixtures partagés par les trois suites du domaine worklog (RM3019 :
// test scindé par couche — un agent qui modifie une vue lit test_cockpit_worklog.view.js / .controller.js, pas le modèle). CommonJS.
"use strict";
const settle = () => new Promise(r => setTimeout(r, 10));
const escO = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fakeElement(id) { const L = []; let inner = ""; const kids = {}; return { id, kids, textContent: "", style: {}, dataset: {}, get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, querySelector(sel) { return kids[sel] || null; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async click(action, data, extra) { const n = Object.assign({ dataset: Object.assign({ action }, data || {}), closest: () => n }, extra || {}); for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); return n; } }; }
  const CFG = { closable_statuses: ["a_mep", "a_tester_demandeur", "a_tester_dev", "en_mep"], batch_modes: { traiter: { statuses: ["a_faire", "en_cours", "a_corriger"], skip: { a_tester_demandeur: "livré" } }, atester: { statuses: ["en_cours"] }, etudier: { statuses: ["a_etudier_chiffrer"] } } };
  const SEL = [{ rm_id: "1", status: "a_etudier_chiffrer" }, { rm_id: "2", status: "a_faire" }, { rm_id: "3", status: "a_tester_demandeur" }, { rm_id: "4", status: "en_cours" }];
  const W = { found: true, checked_ts: 1000, notifications: [{ level: "critical", kind: "hook", ref: "RM1", message: "boum <b>", ts: "t1" }, { level: "info", message: "ok" }], notifications_done: [{}, {}], mrs_pending: [{ iid: 5, ref: "RM2", url: "https://g/5", target: "dev" }], requests_open: [{ n: 3, text: "fais <x>", ts: "t2" }],
    buckets: { todo: [{ ref: "RM1", status: "a_faire", label: "Un <b>", client: "c", project: "p", checklist: { done: 1, total: 2, items: ["reste"] }, next: "suite", note: "n" }, { ref: "libre-x", status: "?", label: "chantier" }], done: [{ ref: "RM2", status: "a_tester_demandeur", opened_status: "en_cours", drifted: true, client: "c", project: "p" }, { ref: "RM3", status: "ferme", client: "d", project: "q" }] },
    mr_stage: { RM2: { stage: "open", url: "https://g/mr/2", count: 1, mrs: [] } }, docs: { RM1: [["docs/cdc.md", "output"], ["'memory: x.md'", "ref"]] } };
module.exports = { settle, escO, fakeElement, CFG, SEL, W };
