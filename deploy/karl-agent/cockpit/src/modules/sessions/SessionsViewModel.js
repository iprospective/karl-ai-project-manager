// viewmodels/sessions/SessionsViewModel — ce que la liste « en cours » PRÉSENTE : tuiles vivantes et grises, en-têtes de groupe,
// bandeau « à traiter », compteurs, titre de la session attachée. Inerte : ni réseau ni DOM. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { effDisposition, autoYesLeft, ago, quietInfo, displayId, tmuxName, tabTip, ghostTip, restartTip, approveShortcutVisible } from "./sessions.js";

/** RM2793 : silence de la session — déplacé d'index.html (même signature) ; la tuile en rend l'équivalent depuis `quiet`. */
export function quietHtml(s, escFn) {
  const q = quietInfo(s); if (!q) return "";
  return '<span class="tquiet" title="' + q.title + '">⏳' + escFn(q.d) + (q.exact ? "" : "~") + "</span>";
}

/** ctx : { resolved, attached, stale (Set), selMode, selected (Set), set: { sets, current, view }, writable(sets, name, view), setLabel(name), now } */
export class SessionTileViewModel extends EntityViewModel {
  constructor(session, ctx = {}) { super(Object.assign({ id: String(session.rm_id), type: "session" }, session), ctx); this.s = session; }
  get r() { return this.ctx.resolved; }
  get key() { return "s:" + this.s.rm_id; }
  get idLabel() { return displayId(this.s); }
  get active() { return this.ctx.attached === this.s.rm_id; }
  get tip() { return tabTip(this.s, this.r); }
  /** RM2515 : la disposition raffine `idle` (et CÈDE au live : nulle hors idle). */
  get disp() { return effDisposition(this.s.state, this.s.disposition); }
  get dotClass() { return "tdot tdisp st-" + (this.s.state || "idle") + (this.disp && this.disp !== "a_traiter" ? " disp-" + this.disp : ""); }
  /** Pastille d'état : { kind, style, title } ou null. */
  get badge() {
    const st = this.s.state;
    if (st === "attention") return { text: "⚠", style: "", title: "" };
    if (st === "choice") return { text: "❓", style: "color:var(--warn)", title: "" };
    if (st === "idle") return this.disp === "parke" ? { text: "🔖", style: "", title: "parké — j'y reviens" }
      : this.disp === "termine" ? { text: "✅", style: "color:var(--ok)", title: "terminé — rien à faire, à fermer" }
      : { text: "💤", style: "opacity:.55", title: "à traiter" };
    return null;
  }
  get autoTitle() { return this.s.auto_yes_until ? "auto-oui armé — " + autoYesLeft(this.s.auto_yes_until) + " restantes" : ""; }
  /** RM2598 : question laissée sans réponse — pas si DÉJÀ en attention/choix (même urgence, un seul signal). */
  get stale() { const st = this.ctx.stale; return !!(st && st.has(String(this.s.rm_id)) && this.s.state !== "attention" && this.s.state !== "choice"); }
  get title() { return this.r && this.r.found ? (this.r.title || "") : ""; }
  get age() { return this.s.created ? ago(this.s.created) : ""; }
  /** RM2445/RM2446 : vivante d'un autre jeu — LEQUEL, ou aucun. */
  get setTag() {
    if (this.s.in_current !== false) return null;
    const labels = this.s.set_labels || [];
    return labels.length ? { text: labels[0].slice(0, 10), title: "appartient au jeu « " + labels.join(" », « ") + " »", opacity: ".65" }
      : { text: "hors jeu", title: "cette session ne figure dans aucun jeu enregistré", opacity: ".5" };
  }
  /** RM2787/RM2793 : le silence, nommé par sa mesure. */
  get quiet() { return quietInfo(this.s); }
  get canApprove() { return this.s.state === "attention"; }
  /** RM2446/RM2673 : ⊖ sort la session du jeu courant — seulement si elle y est ET que le jeu est inscriptible (`setWritable`). */
  get canDrop() { const st = this.ctx.set || {}; return (this.s.sets || []).includes(st.current) && !!(this.ctx.writable && this.ctx.writable(st.sets, st.current, st.view)); }
  get dropTitle() { const st = this.ctx.set || {}; return "Retirer du jeu « " + (this.ctx.setLabel ? this.ctx.setLabel(st.current) : st.current) + " » — la session continue de tourner"; }
  get selMode() { return !!this.ctx.selMode; }
  get selected() { return !!(this.ctx.selected && this.ctx.selected.has(this.s.rm_id)); }
}

