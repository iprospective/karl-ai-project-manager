// core/store — cache borné, observable, et qui sait dire ce qu'il retient.
// RM2889, lot L0. Aucune dépendance : testable sous node nu (C5).
//
// Deux exigences guident ce module, et elles tirent dans le même sens.
//
// 1. Le cache du cockpit doit être BORNÉ PAR CONSTRUCTION. Un cache sans
//    plafond est une fuite mémoire à retardement : c'est exactement ce que
//    l'enquête RM2807 cherche (des sessions au-delà de 20 Go qu'on ne peut
//    plus rouvrir). Ici la taille maximale est un paramètre obligatoire et
//    l'éviction est la plus ancienne lecture (LRU).
// 2. Un abonnement doit pouvoir être RENDU. `subscribe` retourne sa propre
//    fonction de désabonnement ; un composant démonté rend les siens, et
//    `stats()` permet de le VÉRIFIER au lieu de l'espérer.

export class Store {
  /**
   * @param {string} name   nom lisible, utilisé par les statistiques
   * @param {object} opts   { ttl: ms avant péremption, max: entrées retenues, now: horloge (tests) }
   */
  constructor(name, { ttl = 30000, max = 200, now = () => Date.now() } = {}) {
    if (!name) throw new Error("un store doit être nommé");
    if (!(max > 0)) throw new Error(`store ${name} : max doit être > 0`);
    this.name = name;
    this.ttl = ttl;
    this.max = max;
    this.now = now;
    this._entries = new Map();      // clé → { value, at, read, expired }
    this._subs = new Set();
    this._stats = { hits: 0, misses: 0, stale: 0, evictions: 0, sets: 0 };
    this._view = null;
  }

  /** Valeur fraîche, ou `undefined` si absente ou périmée. Les clés sont des chaînes (un rm_id numérique vaut sa chaîne). */
  get(key) {
    key = String(key);
    const now = this.now;
    const e = this._entries.get(key);
    if (!e) { this._stats.misses++; return undefined; }
    if (now() - e.at > this.ttl) {
      this._entries.delete(key);
      this._stats.stale++;
      return undefined;
    }
    e.read = now();
    this._entries.delete(key);      // réinsertion : la Map garde l'ordre d'insertion,
    this._entries.set(key, e);      // ce qui suffit à tenir un LRU sans structure tierce
    this._stats.hits++;
    return e.value;
  }

  /** Présence fraîche, sans compter ni déplacer (LRU). */
  has(key) { const e = this._entries.get(String(key)); return !!e && this.now() - e.at <= this.ttl; }
  /**
   * Âge de l'entrée (ms depuis son écriture) — `Infinity` si absente, périmée ou marquée par `expire()`. C'est la fraîcheur
   * DOUCE d'un dépôt (revalider en arrière-plan, en continuant de servir la valeur) ; le TTL du store est la borne DURE.
   */
  age(key) { const e = this._entries.get(String(key)); if (!e || e.expired) return Infinity; const a = this.now() - e.at; return a > this.ttl ? Infinity : a; }
  /** Marque l'entrée à revalider (`age()` → Infinity) sans la retirer : la vue continue de l'afficher, le dépôt la relit. */
  expire(key) { const e = this._entries.get(String(key)); if (e) e.expired = true; }
  /** Clés, valeurs, paires — des entrées FRAÎCHES seulement (les périmées sont purgées au passage, sans compter comme des lectures). */
  keys() { const now = this.now(); const out = []; for (const [k, e] of this._entries) { if (now - e.at > this.ttl) { this._entries.delete(k); this._stats.stale++; } else out.push(k); } return out; }
  values() { return this.keys().map(k => this._entries.get(k).value); }
  entries() { return this.keys().map(k => [k, this._entries.get(k).value]); }
  get size() { return this.keys().length; }
  /**
   * Lecture indexée, EN LECTURE SEULE : `store.view[id]` ≡ `store.get(id)`, `Object.values(store.view)` ≡ `store.values()`. Pour les
   * fonctions pures qui reçoivent « un objet de résolutions » ; écrire dedans lève — un cache ne se remplit que par `set()`.
   */
  get view() {
    if (!this._view) this._view = new Proxy({}, {
      get: (_, k) => (typeof k === "string" ? this.get(k) : undefined),
      has: (_, k) => typeof k === "string" && this.has(k),
      ownKeys: () => this.keys(),
      getOwnPropertyDescriptor: (_, k) => (typeof k === "string" && this.has(k) ? { value: this.get(k), enumerable: true, configurable: true, writable: false } : undefined),
      set: (_, k) => { throw new Error(`store ${this.name} : view est en lecture seule (${String(k)}) — passer par set()`); },
      deleteProperty: (_, k) => { throw new Error(`store ${this.name} : view est en lecture seule (${String(k)}) — passer par invalidate()`); },
    });
    return this._view;
  }

