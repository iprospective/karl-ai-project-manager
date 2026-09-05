// services/pm.service — le runner PM partagé (fiche, revue, worklog, lanceur, file à tester, commandes) : une commande, ses arguments,
// une confirmation explicite ; le ticket touché voit sa résolution invalidée (le prochain ensureResolved la relit). RM2889.
import { PmRepository } from "../models/pm/PmRepository.js";

export class PmService {
  constructor({ repo = new PmRepository(), caches = {} } = {}) { this.repo = repo; this.caches = caches; }
  async run(name, args, opts) {
    const body = { name, args };
    if (opts && opts.confirm) body.confirm = true;
    const res = await this.repo.run(body);
    const rm = args && (args.rm_id || args.rmId);
    if (rm !== undefined && rm !== null && this.caches.resolveAt) delete this.caches.resolveAt[String(rm)];
    return res;
  }
}
