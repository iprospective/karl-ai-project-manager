// modules/modules/Modules.view — le panneau « Modules ». Gestes en data-action, aucun on*. RM3145.
import { html } from "../../core/html.js";

const Trigger = (t) => html`<div class="mdl-trig${t.ok ? "" : " ko"}">
  ${t.ok ? "↩" : "✗"} <b>${t.on}</b>${t.when ? html` <span class="mdl-when">si ${t.when}</span>` : ""}
  <code>${t.run}</code>${t.errors.map(e => html` <span class="mdl-motif">${e}</span>`)}</div>`;

const Gestes = (m) => html`<div class="mdl-gestes">
  ${m.canDisable ? html`<button class="mini" data-action="disable" data-name="${m.name}"
      title="${m.breaks.length ? "Refusé tant que " + m.breaks.join(", ") + " en dépend(ent)" : "Éteindre ce module — ce qu'il a produit reste en place"}">○ éteindre</button>` : ""}
  ${m.canEnable ? html`<button class="mini" data-action="enable" data-name="${m.name}" title="Rallumer ce module">● allumer</button>` : ""}
  <span class="mdl-nat" title="${m.native ? "Livré avec le noyau : il s'éteint, il ne se retire pas" : "Module tiers : il se désinstalle"}">${m.native ? "natif" : "tiers"}</span>
  ${m.refus ? html`<div class="mdl-refus">✗ ${m.refus}${m.canForce ? html` <button class="mini warn" data-action="force" data-name="${m.name}">⊘ forcer…</button>` : ""}</div>` : ""}
  ${m.confirming ? html`<div class="mdl-confirm">
    <b>Forcer l'extinction de ${m.name}</b> — ${m.breaks.length ? html`<b>${m.breaks.join(", ")}</b> cessera(ont) de fonctionner et sera(ont) signalé(s) tant que ${m.name} restera éteint.` : "des modules en dépendent."}
    Ce que ces modules ont produit reste en place.
    <div>Recopiez le nom du module pour confirmer : <input class="mdl-confirm-in" data-input="confirm" data-name="${m.name}" autocomplete="off" spellcheck="false" placeholder="${m.name}"></div>
    <button class="mini warn" data-action="force-confirm" data-name="${m.name}"${m.confirmOk ? "" : " disabled"}>⊘ forcer l'extinction</button>
    <button class="mini soft" data-action="force-cancel" data-name="${m.name}">annuler</button></div>` : ""}
