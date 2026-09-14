// modules/engines/EnginesRepository — catalogue et état des moteurs, exécution par IDENTIFIANT de recette. RM3069.
// Le client n'envoie jamais de commande : il nomme une recette et une action, le serveur sait quoi lancer.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class EnginesRepository extends Repository {
  constructor() { super({ name: "engines", ttl: 15000, max: 5, factory: new Factory({ type: "engine" }),
    routes: { list: "pm.engines", run: "pm.engine_install", options: "pm.engine_options" } }); }
  async list() { return await get(this.path("list")); }
  async run({ recipe, action, scope, dry_run, force }) { return await post(this.path("run"), { recipe, action, scope, dry_run, force }); }
  // RM3139 : le LANCEMENT des moteurs, distinct de leur INSTALLATION ci-dessus. Le client n'envoie
  // jamais de ligne de commande : il coche des options déclarées, le serveur compose et vérifie.
  async options() { return await get(this.path("options")); }
  async saveOptions({ engine, options, extra_args }) { return await post(this.path("options"), { engine, options, extra_args }); }
}
