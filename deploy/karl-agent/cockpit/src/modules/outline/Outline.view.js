// views/outline/Outline — la minimap de conversation : lignes décorées, recherche surlignée, lecture inline en accordéon. RM2889.
import { html, raw } from "../../core/html.js";

/** Échappe un texte et surligne les occurrences de q (<mark>) — sûr sur du HTML source. */
export function hlq(text, q) {
  const s = String(text == null ? "" : text);
  q = String(q || "").trim();
  if (!q) return String(html`${s}`);
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  const parts = []; let last = 0, m;
  while ((m = re.exec(s))) {
    if (m.index === re.lastIndex) { re.lastIndex++; continue; }
    parts.push(html`${s.slice(last, m.index)}<mark>${m[0]}</mark>`);
    last = m.index + m[0].length;
  }
  parts.push(s.slice(last));
  return String(html`${parts}`);
}

export function OutlineList(vm, { linkify }) {
  const k = vm.kind;
  if (k === "detached") return html`<div class="empty">attache une session…</div>`;
  if (k === "empty") return html`<div class="empty">conversation vide (ou moteur sans marqueurs « > » / « ⏺ »)</div>`;
  if (k === "nomatch") return html`<div class="empty">aucun message${vm.query ? html` ne contient « ${vm.query} »` : " pour ce filtre"}</div>`;
  const q = vm.query;
  return html`${vm.rows().map(r => html`<div class="${r.cls}" title="${r.title}" data-action="jump" data-line="${String(r.line)}">${r.icon} ${r.tag ? html`<span class="otag">${r.tag}</span>` : ""}${raw(hlq(r.text, q))}</div>${r.open
    ? html`<div class="oexp"><div class="oexpbar"><span class="sp"></span><button class="mini" data-action="copy" data-line="${String(r.line)}" title="Copier le message">⧉ copier</button><button class="mini" data-action="close-read" title="Replier">✕</button></div><div class="oexptxt">${raw(linkify(r.full))}</div></div>` : ""}`)}`;
}
