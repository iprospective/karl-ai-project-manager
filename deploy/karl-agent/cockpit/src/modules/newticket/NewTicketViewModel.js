// viewmodels/tickets/NewTicketViewModel — le formulaire pleine page, décidé. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { clientsOf, projectsOf, pickClient, pickProject, REPRO, AGENT_TEST, DIFFICULTY } from "./newTicket.js";

export class NewTicketViewModel extends EntityViewModel {
  /** e = { types, priorities, projects } ; ctx = { client, project } (défauts) */
  constructor(e, ctx) { super(e || {}, ctx); }
  get types() { return this.e.types || []; }
  get priorities() { return this.e.priorities || []; }
  get clients() { return clientsOf(this.e.projects); }
  get client() { return pickClient(this.e.projects, this.ctx.client); }
  get noProjects() { return !this.clients.length; }
  radios(client = this.client, cur = this.ctx.project) {
    const list = projectsOf(this.e.projects, client), pick = pickProject(this.e.projects, client, cur);
    return list.map(p => ({ value: client + "/" + p, label: p, checked: p === pick }));
  }
  get repro() { return REPRO; } get agentTest() { return AGENT_TEST; } get difficulty() { return DIFFICULTY; }
}
