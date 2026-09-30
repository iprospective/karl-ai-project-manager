// views/health — badge d'en-tête et page de santé du système PM (RM3369).
// Le balisage reprend celui de la santé du poste (classes .es-*) : c'est le même
// objet à l'écran — des familles, des lignes, une commande à copier — et deux
// styles pour la même chose se seraient mis à diverger. La commande de
// remédiation n'entre JAMAIS dans un attribut : le bouton lit le <code> voisin.
import { html } from "../../core/html.js";

export function HealthBadge(vm) {
  if (!vm.show) return "";
  return html`<span class="pill ${vm.cls}" title="${vm.title}">🩺 ${vm.count}</span>`;
}

const ICON = { ok: "✓", info: "·", warn: "!", error: "✗" };
const Badge = (e, w) => html`${e ? html` <span class="es-badge es-error">✗ ${e}</span>` : ""}${w ? html` <span class="es-badge es-warn">! ${w}</span>` : ""}`;
const Row = (c) => { const lv = c.level || "info"; return html`<div class="es-row es-${lv}"><span class="es-mark">${ICON[lv] || "·"}</span><span class="es-label">${c.label || ""}</span>${c.detail ? html`<span class="es-detail">${c.detail}</span>` : ""}${c.fix
  ? html`<div class="es-fixrow"><code class="es-fix">${c.fix}</code><button class="es-copy" data-action="copy" title="Copier la commande">copier</button></div>` : ""}</div>`; };

export function HealthStatus(vm) {
  if (vm.unavailable) return html`<div class="es-detail">aucun rapport de santé PM — lance <code class="es-fix">scripts/pm-health-report.py</code></div>`;
  const s = vm.counts;
  return html`<div class="es-head"><span style="color:var(--ok)">✓ ${s.ok || 0}</span> · <span style="color:var(--warn)">! ${s.warn || 0}</span> · <span style="color:#f85149">✗ ${s.error || 0}</span><span class="es-when">${vm.headline}${vm.age ? " — calculé " + vm.age : ""}</span></div><div class="rsub">${vm.tabs.map(t =>
    html`<button class="${t.name === vm.current ? "active" : ""}" data-action="tab" data-tab="${t.name}">${t.name}${Badge(t.error, t.warn)}</button>`)}</div><div class="es-group">${vm.flat
    ? (vm.group.checks || []).map(Row)
    : vm.sections.map(s => !s.name ? s.checks.map(Row)
      : html`<details class="es-sec"${s.bad ? " open" : ""}><summary>${s.name} <span class="es-seccnt">${s.checks.length}</span>${Badge(s.error, s.warn)}</summary>${s.checks.map(Row)}</details>`)}</div>`;
}

export function HealthPage(body) {
  return html`<div class="es-bar"><button class="mini" data-action="refresh" title="Relire le dernier rapport">↻ rafraîchir</button><span class="es-hint">champs Redmine par projet · miroirs sans champ en face · cohérence des projets · normes — chaque défaut porte sa commande</span></div><div id="ph-body"${body === undefined ? ' style="color:var(--muted)"' : ""}>${body === undefined ? "lecture du rapport…" : body}</div>`;
}

export function HealthError(message) {
  return html`<div class="es-row es-error"><span class="es-mark">✗</span><span class="es-detail">santé PM illisible : ${message}</span></div>`;
}
