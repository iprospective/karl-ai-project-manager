// modules/monitor/MonitorRepository — l'observateur du parc : alertes situées, hôtes, association. RM3112.
// Le cockpit ne parle jamais à l'outil de supervision : il parle au serveur, qui sait quel observateur
// répond et détient sa clé. Aucun jeton ne descend jusqu'ici.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class MonitorRepository extends Repository {
  constructor() { super({ name: "monitor", ttl: 30000, max: 5, factory: new Factory({ type: "alert" }),
    routes: { alerts: "monitor.alerts", hosts: "monitor.hosts", assign: "monitor.assign", ticket: "monitor.ticket" } }); }
  async alerts({ severity = 0, limit = 200 } = {}) { return await get(this.path("alerts") + `?severity=${severity}&limit=${limit}`); }
  async hosts() { return await get(this.path("hosts")); }
  /** Confirme l'association d'un hôte ; `client` vide la retire. */
  async assign(body) { return await post(this.path("assign"), body); }
  /** Ouvre un ticket depuis une alerte, dans le client/projet donné — jamais deviné ici. */
  async ticket(body) { return await post(this.path("ticket"), body); }
}
