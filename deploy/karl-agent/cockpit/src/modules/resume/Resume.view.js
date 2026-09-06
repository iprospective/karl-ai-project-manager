// views/sessions/Resume — la liste des sessions reprenables, la note des archivées, les options des filtres. Gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";

export function ResumeList(vm, { markPill }) {
  const arch = ArchivedNote(vm);
  if (vm.empty) return html`<div class="empty">${vm.emptyText}</div>${arch}`;
  return html`${vm.rows().map(r => html`<li title="${r.tip}" data-action="resume" data-sid="${r.id}"><div class="r-top">${raw(markPill(r.mark))}<span class="r-title">${r.title}</span>${r.transcript ? html` <span class="pill" title="Trouvé dans le transcript de la conversation">transcript</span>` : ""}<button class="r-move" title="Déplacer cette session vers un autre projet" data-action="move" data-sid="${r.id}">⇄</button></div><div class="r-meta">${r.where}${r.tickets ? " · " + r.tickets : ""} · ${r.age}${r.live ? html` · <span class="pill ok">tmux vivant</span>` : ""}</div></li>`)}${arch}`;
}
export function ArchivedNote(vm) {
  const a = vm.archived();
  if (!a.length) return "";
  return html`<div class="rs-archived">${a.length} session(s) archivée(s) correspondent aussi — worklog conservé, transcript disparu : <b>non reprenables</b>.${a.map(s => html`<div>· <code>${s.id}</code>${s.updated ? " " + s.updated : ""}${s.refs ? " — " + s.refs : ""}</div>`)}</div>`;
}
export function SelectOptions(options, current, allLabel) {
  return html`<option value="">${allLabel}</option>${options.map(o => { const v = typeof o === "string" ? o : o.value, l = typeof o === "string" ? o : o.label; return html`<option value="${v}"${v === current ? " selected" : ""}>${l}</option>`; })}`;
}
