// modules/cdc/CdcViewModel — les trois pages décidées : fonctionnalités (table triable, filtrée), feuille de route (par jalon ou par état),
// chapitres (sous-onglets + texte rendu avec ancres D/Q/N/F). RM3044 — reprise des pages du POC AtomBox (pages.vue.js).
import { EntityViewModel } from "../../core/EntityViewModel.js";

export const COLS = [["id", "#"], ["libelle", "Fonctionnalité"], ["domaine", "Domaine"], ["tickets", "Ticket(s)"], ["type", "Type"], ["jalon", "Jalon"], ["etat", "État"], ["date", "Date"]];
export const ORDRE_ETAT = { "livré": 0, "éprouvé": 0, "codé": 1, "en cours": 2, "prévu": 3, "décidé": 3, "à trancher": 4, "en pause": 5 };
const etatKey = (e) => String(e || "").startsWith("écarté") ? "écarté" : String(e || "");
const ETAT_CLS = { "livré": "ok", "éprouvé": "ok", "codé": "wait", "en cours": "wait", "prévu": "", "décidé": "", "à trancher": "due", "en pause": "pause", "écarté": "off" };
export const etatClass = (e) => ETAT_CLS[etatKey(e)] || "";
const ticketsOf = (e) => [].concat(e.rm ? [e.rm] : [], (e.tickets || []).filter(t => t !== e.rm)).map(Number).filter(n => n);

/** L'en-tête commun : les onglets du panneau (fonctionnalités, CDC, feuille de route), les CDC disponibles, celui en contexte. */
export class CdcHeaderViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get title() { const c = this.e.current; return c ? c.title : "CDC vivant"; }
  get context() { const c = this.e.current; return c ? c.client + "/" + c.project + " · " + c.prefix : ""; }
  get choices() { const cs = this.e.cdcs || []; return cs.length > 1 ? cs.map(c => ({ key: c.key, label: c.project + " · " + c.prefix, on: this.e.current && c.key === this.e.current.key })) : []; }
  get pages() { return [["cdc-features", "📋 Fonctionnalités"], ["cdc", "📘 CDC"], ["cdc-roadmap", "🗺 Feuille de route"]].map(([k, l]) => ({ key: k, label: l, on: k === this.e.page })); }
  get empty() { return !(this.e.cdcs || []).length; }
  get error() { return this.e.error || ""; }
}

/** e = { data: {entrees, domaines, jalons, missing}, sort, desc, q } */
export class FeaturesViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.all = ((this.e.data || {}).entrees || []).map(x => Object.assign({}, x, { tickets: ticketsOf(x) })); }
  get missing() { return !!(this.e.data || {}).missing; }
  get hasJalon() { return this.all.some(f => f.jalon !== null && f.jalon !== undefined); }
  get cols() { const s = this.e.sort || "id"; return COLS.filter(([k]) => k !== "jalon" || this.hasJalon).map(([k, l]) => ({ key: k, label: l, on: k === s, arrow: k === s ? (this.e.desc ? " ↓" : " ↑") : "" })); }
  get counts() { const n = {}; for (const f of this.all) { const k = etatKey(f.etat); n[k] = (n[k] || 0) + 1; } return Object.keys(n).sort((a, b) => (ORDRE_ETAT[a] ?? 8) - (ORDRE_ETAT[b] ?? 8)).map(k => ({ etat: k, n: n[k], cls: etatClass(k) })); }
  get query() { return this.e.q || ""; }
  rows() {
    const q = String(this.e.q || "").trim().toLowerCase(); const s = this.e.sort || "id", desc = !!this.e.desc;
    const val = f => { if (s === "jalon") return f.jalon === null || f.jalon === undefined ? 99 : Number(f.jalon); if (s === "etat") return ORDRE_ETAT[etatKey(f.etat)] ?? 8; if (s === "tickets") return f.tickets[0] || 0; return String(f[s] || ""); };
    const rows = this.all.filter(f => !q || [f.id, f.libelle, f.domaine, f.etat, f.type, ...f.tickets.map(t => "rm" + t)].join(" ").toLowerCase().includes(q));
    rows.sort((a, b) => { const x = val(a), y = val(b); const c = typeof x === "number" ? x - y : x.localeCompare(y); return (desc ? -c : c) || (a.id < b.id ? -1 : 1); });
    return rows.map(f => ({ id: f.id, libelle: f.libelle || "", domaine: f.domaine || "", tickets: f.tickets, type: f.type || "", jalon: f.jalon === null || f.jalon === undefined ? "" : "V" + f.jalon, etat: f.etat || "", cls: etatClass(f.etat), date: f.date || "", manuel: !!f.manuel, parent: f.parent || null }));
  }
  get count() { return this.rows().length + " / " + this.all.length; }
}

