// modules/layout/Layout.view — la barre de navigation du gabarit mobile (RM3003). Gestes en data-mpage, aucun on*.
import { html } from "../../core/html.js";

export function MobileNav(items) {
  return html`${items.map(i => html`<button class="mnav-btn${i.active ? " active" : ""}" data-mpage="${i.page}" title="${i.label}"><span class="mnav-ico">${i.icon}</span><span class="mnav-lbl">${i.label}</span>${i.badge ? html`<span class="nbadge att">${i.badge}</span>` : ""}</button>`)}`;
}
