// modules/engines/engines.service — l'état du panneau Moteurs. RM3069.
import { EnginesRepository } from "./EnginesRepository.js";

export class EnginesService {
  constructor({ repo = new EnginesRepository() } = {}) { this.repo = repo; this.data = null; }
  async load() { this.data = await this.repo.list(); return this.data; }
  async run(body) { const r = await this.repo.run(body); if (!body.dry_run) await this.load(); return r; }
}
