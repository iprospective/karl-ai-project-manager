// controllers/attach.controller — l'ATTACHE : la session affichée au centre. Attacher ferme les autres vues (RM2759/2816/2353/2672), monte
// le terminal, déplie la colonne (RM2466), aligne l'encart (RM2173), l'outline (RM2330), le worklog (RM2466), git (RM2602), les fichiers
// (RM2673), les chips (RM1893), bascule sur « en cours » (RM2283) et note l'onglet (RM2672) ; détacher défait tout et rend le tableau de bord
// (RM2697). Porte aussi les raccourcis clavier de la conversation (RM2330 Alt+↑/↓/Fin, RM2527 Alt+C → composer). RM2889.
export function mountAttach({ placeholder, tabactions, reviewpane, chipsrow, composer, root } = {}, ctx = {}) {
  let attached = null;
  const show = (el, on, mode) => { if (el) el.style.display = on ? (mode || "") : "none"; };
  const vis = (tab) => !!(ctx.layout && ctx.layout.rightVisible(tab));
  const call = (obj, fn, ...a) => (obj && typeof obj[fn] === "function" ? obj[fn](...a) : undefined);
  function attach(rmId) {
    attached = String(rmId);
    call(ctx.center, "closeView"); call(ctx.center, "closePanel");                    // RM2759/RM2816 : la vue et le panneau central cèdent la place
    call(ctx.review, "yieldTo"); call(ctx.project, "close"); call(ctx.newticket, "close");   // revue, fiche projet (RM2353), création (RM2672)
    show(placeholder, false);
    call(ctx.terminal, "mountTerm", rmId);
    show(tabactions, true);
    call(ctx.layout, "showRight");                                                    // RM2466 : déplie, sans changer d'onglet actif
    call(ctx.meta, "onAttach", rmId);                                                 // RM2173 : le ticket affiché = l'ancrage de la session
    call(ctx.outline, "reset"); if (vis("outline")) call(ctx.outline, "load");       // RM2330
    if (vis("state")) call(ctx.worklog, "load");                                      // RM2466
    call(ctx.git, "reset"); if (vis("git")) call(ctx.git, "refresh");                 // RM2602
    if (vis("files")) call(ctx.files, "ensure");                                      // RM2673
    call(ctx.actions, "renderChips");                                                 // RM1893 §2
    call(ctx.layout, "switchPanel", "running");                                       // RM2283
    call(ctx.center, "title");
    call(ctx.center, "note", "session", attached, (/^\d+$/.test(attached) ? "RM" : "") + attached);   // RM2672 : un onglet, non épinglé
    call(ctx.refresh, "refreshSessions");                                             // re-rend la liste pour marquer l'actif
  }
  function reattach() { if (attached) attach(attached); }
  function detach() {
    attached = null;
    call(ctx.meta, "setTicket", null);
    show(reviewpane, false);
    call(ctx.terminal, "unmountTerm");
    show(placeholder, true, "flex");
    call(ctx.dashboard, "refresh");                                                   // RM2697 : le centre redevient le tableau de bord
    show(tabactions, false);
    call(ctx.layout, "collapseRight");                                                // RM2466 : plus de session → la colonne se replie
    call(ctx.meta, "render");                                                         // RM2579 : vide infos + tickets
    call(ctx.outline, "reset");
    call(ctx.files, "reset"); if (vis("files")) call(ctx.files, "ensure");            // RM2586/RM2673 : repli sur le projet courant
    show(chipsrow, false);
    call(ctx.center, "title");
  }
  const disposers = [];
  const listen = (node, type, fn) => { if (node && node.addEventListener) { node.addEventListener(type, fn); disposers.push(() => node.removeEventListener(type, fn)); } };
  // RM2330 : navigation clavier dans la conversation — seulement quand le focus est sur la page (l'iframe ttyd est cross-origin)
  listen(root, "keydown", (e) => {
    if (!attached || !e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === "ArrowUp") { e.preventDefault(); call(ctx.outline, "jumpUser", -1); }
    else if (e.key === "ArrowDown") { e.preventDefault(); call(ctx.outline, "jumpUser", 1); }
    else if (e.key === "End") { e.preventDefault(); call(ctx.outline, "scrollLive"); }
    else if (e.key === "c" || e.key === "C") { if (composer && composer.offsetParent) { e.preventDefault(); composer.focus(); } }   // RM2527 : sortir du terminal
  });
  return { attach, detach, reattach, current: () => attached, unmount() { disposers.forEach(d => d()); disposers.length = 0; } };
}
