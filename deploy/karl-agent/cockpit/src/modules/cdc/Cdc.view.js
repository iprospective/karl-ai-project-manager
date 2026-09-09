// modules/cdc/Cdc.view — les trois pages centrales du CDC vivant. Gestes en data-action, aucun on*. RM3044.
import { html, raw } from "../../core/html.js";

export function CdcHeader(vm) {
  return html`<div class="cdc-head"><div class="cdc-pages" role="tablist">${vm.pages.map(p => html`<button class="chip${p.on ? " on" : ""}" data-action="page" data-page="${p.key}">${p.label}</button>`)}</div>
    ${vm.choices.length ? html`<div class="cdc-choices">${vm.choices.map(c => html`<button class="chip${c.on ? " on" : ""}" data-action="select" data-key="${c.key}" title="Changer de CDC">${c.label}</button>`)}</div>` : ""}
    <div class="cdc-ctx">${vm.context}</div></div>`;
}
const Empty = (vm) => vm.error ? html`<div class="empty">CDC injoignables : ${vm.error}</div>` : html`<div class="empty">Aucun CDC vivant : un projet en porte un dès qu'il a un <code>docs/cdc-&lt;prefix&gt;-00-sommaire.md</code> (<code>pm-cdc-features --init</code>).</div>`;

const Tickets = (ts) => html`${ts.map((t, i) => html`${i ? ", " : ""}<a href="#" class="cdcrm" data-action="ticket" data-rm="${t}">RM${t}</a>`)}`;

export function FeaturesPage(head, vm) {
  if (head.empty) return html`<h2>📋 Fonctionnalités</h2>${CdcHeader(head)}${Empty(head)}`;
  if (vm.missing) return html`<h2>📋 Fonctionnalités <span class="cdc-count">${head.title}</span></h2>${CdcHeader(head)}<div class="empty">Ce CDC n'a pas de registre de fonctionnalités (<code>pm-cdc-features --init --prefix …</code>).</div>`;
  const rows = vm.rows();
  return html`<h2>📋 Fonctionnalités <span class="cdc-count">${vm.count}</span></h2>${CdcHeader(head)}
    <div class="cdc-bar"><input class="cdc-q" type="search" data-action="q" placeholder="Filtrer (libellé, domaine, état, RM…)" value="${vm.query}" autocomplete="off">
      <span class="cdc-counts">${vm.counts.map(c => html`<span class="st ${c.cls}">${c.etat}</span> ${String(c.n)} `)}</span></div>
    <div class="cdc-hint">Cliquez un en-tête pour trier ; un second clic inverse. Le sélecteur d'une ligne change son état (prévu, en cours, en pause, écarté, livré) et fige l'entrée ; une fonctionnalité ne se supprime pas, elle s'écarte. La version (colonne) renvoie à la roadmap : une version = un rôle, jamais une copie de cette liste.</div>
    <div class="cdc-tablewrap"><table class="cdc-table"><thead><tr>${vm.cols.map(c => html`<th class="${c.on ? "on" : ""}" data-action="sort" data-key="${c.key}">${c.label}${c.arrow}</th>`)}</tr></thead>
    <tbody>${rows.map(r => html`<tr><td><b>${r.id}</b></td><td>${r.libelle}${r.parent ? html` <i class="cdc-sub">(sous-tâche de RM${String(r.parent)})</i>` : ""}</td><td class="cdc-dom">${r.domaine}</td><td>${Tickets(r.tickets)}</td><td class="cdc-dom">${r.type}</td>${vm.hasVersion ? html`<td>${r.version}</td>` : ""}<td><span class="st ${r.cls}">${r.etat}</span> <select class="mini cdc-fstate" data-action="feature-state" data-id="${r.id}" title="Changer l'état (l'entrée est alors figée : --sync ne la réécrit plus)"><option value="">…</option>${vm.featureStates.map(s => html`<option value="${s}">${s}</option>`)}</select></td><td class="cdc-date">${r.date}</td></tr>`)}</tbody></table></div>`;
}

export function ChaptersPage(head, vm, { md }) {
  if (head.empty) return html`<h2>📘 CDC</h2>${CdcHeader(head)}${Empty(head)}`;
  return html`<h2>📘 ${head.title} <span class="cdc-count">${(vm.tabs.find(t => t.on) || {}).title || ""}</span></h2>${CdcHeader(head)}
    <div class="cdc-body mdview-host" data-role="body">${raw(vm.anchored(md(vm.md)))}</div>`;
}
