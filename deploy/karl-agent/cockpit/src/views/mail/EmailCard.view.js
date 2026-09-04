// views/mail/EmailCard — un email de la file, niveau « card ». RM2889, L1.
//
// Rend depuis un EmailViewModel, rien d'autre. Plus aucun onclick : chaque
// geste est un `data-action` que le contrôleur attrape par délégation — donc
// un écouteur POSÉ, donc retirable (core/dom.js). Le balisage et les styles
// inline sont repris tels quels de renderMailList : un lot déplace.

import { html } from "../../core/html.js";

const muted = "color:var(--muted);font-size:11px";

export function EmailCard(vm) {
  return html`<div class="card" data-key="${vm.e.key}" style="margin-bottom:6px${vm.open ? ";border-color:var(--accent)" : ""}">
    <div style="display:flex;gap:6px;align-items:baseline;cursor:pointer" data-action="toggle">
      <span title="${vm.state}">${vm.badge}</span>
      <b style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">${vm.title}</b>
      <span style="${muted}">${vm.day}</span>
    </div>
    <div style="${muted};margin-top:2px">${vm.sender} — ${vm.e.folder}${vm.e.attachments ? " · 📎" + vm.e.attachments : ""}</div>
    <div style="margin-top:4px;font-size:11px">🎯 <b>${vm.target}</b>${vm.confidence
      ? html` <span style="color:var(--muted)">${vm.confidence} · ${vm.source}</span>` : ""}${vm.e.rm_id
      ? html` · <span title="réponse dans un fil existant">↩ RM${vm.e.rm_id}</span>` : ""}${vm.e.created_rm
      ? html` · <b>→ RM${vm.e.created_rm}</b>` : ""}</div>
    ${vm.dismissedReason !== null ? html`<div style="${muted}">⊘ écarté — ${vm.dismissedReason}</div>` : ""}
    ${vm.open ? Opened(vm) : ""}
  </div>`;
}

function Opened(vm) {
  return html`${vm.hasDraft ? html`
    <div style="margin-top:8px;border-top:1px solid var(--line);padding-top:6px">
      <div style="${muted}">proposition${vm.draftConfidence ? " · " + vm.draftConfidence : ""}${vm.draft.actionable === false ? html` · <b>non actionnable</b>` : ""}</div>
      <label>Titre</label><input id="ml-title" value="${vm.draft.title}">
      <label>Projet</label><input id="ml-project" value="${vm.draftProject}" placeholder="client/projet">
      <label>Priorité</label><select id="ml-prio">${vm.priorities.map(p =>
        html`<option${p === vm.draftPriority ? " selected" : ""}>${p}</option>`)}</select>
      ${vm.warnings.map(w => html`<div style="font-size:11px;color:var(--warn)">⚠ ${w}</div>`)}
      <div style="font-size:11px;white-space:pre-wrap;margin-top:6px;color:var(--muted)">${vm.description}</div>
    </div>` : ""}
    ${vm.e.body ? html`<details style="margin-top:6px"><summary style="font-size:11px">corps de l'email</summary>
      <div style="font-size:11px;white-space:pre-wrap;max-height:220px;overflow:auto">${vm.e.body}${vm.e.body_truncated ? "\n…(tronqué à la relève)" : ""}</div></details>` : ""}
    <div style="margin-top:8px;display:flex;gap:4px;flex-wrap:wrap">${vm.actions().map(a =>
      html`<button class="mini${a.primary ? " primary" : ""}" data-action="${a.id}" title="${a.title || ""}">${a.label}</button>`)}</div>`;
}
