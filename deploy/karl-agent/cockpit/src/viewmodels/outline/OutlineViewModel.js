// viewmodels/outline/OutlineViewModel — la conversation en minimap, décidée : filtre, recherche, position, lecture inline. RM2889.
import { EntityViewModel } from "../EntityViewModel.js";
import { outMatch, outByKind, outlineDecor, outlineFull } from "../../models/outline/outline.js";

/** e = { items, source, query, filter, pos, open, attached } */
export class OutlineViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.items = this.e.items || []; this.shown = outByKind(outMatch(this.items, this.e.query), this.e.filter || "all"); }
  get query() { return String(this.e.query || ""); }
  get filtered() { return !!(this.query || (this.e.filter && this.e.filter !== "all")); }
  get unresolved() { return this.items.filter(i => i.kind === "question" && !i.resolved).length; }
  /** Ce que dit le compteur : « N msg · ⚠ k sans réponse », ou « N affiché(s) » sous filtre. */
  get count() {
    if (this.filtered) return this.shown.length + " affiché" + (this.shown.length > 1 ? "s" : "");
    return this.items.filter(i => i.kind === "user").length + " msg" + (this.unresolved ? " · ⚠ " + this.unresolved + " sans réponse" : "");
  }
  get kind() { if (!this.e.attached) return "detached"; if (!this.items.length) return "empty"; if (this.filtered && !this.shown.length) return "nomatch"; return "list"; }
  get transcript() { return this.e.source === "transcript"; }
  rows() {
    const pos = this.e.pos, open = this.e.open, tr = this.transcript;
    return this.shown.map(it => { const d = outlineDecor(it); return { line: it.line, text: String(it.text || ""), icon: d.icon, tag: d.tag, cls: "oline" + (d.cls ? " " + d.cls : "") + (pos === it.line ? " ocur" : ""),
      title: d.title + (tr ? " — clic : lire ce message" : " — clic : lire + faire défiler le terminal"), open: open === it.line, full: open === it.line ? outlineFull(it) : "" }; });
  }
}
