// viewmodels/mail/EmailViewModel — présente un email de la file. RM2889, L1.
//
// Inerte : tout ce que renderMailList décidait en plein gabarit (badge d'état,
// cible, confiance, ce qu'on montre replié ou déplié) est ici, testable avec
// une entité de fixture et sans une ligne de HTML.

import { EntityViewModel } from "../../core/EntityViewModel.js";
import { routingTarget, confidencePct, proposedProject } from "./Email.js";

const BADGE = { "à traiter": "•", "proposé": "✎", "écarté": "⊘", "créé": "✓" };

export class EmailViewModel extends EntityViewModel {
  get title()      { return this.e.subject || "(sans objet)"; }
  get state()      { return this.e.state; }
  get badge()      { return BADGE[this.state] || "•"; }
  get open()       { return !!this.ctx.openKey && this.ctx.openKey === this.e.key; }
  get day()        { return (this.e.date || "").slice(0, 10); }
  // RM3147 : l'annuaire sait souvent qui écrit. `contact` vient du serveur, qui
  // résout l'adresse une fois pour toute la file — pas un aller-retour de plus.
  get contact()    { return this.e.contact || null; }
  get known()      { return !!(this.contact && this.contact.known); }
  get contactRef() { return this.known ? this.contact.ref : ""; }
  get internal()   { return !!(this.contact && this.contact.internal); }
  /** Le nom de l'annuaire prime : c'est lui qui reste juste quand l'adresse change. */
  get sender()     { return (this.known && this.contact.name)
                            || this.e.from_name || this.e.from || ""; }
  /** Ce qu'on pré-remplirait pour créer sa fiche — jamais deviné, lu de l'email. */
  get newContact() {
    const brut = String(this.e.from_name || "").trim();
    const mots = brut ? brut.split(/\s+/) : [];
    return { email: (this.e.from || "").trim().toLowerCase(),
             first_name: mots.length > 1 ? mots.slice(0, -1).join(" ") : brut,
             last_name: mots.length > 1 ? mots[mots.length - 1] : "" };
  }
  get target()     { return routingTarget(this.e); }
  get confidence() { return confidencePct(this.e.routing); }
  get source()     { return (this.e.routing || {}).source || ""; }
  get draft()      { return this.e.draft || {}; }
  get hasDraft()   { return !!this.draft.title; }
  get draftConfidence() { return confidencePct(this.draft); }
  get draftProject()    { return proposedProject(this.e); }
  get draftPriority()   { return this.draft.priority || "normal"; }
  get priorities()      { return ["low", "normal", "high", "urgent"]; }
  get description()     { return (this.draft.description || "").slice(0, 600); }
  get warnings()        { return this.draft.warnings || []; }
  get dismissedReason() { return this.e.dismissed ? (this.e.dismissed.reason || "") : null; }
  /** Actions disponibles une fois déplié — l'ordre est celui de l'écran. */
  actions() {
    return [
      { id: "center",  label: "⤢ au centre",      title: "Afficher cet email dans un onglet du panneau central" },
      { id: "draft",   label: "✎ Rédiger" },
      { id: "create",  label: "✓ Créer le ticket", primary: true },
      { id: "note",    label: "↩ Note sur…",       title: "Rattacher à un ticket existant : pose une note au lieu de créer" },
      { id: "reroute", label: "🎯 Reclasser",       title: "Corriger le client/projet — la correction est apprise" },
      { id: "dismiss", label: "⊘ Écarter" },
    ];
  }
}
