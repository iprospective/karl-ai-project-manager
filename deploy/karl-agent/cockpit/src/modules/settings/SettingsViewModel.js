// viewmodels/settings — groupes de réglages, champs typés. RM2889, L5.
import { EntityViewModel } from "../../core/EntityViewModel.js";
const OPEN = new Set(["Conf PM", "Design front", "Sessions"]);
export class SettingsViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || { settings: [] }, ctx); }
  groups() {
    const g = {};
    (this.e.settings || []).forEach(s => { (g[s.group] = g[s.group] || []).push(s); });
    return Object.keys(g).map(name => ({ name, open: OPEN.has(name), entries: g[name].map(s => ({
      // RM3159 : `rows` et `help` accompagnent un réglage de type texte — la hauteur du champ et la
      // phrase qui dit à quoi il sert. Les laisser tomber ici afficherait un cadre nu, à remplir au
      // jugé : on ne modifie pas ce qu'on ne comprend pas.
      key: s.key, label: s.label, type: s.type, value: s.value, options: s.options || [],
      pinned: s.pinned || "", rows: s.rows || 0, help: s.help || "" })) }));
  }
}
