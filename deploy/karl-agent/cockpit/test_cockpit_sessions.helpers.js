// test_cockpit_sessions.helpers — faux DOM, fixtures et faux dépôt partagés par les trois suites du domaine sessions (RM3018 : test scindé
// par couche — un agent qui modifie une vue lit test_cockpit_sessions.view.js / .controller.js, pas le modèle). CommonJS (require).
"use strict";
function fakeEl(id, extra) { const L = []; let inner = ""; const self = Object.assign({ id, style: {}, value: "", dataset: {}, kids: {}, textContent: "", title: "", checked: false, options: [{ textContent: "" }], get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, querySelector(sel) { return self.kids[sel] || null; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, target, extra2) { for (const [t, f] of [...L]) if (t === type) await f(Object.assign({ target, currentTarget: self, preventDefault() {}, stopPropagation() {} }, extra2 || {})); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: (sel) => (sel === "[data-action]" || sel === '[data-action="' + action + '"]') ? n : null, disabled: false }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, currentTarget: self, preventDefault() {}, stopPropagation() {} }); return n; } }, extra || {}); return self; }
const settle = () => new Promise(r => setTimeout(r, 0));
const now = Math.floor(Date.now() / 1000);
const SETS = [{ name: "default", label: "Défaut" }, { name: "pm", label: "PM", derived: true }];
const writable = (sets, name, view) => !/^client:/.test(String(view || "")) && !((sets || []).find(s => s && s.name === name) || {}).derived;
/** Le faux dépôt (approve / approveAll / autoYes) : `calls` journalise ; `st.clock` est l'horloge injectée au service (gel RM2346). */
function mkRepo(t) {
  const calls = []; const st = { clock: 1000 };
  const repo = { async approve(rm) { calls.push(["approve", rm]); if (rm === "ko") throw new Error("plus de question"); return { sent: "y" }; }, async approveAll() { calls.push(["all"]); return { approved: [{ rm_id: "1" }, { rm_id: "2" }] }; }, async compact(rm) { calls.push(["compact", rm]); return { cmd: "/compact" }; }, async autoYes(rm, m) { calls.push(["auto", rm, m]); return m ? { auto_yes_until: t + 60 * m } : {}; } };
  return { repo, calls, st };
}
module.exports = { fakeEl, settle, now, SETS, writable, mkRepo };
