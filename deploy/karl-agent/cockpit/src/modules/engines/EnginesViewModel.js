// modules/engines/EnginesViewModel — le panneau Moteurs, décidé : deux familles, l'état de chacune, ce qui
// se met à jour, ce qui est bloqué par une session en cours. RM3069.
import { EntityViewModel } from "../../core/EntityViewModel.js";

/** e = { data: {catalogue, etats}, busy } */
export class EnginesViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.cat = (this.e.data || {}).catalogue || { engines: [], servers: [] }; this.etats = (this.e.data || {}).etats || []; }
  get empty() { return !(this.cat.engines || []).length && !(this.cat.servers || []).length; }
  etatDe(id) { return this.etats.find(x => x.id === id) || {}; }
  /** Deux portées possibles : « pour moi » (aucun privilège) et « pour tous » (sudo). Un outil posé par
   *  l'utilisateur est bien installé — l'ignorer parce qu'il n'est pas dans le PATH du démon serait faux. */
  static portee(s) { return s === "system" ? "pour tous" : "pour moi"; }
  /** Ce qu'on peut faire, portée par portée : mettre à jour là où c'est installé, installer ailleurs. */
  actions(r, e) {
    const cmds = r.cmds || {}, offertes = r.scopes || [];
    const out = [];
    for (const s of offertes) {
      const ici = e.installed && e.scope === s;
      if (ici && !e.update_available) continue;                 // à jour ici : rien à proposer
      const act = ici ? "update" : "install";
      if (!(cmds[s] || {})[act]) continue;
      out.push({ scope: s, act, cmd: cmds[s][act], primary: ici || !e.installed,
                 label: (act === "update" ? "mettre à jour " : "installer ") + EnginesViewModel.portee(s),
                 sudo: s === "system" });
    }
    return out;
  }
  ligne(r) {
    const e = this.etatDe(r.id);
    const sessions = (e.sessions || []).length;
    const actions = this.actions(r, e);
    return { id: r.id, label: r.label, bin: r.bin, note: r.note || "", config: r.config || "",
      providerType: r.provider_type || "", path: e.path || "",
      installed: !!e.installed, version: e.version || "", latest: e.latest || "",
      scope: e.scope || "", scopeLabel: e.scope ? EnginesViewModel.portee(e.scope) : "",
      updatable: !!e.update_available, service: e.service || "", sessions,
      busy: this.e.busy === r.id, actions,
      cmd: (actions.find(a => a.primary) || actions[0] || {}).cmd || "",
      state: !e.installed ? "absent"
             : (e.update_available ? "à mettre à jour" : "à jour") + " · " + EnginesViewModel.portee(e.scope),
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
