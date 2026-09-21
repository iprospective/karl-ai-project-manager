// modules/layout/Layout.view — la barre de navigation du gabarit mobile (RM3003). Gestes en data-mpage, aucun on*.
import { html } from "../../core/html.js";

export function MobileNav(items, full = null) {
  // RM3270 : la bascule plein écran vit dans cette barre — c'est la seule qui reste visible quand le reste s'efface.
  const toggle = full ? html`<button class="mnav-btn mnav-full${full.full ? " active" : ""}" data-mfull="1" title="${full.label}"><span class="mnav-ico">${full.icon}</span><span class="mnav-lbl">${full.label}</span></button>` : "";
  return html`${items.map(i => html`<button class="mnav-btn${i.active ? " active" : ""}" data-mpage="${i.page}" title="${i.label}"><span class="mnav-ico">${i.icon}</span><span class="mnav-lbl">${i.label}</span>${i.badge ? html`<span class="nbadge att">${i.badge}</span>` : ""}</button>`)}${toggle}`;
}
