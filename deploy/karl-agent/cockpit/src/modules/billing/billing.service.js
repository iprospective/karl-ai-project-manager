// modules/billing/billing.service — l'état de l'écran « Facturation » : la journée regardée, ce que le
// serveur en dit, l'ajustement en cours d'édition. Aucun DOM. RM3229, lot L3.
//
// Règle de l'écran : on valide UNE journée à la fois, et on la valide en la regardant. Le service ne
// valide jamais tout seul, ne valide jamais un lot, et recharge toujours la journée APRÈS l'écriture —
// ce qui s'affiche ensuite vient de Redmine, pas de ce qu'on espérait y avoir mis.
import { BillingRepository } from "./BillingRepository.js";
import { heuresNormales } from "./billing.js";

const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

export class BillingService {
  constructor({ repo = new BillingRepository(), run = null, day = null } = {}) {
    this.repo = repo;
    this.run = run;                      // (name, args, opts) => Promise — le runner du catalogue PM
    this.day = day || today();
    this.jour = null;                    // la charge serveur de la journée
    this.loading = false;
    this.error = null;
    this.busy = null;                    // geste en cours : "adjust" | "apply"
    this.edit = null;                    // { debut, fin, client, projet, pause } en cours de saisie
    this.projets = [];                   // {client, project}[] — chargé une fois, pour les menus
    this.ligne = null;                   // clé de la ligne en cours de correction
    this.ajout = null;                   // formulaire d'ajout d'une ligne, s'il est ouvert
    this.ligneEdit = null;               // {client, projet, ticket} en cours de saisie
    this.vue = "jour";                   // jour | semaine | mois
    this.mois = {};                      // AAAA-MM → {date → résumé}, gardé d'une vue à l'autre
    this.moisCharge = null;              // mois en cours de lecture (pour l'attente)
  }

  /**
   * La liste des clients et projets PM. Chargée UNE fois : elle ne change pas d'une
   * journée à l'autre, et l'écran en a besoin dès le premier rendu du formulaire.
   * Un échec est sans gravité — les menus retombent sur une saisie libre.
   */
  async chargerProjets() {
    if (this.projets.length) return this.projets;
    try {
      const r = await this.repo.projects();
      this.projets = (r && r.projects) || [];
    } catch (e) { this.projets = []; }
    return this.projets;
  }

  /** Bascule de vue. La journée regardée ne change pas : on la retrouve en revenant. */
  setVue(v) { this.vue = ["jour", "semaine", "mois"].includes(v) ? v : "jour"; return this.vue; }

  /**
   * Les résumés d'un mois, lus une fois puis gardés.
   *
   * Une grille de semaine à cheval sur deux mois en charge DEUX : sans quoi la moitié
   * des cases serait vide sans raison visible.
   */
  async chargerMois(mois) {
    if (this.mois[mois]) return this.mois[mois];
    this.moisCharge = mois;
    try {
      const r = await this.repo.month(mois, true);
      const par = {};
      for (const j of (r && r.jours) || []) if (j && j.date) par[j.date] = j;
      this.mois[mois] = par;
    } catch (e) {
      this.error = e.message;
      this.mois[mois] = {};
    } finally { this.moisCharge = null; }
    return this.mois[mois];
  }

  /** Les résumés couvrant une période — un ou deux mois selon le chevauchement. */
  resumes(moisVoulus) {
    const out = {};
    for (const m of moisVoulus) Object.assign(out, this.mois[m] || {});
    return out;
  }

  /** Oublie les résumés d'un mois : après une validation, ils sont périmés. */
  invaliderMois(mois) { delete this.mois[mois]; }

  /** Change de journée : l'édition en cours ne suit pas — elle appartenait à l'autre jour. */
  setDay(jour) {
    this.day = String(jour); this.jour = null; this.edit = null; this.error = null;
    this.ligne = null; this.ligneEdit = null; this.ajout = null;
  }

  // ── Une ligne à la fois ───────────────────────────────────────────────────
  //
  // L'unité de validation n'est plus forcément la journée : une ligne se corrige et
  // s'écrit seule. On ne touche jamais aux MINUTES ici — seulement au rattachement
  // (client, projet, ticket) : déplacer du temps, ce n'est pas en créer.

