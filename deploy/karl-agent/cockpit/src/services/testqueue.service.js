// services/testqueue.service — la file et ses gestes d'environnement (via le runner PM prêté). RM2889.
import { TestQueueRepository } from "../models/testqueue/TestQueueRepository.js";
export class TestQueueService {
  constructor(repo = new TestQueueRepository(), run = null) { this.repo = repo; this._run = run; this.all = []; this.byId = {}; this.loaded = false; }
  async load() { const q = await this.repo.list(); this.all = q; this.byId = {}; q.forEach(e => { this.byId[String(e.rm_id)] = e; }); this.loaded = true; return q; }
  entry(rm) { return this.byId[String(rm)]; }
  async _pm(name, args, okMsg, title) {
    try { const r = await this._run(name, args, { confirm: true }); const out = (r.stdout || "") + (r.ok ? "" : "\n" + (r.stderr || ""));
      return { ok: !!r.ok, message: r.ok ? okMsg : "Échec (rc=" + r.rc + ")", title: title + (r.ok ? "" : " — ÉCHEC"), out: out || "(ok)" }; }
    catch (e) { return { ok: false, message: e.message }; }
  }
  cockpitEnv(rm, action) { return this._pm("cockpit-test-env", { action, rm_id: String(rm) }, action === "create" ? "Instance de test RM" + rm + " prête — lien dans la fiche" : "Instance de test démontée", "Instance cockpit de test RM" + rm); }
  deploy(rm, clone) { const args = { action: "create", rm_id: String(rm) }; args[clone ? "db_clone" : "no_db_clone"] = true; return this._pm("env-session-create", args, "Env de test RM" + rm + " déployé", "Déploiement RM" + rm); }
  teardown(rm) { return this._pm("env-session-teardown", { action: "teardown", rm_id: String(rm) }, "Env RM" + rm + " démonté", "Teardown RM" + rm); }
  deployShared(rm) { return this._pm("env-deploy", { action: "deploy", rm_id: String(rm) }, "📤 branche déployée dans l'env partagé", "Env partagé — RM" + rm); }
}
