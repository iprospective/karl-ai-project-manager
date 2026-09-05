// services/auth.service — la session de ce navigateur (jeton d'appareil, utilisateur, admin) et les gestes d'auth (RM2334). Aucun DOM. RM2889.
import { AuthRepository } from "../models/auth/AuthRepository.js";
import { AUTH_KEYS } from "../models/auth/auth.js";

export class AuthService {
  constructor({ repo = new AuthRepository(), storage = null } = {}) { this.repo = repo; this.storage = storage; }
  _get(k) { try { return this.storage ? this.storage.getItem(k) : null; } catch (e) { return null; } }
  _set(k, v) { try { if (this.storage) this.storage.setItem(k, v); } catch (e) { /* mode privé */ } }
  _del(k) { try { if (this.storage) this.storage.removeItem(k); } catch (e) { /* mode privé */ } }
  token() { return this._get("karlToken") || ""; }
  user() { return this._get("karlUser") || ""; }
  admin() { return this._get("karlAdmin") === "1"; }
  deviceId() { return this._get("karlDeviceId") || ""; }
  logged() { return !!(this.token() && this.user()); }
  /** Mode historique : un jeton partagé — il n'appartient à aucun appareil ni utilisateur connu. */
  saveToken(t) { this._set("karlToken", String(t || "").trim()); ["karlDeviceId", "karlUser", "karlAdmin"].forEach(k => this._del(k)); }
  /** RM2334 : identifiants → jeton d'appareil, jamais de mot de passe stocké. Rend l'utilisateur connecté. */
  async login(user, pass, deviceName) {
    const r = await this.repo.login(user, pass, deviceName);
    this._set("karlToken", r.token); this._set("karlDeviceId", r.device_id); this._set("karlUser", r.user); this._set("karlAdmin", r.admin ? "1" : "0");
    return r.user;
  }
  /** Déconnexion = révocation de CET appareil (silencieuse si le serveur ne répond pas), puis oubli local. */
  async logout() {
    const did = this.deviceId();
    if (did) { try { await this.repo.revokeDevice(did); } catch (e) { /* jeton déjà invalide : on oublie quand même */ } }
    AUTH_KEYS.forEach(k => this._del(k));
  }
  /** Jeton présent mais session inconnue (stockage restauré) : whoami resynchronise sans re-login. Vrai si c'était un jeton d'appareil. */
  async whoami() {
    const w = await this.repo.whoami();
    if (!(w && w.mode === "device")) return false;
    this._set("karlUser", w.user || ""); this._set("karlAdmin", w.admin ? "1" : "0"); if (w.device_id) this._set("karlDeviceId", w.device_id);
    return true;
  }
  async devices() { return ((await this.repo.devices()) || {}).devices || []; }
  revoke(id) { return this.repo.revokeDevice(id); }
  async users() { return ((await this.repo.users()) || {}).users || []; }
  create(user, pass) { return this.repo.createUser(user, pass); }
  toggle(user, disabled) { return this.repo.updateUser(user, { disabled: !!disabled }); }
  resetPw(user, pass) { return this.repo.updateUser(user, { pass }); }
  remove(user) { return this.repo.deleteUser(user); }
}
