// modules/engines/EnginesViewModel — le panneau Moteurs, décidé : deux familles, l'état de chacune, ce qui
// se met à jour, ce qui est bloqué par une session en cours. RM3069.
import { EntityViewModel } from "../../core/EntityViewModel.js";

/** e = { data: {catalogue, etats}, busy } */
export class EnginesViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.cat = (this.e.data || {}).catalogue || { engines: [], servers: [] }; this.etats = (this.e.data || {}).etats || []; }
  get empty() { return !(this.cat.engines || []).length && !(this.cat.servers || []).length; }
  etatDe(id) { return this.etats.find(x => x.id === id) || {}; }
  ligne(r) {
    const e = this.etatDe(r.id);
    const sessions = (e.sessions || []).length;
    return { id: r.id, label: r.label, bin: r.bin, sudo: !!r.sudo, note: r.note || "", config: r.config || "",
      providerType: r.provider_type || "",
      installed: !!e.installed, version: e.version || "", latest: e.latest || "",
      updatable: !!e.update_available, service: e.service || "", sessions,
      busy: this.e.busy === r.id,
      cmd: e.installed ? (r.update_cmd || "") : (r.install_cmd || ""),
      action: e.installed ? "update" : "install",
      state: !e.installed ? "absent" : (e.update_available ? "à mettre à jour" : "à jour"),
      cls: !e.installed ? "" : (e.update_available ? "wait" : "ok"),
      warn: sessions && e.update_available ? `${sessions} session(s) en cours : la mise à jour les couperait` : "" };
  }
  get groupes() {
    return [{ key: "engines", label: "Moteurs de session", help: "les clients qui tiennent une session d'agent",
              rows: (this.cat.engines || []).map(r => this.ligne(r)) },
            { key: "servers", label: "Serveurs de modèles", help: "ils ne tiennent pas de session : ils servent les modèles, et se déclarent ensuite comme fournisseurs de l'axe « modèles de travail »",
              rows: (this.cat.servers || []).map(r => this.ligne(r)) }];
  }
  get count() { const n = this.etats.filter(e => e.installed).length; return `${n} installé(s) sur ${this.etats.length}`; }
}
