// modules/providers/Providers.view — le panneau Fournisseurs. Gestes en data-action, aucun on*. RM3068.
// Un champ de secret ne se PRÉREMPLIT JAMAIS : il n'affiche que « posée » ou « non renseignée », et remplace.
import { html } from "../../core/html.js";

const Secret = (inst, s, admin) => html`<div class="pv-secret">
  <span class="pv-skey" title="${s.var}">${s.label}</span>
  <span class="st ${s.set ? "ok" : ""}">${s.set ? "posée" : "non renseignée"}</span>
  <input type="password" class="pv-sval" autocomplete="new-password" placeholder="saisir pour remplacer"
         data-role="secret" data-name="${inst.name}" data-type="${inst.type}" data-key="${s.key}">
  <button class="mini" data-action="secret-save" data-name="${inst.name}" data-type="${inst.type}" data-key="${s.key}">enregistrer</button>
  ${admin ? html`<label class="pv-glob"><input type="checkbox" data-role="scope" data-name="${inst.name}" data-key="${s.key}"> global</label>` : ""}
  ${s.set ? html`<button class="mini pv-del" data-action="secret-unset" data-name="${inst.name}" data-type="${inst.type}" data-key="${s.key}" title="Effacer cette clé">✕</button>` : ""}
</div>`;

const Form = (vm, axis, type, inst) => {
  const champs = vm.formOf(type, inst && inst.fields ? Object.fromEntries(inst.fields.map(f => [f.k, f.v])) : {});
  return html`<div class="pv-form" data-role="form" data-axis="${axis}">
    <label>Nom <input class="pv-in" data-role="name" value="${inst ? inst.name : ""}" ${inst ? "readonly" : ""} placeholder="ex. ollama-strix"></label>
    <label>Type <select class="pv-in" data-role="type" data-axis="${axis}">${vm.typesOf(axis).map(t => html`<option value="${t.type}"${t.type === type ? " selected" : ""}>${t.label}</option>`)}</select></label>
    ${champs.map(f => html`<label>${f.label}${f.required ? " *" : ""} <input class="pv-in" data-role="field" data-name="${f.name}" value="${f.value}" placeholder="${f.help}"></label>`)}
    <div class="pv-actions"><button class="mini" data-action="save" data-axis="${axis}">${inst ? "Enregistrer" : "Ajouter"}</button>
      <button class="mini" data-action="cancel">Annuler</button></div></div>`;
};

export function ProvidersCard(vm) {
  if (vm.empty) return html`<h2>🔌 Fournisseurs</h2><div class="empty">catalogue indisponible</div>`;
  return html`<h2>🔌 Fournisseurs <span class="pv-count">${vm.count} instance(s) · ${vm.user}${vm.admin ? " · admin" : ""}</span></h2>
  <div class="cdc-hint">Les clés ne sont jamais relues : le panneau dit seulement si elles sont posées, et permet de les remplacer. Le rôle (primaire, secondaire) appartient au couple projet ↔ instance, pas à l'instance.</div>
  ${vm.axes().map(a => html`<div class="pv-axis">
    <h3>${a.label} <span class="pv-def">${a.def ? "défaut : " + a.def : "aucun défaut"}</span>
      <button class="mini" data-action="new" data-axis="${a.axis}">＋ instance</button></h3>
    ${a.creating ? Form(vm, a.axis, (vm.typesOf(a.axis)[0] || {}).type) : ""}
    ${a.instances.length ? a.instances.map(i => html`<div class="pv-inst${i.open ? " open" : ""}">
      <div class="pv-head"><button class="mini" data-action="toggle" data-name="${i.name}">${i.open ? "▾" : "▸"}</button>
        <span class="pv-name">${i.name}</span><span class="pv-type">${i.label}</span>
        ${i.isDefault ? html`<span class="st ok">défaut</span>` : html`<button class="mini" data-action="default" data-axis="${a.axis}" data-name="${i.name}">définir par défaut</button>`}
        ${i.local ? html`<span class="pv-local" title="déclarée depuis le cockpit (surcharge locale)">locale</span>` : ""}
        ${i.uses.length ? html`<span class="pv-uses">${String(i.uses.length)} projet(s)</span>` : ""}</div>
      ${i.open ? html`<div class="pv-body">
        <div class="pv-fields">${i.fields.map(f => html`<span><b>${f.k}</b> ${f.v}</span>`)}</div>
        ${i.secrets.length ? i.secrets.map(s => Secret(i, s, vm.admin)) : html`<div class="pv-nosecret">aucun secret pour ce type</div>`}
        ${i.uses.length ? html`<table class="cdc-table"><tbody>${i.uses.map(u => html`<tr><td>${u.project}</td><td><span class="st ${u.role === "primary" ? "ok" : ""}">${u.role === "primary" ? "primaire" : "secondaire"}</span></td><td class="cdc-dom">${u.params}</td></tr>`)}</tbody></table>`
          : html`<div class="pv-nosecret">utilisée par aucun projet</div>`}
        <div class="pv-actions"><button class="mini" data-action="edit" data-name="${i.name}" data-type="${i.type}" data-axis="${a.axis}">Modifier</button>
          <button class="mini pv-del" data-action="delete" data-name="${i.name}">Supprimer la déclaration</button></div>
      </div>` : ""}</div>`) : html`<div class="pv-nosecret">aucune instance déclarée</div>`}
  </div>`)}`;
}
