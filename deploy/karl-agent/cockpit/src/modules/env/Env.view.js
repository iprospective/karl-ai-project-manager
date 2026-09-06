// views/env — badge, page de santé, formulaire des verrous. RM2889, L5.
// Balisage repris d'envWarnBadge, envStatusHtml/GroupHtml, vaultFormHtml ; gestes en
// data-action. La commande de remédiation n'entre JAMAIS dans un attribut : le
// bouton « copier » lit le <code> voisin (data-action="copy").
import { html } from "../../core/html.js";

export function EnvBadge(vm) {
  if (!vm.count) return "";
  return html`<span class="pill ${vm.cls}" title="${vm.title}">🩺 ${vm.count}</span>`;
}

const ICON = { ok: "✓", info: "·", warn: "!", error: "✗" };
const Badge = (e, w) => html`${e ? html` <span class="es-badge es-error">✗ ${e}</span>` : ""}${w ? html` <span class="es-badge es-warn">! ${w}</span>` : ""}`;
const Row = (c) => { const lv = c.level || "info"; return html`<div class="es-row es-${lv}"><span class="es-mark">${ICON[lv] || "·"}</span><span class="es-label">${c.label || ""}</span>${c.detail ? html`<span class="es-detail">${c.detail}</span>` : ""}${c.fix
  ? html`<div class="es-fixrow"><code class="es-fix">${c.fix}</code><button class="es-copy" data-action="copy" title="Copier la commande">copier</button></div>` : ""}</div>`; };

export function EnvStatus(vm) {
  if (vm.unavailable) return html`<div class="es-detail">état indisponible</div>`;
  const s = vm.counts;
  return html`<div class="es-head"><span style="color:var(--ok)">✓ ${s.ok || 0}</span> · <span style="color:var(--warn)">! ${s.warn || 0}</span> · <span style="color:#f85149">✗ ${s.error || 0}</span>${vm.generatedAt ? html`<span class="es-when">${vm.generatedAt}</span>` : ""}</div><div class="rsub">${vm.tabs.map(t =>
    html`<button class="${t.name === vm.current ? "active" : ""}" data-action="tab" data-tab="${t.name}">${t.name}${Badge(t.error, t.warn)}</button>`)}</div><div class="es-group">${vm.flat
    ? (vm.group.checks || []).map(Row)
    : vm.sections.map(s => !s.name ? s.checks.map(Row)
      : html`<details class="es-sec"${s.bad ? " open" : ""}><summary>${s.name} <span class="es-seccnt">${s.checks.length}</span>${Badge(s.error, s.warn)}</summary>${s.checks.map(Row)}</details>`)}</div>`;
}

export function EnvStatusPage(body) {
  return html`<div class="es-bar"><button class="mini" data-action="refresh" title="Relancer le diagnostic">↻ rafraîchir</button><span class="es-hint">outils · secrets · git/GitLab · SSH · PM — chaque défaut porte sa commande</span></div><div id="es-body"${body === undefined ? ' style="color:var(--muted)"' : ""}>${body === undefined ? "diagnostic en cours…" : body}</div>`;
}

export function EnvStatusError(message) {
  return html`<div class="es-row es-error"><span class="es-mark">✗</span><span class="es-detail">échec du diagnostic : ${message}</span></div>`;
}

export function VaultForm(vm) {
  if (!vm.secure) return html`<div class="es-row es-error"><span class="es-mark">✗</span><span class="es-detail">Connexion non sécurisée : un mot de passe maître ne se tape pas dans une page en clair. Ouvre le cockpit en <b>https</b> (ou depuis la machine même) puis réessaie.</span></div>`;
  return html`<div class="vlt-sec"><h3>🔐 Coffre de secrets</h3>${!vm.daemon ? html`<div class="es-detail">Agent non démarré — le déverrouillage le lancera.</div>` : ""}${vm.instances.map(i =>
    html`<div class="es-row ${i.unlocked ? "es-ok" : "es-warn"}"><span class="es-mark">${i.unlocked ? "✓" : "!"}</span><span class="es-label">${i.slug}</span><span class="es-detail">${i.unlocked ? "ouvert" + (i.since ? " depuis " + i.since : "") : "verrouillé"}</span></div>`)}${vm.needsUnlock
    ? html`<div class="vlt-form">${vm.choices.length > 1 ? html`<select id="vlt-inst" class="mini">${vm.choices.map(s => html`<option value="${s}">${s}</option>`)}</select>` : html`<input type="hidden" id="vlt-inst" value="${vm.choices[0]}">`}<input id="vlt-pass" type="password" autocomplete="off" placeholder="mot de passe maître" data-enter="unlock"><button class="mini" data-action="unlock">Déverrouiller</button></div><div class="vlt-note">Le mot de passe n'est pas mémorisé : il sert à ouvrir le coffre, puis il est oublié. Le coffre se reverrouille de lui-même après inactivité.</div>` : ""}</div><div class="vlt-sec"><h3>🔑 Agent SSH</h3>${!vm.ssh.reachable
    ? html`<div class="es-row es-error"><span class="es-mark">✗</span><span class="es-detail">agent injoignable — rien à charger tant qu'il ne tourne pas</span></div>`
    : vm.keys.length ? vm.keys.map(k => html`<div class="es-row es-ok"><span class="es-mark">✓</span><span class="es-label">${k.comment || k.hash}</span><span class="es-detail">${k.type || ""} ${k.bits || ""}</span></div>`)
    : html`<div class="es-row es-warn"><span class="es-mark">!</span><span class="es-detail">aucune clé chargée</span></div>`}${vm.canAddKey
    ? html`<div class="vlt-form"><select id="vlt-key" class="mini">${vm.candidates.map(k => html`<option value="${k}">${k}</option>`)}</select><input id="vlt-kpass" type="password" autocomplete="off" placeholder="passphrase de la clé" data-enter="sshadd"><button class="mini" data-action="sshadd">Charger</button></div>` : ""}</div>`;
}
