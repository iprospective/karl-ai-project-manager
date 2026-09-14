// viewmodels/tickets/MetaViewModel — l'encart ℹ, décidé : la session (infos) et ses tickets (facettes). RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { ENGINE_LABEL, cval, fmtTokens, fmtMin, tmuxName, logEntries, FACETS, facetOf } from "./ticketMeta.js";
import { sinceLabel, modelWindow, ctxPct, throughput, fmtUsd, fmtRate, fmtWin } from "../ticket/ticketFormat.js";

/** La conso live d'une session (RM2373/2609/2611). e = entrée usageCache { usage, meta } ou undefined ; ctx = { registry, ago, now } */
export class UsageViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || { __none: true }, ctx); this.known = !!e; }
  get u() { return this.known ? this.e.usage : undefined; }
  get m() { return this.known ? this.e.meta : null; }
  get reg() { return this.ctx.registry || {}; }
  /** En-tête d'exécution : outil, modèle, coût (RM2609). null tant que le méta n'est pas là. */
  head() {
    const m = this.m; if (!m) return null; const u = this.u, r = m.rates;
    return { engine: ENGINE_LABEL[m.engine] || m.engine || "—", model: m.model || "",
      cost: (m.cost_usd != null && u && u.turns) ? fmtUsd(m.cost_usd) : "", ratesKnown: !!r,
      ratesTip: r ? "tarifs /Mtok — entrée " + fmtRate(r.input_per_mtok_usd) + " · sortie " + fmtRate(r.output_per_mtok_usd) + " · cache lu " + fmtRate(r.cache_read_per_mtok_usd) : "" };
  }
  get kind() { const u = this.u; return u === undefined ? "loading" : u === null ? "unavailable" : !u.turns ? "notranscript" : "ok"; }
  get engineNote() { const u = this.u; return u && u.engine && u.engine !== "claude" ? " (moteur " + u.engine + ")" : ""; }
  /** Les compteurs (RM2519 : total = entrée + sortie, cache hors total ; RM2611 : % contexte, débit). */
  stats() {
    const u = this.u, m = this.m; if (this.kind !== "ok") return null;
    const w = modelWindow(m && m.model, m && m.rates, u.context_last), cp = ctxPct(u.context_last, w);
    const tp = this.reg.created ? throughput(u.total, m && m.cost_usd, Date.parse(this.reg.created), this.now) : null;
    return { total: fmtTokens(u.total), input: fmtTokens(u.input), output: fmtTokens(u.output), cache: fmtTokens(u.cache_read) + " / " + fmtTokens(u.cache_creation),
      context: fmtTokens(u.context_last), contextPct: cp != null ? cp + "% de " + fmtWin(w) : "", turns: u.turns,
      rate: tp ? fmtTokens(tp.tpm) + "/min" + (tp.uph ? " · " + fmtUsd(tp.uph) + "/h" : "") : "" };
  }
  dates() {
    const m = this.m, out = [];
    if (this.reg.created) out.push({ k: "créée", v: this.reg.created });
    if (m && m.updated) out.push({ k: "dernière activité", v: "il y a " + (this.ctx.ago ? this.ctx.ago(m.updated) : "?") });
    return out;
  }
  /** Le récap texte (RM2611) — même source que l'affichage. null si rien n'est chargé. */
  recap(rm) {
    const m = this.m, u = this.u; if (!m) return null;
    const L = ["Session RM" + rm, "outil: " + (ENGINE_LABEL[m.engine] || m.engine || "?")];
    if (m.model) L.push("modèle: " + m.model);
    if (m.cost_usd != null && u && u.turns) L.push("coût: " + fmtUsd(m.cost_usd));
    if (u && u.turns) {
      L.push("tokens: " + u.total + " (entrée " + u.input + " / sortie " + u.output + " ; cache " + u.cache_read + "/" + u.cache_creation + ")");
      const w = modelWindow(m.model, m.rates, u.context_last), cp = ctxPct(u.context_last, w);
      L.push("contexte: " + u.context_last + (cp != null ? " (" + cp + "% de " + fmtWin(w) + ")" : ""));
      L.push("tours: " + u.turns);
      const tp = this.reg.created ? throughput(u.total, m.cost_usd, Date.parse(this.reg.created), this.now) : null;
      if (tp) L.push("débit: " + tp.tpm + " tok/min" + (tp.uph ? " · " + fmtUsd(tp.uph) + "/h" : ""));
    }
    if (this.reg.created) L.push("créée: " + this.reg.created);
    if (m.updated) L.push("dernière activité: il y a " + (this.ctx.ago ? this.ctx.ago(m.updated) : "?"));
    return L;
  }
}

