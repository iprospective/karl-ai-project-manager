// views/tickets/MergeBanner — la bannière de cohérence git d'un ticket livré (RM2384). Reprise telle quelle.
import { html } from "../../core/html.js";
const ICON = { ok: "✅", warn: "⚠️", block: "⛔", unknown: "❔" };
export function MergeBanner(mc) {
  if (!mc || !mc.verdict) return "";
  const v = mc.verdict, lvl = v.level || "unknown";
  return html`<div class="mcbanner mc-${lvl}"><div class="mc-head">${ICON[lvl] || ""} ${v.headline || ""}</div>${v.detail ? html`<div class="mc-detail">${v.detail}</div>` : ""}${v.advice ? html`<div class="mc-advice">→ ${v.advice}</div>` : ""}${mc.mr_url ? html`<div class="mc-mr"><a href="${mc.mr_url}" target="_blank">MR ↗</a></div>` : ""}</div>`;
}
