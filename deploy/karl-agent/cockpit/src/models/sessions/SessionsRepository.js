// models/sessions/SessionsRepository — répondre Oui (une session, toutes), armer l'auto-oui. RM2889.
// Les clés de routes sont celles de la carte historique (le chemin /approve y est rangé sous « outline ») : L7 les renomme, pas ce lot.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { post } from "../../core/api.js";

export class SessionsRepository extends Repository {
  constructor() { super({ name: "sessions-list", ttl: 1000, max: 1, factory: new Factory({ type: "session" }), routes: { approve: "outline.approve", approve_all: "session.approve_all", auto_yes: "session_set.auto_yes" } }); }
  approve(rm) { return post(this.path("approve"), { rm_id: rm }); }
  approveAll() { return post(this.path("approve_all"), {}); }
  autoYes(rm, minutes) { return post(this.path("auto_yes"), { rm_id: rm, minutes: Number(minutes) }); }
}
