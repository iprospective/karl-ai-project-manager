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
  /** RM3265 — la session REPRENABLE ancrée sur ce ticket, ou null.
   *  Une session épinglée qu'on clique après la mort de son tmux n'est ni vivante ni « enregistrée
   *  dans un jeu » : le seul fil qui reste est son TRANSCRIPT. On le cherche par le ticket, on
   *  écarte celles qui tournent encore, et on rend la plus récente (l'ordre du serveur). */
  async resumableOf(rm) {
    const id = String(rm == null ? "" : rm).trim();
    if (!/^\d+$/.test(id)) return null;
    const { resumable } = await this.search({ q: "RM" + id });
    return (resumable || []).find(s => !s.live && (s.tickets || []).some(t => String(t.rm_id) === id)) || null;
  }
  /** RM3265 : reprend la conversation d'un ticket, sous le même ancrage. */
  async resumeTicket(rm) {
    const s = await this.resumableOf(rm);
    if (!s) return { ok: false, message: "RM" + rm + " : aucune conversation à reprendre (transcript introuvable)" };
    return this.resume(s, String(rm));
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
