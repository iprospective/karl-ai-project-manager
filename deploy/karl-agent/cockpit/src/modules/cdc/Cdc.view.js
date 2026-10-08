// modules/cdc/Cdc.view — les trois pages centrales du CDC vivant. Gestes en data-action, aucun on*. RM3044.
import { html, raw } from "../../core/html.js";

export function CdcHeader(vm) {
  return html`<div class="cdc-head"><div class="cdc-pages" role="tablist">${vm.pages.map(p => html`<button class="chip${p.on ? " on" : ""}" data-action="page" data-page="${p.key}">${p.label}</button>`)}</div>
    ${vm.choices.length ? html`<div class="cdc-choices">${vm.choices.map(c => html`<button class="chip${c.on ? " on" : ""}" data-action="select" data-key="${c.key}" title="Changer de CDC">${c.label}</button>`)}</div>` : ""}
    <div class="cdc-ctx">${vm.context}</div></div>`;
}
const Empty = (vm) => vm.error ? html`<div class="empty">CDC injoignables : ${vm.error}</div>` : html`<div class="empty">Aucun CDC vivant : un projet en porte un dès qu'il a un <code>docs/cdc.md</code> ou un <code>docs/cdc-&lt;prefix&gt;-00-sommaire.md</code> (<code>pm-cdc-features --init</code>).</div>`;

const Tickets = (ts) => html`${ts.map((t, i) => html`${i ? ", " : ""}<a href="#" class="cdcrm" data-action="ticket" data-rm="${t}">RM${t}</a>`)}`;

export function FeaturesPage(head, vm) {
  if (head.empty) return html`<h2>📋 Fonctionnalités</h2>${CdcHeader(head)}${Empty(head)}`;
  if (vm.missing) return html`<h2>📋 Fonctionnalités <span class="cdc-count">${head.title}</span></h2>${CdcHeader(head)}<div class="empty">Ce CDC n'a pas de registre de fonctionnalités (<code>pm-cdc-features --init</code>).</div>`;
  const rows = vm.rows();
  return html`<h2>📋 Fonctionnalités <span class="cdc-count">${vm.count}</span></h2>${CdcHeader(head)}
    <div class="cdc-bar"><input class="cdc-q" type="search" data-action="q" placeholder="Filtrer (libellé, domaine, état, RM…)" value="${vm.query}" autocomplete="off">
      <span class="cdc-counts">${vm.counts.map(c => html`<span class="st ${c.cls}">${c.etat}</span> ${String(c.n)} `)}${vm.sansTicket.n
        ? html`<button class="mini cdc-noticket${vm.sansTicket.on ? " on" : ""}" data-action="sans-ticket" title="${vm.sansTicket.aFaire
          ? String(vm.sansTicket.aFaire) + " fonctionnalité(s) sans ticket restent à faire — il leur en manque un"
          : "toutes soldées : sans ticket, ce sont des traces"}">${vm.sansTicket.on ? "✕ " : ""}sans ticket ${String(vm.sansTicket.n)}${vm.sansTicket.aFaire ? html` <b>· ${String(vm.sansTicket.aFaire)} à faire</b>` : ""}</button>`
        : ""}</span></div>
    <div class="cdc-hint">Cliquez un en-tête pour trier ; un second clic inverse. Le premier sélecteur d'une ligne la rattache à une <b>version</b> (une étape de travail : voir la feuille de route, où les versions se créent) ; le second change son <b>état</b> et fige l'entrée. Une fonctionnalité ne se supprime pas, elle s'écarte.</div>
    <div class="cdc-tablewrap"><table class="cdc-table"><thead><tr>${vm.cols.map(c => html`<th class="${c.on ? "on" : ""}" data-action="sort" data-key="${c.key}">${c.label}${c.arrow}</th>`)}</tr></thead>
    <tbody>${rows.map(r => html`<tr><td><b>${r.id}</b></td><td>${r.libelle}${r.parent ? html` <i class="cdc-sub">(sous-tâche de RM${String(r.parent)})</i>` : ""}</td><td class="cdc-dom">${r.domaine}</td><td>${r.tickets.length ? Tickets(r.tickets) : "—"}</td><td class="cdc-dom">${r.tech}</td><td class="cdc-dom">${r.type}</td><td class="cdc-ver">${r.version || "—"} <select class="mini" data-action="feature-version" data-id="${r.id}" title="Rattacher cette fonctionnalité à une version (étape de travail)"><option value="">version…</option>${vm.versions.map(v => html`<option value="${v}"${v === r.version ? " selected" : ""}>${v}</option>`)}${r.version ? html`<option value="-">— détacher —</option>` : ""}</select></td><td><span class="st ${r.cls}">${r.etat}</span> <select class="mini cdc-fstate" data-action="feature-state" data-id="${r.id}" title="Changer l'état (l'entrée est alors figée : --sync ne la réécrit plus)"><option value="">…</option>${vm.featureStates.map(s => html`<option value="${s}">${s}</option>`)}</select></td><td class="cdc-date">${r.date}</td></tr>`)}</tbody></table></div>`;
}

/** RM3060 : sur la feuille de route seulement — créer une version, ou compléter celle qu'on nomme.
 *  Une version est une ÉTAPE DE TRAVAIL : un rôle, et à quoi on sait qu'elle est passée. */
const VersionForm = (versions) => html`<div class="cdc-vform" data-role="vform">
  <b>Ajouter ou modifier une version</b>
  <div class="cdc-vrow">
    <input class="cdc-in" data-role="vid" placeholder="V1" title="Identifiant : lettres, chiffres, . et -" list="cdc-vlist">
    <datalist id="cdc-vlist">${versions.map(v => html`<option value="${v}"></option>`)}</datalist>
    <input class="cdc-in cdc-grow" data-role="vrole" placeholder="Ce que cette étape doit permettre">
    <input class="cdc-in cdc-grow" data-role="vcritere" placeholder="À quoi on sait qu'elle est passée">
    <select class="mini" data-role="vetat"><option value="">état…</option>${["prévu", "en cours", "en pause", "écarté", "livré"].map(s => html`<option value="${s}">${s}</option>`)}</select>
    <button class="mini" data-action="version-save">Enregistrer</button>
    <button class="mini cdc-del" data-action="version-drop" title="Retirer cette version du registre et des fonctionnalités qui la portent">Retirer</button>
  </div>
  <div class="cdc-hint">Les fonctionnalités se rattachent depuis l'onglet Fonctionnalités, colonne Version. Retirer une version ne supprime aucune fonctionnalité : elle les détache.</div>
</div>`;

export function ChaptersPage(head, vm, { md, versions }) {
  if (head.empty) return html`<h2>📘 CDC</h2>${CdcHeader(head)}${Empty(head)}`;
  return html`<h2>📘 ${head.title} <span class="cdc-count">${(vm.tabs.find(t => t.on) || {}).title || ""}</span></h2>${CdcHeader(head)}
    ${vm.isRoadmap ? VersionForm(versions || []) : ""}
    <div class="cdc-body mdview-host" data-role="body">${raw(vm.anchored(md(vm.md)))}</div>`;
}
