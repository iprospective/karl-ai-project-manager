// services/launcher.service — l'état du lanceur (ticket résolu, projets connus, contexte client de ce navigateur). RM2889.
import { LauncherRepository } from "./LauncherRepository.js";
import { clientCtxList } from "./launcher.js";

export class LauncherService {
  constructor({ repo = new LauncherRepository(), storage = null } = {}) { this.repo = repo; this.storage = storage; this.resolved = null; this.projects = []; this.clientContext = this._get("karlClientCtx") || ""; }
  _get(k) { try { return this.storage ? this.storage.getItem(k) : null; } catch (e) { return null; } }
  _set(k, v) { try { if (this.storage) this.storage.setItem(k, v); } catch (e) { /* mode privé */ } }
  async resolve(rm) { if (!/^\d+$/.test(String(rm || ""))) { this.resolved = null; return null; } try { this.resolved = await this.repo.resolve(rm); } catch (e) { this.resolved = null; } return this.resolved; }
  async loadProjects() { this.projects = await this.repo.projects(); if (this.clientContext && clientCtxList(this.projects).indexOf(this.clientContext) < 0) this.clientContext = "";   // client disparu → tous
    return this.projects; }
  setClientContext(c) { this.clientContext = c || ""; this._set("karlClientCtx", this.clientContext); return this.clientContext; }
  spawn(body) { return this.repo.spawn(body); }
  createTicket(body) { return this.repo.createTicket(body); }
  async isRunning(rm) { try { return (await this.repo.running()).some(s => String(s.rm_id) === String(rm)); } catch (e) { return false; } }
}
