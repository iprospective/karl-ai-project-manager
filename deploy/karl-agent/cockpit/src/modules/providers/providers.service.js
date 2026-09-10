// modules/providers/providers.service — l'état du panneau Fournisseurs : catalogue, instances, affectations. RM3068.
import { ProvidersRepository } from "./ProvidersRepository.js";

export class ProvidersService {
  constructor({ repo = new ProvidersRepository() } = {}) { this.repo = repo; this.cat = null; this.data = null; this.error = null; this.models = {}; }
  async load(force) {
    if (!this.cat || force) this.cat = await this.repo.types();
    this.data = await this.repo.list();
    return this.data;
  }
  async save(body) { const r = await this.repo.save(body); await this.load(); return r; }
  async secret(body) { const r = await this.repo.secret(body); await this.load(); return r; }
  async assign(body) { const r = await this.repo.assign(body); await this.load(); return r; }
  /** Les modèles d'une instance, gardés le temps du panneau : c'est un appel réseau vers un tiers. */
  async loadModels(instance, body) { const r = await this.repo.models(body || { instance }); this.models[instance] = r; return r; }
}
