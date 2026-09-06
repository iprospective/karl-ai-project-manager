// models/projects/ProjectRepository — la fiche d'un projet, son worklog, ses worktrees, ses fichiers. RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";
import { routeFor } from "../../core/endpoints.js";
import { fsQuery, scopeTag } from "../files/scope.js";
const enc = encodeURIComponent;
const split = (key) => { const [c, p] = String(key || "").split("/"); return { c, p }; };

export class ProjectRepository extends Repository {
  constructor() {
    super({ name: "project", ttl: 10000, max: 20, factory: new Factory({ type: "project-sheet", defaults: { docs: [], environments: [], open_recent: [], closed_recent: [], open_by_status: {} } }),
            routes: { sheet: routeFor("/project"), worktrees: "project.project_worktrees", overview: "dashboard.overview", fsLs: routeFor("/fs/ls"), fsFile: routeFor("/fs/file") } });
  }
  async sheet(key) { const { c, p } = split(key); return this.factory.one(await get(this.path("sheet") + "/" + enc(c) + "/" + enc(p))); }
  async worktrees(key) { const { c, p } = split(key); return get(this.path("worktrees") + "/" + enc(c) + "/" + enc(p)); }
  /** Le worklog PROJET : le groupe de /overview pour ce client/projet (RM2696). */
  async overview(key) { const { c, p } = split(key); const r = await get(this.path("overview") + "?client=" + enc(c) + "&project=" + enc(p)); return (r.projects || [])[0] || null; }
  /** Portée projet seule (RM2590) : client/projet + worktree, sans session. */
  _q(key, wt) { const { c, p } = split(key); return fsQuery(wt, scopeTag({ client: c, project: p }), {}); }
  ls(key, wt, path) { return get(this.path("fsLs") + "?" + this._q(key, wt) + "&path=" + enc(path || "")); }
  file(key, wt, path) { return get(this.path("fsFile") + "?" + this._q(key, wt) + "&path=" + enc(path)); }
}
