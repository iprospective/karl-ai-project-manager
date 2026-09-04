// viewmodels/dashboard/DashboardViewModel — le tableau de bord, décidé. RM2889, L4.
//
// Ce que renderDashboard, attentionHtml et alertsHtml décidaient en plein
// balisage : lignes classées, filtres, compte par nature, plafond de 5 par
// section (RM2697), alertes datées (RM2698). Inerte.
import { EntityViewModel } from "../EntityViewModel.js";
import { attentionRows } from "../../models/dashboard/attention.js";

export const LABEL = { question: "une session attend ta réponse", test: "livré, attend ton verdict",
  mr: "MR ouverte, pas mergée", mep: "attend sa mise en production",
  idle: "session au repos, travail en cours", request: "demande pas encore ticketée" };
export const ICON = { question: "⚠", test: "🧪", mr: "🔀", mep: "🚀", idle: "💤", request: "📥" };
const ALERT_ICON = { orphan: "💤", verdict: "🧪", mep: "🚀", mr: "🔀" };
export const CAP = 5;

export class DashboardViewModel extends EntityViewModel {
  /** e = { overview, alerts } ; ctx = { sessions, stale, filter: {client, project}, nameOf } */
  get filter() { return this.ctx.filter || { client: "", project: "" }; }
  get rows() {
    if (!this._rows) this._rows = attentionRows(this.e.overview, this.ctx.sessions,
      { client: this.filter.client, project: this.filter.project, stale: [...(this.ctx.stale || [])], nameOf: this.ctx.nameOf });
    return this._rows;
  }
  get clients()  { return [...new Set((this.e.overview.projects || []).map(g => g.client))].sort(); }
  get projects() { return [...new Set((this.e.overview.projects || []).filter(g => !this.filter.client || g.client === this.filter.client).map(g => g.project))].sort(); }
  get counts()   { const c = {}; this.rows.forEach(r => { c[r.kind] = (c[r.kind] || 0) + 1; }); return c; }
  /** Sections par nature d'attente : les CAP plus anciennes, et le reste ANNONCÉ. */
  sections() {
    const counts = this.counts, out = []; let cur = null;
    for (const r of this.rows) {
      if (!cur || cur.kind !== r.kind) { cur = { kind: r.kind, label: LABEL[r.kind] || r.kind, total: counts[r.kind], rows: [] }; out.push(cur); }
      if (cur.rows.length < CAP) cur.rows.push({ ...r, action: r.kind === "mr" && r.url ? "open" : r.sid ? "attach" : r.rm_id ? "review" : null });
    }
    for (const s of out) s.more = s.total - s.rows.length;
    return out;
  }
  chips() { const c = this.counts; return Object.keys(c).map(k => ({ kind: k, icon: ICON[k] || "•", count: c[k], label: LABEL[k] || k })); }
  get alertTotal() { const a = this.e.alerts || {}; return a.total || (a.alerts || []).length; }
  get alertHidden() { return (this.e.alerts || {}).hidden || 0; }
  alerts() {
    return ((this.e.alerts || {}).alerts || []).map(a => ({ ...a, icon: ALERT_ICON[a.kind] || "⚠", age: Math.round(a.age_days || 0),
      who: String((a.client || "") + "/" + (a.project || "")) }));
  }
  get hasContent() { return this.rows.length > 0 || this.alerts().length > 0; }
}
