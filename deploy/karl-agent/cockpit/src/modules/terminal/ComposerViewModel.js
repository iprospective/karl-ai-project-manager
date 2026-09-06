// viewmodels/terminal/ComposerViewModel — la garde, les libellés et l'historique du composer, décidés. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { composerGuard, composerLabels, truncate } from "./terminal.js";

/** e = { state (état live de la session), history } */
export class ComposerViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.guard = composerGuard(this.e.state); }
  get allow() { return this.guard.allow; }
  get warn() { return this.guard.warn; }
  get labels() { return composerLabels(this.guard); }
  items() { return (this.e.history || []).map((t, i) => ({ i, text: truncate(t, 300) })); }
}
