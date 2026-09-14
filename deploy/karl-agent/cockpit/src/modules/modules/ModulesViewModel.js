// modules/modules/ModulesViewModel — les modules, décidés : leur état, ce qu'ils fournissent, ce qui
// casserait si on les désactivait, et ce que l'instance porte ENCORE sans module. RM3145 (lot 3).
import { EntityViewModel } from "../../core/EntityViewModel.js";

const ETAT = { actif: { cls: "ok", icone: "✓" }, "désactivé": { cls: "off", icone: "○" },
               "bloqué": { cls: "wait", icone: "⚠" }, erreur: { cls: "due", icone: "✗" } };

/** e = { data: {modules, order, cycles, inventory, bus, root, core_version}, error, open } */
export class ModulesViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.d = this.e.data || {}; }
  get error() { return this.e.error || ""; }
  get empty() { return !this.error && !(this.d.modules || []).length; }
  get root() { return this.d.root || ""; }
  get coreVersion() { return this.d.core_version || ""; }
  get open() { return this.e.open || ""; }
  get cycles() { return this.d.cycles || []; }
  get bus() { return this.d.bus || { pending: 0, errors: 0, last_errors: [] }; }

  rows() {
    return (this.d.modules || []).map(m => ({
      name: m.name, version: m.version, label: m.label, description: m.description,
      state: m.state, cls: (ETAT[m.state] || {}).cls || "", icone: (ETAT[m.state] || {}).icone || "·",
      provides: (m.provides || []).map(([k, n]) => k + " " + n),
      requires: m.requires || [],
      // Ce qui casserait si on le désactivait — la question qu'on se pose au moment de cliquer.
      requiredBy: m.required_by || [],
      triggers: (m.triggers || []).map(t => ({ on: t.on, run: (t.run || []).join(" "),
                                               when: Object.entries(t.when || {}).map(([k, v]) => k + "=" + v).join(", "),
                                               ok: t.ok, errors: t.errors || [] })),
      motifs: (m.errors || []).concat(m.blocked || []),
      open: m.name === this.open,
    }));
  }

  /** L'écart, par registre : ce que PM porte encore SANS module. Le taire donnerait un panneau
   *  flatteur et faux — au lot 0, presque rien n'est décrit. */
  get inventaire() {
    const inv = this.d.inventory || { registres: {}, total: 0, decrits: 0, non_decrits: 0 };
    return {
      total: inv.total || 0, decrits: inv.decrits || 0, restants: inv.non_decrits || 0,
      pct: inv.total ? Math.round((inv.decrits / inv.total) * 100) : 0,
      lignes: Object.entries(inv.registres || {}).map(([cle, items]) => ({
        registre: cle, total: items.length,
        decrits: items.filter(x => x.decrit).length,
        manquants: items.filter(x => !x.decrit).map(x => x.item),
      })).sort((a, b) => a.registre.localeCompare(b.registre)),
    };
  }
  get counts() {
    const r = this.rows();
    return { total: r.length, actifs: r.filter(x => x.state === "actif").length,
             casses: r.filter(x => x.state === "erreur" || x.state === "bloqué").length };
  }
}
