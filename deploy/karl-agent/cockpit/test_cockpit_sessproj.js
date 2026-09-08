#!/usr/bin/env node
// Tests de l'onglet 📂 projets de la colonne de droite (RM3045) : ViewModel (raccourcis, CDC, états vides), vue sans on*, contrôleur (session
// attachée, rechargement par sid, gestes vers la fiche / les fichiers / les pages CDC), et l'onglet présent dans la barre ET dans TABS.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));
function fakeEl(id) { const L = []; let inner = ""; const self = { id, style: {}, textContent: "", kids: {}, get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, querySelector() { return null; }, querySelectorAll() { return []; }, replaceChildren(...n) { inner = n.map(x => x.outerHTML || x.textContent || "").join(""); }, addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await settle(); } }; return self; }
(async () => {
  const VM = await import(path.join(DIR, "src/modules/sessproj/SessProjViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/sessproj/SessProj.view.js"));
  const { mountSessProj } = await import(path.join(DIR, "src/modules/sessproj/sessproj.controller.js"));
  const P = await import(path.join(DIR, "src/modules/layout/panels.js"));
  const projects = [
    { client: "i", project: "pm", name: "ai-project-management", root: "/w/pm", branch: "3044-x", dirty: 2, docs: [{ path: "doc:i/pm/docs" }, { path: "doc:i/pm/project" }], cdcs: [{ key: "i/pm/pm", prefix: "pm", title: "CDC PM", path: "p/cdc-pm-00-sommaire.md", registry: true }, { key: "i/pm/karl", prefix: "karl", title: "CDC karl", path: "p/cdc-karl-00-sommaire.md", registry: false }] },
    { client: "a", project: "site", name: "site", root: "/w/site", branch: "main", docs: [], cdcs: [] },
  ];
  let vm = new VM.SessProjViewModel({ projects, attached: true }); const rows = vm.rows();
  assert(rows.length === 2 && rows[0].key === "i/pm" && rows[0].overview === "projects/clients/i/projects/pm/project/overview.md" && rows[0].docs === 2 && rows[0].cdcs.length === 2 && rows[0].cdcs[1].registry === false && rows[1].cdcs.length === 0, "lignes : clé, fiche, racines doc, CDC (registre ou non)");
  assert(/attache une session/.test(new VM.SessProjViewModel({ projects: [], attached: false }).emptyText) && /aucun projet PM/.test(new VM.SessProjViewModel({ projects: [], attached: true }).emptyText) && /injoignables/.test(new VM.SessProjViewModel({ error: "boom" }).emptyText), "états vides explicites");
  const s = String(V.SessProjPanel(vm)); assert(!/\son\w+=/.test(s), "aucun on*"); assert(/data-action="overview" data-path="projects\/clients\/i\/projects\/pm\/project\/overview.md"/.test(s) && /data-action="cdc" data-key="i\/pm\/pm" data-page="cdc-features"/.test(s) && /data-action="cdc" data-key="i\/pm\/karl" data-page="cdc-features" disabled/.test(s) && /pas de CDC vivant/.test(s) && /3044-x/.test(s), "gestes : fiche, CDC (désactivé sans registre), invitation, branche");
  console.log("✓ projets (RM3045) : ViewModel et vue");
  const el = fakeEl("rp-projects"); const calls = []; let sid = null; let n = 0;
  const ctl = mountSessProj(el, { attached: () => sid, repo: { worktrees: async (s2) => { n++; return { projects: s2 === "s1" ? projects : [] }; } }, openDoc: (p, nm) => calls.push("doc:" + nm), showFiles: (r) => calls.push("files:" + r), openCdc: (k, pg) => calls.push("cdc:" + k + ":" + pg) });
  assert(/attache une session/.test(el.innerHTML), "sans session : invitation");
  sid = "s1"; await ctl.refresh(); assert(/ai-project-management/.test(el.innerHTML) && ctl.keys().join(",") === "i/pm,a/site" && n === 1, "session attachée : projets chargés, clés exposées");
  await ctl.refresh(); assert(n === 1, "même sid : pas de rechargement"); await ctl.refresh(true); assert(n === 2, "force : recharge");
  await el.click("overview", { path: "x", name: "pm" }); await el.click("files", { root: "/w/pm" }); await el.click("cdc", { key: "i/pm/pm", page: "cdc-roadmap" });
  assert.deepStrictEqual(calls, ["doc:pm", "files:/w/pm", "cdc:i/pm/pm:cdc-roadmap"], "gestes routés");
  sid = "s2"; await ctl.refresh(); assert(/aucun projet PM/.test(el.innerHTML), "autre session sans projet"); sid = null; await ctl.refresh(); assert(ctl.keys().length === 0);
  ctl.unmount();
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  assert(/data-rpanel="projects"/.test(html) && /id="rp-projects"/.test(html) && P.TABS.includes("projects"), "l'onglet est dans la barre, son hôte existe, et il est dans TABS (incident RM2579)");
  assert.strictEqual(P.rightPanelReduce({ tab: "infos", collapsed: false }, { type: "select", tab: "projects" }).tab, "projects", "sélectionnable");
  console.log("✓ projets (RM3045) : contrôleur et câblage");
  console.log("\nL'onglet projets passe.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
