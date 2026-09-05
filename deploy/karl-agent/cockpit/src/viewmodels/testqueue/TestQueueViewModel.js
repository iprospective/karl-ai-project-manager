// viewmodels/testqueue/TestQueueViewModel — ce que le panneau « à tester » montre. RM2889.
import { EntityViewModel } from "../EntityViewModel.js";
import { filterQueue, sortQueue, projectsOf, envActions, envLink, projectKey } from "../../models/testqueue/testQueue.js";
export class TestQueueViewModel extends EntityViewModel {
  /** e = { all, loaded } ; ctx = { filters: {project,status,deployable,q,sort}, pin } */
  constructor(e, ctx) { super(e || { all: [] }, ctx); }
  get f() { return this.ctx.filters || {}; }
  get all() { return this.e.all || []; }
  get shown() { return this._s || (this._s = sortQueue(filterQueue(this.all, this.f), this.f.sort || "oldest")); }
  get count() { const n = this.shown.length, t = this.all.length; return n ? "(" + n + (n !== t ? "/" + t : "") + ")" : ""; }
  get projects() { return projectsOf(this.all); }
  get emptyText() { return this.all.length ? "aucun résultat avec ces filtres" : "rien à tester 🎉"; }
  items() { return this.shown.map(e => ({ rm: String(e.rm_id), title: e.title || "", dem: e.status === "a_tester_demandeur", project: projectKey(e), branch: e.branch || "", link: envLink(e), actions: envActions(e), pin: this.ctx.pin ? this.ctx.pin("review", e.rm_id) : "" })); }
}
