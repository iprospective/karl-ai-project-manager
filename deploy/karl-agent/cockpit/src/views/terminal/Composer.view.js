// views/terminal/Composer — l'avertissement de garde et l'historique des envois. Gestes en data-*. RM2889.
import { html } from "../../core/html.js";
export function ComposerWarn(vm) { return vm.warn ? html`<b>Envoi retenu.</b> ${vm.warn}` : ""; }
export function ComposerHistory(vm) {
  const items = vm.items();
  if (!items.length) return html`<div class="hempty">Aucun message envoyé dans cette session.</div>`;
  return html`${items.map(h => html`<div class="hitem" data-i="${String(h.i)}" title="Cliquer pour reprendre ce message">${h.text}</div>`)}`;
}
