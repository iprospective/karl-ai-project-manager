// controllers/project.controller — la surface « fiche projet » du centre. RM2889.
// Deuxième surface enregistrée auprès du routeur. Le contexte prête : les sessions
// du groupe, l'attache, la fiche ticket, l'ouverture d'un doc, le lien de titre,
// la ligne de MR, le rendu de fichier, le runner PM, le panneau fichiers de droite.
import { mount } from "../core/dom.js";
import { html } from "../core/html.js";
import { ProjectService } from "../services/project.service.js";
import { ProjectSheetViewModel, ProjectWorklogViewModel, ProjectFilesViewModel, ProjectConfigViewModel } from "../viewmodels/projects/ProjectViewModels.js";
import { ProjectSheet, ProjectHeader, ProjectWorklog, ProjectFiles, ConfigForm, SessionPills } from "../views/projects/ProjectPane.view.js";
import { configArgs } from "../models/projects/projectConfig.js";

export function mountProject(el, ctx = {}) {
  const svc = ctx.service || new ProjectService(undefined, ctx.run);
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const confirm = ctx.confirm || ((m) => window.confirm(m));
  const state = { key: null, data: null, tab: "fiche", group: null, wts: [], files: { wt: null, path: "", entries: [], file: null } };
  const q = (sel) => (handle.el.querySelector ? handle.el.querySelector(sel) : null);
  const titleLink = ctx.titleLink || ((rm, t) => String(t || ""));
  const mrLine = ctx.mrLine || (() => "");
  const fileBody = ctx.fileBody || (() => "");

  const sheetVM = () => new ProjectSheetViewModel(state.data, { key: state.key, tab: state.tab, sessions: ctx.sessions ? ctx.sessions(state.key) : [], ago: ctx.ago });
  const filesFrag = () => ProjectFiles(new ProjectFilesViewModel({ worktrees: state.wts, ...state.files }), fileBody);
  function paint() {
    if (!state.data) return;
    if (state.tab === "worklog") { handle.update(html`${ProjectHeader(sheetVM())}<div id="projworklog">${state.group === undefined ? html`<div class="empty">chargement du worklog projet…</div>` : ProjectWorklog(new ProjectWorklogViewModel(state.group), mrLine)}</div>`); return; }
    handle.update(ProjectSheet(sheetVM(), titleLink, filesFrag()));
  }

  async function open(key) {
    if (ctx.center) ctx.center.yield("project");
    state.key = key; state.data = null; state.group = undefined; state.wts = []; state.files = { wt: null, path: "", entries: [], file: null };
    if (ctx.show) ctx.show(true);
    handle.update(html`<div class="empty">chargement de la fiche projet…</div>`);
    if (ctx.center) { ctx.center.note("project", key, key); ctx.center.title(); }
    if (ctx.filesEnsure) ctx.filesEnsure();                    // RM2673 : le panneau suit le projet ouvert
    const [c, p] = String(key).split("/");
    if (!c || !p || key === "divers") { handle.update(html`<div class="empty">groupe « divers » — sessions non rattachées à un projet PM.</div>${SessionPills(sheetVM())}`); return; }
    try { const d = await svc.sheet(key); if (state.key !== key) return; state.data = d; paint(); if (state.tab === "worklog") refreshWorklog(); else loadWorktrees(key); }
    catch (e) { if (state.key === key) handle.update(html`<div class="empty">fiche projet indisponible : ${e.message}</div>${SessionPills(sheetVM())}`); }
  }
  function close() { state.key = null; state.data = null; if (ctx.show) ctx.show(false); if (ctx.center) { ctx.center.fallback(); ctx.center.title(); } }
  const current = () => state.key;
  async function refreshWorklog() { const key = state.key; if (!key) return; try { const g = await svc.worklog(key); if (state.key === key) { state.group = g; if (state.tab === "worklog") paint(); } } catch (e) { if (state.key === key && state.tab === "worklog") handle.update(html`${ProjectHeader(sheetVM())}<div class="empty">worklog projet indisponible : ${e.message}</div>`); } }
  async function loadWorktrees(key) { try { const w = await svc.worktrees(key); if (state.key === key) { state.wts = w.worktrees || []; paintFiles(); } } catch (e) { const b = q("#projfiles"); if (b) b.innerHTML = String(html`<div class="empty">${e.message}</div>`); } }
  const paintFiles = () => { const b = q("#projfiles"); if (b) b.innerHTML = String(filesFrag()); };
  async function browse(wt, path) { state.files = { ...state.files, wt, path, file: null }; const r = await svc.browse(state.key, wt, path); state.files.entries = r.entries; if (r.error) notify(r.error, true); paintFiles(); }
  async function openFile(name) { const sp = state.files.path ? state.files.path + "/" + name : name; const r = await svc.open(state.key, state.files.wt, sp); if (r.error) { notify(r.error, true); return; } state.files.file = r.file; paintFiles(); }
  function openConfig(scope) { if (!state.data || !state.key) return; handle.update(ConfigForm(new ProjectConfigViewModel(state.data, { scope, key: state.key }))); }
  async function onSave(scope, btn) {
    const fields = {}; for (const n of handle.el.querySelectorAll ? handle.el.querySelectorAll("[data-cfg]") : []) fields[n.dataset.cfg] = n.value;
    if (!configArgs(scope, state.key, fields)) { notify("Aucun champ à modifier", true); return; }
    if (!confirm("Modifier la conf " + (scope === "project" ? "du projet" : "du client") + " (écrit meta.yml) ?")) return;
    btn.disabled = true;
    const r = await svc.saveConfig(scope, state.key, fields);
    notify(r.message, !r.ok);
    if (r.ok) open(state.key); else btn.disabled = false;
  }
  const gestures = { "merge-one": (n) => ctx.mergeMr && ctx.mergeMr(n.dataset.url, n.dataset.iid, n.dataset.target, n),
    close: () => close(), tab: (n) => { state.tab = n.dataset.tab === "worklog" ? "worklog" : "fiche"; paint(); if (state.tab === "worklog") refreshWorklog(); else loadWorktrees(state.key); },
    conf: (n) => openConfig(n.dataset.scope), attach: (n) => ctx.attach && ctx.attach(n.dataset.sid), ticket: (n) => ctx.showTicket && ctx.showTicket(n.dataset.rm),
    doc: (n) => ctx.openDoc && ctx.openDoc(n.dataset.path, n.dataset.name),
    wt: (n) => browse(n.dataset.path, ""), browse: (n) => browse(state.files.wt, n.dataset.path || ""), wts: () => { state.files = { wt: null, path: "", entries: [], file: null }; paintFiles(); },
    open: (n) => openFile(n.dataset.name), save: (n) => onSave(n.dataset.scope, n), cancel: () => open(state.key),
  };
  const handle = mount(el, "", { events: [["click", "[data-action]", (ev, n) => { const g = gestures[n.dataset.action]; if (!g) return; if (ev.preventDefault) ev.preventDefault(); return g(n); }]] });
  return Object.assign(handle, { open, close, current, refreshWorklog, state, titleHtml: () => state.key ? String(html`📁 <span class="tid">${state.key}</span><span class="ttitle">fiche projet</span>`) : "" });
}
