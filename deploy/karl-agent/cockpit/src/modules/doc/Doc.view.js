// views/glossary/Doc — la modale doc : glossaire cherchable, page d'aide avec sommaire, document rendu. Gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";

export function GlossaryList(vm) {
  const groups = vm.groups();
  if (!groups.length) return html`<div class="glossempty">Aucun terme ne correspond.</div>`;
  return html`${groups.map(g => html`<div class="glosscat">${g.label}</div>${g.items.map(e => html`<div class="glossrow${e.hi ? " glosshi" : ""}" data-k="${e.key}"><span class="glossterm">${e.term}</span>${e.alias ? html`<span class="glossalias">${e.alias}</span>` : ""}<div class="glossdef">${e.def}</div></div>`)}`)}`;
}
export function GlossaryPanel(vm) {
  return html`<div class="glosstop"><input id="glosssearch" type="search" placeholder="Rechercher un terme ou une définition…" autocomplete="off" value="${vm.e.query || ""}"><span class="glosscount" id="glosscount">${vm.count}</span></div><div id="glosslist">${GlossaryList(vm)}</div>`;
}
export function HelpPage(vm, { md }) {
  return html`<div class="helptoc">${vm.toc.map(t => html`<button class="chip${t.on ? " on" : ""}" data-action="help" data-topic="${t.id}">${t.title}</button>`)}</div><div class="helpbody">${raw(md(vm.md))}</div>`;
}
