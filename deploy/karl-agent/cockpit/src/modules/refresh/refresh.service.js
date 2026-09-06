// services/refresh.service — le composite /refresh : un seul en vol, les rejoués après, les hashs et l'âge par bloc, le dispatch des blocs
// reçus au rendu (prêté). Aucun DOM. RM2889 (RM2763).
import { RefreshRepository } from "./RefreshRepository.js";
import { buildSpecs, pendStaleSet, seedBriefs } from "./refresh.js";

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
      const b = r.blocks || {};
      if (b.health) { this.hashes.health = b.health.hash; on.health(b.health.data); }
      if (b.pending) { this.hashes.pending = b.pending.hash; this.stale = pendStaleSet((b.pending.data || {}).entries || []); }
      if (b.dashboard) { this.hashes.dashboard = b.dashboard.hash; on.dashboard(b.dashboard.data); }
      if (b.vault) { this.hashes.vault = b.vault.hash; on.env("vault", b.vault.data); }
      if (b.envcheck) { this.hashes.envcheck = b.envcheck.hash; on.env("envcheck", b.envcheck.data); }
      if (b.coreupdate) { this.hashes.coreupdate = b.coreupdate.hash; on.coreupdate(b.coreupdate.data); }
      if (b.sessions) {
        this.hashes.sessions = b.sessions.hash;
        seedBriefs(b.sessions.data.briefs, this.stores.resolve);
        const c = on.sessions(b.sessions.data.sessions);
        if (c) this.hot = (c.attention || 0) + (c.choice || 0);
      }
      // garde : une réponse worklog d'une session qu'on a quittée entre-temps est jetée
      if (b.worklog && b.worklog.data && String(b.worklog.data.rm_id) === String(env().attached)) { this.hashes.worklog = b.worklog.hash; on.worklog(b.worklog.data); }
    })().catch(e => { on.healthKo(e.message); })
      .finally(() => { this.inFlight = null; if (this.queued) { const q = this.queued; this.queued = null; this.fetch(q, env, on); } });
    return this.inFlight;
  }
  coreUpdate() { return this.repo.coreUpdate(); }
}
