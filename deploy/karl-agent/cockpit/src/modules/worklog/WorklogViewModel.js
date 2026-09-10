// viewmodels/worklog/WorklogViewModel — le worklog de la session et ses écrans de lot, décidés. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { worklogSections, worklogDocs, worklogTabList, notifyDecor, groupWorklogItems, mrStage, statusInfo, worklogProgress, branchesByRm, isTicketRef, refId, mrCycle, mrTodoCount, MR_GROUPS } from "./worklog.js";

/** e = { data (worklog), attached, branches (registre), selected (Set de refs), sub } ; ctx = { ago } */
export class WorklogViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.w = this.e.data || {}; this.secs = worklogSections(this.w.buckets); this.docs = worklogDocs(this.w.docs); this.brByRm = branchesByRm(this.e.branches); this.used = new Set(); }
  get attached() { return !!this.e.attached; }
  get fresh() { return (this.attached && this.w.checked_ts && this.ctx.ago) ? "vérifié " + this.ctx.ago(this.w.checked_ts) : ""; }
  notifications() { return (this.w.notifications || []).map(n => { const d = notifyDecor(n.level); return { icon: d.icon, cls: d.cls, label: d.label, kind: (n.kind && n.kind !== "autre") ? n.kind : "", ref: n.ref || "", message: n.message || "", ts: n.ts || "" }; }); }
  get notificationsDone() { return (this.w.notifications_done || []).length; }
  mrs() { return (this.w.mrs_pending || []).map(m => mrLine(m)); }
  /** RM3074 : le cycle complet, groupé — l'onglet MR. `integration` vient de la conf du projet. */
  get mrTodo() { return mrTodoCount(this.w.mrs_all || this.w.mrs_pending, this.ctx.integration); }
  mrGroups() {
    const cycle = mrCycle(this.w.mrs_all || this.w.mrs_pending, this.ctx.integration);
    return MR_GROUPS.map(g => ({ key: g.key, icon: g.icon, label: g.label, hint: g.hint,
      rows: (cycle[g.key] || []).map(m => mrDetail(m, this.ctx)) })).filter(g => g.rows.length);
  }
  requests() { return (this.w.requests_open || []).map(r => ({ n: String(r.n), text: r.text || "", ts: r.ts || "" })); }
  get nTickets() { return this.secs.reduce((a, s) => a + s.items.length, 0); }
  /** Rien à montrer — ni ticket, ni document, ni branche. Le message distingue « worklog vide » de « pas de worklog » (la garde legacy `!found` rendait la première formulation inatteignable). */
  get empty() { return !this.nTickets && !this.docs.length && !(this.e.branches || []).length && !this.mrTodo; }
  get emptyText() { return this.w.found ? "aucun ticket ouvert dans cette session" : "pas de worklog pour cette session (rien n’a encore été ouvert)"; }
  /** Une ligne de ticket : tout ce que la vue affiche, rien qu'elle n'ait à décider. */
  item(it) {
    const ref = String(it.ref || ""), ticket = isTicketRef(ref), brs = this.brByRm[ref] || [];
    brs.forEach(b => this.used.add(b));
    return { ref, rm: ticket ? refId(ref) : "", ticket, label: it.label || "", next: it.next || "", note: it.note || "", branches: brs, selected: !!(this.e.selected && this.e.selected.has(ref)),
      status: statusInfo(it), stage: mrStage((this.w.mr_stage || {})[ref]), progress: worklogProgress(it), points: { points: ((it.checklist || {}).items || []).slice(), points_truncated: !!(it.checklist || {}).truncated } };
  }
  /** RM2798 : par client/projet dans chaque statut ; un seul groupe ⇒ pas d'en-tête. */
  buckets() { const out = {}; for (const s of this.secs) { const groupes = groupWorklogItems(s.items); out[s.key] = groupes.length <= 1 ? [{ key: null, items: s.items.map(it => this.item(it)) }] : groupes.map(g => ({ key: g.key, items: g.items.map(it => this.item(it)) })); } return out; }
  orphans() { return (this.e.branches || []).filter(b => !this.used.has(b)); }
  tabs(orphanCount) { const tabs = worklogTabList(this.secs, this.docs.length, orphanCount, this.mrTodo); let sub = this.e.sub; if (!tabs.some(t => t.key === sub)) sub = tabs.length ? tabs[0].key : "documents"; return { tabs: tabs.map(t => ({ key: t.key, label: t.label, n: t.n, active: t.key === sub })), sub }; }
  /** RM2935 : les documents groupés par ticket, noms débarrassés de leurs quotes YAML. */
  docGroups() { const out = []; let cur = null; for (const d of this.docs) { if (!cur || cur.ref !== d.ref) { cur = { ref: String(d.ref == null ? "" : d.ref), rm: isTicketRef(d.ref) ? refId(d.ref) : "", docs: [] }; out.push(cur); } cur.docs.push({ name: String(d.name == null ? "" : d.name).replace(/^['"]|['"]$/g, ""), kind: d.kind || "" }); } return out; }
}
/** RM2723 : une ligne « MR à merger » — le bouton n'existe que s'il y a une URL (c'est elle qui identifie la MR pour pm-mr). */
export function mrLine(m) { const mr = m || {}; return { iid: String(mr.iid || "?"), ref: mr.ref ? String(mr.ref) : "", target: mr.target ? String(mr.target) : "", url: mr.url ? String(mr.url) : "", dead: mr.alive === false }; }

/** RM3074 — une MR détaillée : tout ce que l'onglet affiche, rien que la vue ait à décider. */
export function mrDetail(m, ctx) {
  const mr = m || {}, ago = (ctx && ctx.ago) ? ctx.ago : null;
  const state = String(mr.state || "opened").toLowerCase();
  return { iid: String(mr.iid || "?"), ref: mr.ref ? String(mr.ref) : "", rm: isTicketRef(mr.ref) ? refId(mr.ref) : "",
    repo: mr.repo ? String(mr.repo) : "", source: mr.source ? String(mr.source) : "", target: mr.target ? String(mr.target) : "",
    url: mr.url ? String(mr.url) : "", state, stage: String(mr.stage || ""), dead: mr.alive === false,
    age: (ago && mr.ts) ? ago(mr.ts) : "",
    mergeable: state === "opened" || state === "open" || state === "reopened" };
}

/** RM2716/2719/2720 : le récapitulatif AVANT envoi. e = plan du serveur ; ctx = { mode } */
export class BatchPlanViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get todo() { return (this.e.todo || []).map((t, i) => ({ n: i + 1, rm: String(t.rm_id), status: String(t.status || ""), title: String(t.title || ""), instruction: String(t.instruction || ""), points: (t.points || []).map((p, j) => ({ j, text: String(p) })), truncated: !!t.points_truncated })); }
  get skipped() { return (this.e.skipped || []).map(s => ({ rm: String(s.rm_id), title: String(s.title || ""), reason: String(s.reason || "") })); }
  get big() { return (this.e.todo || []).length > 10; }
  get prompt() { return String(this.e.prompt || ""); }
}
/** RM2720 : l'écran d'un lot de merges — vers où, ce qui est écarté, et qu'une promotion emporte tout dev. */
export class MrBatchViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get prod() { return this.e.mode === "prod"; }
  get title() { return (this.prod ? "⇥ promotion en production" : "⇥ merge dans l’intégration") + " (" + (this.e.runs || []).length + ")"; }
  get runs() { return (this.e.runs || []).map(r => ({ rms: (r.rm_ids || []).map(String), source: String(r.source || ""), target: String(r.target || "") })); }
  get source() { return String(((this.e.runs || [])[0] || {}).source || "dev"); }
  get live() { return (this.e.live || []).map(String); }
  get skipped() { return (this.e.skipped || []).map(k => ({ rm: String(k.rm_id), reason: String(k.reason || "") })); }
}
