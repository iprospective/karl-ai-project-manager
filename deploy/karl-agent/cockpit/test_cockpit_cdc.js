#!/usr/bin/env node
// Tests des pages du CDC vivant (RM3044) : choix du CDC en contexte, table des fonctionnalités (tri, filtre, comptes), feuille de route
// (par jalon / par état), chapitres (ancres D/Q, liens relatifs, RM cliquables), vues sans on*, contrôleur avec service factice.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));
function fakeEl(id) { const L = []; let inner = ""; const self = { id, style: {}, textContent: "", kids: {}, get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, querySelector(s) { return self.kids[s] || null; }, querySelectorAll() { return []; }, contains() { return true; }, appendChild() {}, replaceChildren(...n) { inner = n.map(x => x.outerHTML || x.textContent || "").join(""); }, addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n, getAttribute: (k) => (data || {})[k], value: "" }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await settle(); },
  async input(value) { const n = { dataset: { action: "q" }, closest: () => n, value }; for (const [t, f] of [...L]) if (t === "input") await f({ target: n, preventDefault() {} }); await settle(); },
  async link(href) { const n = { getAttribute: () => href, closest: (s) => s === "a[href]" ? n : null, dataset: {} }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await settle(); } }; return self; }
(async () => {
  const S = await import(path.join(DIR, "src/modules/cdc/cdc.service.js"));
  const VM = await import(path.join(DIR, "src/modules/cdc/CdcViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/cdc/Cdc.view.js"));
  const { mountCdc } = await import(path.join(DIR, "src/modules/cdc/cdc.controller.js"));
  const { mdToHtml } = await import(path.join(DIR, "src/core/markdown.js"));
  const cdcs = [
    { key: "i/pm/pm", client: "i", project: "pm", prefix: "pm", title: "CDC PM", path: "projects/clients/i/projects/pm/docs/cdc-pm-00-sommaire.md", registry: true, chapters: [{ file: "cdc-pm-00-sommaire.md", path: "projects/clients/i/projects/pm/docs/cdc-pm-00-sommaire.md", title: "CDC PM" }, { file: "cdc-pm-90-decisions.md", path: "projects/clients/i/projects/pm/docs/cdc-pm-90-decisions.md", title: "90 — Décisions" }] },
    { key: "a/site/site", client: "a", project: "site", prefix: "site", title: "CDC Site", path: "projects/clients/a/projects/site/docs/cdc-site-00-sommaire.md", registry: false, chapters: [] },
  ];
  // — pickCdc —
  assert.strictEqual(S.pickCdc([], "", []), null); assert.strictEqual(S.pickCdc(cdcs, "a/site/site", []).key, "a/site/site", "la préférence mémorisée gagne");
  assert.strictEqual(S.pickCdc(cdcs, "zz", ["a/site"]).key, "a/site/site", "préférence périmée → projet de la session"); assert.strictEqual(S.pickCdc(cdcs, "", []).key, "i/pm/pm", "sinon le premier");
  // — FeaturesViewModel —
  const data = { entrees: [
    { id: "F001", rm: 10, libelle: "Onglet journal", domaine: "Cockpit", type: "feature", etat: "livré", date: "2026-08-01" },
    { id: "F002", rm: 11, libelle: "Bug porcelain", domaine: "Outillage", type: "bugfix", etat: "livré", date: "2026-08-02" },
    { id: "F003", rm: 12, libelle: "Truc en cours", domaine: "Cockpit", type: "feature", etat: "en cours", date: "2026-09-01", parent: 5 },
    { id: "F004", libelle: "Capacité curée", domaine: "Karl", type: "feature", etat: "prévu", date: "2026-09-02", tickets: [20, 21], manuel: true },
    { id: "F005", rm: 13, libelle: "Abandonné", domaine: "Cockpit", type: "feature", etat: "écarté (abandonne)", date: "2026-07-01" },
  ], domaines: ["Cockpit", "Outillage", "Karl"], jalons: [] };
  let f = new VM.FeaturesViewModel({ data, sort: "id" });
  assert.deepStrictEqual(f.rows().map(r => r.id), ["F001", "F002", "F003", "F004", "F005"]); assert(!f.hasJalon && f.cols.every(c => c.key !== "jalon"), "pas de colonne jalon sans jalon");
  assert.deepStrictEqual(f.counts.map(c => c.etat + ":" + c.n), ["livré:2", "en cours:1", "prévu:1", "écarté:1"], "comptes par état, écarté regroupé");
  assert.deepStrictEqual(f.rows()[3].tickets, [20, 21], "tickets multiples d'une entrée curée"); assert.strictEqual(f.rows()[2].parent, 5);
  f = new VM.FeaturesViewModel({ data, sort: "etat", desc: true }); assert.strictEqual(f.rows()[0].id, "F005", "tri par état inversé : écarté d'abord");
  f = new VM.FeaturesViewModel({ data, sort: "date" }); assert.strictEqual(f.rows()[0].id, "F005", "tri par date");
  f = new VM.FeaturesViewModel({ data, q: "rm21" }); assert.deepStrictEqual(f.rows().map(r => r.id), ["F004"], "filtre sur un RM couvert"); assert.strictEqual(f.count, "1 / 5");
  f = new VM.FeaturesViewModel({ data: { entrees: [{ id: "F001", libelle: "x", etat: "livré", jalon: 1 }], jalons: [{ id: "V1", titre: "pilote" }] } }); assert(f.hasJalon && f.rows()[0].jalon === "V1");
  // — RoadmapViewModel —
  let r = new VM.RoadmapViewModel({ data }); assert(!r.byJalon); let g = r.groups();
  assert.deepStrictEqual(g.map(x => x.label), ["En cours", "Prévu", "Livré récemment"], "sans jalon : par état, livrées récentes en bas, écartés absents");
  assert.strictEqual(g[2].rows[0].id, "F002", "livrées triées par date décroissante");
  r = new VM.RoadmapViewModel({ data: { entrees: [{ id: "F001", libelle: "a", etat: "livré", jalon: 0 }, { id: "F002", libelle: "b", etat: "prévu", jalon: 1 }, { id: "F003", libelle: "c", etat: "prévu" }], jalons: [{ id: "V1", titre: "pilote", note: "n" }] } });
  g = r.groups(); assert(r.byJalon && g.map(x => x.label).join("|") === "V0|V1 — pilote|Sans jalon" && g[1].avancement === "prévu 1", "par jalon : V0, V1 titré, sans jalon à la fin");
  // — ChaptersViewModel —
  const c = new VM.ChaptersViewModel({ cdc: cdcs[0], path: cdcs[0].chapters[1].path, md: "| # | Objet |\n|---|---|\n| D001 | Un choix (RM3013) |\n| ~~Q002~~ | fermée |\n" });
  assert.deepStrictEqual(c.tabs.map(t => t.title + (t.on ? "*" : "")), ["CDC PM", "Décisions*"], "sous-onglets, numéro retiré, courant marqué");
  const hh = c.anchored(mdToHtml(c.md)); assert(/<td id="sec-D001">D001/.test(hh), "ancre posée sur l'identifiant en tête de cellule"); assert(/data-action="ticket" data-rm="3013">RM3013<\/a>/.test(hh), "RM nu → geste vers la fiche"); assert(!/onclick=/.test(hh));
  assert(c.isDocLink("cdc-pm-90-decisions.md#sec-D001") && !c.isDocLink("https://x/y.md") && !c.isDocLink("#sec-D001"), "liens relatifs .md seulement");
  assert.strictEqual(c.resolve("../project/overview.md"), "projects/clients/i/projects/pm/project/overview.md");
  // — vues : aucun on*, gestes en data-action —
  const head = new VM.CdcHeaderViewModel({ cdcs, current: cdcs[0], page: "cdc-features" });
  for (const frag of [V.FeaturesPage(head, new VM.FeaturesViewModel({ data })), V.RoadmapPage(head, new VM.RoadmapViewModel({ data })), V.ChaptersPage(head, c, { md: mdToHtml }), V.FeaturesPage(new VM.CdcHeaderViewModel({ cdcs: [] }), new VM.FeaturesViewModel({}))]) { const s = String(frag); assert(!/\son\w+=/.test(s), "aucun on* dans les vues"); }
  const sF = String(V.FeaturesPage(head, new VM.FeaturesViewModel({ data }))); assert(/data-action="sort" data-key="etat"/.test(sF) && /data-action="select" data-key="a\/site\/site"/.test(sF) && /data-action="ticket" data-rm="20"/.test(sF) && /data-action="page" data-page="cdc-roadmap"/.test(sF), "en-têtes triables, sélecteur (2 CDC), tickets, pages");
  assert(/Aucun CDC vivant/.test(String(V.FeaturesPage(new VM.CdcHeaderViewModel({ cdcs: [] }), new VM.FeaturesViewModel({})))), "état vide explicite");
  assert(/pas de registre/.test(String(V.FeaturesPage(new VM.CdcHeaderViewModel({ cdcs, current: cdcs[1] }), new VM.FeaturesViewModel({ data: { missing: true } })))), "CDC sans registre : dit quoi faire");
  console.log("✓ CDC (RM3044) : choix du CDC, table triée/filtrée/comptée, feuille de route par état et par jalon, chapitres ancrés, vues sans on*");
  // — contrôleur —
  const calls = []; const store = { m: {}, getItem(k) { return this.m[k] || null; }, setItem(k, v) { this.m[k] = String(v); } };
  const svc = new S.CdcService({ storage: store, repo: { cdcs: async () => cdcs, features: async (cl, p, pr) => { calls.push("feat:" + pr); return data; }, file: async (pth) => { calls.push("file:" + pth.split("/").pop()); return "# " + pth.split("/").pop() + "\n\n| # | O |\n|---|---|\n| D001 | x |\n\n[déc](cdc-pm-90-decisions.md#sec-D001)"; } } });
  const F = fakeEl("cdcfeat"), C = fakeEl("cdcchap"), R = fakeEl("cdcroad"); const opened = [], tickets = [];
  const ctl = mountCdc({ features: F, chapters: C, roadmap: R }, { service: svc, storage: store, md: mdToHtml, later: (fn) => { fn(); return 1; }, openPanel: (n) => opened.push(n), showTicket: (rm) => tickets.push(rm), sessionProjects: () => ["a/site"] });
  await ctl.open("cdc-features"); assert(ctl.current().key === "a/site/site", "le CDC du projet de la session est pris"); assert(/pas de registre/.test(F.innerHTML), "site n'a pas de registre");
  await F.click("select", { key: "i/pm/pm" }); assert(ctl.current().key === "i/pm/pm" && store.m.karlCdc === "i/pm/pm" && /F001/.test(F.innerHTML), "changer de CDC : mémorisé, table rendue");
  await F.click("sort", { key: "date" }); assert(ctl.state.sort === "date" && store.m.karlCdcSort === "date:0"); await F.click("sort", { key: "date" }); assert(ctl.state.desc === true, "second clic inverse");
  await F.input("journal"); await settle(); assert(ctl.state.q === "journal" && /F001/.test(F.innerHTML) && !/F003/.test(F.innerHTML), "filtre appliqué (debounce immédiat en test)");
  await F.click("ticket", { rm: "10" }); assert.deepStrictEqual(tickets, ["10"], "un ticket ouvre sa fiche");
  await F.click("page", { page: "cdc-roadmap" }); assert(opened.includes("cdc-roadmap"), "les chips de page passent par le centre");
  await ctl.open("cdc"); assert(/cdc-pm-00-sommaire.md/.test(C.innerHTML) && calls.includes("file:cdc-pm-00-sommaire.md"), "le CDC s'ouvre sur son sommaire");
  await C.link("cdc-pm-90-decisions.md#sec-D001"); assert(calls.includes("file:cdc-pm-90-decisions.md") && ctl.state.chapter.endsWith("cdc-pm-90-decisions.md"), "lien relatif : chapitre suivi dans la page");
  await C.click("chapter", { path: cdcs[0].chapters[0].path }); assert(ctl.state.chapter === cdcs[0].chapters[0].path, "sous-onglet");
  ctl.goto({ key: "i/pm/pm", path: cdcs[0].chapters[1].path, sec: "D001" }); await settle(); assert(opened.includes("cdc") && ctl.state.chapter.endsWith("decisions.md"), "goto : CDC + chapitre + section");
  await ctl.open("cdc-roadmap"); assert(/En cours/.test(R.innerHTML) && /F003/.test(R.innerHTML), "feuille de route rendue");
  const n0 = calls.filter(x => x.startsWith("feat:")).length; await ctl.open("cdc-features"); assert(calls.filter(x => x.startsWith("feat:")).length === n0, "registre mis en cache par CDC");
  ctl.unmount();
  console.log("✓ CDC contrôleur : contexte de session, sélection mémorisée, tri persistant, filtre, tickets, pages, chapitres, liens, goto, cache");
  console.log("\nLes pages du CDC vivant passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
