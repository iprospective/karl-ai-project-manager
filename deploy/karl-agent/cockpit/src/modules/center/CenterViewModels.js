// viewmodels/center — onglets, historique, titre, contenus. RM2889, cluster centre.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { tabId, tabTooltip, ICONS } from "./tabs.js";
import { parseViewKey } from "./viewKey.js";

/** La barre d'onglets : e = { tabs, active } ; ctx = { resolve } */
export class TabsViewModel extends EntityViewModel {
  entries() {
    return (this.e.tabs || []).map(t => {
      const id = tabId(t.kind, t.key);
      return { id, kind: t.kind, label: t.label, fixed: !!t.fixed, pinned: !!t.pinned,
        cls: "ctab" + (id === this.e.active ? " active" : "") + (t.pinned ? "" : " temp"),
        icon: ICONS[t.kind] || "•",
        tooltip: tabTooltip(t, this.ctx.resolve || {}, parseViewKey) + (t.fixed ? " — toujours là" : t.pinned ? "" : " — non épinglé : la prochaine vue le remplace"),
        pinTitle: t.pinned ? "Détacher" : "Épingler : garder cet onglet ouvert" };
    });
  }
}

/** La liste de l'historique : la plus récente en tête, la courante marquée, les fermées grisées. */
export class HistoryViewModel extends EntityViewModel {
  rows() {
    const st = this.e && Array.isArray(this.e.items) ? this.e : { items: [], idx: -1 };
    const isOpen = this.ctx.isOpen;
    const out = [];
    for (let i = st.items.length - 1; i >= 0; i--) {
      const e = st.items[i];
      const ouvert = !isOpen || isOpen(e.id);
      out.push({ id: e.id, label: e.label, icon: ICONS[e.kind] || "•", cur: i === st.idx, ouvert,
        title: ouvert ? e.id : e.id + " — vue fermée depuis" });
    }
    return out;
  }
}

/** Le titre du centre pour ce que le contrôleur possède (vue, panneau, tableau de bord, rien). */
export class CenterTitleViewModel extends EntityViewModel {
  /** e = { view: {kind,key}|null, panel: name|null, active, tabs, panels } */
  get icon() { return this.e.view ? (ICONS[this.e.view.kind] || "•") : this.e.panel === "pm" ? "⚙" : this.e.panel === "journal" ? "📜" : this.e.panel === "memory" ? "🧠" : "🔧"; }
  get viewLabel() {
    const v = this.e.view; if (!v) return "";
    const t = (this.e.tabs || []).find(x => x.kind === v.kind && x.key === v.key);
    return (t && t.label) || parseViewKey(v.key).pop() || "";
  }
  get panelLabel() { const p = this.e.panels || {}; return (p[this.e.panel] || {}).label || this.e.panel || ""; }
  get mode() { return this.e.view ? "view" : this.e.panel ? "panel" : this.e.active === "dash:" ? "dash" : "none"; }
}

/** Un fichier ouvert : le corps se rend à UN seul endroit (RM2861). ctx.md = rendu markdown. */
export class FileViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get content() { return String(this.e.content == null ? "" : this.e.content); }
  get markdown() { return !!this.e.markdown; }
  get title() { return this.e.path || this.e.name || "fichier"; }
  get sizeKo() { return this.e.size != null ? " · " + (Math.round(this.e.size / 102.4) / 10) + " Ko" : ""; }
  /** HTML déjà sûr du corps markdown (rendu injecté, qui échappe lui-même). */
  get rendered() { return this.ctx.md ? this.ctx.md(this.content) : ""; }
}

/** Un dossier NAVIGABLE : fil d'ariane et entrées, chacune emportant la portée. */
export class DirViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get src() { return String(this.e.src || "wt"); }
  get wt() { return String(this.e.wt || ""); }
  get path() { return String(this.e.path || ""); }
  get tag() { return String(this.e.tag || ""); }
  get entries() { return this.e.entries || []; }
  crumbs() {
    const crumbs = [{ name: this.e.rootName || "racine", path: "" }];
    let acc = "";
    for (const seg of this.path.split("/").filter(Boolean)) { acc = acc ? acc + "/" + seg : seg; crumbs.push({ name: seg, path: acc }); }
    return crumbs;
  }
  child(name) { return (this.path ? this.path + "/" : "") + name; }
}

export class EmailViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get subject() { return this.e.subject || "(sans sujet)"; }
  get from() { return this.e.from_name ? this.e.from_name + " <" + this.e.from + ">" : this.e.from; }
  get attachments() { return (this.e.attachment_list || []).map(a => (a && (a.name || a)) || "").filter(Boolean); }
  lines() { const m = this.e; return [["de", this.from], ["date", m.date], ["dossier", m.folder], ["état", m.state], ["ticket", m.created_rm ? "RM" + m.created_rm : ""], ["pièces jointes", this.attachments.join(" · ")]].filter(([, v]) => v); }
}

export class ClientViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get name() { return this.e.name || this.e.client || "client"; }
  identity() { const c = this.e; return [["slug", c.client], ["statut", c.status], ["type", c.type], ["créé le", c.created]].filter(([, v]) => v); }
  contacts() { return (this.e.contacts || []).map(p => ({ nom: [p.first_name, p.last_name].filter(Boolean).join(" ") || p.name || "—", det: [p.title, p.role, p.email, p.phone].filter(Boolean).join(" · "), internal: !!p.internal })); }
  get team() { return ((this.e.defaults || {}).team || []).map(t => (t && (t.username || t.email)) || "").filter(Boolean); }
  get priority() { return (this.e.defaults || {}).priority || ""; }
  get projects() { return this.e.projects || []; }
  get used() { return this.e.projects_used || []; }
  get docs() { return this.e.docs || []; }
}
