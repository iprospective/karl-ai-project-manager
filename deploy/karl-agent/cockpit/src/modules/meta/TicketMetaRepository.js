// models/tickets/TicketMetaRepository — ce que l'encart ℹ va chercher lui-même : l'état git du
// worktree d'un ticket (intérim RM1883) et la fiche du projet qui le porte (RM2614). RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";
import { routeFor } from "../../core/endpoints.js";
const enc = encodeURIComponent;

export class TicketMetaRepository extends Repository {
  constructor() {
    super({ name: "ticket-meta", ttl: 30000, max: 100, factory: new Factory({ type: "workspace-status" }),
            routes: { workspace: "ticket.workspace_status", project: routeFor("/project"),
                      sessions: routeFor("/ticket-sessions"),
                      impact: "ticket.impact" } });
    this.ws = {};       // rm → état git (undefined : jamais demandé ; null : pas de ticket, ou échec)
    this.cards = {};    // client/projet → fiche (null : en vol ; {error:true} : échec)
    this.sess = {};     // rm → sessions du ticket (undefined : jamais demandé ; null : en vol)
    this.imp = {};      // rm → impact (mêmes conventions)
  }
  workspace(rm) { return this.ws[String(rm)]; }

  /** RM3164 — ce que le ticket a touché. Mêmes conventions que `ticketSessions`. */
  ticketImpact(rm, onLoad) {
    rm = String(rm);
    if (!/^\d+$/.test(rm)) return undefined;
    if (this.imp[rm] !== undefined) return this.imp[rm];
    this.imp[rm] = null;
    get(this.path("impact") + "/" + enc(rm))
      .then(d => { this.imp[rm] = d || {}; if (onLoad) onLoad(d); })
      .catch(() => { this.imp[rm] = { error: true }; if (onLoad) onLoad(null); });
    return null;
  }

  /** RM3164 — qui traite ce ticket. UNE requête par ticket, pas une par rendu : le panneau se
   *  redessine à chaque frappe et à chaque poll. Rend les sessions si elles sont connues,
   *  `null` pendant le vol, `undefined` si on ne les a jamais demandées — `onLoad` prévient. */
  ticketSessions(rm, onLoad) {
    rm = String(rm);
    if (!/^\d+$/.test(rm)) return undefined;              // slug : pas un ticket
    if (this.sess[rm] !== undefined) return this.sess[rm];
    this.sess[rm] = null;
    get(this.path("sessions") + "/" + enc(rm))
      .then(d => { this.sess[rm] = d || {}; if (onLoad) onLoad(d); })
      .catch(() => { this.sess[rm] = { error: true }; if (onLoad) onLoad(null); });
    return null;
  }
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
