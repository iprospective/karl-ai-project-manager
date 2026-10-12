// modules/billing/Billing.view — l'écran de validation d'une journée. Fonctions pures : un ViewModel entre,
// un fragment sûr sort. Gestes en data-action, aucun on*. RM3229, lot L3.
import { html, raw } from "../../core/html.js";
import { fmtMin as fmtMinV } from "./billing.js";

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
    <div class="bl-ruler">${f.heures.map(h => html`<span class="bl-tick${h.label ? "" : " bl-tick-nu"}" style="left:${String(h.left)}%"><i></i>${h.label}</span>`)}</div>
    <div class="bl-lane bl-lane-h" title="Temps humain mesuré (plages fusionnées : rien n'est compté deux fois). La couleur est celle du client dominant de la plage ; le survol donne le détail.">
      ${f.normal ? html`<span class="bl-normal" style="left:${String(f.normal.left)}%;width:${String(f.normal.width)}%" title="Heures normales déclarées : ${f.normal.debut}–${f.normal.fin}"></span>` : ""}
      ${f.pause ? html`<span class="bl-pause-band${f.pause.declaree ? " bl-pd" : ""}" style="left:${String(f.pause.left)}%;width:${String(f.pause.width)}%" title="${f.pause.titre}"></span>` : ""}
      ${f.bandes.length
        ? f.bandes.map(b => html`<span class="bl-seg" style="left:${String(b.left)}%;width:${String(b.width)}%;background:${b.couleur}" title="${b.titre}"></span>`)
        : f.humain.map(s => html`<span class="bl-seg" style="left:${String(s.left)}%;width:${String(s.width)}%" title="${s.debut}–${s.fin}"></span>`)}
      <span class="bl-lane-label">humain</span>
    </div>
    <svg class="bl-liens" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
      ${f.liens.map(l => html`<line x1="${String(l.x1)}" y1="10" x2="${String(l.x2)}" y2="0" stroke="${l.orphelin ? "var(--warn)" : l.couleur}" stroke-width="0.12" ${l.orphelin ? raw('stroke-dasharray="0.6 0.6"') : raw("")}><title>${l.titre}</title></line>`)}
    </svg>
    <div class="bl-lane bl-lane-ia" title="Tours d'agent : ce que l'IA a produit pendant la journée. La couleur est celle du client ; le trait monte vers la plage humaine qui le contient.">
      ${f.ia.map(k => html`<span class="bl-ia" style="left:${String(k.left)}%;background:${k.couleur}" title="${k.heure} · ${String(k.tours)} tour(s)${k.client ? " · " + k.client : ""}${k.tickets.length ? " · RM" + k.tickets.join(", RM") : ""}"></span>`)}
      <span class="bl-lane-label">IA</span>
    </div>
    ${Legende(vm)}
  </div>`;
}

/**
 * La note de la journée, telle qu'elle est écrite.
 *
 * Texte libre : on l'affiche, on ne l'interprète pas. Quand une ligne ne contient que
 * des horaires, ils sont PROPOSÉS — un clic les reporte dans le formulaire, jamais
 * automatiquement : c'est l'humain qui décide ce qui fait foi.
 */
export function NoteDuJour(vm) {
  const n = vm.note;
  if (!n) return html`<div class="bl-note bl-note-vide">aucune note pour cette journée</div>`;
  return html`<details class="bl-note" open><summary>📝 note du jour <span class="bl-dim">${n.fichier}</span>${n.heures ? html` · <b>${n.heures.debut}–${n.heures.fin}</b> <button class="mini" data-action="note-heures" data-debut="${n.heures.debut}" data-fin="${n.heures.fin}" title="Reporter ces horaires dans le formulaire">↧ reprendre</button>` : ""}</summary><pre class="bl-note-txt">${n.texte}</pre></details>`;
}

/** La notice de la frise : à quel client correspond quelle couleur, et combien il pèse. */
export function Legende(vm) {
  const l = vm.legende;
  if (!l.length) return "";
  return html`<div class="bl-leg">${l.map(x => html`<span class="bl-leg-i" title="${x.client} — ${x.duree} mesurées ce jour-là"><i style="background:${x.couleur}"></i>${x.client} <b>${x.duree}</b></span>`)}${vm.frise.pause ? html`<span class="bl-leg-i" title="Pause : du temps qui ne se facture à personne"><i class="bl-leg-pause"></i>pause</span>` : ""}</div>`;
}

/** Les heures normales de la journée et son client principal — ce que Mathieu corrige. */
export function Ajustement(vm) {
  const h = vm.heures;
  return html`<div class="bl-adj">
    <label>début <input class="bl-h" type="time" data-action="field" data-field="debut" value="${h.debut}"></label>
    <label>fin <input class="bl-h" type="time" data-action="field" data-field="fin" value="${h.fin}"></label>
    <label title="Vide : 1 h au-delà de 6 h travaillées">pause <input class="bl-p" data-action="field" data-field="pause" value="${String(h.pause)}" placeholder="auto"></label>
    ${vm.pause.declaree ? "" : html`<button class="mini${vm.pause.manquante ? " bl-manque" : ""}" data-action="pause-midi" title="Noter la pause de midi : ${String(vm.pause.proposition)} h${vm.pause.ou ? " sur " + vm.pause.ou : ""}${vm.pause.commentaire ? ", « " + vm.pause.commentaire + " »" : ""}. Elle ne se facture à personne.">+ pause midi</button>`}
    <span class="bl-worked" title="Heures travaillées, pause déduite">= ${h.label}</span>
    <label title="Client pour qui la journée a majoritairement été faite">client <select class="bl-c" data-action="field" data-field="client"><option value="">—</option>${vm.clients.map(c => html`<option value="${c.value}"${c.selected ? raw(" selected") : ""}>${c.value}</option>`)}</select></label>
    <label>projet <select class="bl-c" data-action="field" data-field="projet"><option value="">—</option>${vm.projetsDuClient.map(x => html`<option value="${x.value}"${x.selected ? raw(" selected") : ""}>${x.value}</option>`)}</select></label>
    <label title="Journée chez le client, ou à la maison">lieu <select class="bl-c" data-action="field" data-field="lieu">${vm.lieux.map(l => html`<option value="${l.value}"${l.selected ? raw(" selected") : ""}>${l.label}</option>`)}</select></label>
    <button class="mini${vm.dirty ? " active" : ""}" data-action="save" ${vm.dirty && !vm.busy ? raw("") : raw("disabled")}>Enregistrer</button>
    ${vm.ajuste ? html`<button class="mini" data-action="clear" title="Revenir à ce que les traces disent">↺ ajustement</button>` : ""}
    <span class="bl-src">${vm.ajuste ? "heures ajustées à la main" : h.debut ? "heures déduites des traces" : ""}</span>
    <span class="bl-pz${vm.pause.manquante ? " bl-manque" : ""}">${vm.pause.texte}</span>
    ${vm.hors ? html`<div class="bl-hors">${vm.hors}</div>` : ""}
  </div>`;
}

/** La proposition, par client puis par projet/ticket : ce qui sera écrit, ligne à ligne. */
export function Proposition(vm) {
  if (!vm.groupes.length) return html`<div class="bl-empty">rien à ajouter — ${vm.t.deja ? "tout est déjà noté à la main" : "aucune trace exploitable ce jour-là"}</div>`;
  return html`<div class="bl-prop">${vm.groupes.map(g => html`<div class="bl-grp"><div class="bl-grp-h"><b${g.facturable ? raw("") : raw(' class="bl-nf"')}>${g.client}</b>${g.facturable ? "" : html`<span class="bl-nf-tag" title="Entité de type « self » : ce temps est noté, jamais facturé">non facturé</span>`}<span>${g.total}</span></div>${g.lignes.map(l => html`<div class="bl-line"><span class="bl-prj">${l.projet}</span>${l.rm ? html`<a class="bl-rm" data-action="ticket" data-rm="${String(l.rm)}" href="#">${l.ticket}</a>` : html`<span class="bl-rm bl-none">sans ticket</span>`}<span class="bl-min">${l.minutes}</span>${l.outillage ? html`<span class="bl-tool" title="Temps d'outillage PM mutualisé, réparti sur les clients travaillés">${l.outillage}</span>` : ""}</div>`)}</div>`)}</div>`;
}

/** Ce qui est DÉJÀ dans Redmine ce jour-là : la garantie qu'on ne compte pas deux fois. */
export function DejaSaisi(vm) {
  if (!vm.dejaSaisi.length) return "";
  return html`<details class="bl-deja" open><summary>déjà noté dans Redmine — ${vm.chiffres[1].valeur} (déduit de la proposition)</summary>${vm.dejaSaisi.map(s => html`<div class="bl-line"><span class="bl-min">${s.minutes}</span><span class="bl-cl">${s.client}</span><span class="bl-prj">${s.projet}</span>${s.rm ? html`<a class="bl-rm" data-action="ticket" data-rm="${String(s.rm)}" href="#">${s.ticket}</a>` : html`<span class="bl-rm"></span>`}<span class="bl-lib">${s.libelle}</span><span class="bl-orig ${s.auto ? "bl-o-auto" : "bl-o-main"}" title="${s.auto ? "posée par l'outil — reprenable" : "notée à la main — jamais touchée par une reprise"}">${s.auto ? "outil" : "à la main"}</span></div>`)}</details>`;
}

/** Comment le temps transversal a été traité, et le complément de régie éventuel. */
export function Contexte(vm) {
  const tr = vm.transversal;
  const rg = vm.regie;
  if (!tr && !rg.length) return "";
  return html`<div class="bl-ctx">${tr ? html`<div class="bl-tr">temps transversal (PM, infra, écosystèmes) : <b>${tr.destin}</b>${tr.cle ? html` — ${tr.cle}` : ""}${vm.transversalCumul.length ? html`<div class="bl-tc">${vm.transversalCumul.map(x => html`<span class="bl-tc-i" title="${x.client} a reçu ${x.duree} de temps transversal ce jour-là"><i style="background:${x.couleur}"></i>${x.client} <b>${x.duree}</b></span>`)}</div>` : ""}${tr.ouvre ? html` <span class="bl-dim">${tr.ouvre}${tr.hors ? ", " + tr.hors : ""}</span>` : ""}${tr.alerte ? html`<div class="bl-warn">⚠ ${tr.alerte}</div>` : ""}</div>` : ""}${rg.length ? html`<div class="bl-rg">complément de régie : ${rg.map(r => html`<span>${r.client} ${r.minutes} <i>(${r.motif})</i></span>`)}</div>` : ""}</div>`;
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

/**
 * Les traces horodatées de la journée : ce sur quoi le calcul s'appuie, à la minute.
 *
 * Un chiffre sans ses preuves demande qu'on le croie. Cette liste le donne à vérifier.
 */
export function Traces(vm) {
  const t = vm.traces;
  if (!t.length) return "";
  return html`<details class="bl-ev"><summary>traces de la journée — ${String(t.length)} (${String(vm.tracesHumaines)} humaines)</summary><div class="bl-evl">${t.map(x => html`<div class="bl-evr${x.humain ? "" : " bl-ag"}"><span class="bl-eh">${x.heure}</span><span class="bl-es" title="${x.humain ? "trace humaine : elle crée du temps" : "trace d'agent : elle attribue le temps, elle n'en crée pas"}">${x.source}</span><span class="bl-ec">${x.cible}${x.rm ? html` <a class="bl-rm" data-action="ticket" data-rm="${String(x.rm)}" href="#">RM${String(x.rm)}</a>` : ""}</span><span class="bl-ex">${x.extrait}</span></div>`)}</div></details>`;
}

/** Les commits de la journée : la trace la plus dure de ce qui a été produit. */
export function Commits(vm) {
  const c = vm.commits;
  if (!c.total) return "";
  const ligne = (x) => html`<div class="bl-evr"><span class="bl-eh">${x.heure}</span><span class="bl-ed" title="${x.client}">${x.depot}</span><span class="bl-ex">${x.sujet}</span><span class="bl-sha">${x.sha}</span></div>`;
  return html`<details class="bl-ev" open><summary>commits — ${String(c.travail.length)} de travail${c.plomberie.length ? html` <span class="bl-dim">· ${String(c.plomberie.length)} de plomberie PM</span>` : ""}</summary><div class="bl-evl">${c.travail.map(ligne)}</div>${c.plomberie.length ? html`<details class="bl-sub2"><summary>plomberie PM (${String(c.plomberie.length)}) — ticks, moissons, rapports</summary><div class="bl-evl">${c.plomberie.map(ligne)}</div></details>` : ""}</details>`;
}

/** Le temps de l'IA, groupé par ticket — en face du temps humain, jamais mélangé avec lui. */
export function TempsIA(vm) {
  const g = vm.ia;
  if (!g.length) return "";
  return html`<details class="bl-ev"><summary>temps IA — ${vm.chiffres[3].valeur} sur ${String(g.length)} cible(s)</summary><div class="bl-evl">${g.map(x => html`<div class="bl-evr"><span class="bl-eh">${x.plage}</span><span class="bl-ec">${x.rm ? html`<a class="bl-rm" data-action="ticket" data-rm="${String(x.rm)}" href="#">${x.cle}</a>` : x.cle}</span><span class="bl-ex">${x.cible} <span class="bl-dim">${x.modeles}</span></span><span class="bl-min">${x.duree}</span><span class="bl-tool">${String(x.tours)} tours · ${x.jetons}</span></div>`)}</div></details>`;
}

const GENRE = { trace: "trace", commit: "commit", livraison: "livré", plomberie: "pm", ia: "IA" };

/**
 * TOUT ce qui s'est passé dans la journée, dans l'ordre : traces, commits, tours d'agent.
 *
 * La couture entre trois listes séparées se faisait dans la tête ; elle se fait ici.
 */
export function Fil(vm) {
  const f = vm.fil;
  if (!f.length) return "";
  const c = vm.commits;
  return html`<details class="bl-ev" open><summary>ce qui s'est passé — ${String(f.length)} actions <span class="bl-dim">· ${String(vm.tracesHumaines)} traces humaines · ${String(c.travail.length)} commits${c.fusions.length ? " · " + String(c.fusions.length) + " livraison(s)" : ""} · ${String(vm.iaTotaux.tours)} tours d'agent</span></summary><div class="bl-evl">${f.map(x => html`<div class="bl-evr bl-g-${x.genre}${x.humain ? "" : " bl-ag"}"><span class="bl-eh">${x.heure}</span><span class="bl-gn">${GENRE[x.genre] || x.genre}</span><span class="bl-es">${x.source}</span><span class="bl-ec">${x.cible}${x.rm ? html` <a class="bl-rm" data-action="ticket" data-rm="${String(x.rm)}" href="#">RM${String(x.rm)}</a>` : ""}</span><span class="bl-ex">${x.texte}</span></div>`)}</div></details>`;
}

/** Une ligne de preuve dans le dossier d'une plage. */
const Preuve = (icone, titre, items, rendu) => items.length
  ? html`<div class="bl-pv"><span class="bl-pv-t" title="${titre}">${icone} ${String(items.length)}</span><span class="bl-pv-l">${items.map(rendu)}</span></div>`
  : "";

/**
 * Le dossier de la journée : chaque plage humaine, et ce qui la justifie.
 *
 * C'est la pièce qu'on sort quand un client demande à quoi ont servi ces heures. Une
 * plage sans aucune preuve est signalée — c'est précisément celle qu'il faut regarder.
 */
/**
 * Les blocs destinés à Redmine, et ce qui justifie chacun.
 *
 * C'est l'unité qui compte : un bloc = du temps + une activité + UN projet + si possible
 * un ticket. C'est lui qu'on valide, donc lui qu'il faut pouvoir défendre.
 */
export function Blocs(vm) {
  const b = vm.blocs;
  if (!b.length) return "";
  const bi = vm.bilanBlocs;
  const hors = vm.iaHorsPlage;
  return html`<details class="bl-ev" open><summary>blocs à insérer dans Redmine — ${String(bi.blocs)} bloc(s) · ${String(bi.clients)} client(s)${bi.sansTicket ? html` · <span class="bl-dim">${String(bi.sansTicket)} sans ticket</span>` : ""}${bi.sansPreuve ? html` · <b class="bl-manque">${String(bi.sansPreuve)} sans preuve directe</b>` : ""}</summary>
    <div class="bl-cor">${b.map(x => html`<div class="bl-bloc${x.preuves ? "" : " bl-cp-vide"}">
      <div class="bl-bloc-h"><i style="background:${x.couleur}"></i><b>${x.duree}</b><span class="bl-bk">${x.client}/${x.projet}</span>${x.ticket ? html`<a class="bl-rm" data-action="ticket" data-rm="${String(x.ticket)}" href="#">RM${String(x.ticket)}</a>` : html`<span class="bl-rm bl-none">sans ticket</span>`}<span class="bl-act">${x.activiteNom}</span>${x.facturable ? "" : html`<span class="bl-nf-tag">non facturé</span>`}${x.plage ? html`<span class="bl-dim">${x.plage}</span>` : ""}</div>
      <div class="bl-bloc-p">${x.ia.length ? html`<span class="bl-pv-i" title="tours d'agent sur ce ticket">🤖 ${String(x.ia.length)} · ${x.iaDuree}</span>` : ""}${x.prompts.length ? html`<span class="bl-pv-i" title="ce que tu as écrit pour cette cible">✍ ${String(x.prompts.length)}</span>` : ""}${x.commits.length ? html`<span class="bl-pv-i" title="commits chez ce client">⎇ ${String(x.commits.length)}</span>` : ""}${x.fusions.length ? html`<span class="bl-pv-i bl-mr" title="livraisons">🚀 ${String(x.fusions.length)}</span>` : ""}${x.outillage ? html`<span class="bl-tool">dont ${fmtMinV(x.outillage)} d'outillage PM mutualisé</span>` : ""}${x.preuves ? "" : html`<span class="bl-manque">aucune preuve directe — temps réparti par la clé de refacturation</span>`}</div>
    </div>`)}</div>
    ${hors.length ? html`<div class="bl-orph"><b>${String(hors.length)} tour(s) d'agent hors des plages de travail</b> <span class="bl-dim">(${String(bi.minutesHorsPlage)} min, informatif — jamais facturé)</span><div class="bl-pv-l">${hors.map(k => html`<span class="bl-pv-i" title="${k.modele}${k.cible ? " · " + k.cible : ""}"><i style="background:${k.couleur}"></i>${k.heure} ${k.duree}${k.rm ? " RM" + String(k.rm) : ""}</span>`)}</div></div>` : ""}
  </details>`;
}

export function Correspondances(vm) {
  const c = vm.correspondances;
  if (!c.periodes.length) return "";
  const b = vm.bilan;
  const o = c.orphelins;
  return html`<details class="bl-ev" open><summary>plages humaines et leurs preuves — ${String(b.periodes)} plage(s)${b.sansPreuve ? html` · <b class="bl-manque">${String(b.sansPreuve)} sans aucune preuve</b>` : ""}${b.iaOrphelins ? html` · <b class="bl-manque">${String(b.iaOrphelins)} tour(s) d'agent hors plage</b>` : ""}</summary>
    <div class="bl-cor">${c.periodes.map(p => html`<div class="bl-cp${p.vide ? " bl-cp-vide" : ""}">
      <div class="bl-cp-h"><b>${p.debut}–${p.fin}</b><span class="bl-dim">${p.duree}</span>${p.clients.map(x => html`<span class="bl-tc-i"><i style="background:${x.couleur}"></i>${x.client}</span>`)}${p.vide ? html`<span class="bl-manque">aucune preuve — à vérifier avant de facturer</span>` : ""}</div>
      ${Preuve("🤖", "tours d'agent dans cette plage", p.ia, (k) => html`<span class="bl-pv-i" title="${k.heure} · ${k.cible}">${k.heure}${k.rm ? " RM" + String(k.rm) : ""}</span>`)}
      ${Preuve("⎇", "commits écrits pendant cette plage", p.commits, (x) => html`<span class="bl-pv-i" title="${x.depot} · ${x.sujet}">${x.heure} ${x.depot}</span>`)}
      ${Preuve("🚀", "livraisons (MR fusionnées) pendant cette plage", p.fusions, (x) => html`<span class="bl-pv-i bl-mr" title="${x.branche} → ${x.cible}">${x.heure} ${x.rm ? "RM" + String(x.rm) : x.depot}</span>`)}
      ${Preuve("✍", "ce que tu as écrit pendant cette plage", p.prompts, (x) => html`<span class="bl-pv-i" title="${x.texte}">${x.heure}${x.cible ? " " + x.cible : ""}</span>`)}
      ${Preuve("📋", "actions Redmine pendant cette plage", p.redmine, (x) => html`<span class="bl-pv-i" title="${x.texte}">${x.heure}${x.rm ? " RM" + String(x.rm) : ""}</span>`)}
    </div>`)}</div>
    ${c.aOrphelins ? html`<div class="bl-orph"><b class="bl-manque">hors de toute plage humaine</b> — soit une plage manque, soit l'agent a tourné seul :
      ${o.ia.length ? html`<span class="bl-pv-i">🤖 ${String(o.ia.length)} tour(s), ${String(b.minutesOrphelines)} min</span>` : ""}
      ${o.commits.length ? html`<span class="bl-pv-i">⎇ ${String(o.commits.length)} commit(s)</span>` : ""}
      ${o.fusions.length ? html`<span class="bl-pv-i">🚀 ${String(o.fusions.length)} livraison(s)</span>` : ""}
      ${o.prompts.length ? html`<span class="bl-pv-i">✍ ${String(o.prompts.length)} trace(s)</span>` : ""}</div>` : ""}
  </details>`;
}

export function Panel(vm) {
  if (vm.error) return html`${Header(vm)}<div class="bl-err">journée illisible : ${vm.error}</div>`;
  if (vm.loading && !vm.j) return html`${Header(vm)}<div class="bl-load">lecture de la journée…<span class="bl-dim"> (la première fois, les traces sont rejouées : quelques secondes)</span></div>`;
  return html`${Header(vm)}${Chiffres(vm)}${Frise(vm)}${NoteDuJour(vm)}${Ajustement(vm)}${Contexte(vm)}${Proposition(vm)}${DejaSaisi(vm)}${Actions(vm)}${Blocs(vm)}${Correspondances(vm)}${Fil(vm)}`;
}

export function Card(vm) {
  return html`<h2>💶 Facturation <span class="bl-sub">valider le temps de travail, une journée à la fois</span></h2><div class="bl-body">${Panel(vm)}</div>`;
}
