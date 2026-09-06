// models/tickets/TicketsRepository — création (et, à venir, lecture) des tickets. RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { post } from "../../core/api.js";

export class TicketsRepository extends Repository {
  constructor() { super({ name: "tickets", ttl: 5000, max: 50, factory: new Factory({ type: "ticket", required: ["rm_id"] }), routes: { list: "ticket.tickets" } }); }
  /** POST /tickets → { rm_id, … }. */
  async create(body) { const r = await post(this.path("list"), body); this.store.invalidate(); return r; }
}
