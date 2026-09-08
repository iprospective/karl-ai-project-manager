// modules/cdc/cdc.controller — les trois panneaux centraux du CDC vivant (RM3044) : Fonctionnalités (table triable, filtre persistant),
// CDC (chapitres en sous-onglets, liens relatifs et ancres D/Q dans la page), Feuille de route. Un seul service, un seul CDC en contexte.
//
// Hôtes : `features` (#cdcfeat), `chapters` (#cdcchap), `roadmap` (#cdcroad). Le centre appelle `open(name)` à l'ouverture d'un panneau.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { CdcService } from "./cdc.service.js";
import { CdcHeaderViewModel, FeaturesViewModel, RoadmapViewModel, ChaptersViewModel } from "./CdcViewModel.js";
import { FeaturesPage, RoadmapPage, ChaptersPage } from "./Cdc.view.js";

export function mountCdc(hosts = {}, ctx = {}) {
  const svc = ctx.service || new CdcService({ storage: ctx.storage });
  const md = ctx.md || ((s) => String(s));
  const notify = ctx.notify || (() => {});
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const state = { sort: "id", desc: false, q: "", chapter: null, sec: null, qTimer: null };
  try { const s = ctx.storage && ctx.storage.getItem("karlCdcSort"); if (s) { const [k, d] = s.split(":"); state.sort = k || "id"; state.desc = d === "1"; } } catch (e) { /* stockage indisponible */ }
  const events = [["click", "[data-action]", (ev, el) => onAction(ev, el)], ["input", "[data-action=\"q\"]", (ev, el) => onQuery(el.value)]];
  const h = {
    features: hosts.features ? mount(hosts.features, "", { events }) : null,
    chapters: hosts.chapters ? mount(hosts.chapters, "", { events: events.concat([["click", "a[href]", (ev, a) => onLink(ev, a)]]) }) : null,
    roadmap: hosts.roadmap ? mount(hosts.roadmap, "", { events }) : null,
  };
  const head = (page) => new CdcHeaderViewModel({ cdcs: svc.cdcs || [], current: svc.current, page, error: svc.error });
  const sessionProjects = () => (ctx.sessionProjects ? ctx.sessionProjects() : []);

  async function open(name, force) {
    await svc.load(sessionProjects(), force);
    if (name === "cdc-features") return renderFeatures();
    if (name === "cdc-roadmap") return renderRoadmap();
    return renderChapters();
  }
  async function renderFeatures() { if (!h.features) return; h.features.update(html`chargement…`); try { const data = await svc.features(); h.features.update(FeaturesPage(head("cdc-features"), new FeaturesViewModel({ data, sort: state.sort, desc: state.desc, q: state.q }))); } catch (e) { h.features.update(html`<div class="empty">registre injoignable : ${e.message}</div>`); } }
  async function renderRoadmap() { if (!h.roadmap) return; h.roadmap.update(html`chargement…`); try { const data = await svc.features(); h.roadmap.update(RoadmapPage(head("cdc-roadmap"), new RoadmapViewModel({ data }))); } catch (e) { h.roadmap.update(html`<div class="empty">registre injoignable : ${e.message}</div>`); } }
  async function renderChapters() {
    if (!h.chapters) return;
    const c = svc.current; if (!c) { h.chapters.update(ChaptersPage(head("cdc"), new ChaptersViewModel({}), { md })); return; }
    if (!state.chapter || !(c.chapters || []).some(ch => ch.path === state.chapter)) state.chapter = c.path;
    let text = "";
    try { text = await svc.chapter(state.chapter); } catch (e) { text = "*(chapitre introuvable : " + e.message + ")*"; }
    h.chapters.update(ChaptersPage(head("cdc"), new ChaptersViewModel({ cdc: c, path: state.chapter, md: text }), { md }));
    if (state.sec) { const id = state.sec; state.sec = null; later(() => { const n = h.chapters.el && h.chapters.el.querySelector ? h.chapters.el.querySelector("#sec-" + id) : null; if (n && n.scrollIntoView) n.scrollIntoView({ block: "center" }); }, 0); }
  }
  /** Ouvre le CDC sur un chapitre (chemin) et, si donné, une section (D012…) ; `key` change de CDC. */
  function goto({ key, path, sec } = {}) { if (key) svc.select(key); if (path) state.chapter = path; state.sec = sec || null; if (ctx.openPanel) ctx.openPanel("cdc"); else renderChapters(); }
  function onAction(ev, el) {
    const a = el.dataset.action; if (ev && ev.preventDefault && a !== "q") ev.preventDefault();
    if (a === "page") { if (ctx.openPanel) ctx.openPanel(el.dataset.page); }
    else if (a === "select") { svc.select(el.dataset.key); state.chapter = null; rerender(); }
    else if (a === "sort") { const k = el.dataset.key; if (state.sort === k) state.desc = !state.desc; else { state.sort = k; state.desc = false; } try { if (ctx.storage) ctx.storage.setItem("karlCdcSort", state.sort + ":" + (state.desc ? 1 : 0)); } catch (e) { /* */ } renderFeatures(); }
    else if (a === "chapter") { state.chapter = el.dataset.path; state.sec = null; renderChapters(); }
    else if (a === "ticket") { if (ctx.showTicket) ctx.showTicket(el.dataset.rm); else notify("fiche RM" + el.dataset.rm); }
  }
  function onLink(ev, a) {
    const href = a.getAttribute("href"); const vm = new ChaptersViewModel({ path: state.chapter });
    if (href && href.startsWith("#sec-")) { ev.preventDefault(); state.sec = href.slice(5); renderChapters(); return; }
    if (vm.isDocLink(href)) { ev.preventDefault(); state.chapter = vm.resolve(href); state.sec = (href.split("#")[1] || "").replace(/^sec-/, "") || null; renderChapters(); }
  }
  function onQuery(q) { state.q = q; if (state.qTimer) return; state.qTimer = later(() => { state.qTimer = null; renderFeatures(); }, 200); }
  function rerender() { renderFeatures(); renderRoadmap(); renderChapters(); }
  return { open, goto, select: (k) => svc.select(k), current: () => svc.current, cdcs: () => svc.cdcs || [], state, svc, unmount() { for (const k of Object.keys(h)) if (h[k]) h[k].unmount(); } };
}
