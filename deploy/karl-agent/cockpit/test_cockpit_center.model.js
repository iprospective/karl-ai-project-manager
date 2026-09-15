#!/usr/bin/env node
// Tests du cluster centre — MODÈLE (RM3020, scindé de test_cockpit_center.js) : onglets (RM2672/2744/2795/2819), infobulles RM2775 (registre
// des types), historique RM2776, clés et libellés RM2759, portée RM2761.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { esc, fakeElement, RC } = require("./test_cockpit_center.helpers.js");
(async () => {
  const T = await import(path.join(DIR, "src/modules/center/tabs.js"));
  const H = await import(path.join(DIR, "src/modules/center/history.js"));
  const K = await import(path.join(DIR, "src/modules/center/viewKey.js"));
  const SC = await import(path.join(DIR, "src/modules/files/scope.js"));

  // — RM2672 : temporaire unique, épinglage, fermeture —
  let st = T.upsertTab([], "session", "2668", "RM2668");
  assert.equal(st.tabs.length, 1); assert.equal(st.active, "session:2668"); assert.equal(st.tabs[0].pinned, false);
  st = T.upsertTab(st.tabs, "review", "2670", "RM2670"); assert.deepEqual(st.tabs.map(t => t.kind), ["review"], "le temporaire précédent cède la place");
  st = T.upsertTab(st.tabs, "review", "2670", "RM2670", { pin: true }); st = T.upsertTab(st.tabs, "project", "clientb/infra", "clientb/infra");
  assert.deepEqual(st.tabs.map(t => t.kind), ["review", "project"]); st = T.upsertTab(st.tabs, "newticket", "", "nouveau ticket"); assert.deepEqual(st.tabs.map(t => t.kind), ["review", "newticket"]);
  const before = st.tabs.length; st = T.upsertTab(st.tabs, "review", "2670", "RM2670"); assert.equal(st.tabs.length, before); assert.equal(st.active, "review:2670");
  let c = T.closeTabAt(st.tabs, "review:2670", "review:2670"); assert.equal(c.active, "newticket:"); c = T.closeTabAt(c.tabs, "newticket:", "newticket:"); assert.equal(c.tabs.length, 0); assert.equal(c.active, null);
  assert.equal(T.closeTabAt([{ kind: "review", key: "1" }], "review:404", "review:1").tabs.length, 1);
  // — RM2744 : l'onglet permanent —
  let d = T.ensureDashTab([]); assert.equal(d.length, 1); assert.equal(d[0].kind, "dash"); assert(d[0].pinned && d[0].fixed);
  d = T.ensureDashTab([{ kind: "review", key: "2744", label: "RM2744", pinned: true }, { kind: "dash", key: "", label: "vieux libellé", pinned: true, fixed: true }]);
  assert.equal(d.length, 2); assert.equal(d[0].kind, "dash"); assert.equal(d[0].label, "tableau de bord"); assert.equal(d[1].kind, "review");
  const withDash = T.ensureDashTab([{ kind: "review", key: "2744", label: "RM2744", pinned: true }]);
  assert.equal(T.closeTabAt(withDash, "dash:", "dash:").tabs.length, 2, "fermer l'onglet permanent ne ferme rien");
  const after = T.closeTabAt(withDash, "review:2744", "review:2744"); assert.deepEqual(after.tabs.map(t => t.kind), ["dash"]); assert.equal(after.active, "dash:");
  // — RM2795 : la marque —
  const TABS = [{ kind: "dash", key: "", pinned: true, fixed: true }, { kind: "review", key: "2744", pinned: true }, { kind: "session", key: "2673", pinned: false }, { kind: "project", key: "clienta/infra", pinned: true }];
  assert(T.pinMark(TABS, "review", "2744").includes("📌") && T.pinMark(TABS, "project", "clienta/infra").includes("📌"));
  assert.strictEqual(T.pinMark(TABS, "session", "2673"), ""); assert.strictEqual(T.pinMark(TABS, "review", "9999"), ""); assert.strictEqual(T.pinMark(TABS, "session", "2744"), "");
  assert.strictEqual(T.pinMark(TABS, "dash", ""), "", "l'onglet permanent n'est pas une épingle qu'on choisit"); assert.strictEqual(T.pinMark(null, "review", "1"), "");
  assert.strictEqual(T.pinMark(TABS, "review", 2744), T.pinMark(TABS, "review", "2744")); assert(/title="Épinglé dans les onglets/.test(T.pinMark(TABS, "review", "2744")));
  // — RM2819 : session éteinte —
  const S = [{ rm_id: "100", state: "working" }, { rm_id: "200", ghost: true, engine: "claude", session_id: "abc", resumable: true }, { rm_id: "300", ghost: true }, { rm_id: "300", state: "idle" }];
  assert.strictEqual(T.sessionTabAction("100", S).action, "attach"); assert.strictEqual(T.sessionTabAction("200", S).session.session_id, "abc"); assert.strictEqual(T.sessionTabAction("300", S).action, "attach");
  assert.strictEqual(T.sessionTabAction("999", S).action, "missing"); assert.strictEqual(T.sessionTabAction("200", { "200": { rm_id: "200", ghost: true } }).action, "relaunch"); assert.strictEqual(T.sessionTabAction(200, { "200": { rm_id: "200", ghost: true } }).action, "relaunch");
  console.log("✓ onglets (RM2672/2744/2795/2819) : temporaire unique, permanent, marque, session éteinte");


  // — RM2775 : infobulle —
  const tt = (t) => T.tabTooltip(t, RC, K.parseViewKey);
  assert(tt({ kind: "review", key: "2744", label: "RM2744" }).startsWith("RM2744 — Tableau de bord")); assert.strictEqual(tt({ kind: "review", key: "9999", label: "RM9999" }), "RM9999");
  assert.strictEqual(T.tabTooltip({ kind: "review", key: "2744" }, {}, K.parseViewKey), "RM2744"); assert(tt({ kind: "session", key: "2673" }).includes("Améliorations")); assert.strictEqual(tt({ kind: "session", key: "calymix" }), "session calymix");
  assert(tt({ kind: "file", key: K.viewKey(["wt", "/w/repo", "src/api/handlers.py"]) }).includes("src/api/handlers.py")); assert(tt({ kind: "dir", key: K.viewKey(["wt", "/w/repo", ""]) }).includes("racine"));
  const tc = tt({ kind: "commit", key: K.viewKey(["2749", "abcdef1234567890"]) }); assert(tc.includes("abcdef1234567890") && tc.includes("2749"));
  assert(tt({ kind: "conf", key: K.viewKey(["project", "clienta", "presta"]) }).includes("clienta/presta")); assert(tt({ kind: "client", key: K.viewKey(["clienta"]) }).includes("clienta"));
  assert.strictEqual(tt({ kind: "dash", key: "" }), "tableau de bord"); assert.strictEqual(tt({ kind: "pm", key: "" }), "commandes PM"); assert.strictEqual(tt({ kind: "settings", key: "" }), "réglages du cockpit"); assert.strictEqual(tt({}), "");
  console.log("✓ infobulles (RM2775) : titres résolus, chemins, panneaux");

  // — RM2776 : historique —
  let h = { items: [], idx: -1 }; h = H.histVisit(h, { id: "session:2673", kind: "session", label: "2673" }, 40); h = H.histVisit(h, { id: "review:2744", kind: "review", label: "RM2744" }, 40);
  assert.deepEqual(h.items.map(e => e.id), ["session:2673", "review:2744"]); assert.strictEqual(h.idx, 1);
  const h2 = H.histVisit(h, { id: "review:2744", kind: "review", label: "RM2744 (bis)" }, 40); assert.strictEqual(h2.items.length, 2); assert.strictEqual(h2.items[1].label, "RM2744 (bis)");
  assert.strictEqual(H.histVisit(h, {}, 40).items.length, 2); assert.deepEqual(H.histVisit(null, { id: "a:1" }, 40).items.map(e => e.id), ["a:1"]);
  let plein = { items: [], idx: -1 }; for (let i = 0; i < 10; i++) plein = H.histVisit(plein, { id: "review:" + i }, 4);
  assert.deepEqual(plein.items.map(e => e.id), ["review:6", "review:7", "review:8", "review:9"]); assert.strictEqual(plein.idx, 3);
  const ouvertes = new Set(["session:2673", "review:2744", "dash:"]); const isOpen = (id) => ouvertes.has(id);
  assert.strictEqual(H.histCloseTarget(h, "review:2744", isOpen), "session:2673", "fermer la fiche ramène à la session d'où on venait");
  const h3 = H.histVisit(h, { id: "dash:", kind: "dash", label: "tableau de bord" }, 40); assert.strictEqual(H.histCloseTarget(h3, "dash:", (id) => id === "dash:"), null);
  assert.strictEqual(H.histCloseTarget({ items: [], idx: -1 }, "x:1", isOpen), null); assert.strictEqual(H.histCloseTarget(h, "review:2744", null), "session:2673");
  const parcours = { items: [{ id: "a:1" }, { id: "b:2" }, { id: "c:3" }], idx: 2 };
  assert.strictEqual(H.histStep(parcours, -1, () => true).entry.id, "b:2"); assert.strictEqual(H.histStep(parcours, -1, (id) => id !== "b:2").entry.id, "a:1"); assert.strictEqual(H.histStep(parcours, 1, () => true).entry, null);
  assert.strictEqual(H.histStep({ items: [{ id: "a:1" }], idx: 0 }, -1, () => true).entry, null); assert.strictEqual(H.histStep(parcours, -1, () => false).entry, null); assert.strictEqual(H.histStep({ ...parcours, idx: 0 }, 1, () => true).entry.id, "b:2");
  console.log("✓ historique (RM2776) : visite, plafond, retour d'où l'on vient, sauts");

  // — RM2759 : clés, libellés, vues —
  assert.deepEqual(K.parseViewKey(K.viewKey(["wt", "/a/b", "src/x.py"])), ["wt", "/a/b", "src/x.py"]); assert.deepEqual(K.parseViewKey(K.viewKey(["doc", "", "projects/c/p/docs/cdc.md"])), ["doc", "", "projects/c/p/docs/cdc.md"]);
  assert.deepEqual(K.parseViewKey(K.viewKey(["wt", "/w", "un|pipe & espace.txt"])), ["wt", "/w", "un|pipe & espace.txt"]); assert.deepEqual(K.parseViewKey(""), []); assert.deepEqual(K.parseViewKey("%ZZ"), ["%ZZ"]);
  assert.strictEqual(K.viewTabLabel("file", ["wt", "/w", "a/b/cdc.md"]), "cdc.md"); assert.strictEqual(K.viewTabLabel("dir", ["wt", "/w", "src/api"]), "api/"); assert.strictEqual(K.viewTabLabel("dir", ["wt", "/w", ""]), "racine/");
  assert.strictEqual(K.viewTabLabel("commit", ["2759", "abcdef1234567890"]), "abcdef12"); assert.strictEqual(K.viewTabLabel("mail", ["k1"], "Devis pour le site vitrine"), "Devis pour le site vitrine"); assert.strictEqual(K.viewTabLabel("mail", ["k1"], "x".repeat(40)).length, 30);
  console.log("✓ clés et libellés (RM2759)");

  // — RM2761 : la portée —
  const FD = { projects: [{ root: "/ws/ipro/pm", client: "ipro", project: "pm" }] };
  let sc = SC.fsScope("/ws/ipro/pm/envs/pm-rm42", FD, "karl-RM42", null); assert.equal(sc.client, "ipro"); assert.equal(sc.project, "pm"); assert.equal(sc.sid, "karl-RM42");
  assert.deepEqual(SC.fsScope("/ailleurs/scratch", FD, "karl-RM42", null), { sid: "karl-RM42" }); assert.deepEqual(SC.fsScope("/x", { client: "acme", project: "shop" }, null, null), { client: "acme", project: "shop" });
  assert.deepEqual(SC.fsScope("/x", {}, null, "acme/shop"), { client: "acme", project: "shop" }); assert.deepEqual(SC.fsScope("/x", {}, null, null), {});
  assert.equal(SC.scopeTag({ client: "ipro", project: "pm", sid: "karl-RM42" }), "c:ipro/pm;s:karl-RM42"); assert.deepEqual(SC.scopeFromTag("c:ipro/pm;s:karl-RM42"), { client: "ipro", project: "pm", sid: "karl-RM42" });
  assert.deepEqual(SC.scopeFromTag("s:karl-RM42"), { sid: "karl-RM42" }); assert.equal(SC.scopeFromTag(""), null); assert.equal(SC.scopeFromTag("c:incomplet"), null); assert.equal(SC.scopeQuery({ client: "ipro", project: "pm", sid: "" }), "client=ipro&project=pm&sid=");
  const tag = SC.scopeTag({ client: "ipro", project: "pm", sid: "karl-RM42" }); assert.deepEqual(K.parseViewKey(K.viewKey(["wt", "/ws/ipro/pm/envs/pm-rm42", "docs/a.md", tag])), ["wt", "/ws/ipro/pm/envs/pm-rm42", "docs/a.md", tag]);
  assert.equal(SC.fsQuery("/w", "c:acme&x/appli;s:1", {}), "client=acme%26x&project=appli&sid=1&worktree=%2Fw"); assert.equal(SC.fsQuery("/w", "", { filesData: { client: "a", project: "b" }, attached: null }), "client=a&project=b&worktree=%2Fw"); assert.equal(SC.fsQuery("/w", "", { attached: "42" }), "sid=42&worktree=%2Fw");
  console.log("✓ portée (RM2761) : union session ∪ projet, étiquette aller-retour, requête");
  console.log("\nTous les tests du modèle du centre passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
