// controllers/projects.controller — le panneau « projets » : trois gestes. RM2889, L4.
// Le monolithe prête : les sessions et leur cache de résolution, le client du
// contexte, la marque d'épinglage, et les trois ouvertures au centre.
import { mount } from "../core/dom.js";
import { ProjectsService } from "../services/projects.service.js";
import { ProjectsPanelViewModel } from "../viewmodels/projects/ProjectsPanelViewModel.js";
import { ProjectsPanel } from "../views/projects/ProjectsPanel.view.js";

export function mountProjectsPanel(el, ctx = {}) {
  const svc = ctx.service || new ProjectsService();
  const state = { filtre: "", open: {}, projects: null };

  function render() {
    if (!state.projects) return handle.update(ProjectsPanel(null));
    const vm = new ProjectsPanelViewModel({ projects: state.projects }, {
      filtre: state.filtre, open: state.open, client: ctx.clientContext ? ctx.clientContext() : "",
      sessions: ctx.sessions ? ctx.sessions() : [], resolve: ctx.resolve ? ctx.resolve() : {}, pin: ctx.pin });
    // repeindre remplace l'input : on garde le curseur au bout du filtre en cours de frappe
    handle.update(ProjectsPanel(vm));
    const f = handle.el.querySelector && handle.el.querySelector("#pj-filter");
    if (f && f.focus && state.typing) { f.focus(); if (f.setSelectionRange) f.setSelectionRange(f.value.length, f.value.length); }
  }
  async function refresh() {
    try { state.projects = await svc.all(); } catch (e) { state.projects = []; if (ctx.notify) ctx.notify(e.message, true); }
    render();
  }
  const gestures = {
    help: () => ctx.help && ctx.help("projets"),
    clear: () => { state.filtre = ""; state.typing = false; render(); },
    toggle: (n) => { state.open[n.dataset.client] = !state.open[n.dataset.client]; render(); },
    client: (n) => ctx.openClient && ctx.openClient(n.dataset.client),
    conf: (n) => ctx.openConf && ctx.openConf(n.dataset.scope, n.dataset.client, n.dataset.project || ""),
    project: (n) => ctx.openProject && ctx.openProject(n.dataset.value),
  };
  const handle = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => { const g = gestures[n.dataset.action]; if (g) { if (ev.stopPropagation) ev.stopPropagation(); return g(n); } }],
    ["input", "#pj-filter", (ev, f) => { state.filtre = f.value || ""; state.typing = true; render(); }],
  ] });
  render();
  return Object.assign(handle, { refresh, render, state });
}
