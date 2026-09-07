// modules/journal/JournalViewModel — ce que le panneau « journal » présente : barre de filtres, lignes, compteurs. Inerte. RM3011.
import { LEVELS } from "../../core/log.js";
import { fieldsText, fmtTs, dayOf } from "./journal.js";

export class JournalViewModel {
  constructor({ entries, level, cats, categories, q, paused, error, stats, total }) { this.e = entries || []; this.level = level; this.cats = cats || new Set(); this.categories = categories || []; this.q = q || ""; this.paused = !!paused; this.error = error || null; this.stats = stats || null; this.total = total; }
  get levels() { return Object.keys(LEVELS).map(l => ({ value: l, label: l, selected: l === this.level })); }
  get catChips() { return this.categories.map(c => ({ cat: c, on: this.cats.has(c) })); }
  get allCats() { return !this.cats.size; }
  get rows() {
    let day = "";
    return this.e.map(r => { const d = dayOf(r.ts); const newDay = d !== day; day = d; return { id: r.src + ":" + (r.id != null ? r.id : r.ts), day: newDay ? d : "", time: fmtTs(r.ts), level: r.level, cat: r.cat, src: r.src === "front" ? "front" : "srv", msg: r.msg, fields: fieldsText(r), cls: "jl-" + r.level }; });
  }
  get count() { return this.e.length; }
  get errors() { return this.e.filter(r => r.level === "error").length; }
  get warns() { return this.e.filter(r => r.level === "warn").length; }
  get statsText() { return this.stats ? `${this.stats.written || 0} écrit(s) · niveau serveur ${this.stats.level || "?"} · ${this.stats.path || ""}` : ""; }
  /** Texte brut pour la copie : une ligne par entrée. */
  get plain() { return this.e.map(r => `${r.ts} ${r.level} ${r.cat} ${r.msg}${fieldsText(r) ? " · " + fieldsText(r) : ""}`).join("\n"); }
}
