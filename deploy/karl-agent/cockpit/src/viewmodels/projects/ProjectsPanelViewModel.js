// viewmodels/projects/ProjectsPanelViewModel — le panneau « projets », décidé. RM2889, L4.
// Ce que projectsPanelHtml et renderProjectsPanel décidaient : groupes filtrés,
// compteur, clients dépliés (contexte, main, ou tout sous filtre), sessions vivantes.
import { EntityViewModel } from "../EntityViewModel.js";
import { groupProjectsByClient, liveByProject } from "../../models/projects/projectGroups.js";

export class ProjectsPanelViewModel extends EntityViewModel {
  /** e = { projects } ; ctx = { filtre, open, sessions, resolve, client, pin } */
  get filtre() { return String(this.ctx.filtre || ""); }
  get groups() { return this._g || (this._g = groupProjectsByClient(this.e.projects, this.filtre)); }
  get live()   { return this._l || (this._l = liveByProject(this.ctx.sessions, this.ctx.resolve)); }
  get total()  { return (this.e.projects || []).length; }
  get shown()  { return this.groups.reduce((a, g) => a + g.projects.length, 0); }
  get count()  { return this.total ? (this.filtre.trim() ? this.shown + " / " + this.total : String(this.shown)) : ""; }
  get depliéTout() { return !!this.filtre.trim(); }
  get emptyText() { return this.depliéTout ? "aucun client ni projet ne correspond" : "aucun projet"; }
  clients() {
    const open = this.ctx.open || {}, ctx = this.ctx.client || "";
    return this.groups.map(g => ({
      client: g.client, isCtx: g.client === ctx,
      ouvert: this.depliéTout || !!open[g.client] || g.client === ctx,
      nLive: g.projects.reduce((n, p) => n + (this.live[p.value] || 0), 0),
      projects: g.projects.map(p => ({ ...p, n: this.live[p.value] || 0, pin: this.ctx.pin ? this.ctx.pin("project", p.value) : "" })),
    }));
  }
}
