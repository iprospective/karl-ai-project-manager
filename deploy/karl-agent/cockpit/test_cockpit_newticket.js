#!/usr/bin/env node
// Tests de la surface « nouveau ticket » migrée (RM2889) — porte RM2672 (formulaire), RM2726, RM2752.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
function fakeElement() { const L = []; let inner = ""; const nodes = {}; return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, nodes,
  querySelector(sel) { if (sel === "#ntf-projects") return nodes.projects || (nodes.projects = { innerHTML: "" }); if (sel === "#ntf-bugbox") return nodes.bugbox || (nodes.bugbox = { style: { display: "none" } }); if (sel.startsWith("input[name")) return nodes.radio || null; return null; },
  querySelectorAll(sel) { return sel === "[data-field]" ? Object.values(nodes.fields || {}) : []; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, sel, n) { for (const [t, f] of [...L]) if (t === type) await f({ target: { closest: s => s === sel ? n : null } }); } }; }
(async () => {
  const M = await import(path.join(DIR, "src/modules/newticket/newTicket.js"));
  const { NewTicketViewModel } = await import(path.join(DIR, "src/modules/newticket/NewTicketViewModel.js"));
  const { NewTicketForm, ClientProjectPicker, ProjectRadios } = await import(path.join(DIR, "src/modules/newticket/NewTicket.view.js"));
  const { NewTicketService } = await import(path.join(DIR, "src/modules/newticket/newticket.service.js"));
  const { mountNewTicket } = await import(path.join(DIR, "src/modules/newticket/newticket.controller.js"));
  const PROJ = [{ client: "acme", project: "boutique" }, { client: "acme", project: "infra" }, { client: "iprospective", project: "pm-ai-agents" }, { client: "vide", project: "" }];
  const mk = (client, project, projects = PROJ) => new NewTicketViewModel({ types: [{ value: "feature", label: "feature" }, { value: "bugfix", label: "bugfix" }], priorities: ["low", "normal", "high", "urgent"], projects }, { client, project });
  // — RM2726 : filtre client, radios projet, défauts sûrs —
  const pick = String(ClientProjectPicker(mk("acme", "infra")));
  assert(/id="ntf-client"/.test(pick) && /id="ntf-projects"/.test(pick) && /<option value="acme" selected>/.test(pick) && /value="acme\/infra" checked/.test(pick) && !/pm-ai-agents/.test(pick));
  assert(/data-field="client"/.test(pick) && !/onchange=/.test(pick), "changer de client passe par data-field, pas onchange");
  const pickDefault = String(ClientProjectPicker(mk("inconnu", "")));
  assert(/<option value="acme" selected>/.test(pickDefault) && /value="acme\/boutique" checked/.test(pickDefault) && (pickDefault.match(/checked/g) || []).length === 1);
  assert(/aucun projet pour ce client/.test(String(ProjectRadios(mk("vide", "").radios("vide")))));
  assert(/aucun projet connu/.test(String(ClientProjectPicker(mk("", "", [])))));
  assert(!/value="a"b/.test(String(ProjectRadios(mk('a"b', "", [{ client: 'a"b', project: 'p"q' }]).radios('a"b')))), "client/projet échappés dans value");
  console.log("✓ création de ticket (RM2726) : filtre client, radios projet, défauts sûrs");
  // — RM2672 : formulaire pleine page complet —
  const form = String(NewTicketForm(mk("clientb", "infra", [{ client: "clientb", project: "infra" }])));
  ["ntf-title", "ntf-client", "ntf-projects", "ntf-type", "ntf-prio", "ntf-tags", "ntf-desc", "ntf-agent-test", "ntf-env", "ntf-human", "ntf-ai", "ntf-diff"].forEach(id => assert(form.includes('id="' + id + '"'), "champ manquant : " + id));
  assert(/<option value="feature" selected>/.test(form) && /<option value="normal" selected>/.test(form) && /value="clientb\/infra" checked/.test(form) && /rows="12"/.test(form));
  assert(/data-action="submit"/.test(form) && !/onclick=|onchange=/.test(form), "zéro handler inline");
  // — RM2752 : bugfix → étapes de reproduction —
  ["ntf-bugbox", "ntf-bug-steps", "ntf-bug-repro"].forEach(id => assert(form.includes('id="' + id + '"')));
  assert(/id="ntf-bugbox" style="display:none"/.test(form) && /<option value="always" selected>/.test(form)); M.REPRO.forEach(v => assert(form.includes('value="' + v + '"')));
  assert.deepStrictEqual(M.buildTicketBody({ title: " ", project: "a/b" }), { error: "Titre requis" });
  assert.deepStrictEqual(M.buildTicketBody({ title: "x", project: "" }), { error: "Projet requis — ce client n’a aucun projet" });
  assert.deepStrictEqual(M.buildTicketBody({ title: "x", project: "a/b", type: "bugfix", bug_steps: " " }), { error: "Étapes de reproduction requises pour un bugfix" });
  const ok = M.buildTicketBody({ title: " Bug ", project: "a/b", type: "bugfix", priority: "high", tags: " x ", description: "d", bug_steps: "1. x", bug_reproducibility: "" });
  assert.strictEqual(ok.body.title, "Bug"); assert.strictEqual(ok.body.tags, "x"); assert.strictEqual(ok.body.bug_reproducibility, "always", "reproductibilité vide → always");
  assert(!("bug_steps" in M.buildTicketBody({ title: "f", project: "a/b", type: "feature", bug_steps: "ignoré" }).body), "les champs bug ne partent que pour un bugfix");
  console.log("✓ formulaire (RM2672) et bugfix (RM2752) : champs, défauts, corps validé ici");
  // — contrôleur : ouvrir (cède la place, note l'onglet), client → radios seules, type → bloc bug, créer → fiche —
  const el = fakeElement(); const ev = []; const sent = [];
  const svc = new NewTicketService({ async create(body) { sent.push(body); return { rm_id: 4242 }; } });
  const center = { yield: (k) => ev.push(["yield", k]), note: (...a) => ev.push(["note", ...a]), title: () => ev.push("title"), closeTab: (id) => ev.push(["closeTab", id]), fallback: () => ev.push("fallback") };
  const nt = mountNewTicket(el, { service: svc, center, notify: (m, e) => ev.push(["toast", m, !!e]), openReview: (rm) => ev.push(["review", rm]), show: (on) => ev.push(["show", on]),
    config: () => ({ types: [{ value: "feature", label: "feature" }, { value: "bugfix", label: "bugfix" }], priorities: ["normal"] }), projects: () => PROJ, defaultTarget: () => ({ client: "acme", project: "infra" }) });
  nt.open(); assert.deepStrictEqual(ev.slice(0, 3), [["yield", "newticket"], ["show", true], ["note", "newticket", "", "nouveau ticket"]]); assert(/value="acme\/infra" checked/.test(el.innerHTML));
  await el.fire("change", "[data-field]", { dataset: { field: "client" }, value: "iprospective" }); assert(/pm-ai-agents/.test(el.nodes.projects.innerHTML) && /value="acme\/infra" checked/.test(el.innerHTML), "seules les radios sont re-rendues, la saisie reste");
  await el.fire("change", "[data-field]", { dataset: { field: "type" }, value: "bugfix" }); assert.strictEqual(el.nodes.bugbox.style.display, ""); await el.fire("change", "[data-field]", { dataset: { field: "type" }, value: "feature" }); assert.strictEqual(el.nodes.bugbox.style.display, "none");
  el.nodes.fields = { t: { dataset: { field: "title" }, value: "" } }; const btn = { dataset: { action: "submit" }, disabled: false, textContent: "" };
  await el.fire("click", "[data-action]", btn); assert.deepStrictEqual(ev.pop(), ["toast", "Titre requis", true]); assert.strictEqual(sent.length, 0);
  el.nodes.fields = { t: { dataset: { field: "title" }, value: "Nouveau" }, ty: { dataset: { field: "type" }, value: "feature" }, p: { dataset: { field: "priority" }, value: "normal" } }; el.nodes.radio = { value: "acme/infra" };
  await el.fire("click", "[data-action]", btn); assert.strictEqual(sent[0].project, "acme/infra"); assert.deepStrictEqual(ev.slice(-3), [["toast", "Ticket RM4242 créé", false], ["closeTab", "newticket:"], ["review", "4242"]], "créé → onglet fermé → fiche ouverte");
  nt.close(); assert.deepStrictEqual(ev.slice(-2), [["show", false], "fallback"]);
  nt.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur nouveau ticket : cède la place, radios seules re-rendues, bloc bug, création → fiche");
  console.log("\nTous les tests du nouveau ticket passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
