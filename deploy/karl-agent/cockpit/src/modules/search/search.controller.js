// controllers/search.controller — la carte « Rechercher un ticket » du panneau 🎫 (RM2770/2639/2830/2795). RM2889.
//
// Hôte : la carte #searchcard (champ, ✕, source, client, projet, statut, étiquette, avertissement, résultats).
// Le monolithe prête les projets connus, le contexte client, les statuts NORMS (CFG), le lien de titre (fiche ℹ),
// la marque d'épinglage (routeur), et ce qu'un clic déclenche : préparer le lanceur sur le ticket.
import { mount } from "../../core/dom.js";
import { html } from "../../core/html.js";
import { SearchService } from "./search.service.js";
import { SearchResultsViewModel, SearchFiltersViewModel } from "./SearchViewModel.js";
import { SearchResults, Options } from "./Search.view.js";

export function mountSearch(card, ctx = {}) {
  const svc = ctx.service || new SearchService();
  const notify = ctx.notify || (() => {});
  const q = (sel) => (card && card.querySelector ? card.querySelector(sel) : null);
  const val = (sel) => { const el = q(sel); return el ? String(el.value || "") : ""; };
  const projects = () => (ctx.projects ? ctx.projects() : null) || [];
  const ctxClient = () => (ctx.clientContext ? ctx.clientContext() : "") || "";
  const deps = { titleLink: ctx.titleLink || ((rm, t) => String(t)), pin: ctx.pinOf || (() => "") };
  const filters = () => ({ source: val("#sf-source"), client: val("#sf-client"), project: val("#sf-project"), status: val("#sf-status"), tag: val("#sf-tag") });
  const query = () => val("#search").trim();

  async function search() {
    if (!resH) return;
    const warn = q("#sf-warn"); if (warn) warn.style.display = "none";
    try {
      const r = await svc.search(query(), filters(), ctxClient());
      // RM2770 : une panne Redmine s'affiche À CÔTÉ des résultats locaux, jamais à leur place
      const vm = new SearchResultsViewModel({ results: r.results, error: r.redmine_error, base: ctx.redmineBase ? ctx.redmineBase() : "" });
      if (r.redmine_error && warn) { warn.textContent = vm.error; warn.style.display = ""; }
      resH.update(SearchResults(vm, deps));
    } catch (e) { resH.update(html`<div class="empty">erreur : ${e.message}</div>`); }
  }
  /** Relance seulement s'il y a une requête saisie (après une création, un changement de contexte). */
  function refreshIfQuery() { if (query()) search(); }
  function clear() { const i = q("#search"); if (i) i.value = ""; if (resH) resH.update(""); if (i && i.focus) i.focus(); }
  function fillProjects() {
    const ps = q("#sf-project"); if (!ps) return;
    const r = new SearchFiltersViewModel({ projects: projects(), client: val("#sf-client"), ctxClient: ctxClient(), project: ps.value }).projects;
    ps.innerHTML = String(Options(r.options, r.value, "tous les projets")); ps.value = r.value;
  }
  /** Les projets sont connus : clients, statuts (une fois), projets. */
  function init() {
    const vm = new SearchFiltersViewModel({ projects: projects(), statuses: ctx.statuses ? ctx.statuses() : [] });
    const cs = q("#sf-client"); if (cs) { const cur = cs.value; cs.innerHTML = String(Options(vm.clients, cur, "tous les clients")); cs.value = vm.clients.includes(cur) ? cur : ""; }
    const st = q("#sf-status"); if (st && (!st.options || st.options.length <= 1)) st.innerHTML = String(Options(vm.statuses, "", "tous les statuts"));
    fillProjects();
  }
  /** RM2830 : le menu d'étiquettes vient de GET /tags ; un rafraîchissement ne défait pas le filtre. Les autres menus (triage) sont prévenus. */
  async function loadTags() {
    const tags = await svc.loadTags();
    const sel = q("#sf-tag"); if (sel) { const cur = sel.value; sel.innerHTML = String(Options(new SearchFiltersViewModel({ tags }).tags, cur, "toutes les étiquettes")); sel.value = cur; }
    if (ctx.onTags) ctx.onTags(tags);
    return tags;
  }
  /** RM2832 : clic sur une étiquette ailleurs → la recherche s'y règle (une étiquette inconnue du menu y est ajoutée). */
  function setTag(tag) {
    const sel = q("#sf-tag"); tag = String(tag || "");
    if (sel) { if (tag && !(sel.options && [...sel.options].some(o => o.value === tag))) sel.insertAdjacentHTML("beforeend", String(html`<option value="${tag}">${tag}</option>`)); sel.value = tag; }
    const i = q("#search"); if (i) i.value = "";
    return search();
  }
  function pick(rm) { if (ctx.pick) ctx.pick(rm); }
  function openRedmine(n) { if (n.dataset.url) { if (ctx.openExternal) ctx.openExternal(n.dataset.url); } else notify("URL Redmine non configurée sur cette instance", true); }

  const resEl = q("#results");
  const resH = resEl ? mount(resEl, "", { events: [["click", "[data-action]", (e, n) => { e.stopPropagation(); if (n.dataset.action === "pick") pick(n.dataset.rm); else if (n.dataset.action === "redmine") openRedmine(n); }]] }) : null;
  const disposers = [];
  const listen = (el, type, fn) => { if (el && el.addEventListener) { el.addEventListener(type, fn); disposers.push(() => el.removeEventListener(type, fn)); } };
  listen(card, "keydown", (e) => { if (e.target && e.target.id === "search" && e.key === "Enter") search(); });
  listen(card, "change", (e) => { const id = (e.target && e.target.id) || ""; if (id === "sf-client") { fillProjects(); search(); } else if (/^sf-(source|project|status|tag)$/.test(id)) search(); });
  listen(card, "click", (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (n && n.dataset.action === "clear" && !(resEl && resEl.contains && resEl.contains(n))) { e.preventDefault(); clear(); } });
  return { search, refreshIfQuery, clear, fillProjects, init, loadTags, setTag, filters, query, tags: () => svc.tags, last: () => svc.last,
    unmount() { if (resH) resH.unmount(); disposers.forEach(d => d()); disposers.length = 0; } };
}
