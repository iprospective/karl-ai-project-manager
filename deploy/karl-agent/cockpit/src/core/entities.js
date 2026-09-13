// core/entities — le REGISTRE des types d'entités du cockpit (RM3002, § 10 du plan RM2889).
//
// Un type = ce que le centre, les listes et l'épinglage savaient chacun dans leur coin par `kind === "…"` : son icône, son libellé
// d'onglet, son infobulle, comment on l'ouvre et on le ferme, le titre de son erreur — et, lié par son ViewModel (`bindEntity`), la
// composition de ses QUATRE NIVEAUX d'affichage depuis une seule `sections()` : `row` (une ligne : icône, titre, pastilles),
// `card` (la ligne + les sections résumées), `panel` (+ toutes les sections courantes), `full` (tout). La convention CSS est unique et
// préfixée par niveau (`.e-row`, `.e-card`, `.e-sec`…, styles/_entities.scss) : ajouter un type ne coûte aucune ligne de CSS.
// Aucun import de module ici (le socle ne voit pas les domaines) : les recettes d'ouverture ne parlent qu'à l'`api` que le centre prête.
import { html } from "./html.js";

export const LEVELS = ["row", "card", "panel", "full"];
const RANK = { row: 0, card: 1, panel: 2, full: 3 };
const base = (x) => String(x || "").replace(/\/+$/, "").split("/").pop();
const avec = (tete, suite) => (suite ? tete + " — " + suite : tete);

const DEFAULT = Object.freeze({
  icon: "•", label: "",
  /** infobulle d'un onglet : (key, parts, lbl, resolu) → texte */
  tooltip: (key, parts, lbl) => lbl || key,
  /** libellé court d'un onglet de vue : (parts, hint) → texte */
  tabLabel: (parts, hint) => String(hint || "vue"),
  errorTitle: "Contenu indisponible",
  surface: false,       // une surface historique enregistrée auprès du centre (open/close/current)
  closeLast: false,     // fermée après les autres (c'est elle qui rallume le tableau de bord)
  panel: false,         // un panneau central nommé (commandes, réglages, journal, mémoire)
  fixed: false,         // l'onglet permanent
  restorable: true,     // rouvert au démarrage si c'était l'onglet actif (une session, jamais : RM2672)
  open: null,           // (api, tab, parts) → ouvre la vue
  ViewModel: null,      // lié par bindEntity depuis le module qui le possède
});

const REG = new Map();
export function defineEntity(type, def = {}) { const e = Object.assign({}, DEFAULT, def, { type }); REG.set(type, e); return e; }
/** Le module propriétaire lie son ViewModel au type (import du ViewModel vers le socle, jamais l'inverse). */
export function bindEntity(type, ViewModel) { const e = REG.get(type) || defineEntity(type); e.ViewModel = ViewModel; return e; }
export function entity(type) { return REG.get(type) || Object.assign({}, DEFAULT, { type: String(type || "") }); }
export function isEntity(type) { return REG.has(type); }
export function entityTypes() { return [...REG.keys()]; }
export function iconOf(type) { return entity(type).icon; }
export function surfaceTypes() { return entityTypes().filter(t => REG.get(t).surface); }
export function panelTypes() { return entityTypes().filter(t => REG.get(t).panel); }
/** Infobulle d'un onglet (RM2775) : `parse` = parseViewKey ; `rcache` = résolutions indexées (store.view). */
export function tooltipOf(tab, rcache, parse) {
  const t = tab || {}; if (!t.kind && !t.key && !t.label) return "";
  const key = String(t.key == null ? "" : t.key), lbl = String(t.label || ""), parts = parse ? parse(key) : [];
  const cache = rcache || {}; const resolu = (id) => { const r = cache[String(id)]; return (r && r.found && r.title) ? String(r.title) : ""; };
  return entity(t.kind).tooltip(key, parts, lbl, resolu);
}
export function tabLabelOf(kind, parts, hint) { return entity(kind).tabLabel(parts || [], hint); }

