// viewmodels/sessions/ActionsViewModel — la barre de chips et le menu de disposition, décidés. RM2889.
import { EntityViewModel } from "../EntityViewModel.js";
import { chipList, dispositionItems } from "../../models/sessions/actions.js";

/** e = { actions (CFG.actions), attached } */
export class ChipsViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get shown() { return !!this.e.attached && (this.e.actions || []).some(a => a && !a.ticket_only); }
  items() { return this.shown ? chipList(this.e.actions, this.e.attached) : []; }
}
/** e = { session } */
export class DispositionMenuViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get sid() { return String((this.e.session || {}).rm_id || ""); }
  items() { return dispositionItems((this.e.session || {}).disposition); }
}
