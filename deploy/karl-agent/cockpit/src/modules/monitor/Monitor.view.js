// modules/monitor/Monitor.view — le panneau supervision. Gestes en data-action, aucun on*. RM3112.
import { html } from "../../core/html.js";

const Head = (vm) => html`<div class="cdc-head"><div class="cdc-pages" role="tablist">${vm.pages.map(p => html`<button class="chip${p.on ? " on" : ""}" data-action="page" data-page="${p.key}">${p.label}</button>`)}</div>
  <div class="mon-filtres">${vm.seuils.map(s => html`<button class="chip${s.on ? " on" : ""}" data-action="seuil" data-seuil="${String(s.value)}">${s.label}</button>`)}</div></div>`;

const Alerte = (r) => html`<tr class="${r.grave ? "mon-grave" : ""}">
  <td><span class="st ${r.cls}">${r.severityLabel}</span></td>
  <td class="mon-host" title="${r.hostName}">${r.host || "—"}</td>
  <td>${r.name}</td>
  <td class="cdc-date">${r.since}</td>
  <td>${r.cible ? html`<span class="mon-cible${r.devine ? " devine" : ""}" title="${r.devine ? "proposé : " + r.source : "association confirmée"}">${r.cible}</span>` : html`<span class="mon-manque">${r.manque}</span>`}</td>
  <td class="cdc-act">${r.ticketable
    ? html`<button class="mini" data-action="ticket" data-id="${r.id}" title="Ouvrir un ticket chez ${r.cible}">＋ ticket</button>`
    : html`<button class="mini soft" data-action="page" data-page="hosts" title="${r.manque}">associer…</button>`}</td>
</tr>`;

const Hote = (vm, h) => html`<tr>
  <td class="mon-host">${h.host}${h.actif ? "" : html` <span class="st off">désactivé</span>`}</td>
  <td>${h.client ? html`<span class="mon-cible${h.confirmee ? "" : " devine"}" title="${h.confirmee ? "confirmée" : h.source}">${h.client}${h.project ? "/" + h.project : ""}</span>` : html`<span class="mon-manque">—</span>`}</td>
  <td class="cdc-dom">${h.confirmee ? "confirmée" : h.source}</td>
  <td class="cdc-act">
    <select class="mini" data-action="assign-client" data-host="${h.host}" title="Associer cet hôte à un client"><option value="">client…</option>${vm.clients.map(c => html`<option value="${c}"${c === h.client ? " selected" : ""}>${c}</option>`)}</select>
    <input class="mini mon-proj" data-role="project" data-host="${h.host}" value="${h.project}" placeholder="projet" title="Projet du client (laisser vide si un seul)">
    <button class="mini" data-action="assign-save" data-host="${h.host}">confirmer</button>
    ${h.client ? html`<button class="mini cdc-del" data-action="assign-clear" data-host="${h.host}" title="Retirer l'association">✕</button>` : ""}
  </td>
</tr>`;

export function MonitorCard(vm) {
  const c = vm.counts;
  const titre = html`<h2>🩺 Supervision <span class="cdc-count">${String(c.total)} alerte(s)${c.grave ? " · " + String(c.grave) + " grave(s)" : ""}${c.sans_cible ? " · " + String(c.sans_cible) + " sans client" : ""}</span></h2>`;
  if (vm.error) return html`${titre}${Head(vm)}<div class="empty">observateur injoignable : ${vm.error}</div>`;
  if (vm.page === "hosts") {
    return html`${titre}${Head(vm)}
      <div class="cdc-hint">L'association d'un hôte à un client se <b>propose</b> (par le nom de domaine) et se <b>confirme</b> à la main. Une association proposée est affichée en clair : tant qu'elle n'est pas confirmée, elle peut se tromper de client. Confirmer une association la fige : aucune règle ne la réécrit ensuite.</div>
      <div class="cdc-tablewrap"><table class="cdc-table"><thead><tr><th>Hôte</th><th>Client / projet</th><th>Origine</th><th></th></tr></thead>
      <tbody>${vm.hostRows.map(h => Hote(vm, h))}</tbody></table></div>`;
  }
  if (vm.empty) return html`${titre}${Head(vm)}<div class="empty">rien à signaler à ce seuil.</div>`;
  return html`${titre}${Head(vm)}
    <div class="cdc-hint">Ce que l'observateur rapporte, pas ce qu'il conclut : vérifier les métriques avant de conclure sur une cause. Le bouton <b>＋ ticket</b> ouvre un ticket chez le client associé à l'hôte ; si l'hôte n'est associé à rien, il faut le faire d'abord.</div>
    <div class="cdc-tablewrap"><table class="cdc-table"><thead><tr><th>Sévérité</th><th>Hôte</th><th>Alerte</th><th>Depuis</th><th>Client / projet</th><th></th></tr></thead>
    <tbody>${vm.rows().map(Alerte)}</tbody></table></div>`;
}
