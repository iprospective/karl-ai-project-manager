// modules/sessproj/sessproj.controller — l'onglet 📂 projets de la colonne de droite (RM3045) : les projets touchés par la session
// attachée, avec leurs raccourcis. Le contexte prête la session attachée, l'ouverture d'un doc au centre, l'onglet fichiers et les pages CDC.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { FilesRepository } from "../files/FilesRepository.js";
import { SessProjViewModel } from "./SessProjViewModel.js";
import { SessProjPanel } from "./SessProj.view.js";

export function mountSessProj(el, ctx = {}) {
  const repo = ctx.repo || new FilesRepository();
  const attached = () => { const a = ctx.attached ? ctx.attached() : null; return a == null ? null : String(a); };
  const state = { sid: null, projects: [], error: null, loading: false };
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)]] });
  const paint = () => { h.update(SessProjPanel(new SessProjViewModel({ projects: state.projects, attached: !!state.sid, error: state.error }))); if (ctx.count) ctx.count(state.projects.length); };
  /** Charge (ou recharge) les projets de la session attachée ; sans session, l'état vide explique quoi faire. */
  async function refresh(force) {
    const sid = attached();
    if (!sid) { state.sid = null; state.projects = []; state.error = null; paint(); return; }
    if (state.sid === sid && !force && state.projects.length) { paint(); return; }
    if (state.loading) return; state.loading = true; state.sid = sid;
    try { const r = await repo.worktrees(sid); state.projects = (r && r.projects) || []; state.error = null; }
    catch (e) { state.projects = []; state.error = e.message; }
    finally { state.loading = false; }
    paint();
  }
  function reset() { state.sid = null; state.projects = []; state.error = null; paint(); }
  function onAction(ev, n) {
    const a = n.dataset.action; if (ev && ev.preventDefault) ev.preventDefault();
    if (a === "overview" && ctx.openDoc) ctx.openDoc(n.dataset.path, n.dataset.name);
    else if (a === "files" && ctx.showFiles) ctx.showFiles(n.dataset.root);
    else if (a === "cdc" && ctx.openCdc) ctx.openCdc(n.dataset.key, n.dataset.page);
  }
  /** Les projets de la session sous la forme ["client/project"] — le CDC en contexte s'en sert. */
  const keys = () => state.projects.map(p => (p.client || "") + "/" + (p.project || ""));
  paint();
  return { refresh, reset, keys, projects: () => state.projects, state, unmount() { h.unmount(); } };
}
