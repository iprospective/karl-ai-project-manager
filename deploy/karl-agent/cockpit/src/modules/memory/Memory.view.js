// modules/memory/Memory.view — le panneau « mémoire » (tableau par module, courbes, alertes) et le bloc « sonde » des réglages.
// Gestes en data-action / data-cmd, aucun on*. RM3007.
import { html, raw } from "../../core/html.js";

const Toggle = (vm) => html`<button class="mini${vm.on ? " active" : ""}" data-action="toggle" title="${vm.on ? "Arrêter la sonde" : "Démarrer la sonde (ce navigateur)"}">${vm.on ? "■ arrêter" : "▶ démarrer"}</button>`;
const Interval = (vm) => html`<label class="mp-int">toutes les <select data-action="interval">${vm.intervals.map(i => html`<option value="${i.value}"${i.selected ? raw(" selected") : ""}>${i.label}</option>`)}</select></label>`;

export function Alerts(vm) {
  const a = vm.alerts; if (!a.length) return "";
  return html`<div class="mp-alerts">⚠ grimpe sans redescendre : ${a.map(x => html`<span class="mp-alert"><b>${x.module}</b> ${x.counter} ${String(x.from)} → ${String(x.to)}</span>`)}</div>`;
}

export function Table(vm) {
  const rows = vm.rows;
  if (!rows.length) return html`<div class="empty">${vm.on ? "premier échantillon en attente…" : "sonde désactivée — démarre-la pour mesurer chaque module"}</div>`;
  return html`<table class="mp-table"><thead><tr><th>module</th><th>montés</th><th>nœuds</th><th>courbe (nœuds)</th><th>retenus</th><th>store</th><th>abonnés</th><th>rendus/min</th></tr></thead><tbody>${rows.map(r => html`<tr class="${r.leaks.length ? "mp-leak" : ""}"><td class="mp-mod">${r.module}${r.leaks.length ? html` <span class="mp-flag" title="${r.leaks.join(", ")}">⚠</span>` : ""}</td><td>${String(r.mounted)}</td><td>${String(r.nodes)} <span class="mp-trend">${r.trend}</span></td><td>${r.spark ? html`<svg class="mp-spark" viewBox="0 0 120 24" width="120" height="24"><polyline points="${r.spark}"/></svg>` : ""}</td><td>${String(r.pending)} <span class="mp-trend">${r.pendingTrend}</span></td><td>${String(r.entries)}</td><td>${String(r.subscribers)}</td><td>${String(r.rate)}</td></tr>`)}</tbody></table>`;
}

export function Panel(vm) {
  const t = vm.total;
  return html`<h2>🧠 Mémoire par module <span class="mp-state">${vm.stateText}</span> <button class="helpq" data-action="help" title="Aide sur ce panneau">?</button></h2><div class="mp-bar">${Toggle(vm)}${Interval(vm)}<button class="mini" data-action="tick" title="Prendre un échantillon maintenant">⟳ maintenant</button><button class="mini" data-action="reset" title="Oublier l'historique">↺ vider</button><button class="mini" data-action="export" title="Télécharger l'historique (JSON)">⤓ JSON</button></div>${Alerts(vm)}${Table(vm)}${t ? html`<div class="mp-foot">${String(vm.samples)} échantillon(s) ${vm.sinceText} · ${String(t.mounted)} montage(s), ${String(t.nodes)} nœuds, ${String(t.pending)} retenu(s), ${String(t.entries)} entrée(s) de store${vm.heapText ? " · tas JS " + vm.heapText : ""}</div>` : ""}`;
}

/** Le bloc des réglages : activer, cadence, ouvrir le panneau. */
export function SettingsBlock(vm) {
  return html`<h2>🧠 Sonde mémoire <span style="color:var(--muted);font-weight:normal">(ce navigateur)</span></h2><label class="mp-opt"><input type="checkbox" data-action="toggle"${vm.on ? raw(" checked") : ""}> mesurer chaque module (nœuds, écouteurs, stores, rendus)</label>${Interval(vm)}<div class="mp-hint">${vm.stateText}. <button class="mini" data-cmd="panel" data-arg="memory">🧠 ouvrir le panneau</button></div>`;
}
