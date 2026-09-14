// modules/modules/modules.service — l'état du panneau « Modules ». RM3145.
import { ModulesRepository } from "./ModulesRepository.js";

export class ModulesService {
  constructor({ repo = new ModulesRepository() } = {}) { this.repo = repo; this.data = null; this.error = null; }
  async load() {
    try { this.data = await this.repo.list(); this.error = null; }
    catch (e) { this.data = null; this.error = e.message; }
    return this.data;
  }
}
