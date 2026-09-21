// modules/providers/ProvidersViewModel — le panneau Fournisseurs, décidé : instances par axe, état des clés,
// affectations projet × instance. RM3068. Aucune valeur de secret n'existe ici : le modèle ne connaît que « posée » ou non.
import { EntityViewModel } from "../../core/EntityViewModel.js";

/** e = { cat, data, open, models } — `open` : l'instance dépliée, ou "+<axe>" pour une création ;
 *  `models` : ce qu'un fournisseur a répondu quand on lui a demandé son catalogue (RM3072). */
export class ProvidersViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.cat = this.e.cat || { axes: [], types: [] }; this.data = this.e.data || {}; }
  /** Les services LLM prédéfinis : choisir l'un d'eux pose le type et l'URL, il ne reste que la clé. */
  get services() { return this.cat.llm_services || []; }
  serviceOf(id) { return this.services.find(s => s.id === id) || null; }
  /** Un dialecte qu'on sait interroger : on peut demander au fournisseur ce qu'il sert. */
  listable(type) { return this.services.some(s => s.type === type && s.listable); }
  /** Ce qu'a répondu un fournisseur : la liste, ou l'échec, ou rien si on n'a pas encore demandé. */
  modelsOf(name) {
    const m = (this.e.models || {})[name];
    if (!m) return null;
    if (m.error) return { error: m.error };
    return { list: m.models || [], count: (m.models || []).length, url: m.url || "" };
  }
  get admin() { return !!this.data.admin; }
  /** RM3070 L2 : la portée « global » n'est offerte que si l'instance peut vraiment l'écrire. */
  get canGlobal() { return !!this.data.admin && !!this.data.can_global; }
  get user() { return this.data.user || ""; }
  /** RM3096 : l'état des clés n'a pas pu être lu — à dire, au lieu de les montrer « absentes ». */
  get statesUnknown() { return !!this.data.states_unknown; }
  get statesError() { return this.data.states_error || ""; }
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
        listable: a.axis === "llm" && this.listable(i.type), models: this.modelsOf(i.name),
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
