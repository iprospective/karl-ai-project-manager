// modules/feed/notify.service — l'état du panneau « fil ». RM2792.
import { FeedRepository } from "./FeedRepository.js";

export class FeedService {
  constructor({ repo = new FeedRepository() } = {}) {
    this.repo = repo; this.data = null; this.error = null;
  }
  async load(opts) {
    try { this.data = await this.repo.feed(opts); this.error = null; }
    catch (e) { this.data = null; this.error = e.message; }
    return this.data;
  }
  async mark(body) { const r = await this.repo.mark(body); this.data = null; return r; }
}
