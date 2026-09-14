// modules/engines/engines.controller — le panneau « Moteurs » des réglages (RM3069) : installer, mettre à jour,
// tester. Rien ne part sans confirmation, et la confirmation MONTRE la commande — c'est le garde-fou 10 rendu visible.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { EnginesService } from "./engines.service.js";
import { EnginesViewModel, EngineLaunchViewModel } from "./EnginesViewModel.js";
import { EnginesCard, EnginesLaunchCard } from "./Engines.view.js";

export function mountEngines(el, ctx = {}) {
  const svc = ctx.service || new EnginesService();
  const notify = ctx.notify || (() => {});
  const ask = ctx.confirm || (() => true);
  // `dirty` retient ce que l'utilisateur vient de cocher tant qu'il n'a pas enregistré : sans lui,
  // le re-rendu qui suit chaque clic remettrait la case dans l'état du serveur, sous les doigts.
  const state = { busy: null, journal: "", dirty: {} };
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)],
                                     ["change", "[data-action=opt]", (ev, n) => onOption(n)],
                                     ["input", "[data-action=extra]", (ev, n) => onExtra(n)]] });
  const render = () => h.update(html`${EnginesCard(new EnginesViewModel({ data: svc.data, busy: state.busy }), state.journal)}
    ${EnginesLaunchCard(new EngineLaunchViewModel({ data: svc.launch, dirty: state.dirty, busy: state.busy }))}`);

  const brouillon = (name) => (state.dirty[name] = state.dirty[name] || { options: {}, extra_args: null });
  function onOption(n) {
    const b = brouillon(n.dataset.engine);
    b.options[n.dataset.key] = !!n.checked;
    render();
  }
  function onExtra(n) {
    // pas de `render()` ici : re-rendre à chaque frappe reprendrait le focus et la position du curseur
    brouillon(n.dataset.engine).extra_args = n.value;
    const bouton = el.querySelector(`[data-action=save][data-engine="${n.dataset.engine}"]`);
    if (bouton) bouton.disabled = false;
  }
  /** Ce qu'on envoie : l'état COMPLET des cases de ce moteur, pas le seul delta — le serveur compare
   *  aux défauts et ne consigne que ce qui en diffère. */
  function aEnvoyer(name) {
    const p = ((svc.launch || {}).engines || []).find(x => x.engine === name) || {};
    const b = state.dirty[name] || {};
    const options = {};
    for (const o of (p.options || [])) options[o.key] = o.key in (b.options || {}) ? !!b.options[o.key] : !!o.enabled;
    return { engine: name, options, extra_args: typeof b.extra_args === "string" ? b.extra_args : (p.extra_args || "") };
  }

  async function load() {
    h.update(html`<h2>🧩 Moteurs</h2><div class="empty">chargement…</div>`);
    try { await svc.load(); render(); }
    catch (e) { h.update(html`<h2>🧩 Moteurs</h2><div class="empty">indisponible : ${e.message}</div>`); }
  }
  async function onAction(ev, n) {
    const a = n.dataset.action, id = n.dataset.id; if (ev && ev.preventDefault) ev.preventDefault();
    try {
      if (a === "save") {
        const name = n.dataset.engine;
        state.busy = name; render();
        try {
          await svc.saveOptions(aEnvoyer(name));
          delete state.dirty[name];
          notify(name + " : options enregistrées");
        } catch (e) {
          notify(e.message, true);        // le serveur REFUSE un réglage invalide : on le dit, on ne l'écrit pas
        }
        state.busy = null; render(); return;
      }
      if (a === "test") {
        const r = await svc.run({ recipe: id, action: "test" });
        state.journal = r.cmd + "\n" + (r.out || r.err || "").slice(-800);
        notify(id + (r.ok ? " répond" : " ne répond pas"), !r.ok); render(); return;
      }
      if (a !== "run") return;
      const act = n.dataset.act || "install", scope = n.dataset.scope || "user";
      // la commande vient du serveur, jamais d'ici : on la RÉCUPÈRE pour la montrer, puis on n'envoie que l'identifiant
      const apercu = await svc.run({ recipe: id, action: act, scope, dry_run: true });
      const ou = scope === "system" ? "pour tous les utilisateurs de la machine" : "pour vous seul";
      if (!ask((act === "update" ? "Mettre à jour " : "Installer ") + id + " " + ou + " ?\n\n" + apercu.cmd
               + (scope === "system" ? "\n\nCette commande touche le système (sudo)." : ""))) return;
      state.busy = id; render();
      let r = await svc.run({ recipe: id, action: act, scope });
      if (!r.ok && r.blocked && r.blocked.length
          && ask(r.error + "\n\nForcer quand même ? Les sessions en cours peuvent être coupées.")) {
        r = await svc.run({ recipe: id, action: act, scope, force: true });
      }
      state.busy = null;
      state.journal = r.cmd + "\n" + (r.out || r.err || r.error || "").slice(-1200);
      notify(id + (r.ok ? " : " + act + " réussie" : " : " + act + " échouée"), !r.ok);
      render();
    } catch (e) { state.busy = null; notify(e.message, true); render(); }
  }
  return Object.assign(h, { load, render, state, svc });
}
