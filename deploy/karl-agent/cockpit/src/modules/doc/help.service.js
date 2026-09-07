// services/help.service — aide intégrée et documents : sommaire mis en cache, pages, fichiers. RM2889.
import { HelpRepository } from "./HelpRepository.js";

export class HelpService {
  constructor({ repo = new HelpRepository() } = {}) { this.repo = repo; this._topics = null; }
  async topics() { if (!this._topics) { try { this._topics = await this.repo.topics(); } catch (e) { this._topics = []; } } return this._topics; }
  /** La page demandée, ou la première du sommaire ; le texte dit quand l'aide manque plutôt que de rendre du vide. */
  async page(topic) {
    const topics = await this.topics();
    if (!topic) topic = (topics[0] || {}).id;
    let md = "*(aide indisponible)*";
    if (topic) { try { md = await this.repo.page(topic); } catch (e) { md = "*(page d'aide introuvable)*"; } }
    return { topics, topic, md };
  }
  doc(path) { return this.repo.file(path); }
}
