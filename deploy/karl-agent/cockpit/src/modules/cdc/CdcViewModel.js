// modules/cdc/CdcViewModel — les trois pages décidées : fonctionnalités (table triable, filtrée), feuille de route (par jalon ou par état),
// chapitres (sous-onglets + texte rendu avec ancres D/Q/N/F). RM3044 — reprise des pages du POC AtomBox (pages.vue.js).
import { EntityViewModel } from "../../core/EntityViewModel.js";

export const COLS = [["id", "#"], ["libelle", "Fonctionnalité"], ["domaine", "Domaine"], ["tickets", "Ticket(s)"], ["type", "Type"], ["version", "Version"], ["etat", "État"], ["date", "Date"]];
/** La version d'une entrée : `version` (V0, V1…, RM3015-D018) ou l'ancien `jalon` entier (AtomBox) rendu `V<n>` ; "" sinon. */
export const versionOf = (e) => e.version ? String(e.version) : (e.jalon === null || e.jalon === undefined ? "" : "V" + e.jalon);
export const ORDRE_ETAT = { "livré": 0, "éprouvé": 0, "codé": 1, "en cours": 2, "prévu": 3, "décidé": 3, "à trancher": 4, "en pause": 5 };
const etatKey = (e) => String(e || "").startsWith("écarté") ? "écarté" : String(e || "");
const ETAT_CLS = { "livré": "ok", "éprouvé": "ok", "codé": "wait", "en cours": "wait", "prévu": "", "décidé": "", "à trancher": "due", "en pause": "pause", "écarté": "off" };
export const etatClass = (e) => ETAT_CLS[etatKey(e)] || "";
const ticketsOf = (e) => [].concat(e.rm ? [e.rm] : [], (e.tickets || []).filter(t => t !== e.rm)).map(Number).filter(n => n);

// RM3044-D003 : les onglets suivent PRÉCISÉMENT les parties d'un CDC telles que la norme `cdc` les définit (§ « Les livrables d'un
// CDC complet » et § « Le CDC vivant du projet ») : sommaire, chapitres thématiques, roadmap, dictionnaire, registre des décisions, vrac,
// questions ouvertes, glossaire, guide. Nom et rang canoniques par fichier générique ; les chapitres numérotés (AtomBox) gardent leur titre.
const CANON = [[/^cdc-roadmap\.md$|roadmap|feuille/i, "🗺 Roadmap", 20], [/^cdc-dict\.md$|dictionnaire/i, "📚 Dictionnaire", 30],
               [/^cdc-decisions\.md$|decision/i, "⚖️ Registre des décisions", 40], [/^cdc-notes\.md$|vrac|notes/i, "🗒 Vrac", 50],
               [/^cdc-questions\.md$|question/i, "❓ Questions ouvertes", 60], [/gloss/i, "📖 Glossaire", 70], [/^cdc-help\.md$|help|aide|guide/i, "📖 Guide", 80]];
