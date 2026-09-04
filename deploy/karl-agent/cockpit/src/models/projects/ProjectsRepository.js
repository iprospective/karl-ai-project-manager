// models/projects/ProjectsRepository — la liste client/projet. RM2889, L4.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get } from "../../core/api.js";

export class ProjectsRepository extends Repository {
  constructor() {
    super({ name: "projects", ttl: 60000, max: 2, routes: { list: "project.projects" },
            factory: new Factory({ type: "project", required: ["client", "project"], coerce: { value: (v) => v } }) });
  }
  /** Tous les couples client/projet, hydratés (value = client/projet si absent). */
  all() {
    return this.store.ensure("all", async () => {
      const { projects } = await get(this.path("list"));
      return this.factory.many((projects || []).map(p => ({ ...p, value: p.value || (p.client + "/" + p.project) })));
    });
  }
}
