// modules/clientnotify/clientnotify.controller — LE panneau « compte-rendu client » (RM3052) : un menu déroulant
// au bandeau (un client par ligne, avec son reste à annoncer), et au centre la page du client — ses tickets livrés
// groupés par projet, cochables EN TRAVERS des projets, l'email qui en sort en aperçu, puis Envoyer ou Écarter.
//
// Deux principes tiennent le panneau :
//   • ce qui est coché est ce qui part — l'aperçu affiché est produit par le MÊME code que l'envoi (côté serveur) ;
//   • les deux gestes irréversibles (un email au client, une sortie de file) se font en DEUX clics.
import { html } from "../../core/html.js";
import { mount } from "../../core/dom.js";
import { ClientNotifyService } from "./clientnotify.service.js";
import { ClientMenuViewModel, ClientReportViewModel } from "./ClientNotifyViewModel.js";
import { ClientMenu, ClientReport } from "./ClientNotify.view.js";

export function mountClientNotify(el, ctx = {}) {
  const svc = ctx.service || new ClientNotifyService({ storage: ctx.storage });
  const notify = ctx.notify || (() => {});
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const state = { busy: false, confirm: null, prevTimer: null };
  let menuBox = null;

  const h = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => { if (n.tagName === "INPUT" || n.tagName === "SELECT") return; if (ev && ev.preventDefault) ev.preventDefault(); onAction(n.dataset.action, n); }],
    ["change", "input[data-action], select[data-action]", (ev, n) => onAction(n.dataset.action, n)],
    ["input", "input[data-action=\"testto\"]", (ev, n) => { svc.setTestTo(n.value); }],
  ] });

  function vm() { return new ClientReportViewModel({ client: svc.current(), sel: svc.sel, protocole: svc.protocole, preview: svc.preview, busy: state.busy, confirm: state.confirm, contacts: svc.contacts, testTo: svc.testTo }); }
  function render() { h.update(ClientReport(vm())); }

  /** Relit la file et met à jour le compteur du bandeau — appelée au boot, après chaque geste, et sur demande. */
  async function refresh() {
    await svc.load();
    if (ctx.badge) ctx.badge(new ClientMenuViewModel({ clients: svc.clients, total: svc.total }).badge);
    if (svc.error) notify("compte-rendu client : " + svc.error);
    return svc.total;
  }

  /** Le menu déroulant, ancré sous le bouton du bandeau. */
  async function openMenu(anchor) {
    closeMenu();
    await refresh();
    if (!ctx.popover) { if (svc.clients.length) open(svc.clients[0].client); return; }
    const box = ctx.popover();
    if (!box) return;
    menuBox = mount(box, ClientMenu(new ClientMenuViewModel({ clients: svc.clients, total: svc.total })), {
      events: [["click", "[data-action=\"client\"]", (ev, n) => { if (ev && ev.stopPropagation) ev.stopPropagation(); const cl = n.dataset.client; closeMenu(); open(cl); }]],
    });
    if (ctx.place && anchor) ctx.place(box, anchor);
    if (ctx.onOutsideClick) ctx.onOutsideClick(closeMenu);   // un clic ailleurs referme, comme les autres menus
  }
  function closeMenu() { if (menuBox) { const b = menuBox.el; menuBox.unmount(); if (b && b.remove) b.remove(); menuBox = null; } }

  /** Ouvre la page d'un client (tout coché par défaut) et lance l'aperçu. */
  async function open(client) {
    if (!svc.data) await refresh();
    if (client) svc.open(client);
    state.confirm = null;
    if (ctx.openPanel) ctx.openPanel();
    render();
    schedulePreview(0);
    return svc.current();
  }

  /** L'aperçu suit les cases, mais sans mitrailler le serveur : une seule demande après la dernière coche. */
  function schedulePreview(ms) {
    if (state.prevTimer && ctx.clear) ctx.clear(state.prevTimer);
    state.prevTimer = later(async () => {
      state.prevTimer = null;
      await svc.refreshPreview();
      render();
    }, ms === undefined ? 250 : ms);
  }

  async function act(kind) {
    // Deux temps : le premier clic ARME (le libellé dit ce qui va se passer), le second exécute.
    if (state.confirm !== kind) { state.confirm = kind; render(); later(() => { if (state.confirm === kind) { state.confirm = null; render(); } }, 8000); return; }
    state.confirm = null; state.busy = true; render();
    try {
      const r = kind === "send" ? await svc.send() : await svc.dismiss();
      notify(kind === "send" ? `✉ ${r.sent || 0} ticket(s) annoncés à ${(r.to || []).join(", ")}` : `${r.dismissed || 0} ticket(s) écartés — aucun email`);
    } catch (e) {
      notify((kind === "send" ? "envoi refusé : " : "mise à l'écart refusée : ") + e.message);
    }
    state.busy = false;
    if (ctx.badge) ctx.badge(new ClientMenuViewModel({ clients: svc.clients, total: svc.total }).badge);
    svc.open(svc.client);            // la file a changé : on repart de ce qui reste
    render();
    schedulePreview(0);
  }

  /** Un test part en UN clic : il ne va qu'à l'adresse saisie et ne touche pas à la file —
   * rien à confirmer. Ce qui doit être visible, c'est OÙ il est parti. */
  async function sendTest() {
    const v = vm();
    if (!v.canTest) return;
    if (!v.testValid) { notify(svc.testTo ? "adresse de test invalide : " + svc.testTo : "aucune adresse de test"); return; }
    state.busy = true; render();
    try {
      const r = await svc.sendTest();
      notify(`✉ test envoyé à ${(r.to || []).join(", ")} — la file n'a pas bougé`);
    } catch (e) {
      notify("test refusé : " + e.message);
    }
    state.busy = false; render();
  }

  function onAction(a, node) {
    if (a === "pick") { svc.toggle(node.dataset.rm); state.confirm = null; render(); schedulePreview(); }
    else if (a === "all") { svc.all(node.dataset.on === "1"); state.confirm = null; render(); schedulePreview(); }
    else if (a === "proto") { svc.setProto(node.checked !== false); render(); schedulePreview(); }
    else if (a === "reload") { state.confirm = null; refresh().then(() => { svc.open(svc.client); render(); schedulePreview(0); }); }
    else if (a === "testto") { svc.setTestTo(node.value); render(); }
    else if (a === "testpick") { if (node.value) { svc.setTestTo(node.value); render(); } }
    else if (a === "test") sendTest();
    else if (a === "send" || a === "dismiss") act(a);
  }

  return { open, openMenu, closeMenu, refresh, render, state, svc,
    client: () => svc.client, count: () => svc.selected().length,
    unmount() { closeMenu(); h.unmount(); } };
}
