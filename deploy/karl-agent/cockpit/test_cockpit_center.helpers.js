// test_cockpit_center.helpers — échappement de référence, faux DOM et fixtures partagés par les suites du cluster centre (RM3020 : test
// scindé par couche — un agent qui modifie une vue lit test_cockpit_center.view.js / .controller.js, pas le modèle). CommonJS.
"use strict";
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fakeElement() { const L = []; let inner = ""; return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true,
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async click(action, data) { const n = { dataset: { action, ...(data || {}) } }; for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => s === "[data-action]" ? n : null }, preventDefault() {}, stopPropagation() {} }); } }; }
  const RC = { "2744": { found: true, title: "Tableau de bord : contenu coupé en haut" }, "2673": { found: true, title: "Améliorations ergonomiques PM" }, "9999": { found: false } };
module.exports = { esc, fakeElement, RC };
