#!/usr/bin/env node
// Tests du script injecté par l'app Android (RM2331) — app/src/main/assets/karl-boot.js,
// exécuté sous node contre le VRAI AuthService du cockpit : les clés d'auth sont servies
// depuis la mémoire (jamais écrites dans le localStorage réel), la connexion / déconnexion
// faite dans le cockpit remonte à l'app, les autres clés et le sessionStorage passent.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const vm = require("vm");
const SRC = fs.readFileSync(path.join(__dirname, "app/src/main/assets/karl-boot.js"), "utf8");
const COCKPIT = path.join(__dirname, "../cockpit");

// Un Storage à la manière du navigateur : méthodes sur le PROTOTYPE, état par instance.
function world(preset) {
  class Storage {
    constructor(d) { this._d = Object.assign({}, d); }
    getItem(k) { return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; }
    setItem(k, v) { this._d[k] = String(v); }
    removeItem(k) { delete this._d[k]; }
  }
  const posted = [];
  const w = { Storage, localStorage: new Storage(preset), sessionStorage: new Storage(), KarlApp: { postMessage: (s) => posted.push(JSON.parse(s)) } };
  w.window = w;
  return { w, posted, ctx: vm.createContext(w) };
}
const mem = { karlToken: "T0", karlDeviceId: "d0", karlUser: "bob", karlAdmin: "0" };
// split/join = String.replace de Kotlin (TOUTES les occurrences du marqueur)
const boot = (ctx, m) => vm.runInContext(SRC.split("__MEM__").join(JSON.stringify(m || mem)), ctx);

(async () => {
  const { AuthService } = await import(path.join(COCKPIT, "src/modules/auth/auth.service.js"));
  const { AUTH_KEYS } = await import(path.join(COCKPIT, "src/modules/auth/auth.js"));
  assert.deepStrictEqual(Object.keys(mem), AUTH_KEYS, "le script sert EXACTEMENT les clés d'auth du cockpit");

  // — service : le cockpit se croit connecté, rien n'est sur disque —
  let { w, posted, ctx } = world({ karlToken: "RESIDU", theme: "dark" });
  boot(ctx);
  assert.strictEqual(w.localStorage._d.karlToken, undefined, "copie résiduelle du jeton purgée au démarrage");
  assert.strictEqual(w.localStorage._d.theme, "dark", "les autres clés du cockpit ne sont pas touchées");
  let svc = new AuthService({ storage: w.localStorage, repo: {} });
  assert(svc.logged() && svc.token() === "T0" && svc.user() === "bob" && !svc.admin() && svc.deviceId() === "d0", "le cockpit lit la session servie par l'app");
  w.localStorage.setItem("theme", "light"); w.sessionStorage.setItem("karlToken", "S");
  assert.strictEqual(w.localStorage.getItem("theme"), "light"); assert.strictEqual(w.sessionStorage.getItem("karlToken"), "S", "sessionStorage non intercepté");
  assert.deepStrictEqual(posted, [], "rien de signalé tant que rien ne change");
  console.log("✓ lecture : session servie depuis la mémoire, résidu purgé, autres clés intactes");

  // — whoami (même jeton) : pas de faux login —
  svc.repo = { async whoami() { return { mode: "device", user: "bob", admin: true, device_id: "d0" }; } };
  assert(await svc.whoami()); assert(svc.admin());
  assert.deepStrictEqual(posted, [], "whoami réécrit les clés avec le MÊME jeton : aucun login signalé");

  // — déconnexion dans le cockpit —
  const revoked = []; svc.repo = { async revokeDevice(id) { revoked.push(id); } };
  await svc.logout();
  assert.deepStrictEqual(revoked, ["d0"]); assert.deepStrictEqual(posted, [{ type: "logout" }], "logout signalé une fois");
  assert(!svc.logged() && svc.token() === "", "le cockpit se voit déconnecté");
  console.log("✓ whoami sans faux login ; logout du cockpit → message logout");

  // — reconnexion dans la carte de login du cockpit —
  svc.repo = { async login(u, p, d) { return { token: "T1", device_id: "d1", user: u, admin: true }; } };
  await svc.login("alice", "pw", "Chrome / Android");
  assert.deepStrictEqual(posted[1], { type: "login", karlToken: "T1", karlDeviceId: "d1", karlUser: "alice", karlAdmin: "1" }, "login complet signalé");
  assert.strictEqual(posted.length, 2, "un seul message pour les 4 clés");
  assert.deepStrictEqual(Object.keys(w.localStorage._d).filter(k => AUTH_KEYS.includes(k)), [], "le nouveau jeton non plus n'est pas écrit sur disque");
  assert.strictEqual(JSON.stringify(w.localStorage._d).includes("pw"), false, "mot de passe jamais stocké");
  console.log("✓ login du cockpit → message login unique, jeton gardé en mémoire");

  // — double injection (nouveau document dans le même contexte) : idempotent —
  boot(ctx, { karlToken: "X", karlDeviceId: "", karlUser: "", karlAdmin: "0" });
  assert.strictEqual(w.localStorage.getItem("karlToken"), "T1", "second passage ignoré (garde __karlApp)");

  // — hors app (pas de KarlApp) : le script ne plante pas —
  ({ w, ctx } = world());
  delete w.KarlApp;
  boot(ctx);
  w.localStorage.removeItem("karlToken");
  assert.strictEqual(w.localStorage.getItem("karlToken"), null);
  console.log("✓ injection idempotente ; sans canal KarlApp, aucune erreur");
  console.log("OK test_karl_boot");
})().catch((e) => { console.error(e); process.exit(1); });
