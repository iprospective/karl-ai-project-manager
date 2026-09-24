#!/usr/bin/env node
// Tests des pages du CDC vivant (RM3044) : choix du CDC en contexte, table des fonctionnalités (tri, filtre, comptes), feuille de route
// (par jalon / par état), chapitres (ancres D/Q, liens relatifs, RM cliquables), vues sans on*, contrôleur avec service factice.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));
function fakeEl(id) { const L = []; let inner = ""; const self = { id, style: {}, textContent: "", kids: {}, get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, querySelector(s) { return self.kids[s] || null; }, querySelectorAll() { return []; }, contains() { return true; }, appendChild() {}, replaceChildren(...n) { inner = n.map(x => x.outerHTML || x.textContent || "").join(""); }, addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n, getAttribute: (k) => (data || {})[k], value: "" }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await settle(); },
  async input(value) { const n = { dataset: { action: "q" }, closest: () => n, value }; for (const [t, f] of [...L]) if (t === "input") await f({ target: n, preventDefault() {} }); await settle(); },
  async link(href) { const n = { getAttribute: () => href, closest: (s) => s === "a[href]" ? n : null, dataset: {} }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await settle(); },
  async change(action, data, value) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n, value }; for (const [t, f] of [...L]) if (t === "change") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await settle(); } }; return self; }
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
    { id: "F006", libelle: "Capacité sans ticket", domaine: "Karl", domaine_technique: "Outillage PM", type: "feature", etat: "livré", date: "2026-09-03", manuel: true },
    { id: "F005", rm: 13, libelle: "Abandonné", domaine: "Cockpit", type: "feature", etat: "écarté (abandonne)", date: "2026-07-01" },
  ], domaines: ["Cockpit", "Outillage", "Karl"], jalons: [] };
  let f = new VM.FeaturesViewModel({ data, sort: "id" });
  assert.deepStrictEqual(f.rows().map(r => r.id), ["F001", "F002", "F003", "F004", "F005", "F006"]); assert(!f.hasVersion && f.cols.every(c => c.key !== "version"), "pas de colonne version sans version");
  // RM3099 : le domaine d'USAGE classe, le domaine TECHNIQUE est une étiquette — une colonne, pas un second plan.
  assert(f.cols.some(c => c.key === "domaine_technique"), "colonne Technique (domaine technique en étiquette)");
  assert.strictEqual(f.rows()[5].tech, "Outillage PM", "le domaine technique remonte dans la ligne");
  assert.deepStrictEqual(f.rows()[5].tickets, [], "une fonctionnalité peut n'avoir AUCUN ticket (RM3099-D001)");
  assert.deepStrictEqual(new VM.FeaturesViewModel({ data, q: "outillage pm" }).rows().map(r => r.id), ["F006"], "le filtre porte aussi sur le domaine technique");
  assert.deepStrictEqual(f.counts.map(c => c.etat + ":" + c.n), ["livré:3", "en cours:1", "prévu:1", "écarté:1"], "comptes par état, écarté regroupé");
  assert.deepStrictEqual(f.rows()[3].tickets, [20, 21], "tickets multiples d'une entrée curée"); assert.strictEqual(f.rows()[2].parent, 5);
  const CDCS_T = [{ key: "i/pm/pm", label: "pm", chapters: [] }];
  // RM3306 — isoler les fonctionnalités qu'AUCUN ticket ne porte : elles n'apparaissent dans aucune
  // liste de travail, donc « on la ticketera plus tard » devient « jamais » si rien ne les compte.
  {
    const av = new VM.FeaturesViewModel({ data, sort: "id" });
    assert.deepStrictEqual(av.sansTicket, { n: 1, aFaire: 0, on: false }, "F006 est sans ticket, mais livrée : une trace, rien à faire");
    const ap = new VM.FeaturesViewModel({ data: { ...data, entrees: [...data.entrees, { id: "F007", libelle: "Décidée, pas ticketée", domaine: "Karl", etat: "prévu", date: "2026-09-04" }] }, sort: "id" });
    assert.deepStrictEqual(ap.sansTicket, { n: 2, aFaire: 1, on: false }, "une fonctionnalité PRÉVUE sans ticket compte, elle, comme à faire");
    const filtre = new VM.FeaturesViewModel({ data, q: VM.SANS_TICKET, sort: "id" });
    assert.deepStrictEqual(filtre.rows().map(r => r.id), ["F006"], "le mot-clé isole les entrées sans ticket, sans chercher le texte");
    assert.strictEqual(filtre.sansTicket.on, true, "…et la pastille se sait active");
    assert.deepStrictEqual(new VM.FeaturesViewModel({ data, q: "sans ticket", sort: "id" }).rows().map(r => r.id), ["F006"],
                           "le texte « sans ticket » reste une recherche ordinaire — elle trouve le libellé, pas le filtre");
    const h = String(V.FeaturesPage(new VM.CdcHeaderViewModel({ cdcs: CDCS_T, current: CDCS_T[0], page: "cdc-features" }), ap));
    assert(/data-action="sans-ticket"/.test(h) && /sans ticket 2/.test(h) && /· 1 à faire/.test(h), "la pastille dit le compte et ce qui reste à faire");
    assert(!/data-action="sans-ticket"/.test(String(V.FeaturesPage(new VM.CdcHeaderViewModel({ cdcs: CDCS_T, current: CDCS_T[0], page: "cdc-features" }),
      new VM.FeaturesViewModel({ data: { ...data, entrees: data.entrees.filter(e => e.id !== "F006") }, sort: "id" })))), "aucune sans ticket : pas de pastille");
  }
  f = new VM.FeaturesViewModel({ data, sort: "etat", desc: true }); assert.strictEqual(f.rows()[0].id, "F005", "tri par état inversé : écarté d'abord");
  f = new VM.FeaturesViewModel({ data, sort: "date" }); assert.strictEqual(f.rows()[0].id, "F005", "tri par date");
  f = new VM.FeaturesViewModel({ data, q: "rm21" }); assert.deepStrictEqual(f.rows().map(r => r.id), ["F004"], "filtre sur un RM couvert"); assert.strictEqual(f.count, "1 / 6");
  f = new VM.FeaturesViewModel({ data: { entrees: [{ id: "F001", libelle: "x", etat: "livré", jalon: 1 }, { id: "F002", libelle: "y", etat: "prévu", version: "V2" }, { id: "F003", libelle: "z", etat: "prévu" }] }, sort: "version" }); assert(f.hasVersion && f.rows().map(r => r.version).join("|") === "V1|V2|", "version : `version` ou `jalon` → V<n>, colonne présente, tri (vides en dernier)");
  // — ChaptersViewModel —
  const c = new VM.ChaptersViewModel({ cdc: cdcs[0], path: cdcs[0].chapters[1].path, md: "| # | Objet |\n|---|---|\n| D001 | Un choix (RM3013) |\n| ~~Q002~~ | fermée |\n" });
  assert.deepStrictEqual(c.tabs.map(t => t.title + (t.on ? "*" : "")), ["CDC PM", "Décisions*"], "sous-onglets, numéro retiré, courant marqué");
  const hh = c.anchored(mdToHtml(c.md)); assert(/<td id="sec-D001">D001/.test(hh), "ancre posée sur l'identifiant en tête de cellule"); assert(/data-action="ticket" data-rm="3013">RM3013<\/a>/.test(hh), "RM nu → geste vers la fiche"); assert(!/onclick=/.test(hh));
  assert(c.isDocLink("cdc-pm-90-decisions.md#sec-D001") && !c.isDocLink("https://x/y.md") && !c.isDocLink("#sec-D001"), "liens relatifs .md seulement");
  // RM3064 : un registre fusionné reçoit ses gestes (état + ✕) par ligne, et une colonne d'en-tête ; le RM de l'id n'est pas un lien
  const cm = new VM.ChaptersViewModel({ path: "p/cdc-decisions.md", md: "| # | Ticket | Objet | État |\n|---|---|---|---|\n| RM3044-D001 | RM3044 | Un choix (RM3013) | ✅ |\n" });
  const hm = cm.anchored(mdToHtml(cm.md));
  assert(/<td id="sec-RM3044-D001">RM3044-D001<\/td>/.test(hm), "ancre sur l'id fusionné, RM de l'id non lié"); assert(/data-action="ticket" data-rm="3044">RM3044<\/a>/.test(hm) && /data-rm="3013"/.test(hm), "la colonne Ticket et le RM du texte sont des gestes");
  assert(/data-action="think-state" data-rm="3044" data-id="D001"/.test(hm) && /data-action="think-delete" data-rm="3044" data-id="D001"/.test(hm) && /data-action="think-move" data-rm="3044" data-id="D001"/.test(hm) && /<th class="cdc-act"><\/th>/.test(hm) && !/onclick=/.test(hm), "gestes injectés, en-tête complété, aucun on*");
  assert(!/cdc-act/.test(c.anchored(mdToHtml("| # | Objet |\n|---|---|\n| D001 | x |\n"))), "un CDC numéroté (ids locaux) n'a pas de gestes : ses entrées ne sont pas des think");
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
  assert.strictEqual(VM.chapterLabel({ file: "cdc-pm-99-questions-ouvertes.md", title: "Questions ouvertes — projet PM (RM3043)" }), "❓ Questions ouvertes"); assert.strictEqual(VM.chapterLabel({ file: "cdc-rm2881-16-dictionnaire.md", title: "16 — Dictionnaire des données" }), "📚 Dictionnaire des données");
  // RM3053 : forme générique (cdc.md, cdc-features.md, cdc-roadmap.md, cdc-decisions.md, cdc-questions.md, cdc-notes.md, cdc-help.md)
  const gen = { key: "i/pm/cdc", client: "i", project: "pm", prefix: "cdc", title: "CDC vivant du projet PM", path: "p/cdc.md", registry: true, chapters: [
    { file: "cdc.md", path: "p/cdc.md", title: "CDC vivant du projet PM (pm-ai-agents) — sommaire et méthode" }, { file: "cdc-features.md", path: "p/cdc-features.md", title: "Fonctionnalités du projet `iprospective/pm-ai-agents`" },
    { file: "cdc-roadmap.md", path: "p/cdc-roadmap.md", title: "Roadmap — projet `iprospective/pm-ai-agents`" }, { file: "cdc-decisions.md", path: "p/cdc-decisions.md", title: "Registre des décisions — projet PM (RM3043)" },
    { file: "cdc-questions.md", path: "p/cdc-questions.md", title: "Questions ouvertes — projet PM (RM3043)" }, { file: "cdc-notes.md", path: "p/cdc-notes.md", title: "Notes en vrac — projet PM (RM3043)" }, { file: "cdc-help.md", path: "p/cdc-help.md", title: "Aide — projet `iprospective/pm-ai-agents`" }] };
  const gh = new VM.CdcHeaderViewModel({ cdcs: [gen], current: gen, page: "cdc-features" });
  assert.deepStrictEqual(gh.pages.map(p => p.label), ["📋 Fonctionnalités", "📘 CDC vivant", "🗺 Roadmap", "⚖️ Registre des décisions", "🗒 Vrac", "❓ Questions ouvertes", "📖 Guide"], "forme générique : sommaire = cdc.md, chapitre features exclu, noms et ORDRE de la norme cdc (roadmap, dictionnaire, décisions, vrac, questions, glossaire, guide)");
  const gen2 = Object.assign({}, gen, { chapters: gen.chapters.concat([{ file: "cdc-dict.md", path: "p/cdc-dict.md", title: "Dictionnaire des données" }, { file: "cdc-audit-existant.md", path: "p/cdc-audit-existant.md", title: "Audit de l'existant" }]) });
  assert.deepStrictEqual(new VM.CdcHeaderViewModel({ cdcs: [gen2], current: gen2 }).pages.map(p => p.label), ["📋 Fonctionnalités", "📘 CDC vivant", "Audit de l'existant", "🗺 Roadmap", "📚 Dictionnaire", "⚖️ Registre des décisions", "🗒 Vrac", "❓ Questions ouvertes", "📖 Guide"], "un chapitre thématique passe avant les registres ; le dictionnaire à sa place");
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
  // RM3064 : les gestes d'édition partent vers le service, avec confirmation pour la suppression ; le cache est invalidé
  const edits = []; svc.repo.thinkEdit = async (b) => { edits.push(["think", b]); return { ok: true }; }; svc.repo.featureEdit = async (b) => { edits.push(["feature", b]); return { ok: true }; };
  ctl.unmount();   // sinon son gestionnaire (confirm par défaut) répondrait aussi au clic
  let ok = false; const ctl3 = mountCdc(F, { service: svc, storage: store, md: mdToHtml, later: (fn) => { fn(); return 1; }, confirm: () => ok, notify: () => {}, sessionProjects: () => [] });
  await ctl3.open("cdc-features");
  await F.click("think-delete", { rm: "44", id: "D001" }); assert(edits.length === 0 || edits.every(e => e[0] !== "think"), "suppression refusée sans confirmation");
  ok = true; await F.click("think-delete", { rm: "44", id: "D001" }); assert(edits.some(e => e[0] === "think" && e[1].action === "delete" && e[1].rm === "44" && e[1].id === "D001"), "suppression confirmée → service");
  const n1 = calls.filter(x => x.startsWith("feat:")).length; await ctl3.svc.featureEdit({ id: "F003", etat: "écarté" }); await ctl3.open("cdc-features"); assert(edits.some(e => e[0] === "feature" && e[1].id === "F003" && e[1].etat === "écarté" && e[1].client === "i") && calls.filter(x => x.startsWith("feat:")).length === n1 + 1, "état d'une fonctionnalité → service, registre rechargé");
  ctl3.unmount();   // comme ci-dessus : deux contrôleurs sur le même hôte répondraient tous deux au clic
  // RM3258 : déplacer une entrée vers un autre ticket — même route, le front ne dit que la cible
  let cible = "3015"; const ctlMv = mountCdc(F, { service: svc, storage: store, md: mdToHtml, later: (fn) => { fn(); return 1; }, confirm: () => true, prompt: () => cible, notify: () => {}, sessionProjects: () => [] });
  await ctlMv.open("cdc-features");
  edits.length = 0; await F.click("think-move", { rm: "44", id: "Q002" });
  assert(edits.some(e => e[0] === "think" && e[1].action === "move" && e[1].to === "3015" && e[1].id === "Q002"), "déplacement → service, avec le ticket cible");
  cible = "pas un id"; edits.length = 0; await F.click("think-move", { rm: "44", id: "Q002" });
  assert(edits.length === 0, "saisie invalide : rien n'est envoyé");
  ctlMv.unmount();
  console.log("✓ CDC contrôleur : contexte de session, sélection mémorisée, tri persistant, filtre, tickets, pages, chapitres, liens, goto, cache");
  // ── RM3060 : les versions sont des étapes de travail, créées ici, rattachées là ──
  const dataV = { entrees: [{ id: "F001", libelle: "a", etat: "en cours", version: "V0" }, { id: "F002", libelle: "b", etat: "prévu" }],
                  domaines: [], jalons: [], versions: [{ id: "V0", role: "alpha", etat: "en cours" }, { id: "V1", role: "multi-utilisateur" }] };
  const vmV = new VM.FeaturesViewModel({ data: dataV });
  assert.deepStrictEqual(vmV.versions, ["V0", "V1"], "les versions déclarées sont offertes au rattachement");
  assert(vmV.hasVersion, "la colonne Version s'affiche dès qu'une version existe, même portée par personne");
  const vmOrph = new VM.FeaturesViewModel({ data: { entrees: [{ id: "F001", libelle: "a", version: "V9" }], versions: [] } });
  assert.deepStrictEqual(vmOrph.versions, ["V9"], "une version portée mais non déclarée reste offerte : sinon on ne pourrait plus détacher");
  const sV = String(V.FeaturesPage(head, vmV));
  assert(/data-action="feature-version" data-id="F001"/.test(sV), "chaque ligne porte son sélecteur de version");
  assert(/<option value="V0" selected>/.test(sV), "la version courante est sélectionnée");
  assert(/— détacher —/.test(sV), "une ligne rattachée peut être détachée");
  assert(!/\son\w+=/.test(sV), "aucun on* dans la table avec versions");

  const road = new VM.ChaptersViewModel({ path: "x/docs/cdc-roadmap.md", md: "# rm" });
  assert(road.isRoadmap && !new VM.ChaptersViewModel({ path: "x/docs/cdc-notes.md" }).isRoadmap, "le formulaire n'apparaît que sur la feuille de route");
  const sR = String(V.ChaptersPage(head, road, { md: mdToHtml, versions: ["V0"] }));
  assert(/data-role="vform"/.test(sR) && /data-action="version-save"/.test(sR) && /data-action="version-drop"/.test(sR), "créer et retirer une version depuis la feuille de route");
  assert(/data-role="vrole"/.test(sR) && /data-role="vcritere"/.test(sR), "une version porte un rôle et un critère de passage");
  assert(!/data-role="vform"/.test(String(V.ChaptersPage(head, new VM.ChaptersViewModel({ path: "x/docs/cdc-notes.md", md: "x" }), { md: mdToHtml }))), "pas de formulaire ailleurs");
  assert(!/\son\w+=/.test(sR), "aucun on* dans la feuille de route");

  const vedits = []; svc.repo.versionEdit = async (b) => { vedits.push(b); return { ok: true }; };
  const G = fakeEl("cdcG");
  G.kids['[data-role="vform"]'] = { querySelector: (s) => ({ '[data-role="vid"]': { value: "V2" }, '[data-role="vrole"]': { value: "multi-utilisateur" },
    '[data-role="vcritere"]': { value: "deux devs branchés" }, '[data-role="vetat"]': { value: "prévu" } }[s] || null) };
  let okv = true;
  const ctl4 = mountCdc(G, { service: svc, storage: store, md: mdToHtml, later: (fn) => { fn(); return 1; }, confirm: () => okv, notify: () => {}, sessionProjects: () => [] });
  await ctl4.open("cdc-features");
  await G.change("feature-version", { id: "F002" }, "V1");
  assert.deepStrictEqual(vedits[vedits.length - 1], { client: "i", project: "pm", action: "attach", id: "F002", version: "V1" }, "rattacher une fonctionnalité part vers le service");
  await G.change("feature-version", { id: "F002" }, "-");
  assert.strictEqual(vedits[vedits.length - 1].version, "-", "et on peut la détacher");
  await G.click("version-save");
  assert.deepStrictEqual(vedits[vedits.length - 1], { client: "i", project: "pm", action: "add", version: "V2", role: "multi-utilisateur", critere: "deux devs branchés", etat: "prévu" }, "créer une version envoie son rôle et son critère");
  okv = false; const avant = vedits.length; await G.click("version-drop");
  assert.strictEqual(vedits.length, avant, "retirer une version sans confirmation ne fait rien");
  okv = true; await G.click("version-drop");
  assert.deepStrictEqual(vedits[vedits.length - 1], { client: "i", project: "pm", action: "drop", version: "V2" }, "retrait confirmé → service");
  ctl4.unmount();
  console.log("✓ RM3060 : versions créées depuis la feuille de route, fonctionnalités rattachées depuis la table");

  console.log("\nLes pages du CDC vivant passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
