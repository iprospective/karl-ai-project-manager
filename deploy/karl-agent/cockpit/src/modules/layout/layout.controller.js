// controllers/layout.controller — la disposition : colonne de droite à onglets (un seul actif, repli voulu respecté), colonne
// gauche repliable, largeur réglable à la poignée, préférences de démarrage. RM2889 (RM2466/2579/2599/2952).
//
// Hôtes : `main`, `rpanel` (l'aside), `rnav` (barre d'onglets), `rtoggle`, `ltoggle`, `rhandle` (poignée), `startOpen`, `defTab`
// (réglages), `lnav`/`lbody` (RM2283 : panneaux commutables de la colonne gauche — l'actif est persisté, les panneaux à contenu serveur
// chargent à la première activation par `ctx.panelLoaders`). Ce qu'un onglet visible déclenche (charger l'outline, le worklog, les fichiers, rendre l'encart…) est prêté par
// `onApply(state)` — le routeur de la disposition ne connaît pas les domaines qu'il expose.
import { rightPanelReduce, clampWidth, clampCenterH } from "./panels.js";
import { LayoutService } from "./layout.service.js";
import { detectLayout, forcedLayout, pageOf, navItems, keyboardOpen, fullItem, headerSplit, iconOf, sayLabel } from "./mobile.js";
import { MobileNav } from "./Layout.view.js";
import { paint } from "../../core/dom.js";

