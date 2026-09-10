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
/** RM3043 : le choix d'un CDC vivant quand plusieurs projets en portent (ou aucun). */
export function CdcList(cdcs) {
  if (!cdcs.length) return html`<div class="glossempty">Aucun CDC vivant : un projet en porte un dès qu'il a un <code>docs/cdc-&lt;prefix&gt;-00-sommaire.md</code> (modèle AtomBox, <code>pm-cdc-features --init</code>).</div>`;
  return html`<div class="cdclist">${cdcs.map(c => html`<button class="cdcrow" data-action="cdc-open" data-path="${c.path}" data-name="${c.title}"><span class="cdcproj">${c.client}/${c.project}</span><span class="cdctitle">${c.title}</span><span class="cdcn">${c.chapters.length} chapitres</span></button>`)}</div>`;
}
export function HelpPage(vm, { md }) {
  return html`<div class="helptoc">${vm.toc.map(t => html`<button class="chip${t.on ? " on" : ""}" data-action="help" data-topic="${t.id}">${t.title}</button>`)}</div><div class="helpbody">${raw(md(vm.md))}</div>`;
}
