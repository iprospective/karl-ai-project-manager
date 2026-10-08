// models/refresh/RefreshRepository — GET /refresh?blocks=… (le composite RM2763) et GET /core/update-status (RM2571). RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class RefreshRepository extends Repository {
  constructor() { super({ name: "refresh", ttl: 1000, max: 1, factory: new Factory({ type: "refresh" }), routes: { refresh: "session.refresh", core: "core.update_status", run: "core.update", runlog: "core.update_log" } }); }
  /** Le client joint le hash de la dernière donnée reçue par bloc ; le serveur ne renvoie QUE les blocs changés. */
  pull(specs) { return get(this.path("refresh") + "?blocks=" + encodeURIComponent(specs.join(","))); }
  /** Sonde forcée du remote (rafraîchissement manuel) ; le poll périodique passe par le composite. */
  coreUpdate() { return get(this.path("core") + "?force=1"); }
  /** RM2571 : déclenche la mise à jour du code (travail détaché côté serveur). */
  coreUpdateRun() { return post(this.path("run"), {}); }
  /** RM2571 : avancement du run — relit un journal, donc survit au redémarrage de karl-agent. */
  coreUpdateLog() { return get(this.path("runlog")); }
}
