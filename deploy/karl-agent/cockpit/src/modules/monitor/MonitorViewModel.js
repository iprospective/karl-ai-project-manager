// modules/monitor/MonitorViewModel — la supervision, décidée : ce qui ne va pas, chez qui, et depuis
// quand. RM3112. Une alerte sans client résolu se voit : c'est ce qui empêche d'ouvrir un ticket.
import { EntityViewModel } from "../../core/EntityViewModel.js";

/** Sévérités de l'observateur → classe d'état du cockpit. Au-delà du seuil, c'est « gros souci ». */
const CLS = { 0: "off", 1: "", 2: "wait", 3: "wait", 4: "due", 5: "due" };

/** e = { data: {alerts, counts, seuil_grave}, error, page, hosts, busy, seuil } */
export class MonitorViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.d = this.e.data || {}; }
  get error() { return this.e.error || ""; }
  get empty() { return !this.error && !(this.d.alerts || []).length; }
  get counts() { return this.d.counts || { total: 0, grave: 0, sans_cible: 0 }; }
  get seuil() { return Number(this.e.seuil || 0); }
  /** Les seuils offerts : on regarde rarement « tout », souvent « ce qui est grave ». */
  get seuils() {
    return [[0, "tout"], [2, "à partir d'avertissement"], [3, "à partir de moyen"], [4, "gros souci"]]
      .map(([v, l]) => ({ value: v, label: l, on: v === this.seuil }));
  }
  rows() {
    return (this.d.alerts || []).map(a => {
      const c = a.cible || {};
      return {
        id: a.eventid, name: a.name || "", host: a.host || "", hostName: a.host_name || "",
        severity: a.severity, severityLabel: a.severity_label || "", cls: CLS[a.severity] || "",
        since: a.since || "", grave: !!a.grave, ack: !!a.acknowledged,
        client: c.client || "", project: c.project || "",
        cible: c.client ? (c.client + (c.project ? "/" + c.project : "")) : "",
        // une association devinée se dit ; une association confirmée n'a plus besoin de se justifier
        devine: !!c.client && c.confiance < 1,
        source: c.source || "", confiance: c.confiance || 0,
        // sans projet, on ne sait pas OÙ créer le ticket : le bouton doit le dire, pas échouer après coup
        ticketable: !!(c.client && c.project),
        manque: !c.client ? "aucun client associé à cet hôte" : (!c.project ? "client connu, projet à choisir" : ""),
      };
    });
  }
  /** La page « hôtes » : ce qui est supervisé, et l'association qu'on peut corriger. */
  get hostRows() {
    const h = this.e.hosts || {};
    return (h.hosts || []).map(x => {
      const c = x.cible || {};
      // Le client en cours de choix l'emporte sur celui de la proposition : c'est lui qui doit décider
      // des projets offerts, sinon on choisirait un projet dans la liste du client précédent.
      const choisi = (this.e.choix || {})[x.host];
      const client = choisi !== undefined ? choisi : (c.client || "");
      const projets = this.projetsDe(client);
      return { host: x.host, name: x.name || "", actif: !!x.actif,
               client, project: c.project || "",
               projets, unique: projets.length === 1,
               source: c.source || "", confiance: c.confiance || 0,
               confirmee: (c.confiance || 0) >= 1 && !choisi };
    });
  }
  get clients() { return (this.e.hosts || {}).clients || []; }
  /** Les projets d'un client. Vide si le client est inconnu — on ne propose pas de projet imaginaire. */
  projetsDe(client) { return ((this.e.hosts || {}).projects || {})[client] || []; }
  get page() { return this.e.page === "hosts" ? "hosts" : "alerts"; }
  get pages() {
    return [["alerts", "⚠ Alertes"], ["hosts", "🖥 Hôtes & association"]]
      .map(([k, l]) => ({ key: k, label: l, on: k === this.page }));
  }
}
