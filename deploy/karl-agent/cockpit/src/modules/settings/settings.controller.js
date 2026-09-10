// controllers/settings.controller — réglages serveur et thème local. RM2889, L5.
// Deux cartes du panneau « réglages », un contrôleur ; le thème effectif et
// applyTheme (script de tête, avant le premier paint) sont prêtés par le contexte.
import { mount } from "../../core/dom.js";
import { SettingsService } from "./settings.service.js";
import { SettingsViewModel } from "./SettingsViewModel.js";
import { SettingsBody, SettingsCard, ThemeCard } from "./Settings.view.js";
import { theme } from "./SettingsRepository.js";

export function mountSettings(el, themeEl, ctx = {}) {
  const svc = ctx.service || new SettingsService();
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const ask = ctx.confirm || ((m) => window.confirm(m));
  const store = ctx.storage || (typeof localStorage !== "undefined" ? localStorage : { getItem() { return null; }, setItem() {}, removeItem() {} });

  function paintTheme() {
    if (!themeHandle) return;
    const t = theme.read(store);
    themeHandle.update(ThemeCard({ local: t.local, hint: theme.hint(t, ctx.effectiveTheme ? ctx.effectiveTheme() : ""), showClientCtx: showClientCtx(), centerSplit: centerSplit(), helpSpots: helpSpots(), showMonitor: showMonitor() }));
  }
  /** RM3063 : le filtre « Clients » de l'en-tête est masqué par défaut ; l'option locale le réaffiche (le contexte mémorisé reste appliqué). */
  function showClientCtx() { try { return store.getItem("karlShowClientCtx") === "1"; } catch (e) { return false; } }
  // RM3051 : le split de la zone centrale est porté par la DISPOSITION (elle seule sait
  // masquer/rendre la session) ; les réglages ne font que l'exposer.
  function centerSplit() { return ctx.centerSplit ? !!ctx.centerSplit() : false; }
  function setCenterSplit(on) { if (ctx.setCenterSplit) ctx.setCenterSplit(!!on); paintTheme(); }
  /** RM3075 : repères « ? » — préférence de CE navigateur, affichés par défaut (ils servent à qui ne connaît pas l'écran). */
  function helpSpots() { return ctx.helpSpots ? !!ctx.helpSpots.enabled() : true; }
  function setHelpSpots(on) { if (ctx.helpSpots) ctx.helpSpots.toggle(!!on); paintTheme(); }
  /** RM3094 : commandes de panes tmux — préférence de CE navigateur, affichées par défaut (masquer
   *  d'office changerait le comportement d'une instance sans le dire). */
  function showMonitor() { try { return store.getItem("karlShowMonitor") !== "0"; } catch (e) { return true; } }
  function setShowMonitor(on) { try { store.setItem("karlShowMonitor", on ? "1" : "0"); } catch (e) { /* stockage indisponible */ } if (ctx.applyMonitor) ctx.applyMonitor(!!on); paintTheme(); }
  function setShowClientCtx(on) { try { store.setItem("karlShowClientCtx", on ? "1" : "0"); } catch (e) { /* stockage indisponible */ } if (ctx.applyClientCtx) ctx.applyClientCtx(!!on); paintTheme(); }
  function setServerTheme(v) { theme.setServer(store, v); if (ctx.applyTheme) ctx.applyTheme(); paintTheme(); }
  function setLocalTheme(v)  { theme.setLocal(store, v);  if (ctx.applyTheme) ctx.applyTheme(); paintTheme(); }

  async function load() {
    handle.update(SettingsCard());
    try { await svc.load(); handle.update(SettingsCard(SettingsBody(new SettingsViewModel({ settings: svc.settings })))); }
    catch (e) { handle.update(SettingsCard("")); notify(e.message, true); }
  }
  async function save(row, value, ctrl) {
    const entry = svc.settings.find(s => s.key === row.dataset.key); if (!entry) return;
    if (!ask("Modifier « " + entry.label + " » → " + value + " ?")) { await load(); return; }
    if (ctrl) ctrl.disabled = true;
    const r = await svc.save(entry, value);
    if (r.ok && r.themeChanged) setServerTheme(value);      // RM2386 : immédiat, sans rechargement
    notify(r.message, !r.ok);
    await load();
  }
  const handle = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => n.dataset.action === "help" ? ctx.help && ctx.help("reglages")
      : n.dataset.action === "save" ? save(n.closest("[data-key]"), (n.closest("[data-key]").querySelector("input") || {}).value, n) : undefined],
    ["change", "[data-setting]", (ev, n) => save(n.closest("[data-key]"), n.dataset.setting === "bool" ? n.checked : n.value, n)],
  ] });
  const themeHandle = themeEl ? mount(themeEl, "", { events: [["change", "[data-theme-local]", (ev, s) => setLocalTheme(s.value)], ["change", "[data-show-clientctx]", (ev, c) => setShowClientCtx(c.checked)], ["change", "[data-center-split]", (ev, c) => setCenterSplit(c.checked)], ["change", "[data-help-spots]", (ev, c) => setHelpSpots(c.checked)], ["change", "[data-show-monitor]", (ev, c) => setShowMonitor(c.checked)]] }) : null;
  paintTheme();
  if (ctx.applyClientCtx) ctx.applyClientCtx(showClientCtx());     // état initial de l'en-tête
  if (ctx.applyMonitor) ctx.applyMonitor(showMonitor());           // RM3094 : état initial de la barre du terminal
  return Object.assign(handle, { load, setServerTheme, setLocalTheme, paintTheme, showClientCtx, setShowClientCtx, centerSplit, setCenterSplit, helpSpots, setHelpSpots, showMonitor, setShowMonitor, unmountAll() { handle.unmount(); if (themeHandle) themeHandle.unmount(); } });
}
