// views/tickets/TicketsPanel — la carte « Tickets ouverts » et la liste de triage ROI. Balisage repris ; gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";
const muted = "color:var(--muted)";

export function OpenedList(vm, { tip, pin }) {
  if (!vm.total) return html`<div style="${muted};font-size:11.5px">Aucun ticket ouvert pour l'instant. Ceux que tu consultes s'empilent ici.</div>`;
  const clear = html`<span style="flex:1"></span><button class="mini" data-action="clear" title="Vider la liste">✕ vider</button>`;
  const groups = vm.groups();
  return html`${vm.clients.length > 1
    ? html`<div class="cmpbar" style="flex-wrap:wrap;margin-bottom:6px"><button class="mini${vm.clientAll ? " primary" : ""}" data-action="client" data-client="">tous</button>${vm.clients.map(c => html`<button class="mini${c.active ? " primary" : ""}" data-action="client" data-client="${c.key}">${c.key}</button>`)}${clear}</div>`
    : html`<div class="cmpbar" style="margin-bottom:6px">${clear}</div>`}${vm.families.length > 1
    ? html`<div class="cmpbar" style="flex-wrap:wrap;margin-bottom:6px"><button class="mini${vm.familyAll ? " primary" : ""}" data-action="family" data-family="">tous</button>${vm.families.map(f => html`<button class="mini${f.active ? " primary" : ""}" data-action="family" data-family="${f.key}">${f.label} (${f.n})</button>`)}</div>` : ""}${groups.map(g =>
    html`<div style="margin:6px 0 2px;${muted};font-size:10.5px">${g.label} (${g.items.length})</div>${g.items.map(it =>
      html`<div class="oline otix" data-action="open" data-rm="${it.rm}" title="Ouvrir la fiche"><div class="otix-head"><span class="pill"${raw(tip(it.rm))}>RM${it.rm}</span>${raw(pin("review", it.rm))}<span class="pill" style="opacity:.85">${it.status}</span><span style="flex:1"></span><button class="mini" title="Retirer de la liste" data-action="forget" data-rm="${it.rm}">✕</button></div><div class="otix-title">${it.title}</div></div>`)}`)}${!groups.length
    ? html`<div style="${muted};font-size:11.5px">aucun ticket dans ce filtre — « tous » les ramène.</div>` : ""}`;
}

export function TriageRow(r) {
  return html`<div class="tr-row" data-action="open" data-rm="${r.rm}" title="Ouvrir la fiche du ticket"><span class="tr-rank">${r.rank}</span><span class="tr-score" title="score ROI = gain € × priorité / coût">${r.score}</span><span class="tr-rm">RM${r.rm}</span><span class="tr-title">${r.title}</span><span class="tr-meta"><span class="pill">${r.status}</span> <span class="tr-prio tr-prio-${r.priority}">${r.priority}</span>${r.time ? html` <span class="tr-time">${r.time}</span>` : ""}${r.badges.length ? html` ${r.badges.map((b, i) => html`${i ? " " : ""}<span class="tr-badge ${b.cls}" title="${b.tip}">${b.text}</span>`)}` : ""}</span></div>`;
}

export function TriageList(vm) {
  if (!vm.count) return html`<div style="${muted}">aucun ticket ouvert avec ces filtres</div>`;
  return html`<div class="tr-count">${vm.count} ticket(s) · triés par levier ROI</div>${vm.shown.map(TriageRow)}${vm.more ? html`<div class="tr-more">… ${vm.more} de plus (affine les filtres)</div>` : ""}`;
}

/** Les options d'un <select> de filtre, la valeur courante préservée si elle existe encore. */
export function FilterOptions(values, current, allLabel) {
  return html`<option value="">${allLabel}</option>${values.map(v => html`<option value="${v}"${v === current ? " selected" : ""}>${v}</option>`)}`;
}
