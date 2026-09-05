// models/tickets/TicketRepository — résolution, mergecheck, conso, sessions d'un ticket. RM2889.
//
// Les CACHES sont injectés et partagés par référence avec le monolithe : une
// soixantaine de vues historiques les lisent encore en direct (resolveCache[rm]…).
// Le dépôt possède la LOGIQUE — péremption (RM2630), dédup des résolutions en
// vol (RM2763), verrous in-flight (RM2384, RM2373) — le stockage suit en L6.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get } from "../../core/api.js";
import { routeFor } from "../../core/endpoints.js";
const enc = encodeURIComponent;

export const RESOLVE_TTL_MS = 30000, MC_TTL_MS = 30000, USAGE_TTL_MS = 20000;

export class TicketRepository extends Repository {
  constructor({ caches = {}, now = () => Date.now() } = {}) {
    super({ name: "ticket", ttl: RESOLVE_TTL_MS, max: 500, factory: new Factory({ type: "ticket" }),
            routes: { resolve: "ticket.resolve", mergecheck: "ticket.mergecheck", usage: "ticket.usage", sessions: routeFor("/ticket-sessions") } });
    this.c = { resolve: caches.resolve || {}, resolveAt: caches.resolveAt || {}, mc: caches.mc || {}, usage: caches.usage || {}, ts: caches.ts || {} };
    this.inflight = { resolve: {}, mc: {}, usage: {} };
    this.now = now;
  }
  // ── résolution ────────────────────────────────────────────────────────────
  stale(rm) { const t = this.c.resolveAt[String(rm)]; return t === undefined || (this.now() - t) > RESOLVE_TTL_MS; }
  /** Sert le cache s'il est entier ; sinon UNE résolution partagée par tous les appelants en vol. */
  async ensureResolved(rm, force, onResolved) {
    rm = String(rm);
    const cached = this.c.resolve[rm];
    if (!force && cached !== undefined && !(cached && cached.partial)) return cached;
    if (this.inflight.resolve[rm]) return this.inflight.resolve[rm];
    this.inflight.resolve[rm] = (async () => {
      try { this.c.resolve[rm] = await get(this.path("resolve") + "/" + enc(rm)); } catch (e) { this.c.resolve[rm] = null; }
      this.c.resolveAt[rm] = this.now();
      if (onResolved) onResolved(rm, this.c.resolve[rm]);
      return this.c.resolve[rm];
    })().finally(() => { delete this.inflight.resolve[rm]; });
    return this.inflight.resolve[rm];
  }
  /** Révalidation silencieuse : sert le cache, puis `after(r)` seulement si le serveur a du neuf. */
  revalidate(rm, after, onResolved) {
    rm = String(rm);
    if (!this.stale(rm)) return Promise.resolve(undefined);
    const before = JSON.stringify(this.c.resolve[rm] || null);
    return this.ensureResolved(rm, true, onResolved).then(r => { const changed = JSON.stringify(r || null) !== before; if (changed && after) after(r); return changed; });
  }
  // ── mergeabilité (RM2384) ─────────────────────────────────────────────────
  mcFresh(rm) { const c = this.c.mc[String(rm)]; return !!(c && (this.now() - c.t < MC_TTL_MS)); }
  async ensureMergecheck(rm, force) {
    rm = String(rm);
    if (!force && this.mcFresh(rm)) return this.c.mc[rm].mc;
    if (this.inflight.mc[rm]) return;
    this.inflight.mc[rm] = true;
    try { this.c.mc[rm] = { t: this.now(), mc: await get(this.path("mergecheck") + "/" + enc(rm)) }; }
    catch (e) { this.c.mc[rm] = { t: this.now(), mc: null }; }
    finally { this.inflight.mc[rm] = false; }
    return this.c.mc[rm].mc;
  }
  // ── conso live (RM2373) ───────────────────────────────────────────────────
  usageFresh(rm) { const c = this.c.usage[String(rm)]; return !!(c && (this.now() - c.t < USAGE_TTL_MS)); }
  usageInFlight(rm) { return !!this.inflight.usage[String(rm)]; }
  async ensureUsage(rm, force) {
    rm = String(rm);
    if (!force && this.usageFresh(rm)) return this.c.usage[rm].usage;
    if (this.inflight.usage[rm]) return;
    this.inflight.usage[rm] = true;
    try { const r = await get(this.path("usage") + "/" + enc(rm)); this.c.usage[rm] = { t: this.now(), usage: r.usage || null, meta: r }; }
    catch (e) { this.c.usage[rm] = { t: this.now(), usage: null, meta: null }; }
    finally { this.inflight.usage[rm] = false; }
    return this.c.usage[rm].usage;
  }
  // ── sessions du ticket (RM2726) ───────────────────────────────────────────
  async ensureTicketSessions(rm, force) {
    rm = String(rm);
    if (this.c.ts[rm] !== undefined && !force) return this.c.ts[rm];
    try { this.c.ts[rm] = await get(this.path("sessions") + "/" + enc(rm)); } catch (e) { this.c.ts[rm] = null; }
    return this.c.ts[rm];
  }
}
