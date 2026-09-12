// modules/monitor/monitor.service — l'état du panneau supervision. RM3112.
import { MonitorRepository } from "./MonitorRepository.js";

export class MonitorService {
  constructor({ repo = new MonitorRepository() } = {}) {
    this.repo = repo; this.data = null; this.hosts = null; this.error = null;
  }
  async load(opts) {
    try { this.data = await this.repo.alerts(opts); this.error = null; }
    catch (e) { this.data = null; this.error = e.message; }
    return this.data;
  }
  async loadHosts(force) { if (!this.hosts || force) this.hosts = await this.repo.hosts(); return this.hosts; }
  async assign(body) { const r = await this.repo.assign(body); this.hosts = null; this.data = null; return r; }
  async ticket(body) { return await this.repo.ticket(body); }
}