/** L'onglet « infos » : niveau session uniquement (RM2579/2605/2894). e = { s (entrée /sessions), r (résolution), usage } ; ctx = { sid, ago, now } */
export class SessionInfosViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get sid() { return this.ctx.sid == null ? "" : String(this.ctx.sid); }
  get attached() { return !!this.sid; }
  get s() { return this.e.s || {}; }
  /** RM2894 : le libellé — sujet Redmine si la session est ancrée sur un ticket, sinon titre du transcript. */
  get label() { const r = this.e.r; return (r && r.found && r.title) ? String(r.title) : String(this.s.title || ""); }
  get tmux() { return tmuxName(this.sid); }
  /** RM2605 : les branches vivent dans l'onglet git, les worktrees dans l'onglet fichiers — « infos » garde ce qui n'appartient qu'à la session. */
  get registry() { const reg = this.s.registry; return reg ? { seq: reg.seq, machine: reg.machine || "", created: reg.created || "" } : null; }
  get conflicts() { return (this.s.registry_conflicts || []).map(c => ({ rm: String(c.rm_id), seqs: (c.seqs || []).map(x => "#" + x).join(", ") })); }
  usage() { return new UsageViewModel(this.e.usage, { registry: this.s.registry || {}, ago: this.ctx.ago, now: this.ctx.now }); }
}

/** RM2614 : situer le ticket dans son client et son projet. e = { client, project, card } — card null tant que la fiche n'est pas chargée. */
export class ProjectBriefViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get shown() { return !!(this.e.client && this.e.project); }
  get key() { return this.e.client + "/" + this.e.project; }
  get c() { return this.e.card || {}; }
  get clientName() { return cval(this.c.client_name) || this.e.client; }
  get clientId() { return cval(this.c.client_redmine_project_id); }
  get name() { return cval(this.c.name) || this.e.project; }
  get redmineUrl() { return cval(this.c.redmine_project_url); }
  get open() { return this.c.open_by_status ? Object.values(this.c.open_by_status).reduce((a, b) => a + b, 0) : null; }
  get total() { return this.c.total || 0; }
  get repo() { return cval(this.c.gitlab_repo); }
  get branch() { return cval(this.c.default_branch); }

  /** RM3126 — le PROVIDER qui porte ce ticket : quelle instance de gestion, et les secondaires
   *  déclarés du projet. Évident tant qu'il n'y en avait qu'une ; plus du tout depuis que l'axe
   *  `task` est une liste. `null` si le serveur ne l'a pas résolu — on ne devine pas une
   *  instance, se tromper dirigerait les appels et le jeton vers la mauvaise. */
  get provider() {
    const p = this.e.provider;
    if (!p || !p.name) return null;
    return { name: p.name, type: p.type || "", url: p.url || "", slug: p.slug || "",
             secondaries: p.secondaries || [] };
  }
}

/** L'onglet « tickets » : sous-onglets par ticket, puis facette (RM2579/2673/2797).
 *  e = { tickets (de la session), current, facet, resolve (cache), attached, worklogSeen, ws, card } ; ctx = { now } */
