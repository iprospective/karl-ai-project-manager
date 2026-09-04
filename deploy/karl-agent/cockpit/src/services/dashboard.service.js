// services/dashboard.service — les données du tableau de bord. RM2889, L4.
//
// Deux sources pour le même état : le recalcul forcé (deux GET) et le bloc
// `dashboard` poussé par la pile /refresh (RM2763), que le monolithe lui
// remet via setBlock. Le service tient l'état ; le contrôleur le rend.
import { DashboardRepository } from "../models/dashboard/DashboardRepository.js";

export class DashboardService {
  constructor(repo = new DashboardRepository()) {
    this.repo = repo;
    this.overview = { projects: [] };
    this.alerts = { alerts: [] };
  }
  async reload() {
    try { this.overview = await this.repo.overview(); this.alerts = await this.repo.alerts(); }
    catch (e) { this.overview = { projects: [], error: e.message }; this.alerts = { alerts: [] }; }
    return this;
  }
  /** Bloc `dashboard` de /refresh : {overview, alerts}. */
  setBlock(data) { this.overview = (data && data.overview) || { projects: [] }; this.alerts = (data && data.alerts) || { alerts: [] }; return this; }
  async snooze(key) {
    try { await this.repo.snooze(key, 7); return { ok: true, message: "⏳ alerte reportée de 7 jours — elle reviendra" }; }
    catch (e) { return { ok: false, message: e.message }; }
  }
}
