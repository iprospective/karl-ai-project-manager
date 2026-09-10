// modules/sessproj/SessProj.view — l'onglet projets. Gestes en data-action, aucun on*. RM3045.
import { html } from "../../core/html.js";

export function SessProjPanel(vm) {
  if (vm.empty) return html`<div class="empty">${vm.emptyText}</div>`;
  return html`${vm.rows().map(p => html`<div class="sp-card">
    <div class="sp-head"><span class="sp-name">${p.name}</span><span class="sp-key">${p.key}</span>${p.branch ? html`<span class="sp-branch" title="branche courante">${p.branch}${p.dirty ? html` <i>·${String(p.dirty)}</i>` : ""}</span>` : ""}</div>
    <div class="sp-root" title="${p.root}">${p.root}</div>
    <div class="sp-actions"><button class="mini" data-action="overview" data-path="${p.overview}" data-name="${p.name}" title="La fiche du projet (overview) au centre">📄 fiche</button>
      <button class="mini" data-action="files" data-root="${p.root}" title="Parcourir les fichiers de ce projet (onglet fichiers)">📁 fichiers${p.docs ? html` <i>·${String(p.docs)} racines doc</i>` : ""}</button></div>
    ${p.cdcs.length ? p.cdcs.map(c => html`<div class="sp-cdc"><span class="sp-cdct" title="${c.title}">📘 ${c.title}</span>
      ${c.tabs.map(t => html`<button class="mini" data-action="cdc" data-key="${c.key}" data-page="${t.key}" ${t.enabled ? "" : "disabled"} title="${t.enabled ? t.label : "pas de registre de fonctionnalités"}">${t.label}</button>`)}</div>`)
      : html`<div class="sp-nocdc">pas de CDC vivant — <code>pm-cdc-features --init --prefix &lt;p&gt;</code> dans ce projet en crée un</div>`}
  </div>`)}`;
}
