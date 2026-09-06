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
    themeHandle.update(ThemeCard({ local: t.local, hint: theme.hint(t, ctx.effectiveTheme ? ctx.effectiveTheme() : "") }));
  }
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
  const themeHandle = themeEl ? mount(themeEl, "", { events: [["change", "[data-theme-local]", (ev, s) => setLocalTheme(s.value)]] }) : null;
  paintTheme();
  return Object.assign(handle, { load, setServerTheme, setLocalTheme, paintTheme, unmountAll() { handle.unmount(); if (themeHandle) themeHandle.unmount(); } });
}
