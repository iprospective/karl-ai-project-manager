// viewmodels/projects — fiche, worklog projet, fichiers, conf. RM2889. Inertes.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { configPrefill, crumbs } from "./projectConfig.js";
import { bindEntity } from "../../core/entities.js";
import { html } from "../../core/html.js";

export class ProjectSheetViewModel extends EntityViewModel {
  /** e = fiche ; ctx = { key, tab, sessions: [..], ago } */
  constructor(e, ctx) { super(e || {}, ctx); }
  get key() { return this.ctx.key || ""; }
  get clientKey() { return this.key.split("/")[0]; }
  // RM3002 : quatre niveaux depuis sections() (core/entities) — la fiche du centre reste ProjectSheet
  get type() { return "project"; }
  get id() { return this.key; }
  get title() { return this.e.title || this.e.name || this.key || "projet"; }
  get subtitle() { return this.e.title || this.e.name ? this.key : ""; }
  get badges() { const n = this.byStatus.reduce((a, s) => a + (s.n || 0), 0); return n ? [{ text: n + " ticket(s) ouvert(s)" }] : []; }
  sections() {
    return [{ id: "links", title: "liens", summary: true, body: () => this.links.map(l => (l.kind === "a" ? html`<a href="${l.href}" target="_blank" rel="noopener">${l.label}</a>` : l.label)), empty: "aucun lien" },
            { id: "status", title: "tickets ouverts par statut", summary: true, body: () => this.byStatus.map(s => [s.status, String(s.n)]), empty: "aucun ticket ouvert" },
            { id: "environments", title: "environnements", body: () => this.environments.map(e => [e.name || "env", e.url || ""]), empty: "aucun environnement" },
            { id: "docs", title: "documents", body: () => this.docs.map(d => d.title || d.name || d.path || ""), empty: "aucun document" },
            { id: "recent", title: "récents", level: "full", body: () => this.openRecent.map(t => "RM" + t.rm_id + " · " + t.status + (t.title ? " — " + t.title : "")), empty: "rien de récent" }];
  }
  get tab() { return this.ctx.tab === "worklog" ? "worklog" : "fiche"; }
  get links() { const d = this.e, out = []; if (d.redmine_project_url) out.push({ kind: "a", href: d.redmine_project_url, label: "🎫 Projet Redmine ↗" }); if (d.redmine_issues_url) out.push({ kind: "a", href: d.redmine_issues_url, label: "📋 Liste des tickets ↗" }); if (d.gitlab_repo) out.push({ kind: "pill", label: "🗄 " + d.gitlab_repo, title: "repo GitLab" + (d.default_branch ? " · branche " + d.default_branch : "") }); out.push({ kind: "pill", label: (d.total == null ? "?" : d.total) + " tickets" }); return out; }
  sessions() { return (this.ctx.sessions || []).map(s => ({ sid: String(s.rm_id), state: s.state || "idle", label: s.is_ticket === false ? String(s.rm_id) : "RM" + s.rm_id })); }
  get environments() { return this.e.environments || []; }
  get docs() { return this.e.docs || []; }
  get byStatus() { const bs = this.e.open_by_status || {}; return Object.keys(bs).sort().map(st => ({ status: st, n: bs[st] })); }
  row(t) { return { rm_id: String(t.rm_id), status: t.status || "?", title: t.title || "", when: t.mtime && this.ctx.ago ? this.ctx.ago(t.mtime) : "" }; }
  get openRecent() { return (this.e.open_recent || []).map(t => this.row(t)); }

  /** RM3132 — la SANTÉ du projet : ce qu'on veut savoir en arrivant dessus, et qu'il fallait
   *  jusqu'ici chercher à trois endroits.
   *
   *  Construite à partir de ce que la fiche a DÉJÀ. Ce qui manque (dernière MEP, divergence
   *  dev/main, état des tests) n'est pas inventé ni approximé : `pending` le dit, et la vue
   *  l'affiche comme non renseigné. Une santé à moitié fausse serait pire que pas de santé.
   */
  health() {
    const ouverts = this.byStatus.reduce((a, s) => a + (s.n || 0), 0);
    const attente = this.byStatus.filter(s => /^(a_tester|a_mep|en_mep)/.test(s.status))
                                 .reduce((a, s) => a + (s.n || 0), 0);
    const bloques = this.byStatus.filter(s => s.status === "en_pause" || s.status === "a_corriger")
                                 .reduce((a, s) => a + (s.n || 0), 0);
    const vieux = (this.e.open_recent || []).filter(t => t.mtime)
                    .sort((x, y) => (x.mtime || 0) - (y.mtime || 0))[0];
    return {
      ouverts, attente, bloques,
      total: this.e.total || 0,
      doyen: vieux && this.ctx.ago ? { rm: String(vieux.rm_id), age: this.ctx.ago(vieux.mtime) } : null,
      envs: this.environments.length,
      // Non renseigné tant que la fiche ne le porte pas — dit, jamais deviné.
      pending: ["dernière MEP", "divergence dev/main", "état des tests"],
    };
  }
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
bindEntity("project", ProjectSheetViewModel);   // RM3002
