// services/pmcmd.service — catalogue + exécution. RM2889, L5. L'exécution passe par
// le pmRun prêté par le monolithe (il porte la confirmation serveur, RM2211).
import { PmCommandsRepository, collectArgs } from "../models/pmcmd/PmCommandsRepository.js";

export class PmCommandsService {
  constructor(repo = new PmCommandsRepository(), run = null) { this.repo = repo; this._run = run; this.commands = []; }
  async load() { this.commands = await this.repo.all(); return this.commands; }
  find(name) { return this.commands.find(c => c.name === name) || null; }
  /** Rend {ok, rc, output, message} ; ne lève pas. */
  async run(name, values) {
    const c = this.find(name); if (!c) return { ok: false, message: "commande inconnue : " + name };
    const col = collectArgs(c, values); if (col.error) return { ok: false, message: col.error };
    try {
      const r = await this._run(name, col.args, { confirm: !!c.confirm });
      return { ok: !!r.ok, rc: r.rc, output: (r.stdout || "") + (r.stderr ? "\n--- stderr ---\n" + r.stderr : ""),
               message: r.ok ? "✓ " + (c.label || name) : "Échec (rc=" + r.rc + ")" };
    } catch (e) { return { ok: false, message: e.message }; }
  }
}
