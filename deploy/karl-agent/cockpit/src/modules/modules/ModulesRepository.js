// modules/modules/ModulesRepository — ce que l'instance porte comme modules. RM3145 (lot 3).
// Lecture seule : le panneau n'active ni ne charge rien — il montre ce que le registre a lu.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";

export class ModulesRepository extends Repository {
  constructor() { super({ name: "modules", ttl: 30000, max: 3, factory: new Factory({ type: "module" }),
    routes: { list: "modules.list" } }); }
  async list() { return await get(this.path("list")); }
}
