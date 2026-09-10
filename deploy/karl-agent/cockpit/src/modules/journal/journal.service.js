// modules/journal/journal.service — l'état du panneau « journal » : filtres persistés (ce navigateur), entrées serveur (relues par `since`),
// entrées du front (abonnement au journal core), suivi/pause, badge. Aucun DOM. RM3011.
import { JournalRepository } from "./JournalRepository.js";
import { mergeEntries, filterEntries, badgeCount } from "./journal.js";
import { LEVELS, CATEGORIES } from "../../core/log.js";

export class JournalService {
  constructor({ repo = new JournalRepository(), storage = null, log = null, limit = 300 } = {}) {
    this.repo = repo; this.storage = storage; this.log = log; this.limit = limit;
    this.level = this._read("karlJournalLevel") || "info";
    this.cats = new Set((this._read("karlJournalCats") || "").split(",").filter(Boolean));
    this.q = ""; this.paused = false;
    this.server = []; this.since = null; this.categories = CATEGORIES.slice(); this.stats = null; this.error = null;
    this.seenId = 0;                                                         // badge : dernier id du front vu panneau ouvert
    this.unsub = log ? log.subscribe(() => { if (this.onFront) this.onFront(); }) : null;
  }
  _read(k) { try { return this.storage ? this.storage.getItem(k) : null; } catch (e) { return null; } }
  _write(k, v) { try { if (this.storage) this.storage.setItem(k, v); } catch (e) { /* mode privé */ } }
  setLevel(l) { this.level = LEVELS[l] ? l : "info"; this._write("karlJournalLevel", this.level); }
  toggleCat(c) { this.cats.has(c) ? this.cats.delete(c) : this.cats.add(c); this._write("karlJournalCats", [...this.cats].join(",")); }
  clearCats() { this.cats.clear(); this._write("karlJournalCats", ""); }
  setQuery(q) { this.q = String(q || ""); }
  togglePause() { this.paused = !this.paused; return this.paused; }
  /** Relit le serveur : tout au premier appel, puis seulement le nouveau (`since`). */
  async load(reset = false) {
    if (reset) { this.server = []; this.since = null; }
    try {
      const r = await this.repo.tail({ since: this.since, limit: this.limit });
      const got = (r && r.entries) || [];
      this.server = this.since ? this.server.concat(got) : got;
      if (this.server.length > this.limit * 2) this.server = this.server.slice(-this.limit * 2);
      if (got.length) this.since = got[got.length - 1].ts;
      if (r && r.categories) this.categories = r.categories; if (r && r.stats) this.stats = r.stats;
      this.error = null;
    } catch (e) { this.error = e.message; }
    return this.server;
  }
  entries() { return filterEntries(mergeEntries(this.server, this.log ? this.log.entries() : []), { level: this.level, cats: this.cats, q: this.q }); }
  badge() { return badgeCount(this.log ? this.log.entries() : [], this.seenId); }
  markSeen() { const all = this.log ? this.log.entries() : []; this.seenId = all.length ? all[all.length - 1].id : this.seenId; }
  clearFront() { if (this.log) this.log.clear(); }
  dispose() { if (this.unsub) this.unsub(); }
}