// ── les types du cockpit ───────────────────────────────────────────────────────────────────────────────────────────────────────────
defineEntity("dash",      { icon: "📊", label: "tableau de bord", fixed: true, tooltip: () => "tableau de bord", open: (api) => api.openDashboard() });
defineEntity("session",   { icon: "▶", label: "session", surface: true, restorable: false,
  tooltip: (key, p, lbl, resolu) => avec(/^\d+$/.test(key) ? "session RM" + key : "session " + key, resolu(key)), open: (api, t) => api.openSessionTab(t.key) });
defineEntity("review",    { icon: "🧪", label: "ticket", surface: true, tooltip: (key, p, lbl, resolu) => avec("RM" + key, resolu(key)), open: (api, t) => api.surface("review", "open", t.key) });
defineEntity("project",   { icon: "📁", label: "projet", surface: true, tooltip: (key) => avec("fiche projet", key), open: (api, t) => api.surface("project", "open", t.key) });
defineEntity("newticket", { icon: "＋", label: "nouveau ticket", surface: true, closeLast: true, tooltip: () => "nouveau ticket", open: (api) => api.surface("newticket", "open") });
defineEntity("client",    { icon: "🏢", label: "client", tooltip: (key, p) => avec("fiche client", p[0] || key), open: (api, t, p) => api.openClient(p[0]) });
defineEntity("contacts", { icon: "👤", label: "annuaire", tooltip: (key, p) => avec("annuaire", p[0] ? "« " + p[0] + " »" : ""), tabLabel: (p) => p[0] ? "👤 " + p[0] : "annuaire", open: (api, t, p) => api.openContacts(p[0]) });
defineEntity("contact",  { icon: "👤", label: "personne", errorTitle: "Fiche introuvable", tooltip: (key, p) => avec("personne", p[0] || key), tabLabel: (p) => p[0] || "personne", open: (api, t, p) => api.openContact(p[0]) });
defineEntity("conf",      { icon: "⚙", label: "configuration", tooltip: (key, p) => avec("configuration", p[0] === "project" ? (p[1] || "") + "/" + (p[2] || "") : (p[1] || "")), open: (api, t, p) => api.openConf(p[0], p[1], p[2]) });
defineEntity("file",      { icon: "📄", label: "fichier", tooltip: (key, p, lbl) => avec("fichier", p[2] || p[1] || lbl), tabLabel: (p) => base(p[2]) || base(p[1]) || "fichier", open: (api, t, p) => api.openFile(p[0], p[1], p[2], p[3]) });
defineEntity("dir",       { icon: "🗂", label: "dossier", tooltip: (key, p) => avec("dossier", p[2] || "racine du dépôt"), tabLabel: (p) => (base(p[2]) || "racine") + "/", open: (api, t, p) => api.openDir(p[0], p[1], p[2], p[3]) });
defineEntity("commit",    { icon: "⎇", label: "commit", errorTitle: "Commit indisponible", tooltip: (key, p, lbl) => avec("commit " + (p[1] || lbl), p[0] ? "session " + p[0] : ""), tabLabel: (p) => String(p[1] || "").slice(0, 8) || "commit", open: (api, t, p) => api.openCommit(p[0], p[1]) });
defineEntity("mail",      { icon: "📧", label: "email", errorTitle: "Email indisponible", tooltip: (key, p, lbl) => avec("email", lbl), tabLabel: (p, hint) => { const t = String(hint || p[1] || "email").trim(); return t.length > 30 ? t.slice(0, 29) + "…" : t; }, open: (api, t, p) => api.openMail(p[0], t.label) });
defineEntity("pm",        { icon: "⚙", label: "commandes pm", panel: true, tooltip: () => "commandes PM", open: (api) => api.openPanel("pm") });
defineEntity("settings",  { icon: "🔧", label: "réglages", panel: true, tooltip: () => "réglages du cockpit", open: (api) => api.openPanel("settings") });
defineEntity("journal",   { icon: "📜", label: "journal", panel: true, tooltip: () => "journal (serveur + navigateur)", open: (api) => api.openPanel("journal") });
defineEntity("memory",    { icon: "🧠", label: "mémoire", panel: true, tooltip: () => "mémoire par module (sonde)", open: (api) => api.openPanel("memory") });
// RM3044 : le CDC vivant — un panneau, trois onglets dedans (modèle POC AtomBox : Fonctionnalités · CDC · Feuille de route)
defineEntity("cdc",       { icon: "📋", label: "CDC", panel: true, tooltip: () => "CDC vivant : fonctionnalités, chapitres, feuille de route", open: (api) => api.openPanel("cdc") });

