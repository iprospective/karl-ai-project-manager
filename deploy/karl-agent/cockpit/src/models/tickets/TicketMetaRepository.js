// models/tickets/TicketMetaRepository — ce que l'encart ℹ va chercher lui-même : l'état git du
// worktree d'un ticket (intérim RM1883) et la fiche du projet qui le porte (RM2614). RM2889.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get } from "../../core/api.js";
import { routeFor } from "../../core/endpoints.js";
const enc = encodeURIComponent;

export class TicketMetaRepository extends Repository {
  constructor() {
    super({ name: "ticket-meta", ttl: 30000, max: 100, factory: new Factory({ type: "workspace-status" }),
            routes: { workspace: "ticket.workspace_status", project: routeFor("/project") } });
    this.ws = {};       // rm → état git (undefined : jamais demandé ; null : pas de ticket, ou échec)
    this.cards = {};    // client/projet → fiche (null : en vol ; {error:true} : échec)
  }
  workspace(rm) { return this.ws[String(rm)]; }
  async refreshWorkspace(rm) {
    rm = String(rm);
    if (!/^\d+$/.test(rm)) { this.ws[rm] = null; return null; }     // slug : pas de ticket
    try { this.ws[rm] = await get(this.path("workspace") + "/" + enc(rm)); } catch (e) { this.ws[rm] = null; }
    return this.ws[rm];
  }
  /** La fiche projet : UNE requête par projet, pas une par rendu de fiche (RM2614). Rend la fiche
   *  si elle est connue, null sinon — `onLoad` prévient quand elle arrive. */
  projectCard(client, project, onLoad) {
    const cle = client + "/" + project;
    if (this.cards[cle] !== undefined) return this.cards[cle];
    this.cards[cle] = null;                       // marque « en cours »
    get(this.path("project") + "/" + enc(client) + "/" + enc(project))
      .then(d => { this.cards[cle] = d; if (onLoad) onLoad(d); })
      .catch(() => { this.cards[cle] = { error: true }; });
    return null;
  }
}
