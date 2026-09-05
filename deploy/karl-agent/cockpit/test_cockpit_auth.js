#!/usr/bin/env node
// Tests de l'authentification migrée (RM2889) — porte RM2334 : login identifiants → jeton d'appareil (jamais de mot de passe stocké), écran de
// login plein-cadre, jeton partagé historique, whoami sur session inconnue, appareils (révoquer / celui-ci = déconnexion), comptes (superadmin).
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
function fakeEl(id, extra) { const L = []; let inner = ""; const self = Object.assign({ id, style: {}, value: "", dataset: {}, kids: {}, textContent: "", focused: 0, focus() { self.focused++; }, cl: new Set(), classList: { toggle(c, v) { v ? self.cl.add(c) : self.cl.delete(c); }, add(c) { self.cl.add(c); }, remove(c) { self.cl.delete(c); }, contains(c) { return self.cl.has(c); } },
  get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, querySelector(sel) { return self.kids[sel] || null; }, addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, target, extra2) { for (const [t, f] of [...L]) if (t === type) await f(Object.assign({ target, preventDefault() {} }, extra2 || {})); await new Promise(r => setTimeout(r, 0)); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {} }); await new Promise(r => setTimeout(r, 0)); return n; } }, extra || {}); return self; }
(async () => {
  const M = await import(path.join(DIR, "src/models/auth/auth.js"));
  const { AuthService } = await import(path.join(DIR, "src/services/auth.service.js"));
  const V = await import(path.join(DIR, "src/views/auth/Auth.view.js"));
  const { mountAuth } = await import(path.join(DIR, "src/controllers/auth.controller.js"));

  // — modèle —
  assert.strictEqual(M.deviceName("Mozilla/5.0 (X11; Linux x86_64) Firefox/120"), "Firefox / Linux"); assert.strictEqual(M.deviceName("Mozilla/5.0 (iPhone) AppleWebKit Safari/604"), "Safari / iOS");
  assert.strictEqual(M.deviceName("Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537 Edg/120"), "Edge / Windows"); assert.strictEqual(M.deviceName("Mozilla/5.0 (Macintosh) Chrome/120 Safari/537"), "Chrome / macOS"); assert.strictEqual(M.deviceName("curl"), "navigateur / Linux"); assert.strictEqual(M.deviceName("Android"), "navigateur / Android");
  let st = M.authState({ required: true, token: "t", user: "bob", admin: true, loginEnabled: true }); assert(st.logged && !st.gateShown && st.sessionShown && st.lockText === "🔓 bob (admin)" && st.usersShown, "connecté admin : tout ouvert");
  st = M.authState({ required: true, token: "t", user: "", admin: false }); assert(!st.logged && st.gateShown && st.lockText === "🔒 auth requise" && !st.usersShown, "jeton sans utilisateur : pas connecté → écran de login");
  st = M.authState({ required: true, token: "t", user: "bob", admin: true, loginEnabled: false }); assert(st.logged && !st.usersShown, "comptes : seulement si le login par identifiants est activé"); st = M.authState({ required: false }); assert(!st.required && !st.gateShown, "auth inactive : jamais d'écran");
  assert.deepStrictEqual(M.deviceRows([{ device_id: 7, device_name: "Firefox / Linux", current: true, user: "bob", last_seen: "2026-09-05T10:11:12Z" }, {}]), [{ id: "7", name: "Firefox / Linux", current: true, user: "bob", seen: "2026-09-05T10:11" }, { id: "undefined", name: "appareil", current: false, user: "", seen: "" }]);
  assert.deepStrictEqual(M.userRows([{ user: "a", disabled: true, devices: 2 }, { user: "b" }]), [{ user: "a", disabled: true, devices: 2, toggleLabel: "réactiver" }, { user: "b", disabled: false, devices: 0, toggleLabel: "désactiver" }]); assert.deepStrictEqual(M.AUTH_KEYS, ["karlToken", "karlDeviceId", "karlUser", "karlAdmin"]);
  console.log("✓ modèle (RM2334) : nom d'appareil, état connecté/déconnecté, lignes appareils et comptes");

  // — vues —
  let h = String(V.Me("bo<b>", true)); assert(/Connecté : <b>bo&lt;b&gt;<\/b> <span class="pill">superadmin<\/span>/.test(h)); assert(!/superadmin/.test(String(V.Me("bob", false))));
  h = String(V.Devices(M.deviceRows([{ device_id: "d1", device_name: "Firefox / Linux", current: true, user: "bob", last_seen: "2026-09-05T10:11" }, { device_id: "d2", device_name: "Chrome / Android", user: "bob" }])));
  assert(/Appareils enregistrés/.test(h) && /Firefox \/ Linux ← celui-ci/.test(h) && /data-action="revoke" data-id="d1" data-current="1"/.test(h) && /data-action="revoke" data-id="d2" data-current=""/.test(h) && !/onclick/.test(h), "appareils : celui-ci marqué, gestes en data-action"); assert.strictEqual(String(V.Devices([])), "");
  h = String(V.Users(M.userRows([{ user: "al<i>ce", disabled: true, devices: 2 }]))); assert(/al&lt;i&gt;ce <span class="pill">désactivé<\/span>/.test(h) && /2 appareil\(s\)/.test(h) && /data-action="user-toggle" data-user="al&lt;i&gt;ce" data-disabled="">réactiver</.test(h) && /data-action="user-pw"/.test(h) && /data-action="user-del"/.test(h), "comptes : échappés, gestes en data-action");
  assert(/data-disabled="1">désactiver</.test(String(V.Users(M.userRows([{ user: "b" }])))) && /aucun compte normal/.test(String(V.Users([]))));
  console.log("✓ vues : session, appareils, comptes — échappement, data-action, aucun on*");

  // — service —
  const store = { d: {}, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); }, removeItem(k) { delete this.d[k]; } };
  const calls = []; let who = { mode: "device", user: "bob", admin: true, device_id: "d1" };
  const repo = { async login(u, p, d) { calls.push(["login", u, p, d]); if (p === "ko") throw new Error("identifiants refusés"); return { token: "T1", device_id: "d1", user: u, admin: u === "root" }; }, async whoami() { calls.push(["whoami"]); return who; },
    async devices() { calls.push(["devices"]); return { devices: [{ device_id: "d1", current: true }] }; }, async revokeDevice(id) { calls.push(["revoke", id]); if (id === "ko") throw new Error("déjà révoqué"); return {}; }, async users() { calls.push(["users"]); return { users: [{ user: "a" }] }; },
    async createUser(u, p) { calls.push(["create", u, p]); return {}; }, async updateUser(u, b) { calls.push(["update", u, b]); return {}; }, async deleteUser(u) { calls.push(["delete", u]); return {}; } };
  const svc = new AuthService({ repo, storage: store });
  assert(svc.token() === "" && !svc.logged()); svc.saveToken("  shared "); assert(store.d.karlToken === "shared" && !svc.logged(), "jeton partagé : mémorisé, sans utilisateur");
  store.d.karlUser = "x"; store.d.karlDeviceId = "d0"; svc.saveToken("shared2"); assert(store.d.karlUser === undefined && store.d.karlDeviceId === undefined, "un jeton partagé oublie l'appareil et l'utilisateur");
  assert.strictEqual(await svc.login("root", "pw", "Firefox / Linux"), "root"); assert.deepStrictEqual(calls[calls.length - 1], ["login", "root", "pw", "Firefox / Linux"]); assert(store.d.karlToken === "T1" && store.d.karlDeviceId === "d1" && store.d.karlUser === "root" && store.d.karlAdmin === "1" && svc.logged() && svc.admin(), "connecté : jeton d'appareil, utilisateur, admin");
  assert(!Object.values(store.d).includes("pw"), "le mot de passe n'est JAMAIS stocké"); await assert.rejects(svc.login("bob", "ko", "x"));
  await svc.logout(); assert.deepStrictEqual(calls[calls.length - 1], ["revoke", "d1"]); assert(Object.keys(store.d).length === 0 && !svc.logged(), "déconnexion : appareil révoqué, tout oublié");
  store.d.karlToken = "T2"; store.d.karlDeviceId = "ko"; await svc.logout(); assert(Object.keys(store.d).length === 0, "révocation refusée : on oublie quand même");
  store.d.karlToken = "T3"; assert.strictEqual(await svc.whoami(), true); assert(store.d.karlUser === "bob" && store.d.karlAdmin === "1" && store.d.karlDeviceId === "d1", "whoami resynchronise une session inconnue"); who = { mode: "shared" }; store.d.karlUser = undefined; delete store.d.karlUser; assert.strictEqual(await svc.whoami(), false, "jeton partagé : rien à resynchroniser");
  assert.deepStrictEqual(await svc.devices(), [{ device_id: "d1", current: true }]); assert.deepStrictEqual(await svc.users(), [{ user: "a" }]); await svc.create("c", "p"); await svc.toggle("c", true); await svc.resetPw("c", "np"); await svc.remove("c");
  assert.deepStrictEqual(calls.slice(-4), [["create", "c", "p"], ["update", "c", { disabled: true }], ["update", "c", { pass: "np" }], ["delete", "c"]]);
  console.log("✓ service : jeton partagé, login sans mot de passe stocké, déconnexion = révocation, whoami, appareils, comptes");

  // — contrôleur —
  const gate = fakeEl("authgate"), card = fakeEl("authcard"), users = fakeEl("userscard"), lock = fakeEl("lock");
  const inUser = fakeEl("auth-user"), inPass = fakeEl("auth-pass"), err = fakeEl("gate-err"), tok = fakeEl("token"), session = fakeEl("auth-session"), me = fakeEl("auth-me"), devs = fakeEl("auth-devices"), list = fakeEl("users-list"), nuName = fakeEl("nu-name"), nuPass = fakeEl("nu-pass");
  Object.assign(gate.kids, { "#auth-user": inUser, "#auth-pass": inPass, "#gate-err": err, "#token": tok }); Object.assign(card.kids, { "#auth-session": session, "#auth-me": me, "#auth-devices": devs }); Object.assign(users.kids, { "#users-list": list, "#nu-name": nuName, "#nu-pass": nuPass });
  card.style.display = "none"; users.style.display = "none";
  const st2 = { d: {}, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); }, removeItem(k) { delete this.d[k]; } };
  const ev = []; let cfg = { auth_required: true, login_enabled: true }; let ok = true; let answer = "newpw"; who = { mode: "device", user: "bob", admin: true, device_id: "d1" };
  const svc2 = new AuthService({ repo, storage: st2 });
  const ctr = mountAuth({ gate, card, users, lock }, { service: svc2, cfg: () => cfg, notify: (m, e) => ev.push(["toast", m, !!e]), confirm: (m) => { ev.push(["confirm", m]); return ok; }, prompt: (m) => { ev.push(["prompt", m]); return answer; }, later: (fn) => fn(), ua: "Mozilla/5.0 (X11; Linux) Firefox/1", afterAuth: () => ev.push("after"), switchPanel: (n) => ev.push(["panel", n]) });
  // boot sans jeton : carte visible, écran de login, focus utilisateur, cadenas
  await ctr.boot(); assert(card.style.display === "" && gate.cl.has("show") && inUser.focused === 1 && lock.textContent === "🔒 auth requise" && session.style.display === "none" && users.style.display === "none", "auth requise sans jeton : écran de login, carte visible, comptes masqués");
  // login par Entrée dans le mot de passe ; Entrée dans l'utilisateur → focus mot de passe
  await gate.fire("keydown", inUser, { key: "Enter" }); assert.strictEqual(inPass.focused, 1); inUser.value = " root "; inPass.value = "pw"; calls.length = 0; ev.length = 0; await gate.fire("keydown", inPass, { key: "Enter" });
  assert.deepStrictEqual(calls[0], ["login", "root", "pw", "Firefox / Linux"]); assert(inPass.value === "" && st2.d.karlToken === "T1" && !gate.cl.has("show") && lock.textContent === "🔓 root (admin)" && session.style.display === "" && users.style.display === "" && /Connecté : <b>root<\/b>/.test(me.innerHTML), "connecté : mot de passe effacé, écran levé, cadenas, cartes");
  assert(ev.some(x => x[0] === "toast" && x[1] === "Connecté : root") && ev.includes("after") && ev.some(x => x[0] === "panel" && x[1] === "running"), "santé + sessions relancées, panneau « en cours »"); assert(/data-action="revoke" data-id="d1" data-current="1"/.test(devs.innerHTML) && /data-action="user-toggle" data-user="a"/.test(list.innerHTML), "appareils et comptes chargés");
  // identifiants refusés / vides
  ev.length = 0; inUser.value = "bob"; inPass.value = "ko"; await gate.click("login"); assert(err.textContent === "identifiants refusés" && ev.some(x => x[0] === "toast" && x[2]), "refus : l'erreur s'affiche dans l'écran"); ev.length = 0; inPass.value = ""; await gate.click("login"); assert(ev.some(x => x[1] === "utilisateur et mot de passe requis" && x[2]));
  // appareils : révoquer un autre / celui-ci = déconnexion ; comptes
  calls.length = 0; ev.length = 0; await card.click("revoke", { id: "d9", current: "" }); assert.deepStrictEqual(calls[0], ["revoke", "d9"]); assert(ev.some(x => x[1] === "Appareil révoqué") && calls.some(c => c[0] === "devices"));
  calls.length = 0; ev.length = 0; ok = false; await users.click("user-toggle", { user: "a", disabled: "1" }); assert(ev.some(x => x[0] === "confirm" && /Désactiver a \?/.test(x[1])) && !calls.some(c => c[0] === "update"), "désactiver demande confirmation"); ok = true; await users.click("user-toggle", { user: "a", disabled: "" }); assert(calls.some(c => c[0] === "update" && c[2].disabled === false) && ev.some(x => x[1] === "a réactivé"), "réactiver : sans confirmation");
  calls.length = 0; await users.click("user-pw", { user: "a" }); assert(calls.some(c => c[0] === "update" && c[2].pass === "newpw")); answer = ""; calls.length = 0; await users.click("user-pw", { user: "a" }); assert(!calls.some(c => c[0] === "update"), "mot de passe vide : rien");
  calls.length = 0; ev.length = 0; await users.click("user-del", { user: "a" }); assert(ev.some(x => x[0] === "confirm" && /Supprimer le compte a/.test(x[1])) && calls.some(c => c[0] === "delete" && c[1] === "a"));
  nuName.value = " neo "; nuPass.value = "secret"; calls.length = 0; ev.length = 0; await users.click("create"); assert(calls.some(c => c[0] === "create" && c[1] === "neo" && c[2] === "secret") && nuName.value === "" && nuPass.value === "" && ev.some(x => x[1] === "Compte créé : neo"));
  // déconnexion depuis la carte (= révocation de cet appareil), puis jeton partagé
  calls.length = 0; ev.length = 0; await card.click("logout"); assert(calls.some(c => c[0] === "revoke" && c[1] === "d1") && Object.keys(st2.d).length === 0 && gate.cl.has("show") && lock.textContent === "🔒 auth requise", "déconnecté : appareil révoqué, écran de login");
  tok.value = " shared "; ev.length = 0; await gate.click("save-token"); assert(st2.d.karlToken === "shared" && ev.some(x => x[1] === "Token mémorisé") && ev.includes("after") && gate.cl.has("show"), "jeton partagé : mémorisé, santé relancée — l'écran reste (aucun utilisateur connu)");
  // boot avec un jeton orphelin : pré-rempli, whoami resynchronise ; boot auth inactive : écran levé
  who = { mode: "device", user: "bob", admin: false, device_id: "d5" }; await ctr.boot(); assert(tok.value === "shared" && st2.d.karlUser === "bob" && !gate.cl.has("show") && lock.textContent === "🔓 bob" && users.style.display === "none", "jeton présent, session inconnue : whoami la restaure ; non admin → pas de comptes");
  ctr.showGate(); assert(gate.cl.has("show"), "401 : l'écran revient"); cfg = { auth_required: false }; await ctr.boot(); assert(!gate.cl.has("show"), "auth inactive : jamais d'écran");
  ctr.unmount(); assert.strictEqual(gate.listenerCount + card.listenerCount + users.listenerCount, 0, "unmount libère tout");
  console.log("✓ contrôleur : boot, login (Entrée, refus, vide), cartes, appareils, comptes, déconnexion, jeton partagé, whoami, 401");

  // — hôtes et ponts dans index.html —
  ["authgate", "auth-user", "auth-pass", "gate-err", "token", "authcard", "auth-session", "auth-me", "auth-devices", "userscard", "users-list", "nu-name", "nu-pass", "lock"].forEach(id => assert(html.includes('id="' + id + '"'), "hôte manquant : " + id));
  const gateHtml = html.slice(html.indexOf('<div id="authgate">'), html.indexOf("<header>")); assert(!/\son\w+=/.test(gateHtml) && /data-action="login"/.test(gateHtml) && /data-action="save-token"/.test(gateHtml), "l'écran de login : plus de on*, gestes en data-action");
  const cardsHtml = html.slice(html.indexOf('id="authcard"'), html.indexOf('id="voicecard"')); assert(!/\son\w+=/.test(cardsHtml) && /data-action="logout"/.test(cardsHtml) && /data-action="create"/.test(cardsHtml), "les cartes : idem");
  assert(/function authBoot\(\) \{ karlCall\("auth", "boot"\); \}/.test(html) && /^\s+authBoot\(\);/m.test(html), "pont authBoot appelé par l'init"); assert(!/function (login|logout|renderAuth|loadDevices|loadUsers|createUser|saveToken|deviceName)\(/.test(html), "plus de logique d'auth dans le monolithe");
  assert(/token: \(\) => auth\.token\(\)/.test(fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8")), "le terminal lit le jeton sur le contrôleur");
  console.log("✓ hôtes sans on*, pont authBoot, monolithe vidé de l'auth");
  console.log("\nTous les tests de l'authentification passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
