// controllers/tickets.controller — le panneau 🎫 tickets du volet gauche : triage ROI (RM1952/2830/2831), carte des
// tickets ouverts (RM2606/2757/2883), infobulles d'un RM-id (RM2619). RM2889.
//
// Hôtes : `triage` = la <details> du triage (filtres + liste), `opened` = la <details> des tickets ouverts,
// `badge` = le compteur de l'onglet. Le monolithe prête : les résolutions (cache partagé), l'ouverture d'une
// fiche, l'épinglage, le contexte client, le lancement d'un lot (chemin partagé RM2823/2831), le presse-papier.
import { mount, paint } from "../../core/dom.js";
import { html, attrs } from "../../core/html.js";
import { TicketsPanelService } from "./tickets.service.js";
import { OpenedViewModel, TriageViewModel } from "./TicketsPanelViewModel.js";
import { OpenedList, TriageList, FilterOptions } from "./TicketsPanel.view.js";
import { openedPanelOpen } from "./openedTickets.js";
import { triageBatchItems } from "./triage.js";
import { ticketTipText } from "./briefs.js";

export function mountTicketsPanel({ triage, opened, badge } = {}, ctx = {}) {
  const T = ctx.ticket;
  const svc = ctx.service || new TicketsPanelService({ storage: ctx.storage });
  const notify = ctx.notify || (() => {});
  const q = (root, sel) => (root && root.querySelector ? root.querySelector(sel) : null);
  const resolve = () => ctx.resolve();   // store ticket.resolve (RM3005)
  const state = { client: null, family: null, triageRows: [] };

  // ── infobulles (RM2619) : attribut prêt à coller, briefs demandés en lot, mis à jour en place ──
  function tipAttr(id) {
    const s = String(id == null ? "" : id).replace(/^RM/i, "");
    if (!/^\d+$/.test(s)) return "";
    svc.requestBriefs([s], refreshTips);
    return " " + String(attrs({ "data-tip-rm": s, title: ticketTipText(s, svc.brief(s)) }));
  }
  function refreshTips() {
    if (!ctx.root || !ctx.root.querySelectorAll) return;
    ctx.root.querySelectorAll("[data-tip-rm]").forEach(el => { const id = el.getAttribute("data-tip-rm"); el.setAttribute("title", ticketTipText(id, svc.brief(id))); });
  }

  // ── tickets ouverts (RM2606) ──────────────────────────────────────────────
  function renderOpened() {
    const n = svc.opened.length;
    if (badge) { badge.textContent = String(n); badge.style.display = n ? "" : "none"; }
    if (!openedH) return;
    const vm = new OpenedViewModel({ ids: svc.opened, cache: resolve().view, client: state.client, family: state.family });
    const cnt = q(opened, "#opened-count"); if (cnt) cnt.textContent = vm.countLabel;
    openedH.update(OpenedList(vm, { tip: tipAttr, pin: ctx.pinOf || (() => "") }));
  }
  /** Ce qu'on consulte s'empile ici. RM2807 : UN .then(render) par ticket en vol — jamais un par rendu. */
  function noteOpened(id) {
    svc.note(id);
    svc.opened.forEach(t => { if (resolve().get(t) === undefined && !T.inFlight(t)) T.ensureResolved(t); });   // RM3005 : l'abonnement re-rend
    renderOpened();
  }
  function forget(id) { svc.forget(id); renderOpened(); }
  function clear() { svc.clear(); state.client = null; state.family = null; renderOpened(); }
  function filterClient(c) { state.client = c || null; renderOpened(); }
  function filterFamily(f) { state.family = f || null; renderOpened(); }

  // ── triage ROI (RM1952) ───────────────────────────────────────────────────
  const val = (sel) => { const el = q(triage, sel); return el ? (el.type === "checkbox" ? !!el.checked : String(el.value || "")) : (sel.indexOf("hidevalid") >= 0 ? false : ""); };
  function fillFilters() {
    const tickets = svc.triageTickets, cs = q(triage, "#tr-client"), ps = q(triage, "#tr-project");
    if (cs) {
      const prev = cs.value || (ctx.clientContext ? ctx.clientContext() : "") || "";    // défaut : le contexte client (RM2639)
      const vm = new TriageViewModel({ tickets });
      paint(cs, FilterOptions(vm.clients, prev, "tous les clients"));
    }
    if (ps) { const prev = ps.value; paint(ps, FilterOptions(new TriageViewModel({ tickets, client: val("#tr-client") }).projects, prev, "tous les projets")); }
  }
  function renderTriage() {
    if (!triageH || !svc.triageData) return;
    const ps = q(triage, "#tr-project");
    if (ps) { const prev = ps.value; paint(ps, FilterOptions(new TriageViewModel({ tickets: svc.triageTickets, client: val("#tr-client") }).projects, prev, "tous les projets")); }
    const vm = new TriageViewModel({ tickets: svc.triageTickets, client: val("#tr-client"), project: val("#tr-project"), hideValid: val("#tr-hidevalid"), tag: val("#tr-tag") });
    state.triageRows = vm.rows;                                  // RM2831 : ce qui est affiché EST le lot
    const sp = q(triage, "#tr-spawn"); if (sp) sp.style.display = vm.count ? "" : "none";
    triageH.update(TriageList(vm));
  }
  async function loadTriage(force) {
    if (!triageH) return;
    if (svc.triageData && !force) { renderTriage(); return; }
    triageH.update(html`<div style="color:var(--muted)">calcul du classement ROI…</div>`);
    try { await svc.loadTriage(force); fillFilters(); renderTriage(); }
    catch (e) { triageH.update(html`<div class="tr-err">échec du classement : ${e.message}</div>`); }
  }
  const triageRows = () => state.triageRows.slice();
  /** RM2830 : le menu d'étiquettes du triage vient de l'inventaire chargé par la recherche ; le filtre courant survit. */
  function setTags(tags) { const sel = q(triage, "#tr-tag"); if (!sel) return; const cur = sel.value; paint(sel, FilterOptions((tags || []).map(t => String(t.tag)), cur, "toutes les étiquettes")); sel.value = cur; }
  /** RM2831 : la liste AFFICHÉE part dans une session à elle, par le chemin partagé de RM2823. */
  async function spawnFromTriage(btn) {
    const rows = triageRows();
    if (!rows.length) { notify("aucun ticket dans cette liste", true); return; }
    const max = 10;
    if (ctx.spawnBatch) await ctx.spawnBatch(triageBatchItems(rows, max), btn, { titre: "Ouvrir une session sur ce lot",
      reste: rows.length > max ? "⊘ " + (rows.length - max) + " ticket(s) au-delà des " + max + " premiers ne partent pas (une file trop longue déborde le contexte de l'agent)." : "" });
  }

  // ── montage ──────────────────────────────────────────────────────────────
  const openedActs = { open: (n) => ctx.showTicket && ctx.showTicket(n.dataset.rm), forget: (n) => forget(n.dataset.rm), clear: () => clear(), client: (n) => filterClient(n.dataset.client), family: (n) => filterFamily(n.dataset.family) };
  const openedBox = q(opened, "#openedbox");
  const openedH = openedBox ? mount(openedBox, "", { events: [["click", "[data-action]", (e, n) => { const f = openedActs[n.dataset.action]; if (f) { e.stopPropagation(); f(n); } }]] }) : null;
  const triageBox = q(triage, "#triage-list");
  const triageH = triageBox ? mount(triageBox, "", { events: [["click", "[data-action=\"open\"]", (e, n) => { e.stopPropagation(); if (ctx.showTicket) ctx.showTicket(n.dataset.rm); }]] }) : null;
  if (openedH) openedH.track(resolve().subscribe((k) => { if (k == null || svc.opened.includes(String(k))) renderOpened(); }));   // RM3005
  const handle = { unmount() { if (openedH) openedH.unmount(); if (triageH) triageH.unmount(); disposers.forEach(d => d()); } };
  const disposers = [];
  const listen = (el, type, fn) => { if (el && el.addEventListener) { el.addEventListener(type, fn); disposers.push(() => el.removeEventListener(type, fn)); } };
  // les gestes de la carte (hors liste) : filtres, ↻, ⇱ session, dépliage
  listen(triage, "change", (e) => { const t = e.target; if (t && /^(tr-client|tr-project|tr-tag|tr-hidevalid)$/.test(t.id || "")) renderTriage(); });
  listen(triage, "click", (e) => { const t = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (!t) return; if (t.dataset.action === "reload") { e.preventDefault(); loadTriage(true); } else if (t.dataset.action === "spawn") { e.preventDefault(); spawnFromTriage(t); } });
  listen(triage, "toggle", () => { if (triage.open) loadTriage(); });
  listen(opened, "toggle", () => svc.rememberCard(!!opened.open));
  if (opened && "open" in opened) opened.open = openedPanelOpen(svc.cardOpen());        // RM2757 : replié sauf choix explicite
  renderOpened();                                                                      // RM2606 : restaurée du localStorage
  return Object.assign(handle, { loadTriage, renderTriage, triageRows, spawnFromTriage, setTags, noteOpened, forget, clear, filterClient, filterFamily, renderOpened,
    opened: () => svc.opened.slice(), tipAttr, refreshTips, brief: (id) => svc.brief(id), state });
}
