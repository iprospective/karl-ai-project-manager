// modules/engines/Engines.view — le panneau Moteurs. La commande exacte est montrée AVANT d'agir (garde-fou 10).
// Gestes en data-action, aucun on*. RM3069.
import { html } from "../../core/html.js";

const Ligne = (r) => html`<div class="eg-row">
  <span class="eg-name">${r.label}</span>
  <span class="st ${r.cls}">${r.state}</span>
  ${r.version ? html`<span class="eg-ver">${r.version}${r.updatable ? " → " + r.latest : ""}</span>` : ""}
  ${r.service ? html`<span class="eg-ver" title="service système">service : ${r.service}</span>` : ""}
  ${r.sessions ? html`<span class="eg-ses">${String(r.sessions)} session(s)</span>` : ""}
  ${r.path ? html`<span class="eg-ver" title="où il est installé">${r.path}</span>` : ""}
  ${r.providerType ? html`<span class="eg-ver" title="se déclare ensuite comme fournisseur">→ fournisseur ${r.providerType}</span>` : ""}
  <span class="eg-sp"></span>
  <button class="mini" data-action="test" data-id="${r.id}" title="Vérifier que l'outil répond">tester</button>
  ${r.actions.map(a => html`<button class="mini ${a.primary ? "" : "soft"}" data-action="run" data-id="${r.id}" data-act="${a.act}" data-scope="${a.scope}" title="${a.cmd}" ${r.busy ? "disabled" : ""}>${a.label}${a.sudo ? " ⚠" : ""}</button>`)}
  <div class="eg-cmd">${r.cmd}</div>
  ${r.warn ? html`<div class="eg-warn">${r.warn}</div>` : ""}
  ${r.config ? html`<div class="eg-cfg">à configurer : ${r.config}</div>` : ""}
  ${r.note ? html`<div class="eg-cfg">${r.note}</div>` : ""}
</div>`;

/** RM3139 — un moteur et la façon dont on le lance. Les cases portent leur POURQUOI en infobulle :
 *  cocher « désactiver MCP » sans savoir ce qu'on désactive, c'est un réglage qu'on n'ose pas toucher. */
const LigneLancement = (r) => html`<div class="eg-launch" data-engine="${r.engine}">
  <div class="eg-lname">${r.engine}${r.dirty ? html`<span class="eg-dirty" title="modifié, pas encore enregistré">•</span>` : ""}</div>
  <div class="eg-opts">${r.options.map(o => html`<label class="eg-opt" title="${o.why || o.flag}">
    <input type="checkbox" data-action="opt" data-engine="${r.engine}" data-key="${o.key}"${o.enabled ? " checked" : ""}${r.busy ? " disabled" : ""}>
    <span>${o.label}</span> <code class="eg-flag">${o.flag}</code>${o.source === "pm.config.yml" ? html`<span class="eg-src" title="réglé sur cette instance">réglé ici</span>` : ""}
  </label>`)}${r.options.length ? "" : html`<span class="pv-def">aucune option déclarée pour ce moteur</span>`}</div>
  <div class="eg-extra"><label>options libres
    <input class="cdc-in" type="text" data-action="extra" data-engine="${r.engine}" value="${r.extra}" placeholder="--verbose --foo bar"${r.busy ? " disabled" : ""}>
  </label>
  <button class="mini" data-action="save" data-engine="${r.engine}"${r.dirty && !r.busy ? "" : " disabled"}>enregistrer</button></div>
  <div class="eg-cmd" title="la commande réellement lancée (état enregistré)">${r.cmd}</div>
  ${r.resume ? html`<div class="eg-cmd eg-resume" title="reprise d'une session">${r.resume}</div>` : ""}
  ${r.problems.map(pb => html`<div class="eg-warn">${pb}</div>`)}
</div>`;

export function EnginesLaunchCard(vm) {
  if (vm.error) return html`<div class="eg-grp"><h3>Lancement</h3><div class="empty">options indisponibles : ${vm.error}</div></div>`;
  if (vm.empty) return "";
  return html`<div class="eg-grp"><h3>Lancement <span class="pv-def">ce que PM ajoute à la ligne de commande quand il ouvre une session</span> <span class="pv-count">${vm.count}</span></h3>
    <div class="cdc-hint">Ce qui est coché s'écrit dans <code>pm.config.local.yml</code>, la surcharge de cette instance — jamais dans le fichier de référence. Une option identique au défaut n'y est pas consignée : le jour où le défaut change, l'instance suit. Un réglage invalide est refusé à l'enregistrement, pas au lancement.</div>
    ${vm.rows.map(LigneLancement)}</div>`;
}

export function EnginesCard(vm, journal) {
  if (vm.empty) return html`<h2>🧩 Moteurs</h2><div class="empty">catalogue indisponible</div>`;
  return html`<h2>🧩 Moteurs <span class="pv-count">${vm.count}</span></h2>
  <div class="cdc-hint">Le cockpit n'exécute que des recettes connues : il envoie un identifiant, une action et une portée, jamais une commande. <b>Pour moi</b> installe dans votre espace, sans privilège ; <b>pour tous</b> (⚠) installe sur la machine entière, en sudo, et demande d'être administrateur. La commande exacte est montrée avant d'agir.</div>
  ${vm.groupes.map(g => html`<div class="eg-grp"><h3>${g.label} <span class="pv-def">${g.help}</span></h3>
    ${g.rows.map(Ligne)}</div>`)}
  ${journal ? html`<pre class="eg-out">${journal}</pre>` : ""}`;
}
