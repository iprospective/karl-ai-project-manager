// viewmodels/tickets/ReviewViewModel — la fiche de revue, décidée. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { ticketVerdicts } from "../ticket/ticketStatus.js";
import { promptTemplates } from "../ticket/prompts.js";
import { sinceLabel } from "../ticket/ticketFormat.js";
import { bindEntity } from "../../core/entities.js";
import { mdToHtml } from "../../core/markdown.js";   // RM3137 : une description est du markdown, pas un listing
import { raw } from "../../core/html.js";
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
  /** Le demandeur, cliquable s'il est à l'annuaire (RM3149). */
  get requester() {
    const d = (this.r || {}).requester;
    if (!d || !(d.name || d.email)) return null;
    const nom = d.name || d.email;
    const pastille = d.internal ? html` <span class="pill">interne</span>` : "";
    if (!d.known) return html`${nom}${pastille}`;
    return html`<span style="cursor:pointer;text-decoration:underline dotted"
      data-action="open-contact" data-value="${d.ref}"
      title="Fiche de ${d.ref}">${nom}</span>${pastille}`;
  }
  /** RM3256 — les relations du ticket, une ligne par nature. Rendues en texte : le clic vers un
   *  autre ticket appartient à la vue qui sait où l'ouvrir, pas au registre. */
  get relationLines() {
    const r = this.r || {}, out = [];
    const add = (label, ids) => { const l = (ids || []).map(String).filter(Boolean); if (l.length) out.push([label, l.join(" · ")]); };
    if (r.parent_task) add("parent", [r.parent_task]);
    add("sous-tâches", r.sub_tasks); add("dépend de", r.depends_on); add("bloque", r.blocks); add("liés", r.relates);
    return out;
  }
  sections() {
    const r = this.r || {};
    return [
      // RM3256 : l'identité du ticket — ce que le panneau de droite écrivait de son côté, et que
      // le centre redisait autrement. Une seule définition, deux vues.
      { id: "identite", title: "identité", summary: true, body: () => {
        const out = [];
        if (r.type) out.push(["type", r.type]);
        if (r.status) out.push(["phase", r.status]);
        if (r.priority) out.push(["priorité", r.priority]);
        if (r.completion_pct != null) out.push(["avancement", r.completion_pct + " %"]);
        return out;
      }, empty: "ticket non résolu" },
      { id: "git", title: "git", body: () => { const g = r.git || {}; const out = [];
        if (g.branch) out.push(["branche", g.branch]);
        if (g.mr_url) out.push(["MR", html`<a href="${g.mr_url}" target="_blank" rel="noopener">↗</a>`]);
        return out; }, empty: "aucune branche de ticket" },
      { id: "relations", title: "relations", body: () => this.relationLines, empty: "aucune relation" },
      { id: "links", title: "liens", summary: true, body: () => this.links.map(l => html`<a href="${l.href}" target="_blank" rel="noopener">${l.label}</a>`), empty: "aucun lien" },
            { id: "tags", title: "étiquettes", summary: true, body: () => this.tags.join(" · ") },
            // RM3149 : qui a demandé. Cliquable vers sa fiche quand l'annuaire le
            // connaît ; sinon lisible tel quel — un demandeur hors annuaire ne
            // doit pas disparaître de la fiche.
            { id: "requester", title: "demandeur", summary: true, body: () => this.requester, empty: "inconnu" },
            // RM3256 : l'environnement ACTIF selon la phase du ticket vient en tête, marqué — c'est
            // lui qu'on ouvre, les autres sont du contexte. Le panneau de droite portait seul cette
            // distinction ; elle vaut pour toute vue qui montre les environnements.
            { id: "environments", title: "environnements", body: () => {
              const r = this.r || {}, e = this.environments, out = [];
              const a = r.active_env;
              if (a && a.name) out.push([html`<span class="pill ok">${a.name}</span>`, a.url ? html`<a href="${a.url}" target="_blank" rel="noopener">ouvrir ↗</a>` : "—"]);
              if (e && e.test_url) out.push(["test_url", html`<a href="${e.test_url}" target="_blank" rel="noopener">↗</a>`]);
              for (const x of (e ? e.list : []).filter(x => x.url && !(a && x.name === a.name)))
                out.push([x.name || "env", html`<a href="${x.url}" target="_blank" rel="noopener">↗</a>`]);
              return out;
            }, empty: "aucun environnement" },
            // RM3256 : en markdown, et AVEC sa provenance (champ dédié, note de livraison, description).
            // Rendu en <pre>, un protocole écrit en tableau devenait illisible — la fiche du centre le
            // rendait déjà correctement, de son côté ; c'est cette version-là qui devient la seule.
            { id: "protocol", title: "protocole de test", level: "full",
              body: () => (this.protocol
                ? html`<div class="e-src">(${this.protocol.source})</div><div class="mdview">${raw(mdToHtml(this.protocol.text))}</div>`
                : null),
              empty: "aucune section « À tester » dans la note de livraison ni la description (norme RM2229 : toute livraison devrait en inclure une)" },
            // RM3137 : la description est du MARKDOWN, et elle est repliée à la source vers 80 colonnes
            // (c'est la convention d'écriture des fiches). Rendue dans un <pre>, ces retours à la ligne
            // étaient préservés tels quels : le texte se coupait vers 82 caractères quelle que soit la
            // largeur disponible. En markdown, un saut simple joint le paragraphe et c'est la fenêtre
            // qui décide où la ligne s'arrête — les blocs de code, listes et tableaux gardent leur forme.
            { id: "description", title: "description", level: "full", body: () => (r.description ? raw(mdToHtml(r.description)) : null), empty: "pas de description" },
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
      // RM3262 : la signature (« 2026-09-01 · Mathieu ») accompagne chaque entrée — une question
      // sans date ni auteur ne se relit pas. Vide sur un carnet pas encore migré : on n'invente rien.
      id: String(r.id || ""), text: String(r.text || ""), icon: ICON[r.state] || "·", signature: String(r.signature || ""),
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
  /** RM3238 : une MEP prod bloquée par des questions non tranchées se montre verrouillée, questions à
   *  l'appui — le refus du script ne doit pas être la première nouvelle. Le contournement reste en CLI. */
  items() { return (this.e.transitions || []).map(t => { const qs = t.blocked_by_questions || [];
    return { status: String(t.status), refused: t.redmine_ok === false || qs.length > 0, reason: !!t.needs_close_reason, note: !!t.needs_note,
      tip: String(t.condition || "") + (t.redmine_ok === false ? " — Redmine refusera cette transition pour ce compte" : "")
        + (qs.length ? " — bloqué : question(s) non tranchée(s) " + qs.join(", ") + " (à trancher dans 🧠 Réflexion)" : "") }; }); }
}
bindEntity("review", ReviewViewModel);   // RM3002
