// viewmodels/git/GitPatchViewModel — un patch prêt à rendre. RM2889, L4.
// La vue ne classe pas les lignes ni ne compte les fichiers : c'est décidé ici.
import { EntityViewModel } from "../EntityViewModel.js";
import { gitDiffLine, gitStatLabel } from "../../models/git/gitDiff.js";

export class GitPatchViewModel extends EntityViewModel {
  get label()       { return gitStatLabel(this.e.stats); }
  get files()       { return (this.e.stats || {}).files || []; }
  get truncatedKb() { return this.e.truncated ? Math.round((this.e.max_bytes || 0) / 1024) : null; }
  get empty()       { return !(this.e.stats && this.e.stats.count); }
  lines()           { return String(this.e.patch || "").split("\n").map(text => ({ cls: gitDiffLine(text), text })); }
}
