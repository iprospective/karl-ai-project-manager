// controllers/layout.controller — la disposition : colonne de droite à onglets (un seul actif, repli voulu respecté), colonne
// gauche repliable, largeur réglable à la poignée, préférences de démarrage. RM2889 (RM2466/2579/2599/2952).
//
// Hôtes : `main`, `rpanel` (l'aside), `rnav` (barre d'onglets), `rtoggle`, `ltoggle`, `rhandle` (poignée), `startOpen`, `defTab`
// (réglages). Ce qu'un onglet visible déclenche (charger l'outline, le worklog, les fichiers, rendre l'encart…) est prêté par
// `onApply(state)` — le routeur de la disposition ne connaît pas les domaines qu'il expose.
import { rightPanelReduce, clampWidth } from "../models/layout/panels.js";
import { LayoutService } from "../services/layout.service.js";

export function mountLayout(hosts = {}, ctx = {}) {
  const h = hosts, svc = ctx.service || new LayoutService({ storage: ctx.storage });
  const root = ctx.root || (typeof document !== "undefined" ? document : null);
  const state = { right: { tab: "infos", collapsed: true, manual: false }, left: false, resizing: false, rightEdge: 0 };
  const cls = (el, c, on) => { if (el && el.classList) el.classList.toggle(c, !!on); };
  const all = (sel) => (h.rpanel && h.rpanel.querySelectorAll ? [...h.rpanel.querySelectorAll(sel)] : []);

  function applyRight() {
    const r = state.right;
    cls(h.rpanel, "collapsed", r.collapsed);
    cls(h.rpanel, "wide", !r.collapsed && r.tab === "outline");                       // RM2579 : la conversation est plus large
    all(".rnav button").forEach(b => cls(b, "active", b.dataset && b.dataset.rpanel === r.tab));
    all(".rp").forEach(el => cls(el, "active", el.id === "rp-" + r.tab));
    svc.saveRight(r);
    if (ctx.onApply) ctx.onApply(r, (tab) => !r.collapsed && r.tab === tab);       // les domaines chargent ce qui devient visible
  }
  function applyLeft() { cls(h.main, "lcollapsed", state.left); svc.saveLeft(state.left); }
  function dispatch(action) { state.right = rightPanelReduce(state.right, action); applyRight(); return state.right; }
  const switchRight = (tab) => dispatch({ type: "select", tab }), showRight = (tab) => dispatch({ type: "show", tab }), toggleRight = () => dispatch({ type: "toggle" }), collapseRight = () => dispatch({ type: "collapse" });
  const rightVisible = (tab) => !state.right.collapsed && state.right.tab === tab;
  function toggleLeft() { state.left = !state.left; applyLeft(); }
  // ── largeur (RM2599/2952) ──
  const setVar = (px) => { if (root && root.documentElement) root.documentElement.style.setProperty("--rpanel-w", clampWidth(px) + "px"); };
  function setRightWidth(px) { setVar(px); }
  function resetWidth() { if (root && root.documentElement) root.documentElement.style.removeProperty("--rpanel-w"); svc.resetWidth(); if (ctx.onResized) ctx.onResized(); }   // RM2952 : on RETIRE la variable, pas 330 en dur
  function startResize(e) { if (!h.rpanel || (h.rpanel.classList && h.rpanel.classList.contains("collapsed"))) return; state.resizing = true; state.rightEdge = h.rpanel.getBoundingClientRect ? h.rpanel.getBoundingClientRect().right : 0; cls(h.rpanel, "resizing", true); if (e && e.preventDefault) e.preventDefault(); }
  function doResize(e) { if (!state.resizing) return; setVar(state.rightEdge - e.clientX); }                                          // le panneau grandit vers la gauche
  function endResize() { if (!state.resizing) return; state.resizing = false; cls(h.rpanel, "resizing", false); const w = root && root.documentElement && typeof getComputedStyle === "function" ? getComputedStyle(root.documentElement).getPropertyValue("--rpanel-w").trim() : ""; if (w) svc.saveWidth(parseInt(w, 10)); if (ctx.onResized) ctx.onResized(); }
  /** RM2579 : le démarrage suit les PRÉFÉRENCES (onglet par défaut, dépliée ou non), pas le dernier état ad hoc. */
  function restore() {
    state.right = rightPanelReduce({ tab: svc.defaultTab(), collapsed: !svc.startOpen() }, {});
    state.left = svc.leftCollapsed();
    if (h.startOpen) h.startOpen.checked = svc.startOpen();
    if (h.defTab) h.defTab.value = svc.defaultTab();
    const w = svc.width(); if (w) setVar(w);
    applyRight(); applyLeft();
  }
  const disposers = [];
  const listen = (el, type, fn) => { if (el && el.addEventListener) { el.addEventListener(type, fn); disposers.push(() => el.removeEventListener(type, fn)); } };
  listen(h.rnav, "click", (e) => { const b = e.target && e.target.closest ? e.target.closest("[data-rpanel]") : null; if (b) switchRight(b.dataset.rpanel); });
  listen(h.rtoggle, "click", () => toggleRight()); listen(h.ltoggle, "click", () => toggleLeft());
  listen(h.rhandle, "mousedown", startResize); listen(h.rhandle, "dblclick", () => resetWidth());
  listen(root, "mousemove", doResize); listen(root, "mouseup", endResize);
  listen(h.startOpen, "change", (e) => svc.setStartOpen(!!e.target.checked)); listen(h.defTab, "change", (e) => svc.setDefaultTab(e.target.value));
  return { dispatch, switchRight, showRight, toggleRight, collapseRight, rightVisible, toggleLeft, restore, setRightWidth, resetWidth, right: () => state.right, left: () => state.left, state,
    unmount() { disposers.forEach(d => d()); disposers.length = 0; } };
}
