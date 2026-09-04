// models/dashboard/DashboardRepository — vue d'ensemble, alertes, report. RM2889, L4.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get, post } from "../../core/api.js";

export class DashboardRepository extends Repository {
  constructor() {
    super({ name: "dashboard", ttl: 15000, max: 4, factory: new Factory({ type: "overview", defaults: { projects: [] } }),
            routes: { overview: "dashboard.overview", alerts: "dashboard.alerts", snooze: "dashboard.snooze" } });
  }
  /** Recalcul forcé côté serveur — le rafraîchissement courant passe par la pile /refresh. */
  overview() { return get(this.path("overview") + "?force=1"); }
  alerts()   { return get(this.path("alerts")); }
  /** Reporte une alerte : jamais de suppression, sinon on institutionnalise l'oubli (RM2698). */
  snooze(key, days = 7) { return post(this.path("snooze"), { key, days }); }
}
