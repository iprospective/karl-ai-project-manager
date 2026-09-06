// controllers/center.controller — le ROUTEUR du centre. RM2889, cluster centre.
//
// Il possède : les onglets (RM2672/2744/2775/2795/2819), l'historique de
// navigation (RM2776), le titre du centre, les vues génériques (fichier, dossier,
// commit, email, fiche client, conf — RM2759/2761/2768) et les panneaux centraux
// (commandes PM, réglages — RM2816).
//
// Il ne possède PAS (encore) : la session attachée, la revue, la fiche projet, le
// nouveau ticket. Ce sont des SURFACES enregistrées par boot.js — aujourd'hui des
// ponts vers le monolithe, demain des contrôleurs migrés. Migrer une surface
// remplace son enregistrement, rien d'autre : c'est ce qui rend le cluster
// migrable en plusieurs MR.
//
// Règle unique du centre : une seule vue à la fois. `yieldTo(kind)` demande à
// toutes les autres surfaces de céder la place ; les ouvreurs historiques font
// encore leur propre ménage — le routeur tolère les deux, tant que dure la
// cohabitation.
import { mount } from "../../core/dom.js";
import { html, raw } from "../../core/html.js";
import { tabId, upsertTab, closeTabAt, ensureDashTab, pinMark, sessionTabAction } from "./tabs.js";
import { NAV_MAX, histVisit, histStep, histCloseTarget } from "./history.js";
import { viewKey, parseViewKey, viewTabLabel } from "./viewKey.js";
import { fsScope, scopeTag } from "../files/scope.js";
import { CenterRepository } from "./CenterRepository.js";
import { TabsViewModel, HistoryViewModel, CenterTitleViewModel, FileViewModel, DirViewModel, EmailViewModel, ClientViewModel } from "./CenterViewModels.js";
import { Tabs, History, CenterTitle, FileView, DirView, MailView, CommitView, ClientView, ConfView, ViewError } from "./Center.view.js";
import { GitPatchViewModel } from "../git/GitPatchViewModel.js";
import { GitPatch } from "../git/GitPanel.view.js";

