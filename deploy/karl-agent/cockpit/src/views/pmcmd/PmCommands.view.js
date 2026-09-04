// views/pmcmd — le panneau « ⚙ Commandes PM ». RM2889, L5. Balisage repris de #pmcard,
// loadPmCommands et renderPmForm ; zéro code UI par commande, gestes en data-action.
import { html } from "../../core/html.js";

export function PmMenu(vm) {
  return html`${vm.categories().map(cat => html`<div><div class="cgroup" style="margin:8px 0 4px;text-transform:uppercase;font-size:10px;color:var(--muted)">${cat.name}</div><div class="rels">${cat.commands.map(c =>
    html`<button class="chip" data-action="pick" data-name="${c.name}" title="${c.title}">${c.label}</button>`)}</div></div>`)}`;
}

export function PmForm(vm) {
  if (!vm) return "";
  return html`<div style="border-top:1px solid var(--line);margin-top:10px;padding-top:8px"><b>${vm.title}</b>${vm.mutate ? html` <span class="pill warn">mutation</span>` : html` <span class="pill">lecture</span>`}${vm.fields().map(f =>
    f.widget === "select" ? html`<label for="${f.id}">${f.label}</label><select id="${f.id}" data-arg="${f.name}">${f.required ? "" : html`<option value=""></option>`}${f.choices.map(ch => html`<option>${ch}</option>`)}</select>`
    : f.widget === "checkbox" ? html`<label style="display:flex;align-items:center;gap:6px;margin-top:8px"><input type="checkbox" id="${f.id}" data-arg="${f.name}" style="width:auto"> ${f.label}</label>`
    : f.widget === "textarea" ? html`<label for="${f.id}">${f.label}</label><textarea id="${f.id}" data-arg="${f.name}" rows="3"></textarea>`
    : html`<label for="${f.id}">${f.label}</label><input id="${f.id}" data-arg="${f.name}" type="${f.inputType}">`)}<button class="primary" style="margin-top:10px" data-action="run" data-name="${vm.e.name}">${vm.submitLabel}</button></div>`;
}

export function PmCommandsPanel({ menu, form, result }) {
  return html`<h2>⚙ Commandes PM <span style="color:var(--muted);font-weight:normal">(catalogue RM2209)</span> <button class="helpq" data-action="help" title="Aide sur ce panneau">?</button></h2><div id="pm-menu" style="margin-top:8px">${menu || ""}</div><div id="pm-form">${form || ""}</div><pre id="pm-result" class="logtail" style="${result ? "" : "display:none;"}margin-top:10px;max-height:220px;overflow-y:auto">${result || ""}</pre>`;
}
