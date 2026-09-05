// services/actions.service — envoyer une action à une session, piloter ses panes, sa disposition, la fermer. RM2889.
import { SessionActionsRepository } from "../models/sessions/SessionActionsRepository.js";
import { actionMessage } from "../models/sessions/actions.js";

export class ActionsService {
  constructor({ repo = new SessionActionsRepository() } = {}) { this.repo = repo; }
  /** `id` = ce que remplace {id} (un TICKET pour les actions PM) ; `sid` = la session destinataire (RM2720). */
  async send(a, sid, rid) { await this.repo.send(sid, actionMessage(a, rid), a.enter !== false); return a.enter === false ? "Texte injecté — complète dans le terminal" : "Envoyé : " + a.label; }
  monitor(sid, preset) { return this.repo.monitor(sid, preset); }
  unmonitor(sid) { return this.repo.unmonitor(sid); }
  layout(sid, layout) { return this.repo.layout(sid, layout); }
  disposition(sid, d) { return this.repo.disposition(sid, d); }
  kill(sid) { return this.repo.kill(sid); }
}
