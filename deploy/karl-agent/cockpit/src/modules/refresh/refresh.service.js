// services/refresh.service — le composite /refresh : un seul en vol, les rejoués après, les hashs et l'âge par bloc, le dispatch des blocs
// reçus au rendu (prêté). Aucun DOM. RM2889 (RM2763).
import { RefreshRepository } from "./RefreshRepository.js";
import { buildSpecs, pendStaleSet, seedBriefs, ALL_BLOCKS } from "./refresh.js";

export class RefreshService {
  constructor({ repo = new RefreshRepository(), now = () => Date.now(), stores = {} } = {}) {
    this.repo = repo; this.now = now; this.stores = stores;   // RM3005 : `stores.resolve` reçoit les briefs partiels
    this.hashes = {}; this.at = {}; this.worklogSid = null; this.inFlight = null; this.queued = null;
    this.stale = new Set();                                            // RM2598 : rm_ids ayant une question sans réponse
    this.hot = 0;                                                      // RM2613 : sessions en attention/choix (règle la cadence)
  }
  specs(includes, env) {
    const b = buildSpecs({ hashes: this.hashes, at: this.at, includes, now: this.now(), dashboardVisible: env.dashboardVisible, attached: env.attached, worklogVisible: env.worklogVisible, worklogSid: this.worklogSid });
    if (b.resetWorklogHash) delete this.hashes.worklog;
    this.worklogSid = b.worklogSid;
    return b.specs;
  }
  /**
   * Un composite : `env` = { attached, dashboardVisible, worklogVisible } lu à l'appel ; `on` = { health(data), healthKo(msg), sessions(list) → counts,
   * worklog(data), dashboard(data), env(kind, data), coreupdate(data) }. Un seul en vol ; les includes arrivés pendant le vol sont rejoués après.
   */
  fetch(includes, env, on) {
    includes = includes || [];
    if (this.inFlight) { this.queued = (this.queued || []).concat(includes); return this.inFlight; }
    const specs = this.specs(includes, env());
    if (!specs.length) return Promise.resolve();
    this.inFlight = (async () => {
      const r = await this.repo.pull(specs);
      const now = this.now();
      specs.forEach(sp => { this.at[sp.split(":")[0]] = now; });
      this.ingest(r, env, on, false);
    })().catch(e => { on.healthKo(e.message); })
      .finally(() => { this.inFlight = null; if (this.queued) { const q = this.queued; this.queued = null; this.fetch(q, env, on); } });
    return this.inFlight;
  }
  /**
   * Livre les blocs d'une réponse /refresh — tirée par le tick ou POUSSÉE par le canal (RM3006) — aux domaines. Un bloc dont le hash
   * est déjà le nôtre est ignoré (le canal et le tick peuvent se croiser) ; un bloc poussé date aussi son `at` (il est frais).
   * Rend les noms des blocs livrés.
   */
  ingest(r, env, on, pushed = false) {
    const b = (r && r.blocks) || {}; const seen = [];
    const take = (name) => { const x = b[name]; if (!x || this.hashes[name] === x.hash) return null; this.hashes[name] = x.hash; if (pushed) this.at[name] = this.now(); seen.push(name); return x; };
    let x;
    if ((x = take("health"))) on.health(x.data);
    if ((x = take("pending"))) this.stale = pendStaleSet((x.data || {}).entries || []);
    if ((x = take("dashboard"))) on.dashboard(x.data);
    if ((x = take("vault"))) on.env("vault", x.data);
    if ((x = take("envcheck"))) on.env("envcheck", x.data);
    if ((x = take("coreupdate"))) on.coreupdate(x.data);
    if ((x = take("sessions"))) {
      seedBriefs(x.data.briefs, this.stores.resolve);
      const c = on.sessions(x.data.sessions);
      if (c) this.hot = (c.attention || 0) + (c.choice || 0);
    }
    // garde : une réponse worklog d'une session qu'on a quittée entre-temps est jetée
    if (b.worklog && b.worklog.data && String(b.worklog.data.rm_id) === String(env().attached) && this.hashes.worklog !== b.worklog.hash) { this.hashes.worklog = b.worklog.hash; if (pushed) this.at.worklog = this.now(); seen.push("worklog"); on.worklog(b.worklog.data); }
    return seen;
  }
  /** RM3006 : les specs que le canal de push doit porter — tous les blocs (avec leur hash courant), le worklog si une session est attachée et visible. */
  pushSpecs(env) { return buildSpecs({ hashes: this.hashes, at: {}, includes: ALL_BLOCKS, now: this.now(), dashboardVisible: env.dashboardVisible, attached: env.attached, worklogVisible: env.worklogVisible, worklogSid: this.worklogSid }).specs; }
  coreUpdate() { return this.repo.coreUpdate(); }
}
