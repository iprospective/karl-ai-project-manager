// modules/engines/EnginesRepository — catalogue et état des moteurs, exécution par IDENTIFIANT de recette. RM3069.
// Le client n'envoie jamais de commande : il nomme une recette et une action, le serveur sait quoi lancer.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class EnginesRepository extends Repository {
  constructor() { super({ name: "engines", ttl: 15000, max: 5, factory: new Factory({ type: "engine" }),
    routes: { list: "pm.engines", run: "pm.engine_install" } }); }
  async list() { return await get(this.path("list")); }
  async run({ recipe, action, dry_run, force }) { return await post(this.path("run"), { recipe, action, dry_run, force }); }
}
