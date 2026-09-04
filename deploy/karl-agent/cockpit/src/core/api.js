// core/api — l'unique porte vers le serveur. RM2889, L0.
//
// Comportement REPRIS de `api()` / `headers()` d'index.html — en-tête
// X-Karl-Token, corps JSON ou texte selon le Content-Type, erreur sur !ok
// avec le `error` du serveur ou « status statusText », et repli sur l'écran
// de login au 401. Un test compare les deux tant que la cohabitation dure.
//
// Ce qui change : plus de `document` ni de `CFG` globaux lus ici. Le module
// reçoit sa configuration (`configureApi`), ce qui le rend importable et
// testable sous node nu (C5) avec un `fetch` injecté.

import { ApiError } from "./errors.js";

const cfg = {
  authRequired: false,
  token: () => "",
  onUnauthorized: () => {},
  fetch: (...a) => globalThis.fetch(...a),
};

/** Configure le transport. Appelé une fois par boot.js, réappelable en test. */
export function configureApi(opts = {}) {
  Object.assign(cfg, opts);
  return cfg;
}

/** En-têtes d'une requête : ceux fournis, plus le jeton si l'auth est active. */
export function headers(extra) {
  const h = Object.assign({}, extra || {});
  if (cfg.authRequired && cfg.token()) h["X-Karl-Token"] = cfg.token();
  return h;
}

/**
 * Appel serveur. Rend le corps décodé ; lève un ApiError sur !ok.
 *
 * @param {string} path   chemin (venez-y par `route()` de core/endpoints.js)
 * @param {object} opts   options de fetch
 */
export async function api(path, opts) {
  opts = opts || {};
  opts.headers = headers(opts.headers);
  const r = await cfg.fetch(path, opts);
  const ct = (r.headers && r.headers.get && r.headers.get("content-type")) || "";
  const body = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    if (r.status === 401 && cfg.authRequired) cfg.onUnauthorized();
    const message = (body && body.error) || r.status + " " + r.statusText;
    throw new ApiError(r.status, message, {
      code: body && body.code, detail: body && body.detail, remedy: body && body.remedy,
    });
  }
  return body;
}

/** Raccourcis lisibles dans les repositories. */
export const get = (path) => api(path);
export const post = (path, data) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data ?? {}),
});
