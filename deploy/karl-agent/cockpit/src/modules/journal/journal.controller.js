// modules/journal/journal.controller — le panneau central « journal » (RM3011) et le badge de l'en-tête : filtres persistés, relecture du
// serveur par `since` toutes les 5 s tant que le panneau est visible (suivi), entrées du front en direct, copie, purge. RM3011.
//
// Hôtes : `card` (#journalcard, dans le panneau central #cp-journal), `badge` (#ln-journal sur le bouton d'en-tête). Le centre appelle
// `setVisible(on)` en montrant/masquant le panneau ; `load()` à la première ouverture.
import { JournalService } from "./journal.service.js";
import { JournalViewModel } from "./JournalViewModel.js";
import { Panel, Rows } from "./Journal.view.js";
import { mount, paint } from "../../core/dom.js";

export function mountJournal({ card, badge } = {}, ctx = {}) {
  const svc = ctx.service || new JournalService({ storage: ctx.storage, log: ctx.log });
  const notify = ctx.notify || (() => {});
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const clear = ctx.clear || ((id) => clearTimeout(id));
  let visible = false, timer = null, loaded = false, qTimer = null;
  const vm = () => new JournalViewModel({ entries: svc.entries(), level: svc.level, cats: svc.cats, categories: svc.categories, q: svc.q, paused: svc.paused, error: svc.error, stats: svc.stats });
  const h = card ? mount(card, "", { events: [["click", "[data-action]", (ev, el) => onAction(ev, el)], ["change", "[data-action]", (ev, el) => onChange(ev, el)], ["input", "[data-action=\"q\"]", (ev, el) => onQuery(el.value)]] }) : null;
  function paintBadge() { if (!badge) return; const n = svc.badge(); badge.textContent = n ? String(n) : ""; badge.style.display = n && !visible ? "" : "none"; }
  function render() { if (!h) return; const v = vm(); h.update(Panel(v)); const list = card.querySelector ? card.querySelector('[data-role="list"]') : null; if (list && !svc.paused && list.scrollTop !== undefined) list.scrollTop = list.scrollHeight; }
  function renderRows() { const list = card && card.querySelector ? card.querySelector('[data-role="list"]') : null; if (!list) return render(); paint(list, Rows(vm())); if (!svc.paused) list.scrollTop = list.scrollHeight; }
  async function load(reset) { await svc.load(reset); loaded = true; render(); }
  async function tick() { timer = null; if (!visible) return; if (!svc.paused) { await svc.load(false); renderRows(); } timer = later(tick, 5000); }
  /** Le centre montre ou masque le panneau : suivi actif seulement quand il est visible ; l'ouvrir remet le badge à zéro. */
  function setVisible(on) {
    visible = !!on;
    if (visible) { svc.markSeen(); paintBadge(); if (!loaded) load(true); else render(); if (!timer) timer = later(tick, 5000); }
    else { if (timer) { clear(timer); timer = null; } paintBadge(); }
  }
  svc.onFront = () => { if (visible) { if (!svc.paused) renderRows(); svc.markSeen(); } paintBadge(); };
  function onAction(ev, el) {
    const a = el.dataset.action;
    if (a === "cat") { svc.toggleCat(el.dataset.cat); render(); }
    else if (a === "cat-all") { svc.clearCats(); render(); }
    else if (a === "pause") { svc.togglePause(); render(); }
    else if (a === "reload") load(true);
    else if (a === "clear-front") { svc.clearFront(); render(); }
    else if (a === "copy") { const txt = vm().plain; const done = () => notify("journal copié (" + vm().count + " entrées)"); if (ctx.clipboard && ctx.clipboard.writeText) ctx.clipboard.writeText(txt).then(done, () => notify("copie impossible", true)); else if (ctx.copyFallback && ctx.copyFallback(txt)) done(); else notify("copie impossible", true); }
  }
  function onChange(ev, el) { if (el.dataset.action === "level") { svc.setLevel(el.value); render(); } }
  function onQuery(q) { svc.setQuery(q); if (qTimer) clear(qTimer); qTimer = later(() => { qTimer = null; renderRows(); }, 200); }
  paintBadge();
  return { load, render, setVisible, paintBadge, entries: () => svc.entries(), svc, unmount() { if (timer) clear(timer); if (qTimer) clear(qTimer); svc.dispose(); if (h) h.unmount(); } };
}
