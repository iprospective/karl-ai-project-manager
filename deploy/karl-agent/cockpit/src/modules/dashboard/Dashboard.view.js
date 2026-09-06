// views/dashboard/Dashboard — « ce qui requiert ton attention ». RM2889, L4.
// Balisage repris de renderDashboard / attentionHtml / alertsHtml (RM2697, RM2698,
// RM2744) ; gestes en data-action. La dérive s'affiche AVANT l'état.
import { html } from "../../core/html.js";

export function Attention(vm) {
  const secs = vm.sections();
  if (!secs.length) return html`<div class="dash-empty">✓ rien n’attend de toi.<br><span style="font-size:12px">Les tickets en cours avancent dans leurs sessions ; le worklog projet donne le détail.</span></div>`;
  return html`<div class="dash-sum">${vm.chips().map(c => html`<span class="dash-chip" title="${c.label}">${c.icon} ${c.count}</span>`)}</div>${secs.map(s =>
    html`<div class="dash-sec">${s.label} (${s.total})</div>${s.rows.map(r =>
      html`<div class="dash-row"${r.action ? html` data-action="${r.action}" data-arg="${r.action === "open" ? r.url : r.action === "attach" ? r.sid : r.rm_id}"` : ""}><span class="dash-icon">${r.icon}</span><span class="dash-verb">${r.verb}</span><span class="dash-who">${r.client + "/" + r.project}</span>${r.rm_id ? html`<span class="r-id">RM${String(r.rm_id)}</span> ` : ""}<span class="dash-txt">${String(r.text || "")}</span>${r.since ? html`<span class="dash-since" title="dernière activité">${String(r.since).slice(0, 10)}</span>` : ""}</div>`)}${s.more
      ? html`<div class="dash-more">… et ${s.more} autre(s) — les plus anciens sont listés en premier</div>` : ""}`)}`;
}

export function Alerts(vm) {
  const as = vm.alerts();
  if (!as.length) return "";
  return html`<div class="dash-alerts"><div class="dash-sec" style="margin-top:0">⚠ dérives (${vm.alertTotal})</div>${as.map(a =>
    html`<div class="alert-row"><span class="dash-icon">${a.icon}</span><span class="alert-age" title="temps écoulé depuis la dernière activité">${a.age} j</span><span class="dash-who">${a.who}</span>${a.rm_id
      ? html`<span class="r-id" style="cursor:pointer" data-action="review" data-arg="${String(a.rm_id)}">RM${String(a.rm_id)}</span> ` : ""}<span class="dash-txt">${String(a.label || "")}${a.title ? " — " + String(a.title) : ""}</span>${a.url
      ? html`<a class="pill" href="${String(a.url)}" target="_blank" rel="noopener">ouvrir ↗</a>` : ""}<button class="mini" title="Reporter cette alerte de 7 jours (elle reviendra)" data-action="snooze" data-arg="${String(a.key)}">⏳ 7 j</button></div>`)}${vm.alertHidden
    ? html`<div class="dash-more">… et ${vm.alertHidden} dérive(s) plus récente(s) — les seuils se règlent dans 🔧 réglages</div>` : ""}</div>`;
}

const opt = (v, cur) => html`<option value="${v}"${v === cur ? " selected" : ""}>${v || "tous"}</option>`;

export function Dashboard(vm) {
  return html`<div class="dash-head"><b>Ce qui requiert ton attention</b><span class="dash-cnt">${vm.rows.length}</span><select data-filter="client">${[""].concat(vm.clients).map(c => opt(c, vm.filter.client))}</select><select data-filter="project">${[""].concat(vm.projects).map(p => opt(p, vm.filter.project))}</select><button class="mini" data-action="refresh" title="Recalculer">⟳</button></div>${Alerts(vm)}${Attention(vm)}`;
}
