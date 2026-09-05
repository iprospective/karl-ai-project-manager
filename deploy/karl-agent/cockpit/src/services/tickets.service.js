// services/tickets.service — le panneau 🎫 tickets : liste des tickets ouverts (persistée), triage, briefs. RM2889.
import { TicketsPanelRepository } from "../models/tickets/TicketsPanelRepository.js";
import { openedAdd } from "../models/tickets/openedTickets.js";

export class TicketsPanelService {
  constructor({ repo = new TicketsPanelRepository(), storage = null } = {}) {
    this.repo = repo; this.storage = storage; this.triageData = null;
    this.opened = this._read("karlOpenedTickets", []);
  }
  _read(k, dflt) { try { const v = this.storage && this.storage.getItem(k); return v == null ? dflt : (k === "karlOpenedTickets" ? JSON.parse(v) : v); } catch (e) { return dflt; } }
  _write(k, v) { try { if (this.storage) this.storage.setItem(k, v); } catch (e) { /* mode privé */ } }
  // ── tickets ouverts (RM2606) ──────────────────────────────────────────────
  /** Rend vrai si la liste a changé (ordre compris) — c'est alors qu'on la sauve. */
  note(id) { const avant = this.opened; this.opened = openedAdd(avant, id, 40); const changed = this.opened.length !== avant.length || String(this.opened[0]) !== String(id) || avant[0] !== this.opened[0]; if (changed) this.save(); return changed; }
  forget(id) { this.opened = this.opened.filter(x => String(x) !== String(id)); this.save(); }
  clear() { this.opened = []; this.save(); }
  save() { this._write("karlOpenedTickets", JSON.stringify(this.opened)); }
  cardOpen() { return this._read("karlOpenedCard", null); }
  rememberCard(open) { this._write("karlOpenedCard", open ? "1" : "0"); }
  // ── triage (RM1952) ───────────────────────────────────────────────────────
  async loadTriage(force) { if (this.triageData && !force) return this.triageData; this.triageData = await this.repo.triage(); return this.triageData; }
  get triageTickets() { return (this.triageData && this.triageData.tickets) || []; }
  // ── briefs (RM2619) ───────────────────────────────────────────────────────
  brief(id) { return this.repo.brief(id); }
  requestBriefs(ids, onLoad) { return this.repo.requestBriefs(ids, onLoad); }
}
