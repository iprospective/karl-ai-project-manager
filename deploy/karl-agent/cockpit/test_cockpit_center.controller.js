#!/usr/bin/env node
// Tests du cluster centre — CONTRÔLEUR (RM3020, scindé de test_cockpit_center.js) : routage, surfaces, historique, portée capturée au clic,
// panneaux, tableau de bord, restauration sans session.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { esc, fakeElement, RC } = require("./test_cockpit_center.helpers.js");
(async () => {
  const T = await import(path.join(DIR, "src/modules/center/tabs.js"));
  const KS = await import(path.join(DIR, "src/core/store.js")); const mkStore = (name, obj) => { const s = new KS.Store(name, { ttl: 1e9, max: 1000 }); Object.entries(obj || {}).forEach(([k, v]) => s.set(k, v)); return s; };   // RM3005
  const { mountCenter } = await import(path.join(DIR, "src/modules/center/center.controller.js"));

  // — le contrôleur : routage, surfaces, historique, portée capturée, restauration —
  const mem = {}; const store = { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; }, removeItem: k => { delete mem[k]; } };
  const ev2 = []; const hosts = { tabs: fakeElement(), hist: fakeElement(), view: fakeElement(), title: fakeElement() };
  const calls = []; let attachedSid = null, review = null;
  const repo = { async docFile(p) { calls.push(["doc", p]); return "# x"; }, async fsFile(wt, tag, p, ctx) { calls.push(["fsFile", wt, tag, p]); return { name: "a.md", content: "# x", markdown: true }; },
    async fsLs(wt, tag, p) { calls.push(["fsLs", wt, tag, p]); return { entries: [{ name: "s", dir: true }] }; }, async commit(sid, sha) { calls.push(["commit", sid, sha]); if (sha === "dead") throw new Error("erreur 404"); return { commit: { short: sha }, message: "m", stats: { count: 0 }, patch: "" }; },
    async email(k) { return { key: k, subject: "Devis", body: "b" }; }, async client(c) { return { client: c }; }, async conf() { return { content: "a: 1" }; } };
  let histOpen = false; let placeholder = null;
  const ctr = mountCenter(hosts, { repo, storage: store, md: (x) => "<md>" + x + "</md>", resolve: () => mkStore("r"),
    scope: () => ({ filesData: { projects: [{ root: "/w/appli", client: "acme", project: "appli" }] }, attached: attachedSid, projectKey: null }),
    surfaces: { session: { sessions: () => ({ "42": { rm_id: "42" } }), list: async () => [{ rm_id: "77", ghost: true, session_id: "s77" }], open: (sid) => { attachedSid = sid; ev2.push(["attach", sid]); }, relaunch: (s) => ev2.push(["relaunch", s.session_id]), resume: async (rm) => { ev2.push(["resume", rm]); return rm === "888"; }, close: () => { if (attachedSid) { ev2.push(["detach", attachedSid]); attachedSid = null; } } },
      review: { open: (rm) => { review = rm; ev2.push(["review", rm]); }, close: () => { if (review) { ev2.push(["closeReview", review]); review = null; } } },
      project: { open: (k) => ev2.push(["project", k]), close: () => ev2.push(["closeProject"]) }, newticket: { open: () => ev2.push(["newticket"]), close: () => ev2.push(["closeNewTicket"]) } },
    panels: { pm: { label: "commandes pm", load: () => ev2.push(["load", "pm"]), show: (on) => ev2.push(["cp-pm", on]) }, settings: { label: "réglages", load: () => ev2.push(["load", "settings"]), show: (on) => ev2.push(["cp-settings", on]) } },
    panelShow: (on) => ev2.push(["panelpane", on]), viewShow: (on) => ev2.push(["viewpane", on]), placeholder: (on) => { placeholder = on; }, dashboard: () => ev2.push(["dashboard"]),
    nothingElse: () => !attachedSid && !review, histOpen: () => histOpen, histShow: (on) => { histOpen = on; }, navButtons: (b) => ev2.push(["nav", b.back, b.fwd]),
    legacyTitle: () => attachedSid ? "<b>session " + attachedSid + "</b>" : "", afterTitle: () => ev2.push("afterTitle"), notifyAction: (m) => ev2.push(["toastAction", m]), onPinChange: () => ev2.push("pins") });
  assert.deepEqual(ctr.state.tabs.map(t => t.kind), ["dash"], "au montage : l'onglet permanent, rien d'autre");
  ctr.restore(); assert.strictEqual(ctr.state.active, "dash:"); assert(/📊/.test(hosts.tabs.innerHTML) && /tableau de bord/.test(hosts.title.innerHTML), "sans onglet restauré : le tableau de bord, titré");
  // ouvrir une session (par la surface) puis une fiche depuis elle : fermer la fiche ramène à la session
  ctr.note("session", "42", "RM42"); assert.strictEqual(ctr.state.active, "session:42"); assert(!JSON.parse(mem.karlTabs).some(t => t.kind === "session"), "un temporaire n'est pas persisté (le permanent, si)");
  attachedSid = "42"; ctr.title(); assert(/<b>session 42<\/b>/.test(hosts.title.innerHTML) && ev2.includes("afterTitle"), "le titre d'une surface historique est prêté, les effets de bord aussi");
  ctr.note("review", "2744", "RM2744", { pin: true }); assert(ev2.includes("pins")); assert(JSON.parse(mem.karlTabs).some(t => t.kind === "review"), "un épinglé est persisté");
  assert.deepEqual(ctr.state.tabs.map(t => t.kind), ["dash", "session", "review"], "épingler n'évince pas le temporaire (seule une nouvelle vue temporaire le fait)");
  ctr.note("session", "42", "RM42"); ctr.note("review", "2744", "RM2744");
  ctr.closeTab("review:2744"); assert.strictEqual(ctr.state.active, "session:42", "fermer la fiche ramène à la session d'où on venait (historique), pas au voisin de barre");
  assert.deepEqual(ev2.filter(x => x[0] === "attach").length, 1, "…et la réactive par sa surface");
  // activer un onglet de session éteinte relance ; inconnue → on le dit
  ctr.note("session", "77", "RM77", { pin: true }); await ctr.activate("session:77"); assert.deepEqual(ev2.pop(), ["relaunch", "s77"]);
  // RM3265 : ni vivante ni enregistrée — le clic tente la REPRISE du transcript avant de renoncer.
  // C'est le cas d'une session épinglée dont le tmux est mort : RM2819 ne couvrait que les jeux.
  ctr.note("session", "888", "RM888", { pin: true }); await ctr.activate("session:888");
  assert.deepEqual(ev2.pop(), ["resume", "888"], "session éteinte hors jeu : on tente de la reprendre");
  ctr.note("session", "999", "RM999", { pin: true }); await ctr.activate("session:999");
  assert(/introuvable/.test(ev2.pop()[1]), "…et si le transcript n'existe plus, on le dit");
  assert.deepEqual(ev2.pop(), ["resume", "999"], "…après l'avoir tenté, pas à sa place");
  // vue générique : elle fait céder les surfaces, capture la portée, rend, et son échec se dit
  await ctr.openFile("wt", "/w/appli", "docs/a.md", ""); assert.deepEqual(calls.pop(), ["fsFile", "/w/appli", "c:acme/appli;s:42", "docs/a.md"], "la portée est capturée AU clic (session ∪ projet), avant tout detach");
  assert(ev2.some(x => x[0] === "detach"), "la session a cédé la place"); assert.strictEqual(placeholder, false); assert(/<md># x<\/md>/.test(hosts.view.innerHTML)); assert(/📄/.test(hosts.title.innerHTML));
  await ctr.openFile("doc", "", "projects/x/docs/cdc.md"); assert.deepEqual(calls.pop(), ["doc", "projects/x/docs/cdc.md"]); assert.strictEqual(ctr.state.tabs.filter(t => t.kind === "file").length, 1, "un seul temporaire");
  await ctr.openCommit("42", "dead"); assert(/Commit indisponible/.test(hosts.view.innerHTML) && /erreur 404/.test(hosts.view.innerHTML), "source disparue : dit dans l'onglet");
  await hosts.view.click("open-dir", { src: "wt", wt: "/w/appli", path: "docs", tag: "c:acme/appli" }); assert.deepEqual(calls.pop(), ["fsLs", "/w/appli", "c:acme/appli", "docs"], "un dossier reste navigable, la portée voyage");
  // panneaux centraux et tableau de bord
  ctr.openPanel("settings"); assert(ev2.some(x => x[0] === "cp-settings" && x[1] === true) && ev2.some(x => x[0] === "load" && x[1] === "settings")); assert.strictEqual(ctr.state.view, null, "le panneau a fait céder la vue"); assert(ctr.isBusy());
  ctr.openPanel("settings"); assert.strictEqual(ev2.filter(x => x[0] === "load" && x[1] === "settings").length, 1, "chargé une seule fois");
  ctr.openDashboard(); assert.strictEqual(placeholder, true); assert(!ctr.isBusy()); assert(ev2.some(x => x[0] === "dashboard"), "le tableau de bord est rafraîchi"); assert.strictEqual(ctr.state.active, "dash:");
  // historique ←/→ et liste
  ctr.navGo(-1); assert.notStrictEqual(ctr.state.active, "dash:", "← revient à la vue précédente"); ctr.histToggle(); assert(histOpen && /histrow/.test(hosts.hist.innerHTML)); ctr.histToggle(false); assert(!histOpen);
  // fermer le dernier autre onglet : tout cède, le tableau de bord revient
  ctr.state.tabs.filter(t => !t.fixed).map(t => T.tabId(t.kind, t.key)).forEach(id => ctr.closeTab(id));
  assert.deepEqual(ctr.state.tabs.map(t => t.kind), ["dash"]); assert.strictEqual(ctr.state.active, "dash:");
  // restauration au démarrage : jamais une session
  mem.karlTabs = JSON.stringify([{ kind: "session", key: "42", label: "RM42", pinned: true }]); mem.karlTabActive = "session:42";
  const ctr2 = mountCenter({ tabs: fakeElement(), title: fakeElement() }, { storage: store, resolve: () => mkStore("r"), surfaces: { session: { open: () => ev2.push("ATTACH-AU-BOOT") } } });
  ctr2.restore(); assert(!ev2.includes("ATTACH-AU-BOOT"), "une session restaurée n'est PAS rattachée au boot"); assert.strictEqual(ctr2.state.active, "dash:"); assert.deepEqual(ctr2.state.tabs.map(t => t.kind), ["dash", "session"], "…mais son onglet reste sous la main");
  assert.strictEqual(ctr2.pinOf("session", "42").includes("📌"), true); assert(ctr2.hasTab("42", ["session"]) && !ctr2.hasTab("42", ["review"]));
  ctr.unmount(); assert.strictEqual(hosts.tabs.listenerCount + hosts.view.listenerCount, 0);
  console.log("✓ routeur du centre : surfaces, historique, portée capturée, panneaux, restauration sans session");
  console.log("\nTous les tests du centre passent.");
  console.log("\nTous les tests du contrôleur du centre passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
