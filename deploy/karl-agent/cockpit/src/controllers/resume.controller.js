// controllers/resume.controller — la carte « Reprendre une session » du lanceur (RM1939/2834/2991/2418). RM2889.
//
// Hôte : la carte #rescard (champ de recherche, case transcript, sélecteurs client/projet/statut/moteur, ⟳, liste).
// Le monolithe prête les projets connus (/projects), le contexte client, le lanceur (RM), l'attache, les toasts,
// la pastille de marque, et ce qu'il refait après une reprise (sessions, santé, alerte de jeu plein).
import { mount } from "../core/dom.js";
import { html } from "../core/html.js";
import { ResumeService } from "../services/resume.service.js";
import { ResumeListViewModel, ResumeFiltersViewModel } from "../viewmodels/sessions/ResumeViewModel.js";
import { ResumeList, SelectOptions } from "../views/sessions/Resume.view.js";
import { resumeAnchorDefault } from "../models/sessions/resume.js";

export function mountResume(card, ctx = {}) {
  const svc = ctx.service || new ResumeService();
  const notify = ctx.notify || (() => {});
  const ask = ctx.prompt || ((m, d) => window.prompt(m, d));
  const q = (sel) => (card && card.querySelector ? card.querySelector(sel) : null);
  const val = (sel) => { const el = q(sel); return el ? (el.type === "checkbox" ? !!el.checked : String(el.value || "")) : (sel === "#rs-deep" ? false : ""); };
  const projects = () => (ctx.projects ? ctx.projects() : null) || [];
  const state = { engines: [], timer: null, projectsSet: false };
  const deps = { markPill: ctx.markPill || (() => "") };

  const filters = () => ({ engine: val("#rs-engine"), project: val("#rs-project"), client: val("#rs-client"), status: val("#rs-status"), q: val("#rs-q"), deep: val("#rs-deep") });
  async function load() {
    if (!listH) return;
    listH.update(html`<div class="empty">chargement…</div>`);
    const f = filters();
    try { const r = await svc.search(f); listH.update(ResumeList(new ResumeListViewModel({ resumable: r.resumable, archived: r.archived, needle: f.q }, { ago: ctx.ago }), deps)); }
    catch (e) { listH.update(html`<div class="empty">erreur : ${e.message}</div>`); }
  }
  /** RM2991 : frappe amortie — la dernière touche gagne. */
  function queryChanged() { clearTimeout(state.timer); state.timer = setTimeout(load, 250); }
  function clearSearch() { const i = q("#rs-q"); if (!i) return; i.value = ""; load(); if (i.focus) i.focus(); }
  /** RM2834 : le client filtre les projets ; le projet d'un autre client ne survit pas au changement. */
  function fillProjects() {
    const ps = q("#rs-project"); if (!ps) return "";
    const vm = new ResumeFiltersViewModel({ projects: projects(), client: val("#rs-client"), project: ps.value });
    const r = vm.projects; ps.innerHTML = String(SelectOptions(r.options, r.value, "tous")); ps.value = r.value; return r.value;
  }
  /** Les projets connus arrivent (ou changent) : le sélecteur client se peuple, le projet suit. */
  function setProjects() {
    const cs = q("#rs-client"); if (cs) { const cur = cs.value; cs.innerHTML = String(SelectOptions(new ResumeFiltersViewModel({ projects: projects() }).clients, cur, "tous")); cs.value = cur; }
    fillProjects(); state.projectsSet = true;
  }
  /** RM2639/RM2834 : le contexte client pré-sélectionne le client, donc les projets, puis le projet du contexte s'il en fait partie — sans figer. */
  function applyClientContext(client, project) {
    const cs = q("#rs-client"); if (cs) cs.value = client || "";
    fillProjects();
    if (project) { const ps = q("#rs-project"); if (ps) ps.value = project; }
  }
  /** RM2539 : les moteurs reprenables viennent de la conf serveur. */
  function setEngines(engines) {
    state.engines = engines || []; const sel = q("#rs-engine"); if (!sel) return;
    const prev = sel.value; sel.innerHTML = String(SelectOptions(state.engines, prev, "tous")); if (state.engines.includes(prev)) sel.value = prev;
  }
  const sessionById = (sid) => (svc.last.resumable || []).find(s => String(s.session_id) === String(sid)) || null;
  async function resume(s) {
    if (!s) return;
    const dflt = resumeAnchorDefault(s, ctx.launcherRm ? ctx.launcherRm() : "");
    const rm = ask("Ancrage — ticket RM<id> (idéal), slug, ou vide = slug auto :", dflt || "");
    if (rm === null) return;
    try {
      const res = await svc.resume(s, rm);
      notify(res.message, !res.ok); if (!res.ok) return;
      if (ctx.afterResume) await ctx.afterResume(res.r);       // RM2450/2951 alerte, sessions, santé
      load();                                                   // RM2396 : le panneau ne reste pas périmé
      if (ctx.attach) setTimeout(() => ctx.attach(res.r.rm_id), 400);
    } catch (e) { notify(e.message, true); }
  }
  async function move(s) {
    if (!s) return;
    if (s.live) { notify("Session à tmux vivant : ferme-la d'abord", true); return; }
    const known = projects().map(p => p.value);
    if (!known.length) { notify("Liste des projets non chargée", true); return; }
    const cur = val("#rs-project") || (s.client ? s.client + "/" + s.project : "");
    const target = ask("Déplacer cette session vers quel projet ? (client/projet)\nex. iprospective/pm-ai-agents", cur);
    if (target === null) return;
    try { const res = await svc.move(s, target, known); notify(res.message, !res.ok); if (res.ok) await load(); }
    catch (e) { notify(e.message, true); }
  }

  const listEl = q("#rs-list");
  const listH = listEl ? mount(listEl, "", { events: [["click", "[data-action]", (e, n) => { e.stopPropagation(); const s = sessionById(n.dataset.sid); if (n.dataset.action === "move") move(s); else if (n.dataset.action === "resume") resume(s); }]] }) : null;
  const disposers = [];
  const listen = (el, type, fn) => { if (el && el.addEventListener) { el.addEventListener(type, fn); disposers.push(() => el.removeEventListener(type, fn)); } };
  listen(card, "input", (e) => { const t = e.target; if (t && t.id === "rs-q") queryChanged(); });
  listen(card, "change", (e) => { const t = e.target, id = (t && t.id) || ""; if (id === "rs-client") { fillProjects(); load(); } else if (/^(rs-deep|rs-project|rs-status|rs-engine)$/.test(id)) load(); });
  listen(card, "click", (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (!n || (listEl && listEl.contains && listEl.contains(n) && n !== listEl)) return; if (n.dataset.action === "clear") { e.preventDefault(); clearSearch(); } else if (n.dataset.action === "reload") { e.preventDefault(); load(); } });
  return { load, queryChanged, clearSearch, fillProjects, setProjects, applyClientContext, setEngines, resume, move, filters, state, last: () => svc.last,
    unmount() { clearTimeout(state.timer); if (listH) listH.unmount(); disposers.forEach(d => d()); disposers.length = 0; } };
}