export function mountCenter(hosts, ctx = {}) {
  const repo = ctx.repo || new CenterRepository();
  const store = ctx.storage || { getItem() { return null; }, setItem() {}, removeItem() {} };
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const surfaces = Object.assign({}, ctx.surfaces || {});      // kind → { open(key, tab), close(), current() }
  const panels = Object.assign({}, ctx.panels || {});          // name → { label, load(), show(on) }
  const state = { tabs: [], active: null, hist: { items: [], idx: -1 }, suspend: false, view: null, panel: null, loaded: {} };

  // ── persistance des onglets ÉPINGLÉS (RM2672) ─────────────────────────────
  try { state.tabs = JSON.parse(store.getItem("karlTabs") || "[]").filter(t => t && t.kind); } catch (e) { state.tabs = []; }
  state.tabs = ensureDashTab(state.tabs);
  const save = () => { try { store.setItem("karlTabs", JSON.stringify(state.tabs.filter(t => t.pinned))); store.setItem("karlTabActive", state.active || ""); } catch (e) { /* mode privé */ } };

  // ── rendu ────────────────────────────────────────────────────────────────
  const isOpen = (id) => state.tabs.some(t => t && tabId(t.kind, t.key) === id);
  const resolve = () => (ctx.resolve ? ctx.resolve() : {});
  function renderTabs() { if (h.tabs) h.tabs.update(Tabs(new TabsViewModel({ tabs: state.tabs, active: state.active }, { resolve: resolve() }))); }
  function renderNav() {
    if (ctx.navButtons) ctx.navButtons({ back: !!histStep(state.hist, -1, isOpen).entry, fwd: !!histStep(state.hist, 1, isOpen).entry });
    if (h.hist && ctx.histOpen && ctx.histOpen()) h.hist.update(History(new HistoryViewModel(state.hist, { isOpen })));
  }
  /** Le titre du centre : ce que possède une surface historique d'abord, sinon le nôtre. */
  function title() {
    if (h.title) {
      const legacy = ctx.legacyTitle ? ctx.legacyTitle() : "";
      h.title.update(legacy ? raw(legacy) : CenterTitle(new CenterTitleViewModel({ view: state.view, panel: state.panel, active: state.active, tabs: state.tabs, panels })));
    }
    if (ctx.afterTitle) ctx.afterTitle();
  }
  const pinOf = (kind, key) => pinMark(state.tabs, kind, key);

  // ── onglets ───────────────────────────────────────────────────────────────
  function note(kind, key, label, opts) {
    const r = upsertTab(state.tabs, kind, key, label, opts);
    state.tabs = r.tabs; state.active = r.active;
    save(); renderTabs();
    if (!state.suspend) state.hist = histVisit(state.hist, { id: r.active, kind, label: label || r.active }, NAV_MAX);
    renderNav();
    if (opts && opts.pin && ctx.onPinChange) ctx.onPinChange();
  }
  async function openSessionTab(sid) {
    const s = surfaces.session || {};
    let acte = sessionTabAction(sid, s.sessions ? s.sessions() : {});
    if (acte.action !== "attach" && s.list) { try { acte = sessionTabAction(sid, await s.list()); } catch (e) { /* réseau : on s'en tient au cache */ } }
    if (acte.action === "attach") return s.open && s.open(sid);
    if (acte.action === "relaunch") return s.relaunch && s.relaunch(acte.session);
    if (ctx.notifyAction) ctx.notifyAction("session " + sid + " introuvable — ni vivante, ni enregistrée", "fermer l'onglet", () => closeTab("session:" + String(sid)));
  }
  function activate(id) {
    const t = state.tabs.find(x => tabId(x.kind, x.key) === id);
    if (!t) return;
    const p = parseViewKey(t.key);
    switch (t.kind) {
      case "session":  return openSessionTab(t.key);
      case "review":   return surfaces.review && surfaces.review.open(t.key);
      case "project":  return surfaces.project && surfaces.project.open(t.key);
      case "newticket": return surfaces.newticket && surfaces.newticket.open();
      case "dash":     return openDashboard();
      case "file":     return openFile(p[0], p[1], p[2], p[3]);
      case "dir":      return openDir(p[0], p[1], p[2], p[3]);
      case "commit":   return openCommit(p[0], p[1]);
      case "mail":     return openMail(p[0], t.label);
      case "client":   return openClient(p[0]);
      case "conf":     return openConf(p[0], p[1], p[2]);
      case "pm": case "settings": case "journal": return openPanel(t.kind);
    }
  }
  function togglePin(id) {
    const t = state.tabs.find(x => tabId(x.kind, x.key) === id);
    if (!t || t.fixed) return;
    t.pinned = !t.pinned;
    save(); renderTabs();
    if (ctx.onPinChange) ctx.onPinChange();
  }
  function closeTab(id) {
    const fermaitLaVueAffichee = (id === state.active);   // à lire AVANT de réaffecter
    const r = closeTabAt(state.tabs, id, state.active);
    state.tabs = r.tabs; state.active = r.active;
    const ouvertApres = (x) => r.tabs.some(t => t && tabId(t.kind, t.key) === x);
    if (fermaitLaVueAffichee) { const cible = histCloseTarget(state.hist, id, ouvertApres); if (cible) state.active = cible; }
    save(); renderTabs();
    if (state.active) activate(state.active);
    else closeAll();
  }
  /** Plus rien d'ouvert : chaque surface cède, le tableau de bord revient. */
  function closeAll() {
    for (const k of ["session", "review", "project"]) if (surfaces[k] && surfaces[k].close) surfaces[k].close();
    closeView(); closePanel();
    if (surfaces.newticket && surfaces.newticket.close) surfaces.newticket.close();   // en dernier : c'est lui qui rallume le tableau de bord
  }

  // ── historique (RM2776) ───────────────────────────────────────────────────
  function navGo(delta) {
    const r = histStep(state.hist, delta, isOpen);
    if (!r.entry) return;
    state.hist.idx = r.idx; state.suspend = true;
    try { activate(r.entry.id); } finally { state.suspend = false; }
    renderNav();
  }
  function histGoTo(id) {
    const i = state.hist.items.map(e => e.id).lastIndexOf(id);
    if (i < 0) return;
    state.hist.idx = i; state.suspend = true;
    try { activate(id); } finally { state.suspend = false; }
    histToggle(false); renderNav();
  }
  function histToggle(force) {
    if (!ctx.histShow) return;
    const ouvrir = force === undefined ? !ctx.histOpen() : !!force;
    ctx.histShow(ouvrir);
    if (ouvrir && h.hist) h.hist.update(History(new HistoryViewModel(state.hist, { isOpen })));
  }

  // ── céder la place ───────────────────────────────────────────────────────
  /** Toutes les surfaces sauf `except` se ferment, le vide central se cache. */
  function yieldTo(except) {
    for (const k of ["session", "review", "project", "newticket"]) if (k !== except && surfaces[k] && surfaces[k].close) surfaces[k].close();
    if (except !== "view") closeView();
    if (except !== "panel") closePanel();
    if (ctx.placeholder) ctx.placeholder(false);
  }
  const isBusy = () => !!(state.view || state.panel);

  // ── vues génériques (RM2759) ──────────────────────────────────────────────
  function closeView() { state.view = null; if (h.view) { h.view.update(""); } if (ctx.viewShow) ctx.viewShow(false); }
  function openView(kind, key, label, loader) {
    yieldTo("view");
    if (ctx.viewShow) ctx.viewShow(true);
    if (h.view) h.view.update(html`<div class="empty">chargement…</div>`);
    state.view = { kind, key };
    note(kind, key, label);
    title();
    return (async () => {
      try { const frag = await loader(); if (state.view && state.view.key === key && h.view) h.view.update(frag); }
      catch (e) {
        if (state.view && state.view.key === key && h.view) h.view.update(ViewError(kind === "commit" ? "Commit indisponible" : kind === "mail" ? "Email indisponible" : "Contenu indisponible", e.message));
      }
    })();
  }
  const scopeCtx = () => (ctx.scope ? ctx.scope() : {});
  const defaultTag = (wt) => { const s = scopeCtx(); return scopeTag(fsScope(wt, s.filesData, s.attached, s.projectKey)); };
  function openFile(src, wt, path, tag) {
    tag = tag || (src === "doc" ? "" : defaultTag(wt));
    const key = viewKey([src, wt, path, tag]);
    return openView("file", key, viewTabLabel("file", [src, wt, path]), async () => {
      if (src === "doc") return FileView(new FileViewModel({ path, markdown: /\.md$/i.test(path), content: await repo.docFile(path) }, { md: ctx.md }));
      const f = await repo.fsFile(wt, tag, path, scopeCtx());
      return FileView(new FileViewModel(Object.assign({ path: path || f.name }, f), { md: ctx.md }));
    });
  }
  function openDir(src, wt, path, tag) {
    tag = tag || defaultTag(wt);
    const key = viewKey([src, wt, path, tag]);
    return openView("dir", key, viewTabLabel("dir", [src, wt, path]), async () => {
      const r = await repo.fsLs(wt, tag, path, scopeCtx());
      return DirView(new DirViewModel({ src, wt, path: path || "", rootName: String(wt).split("/").pop(), entries: r.entries || [], tag }));
    });
  }
  function openCommit(sid, sha) {
    const key = viewKey([sid, sha]);
    return openView("commit", key, viewTabLabel("commit", [sid, sha]), async () => {
      const r = await repo.commit(sid, sha);
      return CommitView((r.commit || {}).short || sha, r.message || "", GitPatch(new GitPatchViewModel(r)));
    });
  }
  function openMail(mkey, sujet) {
    const key = viewKey([mkey]);
    return openView("mail", key, viewTabLabel("mail", [mkey], sujet), async () => MailView(new EmailViewModel(await repo.email(mkey))));
  }
  function openClient(client) {
    const key = viewKey([client]);
    return openView("client", key, client, async () => ClientView(new ClientViewModel(await repo.client(client))));
  }
  function openConf(scope, client, project) {
    const key = viewKey([scope, client, project || ""]);
    return openView("conf", key, "⚙ " + (scope === "project" ? project : client), async () => ConfView(await repo.conf(scope, client, project)));
  }

  // ── tableau de bord et panneaux centraux (RM2744, RM2816) ─────────────────
  function openDashboard() {
    yieldTo(null);
    if (ctx.placeholder) ctx.placeholder(true);
    note("dash", "", "tableau de bord", { pin: true });
    if (ctx.dashboard) ctx.dashboard();
    title();
  }
  function closePanel() { state.panel = null; for (const k of Object.keys(panels)) if (panels[k].show) panels[k].show(false); if (ctx.panelShow) ctx.panelShow(false); }
  function openPanel(name) {
    const spec = panels[name]; if (!spec) return;
    state.panel = name;                       // AVANT les fermetures : elles rallumeraient le tableau de bord
    yieldTo("panel");
    if (ctx.panelShow) ctx.panelShow(true);
    for (const k of Object.keys(panels)) if (panels[k].show) panels[k].show(k === name);
    note(name, "", spec.label);
    title();
    if (!state.loaded[name]) { state.loaded[name] = 1; if (spec.load) spec.load(); }
  }
  /** Une surface historique s'est fermée : si plus rien n'occupe le centre, le tableau de bord revient. */
  function fallback() { if (!isBusy() && ctx.nothingElse && ctx.nothingElse()) { if (ctx.placeholder) ctx.placeholder(true); if (ctx.dashboard) ctx.dashboard(); } }

  // ── restauration au démarrage (RM2672/RM2744) : jamais une session ────────
  function restore() {
    renderTabs();
    let last = ""; try { last = store.getItem("karlTabActive") || ""; } catch (e) {}
    const t0 = state.tabs.find(x => tabId(x.kind, x.key) === last);
    if (t0 && t0.kind !== "session") activate(last);
    else { state.active = "dash:"; renderTabs(); title(); }
  }

  // ── montage ──────────────────────────────────────────────────────────────
  const gestures = {
    activate: (n) => activate(n.dataset.id), pin: (n) => togglePin(n.dataset.id), close: (n) => closeTab(n.dataset.id),
    goto: (n) => histGoTo(n.dataset.id),
    "open-dir": (n) => openDir(n.dataset.src, n.dataset.wt, n.dataset.path, n.dataset.tag),
    "open-file": (n) => openFile(n.dataset.src, n.dataset.wt, n.dataset.path, n.dataset.tag),
    "open-project": (n) => surfaces.project && surfaces.project.open(n.dataset.value),
  };
  const onAction = (ev, n) => { const g = gestures[n.dataset.action]; if (!g) return; if (ev.preventDefault) ev.preventDefault(); if (ev.stopPropagation) ev.stopPropagation(); return g(n); };
  const h = {
    tabs: hosts.tabs ? mount(hosts.tabs, "", { events: [["click", "[data-action]", onAction]] }) : null,
    hist: hosts.hist ? mount(hosts.hist, "", { events: [["click", "[data-action]", onAction]] }) : null,
    view: hosts.view ? mount(hosts.view, "", { events: [["click", "[data-action]", onAction]] }) : null,
    title: hosts.title ? mount(hosts.title, "") : null,
  };
  const hasTab = (key, kinds) => state.tabs.some(t => t && String(t.key) === String(key) && (!kinds || kinds.includes(t.kind)));
  return { note, activate, closeTab, togglePin, pinOf, hasTab, renderTabs, title, navGo, histGoTo, histToggle,
           openDashboard, openPanel, closePanel, closeView, isBusy, fallback, restore, yield: yieldTo,
           openFile, openDir, openCommit, openMail, openClient, openConf, current: () => state.view, state,
           register: (kind, surface) => { surfaces[kind] = surface; },
           unmount: () => Object.values(h).forEach(x => x && x.unmount()) };
}
