// controllers/sessions.controller — la liste « en cours » (RM2283 compteurs, RM2346 bandeau + gel, RM2427 tuiles grises, RM2445/2537 hors
// jeu, RM2448 pli + sélection, RM2515 disposition, RM2598 questions sans réponse, RM2639 contexte client, RM2787/2793 silence, RM2210 revues),
// les raccourcis « ✔ Oui » / « ✔ tout » / auto-oui (RM2302/2327/2332), le titre de la session attachée (RM2283) et l'en-tête droit (RM2894). RM2889.
//
// Hôtes : `list` (#runlist), `counters` (#hcnt), `navCount`/`navAtt` (badges de l'onglet), `yesAll`/`yesAtt` (header), `yesBtn`/`autoYes`
// (barre du terminal), `title` (#curtitle : le bouton « ✔ Oui » du titre), `rtitle` (#rtitle), `dynsort` (réglages). Le monolithe prête le
// registre live (store `session.registry`, RM3005), les résolutions, la session attachée, les questions sans réponse, la sélection et
// les jeux (état + `setWritable`/`setLabel` + gestes ⊖ ⟳ relance), l'attache/le détachement, `titleLink` et les rafraîchissements.
import { SessionsService } from "./sessions.service.js";
import { SessionTileViewModel, GhostTileViewModel, GroupViewModel, AttnChipViewModel, CountersViewModel, ReviewTileViewModel, SessionTitleViewModel } from "./SessionsViewModel.js";
import { Tile, Ghost, Group, AttnBand, CtxBanner, ReviewGroup, Empty, Counters, SessionTitle, RTitle } from "./Sessions.view.js";
import { contextGauge, contextCrossed } from "./sessions.js";                      // RM3082
import { ctxPct, modelWindow, fmtWin } from "../ticket/ticketFormat.js";           // RM3082
import { effDisposition, restartTip, approveShortcutVisible, tmuxName, toggleDisposition } from "./sessions.js";
import { mount, paint } from "../../core/dom.js";
import { raw } from "../../core/html.js";

