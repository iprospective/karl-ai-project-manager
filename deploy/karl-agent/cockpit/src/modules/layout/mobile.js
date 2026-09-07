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
