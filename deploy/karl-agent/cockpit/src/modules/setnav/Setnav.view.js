// modules/setnav/Setnav.view — la barre d'onglets des réglages. Gestes en data-action, aucun on*. RM3081.
import { html } from "../../core/html.js";

export function SetnavBar(vm) {
  const actif = vm.tabs.find(t => t.on) || {};
  return html`<div class="setnav" role="tablist">${vm.tabs.map(t => html`<button class="chip${t.on ? " on" : ""}" data-action="settab" data-tab="${t.key}" title="${t.help}">${t.label}</button>`)}</div>
  ${actif.help ? html`<div class="setnav-help">${actif.help}</div>` : ""}`;
}
