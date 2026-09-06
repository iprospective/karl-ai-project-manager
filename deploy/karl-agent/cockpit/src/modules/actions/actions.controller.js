// controllers/actions.controller — les actions d'une session : chips en un clic (RM1893 §2), actions PM d'un ticket (RM2720),
// moniteurs et disposition des panes (§3), menu de disposition (RM2515), fermeture. RM2889.
//
// Hôtes : `chips` (#chipsrow), `bar` (#tabactions : monpreset, monbtn, unmonbtn, layoutsel). Le monolithe prête la session
// attachée, le registre des sessions, CFG, les toasts, le détachement, le rafraîchissement des sessions et de la santé.
import { mount } from "../../core/dom.js";
import { html } from "../../core/html.js";
import { ActionsService } from "./actions.service.js";
import { ChipsViewModel, DispositionMenuViewModel } from "./ActionsViewModel.js";
import { Chips, DispositionMenu, PresetOptions } from "./Actions.view.js";
import { pmActionTarget, pmActions, tmuxLabel } from "./actions.js";

export function mountSessionActions({ chips, bar } = {}, ctx = {}) {
  const svc = ctx.service || new ActionsService();
  const notify = ctx.notify || (() => {});
  const ask = ctx.confirm || ((m) => window.confirm(m));
  const attached = () => { const a = ctx.attached ? ctx.attached() : null; return a == null ? null : String(a); };
  const cfg = () => (ctx.cfg ? ctx.cfg() : null) || {};
  const sess = () => (ctx.sess ? ctx.sess() : null) || {};
  const q = (sel) => (bar && bar.querySelector ? bar.querySelector(sel) : null);
  let menu = null;

  function renderChips() {
    if (!chipsH) return;
    const vm = new ChipsViewModel({ actions: cfg().actions, attached: attached() });
    chipsH.update(vm.shown ? Chips(vm) : "");
    if (chips) chips.style.display = vm.shown ? "flex" : "none";
  }
  /** RM2720 : `id` = le ticket que remplace {id} ; `sid` = la session destinataire. */
  async function sendAction(a, btn, id, sid) {
    const target = sid || attached(); if (!target || !a) return;
    const rid = id == null ? target : String(id);
    if (btn) btn.disabled = true;
    try { notify(await svc.send(a, target, rid)); } catch (e) { notify(e.message, true); } finally { if (btn) btn.disabled = false; }
  }
  const pmTarget = (rm) => pmActionTarget(rm, sess(), attached());
  /** RM2720 : action PM d'un ticket — confirmation seulement si la cible n'est PAS la session du ticket. */
  async function sendPmAction(idx, rm, btn) {
    const a = pmActions(cfg().actions)[idx]; if (!a) return;
    const tgt = pmTarget(rm);
    if (!tgt.sid) { notify(tgt.why, true); return; }
    if (!tgt.own && !ask("« " + a.label + " » de RM" + rm + "\n" + tgt.why + "\n\nEnvoyer quand même ?")) return;
    await sendAction(a, btn, rm, tgt.sid);
  }
  // ── §3 : moniteurs et disposition des panes (redessin live côté ttyd, pas de reattach) ──
  function fillPresets(c) { const conf = c || cfg(); const mp = q("#monpreset"); if (mp) mp.insertAdjacentHTML("beforeend", String(PresetOptions(conf.monitors || [], "📺 "))); const ls = q("#layoutsel"); if (ls) ls.insertAdjacentHTML("beforeend", String(PresetOptions(conf.layouts || []))); }
  async function addMonitor() { const a = attached(), mp = q("#monpreset"); const preset = mp ? String(mp.value || "") : ""; if (!a || !preset) return; try { await svc.monitor(a, preset); notify("Moniteur « " + preset + " » ajouté"); } catch (e) { notify(e.message, true); } }
  async function removeMonitor() { const a = attached(); if (!a) return; try { await svc.unmonitor(a); notify("Moniteur fermé"); } catch (e) { notify(e.message, true); } }
  async function setLayout() { const a = attached(), ls = q("#layoutsel"); const layout = ls ? String(ls.value || "") : ""; if (!a || !layout) return; try { await svc.layout(a, layout); } catch (e) { notify(e.message, true); } if (ls) ls.value = ""; }
  // ── RM2515 : menu de disposition d'une session (popover ancré sur la pastille) + fermer ──
  function closeDispMenu() { if (menu) { if (menu.remove) menu.remove(); menu = null; } }
  function openDispositionMenu(s, anchor) {
    closeDispMenu(); if (!ctx.popover) return;
    const vm = new DispositionMenuViewModel({ session: s });
    menu = ctx.popover(); menu.innerHTML = String(DispositionMenu(vm));
    if (ctx.place && anchor) ctx.place(menu, anchor);
    const onClick = (e) => { const b = e.target && e.target.closest ? e.target.closest("button") : null; if (!b) return; e.stopPropagation(); if (b.dataset.kill) { closeDispMenu(); kill(vm.sid); return; } setDisposition(vm.sid, b.dataset.v); closeDispMenu(); };
    if (menu.addEventListener) menu.addEventListener("click", onClick);
    if (ctx.onOutsideClick) ctx.onOutsideClick(closeDispMenu);
  }
  async function setDisposition(rmId, disposition) { try { await svc.disposition(rmId, disposition); } catch (e) { notify(e.message, true); } if (ctx.refreshSessions) ctx.refreshSessions(); }
  async function kill(rmId) {
    if (!ask("Fermer la session " + tmuxLabel(rmId) + " ? (le travail non sauvé est perdu)")) return;
    try {
      await svc.kill(rmId); notify("Session karl-RM" + rmId + " fermée");
      if (attached() === String(rmId) && ctx.detach) ctx.detach();
      if (ctx.refreshSessions) ctx.refreshSessions(); if (ctx.refreshHealth) ctx.refreshHealth();
    } catch (e) { notify(e.message, true); }
  }
  const chipsH = chips ? mount(chips, "", { events: [["click", "[data-action=\"chip\"]", (e, n) => { const a = (cfg().actions || [])[Number(n.dataset.i)]; sendAction(a, n); }]] }) : null;
  const disposers = [];
  const listen = (el, type, fn) => { if (el && el.addEventListener) { el.addEventListener(type, fn); disposers.push(() => el.removeEventListener(type, fn)); } };
  listen(bar, "click", (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (!n) return; if (n.dataset.action === "monitor-add") { e.preventDefault(); addMonitor(); } else if (n.dataset.action === "monitor-remove") { e.preventDefault(); removeMonitor(); } });
  listen(bar, "change", (e) => { if (e.target && e.target.id === "layoutsel") setLayout(); });
  return { renderChips, sendAction, sendPmAction, pmTarget, fillPresets, addMonitor, removeMonitor, setLayout, openDispositionMenu, closeDispMenu, setDisposition, kill,
    unmount() { closeDispMenu(); if (chipsH) chipsH.unmount(); disposers.forEach(d => d()); disposers.length = 0; } };
}
