// services/health — l'état de santé du PM, tenu par deux voies (RM3369).
// Le bloc `pmhealth` de la pile /refresh alimente le badge ; la page complète est
// un appel direct, fait à l'ouverture. Aucun calcul ici : le serveur lit un
// rapport produit en tâche de fond, le front ne fait que le montrer.
import { HealthRepository } from "./HealthRepository.js";

export class HealthService {
  constructor(repo = new HealthRepository()) { this.repo = repo; this.check = null; this.status = null; }
  setBlock(data) { this.check = data; return this; }
  async reloadCheck() { try { this.check = await this.repo.check(); } catch (e) { /* badge muet */ } return this.check; }
  async loadStatus(force) { if (force || !this.status) this.status = await this.repo.status(); return this.status; }
}
