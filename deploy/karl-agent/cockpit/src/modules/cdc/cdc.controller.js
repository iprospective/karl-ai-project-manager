// modules/cdc/cdc.controller — LE panneau central « CDC » (RM3044) : un seul menu en haut, et dedans trois onglets — Fonctionnalités
// (table triable, filtre persistant), CDC (chapitres en sous-onglets, liens relatifs et ancres D/Q dans la page), Feuille de route.
// Un seul service, un seul CDC en contexte, un seul hôte (#cdccard) ; l'onglet courant est mémorisé (karlCdcPage).
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { CdcService } from "./cdc.service.js";
import { CdcHeaderViewModel, FeaturesViewModel, RoadmapViewModel, ChaptersViewModel } from "./CdcViewModel.js";
import { FeaturesPage, RoadmapPage, ChaptersPage } from "./Cdc.view.js";

export function mountCdc(el, ctx = {}) {
  const svc = ctx.service || new CdcService({ storage: ctx.storage });
  const md = ctx.md || ((s) => String(s));
  const notify = ctx.notify || (() => {});
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const PAGES = ["cdc-features", "cdc", "cdc-roadmap"];
  const isPage = (p) => PAGES.includes(p) || (typeof p === "string" && p.startsWith("chap:"));
  const state = { page: "cdc-features", sort: "id", desc: false, q: "", chapter: null, sec: null, qTimer: null };
  try { const s = ctx.storage && ctx.storage.getItem("karlCdcSort"); if (s) { const [k, d] = s.split(":"); state.sort = k || "id"; state.desc = d === "1"; } const pg = ctx.storage && ctx.storage.getItem("karlCdcPage"); if (isPage(pg)) setPage(pg); } catch (e) { /* stockage indisponible */ }
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)], ["input", "[data-action=\"q\"]", (ev, n) => onQuery(n.value)], ["click", "a[href]", (ev, a) => onLink(ev, a)]] });
  const head = (page) => new CdcHeaderViewModel({ cdcs: svc.cdcs || [], current: svc.current, page, path: state.chapter, error: svc.error });
  const sessionProjects = () => (ctx.sessionProjects ? ctx.sessionProjects() : []);

  /** Ouvre le panneau sur un onglet (`page`, sinon le dernier) ; relit le contexte (session) à chaque ouverture. */
  async function open(page, force) {
    if (isPage(page)) setPage(page);
    await svc.load(sessionProjects(), force);
    return render();
  }
  /** `chap:<path>` = un chapitre précis (onglet à plat) ; « cdc » = le sommaire, ou le dernier chapitre ouvert. */
  function setPage(p) { if (p.startsWith("chap:")) { state.chapter = p.slice(5); p = "cdc"; } state.page = p; try { if (ctx.storage) ctx.storage.setItem("karlCdcPage", p === "cdc" && state.chapter ? "chap:" + state.chapter : p); } catch (e) { /* */ } }
  function render() { if (state.page === "cdc-features") return renderFeatures(); if (state.page === "cdc-roadmap") return renderRoadmap(); return renderChapters(); }
  async function renderFeatures() { h.update(html`chargement…`); try { const data = await svc.features(); if (state.page !== "cdc-features") return; h.update(FeaturesPage(head("cdc-features"), new FeaturesViewModel({ data, sort: state.sort, desc: state.desc, q: state.q }))); } catch (e) { h.update(html`<div class="empty">registre injoignable : ${e.message}</div>`); } }
  async function renderRoadmap() { h.update(html`chargement…`); try { const data = await svc.features(); if (state.page !== "cdc-roadmap") return; h.update(RoadmapPage(head("cdc-roadmap"), new RoadmapViewModel({ data }))); } catch (e) { h.update(html`<div class="empty">registre injoignable : ${e.message}</div>`); } }
  async function renderChapters() {
    const c = svc.current; if (!c) { h.update(ChaptersPage(head("cdc"), new ChaptersViewModel({}), { md })); return; }
    if (!state.chapter || !(c.chapters || []).some(ch => ch.path === state.chapter)) state.chapter = c.path;
    let text = "";
    try { text = await svc.chapter(state.chapter); } catch (e) { text = "*(chapitre introuvable : " + e.message + ")*"; }
    if (state.page !== "cdc") return;
    h.update(ChaptersPage(head("cdc"), new ChaptersViewModel({ cdc: c, path: state.chapter, md: text }), { md }));
    if (state.sec) { const id = state.sec; state.sec = null; later(() => { const n = h.el && h.el.querySelector ? h.el.querySelector("#sec-" + id) : null; if (n && n.scrollIntoView) n.scrollIntoView({ block: "center" }); }, 0); }
  }
  /** Ouvre le CDC (onglet chapitres) sur un chapitre (chemin) et, si donné, une section (D012…) ; `key` change de CDC. */
  function goto({ key, path, sec } = {}) { if (key) svc.select(key); if (path) state.chapter = path; state.sec = sec || null; setPage(state.chapter ? "chap:" + state.chapter : "cdc"); if (ctx.openPanel) ctx.openPanel(); render(); }
  function onAction(ev, el) {
    const a = el.dataset.action; if (ev && ev.preventDefault && a !== "q") ev.preventDefault();
    if (a === "page") { if (isPage(el.dataset.page)) { setPage(el.dataset.page); state.sec = null; render(); } }
    else if (a === "select") { svc.select(el.dataset.key); state.chapter = null; render(); }
    else if (a === "sort") { const k = el.dataset.key; if (state.sort === k) state.desc = !state.desc; else { state.sort = k; state.desc = false; } try { if (ctx.storage) ctx.storage.setItem("karlCdcSort", state.sort + ":" + (state.desc ? 1 : 0)); } catch (e) { /* */ } renderFeatures(); }
    else if (a === "chapter") { setPage("chap:" + el.dataset.path); state.sec = null; renderChapters(); }
    else if (a === "ticket") { if (ctx.showTicket) ctx.showTicket(el.dataset.rm); else notify("fiche RM" + el.dataset.rm); }
  }
  function onLink(ev, a) {
    const href = a.getAttribute("href"); const vm = new ChaptersViewModel({ path: state.chapter });
    if (state.page !== "cdc") return;
    if (href && href.startsWith("#sec-")) { ev.preventDefault(); state.sec = href.slice(5); renderChapters(); return; }
    if (vm.isDocLink(href)) { ev.preventDefault(); setPage("chap:" + vm.resolve(href)); state.sec = (href.split("#")[1] || "").replace(/^sec-/, "") || null; renderChapters(); }
  }
  function onQuery(q) { state.q = q; if (state.qTimer) return; state.qTimer = later(() => { state.qTimer = null; renderFeatures(); }, 200); }
  return { open, goto, render, page: () => state.page, select: (k) => svc.select(k), current: () => svc.current, cdcs: () => svc.cdcs || [], state, svc, unmount() { h.unmount(); } };
}
