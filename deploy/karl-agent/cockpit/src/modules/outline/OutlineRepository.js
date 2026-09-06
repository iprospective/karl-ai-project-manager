// models/outline/OutlineRepository — l'outline d'une session (/outline) et le défilement du terminal (/scroll). RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";
import { normalizeItems } from "./outline.js";

export class OutlineRepository extends Repository {
  constructor() { super({ name: "outline", ttl: 5000, max: 20, factory: new Factory({ type: "outline" }), routes: { outline: "layout.outline", scroll: "outline.scroll" } }); }
  async load(sid) {
    const r = await get(this.path("outline") + "/" + encodeURIComponent(sid));
    return { items: normalizeItems(r.items), total: r.total_lines || 0, source: r.source || "tmux" };
  }
  scrollTo(sid, line) { return post(this.path("scroll"), { rm_id: sid, line: Math.max(0, line - 2) }); }
  scrollBottom(sid) { return post(this.path("scroll"), { rm_id: sid, bottom: true }); }
}
