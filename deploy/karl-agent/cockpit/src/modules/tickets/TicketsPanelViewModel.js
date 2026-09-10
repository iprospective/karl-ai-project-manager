// viewmodels/tickets/TicketsPanelViewModel — la carte des tickets ouverts et le triage ROI, décidés. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { groupOpenedTickets, openedCountLabel } from "./openedTickets.js";
import { triageFilter, triageClients, triageProjects } from "./triage.js";

/** e = { ids, cache (résolutions), client, family } */
export class OpenedViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.g = groupOpenedTickets(this.e.ids, this.e.cache, this.e.client || null, this.e.family || null); }
  get total() { return (this.e.ids || []).length; }
  get shown() { return this.g.keys.reduce((n, k) => n + this.g.groups.get(k).length, 0); }
  get countLabel() { return openedCountLabel(this.shown, this.total); }
  get clients() { return this.g.clients.map(c => ({ key: c, active: this.e.client === c })); }
  get clientAll() { return !this.e.client; }
  get families() { return this.g.families.map(f => ({ key: f.key, label: f.label, n: f.n, active: this.e.family === f.key })); }
  get familyAll() { return !this.e.family; }
  groups() { return this.g.keys.map(k => ({ key: k, label: k === "…" ? "en cours de résolution" : k, items: this.g.groups.get(k).map(it => ({ rm: it.rm_id, status: it.status, title: it.title || (it.resolved ? "" : "chargement…") })) })); }
}

/** e = { tickets (du serveur), client, project, hideValid, tag } */
export class TriageViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.rows = triageFilter(this.e.tickets, this.e.client, this.e.project, this.e.hideValid, this.e.tag); }
  get clients() { return triageClients(this.e.tickets); }
  get projects() { return triageProjects(this.e.tickets, this.e.client); }
  get count() { return this.rows.length; }
  get shown() { return this.rows.slice(0, 60).map((e, i) => this.row(e, i + 1)); }
  get more() { return Math.max(0, this.rows.length - 60); }
  row(e, rank) {
    const badges = [];
    if (e.unblocks) badges.push({ cls: "tr-unblock", tip: "débloque " + e.unblocks + " ticket(s) ouvert(s)", text: "🔓 " + e.unblocks });
    if (e.awaiting_validation) badges.push({ cls: "tr-valid", tip: "en attente de validation", text: "⏳" });
    if (e.blocked) badges.push({ cls: "tr-blocked", tip: "bloqué par : " + (e.blocked_by || []).join(", "), text: "⛔" });
    return { rank, rm: String(e.rm_id), score: String(e.score), title: e.title || "", status: e.status || "", priority: String(e.priority || ""), time: e.time_minutes ? Math.round(e.time_minutes) + " min" : "", badges };
  }
}