  /** Ouvre (ou referme) la correction d'une ligne, en partant de son état actuel. */
  editerLigne(cle, depart = null) {
    if (!cle || this.ligne === cle) { this.ligne = null; this.ligneEdit = null; return null; }
    this.ligne = cle;
    this.ligneEdit = Object.assign({ client: "", projet: "", ticket: "" }, depart || {});
    return this.ligne;
  }

  setLigneChamp(champ, valeur) {
    this.ligneEdit = Object.assign({}, this.ligneEdit, { [champ]: valeur });
  }

  /** Enregistre le rattachement corrigé, puis relit la journée. */
  async enregistrerLigne() {
    this._need();
    if (!this.ligne) throw new Error("aucune ligne en cours de correction");
    const e = this.ligneEdit || {};
    const args = { day: this.day, ligne: this.ligne };
    for (const [k, v] of [["set_client", e.client], ["set_projet", e.projet],
                          ["set_ticket", e.ticket]]) {
      if (v !== null && v !== undefined && String(v) !== "") args[k] = String(v);
    }
    this.busy = "ligne";
    try {
      await this.run("timesheet-line-adjust", args);
      this.ligne = null; this.ligneEdit = null;
      return await this.load();
    } finally { this.busy = null; }
  }

  /** Retire la correction : la ligne redevient ce que le calcul dit. */
  async retablirLigne(cle) {
    this._need();
    this.busy = "ligne";
    try {
      await this.run("timesheet-line-adjust", { day: this.day, ligne: cle, clear_ligne: true });
      this.ligne = null; this.ligneEdit = null;
      return await this.load();
    } finally { this.busy = null; }
  }

  /** Scinde une ligne : elle garde `minutes`, une seconde reçoit le reste. */
  async scinderLigne(cle, minutes) {
    this._need();
    this.busy = "ligne";
    try {
      await this.run("timesheet-line-adjust", { day: this.day, ligne: cle, split: minutes });
      this.ligne = null; this.ligneEdit = null;
      return await this.load();
    } finally { this.busy = null; }
  }

  /** Retire une ligne de la proposition. Réversible : `retablirLigne` la ramène. */
  async supprimerLigne(cle) {
    this._need();
    this.busy = "ligne";
    try {
      await this.run("timesheet-line-adjust", { day: this.day, ligne: cle, delete_ligne: true });
      this.ligne = null; this.ligneEdit = null;
      return await this.load();
    } finally { this.busy = null; }
  }

  /** Ouvre (ou referme) le formulaire d'ajout d'une ligne. */
  editerAjout(ouvrir = true) {
    this.ajout = ouvrir ? Object.assign({ client: "", projet: "", ticket: "",
                                          minutes: "", commentaire: "" }, this.ajout || {})
                        : null;
    return this.ajout;
  }

  setAjoutChamp(champ, valeur) {
    this.ajout = Object.assign({}, this.ajout, { [champ]: valeur });
  }

  /** Ajoute une ligne que le calcul n'a pas vue. Elle CRÉE du temps. */
  async ajouterLigne() {
    this._need();
    const a = this.ajout || {};
    if (!a.client) throw new Error("un client est nécessaire");
    const minutes = parseInt(a.minutes, 10);
    if (!(minutes > 0)) throw new Error("une durée en minutes est nécessaire");
    const args = { day: this.day, set_client: a.client, set_minutes: minutes };
    for (const [k, v] of [["set_projet", a.projet], ["set_ticket", a.ticket],
                          ["commentaire", a.commentaire]]) {
      if (v !== null && v !== undefined && String(v) !== "") args[k] = String(v);
    }
    this.busy = "ligne";
    try {
      await this.run("timesheet-line-add", args);
      this.ajout = null;
      return await this.load();
    } finally { this.busy = null; }
  }

