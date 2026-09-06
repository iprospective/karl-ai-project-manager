// core/log — le journal du front (RM3011) : mêmes sévérités et catégories que le serveur (scripts/pm_log.py, RM3010), tampon circulaire
// en mémoire, abonnés (le panneau « journal », le badge), remontée des `warn`/`error` au serveur par lots (POST /api/log/write) — sans
// jamais boucler sur son propre échec. Aucune dépendance au DOM : `installGlobalCapture` reçoit la fenêtre.
export const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };
export const CATEGORIES = ["auth", "issue", "provider", "tmux", "claude", "worklog", "files", "api", "mail", "sets", "refresh", "pm", "session", "voice", "env", "front", "system"];

/** Résumé court d'une erreur : type, message, deux premiers cadres de la pile. */
export function errorBrief(e, limit = 600) {
  if (e == null) return "";
  const head = e && e.message !== undefined ? `${e.name || "Error"}: ${e.message}` : String(e);
  const stack = e && e.stack ? String(e.stack).split("\n").slice(1, 3).map(s => s.trim()).join(" ← ") : "";
  return (head + (stack ? " @ " + stack : "")).slice(0, limit);
}

/**
 * @param {object} o  { capacity (500), now, remote(rec) → Promise (POST du serveur ; null = local seul), minRemote ("warn"), later, version, ua }
 */
export function createLog({ capacity = 500, now = () => new Date(), remote = null, minRemote = "warn", later = (fn, ms) => setTimeout(fn, ms), version = "", ua = "" } = {}) {
  const entries = []; const subs = new Set(); let seq = 0; let pending = []; let timer = null; let failures = 0;
  function push(cat, level, msg, fields) {
    const lvl = LEVELS[level] ? level : "info";
    const rec = Object.assign({ id: ++seq, ts: now().toISOString(), level: lvl, cat: CATEGORIES.includes(cat) ? cat : "front", msg: String(msg == null ? "" : msg), src: "front" }, fields || {});
    if (!CATEGORIES.includes(cat)) rec.bad_category = String(cat);
    entries.push(rec); if (entries.length > capacity) entries.splice(0, entries.length - capacity);
    for (const fn of subs) { try { fn(rec); } catch (e) { /* un abonné qui plante ne coupe pas le journal */ } }
    if (remote && LEVELS[lvl] >= LEVELS[minRemote] && failures < 5) { pending.push(rec); if (!timer) timer = later(flush, 800); }
    return rec;
  }
  async function flush() {
    timer = null; const batch = pending.splice(0);
    for (const r of batch) {
      const fields = Object.fromEntries(Object.entries(r).filter(([k]) => !["id", "ts", "level", "cat", "msg", "src"].includes(k)));
      try { await remote({ category: r.cat, level: r.level, message: r.msg, fields: Object.assign(fields, { version, ua: String(ua).slice(0, 120) }) }); failures = 0; }
      catch (e) { failures++; }                                                  // jamais journalisé : ça bouclerait
    }
  }
  const api = { log: push, entries: () => entries.slice(), subscribe(fn) { subs.add(fn); return () => subs.delete(fn); }, clear() { entries.length = 0; }, flush, pending: () => pending.length, failures: () => failures };
  for (const lvl of Object.keys(LEVELS)) api[lvl] = (cat, msg, fields) => push(cat, lvl, msg, fields);
  return api;
}

/** Capte les exceptions non rattrapées et les promesses rejetées de la fenêtre → `front` / `error`. Rend le désabonnement. */
export function installGlobalCapture(log, win) {
  if (!win || !win.addEventListener) return () => {};
  const onError = (e) => log.error("front", (e && e.message) || "erreur non rattrapée", { file: e && e.filename, line: e && e.lineno, trace: e && e.error ? errorBrief(e.error) : undefined });
  const onReject = (e) => { const r = e && e.reason; log.error("front", "promesse rejetée : " + ((r && r.message) || String(r)), { trace: r && r.stack ? errorBrief(r) : undefined }); };
  win.addEventListener("error", onError); win.addEventListener("unhandledrejection", onReject);
  return () => { win.removeEventListener("error", onError); win.removeEventListener("unhandledrejection", onReject); };
}
