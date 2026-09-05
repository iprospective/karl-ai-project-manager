// models/tickets/TicketsPanelRepository — ce que le panneau 🎫 tickets va chercher : le classement ROI (RM1952)
// et les briefs de tickets par lot (RM2619, regroupés : vingt RM-id affichés au même rendu = une requête). RM2889.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get } from "../../core/api.js";
import { pendingBriefIds } from "./briefs.js";

export class TicketsPanelRepository extends Repository {
  constructor({ delay = 120, timers = { set: (fn, ms) => setTimeout(fn, ms) } } = {}) {   // jamais `setTimeout` nu : appelé comme méthode, un navigateur refuse (« Illegal invocation »)
    super({ name: "tickets-panel", ttl: 30000, max: 50, factory: new Factory({ type: "ticket-brief" }), routes: { triage: "ticket.triage", brief: "ticket.brief" } });
    this.briefs = {};                 // rm_id → brief (ou {found:false})
    this.inflight = new Set(); this.queue = new Set(); this.timer = null; this.delay = delay; this.timers = timers;
  }
  triage() { return get(this.path("triage")); }
  brief(id) { return this.briefs[String(id)]; }
  /** Demandes groupées : un court délai rassemble tout ce qu'un rendu affiche. `onLoad` après chaque lot reçu. */
  requestBriefs(ids, onLoad) {
    for (const id of pendingBriefIds(ids, this.briefs, this.inflight)) this.queue.add(id);
    if (!this.queue.size || this.timer) return false;
    this.timer = this.timers.set(async () => {
      this.timer = null;
      const lot = [...this.queue].slice(0, 100); this.queue.clear();
      lot.forEach(id => this.inflight.add(id));
      try {
        const r = await get(this.path("brief") + "?ids=" + encodeURIComponent(lot.join(",")));
        Object.assign(this.briefs, r.tickets || {});
        lot.forEach(id => { if (this.briefs[id] === undefined) this.briefs[id] = { found: false, rm_id: id }; });   // jamais redemandé en boucle
        if (onLoad) onLoad();
      } catch (e) {
        lot.forEach(id => { this.briefs[id] = { found: false, rm_id: id, error: true }; });
      } finally { lot.forEach(id => this.inflight.delete(id)); }
    }, this.delay);
    return true;
  }
}
