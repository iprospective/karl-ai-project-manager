// models/env/EnvRepository — diagnostic du poste, coffre, agent SSH. RM2889, L5.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get, post } from "../../core/api.js";

export class EnvRepository extends Repository {
  constructor() {
    super({ name: "env", ttl: 10000, max: 4, factory: new Factory({ type: "env-report" }),
            routes: { check: "env.env_check", status: "env.env_status", unlock: "env.unlock", sshAdd: "env.ssh_add" } });
  }
  check()  { return get(this.path("check") + "?force=1"); }
  status() { return get(this.path("status")); }
  /** Le mot de passe traverse ici et nulle part ailleurs : jamais mémorisé. */
  unlock(instance, password) { return post(this.path("unlock"), { instance, password }); }
  sshAdd(key, passphrase)    { return post(this.path("sshAdd"), { key, passphrase }); }
}
