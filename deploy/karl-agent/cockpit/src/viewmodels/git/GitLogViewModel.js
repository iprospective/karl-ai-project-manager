// viewmodels/git/GitLogViewModel — ce que l'onglet git montre. RM2889, L4.
//
// Les décisions que gitRender prenait en plein DOM : pas un dépôt, dépôt de
// données PM (on le dit, on n'affiche pas ses pm(tick)), vide, ou liste ;
// le compteur d'en-tête ; l'état de chaque commit. Inerte et testé.

import { EntityViewModel } from "../EntityViewModel.js";
import { gitStatLabel } from "../../models/git/gitDiff.js";

export class GitLogViewModel extends EntityViewModel {
  /** @param log   la charge de /git/log
   *  @param ctx   { sel: sha sélectionné, branches: celles du registre de session } */
  get mode() {
    if (!this.e.is_git) return "not_git";
    if (this.e.pm_data_repo) return "pm_data";
    return this.e.commits.length ? "list" : "empty";
  }
  get local()  { return this.e.commits.filter(c => !c.pushed).length; }
  get branch() { return this.e.branch || "?"; }
  get branches() { return (this.ctx.branches || []).filter(Boolean); }
  /** Le compteur de l'en-tête et son infobulle. */
  get count() {
    if (this.mode === "not_git") return "";
    if (this.mode === "pm_data") return "aucun code";
    const l = this.local, d = this.e.dirty;
    return this.branch + (l ? " · " + l + " non poussé" + (l > 1 ? "s" : "") : "")
      + (d ? " · " + d + " modifié" + (d > 1 ? "s" : "") : "");
  }
  get countTitle() { return "Dépôt : " + (this.e.cwd || "?") + "\n(" + (this.e.origin || "?") + ")"; }
  commits() {
    return this.e.commits.map(c => ({
      sha: c.sha, short: c.short, subject: c.subject, merge: !!c.merge, pushed: !!c.pushed,
      cur: this.ctx.sel === c.sha,
      when: (c.date || "").slice(0, 16).replace("T", " "), author: c.author,
      title: (c.pushed ? "Poussé" : "LOCAL — n'existe sur aucun remote") + " — clic : voir le diff",
    }));
  }
  static statLabel(stats) { return gitStatLabel(stats); }
}
