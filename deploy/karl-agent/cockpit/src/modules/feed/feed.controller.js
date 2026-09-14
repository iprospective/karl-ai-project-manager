// modules/feed/notify.controller — le panneau « Fil » (RM2792) : ce qui attend, toutes sources
// confondues, et les deux gestes qui le vident — lu, puis traité. Le fil vit côté serveur : ce module
// ne décide de rien, il montre et il marque.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { FeedService } from "./feed.service.js";
import { FeedViewModel } from "./FeedViewModel.js";
import { FeedCard } from "./Feed.view.js";

export function mountFeed(el, ctx = {}) {
  const svc = ctx.service || new FeedService();
  const notify = ctx.notify || (() => {});
  const ask = ctx.confirm || (() => true);
  const state = { etat: "ouvert", user: "" };
  const h = mount(el, "", { events: [["click", "[data-action]", (ev, n) => onAction(ev, n)]] });
  const vm = () => new FeedViewModel({ data: svc.data, error: svc.error, etat: state.etat, user: state.user });
  const render = () => h.update(FeedCard(vm()));

  async function open(etat) {
    if (etat) state.etat = etat;
    h.update(html`<h2>🔔 Fil</h2><div class="empty">lecture du fil…</div>`);
    await svc.load({ etat: state.etat, user: state.user });
    render();
    return svc.data;
  }

  /** Ce que le bouton d'en-tête doit montrer : rien tant que rien n'attend. */
  async function poll() {
    const d = await svc.load({ etat: "ouvert", user: state.user });
    const c = (d && d.counts) || { open: 0, worst: null };
    if (ctx.onCounts) ctx.onCounts(c);
    return c;
  }

  async function onAction(ev, n) {
    if (ev && ev.preventDefault) ev.preventDefault();
    const a = n.dataset.action;
    try {
      if (a === "vue") { state.etat = n.dataset.vue || "ouvert"; await open(); return; }
      if (a === "user") { state.user = n.dataset.user || ""; await open(); return; }
      if (a === "ticket") { if (ctx.showTicket) ctx.showTicket(String(n.dataset.rm || "")); return; }
      if (a === "lu" || a === "done") {
        await svc.mark({ ids: [n.dataset.id], etat: a === "lu" ? "lu" : "traite" });
        await open(); if (ctx.onCounts) await poll(); return;
      }
      if (a === "done-all") {
        const c = vm().counts;
        // « tout » est un geste qu'on ne défait pas : il doit dire COMBIEN il emporte.
        if (!ask("Marquer traité " + c.open + " notification(s) ?\n\nElles sortent de la vue ; le fil les garde.")) return;
        const r = await svc.mark({ all: true, etat: "traite" });
        notify((r && r.marked ? r.marked : 0) + " notification(s) traitée(s)");
        await open(); if (ctx.onCounts) await poll(); return;
      }
    } catch (e) { notify(e.message, true); }
  }
  return Object.assign(h, { open, render, poll, state, svc, vm });
}
