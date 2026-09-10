// views/auth/Auth — la session connectée, les appareils enregistrés, les comptes (RM2334). Gestes en data-action, aucun on*. RM2889.
import { html, raw } from "../../core/html.js";

export function Me(user, admin) { return html`Connecté : <b>${user}</b>${admin ? raw(' <span class="pill">superadmin</span>') : ""}`; }

export function Devices(rows) {
  if (!rows.length) return "";
  return html`<div style="color:var(--muted);font-size:12px;margin-bottom:4px">Appareils enregistrés</div>${rows.map(x => html`<div class="kv" style="align-items:center;gap:6px"><span class="v">${x.name}${x.current ? " ← celui-ci" : ""}</span><span class="k">${x.user} · vu ${x.seen}</span><button class="mini" data-action="revoke" data-id="${x.id}" data-current="${x.current ? "1" : ""}">révoquer</button></div>`)}`;
}

export function Users(rows) {
  if (!rows.length) return html`<span style="color:var(--muted);font-size:12px">aucun compte normal — le superadmin vit dans le .env</span>`;
  return html`${rows.map(u => html`<div class="kv" style="align-items:center;gap:6px"><span class="v">${u.user}${u.disabled ? raw(' <span class="pill">désactivé</span>') : ""}</span><span class="k">${String(u.devices)} appareil(s)</span><button class="mini" data-action="user-toggle" data-user="${u.user}" data-disabled="${u.disabled ? "" : "1"}">${u.toggleLabel}</button><button class="mini" data-action="user-pw" data-user="${u.user}">mdp</button><button class="mini" data-action="user-del" data-user="${u.user}">✕</button></div>`)}`;
}
