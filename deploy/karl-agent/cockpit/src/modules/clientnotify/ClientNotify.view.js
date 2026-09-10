// modules/clientnotify/ClientNotify.view — le menu des clients et la page « compte-rendu » d'un client.
// Gestes en data-action, aucun on*. RM3052.
import { html } from "../../core/html.js";

/** Le menu déroulant du bouton haut : un client par ligne, avec ce qu'il reste à lui annoncer. */
export function ClientMenu(vm) {
  if (vm.empty) return html`<button disabled>Rien à annoncer</button>`;
  return html`${vm.items.map(i => html`<button data-action="client" data-client="${i.client}" title="Ouvrir le compte-rendu de ${i.label}">${i.text}</button>`)}`;
}

const Ticket = (t) => html`<div class="cn-t${t.on ? " on" : ""}">
  <label class="cn-pick"><input type="checkbox" data-action="pick" data-rm="${t.id}"${t.on ? " checked" : ""}>
    <span class="cn-rm">RM${t.id}</span><span class="cn-title">${t.title}</span></label>
  <label class="cn-dem" title="Prévenir aussi le DEMANDEUR de ce ticket : il reçoit un email à part, ne contenant que ses tickets"><input type="checkbox" data-action="pickdem" data-rm="${t.id}"${t.dem ? " checked" : ""}${t.on ? "" : " disabled"}> demandeur</label>
  <span class="cn-since" title="En file depuis le passage en production">${t.queued_at}</span></div>`;

export function ClientReport(vm) {
  if (!vm.client) return html`<h2>✉ Compte-rendu client</h2><div class="empty">Choisissez un client dans le menu ✉ du bandeau.</div>`;
  if (vm.empty) return html`<h2>✉ Compte-rendu — ${vm.label}</h2><div class="empty">Aucune évolution en attente d'annonce pour ce client.</div>`;
  return html`<h2>✉ Compte-rendu — ${vm.label} <span class="cdc-count">${vm.count} / ${vm.total}</span></h2>
    <div class="cn-head">
      <div class="cn-to"><b>À :</b> ${vm.recipients.length ? vm.recipients.join(", ") : html`<span class="cn-warn">aucun destinataire résolu</span>`}
        ${vm.orphans.length ? html` <span class="cn-warn" title="Ces références d'annuaire n'existent pas : elles sont ignorées">⚠ ref inconnue : ${vm.orphans.join(", ")}</span>` : ""}</div>
      <div class="cn-opts">
        <button class="chip" data-action="all" data-on="${vm.allOn ? "0" : "1"}">${vm.allOn ? "Tout décocher" : "Tout cocher"}</button>
        <label class="chip" title="Inclure, pour chaque ticket, le protocole de test — « comment le vérifier » côté client"><input type="checkbox" data-action="proto"${vm.protocole ? " checked" : ""}> protocoles de test</label>
        <label class="chip" title="Prévenir le demandeur de CHAQUE ticket coché (chacun reçoit un email limité à ses tickets)"><input type="checkbox" data-action="alldem"${vm.allDemOn ? " checked" : ""}> prévenir les demandeurs</label>
        <button class="chip" data-action="reload" title="Relire la file">↻</button>
      </div>
    </div>
    ${vm.inactives.length ? html`<div class="cn-warn cn-note">Notification inactive sur : ${vm.inactives.join(", ")} — ces tickets n'ont pas de destinataire (<code>pm-client-notify config</code>).</div>` : ""}
    ${vm.groups.map(g => html`<div class="cn-group"><h3>${g.label}${g.actif ? "" : html` <span class="cn-warn">(option inactive)</span>`}</h3>${g.tickets.map(Ticket)}</div>`)}
    ${vm.multi ? html`<div class="cn-note">La sélection couvre plusieurs projets : <b>un seul email</b> partira, les évolutions groupées par projet.</div>` : ""}
    ${vm.demCount ? html`<div class="cn-note">${vm.demCount} demandeur(s) seront prévenus séparément — chacun ne reçoit que ses propres tickets.</div>` : ""}
    <div class="cn-actions">
      <button class="cn-send" data-action="send"${vm.canSend ? "" : " disabled"}>${vm.sendLabel}</button>
      <button data-action="dismiss"${vm.canDismiss ? "" : " disabled"} title="Sortir ces tickets de la file sans prévenir le client">${vm.dismissLabel}</button>
      ${vm.busy ? html`<span class="cn-busy">…</span>` : ""}<span class="cn-why">${vm.why}</span>
    </div>
    <div class="cn-test">
      <label class="cn-testlbl" for="cn-testto">Test d'envoi</label>
      ${vm.contacts.length ? html`<select class="cn-testsel" data-action="testpick" title="Choisir un contact de l'annuaire">
        <option value="">— contact —</option>${vm.contacts.map(c => html`<option value="${c.email}"${c.email === vm.testTo ? " selected" : ""}>${c.label}</option>`)}</select>` : ""}
      <input class="cn-testto" id="cn-testto" type="email" data-action="testto" value="${vm.testTo}" placeholder="adresse@exemple.fr" autocomplete="email">
      <button data-action="test"${vm.canTest ? "" : " disabled"} title="Envoyer CE compte-rendu à cette adresse, sans rien changer à la file">Envoyer un test</button>
      <span class="cn-why">${vm.testWhy}</span>
    </div>
    <h3 class="cn-prevh">Aperçu de l'email</h3>
    ${vm.preview ? html`<div class="cn-prev"><div class="cn-subj"><b>Objet :</b> ${vm.preview.subject}</div>
      ${vm.previewHtml ? html`<iframe class="cn-frame" sandbox="" title="Aperçu de l'email" srcdoc="${vm.previewHtml}"></iframe>`
        : html`<pre class="cn-body">${vm.preview.body}</pre>`}</div>`
      : html`<div class="empty">${vm.count ? "aperçu en cours…" : "Rien de coché : aucun email à prévisualiser."}</div>`}`;
}
