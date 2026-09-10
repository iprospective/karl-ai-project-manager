#!/usr/bin/env node
// Tests du markdown (RM2309), du glossaire du jargon (RM2623/2634), du glossaire de projet (RM2675), de l'aide intégrée
// (RM2593) et de la modale doc (RM2759) migrés — RM2889.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 10));
const escO = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fakeElement(id) { const L = []; let inner = ""; const kids = {}; const cls = new Set(); return { id, kids, dataset: {}, style: {}, textContent: "", value: "", get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, set className(v) { cls.clear(); if (v) cls.add(v); }, get className() { return [...cls].join(" "); },
  classList: { toggle(c, on) { on ? cls.add(c) : cls.delete(c); }, contains(c) { return cls.has(c); }, add(c) { cls.add(c); }, remove(c) { cls.delete(c); } },
  querySelector(sel) { return kids[sel] || null; }, addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, target) { for (const [t, f] of [...L]) if (t === type) await f({ target, preventDefault() {}, stopPropagation() {} }); } }; }
(async () => {
  const { mdToHtml } = await import(path.join(DIR, "src/core/markdown.js"));
  const G = await import(path.join(DIR, "src/modules/doc/glossary.js"));
  const { HelpService } = await import(path.join(DIR, "src/modules/doc/help.service.js"));
  const VM = await import(path.join(DIR, "src/modules/doc/GlossaryViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/doc/Doc.view.js"));
  const { mountDocModal } = await import(path.join(DIR, "src/modules/doc/doc.controller.js"));
  // — RM2309 : markdown sûr —
  let h = mdToHtml('<script>alert(1)</script> et <img src=x onerror=y>'); assert(!/<script|<img/.test(h) && h.includes("&lt;script&gt;"));
  h = mdToHtml("[clic](javascript:alert(1)) et [ok](https://ex.te/p)"); assert(!h.includes('href="javascript:') && h.includes('href="https://ex.te/p"') && h.includes('rel="noopener"'));
  h = mdToHtml("---\ntitle: X\n---\n# Titre\n\n## Sous *titre*\n\ntexte **fort** et `code`\n\n- [x] fait\n- [ ] à faire\n1. un\n\n> note\n\n---\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nlet x = '<b>'\n```");
  for (const frag of ['<pre class="mdfm">title: X</pre>', "<h1>Titre</h1>", "<h2>Sous <i>titre</i></h2>", "<b>fort</b>", "<code>code</code>", "<li>☑ fait</li>", "<li>☐ à faire</li>", "<ol><li>un</li></ol>", "<blockquote>note</blockquote>", "<hr>", "<th>a</th>", "<td>2</td>", "<pre>let x = '&lt;b&gt;'</pre>"]) assert(h.includes(frag), "fragment attendu : " + frag);
  assert(h.startsWith('<div class="mdview">')); h = mdToHtml("ligne un\nligne deux\n\nautre para"); assert(h.includes("<p>ligne un ligne deux</p>") && h.includes("<p>autre para</p>")); assert.strictEqual(mdToHtml(null), '<div class="mdview"></div>');
  console.log("✓ markdown (RM2309) : échappement, liens filtrés, titres, listes/cases, code, tableau, citation, hr, frontmatter, paragraphes");
  // — RM2623 / RM2634 : glossaire du jargon —
  const { GLOSSARY, GLOSS, glossNorm, glossMatch, glossify, glossGroups } = G;
  assert.strictEqual(glossNorm("  Worktree, "), "worktree"); assert.strictEqual(glossNorm("serve-check"), "serve-check"); assert(GLOSS.map["worktrees"] && GLOSS.map["worktrees"].t === "worktree"); assert.strictEqual(GLOSS.surfaces.indexOf("scope"), -1); assert(GLOSS.surfaces[0].length >= GLOSS.surfaces[GLOSS.surfaces.length - 1].length);
  assert(glossMatch("worktree", GLOSSARY).some(e => e.t === "worktree")); assert(glossMatch("bac à sable", GLOSSARY).some(e => e.t === "sandbox")); assert.strictEqual(glossMatch("zzznope", GLOSSARY).length, 0); assert.strictEqual(glossMatch("", GLOSSARY).length, GLOSSARY.length);
  const gy = glossify(escO("un worktree ici")); assert(/<span class="gloss" data-term="worktree"/.test(gy) && /title="Copie de travail Git/.test(gy)); assert.strictEqual(glossify(escO("reworktreeX")), "reworktreeX"); assert(!/gloss/.test(glossify(escO("un scope large")))); assert(/data-term="worktree"/.test(glossify(escO("des worktrees")))); assert(!/<b>/.test(glossify(escO("<b>worktree</b>"))) && /&lt;b&gt;/.test(glossify(escO("<b>worktree</b>"))));
  assert.strictEqual(glossify("x", { surfaces: [], map: {} }), "x", "index vide : texte inchangé"); assert.strictEqual(glossify(null), "");
  const gg = glossGroups(GLOSSARY); assert(gg.length >= 5 && gg.every(g => g.items.length > 0) && gg.reduce((n, g) => n + g.items.length, 0) === GLOSSARY.length); const cats = gg.map(g => g.cat); assert(cats.indexOf("git") >= 0 && cats.indexOf("git") < cats.indexOf("gen"));
  const names = gg.find(g => g.cat === "git").items.map(i => i.t); assert(JSON.stringify(names) === JSON.stringify(names.slice().sort((a, b) => a.localeCompare(b)))); const filtered = glossGroups(glossMatch("git", GLOSSARY)); assert(filtered.length >= 1 && filtered.every(g => g.items.length > 0)); assert.strictEqual(glossGroups([{ t: "x", d: "y" }])[0].cat, "gen"); assert.strictEqual(glossGroups([{ t: "z", d: "w", c: "zzz" }])[0].cat, "zzz");
  // — RM2675 : glossaire de projet —
  const MD2675 = ["---", "title: Glossaire", "---", "# Glossaire du projet", "", "| Terme | Définition | Contexte | Alias |", "|---|---|---|---|", "| HFOV | Champ horizontal d'une optique. | 24 mm ⇒ 74°. | horizontal field of view |", "| rampe | Barre portant la rangée de guillotines. | 75 vannes × 40 mm. | — |"].join("\n");
  const rows = G.glossaireRows(MD2675); assert.strictEqual(rows.length, 2); assert(rows[0].terme === "HFOV" && rows[0].alias.includes("field of view")); assert(G.glossaireRows("").length === 0 && G.glossaireRows(null).length === 0); assert.strictEqual(G.glossaireRows("| a | b |")[0].contexte, "");
  assert.strictEqual(G.glossaireFiltre(rows, "").length, 2); assert.strictEqual(G.glossaireFiltre(rows, "RAMP").length, 1); assert.strictEqual(G.glossaireFiltre(rows, "field of view")[0].terme, "HFOV"); assert.strictEqual(G.glossaireFiltre(rows, "guillotines")[0].terme, "rampe"); assert.strictEqual(G.glossaireFiltre(rows, "zzz").length, 0);
  console.log("✓ glossaires (RM2623/2634/2675) : normalisation, index, recherche, soulignage sûr, catégories, tableau de projet filtrable");
  // — ViewModels et vues —
  const gvm = new VM.GlossaryViewModel({ query: "worktree", focus: "Worktrees" }); assert(/\/ \d+$/.test(gvm.count) && gvm.rows.length >= 1); const grp = gvm.groups(); assert(grp.some(g => g.items.some(i => i.key === "worktree" && i.hi)), "le terme demandé est mis en évidence, même par son alias");
  const gl = String(V.GlossaryList(gvm)); assert(/class="glosscat">Git &amp; versionnage/.test(gl) && /class="glossrow glosshi" data-k="worktree"/.test(gl) && /class="glossterm">worktree</.test(gl) && /class="glossalias">worktrees/.test(gl) && /class="glossdef">Copie de travail/.test(gl));
  assert(/Aucun terme ne correspond/.test(String(V.GlossaryList(new VM.GlossaryViewModel({ query: "zzznope" }))))); const gp = String(V.GlossaryPanel(new VM.GlossaryViewModel({ query: "" }))); assert(/id="glosssearch"/.test(gp) && /id="glosscount">\d+ \/ \d+</.test(gp) && /id="glosslist"/.test(gp) && !/onclick=|oninput=/.test(gp));
  const hvm = new VM.HelpViewModel({ topics: [{ id: "index", title: "Accueil" }, { id: "tickets", title: "Tickets <b>" }], topic: "tickets", md: "# Aide\nvoir [index](index) et [ext](https://x)" });
  const hp = String(V.HelpPage(hvm, { md: mdToHtml })); assert(/class="chip" data-action="help" data-topic="index">Accueil</.test(hp) && /class="chip on" data-action="help" data-topic="tickets">Tickets &lt;b&gt;</.test(hp) && /<h1>Aide<\/h1>/.test(hp) && /href="https:\/\/x"/.test(hp) && !/href="index"/.test(hp), "sommaire en chips, page active marquée, corps en markdown");
  assert(hvm.isTopic("index") && !hvm.isTopic("https://x"));
  // — service : sommaire en cache, page manquante dite, fichier —
  const calls = []; const repo = { async topics() { calls.push("topics"); return [{ id: "index", title: "Accueil" }, { id: "tickets", title: "Tickets" }]; }, async page(t) { calls.push("page:" + t); if (t === "zz") throw new Error("404"); return "# " + t; }, async file(p) { calls.push("file:" + p); if (/absent/.test(p)) throw new Error("404 Not Found"); return "# Doc " + p; } };
  const svc = new HelpService({ repo }); let pg = await svc.page(); assert.deepStrictEqual([pg.topic, pg.md], ["index", "# index"], "sans sujet : la première page"); pg = await svc.page("tickets"); assert.strictEqual(pg.md, "# tickets"); assert.strictEqual(calls.filter(c => c === "topics").length, 1, "le sommaire n'est demandé qu'une fois");
  assert.strictEqual((await svc.page("zz")).md, "*(page d'aide introuvable)*"); const svcKo = new HelpService({ repo: { async topics() { throw new Error("x"); } } }); assert.strictEqual((await svcKo.page()).md, "*(aide indisponible)*", "sans sommaire : dit, pas vide");
  console.log("✓ aide (RM2593) : sommaire mis en cache, page par défaut, absences nommées ; vues sans onclick");
  // — le contrôleur —
  const el = fakeElement("docmodal"), title = fakeElement("doctitle"), content = fakeElement("doccontent"), toCenter = fakeElement("doc2center"), root = fakeElement("document");
  Object.assign(el.kids, { "#doctitle": title, "#doccontent": content, "#doc2center": toCenter });
  const ev = []; const ctr = mountDocModal(el, { service: svc, root, openCenterFile: (...a) => ev.push(["center", ...a]) });
  await ctr.openDoc("docs/cdc.md", "CDC"); assert(el.classList.contains("show") && title.textContent === "CDC" && toCenter.style.display === "" && /<h1>Doc docs\/cdc.md<\/h1>/.test(content.innerHTML), "RM2309 : document rendu en markdown"); assert.deepStrictEqual(ctr.current(), { path: "docs/cdc.md", name: "CDC" });
  ctr.docToCenter(); assert(!el.classList.contains("show") && ev.some(x => x[0] === "center" && x[1] === "doc" && x[3] === "docs/cdc.md"), "RM2759 : au centre, la modale se ferme");
  await ctr.openDoc("absent.md", "X"); assert(/erreur : 404 Not Found/.test(content.innerHTML));
  await ctr.openHelp(); assert(title.textContent === "❓ Aide" && toCenter.style.display === "none" && ctr.current() === null && /data-topic="index"/.test(content.innerHTML) && /<h1>index<\/h1>/.test(content.innerHTML), "aide : première page, plus de bouton « au centre »");
  await el.fire("click", { closest: (s) => s === "[data-action]" ? { dataset: { action: "help", topic: "tickets" } } : null }); await settle(); assert(/<h1>tickets<\/h1>/.test(content.innerHTML) && /class="chip on" data-action="help" data-topic="tickets"/.test(content.innerHTML), "le sommaire navigue");
  await el.fire("click", { closest: (s) => s === ".helpbody a[href]" ? { getAttribute: () => "index" } : null }); await settle(); assert(/<h1>index<\/h1>/.test(content.innerHTML), "un lien interne (href = id de sujet) navigue dans l'aide");
  // — RM3043 : menu CDC — un seul CDC s'ouvre directement, plusieurs se choisissent, les liens relatifs entre chapitres restent dans la modale
  const one = [{ client: "c", project: "p", prefix: "pm", path: "projects/clients/c/projects/p/docs/cdc-pm-00-sommaire.md", title: "CDC p", chapters: [{ file: "cdc-pm-00-sommaire.md" }, { file: "cdc-pm-90-decisions.md" }] }];
  const svc2 = { cdcs: async () => one, doc: async (pth) => "# Doc " + pth + "\n\n[décisions](cdc-pm-90-decisions.md) [ext](https://ex.te/x)", page: svc.page.bind(svc), topics: svc.topics.bind(svc) };
  const el2 = fakeElement("docmodal"), title2 = fakeElement("doctitle"), content2 = fakeElement("doccontent"), toCenter2 = fakeElement("doc2center");
  Object.assign(el2.kids, { "#doctitle": title2, "#doccontent": content2, "#doc2center": toCenter2 });
  const c2 = mountDocModal(el2, { service: svc2, root: fakeElement("document"), openCenterFile: () => {} });
  await c2.openCdc(); assert(title2.textContent === "CDC p" && c2.current().path === one[0].path && toCenter2.style.display === "", "un seul CDC : ouvert directement sur son sommaire");
  assert(c2.followDocLink("cdc-pm-90-decisions.md") === true && c2.current().path === "projects/clients/c/projects/p/docs/cdc-pm-90-decisions.md" && title2.textContent === "cdc-pm-90-decisions.md", "lien relatif : chapitre du même dossier ouvert dans la modale");
  assert(c2.followDocLink("../project/overview.md") === true && c2.current().path === "projects/clients/c/projects/p/project/overview.md", "lien relatif avec .. résolu");
  assert(c2.followDocLink("https://ex.te/x") === false && c2.followDocLink("#ancre") === false && c2.followDocLink("/abs.md") === false && c2.followDocLink("image.png") === false, "liens externes, ancres, absolus, non-.md : laissés au navigateur");
  await el2.fire("click", { closest: (s) => s === "#doccontent a[href]" ? { getAttribute: () => "cdc-pm-00-sommaire.md" } : null }); await settle(); assert(c2.current().path.endsWith("/project/cdc-pm-00-sommaire.md") || c2.current().path.endsWith("cdc-pm-00-sommaire.md"), "clic sur un lien relatif du document rendu → navigation dans la modale");
  svc2.cdcs = async () => [...one, { client: "c", project: "q", prefix: "q", path: "projects/clients/c/projects/q/docs/cdc-q-00-sommaire.md", title: "CDC q", chapters: [] }];
  await c2.openCdc(); assert(title2.textContent === "📋 CDC vivant" && c2.current() === null && /data-action="cdc-open"/.test(content2.innerHTML) && /c\/q/.test(content2.innerHTML) && !/onclick=/.test(content2.innerHTML), "plusieurs CDC : liste à choisir, gestes en data-*");
  await el2.fire("click", { closest: (s) => s === "[data-action]" ? { dataset: { action: "cdc-open", path: "projects/clients/c/projects/q/docs/cdc-q-00-sommaire.md", name: "CDC q" } } : null }); await settle(); assert(title2.textContent === "CDC q" && c2.current().path.endsWith("cdc-q-00-sommaire.md"), "choisir un CDC l'ouvre");
  svc2.cdcs = async () => []; await c2.openCdc(); assert(/Aucun CDC vivant/.test(content2.innerHTML), "aucun CDC : le texte dit comment en créer un");
  assert(typeof V.CdcList === "function" && String(V.CdcList([])).includes("Aucun CDC"), "vue CdcList exportée");
  console.log("✓ CDC vivant (RM3043) : ouverture directe / liste / vide, liens relatifs entre chapitres dans la modale");
  ctr.openGlossary("worktrees"); assert(title.textContent === "📖 Glossaire du jargon" && /id="glosssearch"/.test(content.innerHTML), "le glossaire prend la modale"); assert.strictEqual(ctr.mode(), "glossary");
  const list = fakeElement("glosslist"), cnt = fakeElement("glosscount"); Object.assign(el.kids, { "#glosslist": list, "#glosscount": cnt }); const vmF = ctr.renderGlossary("", "worktrees"); assert(/glosshi" data-k="worktree"/.test(list.innerHTML) && /^\d+ \/ \d+$/.test(cnt.textContent) && vmF.rows.length === GLOSSARY.length, "ouvert sur un terme : liste complète, le terme surligné");
  await el.fire("input", { id: "glosssearch", value: "zzznope" }); assert(/Aucun terme ne correspond/.test(list.innerHTML) && /^0 \//.test(cnt.textContent), "la recherche filtre en place");
  el.classList.remove("show"); await root.fire("click", { closest: (s) => s === ".gloss" ? { getAttribute: () => "sandbox" } : null }); assert(el.classList.contains("show") && title.textContent === "📖 Glossaire du jargon", "RM2623 : un terme souligné n'importe où ouvre le glossaire dessus");
  await el.fire("click", el); assert(!el.classList.contains("show"), "clic sur le voile : fermé"); ctr.openHelp(); await settle(); await el.fire("click", { closest: (s) => s === "[data-action]" ? { dataset: { action: "close" } } : null }); assert(!el.classList.contains("show"));
  assert.strictEqual(ctr.md("**a**"), '<div class="mdview"><p><b>a</b></p></div>'); assert(/data-term="worktree"/.test(ctr.glossify("un worktree")));
  ctr.unmount(); assert.strictEqual(el.listenerCount + root.listenerCount, 0);
  console.log("✓ modale doc : document → markdown → centre, aide naviguée (sommaire, liens internes), glossaire cherchable et ouvert sur un terme, voile");
  console.log("\nTous les tests markdown / glossaire / aide / modale passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
