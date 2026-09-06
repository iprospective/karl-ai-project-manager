// controllers/auth.controller — l'authentification (RM2334) : écran de login plein-cadre (identifiants → jeton d'appareil, ou jeton partagé
// historique), cadenas de l'en-tête, carte « Authentification » (session, appareils), carte « Utilisateurs » (superadmin). RM2889.
//
// Hôtes : `gate` (#authgate : #auth-user, #auth-pass, #gate-err, #token, boutons), `card` (#authcard : #auth-session, #auth-me,
// #auth-devices, bouton), `users` (#userscard : #users-list, #nu-name, #nu-pass, bouton), `lock` (#lock). Le monolithe prête CFG, le
// toast, confirm/prompt, et ce qu'une connexion déclenche (santé + sessions, panneau « en cours »).
import { AuthService } from "./auth.service.js";
import { Me, Devices, Users } from "./Auth.view.js";
import { authState, deviceName, deviceRows, userRows } from "./auth.js";

export function mountAuth({ gate, card, users, lock } = {}, ctx = {}) {
  const svc = ctx.service || new AuthService({ storage: ctx.storage });
  const notify = ctx.notify || (() => {});
  const confirm = ctx.confirm || ((m) => window.confirm(m));
  const prompt = ctx.prompt || ((m) => window.prompt(m));
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const cfg = () => (ctx.cfg ? ctx.cfg() : null) || {};
  const q = (root, sel) => (root && root.querySelector ? root.querySelector(sel) : null);
  const el = { user: () => q(gate, "#auth-user"), pass: () => q(gate, "#auth-pass"), err: () => q(gate, "#gate-err"), token: () => q(gate, "#token"),
    session: () => q(card, "#auth-session"), me: () => q(card, "#auth-me"), devices: () => q(card, "#auth-devices"), list: () => q(users, "#users-list"), nuName: () => q(users, "#nu-name"), nuPass: () => q(users, "#nu-pass") };
  const show = (n, on) => { if (n) n.style.display = on ? "" : "none"; };
  const fail = (e) => notify(e.message, true);
  const afterAuth = () => { if (ctx.afterAuth) ctx.afterAuth(); };

  /** L'état connecté gouverne tout : écran de login, cadenas, carte de session, carte des comptes. */
  function render() {
    const c = cfg(); const st = authState({ required: c.auth_required, token: svc.token(), user: svc.user(), admin: svc.admin(), loginEnabled: c.login_enabled });
    if (gate && gate.classList) gate.classList.toggle("show", st.gateShown);
    if (!st.required) return st;
    if (!st.logged) { const u = el.user(); if (u && u.focus) later(() => u.focus(), 0); }
    show(el.session(), st.sessionShown);
    if (lock) lock.textContent = st.lockText;
    show(users, st.usersShown);
    if (st.logged) { const me = el.me(); if (me) me.innerHTML = String(Me(svc.user(), svc.admin())); loadDevices(); if (st.usersShown) loadUsers(); }
    return st;
  }
  /** 401 : jeton invalide/révoqué/expiré → l'écran de login revient, quel que soit l'état mémorisé. */
  function showGate() { if (gate && gate.classList) gate.classList.add("show"); }
  /** À l'init, une fois CFG connu : carte visible si l'auth est active, jeton historique pré-rempli, whoami si la session est inconnue. */
  async function boot() {
    const c = cfg();
    if (!c.auth_required) { render(); return; }
    show(card, true);
    const orphan = svc.token() && !svc.user();
    if (orphan && el.token()) el.token().value = svc.token();
    render();
    if (orphan) { try { if (await svc.whoami()) render(); } catch (e) { /* jeton partagé ou invalide : l'écran reste */ } }
  }
  async function login() {
    const user = ((el.user() || {}).value || "").trim(), pass = (el.pass() || {}).value || "";
    if (!user || !pass) { notify("utilisateur et mot de passe requis", true); return; }
    try {
      const u = await svc.login(user, pass, deviceName(ctx.ua || (typeof navigator !== "undefined" ? navigator.userAgent : "")));
      if (el.pass()) el.pass().value = "";                                          // jamais conservé
      if (el.err()) el.err().textContent = "";
      notify("Connecté : " + u); render(); afterAuth(); if (ctx.switchPanel) ctx.switchPanel("running");
    } catch (e) { if (el.err()) el.err().textContent = e.message; fail(e); }
  }
  function saveToken() { svc.saveToken((el.token() || {}).value || ""); notify("Token mémorisé"); render(); afterAuth(); }
  async function logout() { await svc.logout(); notify("Déconnecté — appareil révoqué"); render(); }
  async function loadDevices() { const d = el.devices(); if (!d) return; try { d.innerHTML = String(Devices(deviceRows(await svc.devices()))); } catch (e) { /* silencieux : la carte reste utilisable */ } }
  async function revoke(id, isCurrent) { if (isCurrent) return logout(); try { await svc.revoke(id); notify("Appareil révoqué"); loadDevices(); } catch (e) { fail(e); } }
  async function loadUsers() { const l = el.list(); if (!l) return; try { l.innerHTML = String(Users(userRows(await svc.users()))); } catch (e) { fail(e); } }
  async function createUser() {
    const user = ((el.nuName() || {}).value || "").trim(), pass = (el.nuPass() || {}).value || "";
    try { await svc.create(user, pass); if (el.nuName()) el.nuName().value = ""; if (el.nuPass()) el.nuPass().value = ""; notify("Compte créé : " + user); loadUsers(); } catch (e) { fail(e); }
  }
  async function toggleUser(user, disabled) {
    if (disabled && !confirm("Désactiver " + user + " ? Ses appareils seront révoqués.")) return;
    try { await svc.toggle(user, disabled); notify(user + (disabled ? " désactivé" : " réactivé")); loadUsers(); } catch (e) { fail(e); }
  }
  async function resetUserPw(user) {
    const pass = prompt("Nouveau mot de passe pour " + user + " (≥ 8 car.) — ses appareils seront révoqués :");
    if (!pass) return;
    try { await svc.resetPw(user, pass); notify("Mot de passe changé pour " + user); loadUsers(); } catch (e) { fail(e); }
  }
  async function deleteUser(user) {
    if (!confirm("Supprimer le compte " + user + " ? (appareils révoqués)")) return;
    try { await svc.remove(user); notify("Compte supprimé : " + user); loadUsers(); } catch (e) { fail(e); }
  }
  const disposers = [];
  const listen = (node, type, fn) => { if (node && node.addEventListener) { node.addEventListener(type, fn); disposers.push(() => node.removeEventListener(type, fn)); } };
  const act = (e) => (e.target && e.target.closest ? e.target.closest("[data-action]") : null);
  listen(gate, "click", (e) => { const n = act(e); if (!n) return; if (n.dataset.action === "login") login(); else if (n.dataset.action === "save-token") saveToken(); });
  listen(gate, "keydown", (e) => { const id = (e.target && e.target.id) || ""; if (e.key !== "Enter") return; if (id === "auth-pass") login(); else if (id === "auth-user" && el.pass() && el.pass().focus) el.pass().focus(); });
  listen(card, "click", (e) => { const n = act(e); if (!n) return; if (n.dataset.action === "logout") logout(); else if (n.dataset.action === "revoke") revoke(n.dataset.id, n.dataset.current === "1"); });
  listen(users, "click", (e) => { const n = act(e); if (!n) return; const a = n.dataset.action, u = n.dataset.user;
    if (a === "create") createUser(); else if (a === "user-toggle") toggleUser(u, n.dataset.disabled === "1"); else if (a === "user-pw") resetUserPw(u); else if (a === "user-del") deleteUser(u); });
  return { render, boot, showGate, login, logout, saveToken, loadDevices, loadUsers, revoke, createUser, toggleUser, resetUserPw, deleteUser,
    token: () => svc.token(), user: () => svc.user(), admin: () => svc.admin(), logged: () => svc.logged(), svc,
    unmount() { disposers.forEach(d => d()); disposers.length = 0; } };
}
