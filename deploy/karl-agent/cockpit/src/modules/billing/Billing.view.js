// modules/billing/Billing.view — l'écran de validation d'une journée. Fonctions pures : un ViewModel entre,
// un fragment sûr sort. Gestes en data-action, aucun on*. RM3229, lot L3.
import { html, raw } from "../../core/html.js";

/** La barre du haut : la journée regardée, les flèches, l'état, la relecture. */
export function Header(vm) {
  return html`<div class="bl-head">
    <button class="mini" data-action="prev" title="Journée précédente">←</button>
    <input class="bl-date" type="date" data-action="date" value="${vm.day}">
    <button class="mini" data-action="next" title="Journée suivante">→</button>
    <button class="mini" data-action="today" title="Revenir à aujourd'hui">aujourd'hui</button>
    <span class="bl-title">${vm.titre}${vm.weekend ? html` <span class="bl-we" title="Week-end : le temps transversal reste à ma charge">week-end</span>` : ""}</span>
    <span class="bl-state bl-${vm.etat}">${vm.etatLabel}</span>
    <button class="mini" data-action="reload" title="Rejouer les traces de cette journée (quelques secondes)">⟳ relire</button>
  </div>`;
}

/** Les quatre chiffres qui résument la journée. */
export function Chiffres(vm) {
  return html`<div class="bl-nums">${vm.chiffres.map(c => html`<div class="bl-num bl-n-${c.cle}" title="${c.aide}"><b>${c.valeur}</b><span>${c.label}</span></div>`)}</div>`;
}

/**
 * La frise : le temps humain en haut, le travail de l'IA en dessous, sur la MÊME échelle.
 * C'est l'argument de la journée — une plage se défend par ce qui s'y est passé.
 */
export function Frise(vm) {
  const f = vm.frise;
  return html`<div class="bl-frise">
    <div class="bl-ruler">${f.heures.map(h => html`<span class="bl-tick" style="left:${String(h.left)}%"><i></i>${h.label}</span>`)}</div>
    <div class="bl-lane bl-lane-h" title="Temps humain mesuré (plages fusionnées : rien n'est compté deux fois)">
      ${f.normal ? html`<span class="bl-normal" style="left:${String(f.normal.left)}%;width:${String(f.normal.width)}%" title="Heures normales déclarées : ${f.normal.debut}–${f.normal.fin}"></span>` : ""}
      ${f.humain.map(s => html`<span class="bl-seg" style="left:${String(s.left)}%;width:${String(s.width)}%" title="${s.debut}–${s.fin}"></span>`)}
      <span class="bl-lane-label">humain</span>
    </div>
    <div class="bl-lane bl-lane-ia" title="Tours d'agent : ce que l'IA a produit pendant la journée">
      ${f.ia.map(k => html`<span class="bl-ia" style="left:${String(k.left)}%" title="${k.heure} · ${String(k.tours)} tour(s)${k.tickets.length ? " · RM" + k.tickets.join(", RM") : ""}"></span>`)}
      <span class="bl-lane-label">IA</span>
    </div>
  </div>`;
}

/** Les heures normales de la journée et son client principal — ce que Mathieu corrige. */
export function Ajustement(vm) {
  const h = vm.heures;
  return html`<div class="bl-adj">
    <label>début <input class="bl-h" type="time" data-action="field" data-field="debut" value="${h.debut}"></label>
    <label>fin <input class="bl-h" type="time" data-action="field" data-field="fin" value="${h.fin}"></label>
    <label title="Vide : 1 h au-delà de 6 h travaillées">pause <input class="bl-p" data-action="field" data-field="pause" value="${String(h.pause)}" placeholder="auto"></label>
    <span class="bl-worked" title="Heures travaillées, pause déduite">= ${h.label}</span>
    <label title="Client pour qui la journée a majoritairement été faite">client <input class="bl-c" data-action="field" data-field="client" value="${vm.f.client || ""}" placeholder="—"></label>
    <label>projet <input class="bl-c" data-action="field" data-field="projet" value="${vm.f.projet || ""}" placeholder="—"></label>
    <button class="mini${vm.dirty ? " active" : ""}" data-action="save" ${vm.dirty && !vm.busy ? raw("") : raw("disabled")}>Enregistrer</button>
    ${vm.ajuste ? html`<button class="mini" data-action="clear" title="Revenir à ce que les traces disent">↺ ajustement</button>` : ""}
    <span class="bl-src">${vm.ajuste ? "heures ajustées à la main" : h.debut ? "heures déduites des traces" : ""}</span>
    ${vm.hors ? html`<div class="bl-hors">${vm.hors}</div>` : ""}
  </div>`;
}

