// controllers/dashboard.controller — le tableau de bord du centre. RM2889, L4.
//
// Le monolithe prête : la visibilité du vide central (placeholder + session
// attachée), le cache des sessions, les questions sans réponse, l'attache
// d'une session, l'ouverture d'une fiche, la pile /refresh, la notification.
import { mount } from "../core/dom.js";
import { DashboardService } from "../services/dashboard.service.js";
import { DashboardViewModel } from "../viewmodels/dashboard/DashboardViewModel.js";
import { Dashboard } from "../views/dashboard/Dashboard.view.js";

export function mountDashboard(el, ctx = {}) {
  const svc = ctx.service || new DashboardService();
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const filter = { client: "", project: "" };
  const visible = () => (ctx.visible ? !!ctx.visible() : true);

  function render() {
    if (!visible()) { if (ctx.shown) ctx.shown(false, false); return; }
    const vm = new DashboardViewModel({ overview: svc.overview, alerts: svc.alerts },
      { sessions: ctx.sessions ? ctx.sessions() : {}, stale: ctx.stale ? ctx.stale() : [], filter, nameOf: ctx.nameOf });
    handle.update(Dashboard(vm));
    if (ctx.shown) ctx.shown(true, vm.hasContent);
  }
  /** force : recalcul serveur ; sinon la pile /refresh (RM2763) rappellera setBlock. */
  async function refresh(force) {
    if (!visible()) return;
    if (!force) return ctx.pull && ctx.pull();
    await svc.reload(); render();
  }
  function setBlock(data) { svc.setBlock(data); render(); }

  const gestures = {
    refresh: () => refresh(true),
    attach: (sid) => ctx.attach && ctx.attach(sid),
    review: (rm) => ctx.openReview && ctx.openReview(rm),
    open: (url) => ctx.open ? ctx.open(url) : window.open(url, "_blank"),
    snooze: async (key) => { const r = await svc.snooze(key); notify(r.message, !r.ok); if (r.ok) await refresh(true); },
  };
  const handle = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => { const g = gestures[n.dataset.action]; if (g) { if (ev.stopPropagation) ev.stopPropagation(); return g(n.dataset.arg); } }],
    ["change", "[data-filter]", (ev, sel) => { filter[sel.dataset.filter] = sel.value; if (sel.dataset.filter === "client") filter.project = ""; render(); }],
  ] });
  return Object.assign(handle, { refresh, render, setBlock, visible, filter });
}
