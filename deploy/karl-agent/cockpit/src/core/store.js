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

const now = () => Date.now();

export class Store {
  /**
   * @param {string} name   nom lisible, utilisé par les statistiques
   * @param {object} opts   { ttl: ms avant péremption, max: entrées retenues }
   */
  constructor(name, { ttl = 30000, max = 200 } = {}) {
    if (!name) throw new Error("un store doit être nommé");
    if (!(max > 0)) throw new Error(`store ${name} : max doit être > 0`);
    this.name = name;
    this.ttl = ttl;
    this.max = max;
    this._entries = new Map();      // clé → { value, at, read }
    this._subs = new Set();
    this._stats = { hits: 0, misses: 0, stale: 0, evictions: 0, sets: 0 };
  }

  /** Valeur fraîche, ou `undefined` si absente ou périmée. */
  get(key) {
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

  /** Écrit, évince si nécessaire, puis notifie les abonnés. */
  set(key, value) {
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

/** État de tous les stores — ce que la sonde mémoire affichera. */
export function storeStats() {
  return [...registry.values()].map(s => s.stats());
}

/** Remise à zéro complète (tests, et bouton « vider le cache »). */
export function resetStores() {
  for (const s of registry.values()) s.invalidate();
  registry.clear();
}
