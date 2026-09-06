// models/pmcmd/PmCommandsRepository — le catalogue de commandes (RM2209/RM2211). RM2889, L5.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";

export class PmCommandsRepository extends Repository {
  constructor() {
    super({ name: "pm-commands", ttl: 300000, max: 2, routes: { list: "pm.commands" },
            factory: new Factory({ type: "pm-command", required: ["name"], defaults: { args: [], category: "autres", mutate: false, confirm: false } }) });
  }
  all() { return this.store.ensure("all", async () => this.factory.many((await get(this.path("list"))).commands || [])); }
}

/** Les arguments d'un formulaire, lus depuis des valeurs brutes {name: value} :
 *  bool absent → omis ; texte vide → omis, sauf requis → erreur nommée. */
export function collectArgs(cmd, values) {
  const args = {};
  for (const a of cmd.args || []) {
    if (a.server) continue;
    if (!(a.name in values)) continue;
    const v = a.type === "bool" ? !!values[a.name] : String(values[a.name] == null ? "" : values[a.name]).trim();
    if (a.type === "bool") { if (v) args[a.name] = true; }
    else if (v !== "") args[a.name] = v;
    else if (a.required) return { error: "Champ requis : " + (a.label || a.name) };
  }
  return { args };
}
