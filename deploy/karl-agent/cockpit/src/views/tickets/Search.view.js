// views/tickets/Search — les résultats de recherche (RM2770/2795/2830). Gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";

export function SearchResults(vm, { titleLink, pin }) {
  if (vm.empty) return html`<div class="empty">aucun résultat</div>`;
  return html`${vm.rows().map(r => html`<li title="${r.tip}" data-action="${r.absent ? "redmine" : "pick"}" data-rm="${r.rm}"${r.url ? html` data-url="${r.url}"` : ""}><div class="r-top"><span class="r-id">RM${r.rm}</span>${raw(pin("review", r.rm))}<span class="r-title">${raw(titleLink(r.rm, r.title))}</span></div><div class="r-meta">${r.meta}</div></li>`)}`;
}
/** Options d'un sélecteur ; `options` = chaînes ou {value,label} ; la valeur courante reste sélectionnée si elle existe. */
export function Options(options, current, allLabel) {
  return html`<option value="">${allLabel}</option>${options.map(o => { const v = typeof o === "string" ? o : o.value, l = typeof o === "string" ? o : o.label; return html`<option value="${v}"${v === current ? " selected" : ""}>${l}</option>`; })}`;
}
