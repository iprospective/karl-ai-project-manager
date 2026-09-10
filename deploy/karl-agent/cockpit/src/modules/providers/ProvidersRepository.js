// modules/providers/ProvidersRepository — le catalogue des types, les instances déclarées, l'écriture (RM3068).
// Une VALEUR de secret ne part que dans un sens : elle est postée, jamais lue. Aucune méthode ne la relit.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class ProvidersRepository extends Repository {
  constructor() { super({ name: "providers", ttl: 20000, max: 10, factory: new Factory({ type: "provider" }),
    routes: { types: "pm.provider_types", list: "pm.providers", secret: "pm.provider_secret",
              assign: "pm.provider_assign", models: "pm.llm_models" } }); }
  async types() { return await get(this.path("types")); }
  async list() { return await get(this.path("list")); }
  async save(body) { return await post(this.path("list"), body); }
  /** La valeur part ici et ne revient jamais : le serveur ne rend qu'un accusé. */
  async secret(body) { return await post(this.path("secret"), body); }
  async assign(body) { return await post(this.path("assign"), body); }
  /** Ce que le fournisseur sert vraiment : on le lui demande (RM3072). La clé reste au serveur. */
  async models(body) { return await post(this.path("models"), body); }
}
