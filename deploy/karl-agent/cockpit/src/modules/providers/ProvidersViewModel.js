// modules/providers/ProvidersViewModel — le panneau Fournisseurs, décidé : instances par axe, état des clés,
// affectations projet × instance. RM3068. Aucune valeur de secret n'existe ici : le modèle ne connaît que « posée » ou non.
import { EntityViewModel } from "../../core/EntityViewModel.js";

/** e = { cat, data, open } — `open` : l'instance dont le détail est déplié, ou "+<axe>" pour une création. */
export class ProvidersViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.cat = this.e.cat || { axes: [], types: [] }; this.data = this.e.data || {}; }
  get admin() { return !!this.data.admin; }
  get user() { return this.data.user || ""; }
  get empty() { return !(this.cat.types || []).length; }
  typesOf(axis) { return (this.cat.types || []).filter(t => t.axis === axis); }
  typeOf(nom) { return (this.cat.types || []).find(t => t.type === nom) || { fields: [], secrets: [] }; }
  /** Les axes avec leurs instances, le défaut, et l'état des clés de chacune. */
  axes() {
    const insts = this.data.instances || [], def = this.data.defaults || {};
    return (this.cat.axes || []).map(a => ({
      axis: a.axis, label: a.label, def: def[a.axis] || "",
      creating: this.e.open === "+" + a.axis,
      types: this.typesOf(a.axis),
      instances: insts.filter(i => i.axis === a.axis).map(i => ({
        name: i.name, type: i.type, local: !!i.local, open: this.e.open === i.name,
        label: (this.typeOf(i.type).label || i.type),
        fields: Object.entries(i.fields || {}).map(([k, v]) => ({ k, v: Array.isArray(v) ? v.join(", ") : String(v) })),
        secrets: (i.secrets || []).map(s => ({ key: s.key, label: s.label, var: s.var, set: !!s.set })),
        isDefault: def[a.axis] === i.name,
        uses: (this.data.assignments || []).filter(x => x.instance === i.name)
          .map(x => ({ project: x.client + "/" + x.project, role: x.role, params: Object.entries(x.params || {}).map(([k, v]) => k + "=" + v).join(" ") })),
      })),
    }));
  }
  /** Les champs à saisir pour un type donné (création ou édition). */
  formOf(type, fields) {
    const t = this.typeOf(type), cur = fields || {};
    return (t.fields || []).map(f => ({ ...f, value: cur[f.name] === undefined ? "" : (Array.isArray(cur[f.name]) ? cur[f.name].join(", ") : String(cur[f.name])) }));
  }
  get count() { return String((this.data.instances || []).length); }
}
