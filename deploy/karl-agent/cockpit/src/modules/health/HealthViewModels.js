// viewmodels/health — badge et page de santé du système PM (RM3369). Inertes.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { checkTabs, checkDefaultTab, checkSections } from "../../core/checks.js";
import { healthBadgeState, healthHeadline, healthAge } from "./pmHealth.js";

/** Le badge d'en-tête : rien quand tout va bien ; le survol dit QUOI. */
export class HealthBadgeViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get state() { return this._s || (this._s = healthBadgeState(this.e)); }
  get show()  { return this.state.show; }
  get count() { return this.state.count; }
  get cls()   { return this.state.cls; }
  get title() { return this.state.title; }
}

/** La page : une famille à la fois, les lignes en défaut d'abord. */
export class HealthStatusViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.known = !!e; }
  get unavailable() { return !this.known || !this.e.groups; }
  get counts() { return (this.e.summary && this.e.summary.counts) || { ok: 0, warn: 0, error: 0 }; }
  get headline() { return healthHeadline(this.known ? this.e : null); }
  get when() { return this.e.generated_label || ""; }
  get age()  { return healthAge(this.e.generated_at, this.ctx.now); }
  get tabs() { return this._t || (this._t = checkTabs(this.e.groups)); }
  get current() { const a = this.ctx.active; return this.tabs.some(t => t.name === a) ? a : checkDefaultTab(this.tabs); }
  get group() { return (this.e.groups || []).find(x => (x.name || "") === this.current) || { checks: [] }; }
  get flat() { const s = this.sections; return s.length === 1 && s[0].name === ""; }
  get sections() {
    return checkSections(this.group.checks || []).map(s => ({ ...s, bad: s.worst > 0,
      error: s.checks.filter(c => c.level === "error").length, warn: s.checks.filter(c => c.level === "warn").length }));
  }
}
