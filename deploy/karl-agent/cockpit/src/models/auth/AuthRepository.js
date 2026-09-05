// models/auth/AuthRepository — /auth/login, /auth/whoami, /auth/devices, /auth/users (RM2334). RM2889.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { api, get, post } from "../../core/api.js";

const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export class AuthRepository extends Repository {
  constructor() { super({ name: "auth", ttl: 1000, max: 1, factory: new Factory({ type: "auth" }), routes: { login: "auth.login", whoami: "auth.whoami", devices: "auth.devices", users: "auth.users" } }); }
  /** Identifiants → jeton d'appareil ; le mot de passe ne fait que passer. */
  login(user, pass, device_name) { return post(this.path("login"), { user, pass, device_name }); }
  whoami() { return get(this.path("whoami")); }
  devices() { return get(this.path("devices")); }
  revokeDevice(id) { return api(this.path("devices") + "/" + encodeURIComponent(id), { method: "DELETE" }); }
  users() { return get(this.path("users")); }
  createUser(user, pass) { return post(this.path("users"), { user, pass }); }
  updateUser(user, body) { return api(this.path("users") + "/" + encodeURIComponent(user), json("PUT", body)); }
  deleteUser(user) { return api(this.path("users") + "/" + encodeURIComponent(user), { method: "DELETE" }); }
}
