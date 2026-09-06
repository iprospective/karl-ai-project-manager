// services/search.service — recherche de tickets : résultats, panne Redmine à côté (jamais à la place), étiquettes en cache. RM2889.
import { SearchRepository } from "./SearchRepository.js";

export class SearchService {
  constructor({ repo = new SearchRepository() } = {}) { this.repo = repo; this.tags = []; this.last = { results: [], redmine_error: "" }; }
  async search(q, filters, ctxClient) { this.last = await this.repo.search(q, filters, ctxClient); return this.last; }
  async loadTags() { try { this.tags = await this.repo.tags(); } catch (e) { this.tags = []; } return this.tags; }
}
