// modules/feed/Notify.view — le panneau « fil ». Gestes en data-action, aucun on*. RM2792.
import { html } from "../../core/html.js";

const Head = (vm) => html`<div class="cdc-head">
  <div class="cdc-pages" role="tablist">${vm.vues.map(v => html`<button class="chip${v.on ? " on" : ""}" data-action="vue" data-vue="${v.key}">${v.label}</button>`)}</div>
  <div class="feed-filtres">${vm.users.map(u => html`<button class="chip${u.on ? " on" : ""}" data-action="user" data-user="${u.key}">${u.label}</button>`)}</div></div>`;

const Ligne = (r) => html`<tr class="${r.traite ? "feed-traite" : ""}">
  <td class="feed-etat" title="${r.etat}">${r.marque}</td>
  <td><span class="st ${r.cls}" title="${r.niveau}">${r.icone}</span></td>
  <td class="cdc-date">${r.quand}</td>
  <td class="feed-src">${r.origine}${r.job ? html`<span class="feed-job" title="le travail qui l'a émise">${r.job}</span>` : ""}</td>
  <td class="feed-msg">${r.msg}${r.mesure ? html` <span class="feed-mes" title="la mesure qui a déclenché l'alerte">${r.mesure}</span>` : ""}${r.repeats > 1 ? html` <span class="feed-rep" title="cette notification s'est répétée${r.fenetre ? " sur " + r.fenetre : ""}">×${String(r.repeats)}${r.fenetre ? html` <i>sur ${r.fenetre}</i>` : ""}</span>` : ""}
    ${r.user ? html` <span class="feed-user${r.prive ? " prive" : ""}" title="${r.prive ? "privée — visible de cette personne seule" : "concerne cette personne"}">${r.prive ? "🔒" : "@"}${r.user}</span>` : ""}
    ${r.rm ? html` <a class="feed-rm" href="#" data-action="ticket" data-rm="${r.rm}" title="Ouvrir la fiche du ticket">RM${r.rm}</a>` : ""}
    ${r.client || r.projet ? html` <span class="feed-ou" title="le projet concerné">${r.client ? r.client : ""}${r.client && r.projet ? " · " : ""}${r.projet ? r.projet : ""}</span>` : ""}
    ${r.sid ? html` <span class="feed-sid" title="émise depuis la session ${r.sid}">⧉ ${r.sid.slice(0, 8)}</span>` : ""}</td>
  <td class="cdc-act">${r.traite ? "" : html`<button class="mini soft" data-action="lu" data-id="${r.id}" title="Marquer lue — elle reste dans la file">○ lue</button><button class="mini" data-action="done" data-id="${r.id}" title="Marquer traitée — elle sort de la vue">✓ traitée</button>`}</td>
</tr>`;

export function FeedCard(vm) {
  const c = vm.counts;
  const titre = html`<h2>🔔 Fil <span class="cdc-count">${String(c.open)} en attente${c.neuf ? " · " + String(c.neuf) + " non lue(s)" : ""}${c.worst ? " · pire niveau : " + c.worst : ""}</span></h2>`;
  if (vm.error) return html`${titre}${Head(vm)}<div class="empty">fil illisible : ${vm.error}</div>`;
  if (vm.empty) return html`${titre}${Head(vm)}<div class="empty">${vm.etat === "ouvert" ? "rien n'attend." : "le fil est vide."}</div>`;
  return html`${titre}${Head(vm)}
    <div class="cdc-hint">Une <b>file</b>, pas un journal : chaque entrée attend d'être lue puis traitée, et une notification traitée sort de la vue. Une alerte qui se répète ne s'ajoute pas, elle remonte avec son compteur. Le fil est lu au nom de <b>${vm.viewer || "personne — les entrées privées n'apparaissent pas"}</b>.</div>
    <div class="cdc-tablewrap"><table class="cdc-table"><thead><tr><th></th><th>Niv.</th><th>Quand</th><th>Source</th><th>Notification</th><th class="cdc-act">${vm.etat === "ouvert" ? html`<button class="mini soft" data-action="done-all" title="Marquer traité tout ce qui attend dans cette vue">✓ tout</button>` : ""}</th></tr></thead>
    <tbody>${vm.rows().map(Ligne)}</tbody></table></div>`;
}
