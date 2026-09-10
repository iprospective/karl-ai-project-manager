// modules/providers/providers.controller — le panneau « Fournisseurs » des réglages (RM3068) : déclarer une
// instance, poser sa clé, voir où elle sert. La valeur d'un secret part vers le serveur et n'en revient jamais ;
// le champ de saisie est vidé aussitôt, et rien ne la garde en mémoire.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { ProvidersService } from "./providers.service.js";
import { ProvidersViewModel } from "./ProvidersViewModel.js";
import { ProvidersCard } from "./Providers.view.js";

export function mountProviders(el, ctx = {}) {
  const svc = ctx.service || new ProvidersService();
  const notify = ctx.notify || (() => {});
  const ask = ctx.confirm || (() => true);
  const state = { open: null, loaded: false };
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)],
                                     ["change", "[data-role=\"type\"]", () => render()]] });
  const vm = () => new ProvidersViewModel({ cat: svc.cat, data: svc.data, open: state.open });
  const render = () => h.update(ProvidersCard(vm()));
  const q = (sel) => (el && el.querySelector ? el.querySelector(sel) : null);

  async function load(force) {
    h.update(html`<h2>🔌 Fournisseurs</h2><div class="empty">chargement…</div>`);
    try { await svc.load(force); state.loaded = true; render(); }
    catch (e) { h.update(html`<h2>🔌 Fournisseurs</h2><div class="empty">indisponible : ${e.message}</div>`); }
  }
  /** Le formulaire courant, lu au moment du clic (jamais gardé en mémoire). */
  function formValues() {
    const f = q('[data-role="form"]'); if (!f) return null;
    const val = (sel) => { const n = f.querySelector(sel); return n ? String(n.value || "").trim() : ""; };
    const fields = {};
    (f.querySelectorAll ? f.querySelectorAll('[data-role="field"]') : []).forEach(n => { fields[n.dataset.name] = String(n.value || "").trim(); });
    return { name: val('[data-role="name"]'), type: val('[data-role="type"]'), fields, axis: f.dataset.axis };
  }
  async function onAction(ev, n) {
    const a = n.dataset.action; if (ev && ev.preventDefault) ev.preventDefault();
    try {
      if (a === "toggle") { state.open = state.open === n.dataset.name ? null : n.dataset.name; render(); }
      else if (a === "new") { state.open = "+" + n.dataset.axis; render(); }
      else if (a === "cancel") { state.open = null; render(); }
      else if (a === "edit") { state.open = n.dataset.name; render(); }
      else if (a === "default") { await svc.save({ default_for: n.dataset.axis, name: n.dataset.name }); notify(n.dataset.name + " : défaut de l'axe"); render(); }
      else if (a === "delete") {
        if (!ask("Supprimer la déclaration de " + n.dataset.name + " ? (la clé posée dans le .env, elle, reste)")) return;
        await svc.save({ name: n.dataset.name, delete: true }); state.open = null; notify(n.dataset.name + " retirée"); render();
      } else if (a === "save") {
        const v = formValues(); if (!v || !v.name) { notify("nom requis", true); return; }
        await svc.save({ name: v.name, type: v.type, fields: v.fields }); state.open = null; notify(v.name + " enregistrée"); render();
      } else if (a === "secret-save" || a === "secret-unset") {
        const champ = q(`[data-role="secret"][data-name="${n.dataset.name}"][data-key="${n.dataset.key}"]`);
        const boite = q(`[data-role="scope"][data-name="${n.dataset.name}"][data-key="${n.dataset.key}"]`);
        const corps = { name: n.dataset.name, type: n.dataset.type, key: n.dataset.key, scope: (boite && boite.checked) ? "global" : "user" };
        if (a === "secret-unset") {
          if (!ask("Effacer la clé " + n.dataset.key + " de " + n.dataset.name + " ?")) return;
          corps.unset = true;
        } else {
          const valeur = champ ? String(champ.value || "") : "";
          if (!valeur.trim()) { notify("saisis la valeur à enregistrer", true); return; }
          corps.value = valeur;
          if (champ) champ.value = "";                    // vidé aussitôt : rien ne reste à l'écran ni en mémoire
        }
        await svc.secret(corps);
        notify(n.dataset.key + (corps.unset ? " effacée" : " enregistrée") + (corps.scope === "global" ? " (global)" : ""));
        render();
      }
    } catch (e) { notify(e.message, true); }
  }
  return Object.assign(h, { load, render, state, svc, vm });
}
