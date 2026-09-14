// controllers/pmcmd.controller — commandes PM : trois gestes. RM2889, L5.
import { mount } from "../../core/dom.js";
import { PmCommandsService } from "./pmcmd.service.js";
import { PmMenuViewModel, PmFormViewModel } from "./PmCommandsViewModel.js";
import { PmMenu, PmForm, PmCommandsPanel } from "./PmCommands.view.js";

export function mountPmCommands(el, ctx = {}) {
  const svc = ctx.service || new PmCommandsService(undefined, ctx.run);
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const ask = ctx.confirm || ((m) => window.confirm(m));
  const state = { current: null, result: null, loaded: false };
  const paint = () => handle.update(PmCommandsPanel({
    menu: PmMenu(new PmMenuViewModel({ commands: svc.commands })),
    form: state.current ? PmForm(new PmFormViewModel(state.current)) : "", result: state.result }));
  async function load() { try { await svc.load(); state.loaded = true; } catch (e) { notify(e.message, true); } paint(); }
  const values = () => { const out = {}; for (const n of handle.el.querySelectorAll ? handle.el.querySelectorAll("[data-arg]") : []) out[n.dataset.arg] = n.type === "checkbox" ? n.checked : n.value; return out; };
  const gestures = {
    help: () => ctx.help && ctx.help("commandes"),
    pick: (n) => { state.current = svc.find(n.dataset.name); state.result = null; paint(); },
    run: async (n) => {
      const c = svc.find(n.dataset.name); if (!c) return;
      const v = values();
      if (c.confirm && !ask((c.label || c.name) + " — exécuter cette mutation ?")) return;
      n.disabled = true;
      try { const r = await svc.run(c.name, v); notify(r.message, !r.ok); if (r.output !== undefined) { state.result = r.output; paint(); } }
      finally { n.disabled = false; }
    },
  };
  const handle = mount(el, "", { events: [["click", "[data-action]", (ev, n) => { const g = gestures[n.dataset.action]; if (g) return g(n); }]] });
  paint();
  /** RM3147 — exécuter une commande du catalogue depuis un AUTRE module (le
   *  panneau emails, pour créer une fiche d'annuaire). On prête le service déjà
   *  chargé plutôt que d'en instancier un second : deux catalogues en mémoire,
   *  c'est deux vérités sur ce que le serveur accepte. Charge à la demande. */
  const runFor = async (name, values) => {
    if (!svc.commands.length) await load();
    return svc.run(name, values);
  };
  return Object.assign(handle, { load, run: runFor, state });
}