export function mountSessions(hosts = {}, ctx = {}) {
  const svc = ctx.service || new SessionsService({ storage: ctx.storage });
  const notify = ctx.notify || (() => {});
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const sess = ctx.sess();                                               // store session.registry : rm_id → entrée /sessions (RM2166 ; RM3005)
  const resolve = () => ctx.resolve();                                   // store ticket.resolve
  const attached = () => (ctx.attached ? ctx.attached() : null);
  const selection = () => (ctx.selection ? ctx.selection() : { on: false, set: new Set() });
  const sets = () => (ctx.sets ? ctx.sets() : { sets: [], current: "default", view: "set" });
  const lend = { pin: (k, key) => (ctx.pin ? ctx.pin(k, key) : "") || "", titleLink: (rm, t) => (ctx.titleLink ? ctx.titleLink(rm, t) : "") || "" };
  const state = { ordered: [], groups: {}, byKey: {} };
  const h = hosts.list ? mount(hosts.list, raw(hosts.list.innerHTML || ""), { events: [
    ["click", "[data-action]", (ev, el) => onAction(ev, el)],
    // RM2792 : le menu complet au clic droit — le navigateur, lui, n'a rien d'utile à proposer ici.
    ["contextmenu", "[data-action=\"disp\"]", (ev, el) => {
      const s = el.dataset.k ? state.byKey[el.dataset.k] : null;
      if (!s) return;
      if (ev.preventDefault) ev.preventDefault();
      if (ctx.openDispositionMenu) ctx.openDispositionMenu(s, el);
    }]] }) : null;
  const disposers = [];
  const listen = (node, type, fn) => { if (node && node.addEventListener) { node.addEventListener(type, fn); disposers.push(() => node.removeEventListener(type, fn)); } };
  // RM2346 : suit l'interaction sur la liste pour geler le tri dynamique le temps de cliquer
  listen(hosts.list, "mouseenter", () => svc.enter()); listen(hosts.list, "mouseleave", () => svc.leave()); listen(hosts.list, "mousemove", () => svc.moved());

  // RM3082 : la jauge de contexte. `ctxSeen` retient le palier atteint par session pour n'animer
  // que le FRANCHISSEMENT ; `ctxPulsing` porte les tuiles qui bougent, vidées après l'animation.
  const ctxSeen = new Map(), ctxPulsing = new Set();
  const ctxTh = () => ((ctx.cfg ? ctx.cfg() : {}) || {}).context_thresholds || { warn: 50, high: 75, crit: 90 };
  const gaugeOf = (s) => contextGauge(s, ctxTh(), ctxPct, modelWindow, fmtWin);
  const tileCtx = (s) => { const sel = selection(); return { resolved: resolve().get(s.rm_id), attached: attached(), stale: ctx.stale ? ctx.stale() : null, selMode: sel.on, selected: sel.set, set: sets(), writable: ctx.writable, setLabel: ctx.setLabel, ctxThresholds: ctxTh(), ctxPulsing }; };
  const toggleSel = (s) => { const set = selection().set; set.has(s.rm_id) ? set.delete(s.rm_id) : set.add(s.rm_id); if (ctx.refresh) ctx.refresh(); };

  /** Peint la liste depuis le bloc /sessions ; rend les compteurs (la pile /refresh y lit sa cadence — RM2613). */
  function render(sessions) {
    if (!h) return null;
    try {
      const rcache = resolve().view;   // lecture indexée pour les fonctions pures (computeGroups, sessionInClient)
      const d = svc.compute(sessions, rcache, ctx.clientContext ? ctx.clientContext() : "");   // RM2515 ordre, groupes, RM2639 visibilité
      sessions.forEach(s => sess.set(s.rm_id, s));                                         // RM2166 : registre pour l'encart
      if (ctx.composerRefresh) ctx.composerRefresh();                                          // RM2527 : la garde suit l'état live
      const att = attached();
      if (att && !sessions.some(s => s.rm_id === att && !s.ghost) && ctx.detach) ctx.detach();   // kill externe (RM2427 : un fantôme ne compte pas)
      for (const s of sessions) if (s.is_ticket !== false && rcache[s.rm_id] === undefined && ctx.ticket) ctx.ticket.ensureResolved(s.rm_id);   // RM2144
      if (ctx.projectsVisible && ctx.projectsVisible() && ctx.renderProjects) ctx.renderProjects();   // RM2760 : compteurs ▶ du panneau projets
      state.ordered = d.ordered; state.groups = {}; state.byKey = {};
      const reviews = (ctx.review && ctx.review.tabs ? ctx.review.tabs() : []) || [];
      const parts = [];
      if (!sessions.length && !reviews.length) parts.push(Empty());
      // RM3082 : le palier atteint est relevé AVANT le rendu — la tuile qui vient de franchir un
      // seuil pulse une fois, puis `later` la rend muette. Une session éteinte oublie son palier.
      const alive = new Set(sessions.filter(s => !s.ghost).map(s => String(s.rm_id)));
      for (const k of [...ctxSeen.keys()]) if (!alive.has(k)) ctxSeen.delete(k);
      for (const s of sessions) {
        if (s.ghost) continue;
        const g = gaugeOf(s);
        if (contextCrossed(s.rm_id, g ? g.level : "", ctxSeen)) {
          ctxPulsing.add(String(s.rm_id));
          const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
          later(() => { ctxPulsing.delete(String(s.rm_id)); }, 2200);
        }
      }
      // RM2346 — et RM3082 : une session au palier critique appelle un geste (consigner, repartir), donc elle est « à traiter ».
      parts.push(AttnBand(sessions.filter(s => !s.ghost && (s.state === "attention" || s.state === "choice" || (gaugeOf(s) || {}).level === "crit")).map(s => new AttnChipViewModel(s, rcache[s.rm_id], gaugeOf(s))), lend));
      const cc = ctx.clientContext ? ctx.clientContext() : "";
      if (cc) parts.push(CtxBanner(cc, d.hidden));
      for (const key of d.visKeys) {
        const group = d.groups.get(key); state.groups[key] = group;
        const gvm = new GroupViewModel({ key, sessions: group, folded: svc.isCollapsed(key) });
        parts.push(Group(gvm, gvm.folded ? [] : group.map(s => { const vm = s.ghost ? new GhostTileViewModel(s, tileCtx(s)) : new SessionTileViewModel(s, tileCtx(s)); state.byKey[vm.key] = s; return s.ghost ? Ghost(vm) : Tile(vm, lend); })));
      }
      const revCur = ctx.review && ctx.review.current ? ctx.review.current() : null;
      parts.push(ReviewGroup(reviews.map(rm => new ReviewTileViewModel(rm, rcache[rm], revCur === rm && !att)), lend));   // RM2210
      h.update(raw(parts.map(String).join("")));
      if (ctx.announce) ctx.announce(sessions);                                                // RM2329 : mode voix
      paintCounters(new CountersViewModel(d.counts));
      if (ctx.renderTitle) ctx.renderTitle();
      return d.counts;
    } catch (e) { console.error("sessions : rendu en erreur", e); return null; }
  }
  const show = (el, on) => { if (el) el.style.display = on ? "" : "none"; };
  function paintCounters(cvm) {
    if (hosts.counters) paint(hosts.counters, Counters(cvm));
    if (hosts.navCount) { hosts.navCount.textContent = String(cvm.c.total); show(hosts.navCount, cvm.c.total); }
    if (hosts.navAtt) { hosts.navAtt.textContent = "⚠" + cvm.waiting; show(hosts.navAtt, cvm.waiting); }
    show(hosts.yesAll, cvm.showYesAll);                                                        // RM2327
    if (ctx.docTitle) ctx.docTitle(cvm.docTitle);                                              // titre du navigateur
  }
  function onAction(ev, el) {
    const a = el.dataset.action, s = el.dataset.k ? state.byKey[el.dataset.k] : null;
    if (a === "attach") { if (!s) return; selection().on ? toggleSel(s) : (ctx.attach && ctx.attach(s.rm_id)); }
    else if (a === "relaunch") { if (!s) return; selection().on ? toggleSel(s) : (ctx.relaunch && ctx.relaunch(s)); }   // RM2427/RM2448
    else if (a === "approve") approve(s ? s.rm_id : attached());                              // RM2302 : « Oui » direct depuis la liste
    else if (a === "kill") { if (s && ctx.kill) ctx.kill(s.rm_id); }
    else if (a === "drop") { if (s && ctx.drop) ctx.drop(s); }                                  // RM2446 : ⊖ sort du jeu sans fermer
    // RM2792 : un clic BASCULE (« à traiter » ⇄ « en pause ») — c'est le geste de tous les jours.
    // Le menu complet reste à un clic droit (ou alt/maj-clic), pour « terminé » et la fermeture.
    else if (a === "disp") {
      if (!s) return;
      if (ev && (ev.altKey || ev.shiftKey)) { if (ctx.openDispositionMenu) ctx.openDispositionMenu(s, el); return; }
      if (ctx.setDisposition) ctx.setDisposition(s.rm_id, toggleDisposition(effDisposition(s.state, s.disposition)));
    }
    else if (a === "restart") { if (s && ctx.toggleRestart) ctx.toggleRestart(s); }
    else if (a === "forget") { if (s && ctx.forget) ctx.forget(s); }
    else if (a === "group") { if (ctx.openProject) ctx.openProject(el.dataset.key); }           // RM2353
    else if (a === "fold") toggleGroup(el.dataset.key);                                         // RM2448
    else if (a === "ctx-clear") { if (ctx.setClientContext) ctx.setClientContext(""); }          // RM2639
    else if (a === "review") { if (ctx.review) ctx.review.open(el.dataset.rm); }
    else if (a === "review-close") { if (ctx.review) ctx.review.close(el.dataset.rm); }
  }
  // ── raccourcis Oui / auto-oui ──
  async function approve(rm) {
    if (!rm) return;
    try { notify(await svc.approve(rm)); later(() => ctx.refresh && ctx.refresh(), 900); }     // laisse le TUI avancer avant de re-peindre
    catch (e) { notify(e.message, true); }
  }
  async function approveAll(btn) {
    if (btn) btn.disabled = true;
    try { notify((await svc.approveAll()).msg); later(() => ctx.refresh && ctx.refresh(), 900); }
    catch (e) { notify(e.message, true); }
    finally { if (btn) btn.disabled = false; }
  }
  async function setAutoYes(minutes) {
    const att = attached(); if (!att || minutes === "" || minutes == null) return;
    try { notify(await svc.autoYes(att, minutes)); if (ctx.refresh) ctx.refresh(); }
    catch (e) { notify(e.message, true); }
  }
  function toggleDynSort(on) { notify(svc.setDynSort(on)); if (ctx.refresh) ctx.refresh(); }    // RM2344
  function toggleGroup(key) { svc.toggleGroup(key); if (ctx.refresh) ctx.refresh(); }
  // ── titre de la vue courante (prêté au routeur du centre) et en-tête du panneau droit ──
  const titleVm = () => { const att = attached(); return new SessionTitleViewModel({ attached: att, sess: att ? sess.get(att) : null, resolved: att ? resolve().get(att) : null }); };
  function titleHtml() { return String(SessionTitle(titleVm(), lend)); }
  function renderRTitle() {
    const el = hosts.rtitle; if (!el) return;
    const vm = titleVm();
    if (!vm.shown) { el.style.display = "none"; paint(el, ""); return; }
    el.style.display = ""; paint(el, RTitle(vm)); el.title = "Session attachée — " + tmuxName(vm.attached);
  }
  /** Effets de bord d'un changement de vue : en-tête droit (RM2894), « ✔ Oui » aux deux emplacements (RM2302/2332), état de l'auto-oui (RM2327). */
  function afterTitle() {
    renderRTitle();
    const att = attached(), on = approveShortcutVisible(att, sess.view);
    show(hosts.yesBtn, on); show(hosts.yesAtt, on);
    const ay = hosts.autoYes;
    if (ay) { const vm = titleVm(); if (ay.options && ay.options[0]) ay.options[0].textContent = vm.autoYesLabel; ay.style.color = vm.autoYesArmed ? "var(--ok)" : ""; ay.value = ""; }
  }
  listen(hosts.title, "click", (e) => { const n = e.target && e.target.closest ? e.target.closest('[data-action="approve"]') : null; if (n) { e.preventDefault(); approve(attached()); } });
  listen(hosts.yesBtn, "click", () => approve(attached())); listen(hosts.yesAtt, "click", () => approve(attached()));
  listen(hosts.yesAll, "click", (e) => approveAll(e.currentTarget || hosts.yesAll));
  listen(hosts.autoYes, "change", (e) => setAutoYes(e.target.value));
  if (hosts.dynsort) { hosts.dynsort.checked = svc.dynSort; listen(hosts.dynsort, "change", (e) => toggleDynSort(e.target.checked)); }
  return { render, approve, approveAll, setAutoYes, toggleDynSort, toggleGroup, titleHtml, afterTitle, renderRTitle,
    ordered: () => state.ordered, groups: () => state.groups, isCollapsed: (k) => svc.isCollapsed(k), restartTip, effDisposition, svc,
    unmount() { disposers.forEach(d => d()); disposers.length = 0; if (h) h.unmount(); } };
}
