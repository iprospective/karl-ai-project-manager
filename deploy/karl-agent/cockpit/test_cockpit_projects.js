#!/usr/bin/env node
// Tests du panneau « projets » migré (RM2889, L4) — porte RM2760 de test_cockpit.js.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
function fakeElement() {
  const L = []; let inner = "";
  return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, querySelector: () => null,
    addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
    get listenerCount() { return L.length; }, get _L() { return L; },
    async click(action, data) { const n = { dataset: { action, ...data } }; for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => s === "[data-action]" ? n : null }, stopPropagation() {} }); },
    async input(value) { const n = { value }; for (const [t, f] of [...L]) if (t === "input") await f({ target: { closest: s => s === "#pj-filter" ? n : null } }); } };
}
(async () => {
  const { groupProjectsByClient, liveByProject } = await import(path.join(DIR, "src/models/projects/projectGroups.js"));
  const { ProjectsPanelViewModel } = await import(path.join(DIR, "src/viewmodels/projects/ProjectsPanelViewModel.js"));
  const { ProjectsList, ProjectsPanel } = await import(path.join(DIR, "src/views/projects/ProjectsPanel.view.js"));
  const { mountProjectsPanel } = await import(path.join(DIR, "src/controllers/projects.controller.js"));
  const PJ = [{ client: "calicote", project: "prestashop", value: "calicote/prestashop" }, { client: "abatik", project: "infra", value: "abatik/infra" },
              { client: "calicote", project: "infra", value: "calicote/infra" }, { client: "abatik", project: "site", value: "abatik/site" }];
  const g = groupProjectsByClient(PJ, "");
  assert.deepEqual(g.map(x => x.client), ["abatik", "calicote"]); assert.deepEqual(g[0].projects.map(p => p.project), ["infra", "site"]);
  assert.deepEqual(groupProjectsByClient([], "").length, 0); assert.deepEqual(groupProjectsByClient(null, "").length, 0); assert.deepEqual(groupProjectsByClient([{ client: "x" }], "").length, 0);
  assert.strictEqual(groupProjectsByClient(PJ, "abatik")[0].projects.length, 2, "filtrer un client garde tous ses projets");
  const gp = groupProjectsByClient(PJ, "infra"); assert.deepEqual(gp.map(x => x.client), ["abatik", "calicote"]); assert.deepEqual(gp[1].projects.map(p => p.project), ["infra"]);
  assert.strictEqual(groupProjectsByClient(PJ, "CALICOTE").length, 1); assert.strictEqual(groupProjectsByClient(PJ, "zzz").length, 0);
  const sess = [{ rm_id: "1", client: "abatik", project: "infra" }, { rm_id: "2", client: "abatik", project: "infra" }, { rm_id: "3", ghost: true, client: "abatik", project: "infra" }, { rm_id: "4" }, { rm_id: "5" }];
  assert.deepEqual(liveByProject(sess, { "4": { found: true, client: "calicote", project: "infra" } }), { "abatik/infra": 2, "calicote/infra": 1 }, "un ghost n'est pas compté");
  assert.deepEqual(liveByProject(null, null), {});
  console.log("✓ modèle (RM2760) : groupement, filtre client/projet, sessions vivantes");

  const mk = (ctx) => new ProjectsPanelViewModel({ projects: PJ }, ctx || {});
  assert.strictEqual(mk().count, "4"); assert.strictEqual(mk({ filtre: "infra" }).count, "2 / 4"); assert.strictEqual(new ProjectsPanelViewModel({ projects: [] }, {}).count, "");
  const cs = mk({ client: "abatik", sessions: sess, resolve: {} }).clients();
  assert.strictEqual(cs[0].ouvert, true); assert.strictEqual(cs[0].isCtx, true); assert.strictEqual(cs[0].nLive, 2); assert.strictEqual(cs[1].ouvert, false);
  assert(mk({ filtre: "infra" }).clients().every(c => c.ouvert), "sous filtre, tout est déplié");
  assert.strictEqual(mk({ open: { calicote: true } }).clients()[1].ouvert, true);
  console.log("✓ ViewModel : compteur, dépliage (contexte, main, filtre), sessions par projet");

  const hAll = String(ProjectsList(mk()));
  assert(hAll.includes("▸ abatik") && !/data-action="project" data-value="abatik\/infra"/.test(hAll), "replié par défaut, projets non rendus");
  const hCtx = String(ProjectsList(mk({ client: "abatik" })));
  assert(hCtx.includes("▾ abatik") && /data-action="project" data-value="abatik\/infra"/.test(hCtx) && hCtx.includes("ctx") && hCtx.includes("▸ calicote"));
  assert(/data-value="calicote\/infra"/.test(String(ProjectsList(mk({ filtre: "infra" })))));
  assert(/data-value="calicote\/prestashop"/.test(String(ProjectsList(mk({ open: { calicote: true } })))));
  assert(String(ProjectsList(mk({ client: "abatik", sessions: sess.slice(0, 3) }))).includes("2 ▶"));
  assert(/data-action="conf" data-scope="project" data-client="abatik" data-project="infra"/.test(hCtx) && /data-action="client" data-client="abatik"/.test(hCtx));
  assert(!/onclick=/.test(hCtx), "zéro handler inline");
  assert(String(ProjectsList(new ProjectsPanelViewModel({ projects: [] }, { filtre: "zz" }))).includes("aucun client ni projet ne correspond"));
  assert(String(ProjectsList(new ProjectsPanelViewModel({ projects: [] }, {}))).includes("aucun projet"));
  assert(/<b>épinglé<\/b>/.test(String(ProjectsList(mk({ client: "abatik", pin: () => "<b>épinglé</b>" })))), "la marque d'épinglage prêtée est rendue telle quelle");
  assert(!/<img/.test(String(ProjectsList(new ProjectsPanelViewModel({ projects: [{ client: "<img src=x>", project: "p" }] }, { filtre: "p" })))), "client échappé");
  assert(/chargement…/.test(String(ProjectsPanel(null))) && /value="inf"/.test(String(ProjectsPanel(mk({ filtre: "inf" })))));
  // RM2768 : les icônes, sans effet de bord sur le pliage — la ligne du client EST le
  // bouton de pliage ; c'est le contrôleur qui stoppe la propagation, pour tout geste.
  assert(/data-action="client" data-client="abatik"/.test(hCtx) && /data-scope="client" data-client="abatik" data-project=""/.test(hCtx));
  assert(/data-action="conf" data-scope="project" data-client="abatik" data-project="infra"/.test(hCtx));
  // RM2795 : sans fonction de marque, rendu inchangé ; avec, le projet épinglé la porte
  assert(!/📌/.test(hCtx), "sans fonction de marque, le rendu est inchangé (rétrocompat)");
  assert(/📌/.test(String(ProjectsList(mk({ client: "abatik", pin: (k, v) => (k === "project" && v === "abatik/infra" ? " 📌" : "") })))));
  console.log("✓ vues (RM2760/2768/2795) : replié/déplié, sessions, icônes, épinglage, échappement");

  const el = fakeElement(); const ev = [];
  const h = mountProjectsPanel(el, { service: { async all() { ev.push("all"); return PJ; } }, sessions: () => sess, resolve: () => ({}), clientContext: () => "abatik",
    openProject: v => ev.push(["project", v]), openClient: c => ev.push(["client", c]), openConf: (s, c, p) => ev.push(["conf", s, c, p]), help: k => ev.push(["help", k]) });
  assert(/chargement…/.test(el.innerHTML)); await h.refresh(); assert.strictEqual(ev.pop(), "all"); assert(/▾ abatik/.test(el.innerHTML));
  await el.click("toggle", { client: "calicote" }); assert(/▾ calicote/.test(el.innerHTML)); await el.click("toggle", { client: "calicote" }); assert(/▸ calicote/.test(el.innerHTML));
  await el.input("presta"); assert.strictEqual(h.state.filtre, "presta"); assert(/1 \/ 4/.test(el.innerHTML) && /▾ calicote/.test(el.innerHTML), "filtre : compteur et dépliage");
  await el.click("clear"); assert.strictEqual(h.state.filtre, ""); assert(/>4</.test(el.innerHTML));
  await el.click("project", { value: "abatik/infra" }); assert.deepEqual(ev.pop(), ["project", "abatik/infra"]);
  await el.click("conf", { scope: "client", client: "abatik", project: "" }); assert.deepEqual(ev.pop(), ["conf", "client", "abatik", ""]);
  await el.click("client", { client: "abatik" }); assert.deepEqual(ev.pop(), ["client", "abatik"]);
  let stopped = 0; const n = { dataset: { action: "conf", scope: "project", client: "abatik", project: "infra" } };
  for (const [t, f] of el._L) if (t === "click") await f({ target: { closest: s => s === "[data-action]" ? n : null }, stopPropagation() { stopped++; } });
  assert.strictEqual(stopped, 1, "une icône stoppe la propagation — sinon elle replie le client");
  h.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur : chargement, pliage, filtre, ouvertures au centre, démontage");
  console.log("\nTous les tests du panneau projets passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