  /** ÉCRIT cette seule ligne dans Redmine. Confirmation exigée par le catalogue. */
  async ecrireLigne(cle, { dryRun = false } = {}) {
    this._need();
    this.busy = "ligne-apply";
    try {
      const args = { day: this.day, ligne: cle };
      if (dryRun) args.dry_run = true;
      const res = await this.run("timesheet-line-apply", args, { confirm: true });
      this.invaliderMois(this.day.slice(0, 7));
      await this.load();
      return res;
    } finally { this.busy = null; }
  }

  async load(refresh = false) {
    this.loading = true; this.error = null;
    try {
      const r = await this.repo.day(this.day, refresh);
      this.jour = (r && r.jour) || null;
      this.edit = null;
    } catch (e) { this.error = e.message; this.jour = null; }
    finally { this.loading = false; }
    return this.jour;
  }

  /** Les heures en cours d'édition : celles saisies, sinon celles que le serveur propose. */
  form() {
    const base = heuresNormales(this.jour);
    const s = (this.jour && this.jour.surcharge) || {};
    return Object.assign({
      debut: base.debut, fin: base.fin, pause: base.pause,
      client: s.client || "", projet: s.projet || "", lieu: s.lieu || "",
      pauseDebut: s.pause_debut || "", pauseFin: s.pause_fin || "",
      source: base.source, hors: base.hors,
    }, this.edit || {});
  }

  /** Saisie en cours (non envoyée) — le bouton « Enregistrer » devient actif. */
  setField(champ, valeur) { this.edit = Object.assign({}, this.edit, { [champ]: valeur }); }
  get dirty() { return !!this.edit; }

  _need() {
    if (!this.run) throw new Error("runner PM absent");
    if (this.busy) throw new Error("un geste est déjà en cours");
  }

  /** Enregistre l'ajustement de la journée, puis la relit. */
  async adjust() {
    this._need();
    const f = this.form();
    const args = { day: this.day };
    for (const [k, v] of [["start", f.debut], ["end", f.fin], ["client", f.client],
                          ["projet", f.projet], ["pause", f.pause], ["lieu", f.lieu],
                          ["pause_debut", f.pauseDebut], ["pause_fin", f.pauseFin]]) {
      if (v !== null && v !== undefined && String(v) !== "") args[k] = String(v);
    }
    this.busy = "adjust";
    try { await this.run("timesheet-day-adjust", args); return await this.load(); }
    finally { this.busy = null; }
  }

  /** Retire l'ajustement : la journée redevient ce que les traces disent. */
  async clearOverride() {
    this._need();
    this.busy = "adjust";
    try { await this.run("timesheet-day-adjust", { day: this.day, clear_override: true }); return await this.load(); }
    finally { this.busy = null; }
  }

  /**
   * VALIDE la journée : crée les saisies de temps dans Redmine, pour cette journée seulement.
   * La confirmation est exigée par le catalogue ; l'appelant la passe après avoir demandé à l'humain.
   */
  async apply({ dryRun = false } = {}) {
    this._need();
    this.busy = "apply";
    try {
      const args = { day: this.day };
      if (dryRun) args.dry_run = true;
      const res = await this.run("timesheet-day-apply", args, { confirm: true });
      this.invaliderMois(this.day.slice(0, 7));
      await this.load();
      return res;
    } finally { this.busy = null; }
  }

  /**
   * REPREND la journée : retire les saisies que l'outil y a posées, pour la refaire.
   *
   * Geste à la demande, jamais automatique : rien d'autre dans ce service ne l'appelle.
   * La relecture qui suit est forcée (`refresh`) — après un retrait, la journée doit être
   * réanalysée depuis les traces, pas relue depuis un cache qui décrirait l'état d'avant.
   */
  async revoke() {
    this._need();
    this.busy = "revoke";
    try {
      const res = await this.run("timesheet-day-revoke", { day: this.day }, { confirm: true });
      await this.load(true);
      return res;
    } finally { this.busy = null; }
  }

  /** Journée sans rien à ajouter (tout est déjà noté à la main) : la marquer validée sans créer de saisie. */
  async validateEmpty() {
    this._need();
    this.busy = "apply";
    try { await this.run("timesheet-day-adjust", { day: this.day, validate_empty: true }); return await this.load(); }
    finally { this.busy = null; }
  }
}
