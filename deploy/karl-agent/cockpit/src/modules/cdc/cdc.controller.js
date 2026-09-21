// modules/cdc/cdc.controller — LE panneau central « CDC » (RM3044) : un seul menu en haut, et dedans trois onglets — Fonctionnalités
// (table triable, filtre persistant), CDC (chapitres en sous-onglets, liens relatifs et ancres D/Q dans la page), Feuille de route.
// Un seul service, un seul CDC en contexte, un seul hôte (#cdccard) ; l'onglet courant est mémorisé (karlCdcPage).
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { CdcService } from "./cdc.service.js";
import { CdcHeaderViewModel, FeaturesViewModel, ChaptersViewModel } from "./CdcViewModel.js";
import { FeaturesPage, ChaptersPage } from "./Cdc.view.js";

export function mountCdc(el, ctx = {}) {
  const svc = ctx.service || new CdcService({ storage: ctx.storage });
  const md = ctx.md || ((s) => String(s));
  const notify = ctx.notify || (() => {});
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const PAGES = ["cdc-features", "cdc"];
  const isPage = (p) => PAGES.includes(p) || (typeof p === "string" && p.startsWith("chap:"));
  const state = { page: "cdc-features", sort: "id", desc: false, q: "", chapter: null, sec: null, qTimer: null };
  try { const s = ctx.storage && ctx.storage.getItem("karlCdcSort"); if (s) { const [k, d] = s.split(":"); state.sort = k || "id"; state.desc = d === "1"; } const pg = ctx.storage && ctx.storage.getItem("karlCdcPage"); if (isPage(pg)) setPage(pg); } catch (e) { /* stockage indisponible */ }
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)], ["input", "[data-action=\"q\"]", (ev, n) => onQuery(n.value)], ["click", "a[href]", (ev, a) => onLink(ev, a)],
    ["change", "[data-action=\"think-state\"]", (ev, n) => onThinkState(n)], ["change", "[data-action=\"feature-state\"]", (ev, n) => onFeatureState(n)],
    ["change", "[data-action=\"feature-version\"]", (ev, n) => onFeatureVersion(n)]] });
  const confirm = ctx.confirm || (() => true);
  const demande = ctx.prompt || ((m, d) => window.prompt(m, d));      // RM3258 : injectable, donc testable
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
  function render() { if (state.page === "cdc-features") return renderFeatures(); return renderChapters(); }
  async function renderFeatures() { h.update(html`chargement…`); try { const data = await svc.features(); if (state.page !== "cdc-features") return; h.update(FeaturesPage(head("cdc-features"), new FeaturesViewModel({ data, sort: state.sort, desc: state.desc, q: state.q }))); } catch (e) { h.update(html`<div class="empty">registre injoignable : ${e.message}</div>`); } }
  /** Les versions connues, pour le formulaire de la feuille de route et le rattachement d'une ligne.
   *  Lues du registre, sans appel supplémentaire quand il est déjà en cache. */
  async function versions() {
    try { return new FeaturesViewModel({ data: await svc.features() }).versions; } catch (e) { return []; }
  }
  async function renderChapters() {
    const c = svc.current; if (!c) { h.update(ChaptersPage(head("cdc"), new ChaptersViewModel({}), { md })); return; }
    if (!state.chapter || !(c.chapters || []).some(ch => ch.path === state.chapter)) state.chapter = c.path;
    let text = "";
    try { text = await svc.chapter(state.chapter); } catch (e) { text = "*(chapitre introuvable : " + e.message + ")*"; }
    if (state.page !== "cdc") return;
    const vmc = new ChaptersViewModel({ cdc: c, path: state.chapter, md: text });
    h.update(ChaptersPage(head("cdc"), vmc, { md, versions: vmc.isRoadmap ? await versions() : [] }));
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
    else if (a === "think-delete") { thinkDelete(el.dataset.rm, el.dataset.id); }
    else if (a === "think-move") { thinkMove(el.dataset.rm, el.dataset.id); }
    else if (a === "version-save") { versionSave(); }
    else if (a === "version-drop") { versionDrop(); }
  }
  /** RM3060 : le formulaire de la feuille de route, lu au moment du clic. */
  function vform() {
    const f = h.el && h.el.querySelector ? h.el.querySelector('[data-role="vform"]') : null;
    if (!f) return null;
    const v = (r) => { const n = f.querySelector('[data-role="' + r + '"]'); return n ? String(n.value || "").trim() : ""; };
    return { id: v("vid"), role: v("vrole"), critere: v("vcritere"), etat: v("vetat") };
  }
  async function versionSave() {
    const f = vform(); if (!f) return;
    if (!f.id) { notify("donne un identifiant de version (V1, V2…)", true); return; }
    try {
      await svc.versionEdit({ action: "add", version: f.id, role: f.role, critere: f.critere, etat: f.etat });
      notify("version " + f.id + " enregistrée"); await renderChapters();
    } catch (e) { notify("version refusée : " + e.message, true); }
  }
  async function versionDrop() {
    const f = vform(); if (!f || !f.id) { notify("nomme la version à retirer", true); return; }
    if (!confirm("Retirer la version " + f.id + " ?\n\nLes fonctionnalités qui la portent sont détachées, aucune n'est supprimée.")) return;
    try { await svc.versionEdit({ action: "drop", version: f.id }); notify("version " + f.id + " retirée"); await renderChapters(); }
    catch (e) { notify("retrait impossible : " + e.message, true); }
  }
  // RM3064 : édition d'une entrée depuis le panneau — le geste part vers le script (pm-task-think / pm-cdc-features), jamais vers le fichier
  // RM3258 : mal attribuée plutôt qu'illégitime — elle se déplace, elle ne se perd pas.
  async function thinkMove(rm, id) {
    const saisie = demande("Déplacer " + id + " de RM" + rm + " vers quel ticket ?\nNuméro RM :", "");
    if (saisie === null) return;
    const to = String(saisie).trim().replace(/^RM/i, "");
    if (!/^\d+$/.test(to)) { notify("numéro de ticket attendu", true); return; }
    try { await svc.thinkEdit({ rm, id, action: "move", to }); notify(id + " déplacée vers RM" + to + ", registres régénérés"); await renderChapters(); }
    catch (e) { notify("déplacement impossible : " + e.message, true); }
  }
  async function thinkDelete(rm, id) {
    if (!confirm("Supprimer l'entrée " + id + " du think de RM" + rm + " ? (définitif)")) return;
    try { await svc.thinkEdit({ rm, id, action: "delete" }); notify(id + " supprimée, registres régénérés"); await renderChapters(); }
    catch (e) { notify("suppression impossible : " + e.message, true); }
  }
  // RM3227 : trancher une QUESTION (valide / invalide) propose un commentaire facultatif — sa réponse,
  // consignée en décision « Qnnn : … » par le serveur. Annuler n'écrit rien (et remet le sélecteur).
  // RM3269 : TRANCHER une question appelle sa décision — l'outil la réclame désormais. Le cockpit
  // doit donc pouvoir la POSER (le commentaire devient la décision « Qnnn : … ») et, quand elle
  // n'est pas encore mûre, FORCER en connaissance de cause plutôt que de laisser l'UI bloquée :
  // une transition qu'on ne peut pas faire depuis l'écran n'est pas livrée. Écarter (invalide)
  // n'exige rien — écarter n'est pas trancher.
  async function onThinkState(n) {
    const state = n.value; if (!state) return;
    const estQuestion = /(^|-)Q\d/.test(n.dataset.id || "");
    let comment = "", force = false;
    if (estQuestion && (state === "valide" || state === "invalide")) {
      const tranche = state === "valide";
      const saisie = window.prompt(
        n.dataset.id + " → " + state + "\n"
        + (tranche ? "La DÉCISION qui tranche cette question (elle sera consignée « "
                     + n.dataset.id + " : … ») :"
                   : "Motif de l'écartement (facultatif) :"), "");
      if (saisie === null) { n.value = ""; return; }
      comment = saisie.trim();
      if (tranche && !comment) {
        if (!confirm(n.dataset.id + " : trancher SANS consigner de décision ?\n\n"
                     + "Le pourquoi restera manquant. La question sera retrouvable dans "
                     + "« ce qui manque » (questions tranchées sans décision).")) { n.value = ""; return; }
        force = true;
      }
    }
    const body = { rm: n.dataset.rm, id: n.dataset.id, action: "state", state };
    if (comment) body.comment = comment;
    if (force) body.force = true;
    try {
      await svc.thinkEdit(body);
      notify(n.dataset.id + " → " + state
             + (comment ? " · décision consignée" : force ? " · SANS décision (à reprendre)" : ""),
             force);
      await renderChapters();
    }
    catch (e) { notify("changement d'état impossible : " + e.message, true); }
  }
  async function onFeatureState(n) {
    const etat = n.value; if (!etat) return;
    try { await svc.featureEdit({ id: n.dataset.id, etat }); notify(n.dataset.id + " → " + etat + " (entrée figée)"); await renderFeatures(); }
    catch (e) { notify("changement d'état impossible : " + e.message, true); }
  }
  /** RM3060 : rattacher une fonctionnalité à une version, ou l'en détacher (« - »). */
  async function onFeatureVersion(n) {
    const v = n.value; if (!v) return;
    try {
      await svc.versionEdit({ action: "attach", id: n.dataset.id, version: v });
      notify(n.dataset.id + (v === "-" ? " détachée" : " → version " + v)); await renderFeatures();
    } catch (e) { notify("rattachement impossible : " + e.message, true); }
  }
  function onLink(ev, a) {
    const href = a.getAttribute("href"); const vm = new ChaptersViewModel({ path: state.chapter });
    if (state.page !== "cdc") return;
    if (href && href.startsWith("#sec-")) { ev.preventDefault(); state.sec = href.slice(5); renderChapters(); return; }
    if (vm.isDocLink(href)) { ev.preventDefault(); setPage("chap:" + vm.resolve(href)); state.sec = (href.split("#")[1] || "").replace(/^sec-/, "") || null; renderChapters(); }
  }
  function onQuery(q) { state.q = q; if (state.qTimer) return; state.qTimer = later(() => { state.qTimer = null; renderFeatures(); }, 200); }
  // RM3089 : la fiche d'un ticket tranche ses entrées par ICI (D022) — une seule route d'écriture,
  // une seule refusion des registres du projet.
  return { open, goto, render, page: () => state.page, select: (k) => svc.select(k), current: () => svc.current, cdcs: () => svc.cdcs || [],
    thinkEdit: (body) => svc.thinkEdit(body), state, svc, unmount() { h.unmount(); } };
}
