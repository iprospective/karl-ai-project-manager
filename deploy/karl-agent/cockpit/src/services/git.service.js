// services/git.service — ce que le panneau demande, en un appel. RM2889, L4.
import { GitRepository } from "../models/git/GitRepository.js";

export class GitService {
  constructor(repo = new GitRepository()) { this.repo = repo; }
  log(sid, force) { if (force) this.repo.store.invalidate(`log:${sid}`); return this.repo.log(sid); }
  show(sid, sha) { return this.repo.show(sid, sha); }
  diff(sid, mode) { return this.repo.diff(sid, mode); }
}
