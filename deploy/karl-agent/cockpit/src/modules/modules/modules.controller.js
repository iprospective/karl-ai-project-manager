// modules/modules/modules.controller — le panneau « Modules » (RM3145, lot 3) : ce que l'instance
// porte, ce qui casserait en désactivant, et ce qu'elle porte encore sans module. En lecture.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { ModulesService } from "./modules.service.js";
import { ModulesViewModel } from "./ModulesViewModel.js";
import { ModulesCard } from "./Modules.view.js";

export function mountModules(el, ctx = {}) {
  const svc = ctx.service || new ModulesService();
  const state = { open: "" };
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)]] });
  const vm = () => new ModulesViewModel({ data: svc.data, error: svc.error, open: state.open });
  const render = () => h.update(ModulesCard(vm()));

  async function open() {
    h.update(html`<h2>🧩 Modules</h2><div class="empty">lecture du registre…</div>`);
    await svc.load();
    render();
    return svc.data;
  }
  function onAction(ev, n) {
    if (ev && ev.preventDefault) ev.preventDefault();
    if (n.dataset.action !== "open") return;
    // Un second clic referme : le détail est long, et on compare deux modules en les ouvrant tour à tour.
    state.open = state.open === n.dataset.name ? "" : (n.dataset.name || "");
    render();
  }
  return Object.assign(h, { open, render, state, svc, vm });
}
