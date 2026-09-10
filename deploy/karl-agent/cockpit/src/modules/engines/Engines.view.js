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

export function EnginesCard(vm, journal) {
  if (vm.empty) return html`<h2>🧩 Moteurs</h2><div class="empty">catalogue indisponible</div>`;
  return html`<h2>🧩 Moteurs <span class="pv-count">${vm.count}</span></h2>
  <div class="cdc-hint">Le cockpit n'exécute que des recettes connues : il envoie un identifiant, une action et une portée, jamais une commande. <b>Pour moi</b> installe dans votre espace, sans privilège ; <b>pour tous</b> (⚠) installe sur la machine entière, en sudo, et demande d'être administrateur. La commande exacte est montrée avant d'agir.</div>
  ${vm.groupes.map(g => html`<div class="eg-grp"><h3>${g.label} <span class="pv-def">${g.help}</span></h3>
    ${g.rows.map(Ligne)}</div>`)}
  ${journal ? html`<pre class="eg-out">${journal}</pre>` : ""}`;
}
