// views/sessions/Actions — les chips d'actions de la session attachée et le menu de disposition. Gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";

export function Chips(vm) {
  // RM3418 : un BLOC par groupe (titre + ses chips), et « … » si des chips sont en débordement.
  const blocs = vm.blocks ? vm.blocks() : [];
  const debordement = blocs.some(b => b.chips.some(c => c.extra));
  return html`${blocs.map(b => html`<span class="cblock">${b.group ? html`<span class="cgroup">${b.group}</span>` : ""}${b.chips.map(c => html`<button class="chip${c.extra ? " bar-extra" : ""}" title="${c.title}" data-action="chip" data-i="${String(c.i)}">${c.label}</button>`)}</span>`)}${debordement ? html`<button class="chip chips-more" id="chipsmore" title="Les autres actions de la session" data-action="chips-more">…</button>` : ""}`;
}
export function DispositionMenu(vm) { return html`${vm.items().map(d => html`<button data-v="${d.value}"${d.on ? raw(' class="on"') : ""}>${d.label}</button>`)}<div class="sep"></div><button data-kill="1">✕ fermer la session</button>`; }
export function PresetOptions(values, prefix) { return html`${values.map(v => html`<option value="${v}">${(prefix || "") + v}</option>`)}`; }
