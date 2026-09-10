#!/usr/bin/env node
// Tests de la surface « fiche projet » migrée (RM2889) — porte RM2531 (configArgs), RM2696 (worklog projet),
// et le rendu de la fiche / des fichiers que le harnais runtime vérifiait.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fakeElement() { const L = []; let inner = ""; const sub = {}; return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, sub,
  querySelector(sel) { if (sel === "#projfiles") return sub.files || (sub.files = { innerHTML: "" }); return null; }, querySelectorAll(sel) { return sel === "[data-cfg]" ? Object.values(sub.cfg || {}) : []; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async click(action, data) { const n = { dataset: { action, ...(data || {}) }, disabled: false }; for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => s === "[data-action]" ? n : null }, preventDefault() {} }); return n; } }; }
(async () => {
  const { configArgs, configPrefill, crumbs } = await import(path.join(DIR, "src/modules/projects/projectConfig.js"));
  const VM = await import(path.join(DIR, "src/modules/projects/ProjectViewModels.js"));
  const V = await import(path.join(DIR, "src/modules/projects/ProjectPane.view.js"));
  const { mountProject } = await import(path.join(DIR, "src/modules/projects/project.controller.js"));
  // — RM2531 —
  assert.deepStrictEqual(configArgs("project", "iprospective/pm-ai-agents", { name: "Nouveau", redmine: "pm-ai-agents", repo: "", branch: "  " }), { client: "iprospective", project: "pm-ai-agents", name: "Nouveau", redmine_project_id: "pm-ai-agents" });
  assert.deepStrictEqual(configArgs("project", "c/p", { name: "", redmine: "", repo: "g/r", branch: "dev" }), { client: "c", project: "p", gitlab_repo: "g/r", default_branch: "dev" });
  assert.deepStrictEqual(configArgs("client", "acme/shop", { name: "Acme", redmine: "acme-parent", repo: "x/y", branch: "main" }), { client: "acme", name: "Acme", redmine_project_id: "acme-parent" });
  assert.strictEqual(configArgs("project", "c/p", { name: "", redmine: "", repo: "", branch: "" }), null); assert.strictEqual(configArgs("client", "c/p", {}), null);
  assert.deepStrictEqual(configPrefill("client", { client_name: "Acme", client_redmine_project_id: "acme" }), { name: "Acme", redmine: "acme" });
  assert.deepStrictEqual(crumbs("a/b").map(c => c.path), ["", "a", "a/b"]);
  const cf = String(V.ConfigForm(new VM.ProjectConfigViewModel({ name: "N", redmine_project_id: "r", gitlab_repo: "g/r", default_branch: "dev" }, { scope: "project", key: "c/p" })));
  assert(/✎ Conf projet — c\/p/.test(cf) && /data-cfg="repo"[^>]*value="g\/r"/.test(cf) && /data-action="save" data-scope="project"/.test(cf) && !/onclick=/.test(cf));
  assert(!/data-cfg="repo"/.test(String(V.ConfigForm(new VM.ProjectConfigViewModel({}, { scope: "client", key: "c/p" })))), "la conf client n'a ni repo ni branche");
  console.log("✓ conf projet/client (RM2531) : args, préremplissage, formulaire");
  // — RM2696 —
  const mrLine = (m) => '<div class="mr">!' + esc(m.iid) + (m.alive === false ? " (session éteinte)" : "") + "</div>";
  const wl = (g) => String(V.ProjectWorklog(new VM.ProjectWorklogViewModel(g), mrLine));
  assert(/rien en cours sur ce projet/.test(wl(null)));
  const GRP = { key: "acme/shop", counts: { sessions_live: 1, sessions: 2, active: 2, waiting: 1, orphans: 1, mrs: 1, requests: 1 },
    tickets: [{ rm_id: "11", status: "en_cours", title: "orphelin", bucket: "active", sessions: [], has_live_session: false }, { rm_id: "10", status: "en_cours", title: "suivi", bucket: "active", sessions: ["70"], has_live_session: true, checklist: { done: 1, total: 2 } }, { rm_id: "12", status: "a_tester_demandeur", title: "en attente", bucket: "waiting", sessions: ["71"], has_live_session: false }],
    mrs: [{ iid: "9", ref: "RM12", target: "dev", url: "https://x/9", alive: false }], requests: [{ text: "une demande" }], sessions: [{ sid: "70", alive: true, title: "T" }, { sid: "71", alive: false, title: "U" }] };
  const pw = wl(GRP);
  assert(/1 session\(s\) ouverte\(s\)/.test(pw) && /2 en cours/.test(pw) && /💤 à reprendre/.test(pw) && pw.indexOf("RM11") < pw.indexOf("RM10") && />1\/2 ✓</.test(pw));
  assert(/🔀 MR à merger \(1\)/.test(pw) && /!9/.test(pw) && /session éteinte/.test(pw) && /📥 demandes non ticketées \(1\)/.test(pw) && /a_tester_demandeur : 1/.test(pw));
  assert(/data-action="attach" data-sid="70"/.test(pw) && /data-action="ticket" data-rm="11"/.test(pw) && !/onclick=/.test(pw));
  const many = { counts: {}, tickets: Array.from({ length: 33 }, (_, i) => ({ rm_id: String(200 + i), status: "a_tester_demandeur", title: "t", bucket: "waiting", sessions: [], has_live_session: false })), mrs: [], requests: [], sessions: [] };
  const pwMany = wl(many); assert.strictEqual((pwMany.match(/class="r-id"/g) || []).length, 20); assert(/… et 13 autre\(s\)/.test(pwMany));
  const pwXss = wl({ counts: {}, tickets: [{ rm_id: "1", status: "<b>s", title: "<img src=x>", bucket: "active", sessions: ["<b>"], has_live_session: false }], mrs: [], requests: [{ text: "<script>" }], sessions: [] });
  assert(!/<img/.test(pwXss) && !/<script>/.test(pwXss) && /&lt;img/.test(pwXss));
  console.log("✓ worklog projet (RM2696) : orphelins en tête, MR pendantes, attentes comptées, plafond annoncé");
  // — fiche et fichiers (ex-runtime) —
  const sheet = String(V.ProjectSheet(new VM.ProjectSheetViewModel({ name: "Appli", total: 3, docs: [{ path: "/pm/x.md", name: "x.md" }], open_by_status: { en_cours: 1 }, open_recent: [{ rm_id: "5", status: "en_cours", title: "T5", mtime: 1 }], closed_recent: [], environments: [{ name: "prod", url: "https://p" }], redmine_project_url: "https://r" },
    { key: "acme/appli", tab: "fiche", sessions: [{ rm_id: "42", state: "working" }], ago: () => "il y a 2 min" }), (rm, t) => "<i>" + esc(t) + "</i>", '<div class="empty">chargement…</div>'));
  assert(/📁 acme\/appli/.test(sheet) && /data-action="doc" data-path="\/pm\/x.md"/.test(sheet) && /en_cours : 1/.test(sheet) && /RM5/.test(sheet) && /<i>T5<\/i>/.test(sheet) && /il y a 2 min/.test(sheet));
  assert(/data-action="attach" data-sid="42"/.test(sheet) && /https:\/\/p ↗/.test(sheet) && /3 tickets/.test(sheet) && /data-action="conf" data-scope="client"/.test(sheet) && /id="projfiles"/.test(sheet) && !/onclick=/.test(sheet));
  const files = (e) => String(V.ProjectFiles(new VM.ProjectFilesViewModel(e), (f) => "<pre>" + esc(f.content) + "</pre>"));
  assert(/aucun worktree/.test(files({ worktrees: [] })));
  const WT = [{ path: "/w/appli", name: "appli", exists: true, is_git: true, branch: "dev", clean: false, dirty: 3 }, { path: "/w/gone", name: "gone", exists: false }];
  assert(/data-action="wt" data-path="\/w\/appli"/.test(files({ worktrees: WT })) && /3 modifs/.test(files({ worktrees: WT })) && !/gone/.test(files({ worktrees: WT })));
  const dir = files({ worktrees: WT, wt: "/w/appli", path: "docs", entries: [{ name: "x.md", dir: false }, { name: "sub", dir: true }] });
  assert(/data-action="wts"/.test(dir) && /data-action="browse" data-path=""/.test(dir) && /data-action="open" data-name="x.md"/.test(dir) && /data-action="browse" data-path="docs\/sub"/.test(dir));
  assert(/<pre>hello<\/pre>/.test(files({ worktrees: WT, wt: "/w/appli", path: "docs", entries: [], file: { name: "x.md", content: "hello" } })), "le fichier passe par le rendu commun");
  console.log("✓ fiche projet et fichiers : docs, tickets, sessions, worktrees, navigation, rendu commun");
  // — contrôleur —
  const el = fakeElement(); const ev = []; const runs = [];
  const svc = { async sheet(k) { ev.push(["sheet", k]); return { name: "Appli", total: 1, docs: [], open_by_status: {}, open_recent: [], closed_recent: [], environments: [] }; },
    async worktrees() { return { worktrees: WT }; }, async worklog(k) { ev.push(["worklog", k]); return GRP; },
    async browse(k, wt, p) { ev.push(["browse", wt, p]); return { entries: [{ name: "a.md", dir: false }] }; }, async open(k, wt, p) { return { file: { name: p, content: "c" } }; },
    async saveConfig(scope, key, fields) { runs.push([scope, key, fields]); return { ok: true, message: "✓ conf enregistrée" }; } };
  const center = { yield: (k) => ev.push(["yield", k]), note: (...a) => ev.push(["note", ...a]), title: () => {}, fallback: () => ev.push("fallback") };
  const pr = mountProject(el, { service: svc, center, notify: (m, e) => ev.push(["toast", m, !!e]), confirm: () => true, show: (on) => ev.push(["show", on]), sessions: () => [{ rm_id: "42" }], attach: (s) => ev.push(["attach", s]), showTicket: (rm) => ev.push(["ticket", rm]), openDoc: (p, n) => ev.push(["doc", p, n]), titleLink: (rm, t) => t, ago: () => "", mrLine: mrLine, fileBody: (f) => f.content, filesEnsure: () => ev.push("filesEnsure") });
  await pr.open("acme/appli"); assert.deepStrictEqual(ev.slice(0, 4), [["yield", "project"], ["show", true], ["note", "project", "acme/appli", "acme/appli"], "filesEnsure"]); assert.strictEqual(pr.current(), "acme/appli"); assert(/📁 acme\/appli/.test(el.innerHTML));
  await new Promise(r => setTimeout(r, 0)); assert(/data-action="wt" data-path="\/w\/appli"/.test(el.sub.files.innerHTML), "les worktrees arrivent dans #projfiles : " + el.sub.files.innerHTML);
  await el.click("wt", { path: "/w/appli" }); assert.deepStrictEqual(ev.pop(), ["browse", "/w/appli", ""]); assert(/a\.md/.test(el.sub.files.innerHTML));
  await el.click("open", { name: "a.md" }); assert(/‹ retour/.test(el.sub.files.innerHTML) && /c$/.test(el.sub.files.innerHTML.replace(/<[^>]+>/g, "").trim()));
  await el.click("tab", { tab: "worklog" }); assert(/💤 à reprendre|chargement du worklog/.test(el.innerHTML)); await new Promise(r => setTimeout(r, 0)); assert(/🔀 MR à merger/.test(el.innerHTML), "le worklog projet est rendu sous l'en-tête");
  await el.click("attach", { sid: "70" }); assert.deepStrictEqual(ev.pop(), ["attach", "70"]); await el.click("ticket", { rm: "11" }); assert.deepStrictEqual(ev.pop(), ["ticket", "11"]);
  await el.click("tab", { tab: "fiche" }); await el.click("conf", { scope: "project" }); assert(/✎ Conf projet — acme\/appli/.test(el.innerHTML) && /data-cfg="name"[^>]*value="Appli"/.test(el.innerHTML), "formulaire prérempli depuis la fiche");
  el.sub.cfg = { n: { dataset: { cfg: "name" }, value: "" }, r: { dataset: { cfg: "redmine" }, value: "" } }; await el.click("save", { scope: "project" }); assert.deepStrictEqual(ev.pop(), ["toast", "Aucun champ à modifier", true]); assert.strictEqual(runs.length, 0);
  el.sub.cfg.n.value = "Nouveau"; await el.click("save", { scope: "project" }); assert.deepStrictEqual(runs.pop(), ["project", "acme/appli", { name: "Nouveau", redmine: "" }]); assert(ev.some(x => x[0] === "toast" && x[1] === "✓ conf enregistrée"));
  assert(/📁 <span class="tid">acme\/appli<\/span>/.test(pr.titleHtml())); pr.close(); assert.strictEqual(pr.current(), null); assert(ev.includes("fallback") && ev.some(x => x[0] === "show" && x[1] === false));
  await pr.open("divers"); assert(/groupe « divers »/.test(el.innerHTML) && /data-sid="42"/.test(el.innerHTML), "« divers » : message + sessions du groupe");
  pr.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur fiche projet : ouverture, worktrees, navigation, worklog, conf, divers, démontage");
  console.log("\nTous les tests de la fiche projet passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
