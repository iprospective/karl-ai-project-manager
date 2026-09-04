// boot — pont de cohabitation entre le monolithe et les modules. RM2889, L0.
//
// Le `<script>` historique d'index.html n'est pas un module : il ne peut pas
// `import`. Pendant toute la migration, le socle lui est donc exposé sur
// `window.karl`, en un seul point, et le monolithe s'en sert progressivement —
// c'est ce qui permet de migrer un domaine à la fois sans jamais casser les
// autres (§ 15.1).
//
// Ordre d'exécution : un module est différé, il s'exécute donc APRÈS le script
// inline. Le monolithe ne doit pas lire `window.karl` au chargement, mais dans
// ses gestes — ou attendre l'événement `karl:ready`.
//
// Ce pont disparaît au lot L6, quand plus rien d'inline ne subsiste.

import { esc, jarg, html, raw, isSafe, attrs } from "./core/html.js";
import { Store, defineStore, storeStats, resetStores } from "./core/store.js";
import { mount, on, domStats } from "./core/dom.js";
import { ROUTES, route, targetRoute } from "./core/endpoints.js";
import { api, get, post, configureApi } from "./core/api.js";
import { AppError, ApiError, asAppError } from "./core/errors.js";
import { Repository } from "./models/Repository.js";
import { Factory } from "./models/Factory.js";
import { EntityViewModel, withConso } from "./viewmodels/EntityViewModel.js";

// Le transport lit sa configuration dans les globaux du monolithe tant qu'il
// existe (CFG, token) — à la demande, jamais au chargement : CFG est rempli
// après le login. Le 401 reprend le geste historique : ré-afficher l'écran.
configureApi({
  get authRequired() { return !!(window.CFG && window.CFG.auth_required); },
  token: () => localStorage.getItem("karlToken") || "",
  onUnauthorized: () => {
    const g = document.getElementById("authgate");
    if (g) g.classList.add("show");
  },
});

const karl = Object.freeze({
  // rendu
  esc, jarg, html, raw, isSafe, attrs,
  // cache
  Store, defineStore, resetStores,
  // montage et cycle de vie
  mount, on,
  // routes nommées et transport
  ROUTES, route, targetRoute, api, get, post,
  // erreurs
  AppError, ApiError, asAppError,
  // classes de base
  Repository, Factory, EntityViewModel, withConso,
  /**
   * Ce que le front retient, en clair. Consultable depuis la console pendant
   * l'enquête RM2807 : `karl.stats()`. Devient un panneau d'interface en L1b.
   */
  stats() {
    const stores = storeStats();
    return {
      dom: domStats(),
      stores,
      entries: stores.reduce((n, s) => n + s.entries, 0),
      subscribers: stores.reduce((n, s) => n + s.subscribers, 0),
    };
  },
});

window.karl = karl;
window.dispatchEvent(new CustomEvent("karl:ready", { detail: karl }));
