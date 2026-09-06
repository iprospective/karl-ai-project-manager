// modules/memory/memory.controller — le panneau central « mémoire » (RM3007) et le bloc « sonde » des réglages : une seule sonde
// (core/probe, prêtée par boot.js), démarrée si la préférence de ce navigateur le dit, re-rendue à chaque échantillon quand le
// panneau est visible. Hôtes : `card` (#memorycard), `settings` (#probecard). Le centre appelle `setVisible(on)`.
import { MemoryViewModel } from "./MemoryViewModel.js";
import { Panel, SettingsBlock } from "./Memory.view.js";
import { readOn, writeOn, readInterval, writeInterval, INTERVALS } from "./memory.js";
import { mount } from "../../core/dom.js";

export function mountMemory({ card, settings } = {}, ctx = {}) {
  const probe = ctx.probe; if (!probe) throw new Error("mountMemory : la sonde (ctx.probe) est requise");
  const notify = ctx.notify || (() => {});
  const storage = ctx.storage || null;
  let visible = false, interval = readInterval(storage);
  const vm = () => new MemoryViewModel({ probe, on: probe.on, interval });
  const events = [["click", "[data-action]", (ev, el) => onAction(el)], ["change", "[data-action]", (ev, el) => onChange(el)]];
  const h = card ? mount(card, "", { events }) : null;
  const s = settings ? mount(settings, "", { events }) : null;
  function render() { const v = vm(); if (h && visible) h.update(Panel(v)); if (s) s.update(SettingsBlock(v)); }
  function start() { probe.start(interval * 1000); writeOn(storage, true); render(); }
  function stop() { probe.stop(); writeOn(storage, false); render(); }
  function toggle() { if (probe.on) { stop(); notify("sonde mémoire arrêtée"); } else { start(); notify("sonde mémoire démarrée (toutes les " + interval + " s)"); } }
  function onAction(el) {
    const a = el.dataset.action;
    if (a === "toggle" && el.tagName !== "INPUT" && el.type !== "checkbox") toggle();
    else if (a === "tick") { probe.tick(); }
    else if (a === "reset") { probe.reset(); render(); }
    else if (a === "export") { const name = "karl-memoire-" + new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-") + ".json"; if (ctx.download) { ctx.download(name, JSON.stringify(probe.toJSON(), null, 1)); notify("historique exporté : " + name); } else notify("export indisponible", true); }
    else if (a === "help" && ctx.help) ctx.help("reglages");
  }
  function onChange(el) {
    const a = el.dataset.action;
    if (a === "toggle") toggle();
    else if (a === "interval") { const v = Number(el.value); if (INTERVALS.includes(v)) { interval = v; writeInterval(storage, v); if (probe.on) probe.start(v * 1000); render(); } }
  }
  function setVisible(on) { visible = !!on; if (visible) render(); }
  const off = probe.subscribe(() => render());
  if (h) h.track(off); else if (s) s.track(off);
  if (readOn(storage) && !probe.on) probe.start(interval * 1000);
  render();
  return { render, setVisible, toggle, start, stop, interval: () => interval, probe, unmount() { if (h) h.unmount(); if (s) s.unmount(); } };
}
