// viewmodels/EntityViewModel — base commune à TOUS les types. RM2889, L0 (§ 7.2).
//
// Un ViewModel PRÉSENTE : titre, badges, sections, dérivations d'affichage.
// Il ne va rien chercher — c'est le ViewComposer qui assemble, avec le
// réseau — et il est donc testable avec une entité de fixture (C4).
//
// Ce que la vue « se débrouille » à récupérer vient du contexte injecté
// (`ctx`), jamais du réseau : utilisateur, droits, formats, horloge.
//
// Héritage PLAT : EntityViewModel → XViewModel, un niveau ; le reste par
// mixins (viewmodels/mixins/) et composants — la garde d'AST vérifie la
// profondeur (§ 7.2 bis).

export class EntityViewModel {
  constructor(entity, ctx = {}) {
    if (!entity) throw new Error("un ViewModel exige une entité");
    this.e = entity;
    this.ctx = ctx;
  }
  get id()    { return this.e.id; }
  get type()  { return this.e.type; }
  get title() { return this.e.title || ""; }
  get state() { return this.e.state || ""; }
  /** Pastilles d'en-tête. Spécialisé par type, en s'appuyant sur super. */
  get badges() { return this.state ? [this.state] : []; }
  /** Sections de la fiche — les quatre niveaux d'affichage en sont des compositions (§ 10). */
  sections() { return []; }
  /** Les actions viennent du SERVEUR : le front ne décide pas ce qu'on a le droit de faire. */
  actions() { return this.e.actions || []; }
  /** Sections visibles au niveau compact (card / mobile). */
  summary() { return this.sections().filter(s => s.summary); }

  // — génériques : la vue ne les reçoit pas, elle les prend ici —
  get user() { return this.ctx.user; }
  get can()  { return this.ctx.can || (() => false); }
  get fmt()  { return this.ctx.fmt || {}; }
  get t()    { return this.ctx.i18n || (s => s); }
  get now()  { return this.ctx.now || Date.now(); }
}

/** Mixin d'exemple et de référence : la conso, partagée par ticket, session, projet. */
export const withConso = (Base) => class extends Base {
  get conso() { return this.e.conso || { tokens: 0, cost: 0, minutes: 0 }; }
  consoSection() { return { id: "conso", title: "temps et tokens" }; }
};
