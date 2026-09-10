// controllers/layout.controller — la disposition : colonne de droite à onglets (un seul actif, repli voulu respecté), colonne
// gauche repliable, largeur réglable à la poignée, préférences de démarrage. RM2889 (RM2466/2579/2599/2952).
//
// Hôtes : `main`, `rpanel` (l'aside), `rnav` (barre d'onglets), `rtoggle`, `ltoggle`, `rhandle` (poignée), `startOpen`, `defTab`
// (réglages), `lnav`/`lbody` (RM2283 : panneaux commutables de la colonne gauche — l'actif est persisté, les panneaux à contenu serveur
// chargent à la première activation par `ctx.panelLoaders`). Ce qu'un onglet visible déclenche (charger l'outline, le worklog, les fichiers, rendre l'encart…) est prêté par
// `onApply(state)` — le routeur de la disposition ne connaît pas les domaines qu'il expose.
import { rightPanelReduce, clampWidth, clampCenterH } from "./panels.js";
import { LayoutService } from "./layout.service.js";
import { detectLayout, forcedLayout, pageOf, navItems } from "./mobile.js";
import { MobileNav } from "./Layout.view.js";
import { paint } from "../../core/dom.js";

export function mountLayout(hosts = {}, ctx = {}) {
  const h = hosts, svc = ctx.service || new LayoutService({ storage: ctx.storage });
  const root = ctx.root || (typeof document !== "undefined" ? document : null);
  const state = { right: { tab: "infos", collapsed: true, manual: false }, left: false, resizing: false, rightEdge: 0, panel: null, loaded: {}, mobile: { layout: "desktop", page: "left" },
    center: { shown: false, hidden: null, resizing: false, bottom: 0 } };   // RM3051 : split de la zone centrale
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
  const switchRight = (tab) => dispatch({ type: "select", tab }), showRight = (tab) => { const r = dispatch({ type: "show", tab }); mobileGo("right"); return r; }, toggleRight = () => dispatch({ type: "toggle" }), collapseRight = () => dispatch({ type: "collapse" });
  const rightVisible = (tab) => !state.right.collapsed && state.right.tab === tab;
  function toggleLeft() { state.left = !state.left; applyLeft(); }

  // ── RM3051 : la zone centrale — un ticket/doc À LA PLACE de la session, ou SOUS elle ──
  //
  // Historiquement, ouvrir un ticket affichait `#reviewpane` SANS masquer le terminal : la
  // zone se coupait en deux, sans que personne ne l'ait demandé. Le split devient une option
  // (défaut : OFF), et quand il est actif, la séparation se règle à la poignée.
  const centerEls = () => [h.termhost, h.term, h.composer].filter(Boolean);
  function centerSplit() { return svc.centerSplit(); }
  function setCenterSplit(on) {
    svc.setCenterSplit(!!on);
    if (state.center.shown) showCenter(true);   // bascule à chaud, sans refermer le ticket
    else applyCenter();
    return svc.centerSplit();
  }
  /** Applique la hauteur mémorisée au volet bas, et n'expose la poignée que dans le split. */
  function applyCenter() {
    const split = centerSplit(), on = state.center.shown;
    cls(h.reviewpane, "split", split && on);
    if (h.centerhandle && h.centerhandle.style) h.centerhandle.style.display = (split && on) ? "" : "none";
    const px = svc.centerH();
    if (root && root.documentElement) {
      if (px) root.documentElement.style.setProperty("--reviewpane-h", px + "px");
      else root.documentElement.style.removeProperty("--reviewpane-h");
    }
  }
  /**
   * Montre (ou cache) le volet central bas — la surface des tickets et documents.
   * Sans split, la session est MASQUÉE le temps de la consultation, puis rendue telle
   * qu'elle était : ce qui était caché reste caché (un terminal non attaché, par exemple).
   */
  function showCenter(on) {
    on = !!on;
    if (h.reviewpane && h.reviewpane.style) h.reviewpane.style.display = on ? "" : "none";
    if (on) {
      if (!centerSplit()) {
        if (!state.center.hidden) state.center.hidden = centerEls().filter(el => el.style && el.style.display !== "none");
        state.center.hidden.forEach(el => { el.style.display = "none"; });
      } else if (state.center.hidden) {          // le split vient d'être activé : on rend la session
        state.center.hidden.forEach(el => { el.style.display = ""; });
        state.center.hidden = null;
      }
    } else if (state.center.hidden) {
      state.center.hidden.forEach(el => { el.style.display = ""; });
      state.center.hidden = null;
    }
    state.center.shown = on;
    applyCenter();
    return on;
  }
  const setVarH = (px) => { if (root && root.documentElement) root.documentElement.style.setProperty("--reviewpane-h", clampCenterH(px) + "px"); };
  function startCenterResize(e) { if (!centerSplit() || !state.center.shown) return; state.center.resizing = true; state.center.bottom = h.reviewpane && h.reviewpane.getBoundingClientRect ? h.reviewpane.getBoundingClientRect().bottom : 0; if (e && e.preventDefault) e.preventDefault(); }
  function doCenterResize(e) { if (!state.center.resizing) return; setVarH(state.center.bottom - e.clientY); }   // le volet grandit vers le haut
  function endCenterResize() {
    if (!state.center.resizing) return;
    state.center.resizing = false;
    const v = root && root.documentElement && typeof getComputedStyle === "function" ? getComputedStyle(root.documentElement).getPropertyValue("--reviewpane-h").trim() : "";
    if (v) svc.saveCenterH(parseInt(v, 10));
  }
  function resetCenterH() { svc.resetCenterH(); if (root && root.documentElement) root.documentElement.style.removeProperty("--reviewpane-h"); }
  // ── largeur (RM2599/2952) ──
  const setVar = (px) => { if (root && root.documentElement) root.documentElement.style.setProperty("--rpanel-w", clampWidth(px) + "px"); };
  function setRightWidth(px) { setVar(px); }
  function resetWidth() { if (root && root.documentElement) root.documentElement.style.removeProperty("--rpanel-w"); svc.resetWidth(); if (ctx.onResized) ctx.onResized(); }   // RM2952 : on RETIRE la variable, pas 330 en dur
  function startResize(e) { if (!h.rpanel || (h.rpanel.classList && h.rpanel.classList.contains("collapsed"))) return; state.resizing = true; state.rightEdge = h.rpanel.getBoundingClientRect ? h.rpanel.getBoundingClientRect().right : 0; cls(h.rpanel, "resizing", true); if (e && e.preventDefault) e.preventDefault(); }
  function doResize(e) { if (!state.resizing) return; setVar(state.rightEdge - e.clientX); }                                          // le panneau grandit vers la gauche
  function endResize() { if (!state.resizing) return; state.resizing = false; cls(h.rpanel, "resizing", false); const w = root && root.documentElement && typeof getComputedStyle === "function" ? getComputedStyle(root.documentElement).getPropertyValue("--rpanel-w").trim() : ""; if (w) svc.saveWidth(parseInt(w, 10)); if (ctx.onResized) ctx.onResized(); }
  // ── colonne gauche : panneaux commutables (RM2283 ; RM2816 : pm/réglages n'y sont plus) ──
  const qa = (el, sel) => (el && el.querySelectorAll ? [...el.querySelectorAll(sel)] : []);
  function switchPanel(name) {
    if (!(h.lbody && h.lbody.querySelector && h.lbody.querySelector("#lp-" + name))) name = "running";
    qa(h.lnav, "button").forEach(b => cls(b, "active", !!b.dataset && b.dataset.panel === name));
    qa(h.lbody, ".lpanel").forEach(p => cls(p, "active", p.id === "lp-" + name));
    svc.savePanel(name); state.panel = name; mobileGo("left");
    const loaders = ctx.panelLoaders || {};
    if (loaders[name] && !state.loaded[name]) { state.loaded[name] = 1; loaders[name](); }   // contenu serveur : à la première activation
    return name;
  }
  function restorePanel() { return switchPanel(svc.panel() || "running"); }
  /** RM2579 : le démarrage suit les PRÉFÉRENCES (onglet par défaut, dépliée ou non), pas le dernier état ad hoc. */
  function restore() {
    state.right = rightPanelReduce({ tab: svc.defaultTab(), collapsed: !svc.startOpen() }, {});
    state.left = svc.leftCollapsed();
    if (h.startOpen) h.startOpen.checked = svc.startOpen();
    if (h.defTab) h.defTab.value = svc.defaultTab();
    const w = svc.width(); if (w) setVar(w);
    applyRight(); applyLeft(); applyCenter(); detectMobile();   // RM3051 : hauteur du volet central mémorisée
  }
  // ── gabarit mobile (RM3003) : une colonne à la fois, barre du bas ; mêmes contrôleurs, mêmes vues ──
  const media = ctx.media || null;                                   // MediaQueryList « écran étroit » prêtée par boot (null sous node)
  const isMobile = () => state.mobile.layout === "mobile";
  function detectMobile() {
    const layout = detectLayout({ forced: ctx.forced === undefined ? forcedLayout(ctx.search, svc.layoutPref()) : ctx.forced, narrow: !!(media && media.matches) });
    const changed = layout !== state.mobile.layout; state.mobile.layout = layout;
    applyMobile(); if (changed && ctx.onLayout) ctx.onLayout(layout);
    return layout;
  }
  function applyMobile() {
    if (root && root.documentElement && root.documentElement.dataset) root.documentElement.dataset.layout = state.mobile.layout;
    if (h.main && h.main.dataset) h.main.dataset.mpage = state.mobile.page;
    paintMobileNav();
  }
  function paintMobileNav() {
    if (!h.mnav) return;
    paint(h.mnav, isMobile() ? MobileNav(navItems(state.mobile.page, { attention: ctx.attention ? ctx.attention() : 0, attached: ctx.attached ? ctx.attached() : null })) : "");
  }
  /** Va sur une page du gabarit mobile — sans effet au bureau. Le centre l'appelle quand une vue s'ouvre, la droite quand un onglet se montre. */
  function mobileGo(page) { if (!isMobile()) return null; state.mobile.page = pageOf(page); applyMobile(); return state.mobile.page; }
  const centerShown = () => mobileGo("center");
  const refreshMobileNav = () => paintMobileNav();
  const disposers = [];
  const listen = (el, type, fn) => { if (el && el.addEventListener) { el.addEventListener(type, fn); disposers.push(() => el.removeEventListener(type, fn)); } };
  listen(h.rnav, "click", (e) => { const b = e.target && e.target.closest ? e.target.closest("[data-rpanel]") : null; if (b) switchRight(b.dataset.rpanel); });
  listen(h.rtoggle, "click", () => toggleRight()); listen(h.ltoggle, "click", () => toggleLeft());
  listen(h.lnav, "click", (e) => { const b = e.target && e.target.closest ? e.target.closest("[data-panel]") : null; if (b) switchPanel(b.dataset.panel); });
  listen(h.rhandle, "mousedown", startResize); listen(h.rhandle, "dblclick", () => resetWidth());
  listen(root, "mousemove", doResize); listen(root, "mouseup", endResize);
  // RM3051 : la poignée horizontale du centre (visible seulement quand le split est actif)
  listen(h.centerhandle, "mousedown", startCenterResize); listen(h.centerhandle, "dblclick", () => resetCenterH());
  listen(root, "mousemove", doCenterResize); listen(root, "mouseup", endCenterResize);
  listen(h.startOpen, "change", (e) => svc.setStartOpen(!!e.target.checked)); listen(h.defTab, "change", (e) => svc.setDefaultTab(e.target.value));
  listen(h.mnav, "click", (e) => { const b = e.target && e.target.closest ? e.target.closest("[data-mpage]") : null; if (b) mobileGo(b.dataset.mpage); });
  if (media && media.addEventListener) listen(media, "change", () => detectMobile());
  return { dispatch, switchRight, showRight, toggleRight, collapseRight, rightVisible, toggleLeft, restore, setRightWidth, resetWidth, switchPanel, restorePanel, panel: () => state.panel, right: () => state.right, left: () => state.left, state,
    showCenter, centerSplit, setCenterSplit, resetCenterH, applyCenter,
    mobile: () => Object.assign({}, state.mobile), isMobile, mobileGo, centerShown, refreshMobileNav, detectMobile,
    unmount() { disposers.forEach(d => d()); disposers.length = 0; } };
}
