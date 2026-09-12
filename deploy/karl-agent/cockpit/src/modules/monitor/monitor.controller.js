// modules/monitor/monitor.controller — le panneau « Supervision » (RM3112) : les alertes de l'observateur,
// situées chez un client, et l'ouverture d'un ticket au bon endroit. Le cockpit ne parle jamais à l'outil
// de supervision : il demande au serveur, qui sait lequel répond.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { MonitorService } from "./monitor.service.js";
import { MonitorViewModel } from "./MonitorViewModel.js";
import { MonitorCard } from "./Monitor.view.js";

export function mountMonitor(el, ctx = {}) {
  const svc = ctx.service || new MonitorService();
  const notify = ctx.notify || (() => {});
  const ask = ctx.confirm || (() => true);
  const store = ctx.storage || (typeof localStorage !== "undefined" ? localStorage : { getItem() { return null; }, setItem() {} });
  const state = { page: "alerts", seuil: lu(), busy: null, choix: {} };
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)],
                                     ["change", "[data-action=\"assign-client\"]", (ev, n) => onClient(n)]] });

  function lu() { try { return Number(store.getItem("karlMonitorSeuil") || 0) || 0; } catch (e) { return 0; } }
  const vm = () => new MonitorViewModel({ data: svc.data, error: svc.error, page: state.page,
                                          hosts: svc.hosts, seuil: state.seuil, choix: state.choix });
  const render = () => h.update(MonitorCard(vm()));
  const q = (sel) => (h.el && h.el.querySelector ? h.el.querySelector(sel) : null);

  async function open(page) {
    if (page) state.page = page;
    h.update(html`<h2>🩺 Supervision</h2><div class="empty">interrogation de l'observateur…</div>`);
    try {
      if (state.page === "hosts") await svc.loadHosts();
      else await svc.load({ severity: state.seuil });
      render();
    } catch (e) { h.update(html`<h2>🩺 Supervision</h2><div class="empty">indisponible : ${e.message}</div>`); }
  }

  /** Le client choisi dans le sélecteur d'une ligne, au moment du clic — jamais gardé en mémoire. */
  function clientDe(host) {
    const n = q(`[data-action="assign-client"][data-host="${host}"]`);
    return n ? String(n.value || "").trim() : "";
  }
  function projetDe(host) {
    const n = q(`[data-role="project"][data-host="${host}"]`);
    return n ? String(n.value || "").trim() : "";
  }
  /** Choisir un client ne confirme rien : ça change seulement la liste des projets offerts. */
  function onClient(n) {
    state.choix[n.dataset.host] = String(n.value || "").trim();
    render();
  }

  async function onAction(ev, n) {
    const a = n.dataset.action; if (ev && ev.preventDefault) ev.preventDefault();
    try {
      if (a === "page") { state.page = n.dataset.page; await open(); return; }
      if (a === "seuil") {
        state.seuil = Number(n.dataset.seuil || 0);
        try { store.setItem("karlMonitorSeuil", String(state.seuil)); } catch (e) { /* stockage indisponible */ }
        svc.data = null; await open(); return;
      }
      if (a === "assign-save" || a === "assign-clear") {
        const host = n.dataset.host;
        const client = a === "assign-clear" ? "" : clientDe(host);
        if (a === "assign-clear" && !ask("Retirer l'association de " + host + " ?")) return;
        if (a === "assign-save" && !client) { notify("choisis un client pour " + host, true); return; }
        const projets = vm().hostRows.find(r => r.host === host);
        const projet = a === "assign-clear" ? "" : projetDe(host);
        // Un client à plusieurs projets sans projet choisi ne permettrait pas d'ouvrir un ticket :
        // autant le dire ici plutôt que de laisser découvrir le manque devant une alerte.
        if (a === "assign-save" && !projet && projets && projets.projets.length > 1) {
          notify("choisis aussi le projet : " + client + " en a " + projets.projets.length, true); return;
        }
        await svc.assign({ host, client, project: projet || (projets && projets.unique ? projets.projets[0] : "") });
        delete state.choix[host];
        notify(host + (client ? " → " + client + (projet ? "/" + projet : "") : " : association retirée"));
        await open(); return;
      }
      if (a !== "ticket") return;
      const r = vm().rows().find(x => String(x.id) === String(n.dataset.id));
      if (!r) return;
      // La vue ne montre pas ce bouton sans cible, mais la garde vit ICI aussi : un geste peut venir
      // d'ailleurs (rendu périmé, raccourci), et créer un ticket chez le mauvais client ne se rattrape pas.
      if (!r.ticketable) { notify(r.manque || "hôte non associé à un projet", true); return; }
      if (!ask("Ouvrir un ticket chez " + r.cible + " ?\n\n" + r.host + " : " + r.name
               + "\n\nSévérité : " + r.severityLabel + " · active depuis " + r.since)) return;
      state.busy = r.id; render();
      const res = await svc.ticket({ client: r.client, project: r.project, host: r.host, name: r.name,
                                     severity_label: r.severityLabel, since: r.since, eventid: r.id,
                                     grave: r.grave });
      state.busy = null;
      const rm = res && (res.rm_id || res.id);
      notify(rm ? ("RM" + rm + " créé chez " + r.cible) : "ticket créé");
      if (rm && ctx.showTicket) ctx.showTicket(String(rm));
      render();
    } catch (e) { state.busy = null; notify(e.message, true); render(); }
  }
  return Object.assign(h, { open, render, state, svc, vm });
}
