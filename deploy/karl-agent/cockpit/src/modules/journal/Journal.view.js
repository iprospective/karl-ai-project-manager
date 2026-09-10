// modules/journal/Journal.view — le panneau « journal » : barre de filtres (sévérité, catégories, recherche, suivi, copie, relecture,
// purge du front) et la liste des entrées. Gestes en data-action, aucun on*. RM3011.
import { html, raw } from "../../core/html.js";

export function Toolbar(vm) {
  return html`<div class="jl-bar"><label class="jl-lvl">sévérité <select data-action="level">${vm.levels.map(l => html`<option value="${l.value}"${l.selected ? raw(" selected") : ""}>${l.label}</option>`)}</select></label><div class="jl-cats"><button class="chip${vm.allCats ? " on" : ""}" data-action="cat-all" title="Toutes les catégories">toutes</button>${vm.catChips.map(c => html`<button class="chip${c.on ? " on" : ""}" data-action="cat" data-cat="${c.cat}">${c.cat}</button>`)}</div><input class="jl-q" data-action="q" placeholder="rechercher (message, champs)" value="${vm.q}"><button class="mini${vm.paused ? " active" : ""}" data-action="pause" title="${vm.paused ? "Reprendre le suivi" : "Mettre le suivi en pause"}">${vm.paused ? "▶ suivre" : "⏸ pause"}</button><button class="mini" data-action="reload" title="Relire tout le journal serveur">⟳</button><button class="mini" data-action="copy" title="Copier les entrées affichées">⎘ copier</button><button class="mini" data-action="clear-front" title="Vider le journal du navigateur (le serveur garde le sien)">✕ front</button></div>`;
}

export function Rows(vm) {
  if (!vm.rows.length) return html`<div class="empty">${vm.error ? "journal serveur injoignable : " + vm.error : "rien à afficher avec ces filtres"}</div>`;
  return html`${vm.rows.map(r => html`${r.day ? html`<div class="jl-day">${r.day}</div>` : ""}<div class="jl-row ${r.cls}" data-id="${r.id}"><span class="jl-time">${r.time}</span><span class="jl-level">${r.level}</span><span class="jl-cat">${r.cat}</span><span class="jl-src" title="${r.src === "front" ? "journal du navigateur" : "journal du serveur"}">${r.src}</span><span class="jl-msg">${r.msg}</span>${r.fields ? html`<span class="jl-fields">${r.fields}</span>` : ""}</div>`)}`;
}

export function Panel(vm) {
  return html`<h2>📜 Journal <span class="jl-count">${String(vm.count)} entrée(s)${vm.errors ? html` · <b class="jl-err">${String(vm.errors)} erreur(s)</b>` : ""}${vm.warns ? html` · ${String(vm.warns)} avert.` : ""}</span></h2>${Toolbar(vm)}<div class="jl-list" data-role="list">${Rows(vm)}</div>${vm.statsText ? html`<div class="jl-stats">${vm.statsText}</div>` : ""}`;
}
