// modules/clientnotify/ClientNotifyViewModel — ce que le panneau compte-rendu client montre : le menu des
// clients avec leur compte (« Calicote (5) »), la page d'un client (tickets groupés par projet, cochables
// en travers des projets), et l'état des deux gestes irréversibles. RM3052.
import { EntityViewModel } from "../../core/EntityViewModel.js";

/** e = { clients: [{client,label,count}], total } — le menu déroulant du bouton haut. */
export class ClientMenuViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get items() { return (this.e.clients || []).map(c => ({ client: c.client, label: c.label || c.client, count: c.count || 0, text: `${c.label || c.client} (${c.count || 0})` })); }
  get total() { return this.e.total || 0; }
  get empty() { return !this.items.length; }
  /** Le badge du bouton : rien à annoncer ⇒ rien à afficher (un badge « 0 » est du bruit). */
  get badge() { return this.total ? String(this.total) : ""; }
}

/** e = { client: <fiche client de la file>, sel: Set, protocole, preview, busy, confirm } */
export class ClientReportViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.sel = this.e.sel || new Set(); }
  get client() { return this.e.client || null; }
  get label() { return this.client ? (this.client.label || this.client.client) : ""; }
  get empty() { return !this.client || !this.groups.length; }
  get groups() {
    return ((this.client || {}).projects || []).map(p => ({
      project: p.project, label: p.label || p.project, actif: p.actif !== false,
      tickets: (p.tickets || []).map(t => ({
        id: String(t.id), title: t.title || "", url: t.url || "",
        queued_at: t.queued_at || "", on: this.sel.has(String(t.id)),
      })),
    }));
  }
  /** Plusieurs projets cochés ⇒ l'email les regroupera : le dire, personne ne devine un email non envoyé. */
  get multi() { return this.groups.filter(g => g.tickets.some(t => t.on)).length > 1; }
  get count() { return this.groups.reduce((n, g) => n + g.tickets.filter(t => t.on).length, 0); }
  get total() { return this.groups.reduce((n, g) => n + g.tickets.length, 0); }
  get allOn() { return this.total > 0 && this.count === this.total; }
  get recipients() { return ((this.client || {}).recipients) || []; }
  get orphans() { return ((this.client || {}).orphans) || []; }
  get protocole() { return this.e.protocole !== false; }
  get busy() { return !!this.e.busy; }
  /** Un projet en file dont l'option est coupée : ses tickets ne portent aucun destinataire. À dire, pas à masquer. */
  get inactives() { return this.groups.filter(g => !g.actif).map(g => g.label); }
  get canSend() { return !this.busy && this.count > 0 && this.recipients.length > 0; }
  get canDismiss() { return !this.busy && this.count > 0; }
  /** Deux temps sur les gestes irréversibles : un clic arme, le second exécute. */
  get sendLabel() {
    if (this.e.confirm === "send") return `Confirmer l'envoi à ${this.recipients.join(", ")}`;
    return this.count ? `✉ Envoyer (${this.count})` : "✉ Envoyer";
  }
  get dismissLabel() {
    if (this.e.confirm === "dismiss") return `Confirmer : écarter ${this.count} ticket(s) sans notifier`;
    return this.count ? `Écarter (${this.count})` : "Écarter";
  }
  get why() {
    if (!this.total) return "Rien en attente pour ce client.";
    if (!this.count) return "Cochez les tickets à annoncer.";
    if (!this.recipients.length) return "Aucun destinataire : l'option notif_client_mep est inactive, ou les contacts n'ont pas d'email.";
    return "";
  }
  get preview() { return this.e.preview || null; }
  /** L'aperçu est rendu DANS UNE IFRAME cloisonnée (`sandbox=""`, srcdoc) : c'est l'email
   * exact — styles compris — sans que son HTML ne s'exécute ni ne déteigne sur le cockpit. */
  get previewHtml() { return (this.e.preview && this.e.preview.html) || ""; }
}