/** RM2427 : session enregistrée non démarrée — tuile grise, clic = relancer (ou retenir en mode sélection). */
export class GhostTileViewModel extends EntityViewModel {
  constructor(session, ctx = {}) { super(Object.assign({ id: String(session.rm_id), type: "session" }, session), ctx); this.s = session; }
  get r() { return this.ctx.resolved; }
  get key() { return "g:" + this.s.rm_id; }
  get idLabel() { return displayId(this.s); }
  /** RM2439 : sujet Redmine si connu, sinon le NOM mémorisé dans le jeu. */
  get title() { return ((this.r && this.r.found) ? (this.r.title || "") : "") || this.s.title || ""; }
  get tip() { return ghostTip(this.s, !!this.ctx.selMode); }
  /** RM2442 : plusieurs jeux repris à la fois ⇒ la tuile dit duquel elle vient. */
  get groupTag() { return (this.ctx.set && this.ctx.set.view === "all" && this.s.group_label) ? { text: this.s.group_label.slice(0, 10), title: "jeu « " + this.s.group_label + " »" } : null; }
  /** RM2451 : l'âge de la SESSION prime sur la date d'enregistrement du jeu. */
  get age() { return this.s.last_active ? "inactive depuis " + ago(this.s.last_active) : (this.s.saved_at ? "enregistrée " + ago(this.s.saved_at) : ""); }
  get faded() { return !!(this.s.last_active && ((this.ctx.now || Date.now()) / 1000 - this.s.last_active) > 7 * 86400); }
  /** RM2536/RM2673 : ⊖ et ⟳ agissent SUR un jeu — pas de jeu inscriptible, pas de gestes. */
  get inSet() { const st = this.ctx.set || {}; return !!(this.ctx.writable && this.ctx.writable(st.sets, st.current, st.view)); }
  get restartIcon() { return this.s.restart === "auto" ? "⟳" : "⏸"; }
  get restartTip() { return restartTip(this.s.restart); }
  get selMode() { return !!this.ctx.selMode; }
  get selected() { return !!(this.ctx.selected && this.ctx.selected.has(this.s.rm_id)); }
}

/** En-tête d'un groupe client/projet (RM2353 clic = fiche projet, RM2448 chevron = pli). */
export class GroupViewModel {
  constructor({ key, sessions, folded }) { this.key = key; this.sessions = sessions; this.folded = !!folded; }
  get att() { return this.sessions.filter(s => s.state === "attention").length; }
  get cho() { return this.sessions.filter(s => s.state === "choice").length; }
  get count() { return this.sessions.length; }
  get foldTitle() { return (this.folded ? "Déplier" : "Replier") + " ce groupe"; }
  get chevron() { return this.folded ? "▸" : "▾"; }
  get tip() { return this.key + "\n(clic : fiche projet dans le panneau principal)"; }
}

/** RM2346 : puce du bandeau « à traiter ». */
export class AttnChipViewModel {
  constructor(session, resolved) { this.s = session; this.r = resolved; }
  get idLabel() { return displayId(this.s); }
  get hasTitle() { return !!(this.r && this.r.found && this.r.title); }
  get fallback() { return tmuxName(this.s.rm_id); }
  get canApprove() { return this.s.state === "attention"; }
}

/** RM2283 : compteurs globaux — panneau, badges de l'onglet « en cours », « ✔ tout », titre du navigateur. */
export class CountersViewModel {
  constructor(counts) { this.c = counts || { total: 0, attention: 0, choice: 0, idle: 0, working: 0, ghost: 0 }; }
  get waiting() { return this.c.attention + this.c.choice; }   // RM2327 : ❓ compte aussi
  get showYesAll() { return this.c.attention > 1; }           // RM2327 : dès 2 sessions en attention
  get docTitle() { return (this.waiting ? "⚠" + this.waiting + " " : "") + "Cockpit karl-agent"; }
}

/** RM2210 : tuile d'une revue ouverte (pas une session tmux). */
export class ReviewTileViewModel {
  constructor(rm, resolved, active) { this.rm = rm; this.r = resolved; this.active = !!active; }
  get title() { return this.r && this.r.found ? (this.r.title || "") : ""; }
  get tip() { return "Revue RM" + this.rm + (this.r && this.r.found ? " — " + (this.r.title || "") : ""); }
}

/** Titre de la session attachée dans la barre du centre (RM2283) et en-tête du panneau droit (RM2894), raccourcis ✔ Oui / auto-oui. */
export class SessionTitleViewModel {
  constructor({ attached, sess, resolved }) { this.attached = attached; this.s = sess || {}; this.r = resolved; }
  get shown() { return !!this.attached; }
  get idLabel() { return displayId(this.s, this.attached); }
  get state() { return this.s.state || "idle"; }
  get hasTitle() { return !!(this.r && this.r.found && this.r.title); }
  get fallback() { return tmuxName(this.attached); }
  get tmux() { return tmuxName(this.attached); }
  /** RM2894 : trois sources — sujet Redmine, titre du transcript, rien (et on le dit). */
  get label() { return this.hasTitle ? String(this.r.title) : String(this.s.title || ""); }
  get approveVisible() { return approveShortcutVisible(this.attached, { [this.attached]: this.s }); }
  get autoYesLabel() { return this.s.auto_yes_until ? "⏱✔ " + autoYesLeft(this.s.auto_yes_until) : "⏱ auto-oui…"; }
  get autoYesArmed() { return !!this.s.auto_yes_until; }
}
