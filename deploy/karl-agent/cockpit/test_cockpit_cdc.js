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
  assert.deepStrictEqual(f.rows().map(r => r.id), ["F001", "F002", "F003", "F004", "F005"]); assert(!f.hasVersion && f.cols.every(c => c.key !== "version"), "pas de colonne version sans version");
  assert.deepStrictEqual(f.counts.map(c => c.etat + ":" + c.n), ["livré:2", "en cours:1", "prévu:1", "écarté:1"], "comptes par état, écarté regroupé");
  assert.deepStrictEqual(f.rows()[3].tickets, [20, 21], "tickets multiples d'une entrée curée"); assert.strictEqual(f.rows()[2].parent, 5);
  f = new VM.FeaturesViewModel({ data, sort: "etat", desc: true }); assert.strictEqual(f.rows()[0].id, "F005", "tri par état inversé : écarté d'abord");
  f = new VM.FeaturesViewModel({ data, sort: "date" }); assert.strictEqual(f.rows()[0].id, "F005", "tri par date");
  f = new VM.FeaturesViewModel({ data, q: "rm21" }); assert.deepStrictEqual(f.rows().map(r => r.id), ["F004"], "filtre sur un RM couvert"); assert.strictEqual(f.count, "1 / 5");
  f = new VM.FeaturesViewModel({ data: { entrees: [{ id: "F001", libelle: "x", etat: "livré", jalon: 1 }, { id: "F002", libelle: "y", etat: "prévu", version: "V2" }, { id: "F003", libelle: "z", etat: "prévu" }] }, sort: "version" }); assert(f.hasVersion && f.rows().map(r => r.version).join("|") === "V1|V2|", "version : `version` ou `jalon` → V<n>, colonne présente, tri (vides en dernier)");
  // — ChaptersViewModel —
  const c = new VM.ChaptersViewModel({ cdc: cdcs[0], path: cdcs[0].chapters[1].path, md: "| # | Objet |\n|---|---|\n| D001 | Un choix (RM3013) |\n| ~~Q002~~ | fermée |\n" });
  assert.deepStrictEqual(c.tabs.map(t => t.title + (t.on ? "*" : "")), ["CDC PM", "Décisions*"], "sous-onglets, numéro retiré, courant marqué");
  const hh = c.anchored(mdToHtml(c.md)); assert(/<td id="sec-D001">D001/.test(hh), "ancre posée sur l'identifiant en tête de cellule"); assert(/data-action="ticket" data-rm="3013">RM3013<\/a>/.test(hh), "RM nu → geste vers la fiche"); assert(!/onclick=/.test(hh));
  assert(c.isDocLink("cdc-pm-90-decisions.md#sec-D001") && !c.isDocLink("https://x/y.md") && !c.isDocLink("#sec-D001"), "liens relatifs .md seulement");
  assert.strictEqual(c.resolve("../project/overview.md"), "projects/clients/i/projects/pm/project/overview.md");
  // — vues : aucun on*, gestes en data-action —
  const head = new VM.CdcHeaderViewModel({ cdcs, current: cdcs[0], page: "cdc-features" });
  for (const frag of [V.FeaturesPage(head, new VM.FeaturesViewModel({ data })), V.ChaptersPage(head, c, { md: mdToHtml }), V.FeaturesPage(new VM.CdcHeaderViewModel({ cdcs: [] }), new VM.FeaturesViewModel({}))]) { const s = String(frag); assert(!/\son\w+=/.test(s), "aucun on* dans les vues"); }
  const sF = String(V.FeaturesPage(head, new VM.FeaturesViewModel({ data }))); assert(/data-action="sort" data-key="etat"/.test(sF) && /data-action="select" data-key="a\/site\/site"/.test(sF) && /data-action="ticket" data-rm="20"/.test(sF) && /data-action="page" data-page="chap:/.test(sF), "en-têtes triables, sélecteur (2 CDC), tickets, pages");
  assert(/Aucun CDC vivant/.test(String(V.FeaturesPage(new VM.CdcHeaderViewModel({ cdcs: [] }), new VM.FeaturesViewModel({})))), "état vide explicite");
  assert.deepStrictEqual(head.pages.map(p => p.label), ["📋 Fonctionnalités", "📘 CDC vivant", "⚖️ Décisions"], "onglets à plat : table, sommaire, puis un par chapitre (pas le 10, plus de feuille de route dérivée)");
  assert(head.pages[1].key === "chap:" + cdcs[0].chapters[0].path && head.pages[2].key === "chap:" + cdcs[0].chapters[1].path, "un chapitre = page chap:<path>");
  assert(new VM.CdcHeaderViewModel({ cdcs, current: cdcs[0], page: "cdc", path: cdcs[0].chapters[1].path }).pages[2].on, "le chapitre courant est l'onglet actif");
  assert.deepStrictEqual(VM.cdcTabs(cdcs[1]).map(t => t.label + (t.enabled ? "" : "✗")), ["📋 Fonctionnalités✗", "📘 CDC vivant"], "cdcTabs : fonctionnalités désactivées sans registre (onglet projets)");
  assert.strictEqual(VM.chapterLabel({ file: "cdc-pm-99-questions-ouvertes.md", title: "Questions ouvertes — projet PM (RM3043)" }), "❓ Questions ouvertes");
  // RM3053 : forme générique (cdc.md, cdc-features.md, cdc-roadmap.md, cdc-decisions.md, cdc-questions.md, cdc-notes.md, cdc-help.md)
  const gen = { key: "i/pm/cdc", client: "i", project: "pm", prefix: "cdc", title: "CDC vivant du projet PM", path: "p/cdc.md", registry: true, chapters: [
    { file: "cdc.md", path: "p/cdc.md", title: "CDC vivant du projet PM (pm-ai-agents) — sommaire et méthode" }, { file: "cdc-features.md", path: "p/cdc-features.md", title: "Fonctionnalités du projet `iprospective/pm-ai-agents`" },
    { file: "cdc-roadmap.md", path: "p/cdc-roadmap.md", title: "Roadmap — projet `iprospective/pm-ai-agents`" }, { file: "cdc-decisions.md", path: "p/cdc-decisions.md", title: "Registre des décisions — projet PM (RM3043)" },
    { file: "cdc-questions.md", path: "p/cdc-questions.md", title: "Questions ouvertes — projet PM (RM3043)" }, { file: "cdc-notes.md", path: "p/cdc-notes.md", title: "Notes en vrac — projet PM (RM3043)" }, { file: "cdc-help.md", path: "p/cdc-help.md", title: "Aide — projet `iprospective/pm-ai-agents`" }] };
  const gh = new VM.CdcHeaderViewModel({ cdcs: [gen], current: gen, page: "cdc-features" });
  assert.deepStrictEqual(gh.pages.map(p => p.label), ["📋 Fonctionnalités", "📘 CDC vivant", "🗺 Roadmap", "⚖️ Registre des décisions", "❓ Questions ouvertes", "🗒 Notes en vrac", "📖 Aide"], "forme générique : sommaire = cdc.md, chapitre features exclu, libellés nettoyés");
  assert(gh.pages[1].key === "chap:p/cdc.md", "CDC vivant = cdc.md");
  assert(/pas de registre/.test(String(V.FeaturesPage(new VM.CdcHeaderViewModel({ cdcs, current: cdcs[1] }), new VM.FeaturesViewModel({ data: { missing: true } })))), "CDC sans registre : dit quoi faire");
  console.log("✓ CDC (RM3044) : choix du CDC, table triée/filtrée/comptée avec version, chapitres ancrés, vues sans on*");
  // — contrôleur —
  const calls = []; const store = { m: {}, getItem(k) { return this.m[k] || null; }, setItem(k, v) { this.m[k] = String(v); } };
  const svc = new S.CdcService({ storage: store, repo: { cdcs: async () => cdcs, features: async (cl, p, pr) => { calls.push("feat:" + pr); return data; }, file: async (pth) => { calls.push("file:" + pth.split("/").pop()); return "# " + pth.split("/").pop() + "\n\n| # | O |\n|---|---|\n| D001 | x |\n\n[déc](cdc-pm-90-decisions.md#sec-D001)"; } } });
  const F = fakeEl("cdccard"); const C = F, R = F; const opened = [], tickets = [];
  const ctl = mountCdc(F, { service: svc, storage: store, md: mdToHtml, later: (fn) => { fn(); return 1; }, openPanel: () => opened.push("cdc"), showTicket: (rm) => tickets.push(rm), sessionProjects: () => ["a/site"] });
  await ctl.open("cdc-features"); assert(ctl.page() === "cdc-features" && store.m.karlCdcPage === "cdc-features", "onglet courant mémorisé"); assert(ctl.current().key === "a/site/site", "le CDC du projet de la session est pris"); assert(/pas de registre/.test(F.innerHTML), "site n'a pas de registre");
  await F.click("select", { key: "i/pm/pm" }); assert(ctl.current().key === "i/pm/pm" && store.m.karlCdc === "i/pm/pm" && /F001/.test(F.innerHTML), "changer de CDC : mémorisé, table rendue");
  await F.click("sort", { key: "date" }); assert(ctl.state.sort === "date" && store.m.karlCdcSort === "date:0"); await F.click("sort", { key: "date" }); assert(ctl.state.desc === true, "second clic inverse");
  await F.input("journal"); await settle(); assert(ctl.state.q === "journal" && /F001/.test(F.innerHTML) && !/F003/.test(F.innerHTML), "filtre appliqué (debounce immédiat en test)");
  await F.click("ticket", { rm: "10" }); assert.deepStrictEqual(tickets, ["10"], "un ticket ouvre sa fiche");
  await F.click("page", { page: "chap:" + cdcs[0].chapters[1].path }); assert(ctl.page() === "cdc" && ctl.state.chapter.endsWith("decisions.md") && opened.length === 0, "les onglets changent la page DANS le panneau, sans passer par le centre");
  await F.click("page", { page: "zzz" }); assert(ctl.page() === "cdc", "onglet inconnu ignoré");
  await ctl.open("cdc"); assert(ctl.state.chapter.endsWith("decisions.md") && calls.includes("file:cdc-pm-90-decisions.md"), "« cdc » rouvre le dernier chapitre lu");
  await ctl.open("chap:" + cdcs[0].chapters[0].path); assert(/cdc-pm-00-sommaire.md/.test(C.innerHTML) && calls.includes("file:cdc-pm-00-sommaire.md"), "l'onglet CDC vivant ouvre le sommaire");
  await C.link("cdc-pm-90-decisions.md#sec-D001"); assert(calls.includes("file:cdc-pm-90-decisions.md") && ctl.state.chapter.endsWith("cdc-pm-90-decisions.md"), "lien relatif : chapitre suivi dans la page");
  await C.click("page", { page: "chap:" + cdcs[0].chapters[0].path }); assert(ctl.state.chapter === cdcs[0].chapters[0].path && ctl.page() === "cdc" && store.m.karlCdcPage === "chap:" + cdcs[0].chapters[0].path, "onglet chapitre à plat, mémorisé");
  await ctl.open("cdc-features"); ctl.goto({ key: "i/pm/pm", path: cdcs[0].chapters[1].path, sec: "D001" }); await settle(); assert(opened.includes("cdc") && ctl.page() === "cdc" && ctl.state.chapter.endsWith("decisions.md"), "goto : ouvre le panneau sur l'onglet chapitres, CDC + chapitre + section");
  const ctl2 = mountCdc(fakeEl("x"), { service: svc, storage: store, md: mdToHtml }); assert(ctl2.page() === "cdc" && ctl2.state.chapter.endsWith("decisions.md"), "l'onglet chapitre mémorisé est repris au montage"); ctl2.unmount();
  const n0 = calls.filter(x => x.startsWith("feat:")).length; await ctl.open("cdc-features"); assert(calls.filter(x => x.startsWith("feat:")).length === n0, "registre mis en cache par CDC");
  ctl.unmount();
  console.log("✓ CDC contrôleur : contexte de session, sélection mémorisée, tri persistant, filtre, tickets, pages, chapitres, liens, goto, cache");
  console.log("\nLes pages du CDC vivant passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
