// controllers/newticket.controller — la surface « nouveau ticket » du centre. RM2889.
// Première surface migrée du routeur : elle s'enregistre auprès de lui (open/close)
// et remplace le pont historique. Le changement de client ne re-rend QUE les radios
// (le reste est de la saisie en cours — la re-rendre l'effacerait).
import { mount, paint } from "../../core/dom.js";
import { NewTicketService } from "./newticket.service.js";
import { NewTicketViewModel } from "./NewTicketViewModel.js";
import { NewTicketForm, ProjectRadios } from "./NewTicket.view.js";

export function mountNewTicket(el, ctx = {}) {
  const svc = ctx.service || new NewTicketService();
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const q = (sel) => (handle.el.querySelector ? handle.el.querySelector(sel) : null);
  let vm = null;

  function open() {
    if (ctx.center) ctx.center.yield("newticket");
    if (ctx.show) ctx.show(true);
    const cfg = ctx.config ? ctx.config() : {}, def = ctx.defaultTarget ? ctx.defaultTarget() : {};
    vm = new NewTicketViewModel({ types: cfg.types || [], priorities: cfg.priorities || [], projects: ctx.projects ? ctx.projects() : [] }, { client: def.client, project: def.project });
    handle.update(NewTicketForm(vm));
    if (ctx.center) { ctx.center.note("newticket", "", "nouveau ticket"); ctx.center.title(); }
  }
  function close() { if (ctx.show) ctx.show(false); if (ctx.center) ctx.center.fallback(); }
  const values = () => { const out = {}; for (const n of handle.el.querySelectorAll ? handle.el.querySelectorAll("[data-field]") : []) out[n.dataset.field] = n.value; const pr = q('input[name="ntf-project"]:checked'); out.project = pr ? pr.value : ""; return out; };
  async function submit(btn) {
    btn.disabled = true; btn.textContent = "Création…";
    try {
      const r = await svc.create(values());
      notify(r.message, !r.ok);
      if (r.ok) { if (ctx.center) ctx.center.closeTab("newticket:"); if (ctx.openReview) ctx.openReview(r.rm_id); }   // on enchaîne sur la fiche du ticket créé
    } finally { btn.disabled = false; btn.textContent = "Créer le ticket"; }
  }
  const handle = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => n.dataset.action === "submit" && submit(n)],
    ["change", "[data-field]", (ev, n) => {
      if (n.dataset.field === "client" && vm) { const box = q("#ntf-projects"); if (box) paint(box, ProjectRadios(vm.radios(n.value, ""))); }
      if (n.dataset.field === "type") { const box = q("#ntf-bugbox"); if (box) box.style.display = n.value === "bugfix" ? "" : "none"; }   // RM2752
    }],
  ] });
  return Object.assign(handle, { open, close, values });
}
