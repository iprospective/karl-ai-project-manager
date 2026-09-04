// models/Repository — l'accès aux entités : store + api, jamais de DOM. RM2889, L0.
//
// Un repository par type. Il connaît sa route, son store et sa factory ; il
// ne connaît ni la vue ni le contrôleur. C'est le seul endroit d'un domaine
// où `api()` apparaît — la garde d'imports le vérifie.

import { get, post } from "../core/api.js";
import { defineStore } from "../core/store.js";
import { route } from "../core/endpoints.js";

export class Repository {
  /**
   * @param {object} spec  { name, factory, routes: { list, one, ... }, ttl, max }
   */
  constructor({ name, factory, routes = {}, ttl = 30000, max = 200 }) {
    if (!name) throw new Error("un repository doit être nommé");
    if (!factory) throw new Error(`repository ${name} : factory requise`);
    this.name = name;
    this.factory = factory;
    this.routes = routes;
    this.store = defineStore(name, { ttl, max });
  }

  /** Chemin d'une route nommée du domaine (clé de core/endpoints.js). */
  path(kind, params = {}) {
    const name = this.routes[kind];
    if (!name) throw new Error(`repository ${this.name} : route « ${kind} » non déclarée`);
    let p = route(name);
    for (const [k, v] of Object.entries(params)) p = p.replace(`:${k}`, encodeURIComponent(v));
    return p;
  }

  /** Liste hydratée, servie du cache si elle est fraîche. */
  async list(query = "") {
    return this.store.ensure(`list${query}`, async () =>
      this.factory.many(await get(this.path("list") + query)));
  }

  /** Une entité hydratée, servie du cache si elle est fraîche. */
  async one(id) {
    return this.store.ensure(`one:${id}`, async () =>
      this.factory.one(await get(this.path("one", { id }))));
  }

  /** Écriture : envoie, invalide le cache, rend la réponse hydratée si c'en est une. */
  async send(kind, data, params = {}) {
    const body = await post(this.path(kind, params), data);
    this.store.invalidate();
    return body;
  }

  /** Abonnement aux changements du domaine ; rend le désabonnement. */
  subscribe(fn) { return this.store.subscribe(fn); }
}
