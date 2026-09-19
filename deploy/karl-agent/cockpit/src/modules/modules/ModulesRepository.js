// modules/modules/ModulesRepository — ce que l'instance porte comme modules. RM3145 (lot 3).
// RM3145 L1 : le panneau peut désormais ALLUMER et ÉTEINDRE — il ne charge toujours aucun code.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";

export class ModulesRepository extends Repository {
  constructor() { super({ name: "modules", ttl: 30000, max: 3, factory: new Factory({ type: "module" }),
    routes: { list: "modules.list", state: "pm.modules_state", policy: "pm.modules_policy" } }); }
  async list() { return await get(this.path("list")); }
  /** RM3145 L1 — { name, enabled, force?, confirm? }. Le serveur REFUSE en disant pourquoi (409). */
  async setState(body) { return await this.send("state", body); }
  /** RM3145 Q003 — permettre, ou non, le forçage sur l'instance. */
  async setPolicy(allow) { return await this.send("policy", { allow_force: !!allow }); }
}
