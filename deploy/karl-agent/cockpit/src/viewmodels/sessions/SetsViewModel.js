// viewmodels/sessions/SetsViewModel — ce que la carte « Sessions enregistrées » et la barre des jeux PRÉSENTENT. Inerte. RM2889.
import { ago, restartTip } from "../../models/sessions/sessions.js";
import { relaunchBtnState, entryState, entryLabel, ruleSummary, setLabel } from "../../models/sessions/sets.js";

/** RM2452/RM2741 : le formulaire de règle — création (nom + peuplement + critères facultatifs) ou édition (critères seuls). */
export class RuleFormViewModel {
  constructor({ rule, isNew, shownCount, facets }) { this.rule = rule || {}; this.isNew = !!isNew; this.shown = Number(shownCount) || 0; this.facets = facets || {}; }
  get title() { return this.isNew ? "Nouveau jeu" : "Règle du jeu"; }
  get seedShown() { return this.isNew && this.shown > 0; }
  get clients() { return (this.facets.clients || []).map(c => ({ value: c.slug, label: c.slug + " (" + c.count + ")" })); }
  get projects() { return [...new Set((this.facets.clients || []).flatMap(c => c.projects || []))].sort().map(p => ({ value: p, label: p })); }
  get tags() { return (this.facets.tags || []).map(t => ({ value: t.tag, label: t.tag + " (" + t.count + ")" })); }
  get marks() { return ["wip", "test", "done", "none"].map(m => ({ value: m, label: m })); }
  get tickets() { return (this.rule.tickets || []).join(","); }
  get submitLabel() { return this.isNew ? "Créer" : "Appliquer"; }
}

/** La carte : en-tête, règle, entrées, réglages, boutons. `r` = GET /session-set du jeu RÉGLÉ. */
export class SetCardViewModel {
  constructor({ r, edited, current, sets, ruleFormFor, facets, shownCount, spawnPref }) { this.r = r || {}; this.edited = edited; this.current = current; this.sets = sets || []; this.ruleFormFor = ruleFormFor; this.facets = facets; this.shownCount = shownCount || 0; this.spawnPref = !!spawnPref; }
  get label() { return setLabel(this.sets, this.edited); }
  get currentLabel() { return setLabel(this.sets, this.current); }
  get isCurrent() { return this.edited === this.current; }
  get empty() { return !this.r.exists || !this.r.count; }
  /** RM2955 : l'invite du jeu vide dépend de qui reçoit « 💾 ». */
  get emptyHint() { return this.isCurrent ? "bouton « 💾 → " + this.currentLabel + " » dans « ▶ en cours » pour y verser l'affichage" : "c'est le jeu COURANT qui reçoit « 💾 » ; bascule dessus dans « ▶ en cours » pour y verser l'affichage"; }
  get newForm() { return this.ruleFormFor === "__new__" ? new RuleFormViewModel({ rule: {}, isNew: true, shownCount: this.shownCount, facets: this.facets }) : null; }
  get editForm() { return this.r.derived && this.ruleFormFor === this.edited ? new RuleFormViewModel({ rule: this.r.rule, isNew: false, facets: this.facets }) : null; }
  get derivedHeader() { return this.r.derived && this.ruleFormFor !== this.edited ? ruleSummary(this.r.rule) : null; }
  get headerLabel() { return this.r.label || this.edited; }
  get count() { return this.r.count || 0; }
  get truncated() { return !!this.r.truncated; }
  get total() { return this.r.total; }
  get savedAgo() { return ago(this.r.saved_at); }
  /** RM2427/2439/2673/2949 : une ligne par entrée — ⟳/⏸ et ⊖ seulement si le jeu n'est pas dérivé. */
  get rows() {
    return (this.r.entries || []).map(e => ({ sid: e.sid, label: entryLabel(e.sid), engine: e.engine || "?", state: entryState(e), editable: !this.r.derived, restart: e.restart || "idle",
      restartLabel: e.restart === "auto" ? "⟳ auto" : "⏸ au clic", restartTip: restartTip(e.restart), title: e.title || "", inactive: e.last_active ? "inactive depuis " + ago(e.last_active) : "", cwd: e.cwd || "" }));
  }
  get autostartNote() { return "Au lancement de karl-agent, seules les sessions réglées ⟳ de ce jeu redémarrent — et seulement s'il est le jeu courant" + (this.isCurrent ? "" : " (ce n'est pas le cas ici)") + "."; }
  get hideIdleDays() { return this.r.hide_idle_days || 0; }
  get relaunchCount() { return relaunchBtnState(this.r, "set").count; }
}

/** RM2443 : versions archivées contenant le jeu réglé. */
export class HistoryViewModel {
  constructor({ versions, keep, label }) { this.versions = versions || []; this.keep = keep; this.label = label; }
  get empty() { return !this.versions.length; }
  get rows() { return this.versions.map(v => ({ id: v.id, ago: ago(v.at), count: v.count })); }
}
