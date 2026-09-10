// viewmodels/pmcmd — menu par catégorie, formulaire généré depuis args[]. RM2889, L5.
import { EntityViewModel } from "../../core/EntityViewModel.js";

export class PmMenuViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || { commands: [] }, ctx); }
  categories() {
    const cats = {};
    (this.e.commands || []).forEach(c => { (cats[c.category || "autres"] = cats[c.category || "autres"] || []).push(c); });
    return Object.keys(cats).sort().map(name => ({ name, commands: cats[name].map(c => ({
      name: c.name, label: (c.mutate ? "✏ " : "👁 ") + (c.label || c.name), title: c.name + (c.confirm ? " (confirmation requise)" : "") })) }));
  }
}

/** Le formulaire d'UNE commande : enum→select, bool→case, text long→textarea, rm_id/int→nombre. */
export class PmFormViewModel extends EntityViewModel {
  get title() { return this.e.label || this.e.name; }
  get mutate() { return !!this.e.mutate; }
  get submitLabel() { return this.mutate ? "✏ Exécuter" : "👁 Afficher"; }
  fields() {
    return (this.e.args || []).filter(a => !a.server && !a.const).map(a => ({
      id: "pmf-" + a.name, name: a.name, label: (a.label || a.name) + (a.required ? " *" : ""), required: !!a.required,
      widget: a.type === "enum" ? "select" : a.type === "bool" ? "checkbox" : (a.type === "text" && (!a.max_len || a.max_len > 120)) ? "textarea" : "input",
      inputType: (a.type === "rm_id" || a.type === "int") ? "number" : "text", choices: a.choices || [] }));
  }
}
