// controllers/outline.controller — l'onglet 🗺 conversation de la colonne de droite (RM2330/2466/2549/2596/2601). RM2889.
//
// Hôtes : `body` (#outbody), `count` (#outcnt), `nav` (la barre .outnav : sauts, direct, ⟳, recherche, filtres).
// La position atteinte, la recherche, le filtre et l'entrée dépliée vivent ICI (ex-outPos/outQuery/outFilter/outOpen).
// Le monolithe prête la session attachée, les toasts, linkify (refs cliquables), et lui envoie les raccourcis clavier.
import { mount } from "../../core/dom.js";
import { OutlineService } from "./outline.service.js";
import { OutlineViewModel } from "./OutlineViewModel.js";
import { OutlineList } from "./Outline.view.js";
import { outlineStep, outlineNextUnresolved, outlineFull, OUT_FILTERS } from "./outline.js";

export function mountOutline({ body, count, nav } = {}, ctx = {}) {
  const svc = ctx.service || new OutlineService({ clipboard: ctx.clipboard });
  const notify = ctx.notify || (() => {});
  const attached = () => { const a = ctx.attached ? ctx.attached() : null; return a == null ? null : String(a); };
  const state = { pos: null, query: "", filter: "all", open: null };
  const deps = { linkify: ctx.linkify || ((s) => String(s == null ? "" : s)) };

  function render() {
    const vm = new OutlineViewModel({ items: svc.items, source: svc.source, query: state.query, filter: state.filter, pos: state.pos, open: state.open, attached: attached() });
    if (count) count.textContent = vm.count;
    if (bodyH) bodyH.update(OutlineList(vm, deps));
    return vm;
  }
  /** Charge si rien n'est chargé (ou `force`) ; une seule requête à la fois. */
  async function load(force) {
    const a = attached(); if (!a) return;
    if (svc.items.length && !force) { render(); return; }
    try { const r = await svc.load(a); if (r) render(); }
    catch (e) { if (bodyH) bodyH.update(String(`<div class="empty">${String(e.message).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]))}</div>`)); }
  }
  /** Nouvelle session (ou plus de session) : tout remis à zéro, l'hôte dit ce qu'il attend. */
  function reset() {
    svc.reset(); state.pos = null; state.open = null;
    if (count) count.textContent = "";
    if (bodyH) bodyH.update(attached() ? '<div class="empty">chargement au dépliage…</div>' : '<div class="empty">attache une session…</div>');
  }
  const itemAt = (line) => svc.items.find(x => String(x.line) === String(line)) || null;
  async function jumpTo(it) {
    const a = attached(); if (!a || !it) return;
    state.pos = it.line;
    state.open = (state.open === it.line) ? null : it.line;      // RM2596 : accordéon (toggle à l'endroit du clic)
    render();
    if (body && body.querySelector) { const cur = body.querySelector(".oline.ocur"); if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "center" }); }
    try { await svc.scrollTo(a, it.line); } catch (e) { notify(e.message, true); }
  }
  function withItems(go) { if (!svc.items.length) load().then(go); else go(); }
  function jumpUser(dir) {
    withItems(() => { const it = outlineStep(svc.items, state.pos, dir); if (it) { jumpTo(it); return; } if (dir > 0) scrollLive(); else notify("Pas de message utilisateur plus haut"); });
  }
  function jumpUnresolved() { withItems(() => { const it = outlineNextUnresolved(svc.items, state.pos); if (it) jumpTo(it); else notify("Aucune question sans réponse dans cette conversation"); }); }
  async function scrollLive() {
    const a = attached(); if (!a) return;
    state.pos = null;
    if (svc.source === "transcript") { state.open = null; render(); return; }       // rien à replacer : on referme juste la lecture
    try { await svc.scrollLive(a); render(); notify("⤓ retour au direct"); } catch (e) { notify(e.message, true); }
  }
  function closeRead() { state.open = null; render(); }
  function setQuery(v) { state.query = String(v || ""); render(); }
  function setFilter(f) {
    state.filter = OUT_FILTERS.includes(f) ? f : "all";
    if (nav && nav.querySelectorAll) nav.querySelectorAll("[data-of]").forEach(b => b.classList.toggle("active", b.dataset.of === state.filter));
    render();
  }
  async function copy(line) { const it = itemAt(line); if (!it) return; if (await svc.copy(outlineFull(it))) notify("Message copié"); }

  const acts = { jump: (n) => jumpTo(itemAt(n.dataset.line)), copy: (n) => copy(n.dataset.line), "close-read": () => closeRead(),
    prev: () => jumpUser(-1), next: () => jumpUser(1), unresolved: () => jumpUnresolved(), live: () => scrollLive(), reload: () => load(true) };
  const bodyH = body ? mount(body, '<div class="empty">attache une session…</div>', { events: [["click", "[data-action]", (e, n) => { const f = acts[n.dataset.action]; if (f) { e.stopPropagation(); f(n); } }]] }) : null;
  const disposers = [];
  const listen = (el, type, fn) => { if (el && el.addEventListener) { el.addEventListener(type, fn); disposers.push(() => el.removeEventListener(type, fn)); } };
  listen(nav, "click", (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action],[data-of]") : null; if (!n) return; if (n.dataset.of !== undefined) { setFilter(n.dataset.of); return; } const f = acts[n.dataset.action]; if (f) f(n); });
  listen(nav, "input", (e) => { const t = e.target; if (t && t.id === "outq") setQuery(t.value); });
  return { load, render, reset, jumpTo, jumpUser, jumpUnresolved, scrollLive, closeRead, setQuery, setFilter, copy, items: () => svc.items, source: () => svc.source, state,
    unmount() { if (bodyH) bodyH.unmount(); disposers.forEach(d => d()); disposers.length = 0; } };
}
