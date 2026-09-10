// viewmodels/tickets/ReviewViewModel — la fiche de revue, décidée. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { ticketVerdicts } from "../ticket/ticketStatus.js";
import { promptTemplates } from "../ticket/prompts.js";
import { sinceLabel } from "../ticket/ticketFormat.js";
import { bindEntity } from "../../core/entities.js";
import { html } from "../../core/html.js";

/** Les sessions d'un ticket (RM2726) et la consigne (RM2873). e = payload /ticket-sessions ou null ; ctx = { prompt } */
export class TicketSessionsViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || { __loading: true }, ctx); this.loading = !e; }
  name(s) { return "karl-" + (/^\d+$/.test(String(s.sid)) ? "RM" + s.sid : s.sid); }
  get rm() { return String(this.e.rm_id || ""); }
  handled() { return (this.e.handled || []).map(s => ({ sid: String(s.sid), alive: !!s.alive, name: this.name(s), title: s.title || "", reasons: (s.reasons || []).join(" + "), other: s.same_project ? "" : (s.client || "?") + "/" + (s.project || "?") })); }
  get ownAlive() { return !!this.e.own_alive; }
  get prompt() { const p = this.ctx.prompt || {}; return { tpl: p.tpl || "traiter", text: p.text || "" }; }
  get templates() { return promptTemplates(); }
  candidates() { const cs = this.e.candidates || [], opt = c => ({ sid: String(c.sid), label: this.name(c) + (c.title ? " — " + c.title : "") + (c.same_project ? "" : "  ·  " + (c.client || "?") + "/" + (c.project || "?")) });
    return { mine: cs.filter(c => c.same_project).map(opt), other: cs.filter(c => !c.same_project).map(opt), project: (this.e.client || "?") + "/" + (this.e.project || "?") }; }
}

