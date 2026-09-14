// modules/engines/engines.service — l'état du panneau Moteurs. RM3069.
import { EnginesRepository } from "./EnginesRepository.js";

export class EnginesService {
  constructor({ repo = new EnginesRepository() } = {}) { this.repo = repo; this.data = null; this.launch = null; }
  async load() {
    this.data = await this.repo.list();
    // RM3139 : le panneau montre l'installation ET le lancement. Un catalogue d'options
    // indisponible ne doit pas emporter le panneau entier : on le dit, et le reste s'affiche.
    try { this.launch = await this.repo.options(); } catch (e) { this.launch = { engines: [], error: e.message }; }
    return this.data;
  }
  async run(body) { const r = await this.repo.run(body); if (!body.dry_run) await this.load(); return r; }
  async saveOptions(body) { const r = await this.repo.saveOptions(body); await this.load(); return r; }
}
