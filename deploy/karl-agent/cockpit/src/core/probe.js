// core/probe — la sonde mémoire du cockpit (RM3007) : des échantillons datés, ventilés par module (nœuds montés, écouteurs/minuteries/
// abonnements retenus, rendus, entrées de store), un historique borné, et une lecture qui dit quand un compteur GRIMPE SANS REDESCENDRE.
// C'est l'outil de l'enquête RM2807 (onglets à 20 Go). Aucun DOM ici : `sample()` est prêté (boot.js : domStatsByModule + storeStats +
// tas JS si le navigateur l'expose). Coût nul désactivée : rien ne tourne tant que `start()` n'a pas été appelé.

/** Module « propriétaire » d'un store, par son nom : `ticket.resolve` → ticket, `session.registry` → sessions, `mail` → mail. */
export function storeModule(name) {
  const n = String(name || "");
  if (n.startsWith("session.")) return "sessions";
  return n.includes(".") ? n.split(".")[0] : n;
}

/** Un échantillon normalisé : { t, heap, modules: { <module>: { mounted, nodes, pending, renders, entries, subscribers } }, total }. */
export function normalize(raw, t) {
  const mods = {};
  const at = (m) => mods[m] || (mods[m] = { mounted: 0, nodes: 0, pending: 0, renders: 0, entries: 0, subscribers: 0 });
  for (const [m, d] of Object.entries((raw && raw.dom) || {})) { const x = at(m); x.mounted += d.mounted || 0; x.nodes += d.nodes || 0; x.pending += d.pending || 0; x.renders += d.renders || 0; }
  for (const s of (raw && raw.stores) || []) { const x = at(storeModule(s.name)); x.entries += s.entries || 0; x.subscribers += s.subscribers || 0; }
  const total = { mounted: 0, nodes: 0, pending: 0, renders: 0, entries: 0, subscribers: 0 };
  for (const x of Object.values(mods)) for (const k of Object.keys(total)) total[k] += x[k];
  return { t, heap: raw && raw.heap != null ? raw.heap : null, modules: mods, total };
}

export const WATCHED = ["nodes", "pending", "entries", "subscribers"];

/**
 * Un compteur qui grimpe sans redescendre : sur les `window` derniers échantillons, jamais de baisse, et une hausse d'au moins
 * `minGrowth` (relative) ET `minDelta` (absolue) entre le premier et le dernier. Rend [{ module, counter, from, to }].
 */
export function detectLeaks(history, { window = 6, minGrowth = 0.2, minDelta = 5 } = {}) {
  if (!history || history.length < window) return [];
  const last = history.slice(-window);
  const out = [];
  const mods = new Set(); last.forEach(s => Object.keys(s.modules).forEach(m => mods.add(m)));
  for (const m of [...mods].sort()) {
    for (const c of WATCHED) {
      const vals = last.map(s => (s.modules[m] ? s.modules[m][c] : 0));
      let up = true;
      for (let i = 1; i < vals.length; i++) if (vals[i] < vals[i - 1]) { up = false; break; }
      const from = vals[0], to = vals[vals.length - 1];
      if (up && to - from >= minDelta && to > from * (1 + minGrowth)) out.push({ module: m, counter: c, from, to });
    }
  }
  return out;
}

/** Rendus par minute d'un module entre deux échantillons (le compteur `renders` est cumulé). */
export function rendersPerMin(prev, cur, module) {
  if (!prev || !cur || cur.t <= prev.t) return 0;
  const a = prev.modules[module] ? prev.modules[module].renders : 0, b = cur.modules[module] ? cur.modules[module].renders : 0;
  return Math.max(0, Math.round((b - a) / (cur.t - prev.t) * 60000));
}

/**
 * La sonde : `sample()` prêté, horloge et minuterie injectables (tests). `start(ms)` / `stop()` ; `tick()` prend un échantillon ;
 * `subscribe(fn)` est appelé à chaque échantillon ; `history` (borné à `capacity`), `latest`, `series(module, counter)`, `alerts()`, `toJSON()`.
 */
export function createProbe({ sample, now = () => Date.now(), later = (fn, ms) => setInterval(fn, ms), clear = (id) => clearInterval(id), capacity = 180 } = {}) {
  if (typeof sample !== "function") throw new Error("createProbe : sample() est requis");
  const history = []; const subs = new Set(); let timer = null, interval = 0, prev = null;
  const probe = {
    get on() { return timer !== null; },
    get interval() { return interval; },
    get history() { return history; },
    get latest() { return history.length ? history[history.length - 1] : null; },
    get previous() { return history.length > 1 ? history[history.length - 2] : null; },
    tick() {
      let raw; try { raw = sample(); } catch (e) { raw = { error: String(e && e.message || e) }; }
      const s = normalize(raw, now()); if (raw && raw.error) s.error = raw.error;
      prev = probe.latest; history.push(s); while (history.length > capacity) history.shift();
      for (const fn of subs) { try { fn(s, probe); } catch (e) { console.error("sonde : abonné en erreur", e); } }
      return s;
    },
    start(ms = 10000) { probe.stop(); interval = ms; timer = later(() => probe.tick(), ms); probe.tick(); return probe; },
    stop() { if (timer !== null) { clear(timer); timer = null; } return probe; },
    reset() { history.length = 0; prev = null; return probe; },
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    modules() { const set = new Set(); history.forEach(s => Object.keys(s.modules).forEach(m => set.add(m))); return [...set].sort(); },
    series(module, counter) { return history.map(s => (s.modules[module] ? s.modules[module][counter] || 0 : 0)); },
    rate(module) { return rendersPerMin(probe.previous, probe.latest, module); },
    alerts(opts) { return detectLeaks(history, opts); },
    toJSON() { return { taken_at: now(), interval, samples: history.length, history, alerts: detectLeaks(history) }; },
  };
  void prev;
  return probe;
}
