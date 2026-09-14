// modules/setnav/SetnavViewModel — les réglages, décidés : quels onglets, lequel est ouvert, et
// lesquels n'ont rien à montrer. RM3081.
import { EntityViewModel } from "../../core/EntityViewModel.js";

/** Les groupes, dans l'ordre d'affichage. `cards` : les id des cartes déjà présentes dans la page —
 *  le découpage n'invente aucun contenu, il donne un ordre à ce qui existait en pile. */
export const GROUPES = [
  { key: "instance", label: "⚙ Instance", cards: ["reglages-card", "probecard"],
    help: "ce qui vaut pour toute l'instance" },
  { key: "providers", label: "🔌 Fournisseurs", cards: ["providerscard"],
    help: "tickets, dépôts, documentation, coffres, modèles de travail" },
  { key: "engines", label: "🧩 Moteurs", cards: ["enginescard"],
    help: "moteurs de session et serveurs de modèles" },
  // RM3145 : les modules sont de la CONFIGURATION de l'instance — ce qu'elle porte, et ce qui
  // dépend de quoi. Leur place est ici, pas dans l'en-tête qu'on vient d'alléger (RM3150).
  { key: "modules", label: "🧩 Modules", cards: ["modulescard"],
    help: "ce que l'instance porte, et ce qui dépend de quoi" },
  { key: "display", label: "🎨 Affichage", cards: ["themecard", "rightcard", "sessprefcard", "voicecard"],
    help: "local à ce navigateur" },
  { key: "account", label: "👤 Compte", cards: ["authcard", "userscard"],
    help: "connexion et comptes" },
];

/** e = { open, hidden } — `open` : l'onglet courant ; `hidden` : les clés sans rien à montrer. */
export class SetnavViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get groupes() { return GROUPES; }
  get cache() { return new Set(this.e.hidden || []); }
  /** L'onglet courant : celui demandé s'il a du contenu, sinon le premier qui en a. */
  get courant() {
    const vis = this.onglets;
    return (vis.find(t => t.key === this.e.open) || vis[0] || {}).key || "";
  }
  /** Les onglets à afficher : un groupe dont toutes les cartes sont masquées n'a rien à dire. */
  get onglets() {
    const cache = this.cache;
    return GROUPES.filter(g => !cache.has(g.key))
      .map(g => ({ key: g.key, label: g.label, help: g.help, on: g.key === this.e.open }));
  }
  /** Après résolution : c'est celui-là qui porte la marque, même si `open` visait un onglet masqué. */
  get tabs() {
    const c = this.courant;
    return this.onglets.map(t => ({ ...t, on: t.key === c }));
  }
  cardsOf(key) { return (GROUPES.find(g => g.key === key) || {}).cards || []; }
}
