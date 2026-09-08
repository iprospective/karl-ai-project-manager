// modules/sessproj/SessProjViewModel — l'onglet « projets » de la colonne de droite, décidé : les projets touchés par la session
// attachée (cwd + worktrees), leurs raccourcis (fiche, docs, fichiers) et leurs CDC vivants (fonctionnalités, CDC, feuille de route). RM3045.
import { EntityViewModel } from "../../core/EntityViewModel.js";

/** e = { projects: [{client, project, name, root, branch, dirty, cdcs:[{key,title,prefix,path}], docs:[…]}], attached, error } */
export class SessProjViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get attached() { return !!this.e.attached; }
  get error() { return this.e.error || ""; }
  get empty() { return !(this.e.projects || []).length; }
  get emptyText() { return this.error ? "projets injoignables : " + this.error : (this.attached ? "cette session ne touche aucun projet PM (pas de .mmi-pm dans son cwd ni ses worktrees)" : "attache une session : ses projets et leurs CDC vivants apparaîtront ici"); }
  rows() {
    return (this.e.projects || []).map(p => {
      const c = p.client || "", pj = p.project || "";
      return { key: c + "/" + pj, client: c, project: pj, name: p.name || pj, root: p.root || "", branch: p.branch || "", dirty: p.dirty || 0, exists: p.exists !== false,
        overview: "projects/clients/" + c + "/projects/" + pj + "/project/overview.md",
        docs: (p.docs || []).length, cdcs: (p.cdcs || []).map(x => ({ key: x.key, title: x.title || x.prefix, prefix: x.prefix, path: x.path, registry: x.registry !== false })) };
    });
  }
  get count() { return String((this.e.projects || []).length); }
}
