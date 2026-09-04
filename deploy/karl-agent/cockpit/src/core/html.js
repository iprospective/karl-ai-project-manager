// core/html — fabrication de HTML sûre par défaut. RM2889, lot L0.
//
// Aucune dépendance au DOM : ce module ne manipule que des CHAÎNES, ce qui le
// rend importable sous node nu (contrainte C5 — les tests tournent sans
// navigateur). Le montage dans le document est l'affaire de core/dom.js.
//
// `esc` et `jarg` sont repris à l'IDENTIQUE d'index.html : un lot déplace, il
// ne réécrit pas (§ 15.7). Leur comportement est verrouillé par des tests avant
// que le moindre appelant ne bouge.

/** Échappe le texte destiné à un nœud ou à un attribut entre guillemets doubles. */
export function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/**
 * Argument CHAÎNE d'un handler inline : rend `'...'` — guillemets SIMPLES.
 *
 * L'attribut HTML est écrit en guillemets doubles ; un `JSON.stringify` y
 * refermerait l'attribut au premier `"` et tuerait le handler au clic, sans
 * que tests ni serve-check ne le voient. D'où les simples, et le `&quot;`.
 */
export function jarg(s) {
  return "'" + String(s == null ? "" : s)
    .replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/"/g, "&quot;") + "'";
}

/** Fragment déjà sûr : ne sera pas ré-échappé par `html`. */
class Safe {
  constructor(value) { this.value = value; }
  toString() { return this.value; }
}

/** Marque une chaîne comme du HTML déjà sûr. À n'employer que sur du construit. */
export function raw(value) { return new Safe(String(value == null ? "" : value)); }

/** Vrai si la valeur traverse `html` sans être échappée. */
export function isSafe(value) { return value instanceof Safe; }

function interpolate(value) {
  if (value == null || value === false) return "";
  if (value instanceof Safe) return value.value;
  if (Array.isArray(value)) return value.map(interpolate).join("");
  return esc(value);
}

/**
 * Gabarit balisé : `html`<p>${titre}</p>`` échappe `titre`, sauf s'il est
 * passé par `raw()`. Les tableaux sont concaténés — une liste s'écrit
 * `${items.map(i => row(i))}` sans `.join("")`.
 *
 * C'est la brique des vues (« twig » du projet) : une vue est une fonction
 * pure qui prend un ViewModel et rend un fragment sûr.
 */
export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i++) out += interpolate(values[i]) + strings[i + 1];
  return new Safe(out);
}

/** Attributs depuis un objet : les valeurs `null`/`false` sont omises. */
export function attrs(obj) {
  const parts = [];
  for (const [k, v] of Object.entries(obj || {})) {
    if (v == null || v === false) continue;
    parts.push(v === true ? k : `${k}="${esc(v)}"`);
  }
  return new Safe(parts.join(" "));
}
