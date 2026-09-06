// services/files.service — l'état de l'explorateur (données du contexte, navigation) et ses chargements. RM2889.
import { FilesRepository } from "./FilesRepository.js";
import { filesCtxKey, filesGroups, freshNav } from "./explorer.js";
import { fsQuery } from "./scope.js";

export class FilesService {
  constructor({ repo = new FilesRepository() } = {}) { this.repo = repo; this.data = { sid: null, worktrees: [] }; this.nav = freshNav(null); }
  /** Périmètre de lecture : une SESSION (ses worktrees) ou un PROJET (sa racine, sa doc) — le serveur autorise les deux. */
  query(attached, wt) { return fsQuery(wt == null ? this.nav.wt : wt, null, { filesData: this.data, attached }); }
  reset() { this.data = { sid: null, worktrees: [] }; }
  /** Charge le contexte. Rend { kind: "none" | "empty" | "ok", roots, ctx } ; `force` repart de la première racine. */
  async load(ctx, force) {
    this.data = { sid: null, worktrees: [], ctxKey: filesCtxKey(ctx) };
    if (ctx.kind === "none") return { kind: "none", ctx };
    const r = ctx.kind === "session" ? await this.repo.worktrees(ctx.sid) : await this.repo.projectRoots(ctx.client, ctx.project);
    this.data = Object.assign({}, r, { ctxKey: filesCtxKey(ctx), from: ctx.from || null });
    // RM2659 : une session sans worktree a quand même un projet — sa racine et sa doc restent lisibles
    const roots = filesGroups(this.data.projects, this.data.worktrees).reduce((a, g) => a.concat(g.roots), []);
    if (!roots.length) return { kind: "empty", ctx };
    if (force || !this.nav.wt || !roots.some(w => w.path === this.nav.wt)) this.nav = freshNav(roots[0].path);
    return { kind: "ok", ctx, roots };
  }
  async loadDir(attached, wt, path) {
    const n = this.nav;
    if (wt !== n.wt || path !== n.path) { n.vocabMd = null; n.vocab = false; }   // glossaire propre à CE dossier
    n.wt = wt; n.path = path; n.file = null;
    if (n.commits != null && wt !== n._commitsWt) n.commits = null;              // commits par worktree
    try { n.entries = await this.repo.ls(this.query(attached), path); return null; }
    catch (e) { n.entries = []; return e; }
  }
  async open(attached, name) { const sp = this.nav.path ? this.nav.path + "/" + name : name; this.nav.file = await this.repo.file(this.query(attached), sp); return this.nav.file; }
  async toggleCommits(attached) {
    const n = this.nav; n.showCommits = !n.showCommits;
    if (n.showCommits && n.commits == null) { try { n.commits = await this.repo.log(this.query(attached)); n._commitsWt = n.wt; } catch (e) { n.commits = []; } }
    return n.showCommits;
  }
  /** RM2675 : le glossaire du dossier courant, chargé une fois. Rend l'erreur éventuelle. */
  async vocabShow(attached, on) {
    const n = this.nav; n.vocab = !!on;
    if (on && n.vocabMd == null) {
      const sp = (n.path ? n.path + "/" : "") + "glossaire.md";
      try { const f = await this.repo.file(this.query(attached), sp); n.vocabMd = f.content || ""; } catch (e) { n.vocabMd = ""; return e; }
    }
    return null;
  }
}
