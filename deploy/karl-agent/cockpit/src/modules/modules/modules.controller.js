// modules/modules/modules.controller — le panneau « Modules » (RM3145, lot 3) : ce que l'instance
// porte, ce qui casserait en désactivant, et ce qu'elle porte encore sans module. RM3145 L1 :
// allumer, éteindre, et forcer sous double sécurité (réglage de l'instance + confirmation forte).
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { ModulesService } from "./modules.service.js";
import { ModulesViewModel } from "./ModulesViewModel.js";
import { ModulesCard } from "./Modules.view.js";

export function mountModules(el, ctx = {}) {
  const svc = ctx.service || new ModulesService();
  const notify = ctx.notify || (() => {});
  const state = { open: "", refus: {}, confirming: "", confirmText: "" };
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)],
                                     ["input", "[data-input]", (ev, n) => onInput(ev, n)]] });
  const vm = () => new ModulesViewModel({ data: svc.data, error: svc.error, open: state.open,
                                          refus: state.refus, confirming: state.confirming,
                                          confirmText: state.confirmText });
  const render = () => h.update(ModulesCard(vm()));

  async function open() {
    h.update(html`<h2>🧩 Modules</h2><div class="empty">lecture du registre…</div>`);
    await svc.load();
    render();
    return svc.data;
  }
  async function geste(body, ok) {
    try {
      const r = await svc.setState(body);
      delete state.refus[body.name]; state.confirming = ""; state.confirmText = "";
      notify(ok(r));
      await svc.load(); render();
    } catch (e) {
      // Le serveur REFUSE en disant qui dépend : ce motif est la réponse, pas un incident.
      state.refus[body.name] = e.message; render();
    }
  }
  function onInput(ev, n) {
    if (n.dataset.input !== "confirm") return;
    state.confirmText = n.value || "";
    // Re-rendre seulement pour (dés)activer le bouton — le champ garde son focus et sa valeur.
    const b = el.querySelector && el.querySelector(`[data-action="force-confirm"][data-name="${n.dataset.name}"]`);
    if (b) b.disabled = state.confirmText !== n.dataset.name;
  }
  async function onAction(ev, n) {
    const a = n.dataset.action, name = n.dataset.name || "";
    if (a !== "policy" && ev && ev.preventDefault) ev.preventDefault();
    if (a === "open") {
      // Un second clic referme : le détail est long, et on compare deux modules en les ouvrant tour à tour.
      state.open = state.open === name ? "" : name; render(); return;
    }
    if (a === "enable") return geste({ name, enabled: true }, () => name + " rallumé");
    if (a === "disable") return geste({ name, enabled: false }, () => name + " éteint — ce qu'il a produit reste en place");
    if (a === "force") { state.confirming = name; state.confirmText = ""; render(); return; }
    if (a === "force-cancel") { state.confirming = ""; state.confirmText = ""; render(); return; }
    if (a === "force-confirm") {
      if (state.confirmText !== name) return;       // la garde tient aussi côté client
      return geste({ name, enabled: false, force: true, confirm: state.confirmText },
                   (r) => name + " éteint EN FORÇANT" + (r.casses && r.casses.length ? " — ne fonctionne(nt) plus : " + r.casses.join(", ") : ""));
    }
    if (a === "policy") {
      try { await svc.setPolicy(!!n.checked); await svc.load(); render();
            notify(n.checked ? "forçage des modules permis (confirmation forte à chaque fois)" : "forçage des modules interdit"); }
      catch (e) { notify(e.message, true); }
    }
  }
  return Object.assign(h, { open, render, state, svc, vm });
}