export function mountLayout(hosts = {}, ctx = {}) {
  const h = hosts, svc = ctx.service || new LayoutService({ storage: ctx.storage });
  const root = ctx.root || (typeof document !== "undefined" ? document : null);
  // RM3270 : `full` = plein écran sur le centre (clavier ouvert ou bascule manuelle) ; `auto` retient que
  // c'est le clavier qui l'a demandé, pour ressortir tout seul quand il redescend ; `say` = le bouton du
  // haut dont on vient d'afficher le nom (le second appui, lui, agit).
  const state = { right: { tab: "infos", collapsed: true, manual: false }, left: false, resizing: false, rightEdge: 0, panel: null, loaded: {}, shield: null, mobile: { layout: "desktop", page: "left", full: false, auto: false, say: null, more: false },
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
  // Les trois surfaces SŒURS de la zone centrale. RM3051 n'en gérait qu'une (`reviewpane`) : ouvrir une
  // vue ou un panneau passait par un `display` brut, la session restait affichée, et la page s'empilait
  // SOUS le terminal et sous le composer au lieu de le remplacer. Les trois passent maintenant par ici.
  const SURFACES = ["reviewpane", "viewpane", "panelpane"];
  const surfaceEl = (nom) => h[nom] || (root && root.getElementById ? root.getElementById(nom) : null);
  /** Vrai dès qu'une surface centrale est visible : c'est ce qui décide de masquer la session. */
  function surfaceVisible() {
    return SURFACES.some(n => { const el = surfaceEl(n); return el && el.style && el.style.display !== "none"; });
  }
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
  function showCenter(on, surface) {
    on = !!on;
    const el = surfaceEl(surface || "reviewpane");
    if (el && el.style) el.style.display = on ? "" : "none";
    // « on » ne suffit pas : fermer UNE surface ne doit rendre la session que si plus AUCUNE n'est
    // ouverte — sinon passer d'un onglet à l'autre ferait réapparaître le terminal une fraction de
    // seconde, ou pire, le laisserait revenir sous la vue suivante.
    on = surfaceVisible();
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
  /** Montre une vue ou un panneau du centre : même règle que pour un ticket — à la place de la
   *  session, ou sous elle si le split est activé. */
  const showSurface = (nom, on) => showCenter(on, nom);
  const setVarH = (px) => { if (root && root.documentElement) root.documentElement.style.setProperty("--reviewpane-h", clampCenterH(px) + "px"); };
  function startCenterResize(e) { if (!centerSplit() || !state.center.shown) return; state.center.resizing = true; bouclier(true); state.center.bottom = h.reviewpane && h.reviewpane.getBoundingClientRect ? h.reviewpane.getBoundingClientRect().bottom : 0; if (state.shield) state.shield.style.cursor = "row-resize"; if (e && e.preventDefault) e.preventDefault(); }
  function doCenterResize(e) { if (!state.center.resizing) return; setVarH(state.center.bottom - e.clientY); }   // le volet grandit vers le haut
  function endCenterResize() {
    if (!state.center.resizing) return;
    state.center.resizing = false;
    bouclier(false);
    const v = root && root.documentElement && typeof getComputedStyle === "function" ? getComputedStyle(root.documentElement).getPropertyValue("--reviewpane-h").trim() : "";
    if (v) svc.saveCenterH(parseInt(v, 10));
  }
  function resetCenterH() { svc.resetCenterH(); if (root && root.documentElement) root.documentElement.style.removeProperty("--reviewpane-h"); }
  // ── largeur (RM2599/2952) ──
  const setVar = (px) => { if (root && root.documentElement) root.documentElement.style.setProperty("--rpanel-w", clampWidth(px) + "px"); };
  function setRightWidth(px) { setVar(px); }
  function resetWidth() { if (root && root.documentElement) root.documentElement.style.removeProperty("--rpanel-w"); svc.resetWidth(); if (ctx.onResized) ctx.onResized(); }   // RM2952 : on RETIRE la variable, pas 330 en dur
  // RM3123 : le terminal est une IFRAME, et une iframe avale tous les événements de souris qui passent
  // au-dessus d'elle. Agrandir la colonne de droite veut dire tirer vers la GAUCHE, donc au-dessus du
  // terminal : le document ne recevait plus rien, la largeur cessait de suivre, et au retour elle ne
  // pouvait plus que rétrécir. Un bouclier plein écran posé le temps du glisser reçoit les événements
  // à la place de ce qu'il couvre.
  function bouclier(on) {
    if (!root || !root.body) return;
    if (on) {
      if (state.shield) return;
      const d = root.createElement ? root.createElement("div") : null;
      if (!d) return;
      d.className = "resize-shield";
      d.style.cursor = "col-resize";
      root.body.appendChild(d);
      state.shield = d;
    } else if (state.shield) {
      if (state.shield.remove) state.shield.remove();
      else if (state.shield.parentNode) state.shield.parentNode.removeChild(state.shield);
      state.shield = null;
    }
  }
  function startResize(e) { if (!h.rpanel || (h.rpanel.classList && h.rpanel.classList.contains("collapsed"))) return; state.resizing = true; state.rightEdge = h.rpanel.getBoundingClientRect ? h.rpanel.getBoundingClientRect().right : 0; cls(h.rpanel, "resizing", true); bouclier(true); if (e && e.preventDefault) e.preventDefault(); }
  function doResize(e) { if (!state.resizing) return; setVar(state.rightEdge - e.clientX); }                                          // le panneau grandit vers la gauche
  function endResize() { if (!state.resizing) return; state.resizing = false; bouclier(false); cls(h.rpanel, "resizing", false); const w = root && root.documentElement && typeof getComputedStyle === "function" ? getComputedStyle(root.documentElement).getPropertyValue("--rpanel-w").trim() : ""; if (w) svc.saveWidth(parseInt(w, 10)); if (ctx.onResized) ctx.onResized(); }
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
  const vp = ctx.viewport || null;                                   // visualViewport : le seul à voir monter le clavier (null sous node)
  const isMobile = () => state.mobile.layout === "mobile";
  function detectMobile() {
    const layout = detectLayout({ forced: ctx.forced === undefined ? forcedLayout(ctx.search, svc.layoutPref()) : ctx.forced, narrow: !!(media && media.matches) });
    const changed = layout !== state.mobile.layout; state.mobile.layout = layout;
    applyMobile(); if (changed && ctx.onLayout) ctx.onLayout(layout);
    return layout;
  }
  function applyMobile() {
    const m = state.mobile;
    if (!isMobile() && m.full) { m.full = false; m.auto = false; }      // le bureau n'a pas de plein écran : il a de la place
    if (root && root.documentElement && root.documentElement.dataset) {
      root.documentElement.dataset.layout = m.layout;
      root.documentElement.dataset.mfull = m.full ? "1" : "0";          // RM3270 : le CSS efface la barre du haut et les autres colonnes
    }
    if (h.main && h.main.dataset) h.main.dataset.mpage = m.full ? "center" : m.page;
    condenseHeader(isMobile());
    paintMobileNav();
  }
  function paintMobileNav() {
    if (!h.mnav) return;
    paint(h.mnav, isMobile() ? MobileNav(navItems(state.mobile.page, { attention: ctx.attention ? ctx.attention() : 0, attached: ctx.attached ? ctx.attached() : null }), fullItem(state.mobile.full)) : "");
  }
  /** RM3270 : le second formulaire (composer) sous le terminal — masqué en mobile sauf si on le demande.
   *  Le bureau n'est pas concerné : le CSS ne lit `data-mcomposer` que sous `data-layout="mobile"`. */
  function applyComposer(on) {
    if (root && root.documentElement && root.documentElement.dataset) root.documentElement.dataset.mcomposer = on ? "1" : "0";
    return !!on;
  }
  /** Plein écran : le centre seul. `auto` = demandé par le clavier, donc repartira tout seul. */
  function setFull(on, auto = false) {
    if (!isMobile()) return false;
    state.mobile.full = !!on; state.mobile.auto = !!on && !!auto;
    if (on) state.mobile.page = "center";
    applyMobile();
    return state.mobile.full;
  }
  const toggleFull = () => setFull(!state.mobile.full, false);
  /** Le clavier monte → plein écran ; il redescend → on ressort, mais seulement si c'est lui qui l'avait demandé. */
  function onViewport() {
    if (!isMobile() || !vp) return;
    const open = keyboardOpen({ viewportH: vp.height, windowH: ctx.windowH ? ctx.windowH() : (typeof window !== "undefined" ? window.innerHeight : 0) });
    if (open && !state.mobile.full) setFull(true, true);
    else if (!open && state.mobile.full && state.mobile.auto) setFull(false);
  }
  // ── barre du haut au doigt (RM3270) : icônes seules, les secondaires sous « … », le nom avant l'action ──
  const headerBtns = () => (h.header && h.header.querySelectorAll ? [...h.header.querySelectorAll("button[id]")] : []);
  /** En mobile, chaque bouton perd son libellé (l'icône suffit) et les non-prioritaires passent en « extra ». Réversible. */
  function condenseHeader(on) {
    const btns = headerBtns();
    if (!btns.length) return;
    const { primary } = headerSplit(btns.map(b => b.id));
    btns.forEach(b => {
      if (b.id === "hdrmore") return;                                   // le bouton « … » lui-même ne se condense pas
      if (on && b.dataset.full === undefined) b.dataset.full = b.textContent;   // le libellé d'origine, gardé pour le retour au bureau
      const label = b.dataset.full === undefined ? b.textContent : b.dataset.full;
      if (on) { if (b.textContent !== iconOf(label)) b.textContent = iconOf(label); }
      else if (b.dataset.full !== undefined) { b.textContent = b.dataset.full; delete b.dataset.full; }
      cls(b, "hdr-extra", on && !primary.includes(b.id));
    });
    cls(h.header, "hdr-more", on && state.mobile.more);
    if (!on) { state.mobile.say = null; state.mobile.more = false; }
  }
  /** Premier appui : le nom s'affiche et le geste est arrêté. Second appui sur le MÊME bouton : il passe. */
  function headerTap(ev) {
    if (!isMobile()) return;
    const b = ev.target && ev.target.closest ? ev.target.closest("button[id]") : null;
    if (!b || b.id === "hdrmore" || !h.header || !h.header.contains || !h.header.contains(b)) return;
    if (state.mobile.say === b.id) { state.mobile.say = null; condenseHeader(true); return; }   // 2e appui : on laisse faire
    state.mobile.say = b.id;
    b.textContent = sayLabel({ text: b.dataset.full, title: b.getAttribute ? b.getAttribute("title") : "" });   // le nom, le temps du choix
    if (ev.preventDefault) ev.preventDefault();
    if (ev.stopPropagation) ev.stopPropagation();
  }
  const toggleMore = () => { state.mobile.more = !state.mobile.more; cls(h.header, "hdr-more", isMobile() && state.mobile.more); return state.mobile.more; };
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
  listen(h.mnav, "click", (e) => {
    const n = e.target && e.target.closest ? e.target.closest("[data-mpage],[data-mfull]") : null;
    if (!n) return;
    if (n.dataset.mfull) toggleFull(); else mobileGo(n.dataset.mpage);   // RM3270 : la bascule plein écran partage la barre
  });
  if (media && media.addEventListener) listen(media, "change", () => detectMobile());
  // RM3270 : le nom d'abord, l'action ensuite — en CAPTURE, pour passer avant le dispatcher `data-cmd` de la page
  if (h.header && h.header.addEventListener) {
    h.header.addEventListener("click", headerTap, true);
    disposers.push(() => h.header.removeEventListener("click", headerTap, true));
  }
  listen(h.hdrmore, "click", () => toggleMore());
  if (vp && vp.addEventListener) listen(vp, "resize", onViewport);      // le clavier logiciel ne change QUE le viewport visible
  return { dispatch, switchRight, showRight, toggleRight, collapseRight, rightVisible, toggleLeft, restore, setRightWidth, resetWidth, switchPanel, restorePanel, panel: () => state.panel, right: () => state.right, left: () => state.left, state,
    showCenter, showSurface, centerSplit, setCenterSplit, resetCenterH, applyCenter,
    // RM3123 : exposés pour le test — le bouclier du glisser ne se voit qu'en les appelant
    startResize, doResize, endResize, startCenterResize, endCenterResize,
    mobile: () => Object.assign({}, state.mobile), isMobile, mobileGo, centerShown, refreshMobileNav, detectMobile,
    // RM3270 : plein écran (clavier ou bascule), barre du haut condensée, débordement « … »
    setFull, toggleFull, onViewport, condenseHeader, headerTap, toggleMore, applyComposer,
    unmount() { disposers.forEach(d => d()); disposers.length = 0; } };
}
