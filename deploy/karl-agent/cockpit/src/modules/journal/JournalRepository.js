// modules/journal/JournalRepository — GET /api/log/tail (lecture filtrée du journal serveur, RM3010) et POST /api/log/write. RM3011.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class JournalRepository extends Repository {
  constructor() { super({ name: "journal", ttl: 1000, max: 1, factory: new Factory({ type: "log" }), routes: { tail: "log.tail", write: "log.write" } }); }
  tail({ category, level, since, limit, q } = {}) {
    const p = new URLSearchParams();
    if (category) p.set("category", category); if (level) p.set("level", level); if (since) p.set("since", since); if (limit) p.set("limit", String(limit)); if (q) p.set("q", q);
    const qs = p.toString();
    return get(this.path("tail") + (qs ? "?" + qs : ""));
  }
  write(rec) { return post(this.path("write"), rec); }
}
