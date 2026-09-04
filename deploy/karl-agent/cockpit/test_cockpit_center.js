#!/usr/bin/env node
// Tests du cluster CENTRE migré (RM2889) — porte RM2672, RM2744, RM2759, RM2761, RM2768,
// RM2775, RM2776, RM2795, RM2816, RM2819, RM2861 de test_cockpit.js / test_cockpit_runtime.js.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fakeElement() { const L = []; let inner = ""; return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true,
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async click(action, data) { const n = { dataset: { action, ...(data || {}) } }; for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => s === "[data-action]" ? n : null }, preventDefault() {}, stopPropagation() {} }); } }; }
(async () => {
  const T = await import(path.join(DIR, "src/models/center/tabs.js"));
  const H = await import(path.join(DIR, "src/models/center/history.js"));
  const K = await import(path.join(DIR, "src/models/center/viewKey.js"));
  const SC = await import(path.join(DIR, "src/models/files/scope.js"));
  const VM = await import(path.join(DIR, "src/viewmodels/center/CenterViewModels.js"));
  const V = await import(path.join(DIR, "src/views/center/Center.view.js"));
  const { mountCenter } = await import(path.join(DIR, "src/controllers/center.controller.js"));

  // — RM2672 : temporaire unique, épinglage, fermeture —
  let st = T.upsertTab([], "session", "2668", "RM2668");
  assert.equal(st.tabs.length, 1); assert.equal(st.active, "session:2668"); assert.equal(st.tabs[0].pinned, false);
  st = T.upsertTab(st.tabs, "review", "2670", "RM2670"); assert.deepEqual(st.tabs.map(t => t.kind), ["review"], "le temporaire précédent cède la place");
  st = T.upsertTab(st.tabs, "review", "2670", "RM2670", { pin: true }); st = T.upsertTab(st.tabs, "project", "calyclay/infra", "calyclay/infra");
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
  const TABS = [{ kind: "dash", key: "", pinned: true, fixed: true }, { kind: "review", key: "2744", pinned: true }, { kind: "session", key: "2673", pinned: false }, { kind: "project", key: "calicote/infra", pinned: true }];
  assert(T.pinMark(TABS, "review", "2744").includes("📌") && T.pinMark(TABS, "project", "calicote/infra").includes("📌"));
  assert.strictEqual(T.pinMark(TABS, "session", "2673"), ""); assert.strictEqual(T.pinMark(TABS, "review", "9999"), ""); assert.strictEqual(T.pinMark(TABS, "session", "2744"), "");
  assert.strictEqual(T.pinMark(TABS, "dash", ""), "", "l'onglet permanent n'est pas une épingle qu'on choisit"); assert.strictEqual(T.pinMark(null, "review", "1"), "");
  assert.strictEqual(T.pinMark(TABS, "review", 2744), T.pinMark(TABS, "review", "2744")); assert(/title="Épinglé dans les onglets/.test(T.pinMark(TABS, "review", "2744")));
  // — RM2819 : session éteinte —
  const S = [{ rm_id: "100", state: "working" }, { rm_id: "200", ghost: true, engine: "claude", session_id: "abc", resumable: true }, { rm_id: "300", ghost: true }, { rm_id: "300", state: "idle" }];
  assert.strictEqual(T.sessionTabAction("100", S).action, "attach"); assert.strictEqual(T.sessionTabAction("200", S).session.session_id, "abc"); assert.strictEqual(T.sessionTabAction("300", S).action, "attach");
  assert.strictEqual(T.sessionTabAction("999", S).action, "missing"); assert.strictEqual(T.sessionTabAction("200", { "200": { rm_id: "200", ghost: true } }).action, "relaunch"); assert.strictEqual(T.sessionTabAction(200, { "200": { rm_id: "200", ghost: true } }).action, "relaunch");
  console.log("✓ onglets (RM2672/2744/2795/2819) : temporaire unique, permanent, marque, session éteinte");

  // — RM2775 : infobulle —
  const RC = { "2744": { found: true, title: "Tableau de bord : contenu coupé en haut" }, "2673": { found: true, title: "Améliorations ergonomiques PM" }, "9999": { found: false } };
  const tt = (t) => T.tabTooltip(t, RC, K.parseViewKey);
  assert(tt({ kind: "review", key: "2744", label: "RM2744" }).startsWith("RM2744 — Tableau de bord")); assert.strictEqual(tt({ kind: "review", key: "9999", label: "RM9999" }), "RM9999");
  assert.strictEqual(T.tabTooltip({ kind: "review", key: "2744" }, {}, K.parseViewKey), "RM2744"); assert(tt({ kind: "session", key: "2673" }).includes("Améliorations")); assert.strictEqual(tt({ kind: "session", key: "calymix" }), "session calymix");
  assert(tt({ kind: "file", key: K.viewKey(["wt", "/w/repo", "src/api/handlers.py"]) }).includes("src/api/handlers.py")); assert(tt({ kind: "dir", key: K.viewKey(["wt", "/w/repo", ""]) }).includes("racine"));
  const tc = tt({ kind: "commit", key: K.viewKey(["2749", "abcdef1234567890"]) }); assert(tc.includes("abcdef1234567890") && tc.includes("2749"));
  assert(tt({ kind: "conf", key: K.viewKey(["project", "calicote", "presta"]) }).includes("calicote/presta")); assert(tt({ kind: "client", key: K.viewKey(["calicote"]) }).includes("calicote"));
  assert.strictEqual(tt({ kind: "dash", key: "" }), "tableau de bord"); assert.strictEqual(tt({ kind: "pm", key: "" }), "commandes PM"); assert.strictEqual(tt({ kind: "settings", key: "" }), "réglages du cockpit"); assert.strictEqual(tt({}), "");
  const tabsHtml = String(V.Tabs(new VM.TabsViewModel({ tabs: [{ kind: "review", key: "2670", label: "RM2670", pinned: true }, { kind: "project", key: "x/y", label: "<b>x</b>", pinned: false }, { kind: "dash", key: "", label: "tableau de bord", pinned: true, fixed: true }], active: "review:2670" }, { resolve: RC })));
  assert(/class="ctab active"/.test(tabsHtml) && /📌/.test(tabsHtml) && /⇧/.test(tabsHtml) && /ctab temp/.test(tabsHtml) && !/<b>x<\/b>/.test(tabsHtml) && /&lt;b&gt;/.test(tabsHtml));
  assert(/data-action="activate" data-id="review:2670"/.test(tabsHtml) && /data-action="close" data-id="review:2670"/.test(tabsHtml) && !/onclick=/.test(tabsHtml), "gestes en data-action, zéro onclick");
  assert(/📊/.test(tabsHtml) && !/data-action="close" data-id="dash:"/.test(tabsHtml) && !/data-action="pin" data-id="dash:"/.test(tabsHtml) && /toujours là/.test(tabsHtml), "l'onglet permanent : ni croix ni épingle");
  console.log("✓ infobulles et barre d'onglets (RM2775/2744) : titres, icônes, permanent sans croix");

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
  const lh = String(V.History(new VM.HistoryViewModel({ items: [{ id: "session:2673", kind: "session", label: "2673" }, { id: "review:2744", kind: "review", label: "RM2744" }], idx: 1 }, { isOpen: (id) => id !== "session:2673" })));
  assert(lh.indexOf("RM2744") < lh.indexOf("2673")); assert(/data-action="goto" data-id="review:2744"/.test(lh)); assert(!/data-action="goto" data-id="session:2673"/.test(lh)); assert(lh.includes("fermée") && lh.includes("ici"));
  assert(String(V.History(new VM.HistoryViewModel({ items: [], idx: -1 }, {}))).includes("aucune vue visitée"));
  console.log("✓ historique (RM2776) : visite, plafond, retour d'où l'on vient, sauts, liste");

  // — RM2759 : clés, libellés, vues —
  assert.deepEqual(K.parseViewKey(K.viewKey(["wt", "/a/b", "src/x.py"])), ["wt", "/a/b", "src/x.py"]); assert.deepEqual(K.parseViewKey(K.viewKey(["doc", "", "projects/c/p/docs/cdc.md"])), ["doc", "", "projects/c/p/docs/cdc.md"]);
  assert.deepEqual(K.parseViewKey(K.viewKey(["wt", "/w", "un|pipe & espace.txt"])), ["wt", "/w", "un|pipe & espace.txt"]); assert.deepEqual(K.parseViewKey(""), []); assert.deepEqual(K.parseViewKey("%ZZ"), ["%ZZ"]);
  assert.strictEqual(K.viewTabLabel("file", ["wt", "/w", "a/b/cdc.md"]), "cdc.md"); assert.strictEqual(K.viewTabLabel("dir", ["wt", "/w", "src/api"]), "api/"); assert.strictEqual(K.viewTabLabel("dir", ["wt", "/w", ""]), "racine/");
  assert.strictEqual(K.viewTabLabel("commit", ["2759", "abcdef1234567890"]), "abcdef12"); assert.strictEqual(K.viewTabLabel("mail", ["k1"], "Devis pour le site vitrine"), "Devis pour le site vitrine"); assert.strictEqual(K.viewTabLabel("mail", ["k1"], "x".repeat(40)).length, 30);
  const md = (x) => "<MD>" + x + "</MD>";
  const fvMd = String(V.FileView(new VM.FileViewModel({ path: "docs/cdc.md", markdown: true, size: 2048, content: "# Titre" }, { md }))); assert(fvMd.includes("<MD># Titre</MD>") && fvMd.includes("2 Ko"));
  const fvTxt = String(V.FileView(new VM.FileViewModel({ path: "a.py", markdown: false, content: "<script>x</script>" }, { md }))); assert(!fvTxt.includes("<script>") && fvTxt.includes("&lt;script&gt;"));
  // RM2861 : le corps, un seul rendu, pleine hauteur, jamais `.desc`
  const vMd = String(V.FileBody(new VM.FileViewModel({ markdown: true, content: "# titre" }, { md: (t) => "<md>" + t + "</md>" })));
  assert(/facetfull/.test(vMd) && /descfull/.test(vMd) && /mdview/.test(vMd) && !/class="[^"]*\bdesc\b/.test(vMd) && /<md># titre<\/md>/.test(vMd));
  const vTxt = String(V.FileBody(new VM.FileViewModel({ markdown: false, content: "a < b & c" }, { md }))); assert(/max-height:none/.test(vTxt) && /a &lt; b &amp; c/.test(vTxt) && !/<md>/.test(vTxt));
  assert(String(V.FileBody(new VM.FileViewModel(null, { md }))) !== "" && !/undefined/.test(String(V.FileBody(new VM.FileViewModel({ markdown: false }, { md })))));
  const dv = String(V.DirView(new VM.DirViewModel({ src: "wt", wt: "/w/repo", path: "src", rootName: "repo", entries: [{ name: "api", dir: true }, { name: "main.py", dir: false, size: 512 }] })));
  assert(/data-action="open-dir" data-src="wt" data-wt="\/w\/repo" data-path="src\/api" data-tag=""/.test(dv) && /data-action="open-file"[^>]*data-path="src\/main.py"/.test(dv) && dv.includes("repo") && /data-action="open-dir"[^>]*data-path=""/.test(dv) && !/onclick=/.test(dv));
  assert(String(V.DirView(new VM.DirViewModel({ entries: [] }))).includes("dossier vide"));
  const mv = String(V.MailView(new VM.EmailViewModel({ subject: "Devis", from: "a@b.fr", from_name: "Alice", date: "2026-08-20", body: "Bonjour\nà tous", body_truncated: true, state: "à traiter" })));
  assert(mv.includes("Bonjour") && mv.includes("tronqué à la relève") && mv.includes("Alice") && mv.includes("a@b.fr")); assert(String(V.MailView(new VM.EmailViewModel({ subject: "x" }))).includes("corps non disponible")); assert(String(V.MailView(new VM.EmailViewModel({}))).includes("(sans sujet)"));
  const ev = String(V.ViewError("Commit indisponible", "erreur 404")); assert(ev.includes("Commit indisponible") && ev.includes("erreur 404") && ev.includes("session fermée"));
  console.log("✓ vues centrales (RM2759/2861) : clés, libellés, fichier, dossier navigable, email, erreur");

  // — RM2761 : la portée —
  const FD = { projects: [{ root: "/ws/ipro/pm", client: "ipro", project: "pm" }] };
  let sc = SC.fsScope("/ws/ipro/pm/envs/pm-rm42", FD, "karl-RM42", null); assert.equal(sc.client, "ipro"); assert.equal(sc.project, "pm"); assert.equal(sc.sid, "karl-RM42");
  assert.deepEqual(SC.fsScope("/ailleurs/scratch", FD, "karl-RM42", null), { sid: "karl-RM42" }); assert.deepEqual(SC.fsScope("/x", { client: "acme", project: "shop" }, null, null), { client: "acme", project: "shop" });
  assert.deepEqual(SC.fsScope("/x", {}, null, "acme/shop"), { client: "acme", project: "shop" }); assert.deepEqual(SC.fsScope("/x", {}, null, null), {});
  assert.equal(SC.scopeTag({ client: "ipro", project: "pm", sid: "karl-RM42" }), "c:ipro/pm;s:karl-RM42"); assert.deepEqual(SC.scopeFromTag("c:ipro/pm;s:karl-RM42"), { client: "ipro", project: "pm", sid: "karl-RM42" });
  assert.deepEqual(SC.scopeFromTag("s:karl-RM42"), { sid: "karl-RM42" }); assert.equal(SC.scopeFromTag(""), null); assert.equal(SC.scopeFromTag("c:incomplet"), null); assert.equal(SC.scopeQuery({ client: "ipro", project: "pm", sid: "" }), "client=ipro&project=pm&sid=");
  const tag = SC.scopeTag({ client: "ipro", project: "pm", sid: "karl-RM42" }); assert.deepEqual(K.parseViewKey(K.viewKey(["wt", "/ws/ipro/pm/envs/pm-rm42", "docs/a.md", tag])), ["wt", "/ws/ipro/pm/envs/pm-rm42", "docs/a.md", tag]);
  const dh = String(V.DirView(new VM.DirViewModel({ src: "wt", wt: "/ws/ipro/pm", path: "docs", rootName: "pm", tag, entries: [{ name: "sous", dir: true }, { name: "a.md", size: 10 }] })));
  assert((dh.match(/c:ipro\/pm;s:karl-RM42/g) || []).length >= 3, "fil d'ariane, sous-dossiers et fichiers portent la portée");
  assert.equal(SC.fsQuery("/w", "c:acme&x/appli;s:1", {}), "client=acme%26x&project=appli&sid=1&worktree=%2Fw"); assert.equal(SC.fsQuery("/w", "", { filesData: { client: "a", project: "b" }, attached: null }), "client=a&project=b&worktree=%2Fw"); assert.equal(SC.fsQuery("/w", "", { attached: "42" }), "sid=42&worktree=%2Fw");
  console.log("✓ portée (RM2761) : union session ∪ projet, étiquette aller-retour, requête");

  // — RM2768 : fiche client et conf —
  const CLI = { client: "calicote", name: "Calicote", status: "active", type: "client", created: "2026-05-19", redmine_project_id: "calicote", redmine_project_url: "https://r.test/projects/calicote",
    contacts: [{ first_name: "Sandrine", last_name: "Roche", email: "s@calicote.test", role: "owner", title: "Gérante" }, { name: "Mathieu", email: "m@ipro.test", role: "owner", internal: true }],
    defaults: { priority: "normal", team: [{ username: "iprospective" }] }, projects: [{ project: "prestashop", value: "calicote/prestashop" }], projects_used: ["iprospective/nc-clients"], docs: [{ name: "overview.md", path: "projects/clients/calicote/client/overview.md" }] };
  const cv = String(V.ClientView(new VM.ClientViewModel(CLI)));
  assert(cv.includes("Calicote") && cv.includes("calicote") && cv.includes("Sandrine Roche") && cv.includes("Gérante") && cv.includes("interne"));
  assert(/data-action="open-project" data-value="calicote\/prestashop"/.test(cv) && cv.includes("Projets utilisés") && cv.includes("iprospective/nc-clients"));
  assert(/data-action="open-file" data-src="doc" data-wt="" data-path="projects\/clients\/calicote\/client\/overview\.md"/.test(cv) && cv.includes('href="https://r.test/projects/calicote"') && !/onclick=/.test(cv));
  const cvMin = String(V.ClientView(new VM.ClientViewModel({ client: "x" }))); assert(cvMin.includes("aucun projet") && !cvMin.includes("Contacts")); assert(String(V.ClientView(new VM.ClientViewModel(null))).includes("client"));
  const cf = String(V.ConfView({ label: "calicote/prestashop", name: "meta.yml", content: "slug: x\nrepos:\n  - <b>a</b>\n" }));
  assert(cf.includes("calicote/prestashop") && cf.includes("meta.yml") && cf.includes("&lt;b&gt;a&lt;/b&gt;") && cf.includes("slug: x") && cf.includes("mmi-pm")); assert(String(V.ConfView({})).includes("meta.yml"));
  console.log("✓ fiche client et conf (RM2768) : contacts, partage, docs au centre, conf telle quelle");

  // — le contrôleur : routage, surfaces, historique, portée capturée, restauration —
  const mem = {}; const store = { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; }, removeItem: k => { delete mem[k]; } };
  const ev2 = []; const hosts = { tabs: fakeElement(), hist: fakeElement(), view: fakeElement(), title: fakeElement() };
  const calls = []; let attachedSid = null, review = null;
  const repo = { async docFile(p) { calls.push(["doc", p]); return "# x"; }, async fsFile(wt, tag, p, ctx) { calls.push(["fsFile", wt, tag, p]); return { name: "a.md", content: "# x", markdown: true }; },
    async fsLs(wt, tag, p) { calls.push(["fsLs", wt, tag, p]); return { entries: [{ name: "s", dir: true }] }; }, async commit(sid, sha) { calls.push(["commit", sid, sha]); if (sha === "dead") throw new Error("erreur 404"); return { commit: { short: sha }, message: "m", stats: { count: 0 }, patch: "" }; },
    async email(k) { return { key: k, subject: "Devis", body: "b" }; }, async client(c) { return { client: c }; }, async conf() { return { content: "a: 1" }; } };
  let histOpen = false; let placeholder = null;
  const ctr = mountCenter(hosts, { repo, storage: store, md: (x) => "<md>" + x + "</md>", resolve: () => ({}),
    scope: () => ({ filesData: { projects: [{ root: "/w/appli", client: "acme", project: "appli" }] }, attached: attachedSid, projectKey: null }),
    surfaces: { session: { sessions: () => ({ "42": { rm_id: "42" } }), list: async () => [{ rm_id: "77", ghost: true, session_id: "s77" }], open: (sid) => { attachedSid = sid; ev2.push(["attach", sid]); }, relaunch: (s) => ev2.push(["relaunch", s.session_id]), close: () => { if (attachedSid) { ev2.push(["detach", attachedSid]); attachedSid = null; } } },
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
  ctr.note("session", "999", "RM999", { pin: true }); await ctr.activate("session:999"); assert(/introuvable/.test(ev2.pop()[1]));
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
  const ctr2 = mountCenter({ tabs: fakeElement(), title: fakeElement() }, { storage: store, surfaces: { session: { open: () => ev2.push("ATTACH-AU-BOOT") } } });
  ctr2.restore(); assert(!ev2.includes("ATTACH-AU-BOOT"), "une session restaurée n'est PAS rattachée au boot"); assert.strictEqual(ctr2.state.active, "dash:"); assert.deepEqual(ctr2.state.tabs.map(t => t.kind), ["dash", "session"], "…mais son onglet reste sous la main");
  assert.strictEqual(ctr2.pinOf("session", "42").includes("📌"), true); assert(ctr2.hasTab("42", ["session"]) && !ctr2.hasTab("42", ["review"]));
  ctr.unmount(); assert.strictEqual(hosts.tabs.listenerCount + hosts.view.listenerCount, 0);
  console.log("✓ routeur du centre : surfaces, historique, portée capturée, panneaux, restauration sans session");
  console.log("\nTous les tests du centre passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
