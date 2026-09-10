// models/layout/panels — la disposition des colonnes (RM2466 volet 3, RM2579, RM2599, RM2952) : ce qui se calcule sans DOM. RM2889.

/** Les onglets de la colonne de droite. Un onglet présent dans la barre et absent d'ici devient inactivable (incident RM2579). */
export const TABS = ["state", "infos", "tickets", "files", "git", "projects", "outline"];   // RM3045 : projets de la session
export const R_WIDTH_DEFAULT = 330;

/** État de la colonne de droite. « select » sur l'onglet DÉJÀ actif replie ; « show » sans onglet déplie sans changer d'onglet ;
 *  RM2952 : `manual` distingue le repli VOULU du repli par défaut — un `show` contextuel (attache) le respecte, un `show` ciblé non. */
export function rightPanelReduce(state, action) {
  const norm = t => (t === "meta" ? "infos" : (TABS.indexOf(t) >= 0 ? t : "infos"));
  const cur = { tab: norm((state && state.tab) || "infos"), collapsed: !state || state.collapsed !== false, manual: !!(state && state.manual) };
  const a = action || {};
  if (a.type === "show") { if (!a.tab && cur.collapsed && cur.manual) return cur; return { tab: norm(a.tab || cur.tab), collapsed: false, manual: false }; }
  if (a.type === "collapse") return { tab: cur.tab, collapsed: true, manual: cur.manual };
  if (a.type === "toggle") return { tab: cur.tab, collapsed: !cur.collapsed, manual: cur.collapsed ? false : true };
  if (a.type === "select") { const tab = norm(a.tab || cur.tab); const collapsed = cur.collapsed ? false : tab === cur.tab; return { tab, collapsed, manual: collapsed }; }
  return cur;
}
/** RM2599 : largeur bornée [240, 900] ; défaut si invalide. */
export function clampWidth(px) { const n = Math.round(Number(px)); if (!isFinite(n)) return R_WIDTH_DEFAULT; return Math.max(240, Math.min(900, n)); }
/** RM3051 : hauteur du volet central bas (ticket/doc sous la session) quand le SPLIT est
 *  actif. Bornée pour qu'aucun des deux ne puisse disparaître à la poignée. */
export const CENTER_H_DEFAULT = 300;
export function clampCenterH(px) { const n = Math.round(Number(px)); if (!isFinite(n)) return CENTER_H_DEFAULT; return Math.max(120, Math.min(1200, n)); }
/** RM2579 : l'onglet de démarrage paramétrable — parmi ceux qu'on peut choisir ; « infos » sinon. */
export function defaultTabOf(t) { return (t === "infos" || t === "tickets" || t === "outline" || t === "state") ? t : "infos"; }