/** La proposition, par client puis par projet/ticket : ce qui sera écrit, ligne à ligne. */
export function Proposition(vm) {
  if (!vm.groupes.length) return html`<div class="bl-empty">rien à ajouter — ${vm.t.deja ? "tout est déjà noté à la main" : "aucune trace exploitable ce jour-là"}</div>`;
  return html`<div class="bl-prop">${vm.groupes.map(g => html`<div class="bl-grp"><div class="bl-grp-h"><b>${g.client}</b><span>${g.total}</span></div>${g.lignes.map(l => html`<div class="bl-line"><span class="bl-prj">${l.projet}</span>${l.rm ? html`<a class="bl-rm" data-action="ticket" data-rm="${String(l.rm)}" href="#">${l.ticket}</a>` : html`<span class="bl-rm bl-none">sans ticket</span>`}<span class="bl-min">${l.minutes}</span>${l.outillage ? html`<span class="bl-tool" title="Temps d'outillage PM mutualisé, réparti sur les clients travaillés">${l.outillage}</span>` : ""}</div>`)}</div>`)}</div>`;
}

/** Ce qui est DÉJÀ dans Redmine ce jour-là : la garantie qu'on ne compte pas deux fois. */
export function DejaSaisi(vm) {
  if (!vm.dejaSaisi.length) return "";
  return html`<details class="bl-deja" open><summary>déjà noté dans Redmine — ${vm.chiffres[1].valeur} (déduit de la proposition)</summary>${vm.dejaSaisi.map(s => html`<div class="bl-line"><span class="bl-min">${s.minutes}</span>${s.rm ? html`<a class="bl-rm" data-action="ticket" data-rm="${String(s.rm)}" href="#">${s.ticket}</a>` : html`<span class="bl-rm"></span>`}<span class="bl-lib">${s.libelle}</span><span class="bl-orig ${s.auto ? "bl-o-auto" : "bl-o-main"}" title="${s.auto ? "posée par l'outil — reprenable" : "notée à la main — jamais touchée par une reprise"}">${s.auto ? "outil" : "à la main"}</span></div>`)}</details>`;
}

/** Comment le temps transversal a été traité, et le complément de régie éventuel. */
export function Contexte(vm) {
  const tr = vm.transversal;
  const rg = vm.regie;
  if (!tr && !rg.length) return "";
  return html`<div class="bl-ctx">${tr ? html`<div class="bl-tr">temps transversal (PM, infra, écosystèmes) : <b>${tr.destin}</b>${tr.cle ? html` — ${tr.cle}` : ""}${tr.ouvre ? html` <span class="bl-dim">${tr.ouvre}${tr.hors ? ", " + tr.hors : ""}</span>` : ""}${tr.alerte ? html`<div class="bl-warn">⚠ ${tr.alerte}</div>` : ""}</div>` : ""}${rg.length ? html`<div class="bl-rg">complément de régie : ${rg.map(r => html`<span>${r.client} ${r.minutes} <i>(${r.motif})</i></span>`)}</div>` : ""}</div>`;
}

/** Le pied : le bouton qui écrit, et rien d'autre à côté qui puisse être cliqué par erreur. */
export function Actions(vm) {
  const a = vm.action;
  return html`<div class="bl-actions">
    <button class="btn bl-apply" data-action="${a.geste}" ${a.disabled ? raw("disabled") : raw("")}>${a.label}</button>
    ${!vm.validee && vm.t.propose > 0 ? html`<button class="mini" data-action="dry" title="Voir ce qui serait écrit, sans rien écrire">simuler</button>` : ""}
    ${vm.reprenable ? html`<button class="mini bl-revoke" data-action="revoke" title="Retirer les saisies que l'outil a posées ce jour-là, pour réanalyser la journée. Les saisies notées à la main ne sont pas touchées. Une sauvegarde est écrite avant.">↺ reprendre — retirer ${vm.auto.label}</button>` : ""}
    <span class="bl-hint">la validation écrit les saisies de CETTE journée dans Redmine, au nom de Mathieu</span>
  </div>`;
}

export function Panel(vm) {
  if (vm.error) return html`${Header(vm)}<div class="bl-err">journée illisible : ${vm.error}</div>`;
  if (vm.loading && !vm.j) return html`${Header(vm)}<div class="bl-load">lecture de la journée…<span class="bl-dim"> (la première fois, les traces sont rejouées : quelques secondes)</span></div>`;
  return html`${Header(vm)}${Chiffres(vm)}${Frise(vm)}${Ajustement(vm)}${Contexte(vm)}${Proposition(vm)}${DejaSaisi(vm)}${Actions(vm)}`;
}

export function Card(vm) {
  return html`<h2>💶 Facturation <span class="bl-sub">valider le temps de travail, une journée à la fois</span></h2><div class="bl-body">${Panel(vm)}</div>`;
}
