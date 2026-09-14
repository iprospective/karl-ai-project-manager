// controllers/meta.controller — l'encart ℹ : la colonne de droite « infos » (session) et « tickets »
// (sous-onglet par ticket, puis facette). RM2889 (revue 3/3).
//
// Le ticket affiché et sa facette vivent ICI (ex-`metaTicket` / `metaFacet` du monolithe). Le
// contexte prête ce que le monolithe possède encore : la session attachée, le registre des sessions,
// les stores ticket (RM3005, via la façade), le worklog de session, la colonne de
// droite, les gestes voisins (lanceur, revue, menu de statut, fiche projet, infobulles RM2619).
import { mount } from "../../core/dom.js";
import { MetaService } from "./meta.service.js";
import { SessionInfosViewModel, TicketMetaViewModel } from "./MetaViewModel.js";
import { SessionInfos, TicketsPane } from "./Meta.view.js";
import { ticketsOfSession } from "./ticketMeta.js";

export function mountMeta({ infos, tickets } = {}, ctx = {}) {
  const T = ctx.ticket;                                     // façade du modèle ticket (boot.js)
  const svc = ctx.service || new MetaService({ clipboard: ctx.clipboard });
  const notify = ctx.notify || (() => {});
  const state = { ticket: null, facet: "detail" };
  const resolve = () => ctx.resolve();   // store ticket.resolve (RM3005) : get/view/subscribe
  const sess = () => ctx.sess();         // store session.registry
  const attached = () => { const a = ctx.attached ? ctx.attached() : null; return a == null ? null : String(a); };
  const usageOf = (sid) => (ctx.usage ? ctx.usage().get(sid) : undefined);
  const worklog = () => (ctx.worklog ? ctx.worklog() : null) || null;
  const deps = { md: ctx.md || (s => String(s)), tip: ctx.tipAttr || (() => "") };

  /** Tickets traités par la session attachée : ancrage + registre + worklog (RM2673) — le worklog
   *  n'est lu que s'il est bien celui de la session attachée (l'onglet 🗒 état peut porter une précédente). */
  function sessionTickets() {
    const a = attached(); if (!a) return [];
    const wl = worklog();
    return ticketsOfSession(a, (sess().get(a) || {}).registry, (wl && String(wl.rm_id) === a) ? wl.buckets : null);
  }
  const infosVM = (sid) => new SessionInfosViewModel({ s: sess().get(sid), r: resolve().get(sid), usage: usageOf(sid) }, { sid, ago: ctx.ago });

  // ── rendu ────────────────────────────────────────────────────────────────
  function renderInfos() {
    if (!infosH) return;
    const a = attached();
    if (a && T && !T.usageFresh(a) && !T.usageInFlight(a)) T.ensureUsage(a).then(() => render());
    infosH.update(SessionInfos(infosVM(a)));
  }
  function renderTickets() {
    if (!ticketsH) return;
    const a = attached(), wl = worklog();
    // RM2673 : le worklog est une source de tickets — on ne peut pas attendre que l'onglet 🗒 état soit ouvert
    const wlSeen = !!(wl && String(wl.rm_id || "") === String(a));
    if (a && !wlSeen && (ctx.worklogPending ? ctx.worklogPending() : null) !== a && ctx.loadWorklog) ctx.loadWorklog();
    const base = { tickets: sessionTickets(), current: state.ticket, facet: state.facet, resolve: resolve().view, attached: a, worklogSeen: wlSeen };
    const probe = new TicketMetaViewModel(base), sel = probe.sel;
    // RM2807 : UN .then(render) par ticket en vol — jamais un par rendu (fan-out 2^N, fuite Firefox)
    // RM3140 : et UNE requête pour toute la liste, pas une par ticket. Une vue qui affiche N tickets
    // n'a besoin que du titre, du statut et du projet ; la fiche entière (jusqu'à 6 000 caractères de
    // description) ne sert qu'au ticket qu'on OUVRE — celui-là passe par `ensureResolved` plus bas.
    T.ensureBriefs(probe.list);   // RM3005 : l'abonnement au store re-rend à l'arrivée
    if (sel && probe.facet === "workspace" && svc.workspace(sel) === undefined) refreshWorkspace(sel);
    const r = sel ? resolve().get(sel) : undefined;
    const card = (r && r.found && r.client && r.project) ? svc.projectCard(r.client, r.project, () => render()) : undefined;
    ticketsH.update(TicketsPane(new TicketMetaViewModel(Object.assign(base, { ws: sel ? svc.workspace(sel) : undefined, card })), deps));
  }
  function render() { renderInfos(); renderTickets(); }

  // ── gestes ───────────────────────────────────────────────────────────────
  /** RM2173 : clic sur un RM-id → détail de CE ticket dans l'encart (sans toucher au lanceur ni changer de session). */
  function showTicket(id) {
    id = String(id).replace(/^RM/i, "");
    if (ctx.noteOpened) ctx.noteOpened(id);                 // RM2606 : ce qu'on ouvre reste sous la main
    state.ticket = id; state.facet = "detail";              // RM2579 : on ouvre sur le détail
    if (ctx.showRight) ctx.showRight("tickets");            // RM2579/2466 : le ticket demandé passe au premier plan
    render();
    const still = () => state.ticket === id;
    T.ensureResolved(id).then(() => { if (still()) render(); });
    T.revalidate(id, () => { if (still()) render(); });    // RM2630 : montrer l'état actuel, pas celui du premier affichage
    if (svc.workspace(id) === undefined) refreshWorkspace(id);
  }
  /** Une autre surface (revue, attache) dit quel ticket montrer — sans re-rendre (elle le fait). */
  function setTicket(rm) { state.ticket = rm == null ? null : String(rm); if (rm != null) state.facet = "detail"; }
  const ticketIs = (rm) => state.ticket != null && state.ticket === String(rm);
  function setTab(rm) { rm = String(rm); state.ticket = rm; if (svc.workspace(rm) === undefined) refreshWorkspace(rm); T.ensureResolved(rm); renderTickets(); }   // RM3005 : l'abonnement re-rend à l'arrivée
  function setFacet(f) { state.facet = f; renderTickets(); }
  async function refreshWorkspace(rm) { await svc.refreshWorkspace(rm); if (ticketIs(rm)) render(); }
  function refreshUsage(sid) { T.ensureUsage(sid, true).then(() => render()); }
  async function copyInfos(sid) { const res = await svc.copyRecap(infosVM(sid).usage().recap(sid)); notify(res.message, !res.ok); }
  /** La session attachée change : le ticket affiché = son ancrage (RM2173), changeable via les sous-onglets. */
  function onAttach(sid) {
    sid = String(sid); state.ticket = /^\d+$/.test(sid) ? sid : null; state.facet = "detail";
    render();                                              // affiche le cache (ou « chargement »)
    if (state.ticket) { const rm = state.ticket; T.ensureResolved(rm).then(() => { if (attached() === sid) render(); }); refreshWorkspace(rm); }
  }

  const acts = {
    "refresh-usage": (n) => refreshUsage(n.dataset.rm), "copy-infos": (n) => copyInfos(n.dataset.rm),
    tab: (n) => setTab(n.dataset.rm), facet: (n) => setFacet(n.dataset.facet), ticket: (n) => showTicket(n.dataset.rm),
    launcher: (n) => ctx.gotoTicket && ctx.gotoTicket(n.dataset.rm), review: (n) => ctx.openReview && ctx.openReview(n.dataset.rm),
    reload: (n) => ctx.reload && ctx.reload(n.dataset.rm), status: (n, e) => ctx.openStatusMenu && ctx.openStatusMenu(n.dataset.rm, n, e),
    reopen: (n) => ctx.reopen && ctx.reopen(n.dataset.rm), project: (n) => ctx.openProject && ctx.openProject(n.dataset.key),
    "refresh-ws": (n) => refreshWorkspace(n.dataset.rm),
  };
  const events = [["click", "[data-action]", (e, n) => { const f = acts[n.dataset.action]; if (f) { e.stopPropagation(); f(n, e); } }]];
  const infosH = infos ? mount(infos, "", { events }) : null;
  const ticketsH = tickets ? mount(tickets, "", { events }) : null;
  // RM3005 : UN abonnement au store de résolution — une fiche qui arrive (ou tombe) re-rend la liste si elle la concerne ;
  // c'est ce qui remplace le `.then(render)` par ticket en vol (et reste à l'abri du fan-out 2^N de RM2807)
  if (ticketsH) ticketsH.track(resolve().subscribe((k) => { if (k == null || String(k) === String(state.ticket) || sessionTickets().includes(String(k))) renderTickets(); }));
  const handle = { unmount() { if (infosH) infosH.unmount(); if (ticketsH) ticketsH.unmount(); } };
  return Object.assign(handle, { render, renderInfos, renderTickets, showTicket, setTicket, ticketIs, current: () => state.ticket, facet: () => state.facet,
    setTab, setFacet, refreshWorkspace, refreshUsage, copyInfos, sessionTickets, onAttach, state });
}