/** Les références cliquables `data-link` (RM2585/2596) : ce que chaque sorte déclenche, avec ce que le contexte prête. */
export const LINKS = {
  ticket: (ctx, n) => ctx.showTicket && ctx.showTicket(n.dataset.rm),
  file:   (ctx, n) => ctx.openFileRef && ctx.openFileRef(n.dataset.path),
  ext:    () => {},   // le navigateur suit le lien ; on a seulement empêché la tuile de s'attacher
};
export function linkAction(kind) { return LINKS[kind] || null; }

// ── les quatre niveaux ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
/** Les sections d'un ViewModel visibles à un niveau : row = aucune ; card = celles marquées `summary` ; panel = tout sauf `full` ; full = tout. */
export function sectionsAt(vm, level) {
  const rank = RANK[level]; if (rank === undefined) throw new Error("niveau inconnu : " + level);
  if (rank === 0) return [];
  return (vm.sections() || []).filter(s => s && (rank === 1 ? !!s.summary : RANK[s.level || "panel"] <= rank));
}
const kv = (k, v) => html`<div class="e-kv"><span class="e-k">${k}</span><span class="e-v">${v}</span></div>`;
/** Le corps d'une section : fragment sûr, texte, paires [clé, valeur] (liste clé/valeur), liste de textes, ou fonction (vm) → l'un d'eux. */
export function sectionBody(s, vm) {
  let b = typeof s.body === "function" ? s.body(vm) : s.body;
  if (b == null || b === "") return html`<span class="e-empty">${s.empty || "—"}</span>`;
  if (Array.isArray(b)) return b.length ? html`${b.map(x => (Array.isArray(x) ? kv(x[0], x[1]) : html`<div class="e-line">${x}</div>`))}` : html`<span class="e-empty">${s.empty || "—"}</span>`;
  return html`${b}`;
}
/**
 * Compose un niveau d'affichage d'un ViewModel (§ 10) : en-tête (icône du type, titre, sous-titre, pastilles) puis les sections du
 * niveau. `deps.attrs` (Safe) s'ajoute à la racine (data-action d'une liste, par exemple) ; `deps.icon` remplace l'icône du type.
 */
export function renderEntity(vm, level = "card", deps = {}) {
  const type = vm.type || (vm.e && vm.e.type) || ""; const def = entity(type);
  const secs = sectionsAt(vm, level);
  const badges = (vm.badges || []).filter(Boolean);
  return html`<div class="e-entity e-${level}" data-type="${type}" data-id="${vm.id == null ? "" : vm.id}"${deps.attrs || ""}><div class="e-head"><span class="e-icon">${deps.icon || def.icon}</span><span class="e-title">${vm.title || vm.id || def.label}</span>${vm.subtitle ? html`<span class="e-sub">${vm.subtitle}</span>` : ""}${badges.length ? html`<span class="e-badges">${badges.map(b => html`<span class="e-badge${b && b.cls ? " " + b.cls : ""}"${b && b.title ? html` title="${b.title}"` : ""}>${b && b.text != null ? b.text : b}</span>`)}</span>` : ""}</div>${secs.map(s => html`<section class="e-sec" data-sec="${s.id || ""}">${s.title ? html`<h4 class="e-sec-title">${s.title}</h4>` : ""}<div class="e-sec-body">${sectionBody(s, vm)}</div></section>`)}</div>`;
}
/** Les quatre niveaux d'une entité brute : `entityLevels("review", fiche, ctx).card`. */
export function entityLevels(type, e, ctx = {}, deps = {}) {
  const def = entity(type); if (!def.ViewModel) throw new Error("aucun ViewModel lié au type " + type);
  const vm = new def.ViewModel(e, ctx); const out = {};
  for (const l of LEVELS) out[l] = renderEntity(vm, l, deps);
  return out;
}
