// viewmodels/glossary/GlossaryViewModel — le glossaire cherchable (RM2623/2634) et une page d'aide (RM2593), décidés. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { GLOSSARY, glossNorm, glossMatch, glossGroups, buildGloss } from "./glossary.js";

/** e = { query, focus, entries } — entries injectable (tests), GLOSSARY par défaut. */
export class GlossaryViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.entries = this.e.entries || GLOSSARY; this.rows = glossMatch(this.e.query, this.entries); }
  get count() { return this.rows.length + " / " + this.entries.length; }
  /** Le terme à mettre en évidence, ramené à sa forme canonique (un alias ou un pluriel désigne la même entrée). */
  get focusKey() { const f = this.e.focus, k = f ? glossNorm(f) : ""; if (!k) return null; const hit = buildGloss(this.entries).map[k]; return hit ? glossNorm(hit.t) : k; }
  groups() {
    const fk = this.focusKey;
    return glossGroups(this.rows).map(g => ({ label: g.label, items: g.items.map(x => ({ key: glossNorm(x.t), term: x.t, alias: (x.a && x.a.length) ? x.a.join(", ") : "", def: x.d, hi: fk !== null && glossNorm(x.t) === fk })) }));
  }
}

/** e = { topics, topic, md } */
export class HelpViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get toc() { return (this.e.topics || []).map(t => ({ id: String(t.id), title: t.title || t.id, on: t.id === this.e.topic })); }
  get md() { return this.e.md || ""; }
  isTopic(href) { return (this.e.topics || []).some(t => t.id === href); }
}
