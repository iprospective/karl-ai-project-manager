// models/git/GitRepository — journal, commit, diff d'une session. RM2889, L4.
//
// Trois routes de LECTURE, et rien d'autre : le cockpit ne fait pas d'action
// git (RM2602) — un test le garantit sur la table des routes. La session est
// le premier segment du chemin, comme aujourd'hui.

import { Repository } from "../Repository.js";
import { get } from "../../core/api.js";
import { Factory } from "../Factory.js";

const enc = encodeURIComponent;

export class GitRepository extends Repository {
  constructor() {
    super({ name: "git", ttl: 3000, max: 30, factory: new Factory({ type: "git-log", defaults: { commits: [] } }),
            routes: { log: "git.log", show: "git.show", diff: "git.diff" } });
  }
  /** Journal : {is_git, pm_data_repo, branch, commits, cwd, origin, dirty}. */
  log(sid, limit = 40) {
    return this.store.ensure(`log:${sid}`, () => get(this.path("log") + "/" + enc(sid) + "?limit=" + limit));
  }
  /** Un commit avec son patch : {commit:{short}, message, stats, patch, truncated}. */
  show(sid, sha) { return get(this.path("show") + "/" + enc(sid) + "/" + enc(sha)); }
  /** Diff « branch » (vs base d'intégration) ou « worktree » (non commité). */
  diff(sid, mode) { return get(this.path("diff") + "/" + enc(sid) + "?mode=" + enc(mode)); }
}