export class TicketMetaViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  /** Un ticket ouvert hors session (fiche revue / file à tester) reste visible. */
  get list() { const l = (this.e.tickets || []).map(String); const cur = this.e.current; if (cur && l.indexOf(String(cur)) < 0) l.unshift(String(cur)); return l; }
  get sel() { const l = this.list, cur = this.e.current == null ? null : String(this.e.current); return (cur && l.indexOf(cur) >= 0) ? cur : (l[0] || null); }
  get facet() { return facetOf(this.e.facet); }
  /** RM3164 — le projet d'un ticket, depuis le cache de résolution. "" si on ne le sait pas
   *  encore : un ticket non résolu ne doit pas se retrouver rangé sous un projet au hasard. */
  projectOf(rm) {
    const r = (this.e.resolve || {})[String(rm)];
    return (r && r.found && r.client && r.project) ? r.client + "/" + r.project : "";
  }

  /** Les projets représentés dans la liste, avec leur compte. Vide quand ils sont TOUS dans le
   *  même : proposer un filtre à une seule valeur, c'est occuper la place sans rien trier. */
  get ticketProjects() {
    const n = {};
    for (const rm of this.list) { const p = this.projectOf(rm); if (p) n[p] = (n[p] || 0) + 1; }
    const cles = Object.keys(n);
    if (cles.length < 2) return [];
    const f = this.ctx.ticketFilter || "";
    return cles.sort().map(k => ({ key: k, n: n[k], active: k === f }));
  }

  /** Le filtre EFFECTIF : celui qu'on a posé, sinon le projet de la session attachée s'il est
   *  représenté — c'est le défaut demandé, et il évite de faire chercher le contexte courant. */
  get ticketFilter() {
    const f = this.ctx.ticketFilter;
    if (f !== undefined && f !== null) return f;
    const sess = this.e.sessionProject || "";
    return this.ticketProjects.some(p => p.key === sess) ? sess : "";
  }

  get tabs() {
    const s = this.sel, f = this.ticketFilter;
    return this.list
      .filter(t => !f || this.projectOf(t) === f || t === s)   // l'onglet courant reste visible
      .map(t => ({ rm: t, active: t === s, project: this.projectOf(t) }));
  }

  /** RM3126 : le titre du ticket sélectionné, pour la ligne entre la liste et les onglets.
   *  Vide tant qu'il n'est pas chargé — une ligne de titre qui clignote « … » à chaque
   *  changement d'onglet serait pire que pas de ligne du tout. */
  get currentTitle() { const r = this.r; return (r && r.found && r.title) ? String(r.title) : ""; }
  get facets() { const f = this.facet; return FACETS.map(x => ({ key: x[0], label: x[1], active: x[0] === f })); }
  /** Rien à montrer : dire ce qui a VRAIMENT été regardé — le worklog compris (RM2673). */
  get emptyKind() { const a = this.e.attached; if (!a) return "none"; if (/^\d+$/.test(String(a))) return "untracked"; return this.e.worklogSeen ? "slug-empty" : "slug-loading"; }
  get r() { const s = this.sel; return s ? (this.e.resolve || {})[s] : undefined; }
  get kind() { if (!this.list.length) return "empty"; const r = this.r; if (r === undefined) return "loading"; if (!r || !r.found) return "notfound"; return this.facet; }
  detail() {
    const r = this.r, rm = this.sel, stamp = (r.updated || r.mtime) || "";
    const envs = [];
    if (r.active_env) envs.push({ kind: "active", name: r.active_env.name, url: r.active_env.url || "" });
    if (r.test_url) envs.push({ kind: "test_url", name: "test_url", url: r.test_url });
    (r.environments || []).filter(e => e.url && (!r.active_env || e.name !== r.active_env.name)).forEach(e => envs.push({ kind: "other", name: e.name, url: e.url }));
    const rels = [];
    if (r.parent_task) rels.push({ label: "parent", ids: [r.parent_task] });
    if (r.depends_on && r.depends_on.length) rels.push({ label: "dépend de", ids: r.depends_on });
    if (r.blocks && r.blocks.length) rels.push({ label: "bloque", ids: r.blocks });
    if (r.relates && r.relates.length) rels.push({ label: "lié", ids: r.relates });
    if (r.sub_tasks && r.sub_tasks.length) rels.push({ label: "sous-tâches", ids: r.sub_tasks });
    return { rm, redmineUrl: r.redmine_url || "", title: r.title || "", type: r.type || "—", status: r.status || "", closed: r.status === "ferme",
      priority: r.priority || "—", pct: r.completion_pct != null ? r.completion_pct + " %" : "—",
      freshness: stamp ? { stamp, since: sinceLabel(stamp, this.now) } : null, envs,
      git: (r.git && (r.git.branch || r.git.mr_url)) ? { branch: r.git.branch || "", mrUrl: r.git.mr_url || "" } : null,
      rels: rels.map(x => ({ label: x.label, ids: x.ids.map(String) })), hasDesc: !!r.description, hasLog: !!r.log_tail };
  }
  brief() { const r = this.r || {}; return new ProjectBriefViewModel({ client: r.client, project: r.project, card: this.e.card, provider: r.provider }); }
  desc() { const r = this.r; return (r && r.description) || ""; }
  log() { return logEntries(this.r && this.r.log_tail); }
  /** RM2173/2373/2519 : la conso ENREGISTRÉE par le PM (≠ conso live de l'onglet infos). */
  conso() {
    const m = (this.r && this.r.metrics) || {};
    if (m.tokens_total == null && m.cost_total_usd == null) return null;
    const bd = m.tokens_breakdown || {}, hasBd = !!(bd.input || bd.output || bd.cache_read || bd.cache_creation);
    const tokTot = hasBd ? ((bd.input || 0) + (bd.output || 0)) : m.tokens_total;
    return { total: fmtTokens(tokTot), breakdown: hasBd ? { input: fmtTokens(bd.input), output: fmtTokens(bd.output), cache: fmtTokens(bd.cache_read) + " / " + fmtTokens(bd.cache_creation) } : null,
      cost: m.cost_total_usd != null ? "$" + Number(m.cost_total_usd).toFixed(2) : "—", ai: fmtMin(m.ai_time_total_minutes), human: fmtMin(m.human_time_total_minutes), updated: m.updated || "—" };
  }
  /** RM3164 — les sessions qui traitent ce ticket. `null` tant qu'on ne sait pas (en vol) :
   *  la vue montre « … » plutôt qu'un « aucune session », qui serait un mensonge pendant le
   *  chargement — et c'est exactement le moment où l'on regarde. */
  ticketSessions() {
    const d = this.e.ts;
    if (d === undefined || d === null) return { kind: d === null ? "loading" : "none" };
    if (d.error) return { kind: "error" };
    const rows = (d.handled || []).map(s => ({
      sid: String(s.rm_id || s.sid || s.name || ""), name: s.name || s.title || String(s.rm_id || ""),
      alive: !!s.alive, title: s.title || "",
    })).filter(r => r.sid);
    return { kind: rows.length ? "ok" : "empty", rows, candidates: (d.candidates || []).length };
  }

  /** RM3164 — l'impact du ticket : fichiers touchés, agrégés. Mêmes trois états que les
   *  sessions : « pas demandé », « en vol » et « inconnu » ne se disent pas pareil. */
  impact() {
    const d = this.e.imp;
    if (d === undefined || d === null) return { kind: d === null ? "loading" : "none" };
    if (d.error) return { kind: "error" };
    if (d.pm_data_repo) return { kind: "pmdata" };
    if (!d.is_git) return { kind: "nogit" };
    return { kind: (d.files || []).length ? "ok" : "empty", files: d.files || [],
             commits: d.commits || 0, base: d.base || "", branch: d.branch || "",
             total: d.total_files || 0 };
  }

  workspace() {
    const ws = this.e.ws;
    if (ws === undefined) return { kind: "loading" };
    if (!ws || !ws.is_git) return { kind: "nogit" };
    return { kind: "git", branch: ws.branch || "", clean: !!ws.clean, dirty: ws.dirty || 0, untracked: ws.untracked || 0, ahead: ws.ahead || 0, behind: ws.behind || 0 };
  }
}
