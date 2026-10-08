// viewmodels/sessions/ActionsViewModel — la barre de chips et le menu de disposition, décidés. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { chipBlocks, chipList, dispositionItems } from "./actions.js";

/** e = { actions (CFG.actions), attached, ui (CFG.ui — RM3418), mobile } */
export class ChipsViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get _opts() {
    const ui = this.e.ui || {};
    return { hidden: ui.chips_hidden || [], line: this.e.mobile ? (ui.chips_line || null) : null };
  }
  get shown() { return !!this.e.attached && chipBlocks(this.e.actions, this.e.attached, this._opts).length > 0; }
  blocks() { return this.shown ? chipBlocks(this.e.actions, this.e.attached, this._opts) : []; }
  items() { return this.shown ? chipList(this.e.actions, this.e.attached, this._opts) : []; }
}
/** e = { session } */
export class DispositionMenuViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get sid() { return String((this.e.session || {}).rm_id || ""); }
  items() { return dispositionItems((this.e.session || {}).disposition); }
}
