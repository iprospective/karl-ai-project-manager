// views/sessions/Actions — les chips d'actions de la session attachée et le menu de disposition. Gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";

export function Chips(vm) { return html`${vm.items().map(c => c.group !== undefined ? html`<span class="cgroup">${c.group}</span>` : html`<button class="chip" title="${c.title}" data-action="chip" data-i="${String(c.i)}">${c.label}</button>`)}`; }
export function DispositionMenu(vm) { return html`${vm.items().map(d => html`<button data-v="${d.value}"${d.on ? raw(' class="on"') : ""}>${d.label}</button>`)}<div class="sep"></div><button data-kill="1">✕ fermer la session</button>`; }
export function PresetOptions(values, prefix) { return html`${values.map(v => html`<option value="${v}">${(prefix || "") + v}</option>`)}`; }
