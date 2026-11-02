// views/mail/MailPanel — le panneau « Emails » entier : barre d'outils + file.
// RM2889, L1. Reprend le bloc HTML #lp-mail d'index.html, gestes en data-action.

import { html } from "../../core/html.js";
import { EmailCard } from "./EmailCard.view.js";

export function MailList(vms) {
  if (!vms.length) return html`<div class="empty">file vide — « 📥 Relever » interroge la boîte de karl</div>`;
  return html`${vms.map(EmailCard)}`;
}

/** RM3319 — les envois de karl rejetés, encore ouverts dans le fil : en tête du panneau, en rouge. */
export function BounceList(bounces) {
  if (!bounces || !bounces.length) return "";
  return html`<div class="mail-bounces">
    <b>⚠ ${bounces.length} envoi(s) de karl rejeté(s)</b> — le destinataire ne l'a PAS reçu.
    <ul>${bounces.map(b => html`<li>${b.msg}${b.rm ? html` <a class="feed-rm" href="#" data-action="ticket" data-key="${b.rm}" title="Ouvrir la fiche du ticket">RM${b.rm}</a>` : ""}</li>`)}</ul>
    <span class="mail-bounces-aide">Corriger l'adresse (annuaire 👤), renvoyer, puis marquer l'alerte « traitée » dans le fil 🔔.</span>
  </div>`;
}

export function MailPanel({ vms, pending, done, fullBody, error, bounces = [] }) {
  const lbl = "display:flex;align-items:center;gap:4px;font-size:11px;color:var(--muted)";
  return html`<div class="card">
    <h2>📧 Emails <span id="mail-count" style="color:var(--muted);font-weight:normal">${pending ? "— " + pending + " à traiter" : ""}</span>
      <button class="helpq" data-action="help" title="Aide sur ce panneau">?</button></h2>
    <div style="margin:8px 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
      <button class="mini" data-action="fetch" title="Relève la boîte en IMAP (lecture seule) et alimente la file">📥 Relever</button>
      <button class="mini" data-action="route" title="Propose client/projet pour chaque email de la file">🎯 Router</button>
      <label style="${lbl}" title="Envoie le corps ENTIER de l'email au modèle : propositions nettement plus précises, mais le contenu sort du poste">
        <input type="checkbox" id="mail-fullbody" style="width:auto"${fullBody ? " checked" : ""}> corps entier</label>
      <label style="${lbl}" title="Afficher aussi les emails déjà traités ou écartés">
        <input type="checkbox" id="mail-done" style="width:auto"${done ? " checked" : ""}> traités</label>
      <button class="mini" data-action="refresh" title="Rafraîchir la file">↻</button>
    </div>
    ${BounceList(bounces)}
    <div id="mail-list">${error ? html`<div class="empty">${error}</div>` : MailList(vms)}</div>
  </div>`;
}