  /** Écrit, évince si nécessaire, puis notifie les abonnés. */
  set(key, value) {
    key = String(key);
    const now = this.now;
    if (this._entries.has(key)) this._entries.delete(key);
    this._entries.set(key, { value, at: now(), read: now() });
    this._stats.sets++;
    while (this._entries.size > this.max) {
      const oldest = this._entries.keys().next().value;
      this._entries.delete(oldest);
      this._stats.evictions++;
    }
    this._notify(key, value);
    return value;
  }

  /** Lecture avec repli : appelle `producer` seulement si le cache est froid. */
  async ensure(key, producer) {
    const hit = this.get(key);
    if (hit !== undefined) return hit;
    return this.set(key, await producer(key));
  }

  /** Oublie une clé (ou tout le store si `key` est omise) et notifie. */
  invalidate(key) {
    if (key === undefined) {
      this._entries.clear();
      this._notify(null, undefined);
      return;
    }
    key = String(key);
    if (this._entries.delete(key)) this._notify(key, undefined);
  }

  /** S'abonne aux écritures. Retourne la fonction de DÉSABONNEMENT. */
  subscribe(fn) {
    if (typeof fn !== "function") throw new Error("subscribe attend une fonction");
    this._subs.add(fn);
    return () => this._subs.delete(fn);
  }

  _notify(key, value) {
    for (const fn of this._subs) {
      try { fn(key, value, this); }
      catch (err) {
        // un abonné qui casse ne doit pas empêcher les autres d'être notifiés
        console.error(`store ${this.name} : abonné en erreur`, err);
      }
    }
  }

  /** Ce que le store retient, en clair — pour la sonde mémoire (L1b). */
  stats() {
    return {
      name: this.name, entries: this._entries.size, max: this.max,
      subscribers: this._subs.size, ...this._stats,
    };
  }
}

const registry = new Map();

/** Crée ou retrouve un store nommé. Un seul store par nom, pour toute la page. */
export function defineStore(name, opts) {
  if (!registry.has(name)) registry.set(name, new Store(name, opts));
  return registry.get(name);
}

/**
 * Les caches du cockpit, nommés et bornés en un seul endroit (RM3005). Le TTL est la borne DURE (l'entrée disparaît) ; la
 * fraîcheur DOUCE (revalider sans cesser d'afficher) est celle des dépôts, lue par `age()`. `opts.now` : horloge des tests.
 *   resolve  rm_id → résolution du ticket (/ticket/resolve ; briefs partiels semés par /refresh)
 *   sess     rm_id → entrée live du registre /sessions (réécrite à chaque tick)
 *   mc       rm_id → { t, mc } mergeabilité (RM2384)      usage  rm_id → { t, usage, meta } conso live (RM2373)
 *   ts       rm_id → sessions du ticket (RM2726)          trans  rm_id → transitions de statut (RM2888)
 */
export const STORE_BOUNDS = Object.freeze({
  resolve: { name: "ticket.resolve",      ttl: 30 * 60000, max: 500 },
  sess:    { name: "session.registry",    ttl: 10 * 60000, max: 300 },
  mc:      { name: "ticket.mergecheck",   ttl: 10 * 60000, max: 200 },
  usage:   { name: "ticket.usage",        ttl: 10 * 60000, max: 200 },
  ts:      { name: "ticket.sessions",     ttl: 10 * 60000, max: 200 },
  trans:   { name: "ticket.transitions",  ttl: 20000,      max: 100 },
});
export function appStores(opts = {}) {
  const out = {};
  for (const [k, b] of Object.entries(STORE_BOUNDS)) out[k] = defineStore(b.name, { ttl: b.ttl, max: b.max, now: opts.now });
  return out;
}

/** État de tous les stores — ce que la sonde mémoire affichera. */
export function storeStats() {
  return [...registry.values()].map(s => s.stats());
}

/** Remise à zéro complète (tests, et bouton « vider le cache »). */
export function resetStores() {
  for (const s of registry.values()) s.invalidate();
  registry.clear();
}
