// services/newticket.service — RM2889.
import { TicketsRepository } from "./TicketsRepository.js";
import { buildTicketBody } from "./newTicket.js";
export class NewTicketService {
  constructor(repo = new TicketsRepository()) { this.repo = repo; }
  /** Valide puis crée. Rend {ok, rm_id, message} — ne lève pas. */
  async create(values) {
    const b = buildTicketBody(values || {});
    if (b.error) return { ok: false, message: b.error };
    try { const r = await this.repo.create(b.body); return { ok: true, rm_id: String(r.rm_id), message: "Ticket RM" + r.rm_id + " créé" }; }
    catch (e) { return { ok: false, message: e.message }; }
  }
}
