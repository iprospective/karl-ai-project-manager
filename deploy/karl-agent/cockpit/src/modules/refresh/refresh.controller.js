// controllers/refresh.controller — le tick unique du cockpit (RM2763 : un composite /refresh au rythme des sessions, chaque bloc à sa
// période ; RM2613 : cadence adaptative, pause quand l'onglet est caché), la pastille de santé de l'en-tête, le bouton « ⬆ MAJ dispo »
// (RM2571) et les questions sans réponse (RM2598). RM2889.
//
// Hôtes : `health` (la pastille), `healthtxt`, `updbtn`. Les blocs reçus sont livrés aux domaines par `ctx.on*` (sessions → compteurs,
// worklog, tableau de bord, poste) ; les caches de résolution sont partagés par référence (briefs semés en `partial`).
import { RefreshService } from "./refresh.service.js";
import { pollDelay, healthState, healthKo, coreUpdateState, coreUpdateText } from "./refresh.js";

export function mountRefresh(hosts = {}, ctx = {}) {
  const svc = ctx.service || new RefreshService({ caches: ctx.caches || {} });
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const hidden = () => (ctx.hidden ? !!ctx.hidden() : (typeof document !== "undefined" && document.hidden));
  const env = () => ({ attached: ctx.attached ? ctx.attached() : null, dashboardVisible: ctx.dashboardVisible ? !!ctx.dashboardVisible() : false, worklogVisible: ctx.worklogVisible ? !!ctx.worklogVisible() : false });
  let core = null, timer = null;
  const paint = (s) => { if (hosts.health) { hosts.health.className = s.cls; hosts.health.title = s.title; } if (hosts.healthtxt) hosts.healthtxt.textContent = s.text; };
  function renderHealth(h) { paint(healthState(h)); }
  function renderHealthKo(msg) { paint(healthKo(msg)); }
  function renderCoreUpdate(d) {
    core = d; const st = coreUpdateState(d); const b = hosts.updbtn; if (!b) return;
    b.style.display = st.on ? "" : "none"; if (st.on) { b.textContent = st.text; b.title = st.title; }
  }
  function showCoreUpdate() { if (!core) return; if (ctx.alert) ctx.alert(coreUpdateText(core)); }
  const on = {
    health: renderHealth, healthKo: renderHealthKo, coreupdate: renderCoreUpdate,
    sessions: (list) => (ctx.onSessions ? ctx.onSessions(list) : null),
    worklog: (d) => { if (ctx.onWorklog) ctx.onWorklog(d); },
    dashboard: (d) => { if (ctx.onDashboard) ctx.onDashboard(d); },
    env: (k, d) => { if (ctx.onEnv) ctx.onEnv(k, d); },
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
    Promise.resolve(fetch()).finally(() => { if (!hidden()) timer = later(tick, pollDelay(svc.hot > 0)); });
  }
  const disposers = [];
  const listen = (node, type, fn) => { if (node && node.addEventListener) { node.addEventListener(type, fn); disposers.push(() => node.removeEventListener(type, fn)); } };
  let started = false;
  /** Premier tick (tous les blocs sont dus) + rattrapage au retour au premier plan. À appeler quand la configuration (jeton) est connue. */
  function start() {
    if (started) return; started = true;
    tick();
    listen(ctx.root || (typeof document !== "undefined" ? document : null), "visibilitychange", () => { if (hidden()) return; if (!timer) tick(); });
  }
  listen(hosts.updbtn, "click", () => showCoreUpdate());
  return { fetch, refreshSessions, refreshHealth, loadPending, refreshCoreUpdate, showCoreUpdate, renderHealth, renderHealthKo, renderCoreUpdate, tick, start,
    stale: () => svc.stale, hot: () => svc.hot, core: () => core, svc,
    unmount() { if (timer) { clearTimeout(timer); timer = null; } disposers.forEach(d => d()); disposers.length = 0; } };
}
