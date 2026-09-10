// models/tickets/TicketRepository — résolution, mergecheck, conso, sessions d'un ticket. RM2889.
//
// RM3005 : le stockage est celui de `core/store.js` — les stores nommés `appStores()` (resolve, mc, usage, ts, trans), bornés
// (max + TTL dur) et observables ; les vues lisent `store.get(rm)` ou s'y abonnent. Le dépôt possède la LOGIQUE — fraîcheur
// douce (`store.age`, RM2630), dédup des résolutions en vol (RM2763), verrous in-flight (RM2384, RM2373).
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";
import { routeFor } from "../../core/endpoints.js";
import { appStores } from "../../core/store.js";
const enc = encodeURIComponent;

export const RESOLVE_TTL_MS = 30000, MC_TTL_MS = 30000, USAGE_TTL_MS = 20000, TRANS_TTL_MS = 20000;

export class TicketRepository extends Repository {
  constructor({ stores = null, now = () => Date.now() } = {}) {
    super({ name: "ticket", ttl: RESOLVE_TTL_MS, max: 500, factory: new Factory({ type: "ticket" }),
            routes: { resolve: "ticket.resolve", mergecheck: "ticket.mergecheck", usage: "ticket.usage", sessions: routeFor("/ticket-sessions"),
                      transitions: routeFor("/ticket-transitions"), deliver: routeFor("/mr/deliver"), spawn: "session.spawn", send: "session.send" } });
    this.s = stores || appStores({ now });
    this.inflight = { resolve: {}, mc: {}, usage: {} };   // verrous transitoires (pas du stockage) : une promesse/un drapeau par requête en vol
    this.now = now;
  }
  // ── résolution ────────────────────────────────────────────────────────────
  stale(rm) { return this.s.resolve.age(rm) > RESOLVE_TTL_MS; }
  /** Sert le cache s'il est entier ; sinon UNE résolution partagée par tous les appelants en vol. */
  async ensureResolved(rm, force, onResolved) {
    rm = String(rm);
    const cached = this.s.resolve.get(rm);
    if (!force && cached !== undefined && !(cached && cached.partial)) return cached;
    if (this.inflight.resolve[rm]) return this.inflight.resolve[rm];
    this.inflight.resolve[rm] = (async () => {
      let r; try { r = await get(this.path("resolve") + "/" + enc(rm)); } catch (e) { r = null; }
      this.s.resolve.set(rm, r);
      if (onResolved) onResolved(rm, r);
      return r;
    })().finally(() => { delete this.inflight.resolve[rm]; });
    return this.inflight.resolve[rm];
  }
  /** Révalidation silencieuse : sert le cache, puis `after(r)` seulement si le serveur a du neuf. */
  revalidate(rm, after, onResolved) {
    rm = String(rm);
    if (!this.stale(rm)) return Promise.resolve(undefined);
    const before = JSON.stringify(this.s.resolve.get(rm) || null);
    return this.ensureResolved(rm, true, onResolved).then(r => { const changed = JSON.stringify(r || null) !== before; if (changed && after) after(r); return changed; });
  }
  // ── mergeabilité (RM2384) ─────────────────────────────────────────────────
  mcFresh(rm) { return this.s.mc.age(rm) < MC_TTL_MS; }
  async ensureMergecheck(rm, force) {
    rm = String(rm);
    if (!force && this.mcFresh(rm)) return this.s.mc.get(rm).mc;
    if (this.inflight.mc[rm]) return;
    this.inflight.mc[rm] = true;
    let mc; try { mc = await get(this.path("mergecheck") + "/" + enc(rm)); } catch (e) { mc = null; }
    finally { this.inflight.mc[rm] = false; }
    return this.s.mc.set(rm, { t: this.now(), mc }).mc;
  }
  // ── conso live (RM2373) ───────────────────────────────────────────────────
  usageFresh(rm) { return this.s.usage.age(rm) < USAGE_TTL_MS; }
  usageInFlight(rm) { return !!this.inflight.usage[String(rm)]; }
  async ensureUsage(rm, force) {
    rm = String(rm);
    if (!force && this.usageFresh(rm)) return this.s.usage.get(rm).usage;
    if (this.inflight.usage[rm]) return;
    this.inflight.usage[rm] = true;
    let e; try { const r = await get(this.path("usage") + "/" + enc(rm)); e = { t: this.now(), usage: r.usage || null, meta: r }; }
    catch (err) { e = { t: this.now(), usage: null, meta: null }; }
    finally { this.inflight.usage[rm] = false; }
    return this.s.usage.set(rm, e).usage;
  }
  // ── transitions de statut (RM2888) : la liste vient des NORMS, jamais d'ici ─
  async transitions(rm, force) {
    rm = String(rm);
    const hit = this.s.trans.get(rm);
    if (hit && !force && this.s.trans.age(rm) < TRANS_TTL_MS) return hit;
    return this.s.trans.set(rm, await get(this.path("transitions") + "/" + enc(rm)));
  }
  invalidateTransitions(rm) { this.s.trans.invalidate(rm); }
  /** RM2355 : livre la branche (MR + merge → dev) pour franchir la merge gate. */
  deliver(rm) { return post(this.path("deliver"), { rm_id: String(rm), confirm: true }); }
  spawn(body) { return post(this.path("spawn"), body); }
  send(sid, msg) { return post(this.path("send"), { rm_id: sid, msg, enter: true }); }
  // ── sessions du ticket (RM2726) ───────────────────────────────────────────
  async ensureTicketSessions(rm, force) {
    rm = String(rm);
    const hit = this.s.ts.get(rm);
    if (hit !== undefined && !force) return hit;
    let r; try { r = await get(this.path("sessions") + "/" + enc(rm)); } catch (e) { r = null; }
    return this.s.ts.set(rm, r);
  }
  /** Oublie les sessions connues d'un ticket (après un lancement ou un envoi : la liste a changé). */
  forgetTicketSessions(rm) { this.s.ts.invalidate(rm); }
}
