// controllers/env.controller — santé du poste et verrous : trois gestes. RM2889, L5.
//
// Pas d'hôte propre : le domaine vit dans la modale partagée (docmodal), le badge
// et le bouton d'en-tête. Le contexte prête la modale, le presse-papier, la pile
// /refresh, le contexte sécurisé et la notification. Un secret est lu au moment
// du geste et le champ vidé aussitôt — jamais conservé.
import { mount } from "../../core/dom.js";
import { EnvService } from "./env.service.js";
import { EnvBadgeViewModel, EnvStatusViewModel, VaultViewModel } from "./EnvViewModels.js";
import { EnvBadge, EnvStatus, EnvStatusPage, EnvStatusError, VaultForm } from "./Env.view.js";

export function mountEnv(el, ctx = {}) {
  const svc = ctx.service || new EnvService();
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const state = { tab: null, mode: null };   // mode : "status" | "vault" | null

  const paintBadge = () => ctx.badge && ctx.badge(svc.check ? String(EnvBadge(new EnvBadgeViewModel(svc.check))) : "");
  const paintLock  = () => ctx.lock && ctx.lock(new VaultViewModel(svc.vault || null).button);
  const statusBody = () => EnvStatus(new EnvStatusViewModel(svc.status, { active: state.tab }));
  const paintVault = () => handle.update(VaultForm(new VaultViewModel(svc.vault, { secure: ctx.secure ? ctx.secure() : false })));

  function setBlock(kind, data) { svc.setBlock(kind, data); if (kind === "envcheck") paintBadge(); else paintLock(); }
  async function refreshCheck(force) { if (!force) return ctx.pull && ctx.pull("envcheck"); await svc.reloadCheck(); paintBadge(); }
  async function pullVault() { if (ctx.pull) await ctx.pull("vault"); }
  function boot() { refreshCheck(false); pullVault(); }

  async function openStatus(force) {
    state.mode = "status";
    if (ctx.modal) ctx.modal("🩺 Santé du poste", "");
    handle.update(EnvStatusPage());
    try {
      await svc.loadStatus(force);
      if (state.mode === "status") handle.update(EnvStatusPage(statusBody()));
      refreshCheck(!!force);      // le badge suit le diagnostic qu'on vient de rejouer (RM2722)
    } catch (e) { if (state.mode === "status") handle.update(EnvStatusPage(EnvStatusError(e.message))); }
  }
  async function openVault() {
    state.mode = "vault";
    if (ctx.modal) ctx.modal("🔓 Verrous du poste", "vlt");
    handle.update(`<div style="color:var(--muted)">lecture de l'état…</div>`);
    await pullVault();
    if (state.mode === "vault") paintVault();
  }
  const field = (id) => handle.el.querySelector && handle.el.querySelector("#" + id);
  async function secretGesture(btn, passId, selId, send, idle) {
    const f = field(passId), sel = field(selId);
    if (!f || !f.value) { notify(passId === "vlt-pass" ? "Mot de passe requis" : "Passphrase requise", true); return; }
    const secret = f.value; f.value = "";
    if (btn) { btn.disabled = true; btn.textContent = "…"; }
    try { const r = await send(sel ? sel.value : "", secret); notify(r.message, !r.ok); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = idle; }
      await pullVault(); if (state.mode === "vault") paintVault();
      refreshCheck(true);       // le badge « poste » doit suivre la réparation
    }
  }
  const gestures = {
    refresh: () => openStatus(true),
    tab: (n) => { state.tab = n.dataset.tab; if (svc.status) handle.update(EnvStatusPage(statusBody())); },
    copy: async (n) => { const code = n.previousElementSibling; const ok = ctx.clip ? await ctx.clip(code ? code.textContent : "") : false; notify(ok ? "Commande copiée" : "Copie refusée", !ok); },
    unlock: (n) => secretGesture(n, "vlt-pass", "vlt-inst", (i, p) => svc.unlock(i, p), "Déverrouiller"),
    sshadd: (n) => secretGesture(n, "vlt-kpass", "vlt-key", (k, p) => svc.sshAdd(k, p), "Charger"),
  };
  const handle = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => { const g = gestures[n.dataset.action]; if (g) return g(n); }],
    ["keydown", "input[data-enter]", (ev, n) => { if (ev.key === "Enter") { const g = gestures[n.dataset.enter]; if (g) return g(n.nextElementSibling); } }],
  ] });
  return Object.assign(handle, { boot, refreshCheck, openStatus, openVault, setBlock, state });
}