/** e = { data } — la même donnée que la table, groupée : par jalon quand le registre en déclare, sinon par état (en cours, prévu, en pause, puis les livrées récentes). */
export class RoadmapViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.all = ((this.e.data || {}).entrees || []).map(x => Object.assign({}, x, { tickets: ticketsOf(x) })); this.jalons = (this.e.data || {}).jalons || []; }
  get missing() { return !!(this.e.data || {}).missing; }
  get byJalon() { return this.jalons.length > 0 || this.all.some(f => f.jalon !== null && f.jalon !== undefined); }
  groups() {
    const row = f => ({ id: f.id, libelle: f.libelle || "", domaine: f.domaine || "", tickets: f.tickets, etat: f.etat || "", cls: etatClass(f.etat), date: f.date || "" });
    const byDate = (a, b) => String(b.date || "").localeCompare(String(a.date || "")) || (a.id < b.id ? -1 : 1);
    if (this.byJalon) {
      const nums = new Set(this.all.filter(f => f.jalon !== null && f.jalon !== undefined).map(f => Number(f.jalon))); for (const j of this.jalons) { const v = parseInt(String(j.id || "").replace(/\D/g, ""), 10); if (!isNaN(v)) nums.add(v); }
      const out = [...nums].sort((a, b) => a - b).map(v => { const j = this.jalons.find(x => parseInt(String(x.id || "").replace(/\D/g, ""), 10) === v) || {}; const feats = this.all.filter(f => Number(f.jalon) === v).sort((a, b) => (ORDRE_ETAT[etatKey(a.etat)] ?? 8) - (ORDRE_ETAT[etatKey(b.etat)] ?? 8) || (a.id < b.id ? -1 : 1)); return { label: "V" + v + (j.titre ? " — " + j.titre : ""), note: j.note || "", etat: j.etat || "", avancement: this._avancement(feats), rows: feats.map(row) }; });
      const sans = this.all.filter(f => (f.jalon === null || f.jalon === undefined) && !etatKey(f.etat).startsWith("écarté") && f.etat !== "livré");
      if (sans.length) out.push({ label: "Sans jalon", note: "à placer", etat: "", avancement: this._avancement(sans), rows: sans.sort(byDate).map(row) });
      return out;
    }
    const pick = (k) => this.all.filter(f => etatKey(f.etat) === k).sort(byDate).map(row);
    const out = [["en cours", "En cours", "ce qui est pris, testé ou en MEP"], ["prévu", "Prévu", "à faire ou à l'étude, par date de dernière mise à jour"], ["en pause", "En pause", "bloqué par un tiers"]].map(([k, l, n]) => ({ label: l, note: n, etat: k, avancement: "", rows: pick(k) })).filter(g => g.rows.length);
    const livre = pick("livré").slice(0, 30); if (livre.length) out.push({ label: "Livré récemment", note: "les 30 dernières", etat: "livré", avancement: "", rows: livre });
    return out;
  }
  _avancement(feats) { const n = {}; for (const f of feats) { const k = etatKey(f.etat); n[k] = (n[k] || 0) + 1; } return Object.keys(n).sort((a, b) => (ORDRE_ETAT[a] ?? 8) - (ORDRE_ETAT[b] ?? 8)).map(k => k + " " + n[k]).join(" · "); }
}

/** e = { cdc, path, md } — les chapitres d'un CDC en sous-onglets, le chapitre courant rendu ; les identifiants D/C/Q/N/F en tête de cellule reçoivent une ancre. */
export class ChaptersViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get tabs() { const c = this.e.cdc; return c ? (c.chapters || []).map(ch => ({ path: ch.path, title: (ch.title || ch.file).replace(/^\d+\s*[—-]\s*/, ""), on: ch.path === this.e.path })) : []; }
  get md() { return this.e.md || ""; }
  /** Ancres : `<td>D012` / `<td><del>Q001` deviennent `<td id="sec-D012">…` ; un `RM1234` nu devient un geste vers la fiche. */
  anchored(htmlText) {
    return String(htmlText || "").replace(/<td>(<del>|<s>)?([DCQNF]\d{3}[a-z]?)(?=[\s<])/g, (m, del, id) => '<td id="sec-' + id + '">' + (del || "") + id)
      .replace(/\bRM(\d{3,5})\b(?![^<]*<\/a>)/g, '<a href="#" class="cdcrm" data-action="ticket" data-rm="$1">RM$1</a>');
  }
  isDocLink(href) { return !!href && !/^[a-z]+:/i.test(href) && !href.startsWith("/") && !href.startsWith("#") && href.split("#")[0].endsWith(".md"); }
  resolve(href) { const base = String(this.e.path || "").split("/").slice(0, -1); for (const p of href.split("#")[0].split("/")) { if (p === "..") base.pop(); else if (p !== ".") base.push(p); } return base.join("/"); }
}
