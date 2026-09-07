// models/pm/PmRepository — POST /pm/run : exécuter une commande PM (RM2211/2213). RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { post } from "../../core/api.js";

export class PmRepository extends Repository {
  constructor() { super({ name: "pm-run", ttl: 1000, max: 1, factory: new Factory({ type: "pm_run" }), routes: { run: "pm.run" } }); }
  run(body) { return post(this.path("run"), body); }
}
