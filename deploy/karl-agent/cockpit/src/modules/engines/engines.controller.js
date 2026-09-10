// modules/engines/engines.controller — le panneau « Moteurs » des réglages (RM3069) : installer, mettre à jour,
// tester. Rien ne part sans confirmation, et la confirmation MONTRE la commande — c'est le garde-fou 10 rendu visible.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { EnginesService } from "./engines.service.js";
import { EnginesViewModel } from "./EnginesViewModel.js";
import { EnginesCard } from "./Engines.view.js";

export function mountEngines(el, ctx = {}) {
  const svc = ctx.service || new EnginesService();
  const notify = ctx.notify || (() => {});
  const ask = ctx.confirm || (() => true);
  const state = { busy: null, journal: "" };
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)]] });
  const render = () => h.update(EnginesCard(new EnginesViewModel({ data: svc.data, busy: state.busy }), state.journal));

  async function load() {
    h.update(html`<h2>🧩 Moteurs</h2><div class="empty">chargement…</div>`);
    try { await svc.load(); render(); }
    catch (e) { h.update(html`<h2>🧩 Moteurs</h2><div class="empty">indisponible : ${e.message}</div>`); }
  }
  async function onAction(ev, n) {
    const a = n.dataset.action, id = n.dataset.id; if (ev && ev.preventDefault) ev.preventDefault();
    try {
      if (a === "test") {
        const r = await svc.run({ recipe: id, action: "test" });
        state.journal = r.cmd + "\n" + (r.out || r.err || "").slice(-800);
        notify(id + (r.ok ? " répond" : " ne répond pas"), !r.ok); render(); return;
      }
      if (a !== "run") return;
      const act = n.dataset.act || "install";
      // la commande vient du serveur, jamais d'ici : on la RÉCUPÈRE pour la montrer, puis on n'envoie que l'identifiant
      const apercu = await svc.run({ recipe: id, action: act, dry_run: true });
      if (!ask((act === "update" ? "Mettre à jour " : "Installer ") + id + " ?\n\n" + apercu.cmd
               + "\n\nCette commande touche le système.")) return;
      state.busy = id; render();
      let r = await svc.run({ recipe: id, action: act });
      if (!r.ok && r.blocked && r.blocked.length
          && ask(r.error + "\n\nForcer quand même ? Les sessions en cours peuvent être coupées.")) {
        r = await svc.run({ recipe: id, action: act, force: true });
      }
      state.busy = null;
      state.journal = r.cmd + "\n" + (r.out || r.err || r.error || "").slice(-1200);
      notify(id + (r.ok ? " : " + act + " réussie" : " : " + act + " échouée"), !r.ok);
      render();
    } catch (e) { state.busy = null; notify(e.message, true); render(); }
  }
  return Object.assign(h, { load, render, state, svc });
}
