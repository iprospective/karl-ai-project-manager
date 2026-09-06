// views/testqueue/TestQueue — le panneau « 🧪 À tester » (RM2210/2315/2588). Balisage repris ; gestes en data-*.
import { html, raw } from "../../core/html.js";
const SORTS = [["oldest", "plus ancien d'abord"], ["newest", "plus récent d'abord"], ["rm-desc", "RM ↓"], ["rm-asc", "RM ↑"], ["project", "par projet"]];
export function TestQueueItem(it) {
  return html`<li style="cursor:default"><div class="r-top"><span class="r-id">RM${it.rm}</span>${raw(it.pin)}<span class="pill ${it.dem ? "warn" : ""}">${it.dem ? "demandeur" : "dev"}</span><span class="r-title" title="${it.title}">${it.title}</span></div><div class="r-meta">${it.project}${it.branch ? " · " + it.branch : ""}${it.link
    ? (it.link.href ? html` · <a href="${it.link.href}" target="_blank">${it.link.label} ↗</a>${it.link.live && it.link.href.startsWith("https") ? html` <span title="instance de test en ligne" style="color:var(--ok,#3fb950)">●</span>` : ""}` : html` · <span title="${it.link.warn}" style="color:var(--muted)">${it.link.label} ⚠</span>`) : ""}</div><div class="rels" style="margin-top:5px"><button class="chip" data-action="review" data-rm="${it.rm}">🧪 revue</button>${it.actions.map(a => a.action
    ? html`<button class="chip" data-action="${a.action}" data-rm="${it.rm}" title="${a.title || ""}">${a.label}</button>`
    : html`<span class="pill" title="${a.title}" style="opacity:.5">${a.label}</span>`)}<button class="chip" data-action="verdict" data-kind="valider" data-rm="${it.rm}">✅ testé OK → fermer</button><button class="chip" data-action="verdict" data-kind="mep" data-rm="${it.rm}">🚧 testé OK → MEP</button><button class="chip" data-action="verdict" data-kind="renvoyer" data-rm="${it.rm}">↩ KO → corriger</button></div></li>`;
}
export function TestQueuePanel(vm, { loading = false } = {}) {
  const f = vm.f, items = vm.items();
  return html`<h2>🧪 À tester <span class="tq-count" id="tq-count" style="color:var(--muted);font-weight:normal">${vm.count}</span> <button class="helpq" data-action="help" title="Aide sur ce panneau">?</button></h2>
<div class="searchrow" style="margin-top:8px"><input id="tq-q" type="text" data-filter="q" value="${f.q || ""}" placeholder="mots-clés : id, titre, projet, branche, tag…"><button class="mini" data-action="clear" title="Vider la recherche">✕</button></div>
<div class="row2" style="margin-top:8px"><div><label for="tq-project">Projet</label><select id="tq-project" data-filter="project"><option value=""${!f.project ? " selected" : ""}>tous</option>${vm.projects.map(p => html`<option value="${p}"${p === f.project ? " selected" : ""}>${p}</option>`)}</select></div><div><label for="tq-status">Statut</label><select id="tq-status" data-filter="status"><option value="">tous</option><option value="a_tester_demandeur"${f.status === "a_tester_demandeur" ? " selected" : ""}>demandeur</option><option value="a_tester_dev"${f.status === "a_tester_dev" ? " selected" : ""}>dev</option></select></div></div>
<div class="row2"><div><label for="tq-sort">Tri</label><select id="tq-sort" data-filter="sort">${SORTS.map(([v, l]) => html`<option value="${v}"${(f.sort || "oldest") === v ? " selected" : ""}>${l}</option>`)}</select></div><div><label for="tq-deployable">&nbsp;</label><label style="display:flex;align-items:center;gap:6px;margin:0;color:var(--fg);font-size:12px"><input type="checkbox" id="tq-deployable" data-filter="deployable" style="width:auto"${f.deployable ? " checked" : ""}> déployables</label></div></div>
<button class="mini" style="margin-top:8px" data-action="refresh">⟳ Rafraîchir</button>
<ul class="results" id="tq-list">${loading ? html`<li style="color:var(--muted)">chargement…</li>` : items.length ? items.map(TestQueueItem) : html`<li style="color:var(--muted)">${vm.emptyText}</li>`}</ul>`;
}

TestQueuePanel.item = TestQueueItem;
