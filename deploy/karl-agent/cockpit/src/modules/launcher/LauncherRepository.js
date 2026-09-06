// models/launcher/LauncherRepository — /resolve/<rm>, /spawn, /tickets (création), /projects, /sessions (vivantes). RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class LauncherRepository extends Repository {
  constructor() { super({ name: "launcher", ttl: 5000, max: 20, factory: new Factory({ type: "ticket" }), routes: { resolve: "ticket.resolve", spawn: "session.spawn", tickets: "ticket.tickets", projects: "project.projects", sessions: "session.sessions" } }); }
  resolve(rm) { return get(this.path("resolve") + "/" + encodeURIComponent(rm)); }
  spawn(body) { return post(this.path("spawn"), body); }
  createTicket(body) { return post(this.path("tickets"), body); }
  async projects() { const r = await get(this.path("projects")); return (r && r.projects) || []; }
  /** RM2427 : `ghosts=0` — une session seulement ENREGISTRÉE ne tourne pas, il n'y a rien à attacher. */
  async running() { const r = await get(this.path("sessions") + "?ghosts=0"); return (r && r.sessions) || []; }
}