</div>`;

const Ligne = (m) => html`<div class="mdl-row${m.open ? " on" : ""}">
  <div class="mdl-head" data-action="open" data-name="${m.name}" title="${m.description}">
    <span class="st ${m.cls}">${m.icone}</span>
    <b class="mdl-name">${m.name}</b> <span class="mdl-ver">${m.version}</span>
    <span class="mdl-label">${m.label}</span>
    <span class="mdl-state">${m.state}</span>
  </div>
  ${!m.open && m.motifs.length ? html`<div class="mdl-motif mdl-motif-court">⚠ ${m.motifs[0]}${m.motifs.length > 1
    ? " (+" + String(m.motifs.length - 1) + ")" : ""}</div>` : ""}
  ${m.open ? html`<div class="mdl-detail">
    <div class="mdl-desc">${m.description}</div>
    ${Gestes(m)}
    <div><span class="mdl-k">fournit</span> ${m.provides.length ? m.provides.join(" · ") : "rien"}</div>
    <div><span class="mdl-k">requiert</span> ${m.requires.length ? m.requires.join(", ") : "rien"}</div>
    <div><span class="mdl-k">requis par</span> ${m.requiredBy.length
      ? html`<b title="Désactiver ce module casserait ceux-ci">${m.requiredBy.join(", ")}</b>`
      : "personne"}</div>
    ${m.routes.length ? html`<div class="mdl-trigs"><span class="mdl-k">sert</span>${m.routes.map(r => html`<div class="mdl-trig${r.ok ? "" : " ko"}">${r.ok ? "→" : "✗"} <b>${r.method}</b> <code>${r.url}</code>${r.errors.map(e => html` <span class="mdl-motif">${e}</span>`)}</div>`)}</div>` : ""}
    ${m.triggers.length ? html`<div class="mdl-trigs"><span class="mdl-k">réagit à</span>${m.triggers.map(Trigger)}</div>` : ""}
    ${m.motifs.map(x => html`<div class="mdl-motif">⚠ ${x}</div>`)}
  </div>` : ""}</div>`;

const Ecart = (inv) => html`<div class="ms mdl-ecart">
  <h4>Ce que l'instance porte encore sans module <span class="cdc-count">${String(inv.decrits)}/${String(inv.total)} décrit(s)</span></h4>
  <div class="cdc-hint">Sept registres d'extension, chacun réinventé dans son coin : c'est ce que le
    chantier des modules unifie. Cet écart est la mesure de son avancement — le taire donnerait un
    panneau flatteur, et faux.</div>
  <div class="cdc-tablewrap"><table class="cdc-table"><thead><tr><th>Registre</th><th>Décrits</th><th>Encore sans module</th></tr></thead>
  <tbody>${inv.lignes.map(l => html`<tr>
    <td class="mdl-reg">${l.registre}</td>
    <td class="mdl-num">${String(l.decrits)}/${String(l.total)}</td>
    <td class="mdl-manq">${l.manquants.length ? l.manquants.join(" · ") : "—"}</td></tr>`)}</tbody></table></div>
</div>`;

const Bus = (b) => html`<div class="ms">
  <h4>Bus d'événements <span class="cdc-count">${String(b.pending)} en attente${b.errors ? " · " + String(b.errors) + " en erreur" : ""}</span></h4>
  ${b.errors ? html`<div class="cdc-hint">Un abonné qui échoue ne rejoue pas indéfiniment : son
    événement est marqué avec l'erreur. Sans cette liste, un module semblerait branché et ne
    réagirait jamais.</div>` : ""}
  ${(b.last_errors || []).map(e => html`<div class="mdl-motif">⚠ ${e.name} · ${String(e.ts || "").slice(0, 16).replace("T", " ")} — ${e.error}</div>`)}
</div>`;

export function ModulesCard(vm) {
  const c = vm.counts;
  const titre = html`<h2>🧩 Modules <span class="cdc-count">${String(c.total)} décrit(s)${c.casses ? " · " + String(c.casses) + " à voir" : ""}</span>
    <button class="helpq" data-cmd="help" data-arg="modules" title="Aide sur ce panneau">?</button></h2>`;
  if (vm.error) return html`${titre}<div class="empty">registre illisible : ${vm.error}</div>`;
  return html`${titre}
    <div class="cdc-hint">Un module déclare ce qu'il fournit et ce dont il dépend, dans
      <code>${vm.root}</code>. Éteindre un module ne supprime rien de ce qu'il a produit ; éteindre un
      module dont d'autres dépendent est refusé. Noyau ${vm.coreVersion}.</div>
    <label class="mdl-policy" title="Sans ce réglage, un module dont d'autres dépendent ne peut pas être éteint. Avec, chaque forçage demande encore de recopier le nom du module.">
      <input type="checkbox" data-action="policy"${vm.allowForce ? " checked" : ""}> autoriser le forçage (confirmation forte à chaque fois)</label>
    ${vm.cycles.map(c => html`<div class="mdl-motif">⚠ dépendance circulaire : ${c.join(" → ")}</div>`)}
    ${vm.empty ? html`<div class="empty">aucun module décrit pour l'instant.</div>`
               : html`<div class="mdl-list">${vm.rows().map(Ligne)}</div>`}
    ${Bus(vm.bus)}
    ${Ecart(vm.inventaire)}`;
}
