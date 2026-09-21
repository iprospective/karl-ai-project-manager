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
  }

  /** Change de journée : l'édition en cours ne suit pas — elle appartenait à l'autre jour. */
  setDay(jour) { this.day = String(jour); this.jour = null; this.edit = null; this.error = null; }

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
      client: s.client || "", projet: s.projet || "", source: base.source, hors: base.hors,
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
                          ["projet", f.projet], ["pause", f.pause]]) {
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
      await this.load();
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
