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
      // RM3097 : présent sur la machine, mais dans le home d'un AUTRE — ce n'est pas installé POUR VOUS
      elsewhere: !!e.installed_elsewhere, owner: e.owner || "",
      scope: e.scope || "", scopeLabel: e.scope ? EnginesViewModel.portee(e.scope) : "",
      updatable: !!e.update_available, service: e.service || "", sessions,
      busy: this.e.busy === r.id, actions,
      cmd: (actions.find(a => a.primary) || actions[0] || {}).cmd || "",
      state: e.installed_elsewhere ? `installé par ${e.owner || "un autre utilisateur"} — pas pour vous`
             : !e.installed ? "absent"
             : (e.update_available ? "à mettre à jour" : "à jour") + " · " + EnginesViewModel.portee(e.scope),
      cls: e.installed_elsewhere ? "wait" : (!e.installed ? "" : (e.update_available ? "wait" : "ok")),
      warn: sessions && e.update_available ? `${sessions} session(s) en cours : la mise à jour les couperait` : "" };
  }
  get groupes() {
    return [{ key: "engines", label: "Moteurs de session", help: "les clients qui tiennent une session d'agent",
              rows: (this.cat.engines || []).map(r => this.ligne(r)) },
            { key: "servers", label: "Serveurs de modèles", help: "ils ne tiennent pas de session : ils servent les modèles, et se déclarent ensuite comme fournisseurs de l'axe « modèles de travail »",
              rows: (this.cat.servers || []).map(r => this.ligne(r)) }];
  }
  get count() {
    const n = this.etats.filter(e => e.installed).length;
    const ailleurs = this.etats.filter(e => e.installed_elsewhere).length;
    return `${n} installé(s) sur ${this.etats.length}` + (ailleurs ? ` · ${ailleurs} pour un autre utilisateur` : "");
  }
}

/** RM3139 — comment les moteurs sont LANCÉS : les options cochables, ce qui est saisi à la main, et
 *  la commande qui en sort. Séparé du ViewModel d'installation : deux sujets voisins, deux vues.
 *  e = { data: {engines, error}, dirty: {<engine>: {options, extra_args}}, busy } */
export class EngineLaunchViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.d = (this.e.data || {}); }
  get error() { return this.d.error || ""; }
  get empty() { return !(this.d.engines || []).length; }
  /** L'état AFFICHÉ : ce que l'utilisateur vient de cocher s'il a touché à quelque chose, sinon ce
   *  que le serveur dit. Sans cela, une case décochée se recocherait sous les doigts au re-rendu. */
  brouillon(name) { return (this.e.dirty || {})[name] || null; }
  ligne(p) {
    const d = this.brouillon(p.engine);
    const options = (p.options || []).map(o => ({
      key: o.key, label: o.label || o.key, flag: o.flag, why: o.why || "",
      enabled: d && d.options && o.key in d.options ? !!d.options[o.key] : !!o.enabled,
      source: o.source || "" }));
    const extra = d && typeof d.extra_args === "string" ? d.extra_args : (p.extra_args || "");
    // la commande vient du SERVEUR : tant qu'on n'a pas enregistré, elle décrit l'état enregistré,
    // pas le brouillon — le dire vaut mieux que d'afficher une commande devinée côté client.
    return { engine: p.engine, options, extra, cmd: p.spawn_cmd || p.base_cmd || "",
             resume: p.resume_cmd || "", problems: p.problems || [],
             dirty: !!d, busy: this.e.busy === p.engine };
  }
  get rows() { return (this.d.engines || []).map(p => this.ligne(p)); }
  /** Combien de moteurs portent un réglage propre à l'instance — le reste suit les défauts. */
  get count() {
    const n = this.rows.filter(r => r.options.some(o => o.source === "pm.config.yml") || r.extra).length;
    return n ? `${n} moteur(s) réglé(s) ici` : "tous aux valeurs par défaut";
  }
}
