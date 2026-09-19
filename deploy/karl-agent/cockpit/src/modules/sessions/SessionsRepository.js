// models/sessions/SessionsRepository — répondre Oui (une session, toutes), armer l'auto-oui. RM2889.
// Les clés de routes sont celles de la carte historique (le chemin /approve y est rangé sous « outline ») : L7 les renomme, pas ce lot.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { post } from "../../core/api.js";

export class SessionsRepository extends Repository {
  constructor() { super({ name: "sessions-list", ttl: 1000, max: 1, factory: new Factory({ type: "session" }), routes: { approve: "outline.approve", approve_all: "session.approve_all", auto_yes: "session_set.auto_yes", compact: "session.compact" } }); }
  approve(rm) { return post(this.path("approve"), { rm_id: rm }); }
  approveAll() { return post(this.path("approve_all"), {}); }
  /** RM3249 : le serveur tape la commande de compaction du moteur de la session — le front ne la connaît pas. */
  compact(rm) { return post(this.path("compact"), { rm_id: rm }); }
  autoYes(rm, minutes) { return post(this.path("auto_yes"), { rm_id: rm, minutes: Number(minutes) }); }
}
