// services/meta.service — l'encart ℹ : worktree, fiche projet, presse-papier. RM2889 (revue 3/3).
import { TicketMetaRepository } from "./TicketMetaRepository.js";

export class MetaService {
  constructor({ repo = new TicketMetaRepository(), clipboard = null } = {}) { this.repo = repo; this.clipboard = clipboard; }
  workspace(rm) { return this.repo.workspace(rm); }
  /** RM3164. Tolère un dépôt qui ne l'implémente pas (doubles de test partiels) : le panneau
   *  affiche alors « pas demandé » au lieu de tomber — une information en moins ne vaut pas
   *  un encart mort. */
  ticketSessions(rm, onLoad) {
    return this.repo.ticketSessions ? this.repo.ticketSessions(rm, onLoad) : undefined;
  }
  refreshWorkspace(rm) { return this.repo.refreshWorkspace(rm); }
  projectCard(client, project, onLoad) { return this.repo.projectCard(client, project, onLoad); }
  /** RM2611 : le récap texte des infos de session part au presse-papier. `lines` null = rien de chargé. */
  async copyRecap(lines) {
    if (!lines) return { ok: false, message: "Infos pas encore chargées" };
    if (!this.clipboard) return { ok: false, message: "Presse-papier indisponible" };
    try { await this.clipboard.writeText(lines.join("\n")); return { ok: true, message: "Récap copié" }; }
    catch (e) { return { ok: false, message: "Copie refusée" }; }
  }
}
