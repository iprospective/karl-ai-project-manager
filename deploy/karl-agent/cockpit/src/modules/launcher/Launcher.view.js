// views/launcher/Launcher — la ligne de résolution du lanceur et les options des sélecteurs. Gestes en data-*. RM2889.
import { html } from "../../core/html.js";

export function ResolvedLine(line) {
  if (!line) return "";
  if (!line.found) return html`${line.text}`;
  return html`${line.text}${line.closed ? html` <button class="mini" data-action="reopen" title="Rouvrir le ticket (ferme → a_faire, motif requis)">↻ Rouvrir</button>` : ""}`;   // RM2285
}
export function Options(options, current, allLabel) {
  return html`${allLabel != null ? html`<option value="">${allLabel}</option>` : ""}${options.map(o => html`<option value="${o.value}"${(current != null ? o.value === current : !!o.selected) ? " selected" : ""}>${o.label}</option>`)}`;
}
