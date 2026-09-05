// services/project.service — la fiche projet et ses gestes. RM2889.
import { ProjectRepository } from "../models/projects/ProjectRepository.js";
import { configArgs } from "../models/projects/projectConfig.js";

export class ProjectService {
  constructor(repo = new ProjectRepository(), run = null) { this.repo = repo; this._run = run; }
  sheet(key) { return this.repo.sheet(key); }
  worktrees(key) { return this.repo.worktrees(key); }
  worklog(key) { return this.repo.overview(key); }
  async browse(key, wt, path) { try { return { entries: (await this.repo.ls(key, wt, path)).entries || [] }; } catch (e) { return { entries: [], error: e.message }; } }
  async open(key, wt, path) { try { return { file: await this.repo.file(key, wt, path) }; } catch (e) { return { error: e.message }; } }
  /** Écrit meta.yml via le runner générique ; rend {ok, message}, ne lève pas. */
  async saveConfig(scope, key, fields) {
    const args = configArgs(scope, key, fields);
    if (!args) return { ok: false, message: "Aucun champ à modifier", nothing: true };
    try {
      const r = await this._run(scope === "project" ? "project-config" : "client-config", args, { confirm: true });
      return r.ok ? { ok: true, message: "✓ conf enregistrée" } : { ok: false, message: "Échec (rc=" + r.rc + ") : " + ((r.stderr || r.stdout || "").split("\n")[0]) };
    } catch (e) { return { ok: false, message: e.message }; }
  }
}
