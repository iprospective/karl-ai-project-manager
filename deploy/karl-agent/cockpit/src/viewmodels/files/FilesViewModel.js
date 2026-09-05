// viewmodels/files/FilesViewModel — l'onglet fichiers, décidé : groupes, racines, cadre git, commits, fichier ou dossier, vocabulaire. RM2889.
import { EntityViewModel } from "../EntityViewModel.js";
import { filesGroups, filesGroupOf, fileRootLabel, sortRoots, filesCrumbs, fmtKo } from "../../models/files/explorer.js";
import { glossaireRows, glossaireFiltre } from "../../models/glossary/glossary.js";

/** e = { data (filesData), nav (fileNav), attached } ; ctx = { scopeTag(wt) } */
export class FilesViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.data = this.e.data || {}; this.nav = this.e.nav || {}; this.groups = filesGroups(this.data.projects, this.data.worktrees); this.grp = filesGroupOf(this.groups, this.nav.wt); this.wts = this.grp ? this.grp.roots : []; this.cur = this.wts.find(w => w.path === this.nav.wt) || this.wts[0] || null; }
  get count() { return this.cur ? (this.cur.name || "") : ""; }
  /** RM2673 : sans session attachée, le panneau dit QUEL projet il montre et d'où il le tient. */
  get header() { return (!this.e.attached && this.data.from) ? { project: (this.data.client || "") + "/" + (this.data.project || ""), from: this.data.from } : null; }
  /** RM2659 : la barre des projets n'apparaît QUE s'il y en a plusieurs. */
  get projectTabs() { return this.groups.length > 1 ? this.groups.map(g => ({ label: g.label, tip: g.client ? g.client + " / " + g.label : g.label, wt: g.roots[0].path, active: g === this.grp })) : []; }
  get rootTabs() { return this.wts.length > 1 ? sortRoots(this.wts).map(w => { const lb = fileRootLabel(w); return { wt: w.path, active: w.path === this.nav.wt, doc: w.kind === "doc", icon: lb.icon, name: lb.name, tip: lb.tip }; }) : []; }
  get isDoc() { return !!(this.cur && this.cur.kind === "doc"); }
  get docLabel() { return (this.cur && this.cur.label) || "documentation du projet"; }
  /** RM2675 : l'onglet vocabulaire n'apparaît QUE si le dossier a un glossaire. */
  get hasGloss() { return this.isDoc && (this.nav.entries || []).some(e => e.name === "glossaire.md"); }
  get vocab() { return !!(this.nav.vocab && this.hasGloss); }
  get git() { const c = this.cur; return (c && c.is_git) ? { branch: c.branch || "", clean: !!c.clean, dirty: c.dirty || 0, untracked: c.untracked || 0, ahead: c.ahead || 0, behind: c.behind || 0, open: !!this.nav.showCommits } : null; }
  /** RM2759 : un commit s'ouvre au centre par la session ; sans session, la ligne reste informative. */
  commits() { return (this.nav.commits || []).map(c => ({ hash: c.hash, subject: c.subject || "", date: c.date || "", author: c.author || "", clickable: !!this.e.attached })); }
  get scopeTag() { return this.ctx.scopeTag ? this.ctx.scopeTag(this.nav.wt) : ""; }
  file() { const f = this.nav.file; if (!f) return null; return { name: f.name, size: fmtKo(f.size), path: (this.nav.path ? this.nav.path + "/" : "") + f.name, raw: f }; }
  get crumbs() { const cs = filesCrumbs(this.nav.path); return cs.map((c, i) => ({ name: c.name, path: c.path, last: i === cs.length - 1 })); }
  entries() { const base = this.nav.path ? this.nav.path + "/" : ""; return (this.nav.entries || []).map(e => ({ name: e.name, dir: !!e.dir, child: base + e.name, size: e.size != null ? fmtKo(e.size) : "" })); }
}
/** e = { md, q } — le glossaire du projet, filtrable (RM2675). */
export class VocabViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.all = glossaireRows(this.e.md); this.rows = glossaireFiltre(this.all, this.e.q); }
  get loading() { return this.e.md == null; }
  get q() { return String(this.e.q || ""); }
  get count() { return this.rows.length + " / " + this.all.length + " terme(s)"; }
  list() { return this.rows.map(r => ({ terme: r.terme, definition: r.definition, contexte: r.contexte === "—" ? "" : r.contexte, alias: (r.alias && r.alias !== "—") ? r.alias : "" })); }
}
