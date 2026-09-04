// viewmodels/env — badge d'anomalies, page de santé, verrous. RM2889, L5. Inertes.
import { EntityViewModel } from "../EntityViewModel.js";
import { envStatusTabs, envStatusDefaultTab, envStatusSections, vaultBtnState } from "../../models/env/envStatus.js";

/** Le badge d'en-tête (RM2722) : rien quand tout va bien ; le survol dit QUOI. */
// Ces trois ViewModels acceptent une donnée ABSENTE (pas encore reçue) : c'est un
// état légitime du poste, distinct d'une donnée vide.
export class EnvBadgeViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get items() { return this.e.items || []; }
  get count() { return this.items.length; }
  get cls()   { return this.e.worst === "error" ? "ew-error" : "ew-warn"; }
  get title() {
    const lignes = this.items.slice(0, 8).map(i => "• " + i.family + " — " + i.label + (i.detail ? " : " + i.detail : ""));
    if (this.items.length > 8) lignes.push("… et " + (this.items.length - 8) + " autre(s)");
    return this.count + " anomalie(s) du poste — clic : ouvrir la santé du poste\n" + lignes.join("\n");
  }
}

/** La page de santé (RM2458/RM2708) : une famille à la fois, sections par client. */
export class EnvStatusViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.known = !!e; }
  get unavailable() { return !this.known || !this.e.groups; }
  get counts() { return (this.e.summary && this.e.summary.counts) || { ok: 0, warn: 0, error: 0 }; }
  get generatedAt() { return this.e.generated_at || ""; }
  get tabs() { return this._t || (this._t = envStatusTabs(this.e.groups)); }
  get current() { const a = this.ctx.active; return this.tabs.some(t => t.name === a) ? a : envStatusDefaultTab(this.tabs); }
  get group() { return (this.e.groups || []).find(x => (x.name || "") === this.current) || { checks: [] }; }
  get flat() { const s = this.sections; return s.length === 1 && s[0].name === ""; }
  get sections() {
    return envStatusSections(this.group.checks || []).map(s => ({ ...s, bad: s.worst > 0,
      error: s.checks.filter(c => c.level === "error").length, warn: s.checks.filter(c => c.level === "warn").length }));
  }
}

/** Les verrous (RM2748) : ce qu'on montre, et ce qu'on ose demander. */
export class VaultViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.known = !!e; }
  get secure()    { return !!this.ctx.secure; }
  get st()        { return this.e || {}; }
  get daemon()    { return !!this.st.daemon; }
  get locked()    { return this.st.locked || []; }
  get instances() { return this.st.instances || []; }
  get ssh()       { return this.st.ssh || {}; }
  get keys()      { return this.ssh.keys || []; }
  get candidates(){ return this.ssh.candidates || []; }
  get needsUnlock() { return this.locked.length > 0 || !this.daemon; }
  get choices()   { return this.locked.length ? this.locked : [this.st.default_instance || "vw-ipro"]; }
  get canAddKey() { return !!this.ssh.reachable && this.candidates.length > 0; }
  get button()    { return vaultBtnState(this.known ? this.e : null); }
}