/** La fiche. e = { r (résolution), q (entrée de la file), tqLoaded, tqSize, mc, ts, cfg, pmTarget } ; ctx = { rm, prompt, now } */
export class ReviewViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get rm() { return String(this.ctx.rm); }
  // RM3002 : quatre niveaux depuis sections() (core/entities) — la fiche complète du centre reste ReviewPane
  get type() { return "review"; }
  get id() { return this.rm; }
  get title() { return this.found && this.r.title ? this.r.title : "RM" + this.rm; }
  get subtitle() { return this.found && this.r.client && this.r.project ? this.r.client + "/" + this.r.project : ""; }
  get badges() { const out = []; if (this.status) out.push({ text: this.status, cls: /^ferme|termine/.test(this.status) ? "ok" : /a_corriger|bloqu/.test(this.status) ? "danger" : /a_tester|a_mep|en_mep/.test(this.status) ? "accent" : "" }); if (this.found && this.r.priority) out.push({ text: this.r.priority, cls: /urgent|high/.test(this.r.priority) ? "warn" : "" }); return out; }
  sections() {
    const r = this.r || {};
    return [{ id: "links", title: "liens", summary: true, body: () => this.links.map(l => html`<a href="${l.href}" target="_blank" rel="noopener">${l.label}</a>`), empty: "aucun lien" },
            { id: "tags", title: "étiquettes", summary: true, body: () => this.tags.join(" · ") },
            { id: "environments", title: "environnements", body: () => { const e = this.environments; return e ? (e.test_url ? [["test", e.test_url]] : []).concat(e.list.map(x => [x.name || "env", x.url])) : null; }, empty: "aucun environnement" },
            { id: "protocol", title: "protocole de test", body: () => (this.protocol ? html`<pre>${this.protocol.text}</pre>` : null), empty: "pas de protocole" },
            { id: "description", title: "description", level: "full", body: () => (r.description ? html`<pre>${r.description}</pre>` : null), empty: "pas de description" },
            { id: "log", title: "dernière activité", level: "full", body: () => (r.log_tail ? html`<pre>${r.log_tail}</pre>` : null), empty: "aucune activité enregistrée" }];
  }
  get r() { return this.e.r; }
  get found() { return !!(this.r && this.r.found); }
  get q() { return this.e.q; }
  get version() { const r = this.r; const iso = r && (r.updated || r.mtime); return iso ? { iso, label: sinceLabel(iso, this.ctx.now) || iso } : null; }
  get tags() { return ((this.r && this.r.tags) || []).filter(t => String(t || "").trim()); }
  get links() { const r = this.r || {}, out = []; if (r.redmine_url) out.push({ href: r.redmine_url, label: "Redmine ↗" }); if (r.git && r.git.mr_url) out.push({ href: r.git.mr_url, label: "MR ↗" }); return out; }
  get protocol() { const p = this.r && this.r.test_protocol; return p ? { text: p.text, source: p.source === "cf" ? "champ Protocole de test" : p.source === "note" ? "note de livraison" : "description" } : null; }
  /** L'état du bloc « env de test » : live | broken | deployable | nolayout | left | outside | loading */
  get env() {
    const q = this.q;
    if (q && q.test_host && q.env_live) return { kind: "live", host: q.test_host };
    if (q && q.test_host) return { kind: "broken", host: q.test_host, reason: q.env_reason || "la sonde ne confirme pas cet env" };
    if (q && q.deployable) return { kind: "deployable" };
    if (q) return { kind: "nolayout" };
    if (this.e.tqLoaded && this.found) return { kind: "left", status: this.r.status || "?" };
    if (this.e.tqSize) return { kind: "outside" };
    return { kind: "loading" };
  }
  /** RM3089 : la réflexion du ticket — les quatre rubriques, prêtes à rendre. `null` si le carnet
   *  n'existe pas encore : une fiche sans carnet n'affiche pas un bloc vide. */
  get think() {
    const th = (this.r || {}).think;
    if (!th || !th.file) return null;
    const ICON = { valide: "✅", invalide: "❌", propose: "🟡", attente: "🕐", reserve: "⏸" };
    const rub = (rows, titre) => (rows || []).map(r => ({
      id: String(r.id || ""), text: String(r.text || ""), icon: ICON[r.state] || "·",
      state: String(r.state || ""), closed: !!r.closed, prefix: String(r.prefix || ""),
      open: !r.closed && r.state !== "valide" && r.state !== "invalide", rubrique: titre }));
    const c = th.counts || {};
    return { file: th.file, counts: c,
      questions: rub(th.questions, "question"), decisions: rub(th.decisions, "decision"),
      notes: rub(th.notes, "note"), features: rub(th.features, "feature"),
      openQuestions: rub(th.questions, "question").filter(q => q.open).length,
      // c'est ce chiffre qui explique le refus de clôture AVANT qu'il ne tombe
      blocking: (c.questions_open || 0) + (c.notes_pending || 0) };
  }

  get environments() { const r = this.r || {}; return this.found ? { test_url: r.test_url || "", list: (r.environments || []).filter(e => e.url) } : null; }
  get verdicts() { return ticketVerdicts(String((this.found && this.r.status) || "").toLowerCase(), this.e.cfg); }
  get pmActions() { return ((this.e.cfg || {}).actions || []).filter(a => a.ticket_only).map((a, i) => ({ i, label: a.label, title: String(a.text || "").replaceAll("{id}", this.rm) })); }
  get pmTarget() { return this.e.pmTarget || { sid: null, why: "" }; }
  get status() { return String((this.found && this.r.status) || "").toLowerCase(); }
  sessions() { return new TicketSessionsViewModel(this.e.ts, { prompt: this.ctx.prompt }); }
}

/** Le menu de statut (RM2888) : le serveur décide, l'UI rend. */
export class StatusMenuViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get status() { return String(this.e.status || "?"); }
  get degraded() { return this.e.redmine_checked === false; }
  items() { return (this.e.transitions || []).map(t => ({ status: String(t.status), refused: t.redmine_ok === false, reason: !!t.needs_close_reason, note: !!t.needs_note,
    tip: String(t.condition || "") + (t.redmine_ok === false ? " — Redmine refusera cette transition pour ce compte" : "") })); }
}
bindEntity("review", ReviewViewModel);   // RM3002
