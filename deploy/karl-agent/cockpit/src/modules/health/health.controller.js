// controllers/health — santé du système PM : un badge, une page (RM3369).
//
// Pas d'hôte propre : le domaine vit dans la modale partagée (docmodal) et le
// badge d'en-tête. Le contexte prête la modale, le presse-papier et la pile
// /refresh. Rien n'est calculé ici ni côté serveur au moment du clic : le
// rapport est produit en tâche de fond, on le LIT.
import { mount } from "../../core/dom.js";
import { HealthService } from "./health.service.js";
import { HealthBadgeViewModel, HealthStatusViewModel } from "./HealthViewModels.js";
import { HealthBadge, HealthStatus, HealthPage, HealthError } from "./Health.view.js";

export function mountHealth(el, ctx = {}) {
  const svc = ctx.service || new HealthService();
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const state = { tab: null, open: false };

  const paintBadge = () => ctx.badge && ctx.badge(svc.check ? HealthBadge(new HealthBadgeViewModel(svc.check)) : "");
  const statusBody = () => HealthStatus(new HealthStatusViewModel(svc.status, { active: state.tab }));

  function setBlock(data) { svc.setBlock(data); paintBadge(); }
  async function refreshCheck(force) {
    if (!force && ctx.pull) return ctx.pull("pmhealth");
    await svc.reloadCheck();
    paintBadge();
  }
  function boot() { refreshCheck(false); }

  async function openStatus(force) {
    state.open = true;
    if (ctx.modal) ctx.modal("🩺 Santé du système PM", "");
    handle.update(HealthPage());
    try {
      await svc.loadStatus(force);
      if (state.open) handle.update(HealthPage(statusBody()));
      refreshCheck(!!force);      // le badge suit ce que la page vient de lire
    } catch (e) { if (state.open) handle.update(HealthPage(HealthError(e.message))); }
  }

  const gestures = {
    refresh: () => openStatus(true),
    tab: (n) => { state.tab = n.dataset.tab; if (svc.status) handle.update(HealthPage(statusBody())); },
    copy: async (n) => { const code = n.previousElementSibling; const ok = ctx.clip ? await ctx.clip(code ? code.textContent : "") : false; notify(ok ? "Commande copiée" : "Copie refusée", !ok); },
  };
  const handle = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => { const g = gestures[n.dataset.action]; if (g) return g(n); }],
  ] });
  return Object.assign(handle, { boot, refreshCheck, openStatus, setBlock, state });
}