/** Libellé d'onglet d'un chapitre : nom canonique de la norme pour les parties connues ; sinon le titre, numéro et « — projet … » retirés. */
export function chapterLabel(ch) {
  const canon = CANON.find(([rx]) => rx.test(ch.file)); if (canon && /^cdc-[a-z]+\.md$/.test(ch.file)) return canon[1];
  const t = String(ch.title || ch.file).replace(/^\d+\s*[—-]\s*/, "").replace(/\s*[—-]\s*(projet|CDC).*$/i, "").replace(/\s*\((RM\d+|`[^`]*`)\)\s*$/, "").trim();
  const ic = CANON.find(([rx]) => rx.test(ch.file + " " + t)); return (ic ? ic[1].split(" ")[0] + " " : "") + t;
}
/** Rang d'un chapitre dans l'ordre de la norme ; les chapitres thématiques (numérotés, non canoniques) passent avant les registres. */
export function chapterRank(ch) { const canon = CANON.find(([rx]) => rx.test(ch.file)); return canon ? canon[2] : 10; }
const isSommaire = (ch) => ch.file === "cdc.md" || /-00-/.test(ch.file);
const isFeaturesChapter = (ch) => ch.file === "cdc-features.md" || /-10-/.test(ch.file);
/** Les onglets d'un CDC, tous au même niveau : la table, le sommaire, puis chaque chapitre (sauf le chapitre features généré). Partagé avec l'onglet projets (RM3045). */
export function cdcTabs(cdc) {
  const chs = cdc ? (cdc.chapters || []) : []; const som = chs.find(isSommaire);
  const fixed = [["cdc-features", "📋 Fonctionnalités", !!(cdc && cdc.registry !== false)], [som ? "chap:" + som.path : "cdc", "📘 CDC vivant", true]];
  const rest = chs.filter(ch => ch !== som && !isFeaturesChapter(ch)).map((ch, i) => [ch, chapterRank(ch), i]).sort((x, y) => x[1] - y[1] || x[2] - y[2]).map(([ch]) => ["chap:" + ch.path, chapterLabel(ch), true]);
  return fixed.concat(rest).map(([key, label, enabled]) => ({ key, label, enabled }));
}
/** L'en-tête commun : les onglets du panneau (fonctionnalités, CDC, feuille de route), les CDC disponibles, celui en contexte. */
export class CdcHeaderViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get title() { const c = this.e.current; return c ? c.title : "CDC vivant"; }
  get context() { const c = this.e.current; return c ? c.client + "/" + c.project + " · " + c.prefix : ""; }
  get choices() { const cs = this.e.cdcs || []; return cs.length > 1 ? cs.map(c => ({ key: c.key, label: c.project + " · " + c.prefix, on: this.e.current && c.key === this.e.current.key })) : []; }
  /** Tous les onglets AU MÊME NIVEAU (retour Mathieu, RM3044) : la table, le sommaire du CDC, la feuille de route, puis chaque chapitre du CDC
   *  (le chapitre 10 « fonctionnalités », généré, est déjà la table : il n'a pas d'onglet). `chap:<path>` = un chapitre. */
  // RM3044 (retour Mathieu) : plus de « feuille de route » dérivée du registre — redondante avec la table ; la roadmap est le chapitre cdc-roadmap.md (rôle par version, D018)
  get pages() { return cdcTabs(this.e.current).map(t => ({ key: t.key, label: t.label, on: t.key === this.e.page || (t.key.startsWith("chap:") && this.e.page === "cdc" && this.e.path === t.key.slice(5)) })); }
  get empty() { return !(this.e.cdcs || []).length; }
  get error() { return this.e.error || ""; }
}

/** e = { data: {entrees, domaines, jalons, missing}, sort, desc, q } */
export class FeaturesViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.all = ((this.e.data || {}).entrees || []).map(x => Object.assign({}, x, { tickets: ticketsOf(x) })); }
  get missing() { return !!(this.e.data || {}).missing; }
  get hasVersion() { return this.all.some(f => versionOf(f)); }
  get cols() { const s = this.e.sort || "id"; return COLS.filter(([k]) => k !== "version" || this.hasVersion).map(([k, l]) => ({ key: k, label: l, on: k === s, arrow: k === s ? (this.e.desc ? " ↓" : " ↑") : "" })); }
  get counts() { const n = {}; for (const f of this.all) { const k = etatKey(f.etat); n[k] = (n[k] || 0) + 1; } return Object.keys(n).sort((a, b) => (ORDRE_ETAT[a] ?? 8) - (ORDRE_ETAT[b] ?? 8)).map(k => ({ etat: k, n: n[k], cls: etatClass(k) })); }
  get query() { return this.e.q || ""; }
  rows() {
    const q = String(this.e.q || "").trim().toLowerCase(); const s = this.e.sort || "id", desc = !!this.e.desc;
    const val = f => { if (s === "version") { const vv = versionOf(f); return vv ? "0" + vv : "1"; } /* sans version en dernier (ICU trie la ponctuation avant les lettres) */ if (s === "etat") return ORDRE_ETAT[etatKey(f.etat)] ?? 8; if (s === "tickets") return f.tickets[0] || 0; return String(f[s] || ""); };
    const rows = this.all.filter(f => !q || [f.id, f.libelle, f.domaine, f.etat, f.type, ...f.tickets.map(t => "rm" + t)].join(" ").toLowerCase().includes(q));
    rows.sort((a, b) => { const x = val(a), y = val(b); const c = typeof x === "number" ? x - y : x.localeCompare(y); return (desc ? -c : c) || (a.id < b.id ? -1 : 1); });
    return rows.map(f => ({ id: f.id, libelle: f.libelle || "", domaine: f.domaine || "", tickets: f.tickets, type: f.type || "", version: versionOf(f), etat: f.etat || "", cls: etatClass(f.etat), date: f.date || "", manuel: !!f.manuel, parent: f.parent || null }));
  }
  get count() { return this.rows().length + " / " + this.all.length; }
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
