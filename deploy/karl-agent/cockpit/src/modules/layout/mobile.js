// modules/layout/mobile — le GABARIT mobile (RM3003) : pas un second cockpit, une autre disposition des mêmes surfaces. Sur un écran étroit
// (ou `?layout=mobile`), la page montre UNE colonne à la fois — panneaux de gauche, centre (onglets, terminal, vues), colonne de droite
// (worklog, infos, tickets, fichiers…) — et une barre de navigation en bas ; les contrôleurs, ViewModels et vues sont ceux du bureau,
// rien n'est rendu deux fois. Fonctions PURES : aucun DOM.

export const MOBILE_MAX_PX = 820;                 // au-delà : bureau (media query posée par boot.js)
export const PAGES = ["left", "center", "right"];
export const PAGE_LABELS = { left: "panneaux", center: "centre", right: "session" };
export const PAGE_ICONS = { left: "▶", center: "▣", right: "▤" };

/** Disposition effective : un forçage explicite gagne, sinon la largeur décide. */
export function detectLayout({ forced = null, narrow = false } = {}) {
  if (forced === "mobile" || forced === "desktop") return forced;
  return narrow ? "mobile" : "desktop";
}
/** Le forçage : `?layout=mobile|desktop` dans l'URL, sinon la préférence `karlLayout` de ce navigateur, sinon rien. */
export function forcedLayout(search, stored) {
  const m = /[?&]layout=(mobile|desktop)\b/.exec(String(search || ""));
  if (m) return m[1];
  return stored === "mobile" || stored === "desktop" ? stored : null;
}
export function pageOf(p) { return PAGES.includes(p) ? p : "left"; }
/** Les entrées de la barre du bas : la page active, le compteur des sessions qui attendent sur « panneaux », le libellé de la droite. */
export function navItems(page, { attention = 0, attached = null } = {}) {
  return PAGES.map(p => ({ page: p, icon: PAGE_ICONS[p], active: p === page,
    label: p === "right" ? (attached ? "session " + (/^\d+$/.test(String(attached)) ? "RM" + attached : attached) : "détail") : PAGE_LABELS[p],
    badge: p === "left" && attention > 0 ? String(attention) : "" }));
}

/* RM3270 — l'écran utile au doigt. Trois ajouts au gabarit :
   le PLEIN ÉCRAN (le centre seul, sans barre du haut) qui s'enclenche quand le clavier
   monte, la BARRE DU HAUT en icônes (les importantes sur une ligne, le reste sous « … »),
   et le double appui (nom d'abord, action ensuite) — au doigt, on ne déclenche pas à l'aveugle. */

/** Le clavier logiciel mange le bas de la fenêtre : le viewport visible rétrécit sans que la
 *  fenêtre change de taille. Sous ce ratio, on considère qu'il est ouvert. Pur. */
export function keyboardOpen({ viewportH = 0, windowH = 0, ratio = 0.75 } = {}) {
  if (!(viewportH > 0 && windowH > 0)) return false;
  return viewportH < windowH * ratio;
}

/** La bascule plein écran de la barre du bas (⛶ / ↙). Pur. */
export function fullItem(full) {
  return { icon: full ? "↙" : "⛶", label: full ? "vue normale" : "plein écran", full: !!full };
}

/** Défauts si la conf d'instance ne dit rien (RM3418 : elle le dit, via /cockpit-config). */
export const HEADER_PRIMARY = ["yesatt", "yesall", "voicebtn", "feedbtn", "setbtn", "helpbtn"];
export const SESSION_PRIMARY = ["yesbtn", "micbtn", "reattach"];

/**
 * Répartit les éléments d'une barre (RM3418) : ce qui reste sur la LIGNE (dans l'ordre
 * demandé), ce qui passe sous « … », ce qui ne s'affiche pas du tout. Pur.
 * `line` et `hidden` viennent de la conf d'instance ; un identifiant inconnu est ignoré.
 */
export function barSplit(ids, line, hidden = []) {
  const présents = ids || [];
  const masqués = présents.filter(id => (hidden || []).includes(id));
  const sur_ligne = (line || []).filter(id => présents.includes(id) && !masqués.includes(id));
  return { line: sur_ligne, extra: présents.filter(id => !sur_ligne.includes(id) && !masqués.includes(id)), hidden: masqués };
}

/**
 * L'ordre d'affichage demandé, en numéros de `order` CSS. Les éléments cités passent
 * devant, dans l'ordre de la conf ; les autres suivent. Pur.
 * Limite assumée : `order` ne joue qu'entre frères — un bouton groupé (`.hgo`) se range
 * dans son groupe, et le groupe prend le rang de son premier bouton cité.
 */
export function barOrder(line) {
  const rangs = {};
  (line || []).forEach((id, i) => { rangs[id] = i + 1; });
  return (id) => (rangs[id] === undefined ? 99 : rangs[id]);
}

/** « 🔓 bob (admin) » → « 🔓 bob » : en mobile, le rôle ne vaut pas une ligne. Pur. */
export function lockCompact(text) {
  return String(text || "").replace(/\s*\((?:admin|superadmin)\)\s*$/, "");
}

/** L'icône d'un libellé : ce qui précède le premier espace (« 🩺 Supervision » → « 🩺 »). Pur. */
export function iconOf(label) {
  const t = String(label || "").trim();
  if (!t) return "";
  const first = t.split(/\s+/)[0];
  return first === t ? t : first;
}

/** Le nom à montrer au premier appui : le libellé du bouton s'il en a un, sinon le début de son
 *  infobulle (les boutons déjà réduits à une icône n'ont que ça à dire). Pur. */
export function sayLabel({ text = "", title = "" } = {}) {
  const t = String(text || "").trim();
  if (t && t !== iconOf(t)) return t;
  const short = String(title || "").split(/[—:(]/)[0].trim();
  return short ? (iconOf(t) ? iconOf(t) + " " + short : short) : t;
}
