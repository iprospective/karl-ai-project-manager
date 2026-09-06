// services/env.service — l'état du poste, tenu à jour par deux voies. RM2889, L5.
// La pile /refresh pousse les blocs `envcheck` et `vault` (RM2763) ; le diagnostic
// complet et les gestes du coffre sont des appels directs.
import { EnvRepository } from "./EnvRepository.js";

export class EnvService {
  constructor(repo = new EnvRepository()) { this.repo = repo; this.check = null; this.status = null; this.vault = null; }
  setBlock(kind, data) { if (kind === "envcheck") this.check = data; else if (kind === "vault") this.vault = data; return this; }
  async reloadCheck() { try { this.check = await this.repo.check(); } catch (e) { /* badge muet */ } return this.check; }
  async loadStatus(force) { if (force || !this.status) this.status = await this.repo.status(); return this.status; }
  async unlock(instance, password) {
    try { const r = await this.repo.unlock(instance, password); return { ok: !!r.ok, message: r.ok ? "Coffre déverrouillé" : "Échec : " + (r.detail || "mot de passe refusé") }; }
    catch (e) { return { ok: false, message: "Échec : " + e.message }; }
  }
  async sshAdd(key, passphrase) {
    try { const r = await this.repo.sshAdd(key, passphrase); return { ok: !!r.ok, message: r.ok ? "Clé chargée dans l'agent" : "Échec : " + (r.detail || "passphrase refusée") }; }
    catch (e) { return { ok: false, message: "Échec : " + e.message }; }
  }
}
