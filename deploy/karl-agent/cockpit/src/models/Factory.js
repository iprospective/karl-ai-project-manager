// models/Factory — hydratation depuis la charge serveur. RM2889, L0.
//
// La factory est le SEUL endroit où la forme brute du serveur est connue.
// Elle applique les invariants (champs obligatoires, types, valeurs par
// défaut) AVANT que l'entité n'existe : une entité construite est une entité
// valide, et le reste du front n'a plus à se défendre.

export class Factory {
  /**
   * @param {object} spec  { type, required: [...], defaults: {...}, coerce: {champ: fn} }
   */
  constructor({ type, required = [], defaults = {}, coerce = {} }) {
    if (!type) throw new Error("une factory doit connaître son type");
    this.type = type;
    this.required = required;
    this.defaults = defaults;
    this.coerce = coerce;
  }

  /** Une entité depuis un objet brut. Lève si un invariant est violé. */
  one(raw) {
    if (!raw || typeof raw !== "object") throw new Error(`${this.type} : charge vide`);
    const missing = this.required.filter(k => raw[k] === undefined || raw[k] === null);
    if (missing.length) throw new Error(`${this.type} : champs manquants ${missing.join(", ")}`);
    const e = { ...this.defaults, ...raw, type: this.type };
    for (const [k, fn] of Object.entries(this.coerce)) if (k in e) e[k] = fn(e[k]);
    return Object.freeze(e);
  }

  /** Une liste — accepte le tableau nu ou l'enveloppe `{ items: [...] }`. */
  many(raw) {
    const items = Array.isArray(raw) ? raw : (raw && raw.items) || [];
    return items.map(r => this.one(r));
  }
}
