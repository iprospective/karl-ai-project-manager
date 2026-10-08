// controllers/refresh.controller — le tick unique du cockpit (RM2763 : un composite /refresh au rythme des sessions, chaque bloc à sa
// période ; RM2613 : cadence adaptative, pause quand l'onglet est caché), la pastille de santé de l'en-tête, le bouton « ⬆ MAJ dispo »
// (RM2571) et les questions sans réponse (RM2598). RM2889.
//
// Hôtes : `health` (la pastille), `healthtxt`, `updbtn`. Les blocs reçus sont livrés aux domaines par `ctx.on*` (sessions → compteurs,
// worklog, tableau de bord, poste) ; les briefs sont semés en `partial` dans le store de résolution (RM3005).
import { RefreshService } from "./refresh.service.js";
import { PushService } from "./push.service.js";
import { pollDelay, healthState, healthKo, coreUpdateState, coreUpdateText, coreUpdateRunState, coreUpdateLogText, versionMismatch } from "./refresh.js";

export function mountRefresh(hosts = {}, ctx = {}) {
  const svc = ctx.service || new RefreshService({ stores: ctx.stores || {} });
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const hidden = () => (ctx.hidden ? !!ctx.hidden() : (typeof document !== "undefined" && document.hidden));
  const env = () => ({ attached: ctx.attached ? ctx.attached() : null, dashboardVisible: ctx.dashboardVisible ? !!ctx.dashboardVisible() : false, worklogVisible: ctx.worklogVisible ? !!ctx.worklogVisible() : false });
  let core = null, timer = null;
  // RM3006 : le canal de push — les blocs poussés passent par la même livraison que le tick ; le tick reste, en réconciliation
  const push = ctx.push || new PushService({ open: ctx.eventSource !== undefined ? ctx.eventSource : ((u) => (typeof EventSource !== "undefined" ? new EventSource(u) : null)), token: ctx.token || null });
  push.onBlocks = (d) => svc.ingest(d, env, on, true);
  push.onTopics = (topics, d) => { if (ctx.onTopics) ctx.onTopics(topics, d); };
  push.onState = (alive) => { if (hosts.health) hosts.health.classList && hosts.health.classList.toggle("push", !!alive); if (ctx.onPush) ctx.onPush(alive); };
  const paint = (s) => { if (hosts.health) { hosts.health.className = s.cls + (push.alive ? " push" : ""); hosts.health.title = s.title + (push.alive ? " · canal de push actif" : ""); } if (hosts.healthtxt) hosts.healthtxt.textContent = s.text; };
  function renderHealth(h) { paint(healthState(h)); if (hosts.verwarn) { const m = versionMismatch(h && h.version, ctx.version); hosts.verwarn.textContent = m; hosts.verwarn.style.display = m ? "" : "none"; } }   // RM3000
  function renderHealthKo(msg) { paint(healthKo(msg)); }
  function renderCoreUpdate(d) {
    core = d; const st = coreUpdateState(d); const b = hosts.updbtn; if (!b) return;
    b.style.display = st.on ? "" : "none"; if (st.on) { b.textContent = st.text; b.title = st.title; }
  }
  // ── RM2571 : appliquer la mise à jour DEPUIS le cockpit ───────────────────
  // Le serveur détache le travail (il redémarre karl-agent quand son propre code a changé) : on suit
  // par /core/update-log, et une erreur réseau pendant ce redémarrage n'est PAS un échec — on
  // continue de sonder. Sans ça, le bouton annoncerait une panne au milieu d'un geste réussi.
  let suivi = null;
  function renderCoreRun(d) {
    const st = coreUpdateRunState(d); const b = hosts.updbtn; if (!b) return;
    if (!st.on) return;
    b.style.display = ""; b.textContent = st.text; b.title = st.title;
    b.disabled = !!st.busy;
  }
  function pollCoreUpdate(done) {
    if (suivi) return;
    const battre = async () => {
      let d = null;
      try { d = await svc.coreUpdateLog(); } catch (e) { d = null; }      // redémarrage en cours
      if (d) renderCoreRun(d);
      if (d && !d.running) {
        suivi = null;
        if (ctx.alert) ctx.alert(coreUpdateLogText(d));
        refreshCoreUpdate(true);                                          // la version a changé
        if (done) done(d);
        return;
      }
      suivi = later(battre, 2000);
    };
    suivi = later(battre, 1500);
  }
  async function runCoreUpdate() {
    if (!core) return;
    if (!core.can_update) { if (ctx.alert) ctx.alert(coreUpdateText(core)); return; }
    if (ctx.confirm && !ctx.confirm(coreUpdateText(core))) return;
    try {
      const r = await svc.coreUpdateRun();
      renderCoreRun({ running: true, started_at: r && r.started_at, by: r && r.by, lines: [] });
      pollCoreUpdate();
    } catch (e) { if (ctx.notify) ctx.notify("mise à jour refusée : " + e.message, true); }
  }
  /** Clic : une MAJ dispo se lance ; un run en cours (ou fini) montre son journal. */
  async function showCoreUpdate() {
    let d = null;
    try { d = await svc.coreUpdateLog(); } catch (e) { d = null; }
    if (d && d.running) { if (ctx.alert) ctx.alert(coreUpdateLogText(d)); pollCoreUpdate(); return; }
    if (core && core.available) return runCoreUpdate();
    if (d && d.started_at) { if (ctx.alert) ctx.alert(coreUpdateLogText(d)); return; }
    if (core && ctx.alert) ctx.alert(coreUpdateText(core));
  }
  const on = {
    health: renderHealth, healthKo: renderHealthKo, coreupdate: renderCoreUpdate,
    sessions: (list) => (ctx.onSessions ? ctx.onSessions(list) : null),
    worklog: (d) => { if (ctx.onWorklog) ctx.onWorklog(d); },
    dashboard: (d) => { if (ctx.onDashboard) ctx.onDashboard(d); },
    env: (k, d) => { if (ctx.onEnv) ctx.onEnv(k, d); },
    pmhealth: (d) => { if (ctx.onPmHealth) ctx.onPmHealth(d); },   // RM3369

  };
  /** Un composite ; `includes` force des blocs hors période (après une action : spawn, kill, move…). */
  function fetch(includes) { return svc.fetch(includes, env, on); }
  const refreshSessions = () => fetch(["sessions"]), refreshHealth = () => fetch(["health"]), loadPending = () => fetch(["pending"]);
  /** RM2571 : le poll périodique passe par le composite ; `force` sonde le remote tout de suite. */
  async function refreshCoreUpdate(force) {
    if (!force) return fetch(["coreupdate"]);
    try { renderCoreUpdate(await svc.coreUpdate()); } catch (e) { /* silencieux */ }
  }
  /** RM2613 : tick auto-replanifié ; pause en arrière-plan, repris par visibilitychange. */
  function tick() {
    timer = null;
    if (hidden()) return;
    Promise.resolve(fetch()).finally(() => { push.sync(svc.pushSpecs(env())); if (!hidden()) timer = later(tick, pollDelay(svc.hot > 0, push.alive)); });
  }
  const disposers = [];
  const listen = (node, type, fn) => { if (node && node.addEventListener) { node.addEventListener(type, fn); disposers.push(() => node.removeEventListener(type, fn)); } };
  let started = false;
  /** Premier tick (tous les blocs sont dus) + rattrapage au retour au premier plan. À appeler quand la configuration (jeton) est connue. */
  function start() {
    if (started) return; started = true;
    tick();
    // RM2571 : une mise à jour peut être EN COURS alors que le cockpit vient (re)démarrer — c'est même
    // le cas nominal, puisqu'elle redémarre karl-agent. On reprend son suivi au chargement.
    try { Promise.resolve(svc.coreUpdateLog()).then((d) => { if (d && d.running) { renderCoreRun(d); pollCoreUpdate(); } }).catch(() => {}); } catch (e) { /* service sans suivi */ }
    listen(ctx.root || (typeof document !== "undefined" ? document : null), "visibilitychange", () => { if (hidden()) return; if (!timer) tick(); });
  }
  listen(hosts.updbtn, "click", () => showCoreUpdate());
  return { fetch, refreshSessions, refreshHealth, loadPending, refreshCoreUpdate, showCoreUpdate, runCoreUpdate, pollCoreUpdate, renderCoreRun, renderHealth, renderHealthKo, renderCoreUpdate, tick, start,
    stale: () => svc.stale, hot: () => svc.hot, core: () => core, svc, push,
    unmount() { if (timer) { clearTimeout(timer); timer = null; } if (suivi) { clearTimeout(suivi); suivi = null; } push.disconnect(); disposers.forEach(d => d()); disposers.length = 0; } };
}
