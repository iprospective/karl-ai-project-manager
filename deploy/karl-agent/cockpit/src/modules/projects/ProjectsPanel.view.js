// views/projects/ProjectsPanel — le panneau de gauche « 📁 Projets ». RM2889, L4.
// Balisage repris de #lp-projects et projectsPanelHtml (RM2760, RM2768) ; gestes en data-action.
import { html, raw } from "../../core/html.js";

export function ProjectsList(vm) {
  const cs = vm.clients();
  if (!cs.length) return html`<div class="empty">${vm.emptyText}</div>`;
  return html`${cs.map(g => html`<div class="oline" style="white-space:normal;cursor:pointer;font-weight:600" data-action="toggle" data-client="${g.client}" title="${g.ouvert ? "Replier" : "Déplier"} ${g.client}">${g.ouvert ? "▾ " : "▸ "}${g.client} <span style="color:var(--muted);font-weight:normal">(${g.projects.length})</span>${g.nLive ? html` <span class="pill ok">${g.nLive} ▶</span>` : ""}${g.isCtx ? html` <span class="pill" title="Client du contexte courant">ctx</span>` : ""} <span class="pjicons"><button class="mini" data-action="client" data-client="${g.client}" title="Fiche du client ${g.client} — contacts, projets, valeurs par défaut">🏢</button><button class="mini" data-action="conf" data-scope="client" data-client="${g.client}" data-project="" title="Configuration du client (meta.yml)">⚙</button></span></div>${g.ouvert ? g.projects.map(p =>
    html`<div class="oline" style="white-space:normal;cursor:pointer;padding-left:16px" data-action="project" data-value="${p.value}" title="Ouvrir la fiche de ${p.value} dans le panneau central">📄 ${p.project}${raw(p.pin || "")}${p.n ? html` <span class="pill ok" title="${p.n} session(s) en cours">${p.n} ▶</span>` : ""} <span class="pjicons"><button class="mini" data-action="conf" data-scope="project" data-client="${p.client}" data-project="${p.project}" title="Configuration du projet (meta.yml)">⚙</button></span></div>`) : ""}`)}`;
}

export function ProjectsPanel(vm) {
  return html`<div class="card">
    <h2>📁 Projets <span id="pj-count" style="color:var(--muted);font-weight:normal">${vm ? vm.count : ""}</span>
      <button class="helpq" data-action="help" title="Aide sur ce panneau">?</button></h2>
    <div class="searchrow">
      <input id="pj-filter" type="text" placeholder="filtrer : client ou projet…" value="${vm ? vm.filtre : ""}" aria-label="Filtrer les clients et projets">
      <button class="mini" data-action="clear" title="Vider le filtre">✕</button>
    </div>
    <div id="pj-list">${vm ? ProjectsList(vm) : html`<div class="empty">chargement…</div>`}</div>
  </div>`;
}
