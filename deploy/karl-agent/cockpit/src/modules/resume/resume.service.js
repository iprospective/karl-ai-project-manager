// services/resume.service — reprendre une session : recherche, ancrage, déplacement (gardes). RM2889.
import { ResumeRepository } from "./ResumeRepository.js";
import { rsQuery, normalizeAnchor } from "./resume.js";

export class ResumeService {
  constructor({ repo = new ResumeRepository() } = {}) { this.repo = repo; this.last = { resumable: [], archived: [] }; }
  async search(filters) { this.last = await this.repo.search(rsQuery(filters)); return this.last; }
  /** Reprend `s` sous l'ancrage saisi. Rend { ok, message, r } ; refuse un ancrage invalide sans appeler le serveur. */
  async resume(s, anchorRaw) {
    const rm = normalizeAnchor(anchorRaw);
    if (rm === null) return { ok: false, message: "Ancrage invalide : RM id ou slug [a-z0-9_-]" };
    const body = { session_id: s.session_id }; if (rm) body.rm_id = rm;
    const r = await this.repo.resume(body);
    return { ok: true, message: "Session reprise dans " + r.tmux, r };
  }
  /** RM2418 : déplace une session À L'ARRÊT vers un projet CONNU. */
  async move(s, target, knownValues) {
    if (s.live) return { ok: false, message: "Session à tmux vivant : ferme-la d'abord" };
    if (!(knownValues || []).length) return { ok: false, message: "Liste des projets non chargée" };
    const val = String(target || "").trim();
    if (!(knownValues || []).includes(val)) return { ok: false, message: "Projet inconnu : " + val };
    const [c, p] = val.split("/");
    const r = await this.repo.move(s.session_id, c, p);
    return { ok: true, message: "Session déplacée → " + (r.client ? r.client + "/" + r.project : r.new_slug), r };
  }
}
