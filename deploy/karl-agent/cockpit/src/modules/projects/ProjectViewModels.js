// viewmodels/projects — fiche, worklog projet, fichiers, conf. RM2889. Inertes.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { configPrefill, crumbs } from "./projectConfig.js";

export class ProjectSheetViewModel extends EntityViewModel {
  /** e = fiche ; ctx = { key, tab, sessions: [..], ago } */
  constructor(e, ctx) { super(e || {}, ctx); }
  get key() { return this.ctx.key || ""; }
  get clientKey() { return this.key.split("/")[0]; }
  get tab() { return this.ctx.tab === "worklog" ? "worklog" : "fiche"; }
  get links() { const d = this.e, out = []; if (d.redmine_project_url) out.push({ kind: "a", href: d.redmine_project_url, label: "🎫 Projet Redmine ↗" }); if (d.redmine_issues_url) out.push({ kind: "a", href: d.redmine_issues_url, label: "📋 Liste des tickets ↗" }); if (d.gitlab_repo) out.push({ kind: "pill", label: "🗄 " + d.gitlab_repo, title: "repo GitLab" + (d.default_branch ? " · branche " + d.default_branch : "") }); out.push({ kind: "pill", label: (d.total == null ? "?" : d.total) + " tickets" }); return out; }
  sessions() { return (this.ctx.sessions || []).map(s => ({ sid: String(s.rm_id), state: s.state || "idle", label: s.is_ticket === false ? String(s.rm_id) : "RM" + s.rm_id })); }
  get environments() { return this.e.environments || []; }
  get docs() { return this.e.docs || []; }
  get byStatus() { const bs = this.e.open_by_status || {}; return Object.keys(bs).sort().map(st => ({ status: st, n: bs[st] })); }
  row(t) { return { rm_id: String(t.rm_id), status: t.status || "?", title: t.title || "", when: t.mtime && this.ctx.ago ? this.ctx.ago(t.mtime) : "" }; }
  get openRecent() { return (this.e.open_recent || []).map(t => this.row(t)); }
  get closedRecent() { return (this.e.closed_recent || []).map(t => this.row(t)); }
}

export const WORKLOG_CAP = 20;
export class ProjectWorklogViewModel extends EntityViewModel {
  constructor(g, ctx) { super(g || { __empty: true }, ctx); this.empty = !g; }
  get counts() { const c = this.e.counts || {}; return [[c.sessions_live, "session(s) ouverte(s)", "ok"], [c.active, "en cours", ""], [c.orphans, "sans session", "warn"], [c.waiting, "en attente", ""], [c.mrs, "MR à merger", "warn"], [c.requests, "demande(s)", "warn"]].filter(([n]) => n).map(([n, txt, cls]) => ({ n, txt, cls })); }
  get mrs() { return this.e.mrs || []; }
  get requests() { return this.e.requests || []; }
  ticket(t) { const cl = t.checklist; return { rm_id: String(t.rm_id), status: t.status || "?", title: t.title || "", prog: cl && cl.total ? { done: cl.done, total: cl.total, ok: cl.done >= cl.total } : null, sessions: (t.sessions || []).map(String), cold: t.bucket === "active" && !t.has_live_session }; }
  list(bucket) { const arr = (this.e.tickets || []).filter(t => bucket === "active" ? t.bucket === "active" : t.bucket !== "active"); return { shown: arr.slice(0, WORKLOG_CAP).map(t => this.ticket(t)), more: Math.max(0, arr.length - WORKLOG_CAP), total: arr.length }; }
  get waitingByStatus() { const by = {}; (this.e.tickets || []).filter(t => t.bucket !== "active").forEach(t => { by[t.status || "?"] = (by[t.status || "?"] || 0) + 1; }); return Object.keys(by).sort().map(s => ({ status: s, n: by[s] })); }
  get sessions() { return (this.e.sessions || []).map(s => ({ sid: String(s.sid), alive: !!s.alive, title: String(s.title || s.sid) })); }
  get live() { return (this.e.counts || {}).sessions_live || 0; }
}

export class ProjectFilesViewModel extends EntityViewModel {
  /** e = { worktrees, wt, path, entries, file } */
  constructor(e, ctx) { super(e || {}, ctx); }
  get worktrees() { return (this.e.worktrees || []).filter(w => w.exists); }
  get wt() { return this.e.wt || null; }
  get current() { return this.worktrees.find(w => w.path === this.wt) || {}; }
  get crumbs() { return crumbs(this.e.path); }
  get entries() { return this.e.entries || []; }
  child(name) { return (this.e.path ? this.e.path + "/" : "") + name; }
}

export class ProjectConfigViewModel extends EntityViewModel {
  /** e = fiche ; ctx = { scope, key } */
  constructor(e, ctx) { super(e || {}, ctx); }
  get isProject() { return this.ctx.scope === "project"; }
  get title() { return "✎ Conf " + (this.isProject ? "projet" : "client") + " — " + (this.isProject ? this.ctx.key : String(this.ctx.key || "").split("/")[0]); }
  rows() { const pre = configPrefill(this.ctx.scope, this.e), out = [{ id: "cfg-name", field: "name", label: "Nom affiché", value: pre.name }, { id: "cfg-redmine", field: "redmine", label: this.isProject ? "Projet Redmine (id/slug)" : "Projet Redmine parent (id/slug)", value: pre.redmine }];
    if (this.isProject) out.push({ id: "cfg-repo", field: "repo", label: "Repo GitLab (groupe/nom)", value: pre.repo }, { id: "cfg-branch", field: "branch", label: "Branche par défaut", value: pre.branch }); return out; }
}
