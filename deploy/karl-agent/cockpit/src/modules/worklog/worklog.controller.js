// controllers/worklog.controller — l'onglet 🗒 worklog de la colonne de droite et ses lots (RM2466/2581/2610/2716/2719/2720/
// 2723/2786/2795/2796/2798/2801/2823/2831/2888/2935). RM2889.
//
// Hôtes : `body` (#workbody), `fresh` (#workfresh), `nav` (la barre ⟳ + boutons de lot). L'état (worklog, sélection, plans)
// vit dans le service. Le monolithe prête la session attachée, le registre (branches), CFG, le runner PM, la capture, la
// modale doc (écrans de lot), l'infobulle, la marque, linkify, la revue (fiche, menu de statut), la résolution des tickets,
// le lanceur (moteur/modèle), l'attache, les sessions, la liste des tickets ouverts.
import { mount } from "../../core/dom.js";
import { html } from "../../core/html.js";
import { WorklogService } from "./worklog.service.js";
import { WorklogViewModel, BatchPlanViewModel, MrBatchViewModel } from "./WorklogViewModel.js";
import { WorklogPane, BatchPlan, MrBatch, ClosePlan, CloseRefused } from "./Worklog.view.js";
import { BATCH_MODES, spawnConfirmLines, refId } from "./worklog.js";

export function mountWorklog({ body, fresh, nav } = {}, ctx = {}) {
  const svc = ctx.service || new WorklogService({ run: ctx.run });
  const notify = ctx.notify || (() => {});
  const ask = ctx.confirm || ((m) => window.confirm(m));
  const askText = ctx.prompt || ((m, d) => window.prompt(m, d));
  const alertBox = ctx.alert || ((m) => window.alert(m));
  const attached = () => { const a = ctx.attached ? ctx.attached() : null; return a == null ? null : String(a); };
  const cfg = () => (ctx.cfg ? ctx.cfg() : null) || {};
  const branches = () => { const a = attached(); const s = a && ctx.sess ? ctx.sess().get(a) : null; return ((s && s.registry) || {}).branches || []; };
  const deps = { tip: ctx.tipAttr || (() => ""), pin: ctx.pinOf || (() => ""), linkify: ctx.linkify || ((s) => String(s == null ? "" : s)) };
  const modal = ctx.modal || { open() {}, close() {}, content: () => null };

  function render() {
    const vm = new WorklogViewModel({ data: svc.data, attached: attached(), branches: branches(), selected: new Set(svc.selection.keys()), sub: svc.sub }, { ago: ctx.ago, integration: (svc.data || {}).integration });   // RM3074 : la branche d'intégration vient du serveur
    if (fresh) fresh.textContent = vm.fresh;
    if (bodyH) bodyH.update(WorklogPane(vm, deps));
    renderButtons();
    return vm;
  }
  /** RM2786 : un bouton n'apparaît que si la sélection le justifie ; son compteur dit ce qui va partir. */
  function renderButtons() {
    if (!nav || !nav.querySelector) return;
    const items = svc.selected, n = svc.buttons(cfg());
    const pose = (id, txt, compte) => { const e = nav.querySelector("#" + id); if (!e) return; e.style.display = (items.length && compte) ? "" : "none"; e.textContent = txt + " (" + compte + ")"; };
    pose("batch-etudier-btn", "🔍 analyser", n.etudier); pose("batch-btn", "▶ traiter", n.traiter); pose("batch-atester-btn", "✔ à tester", n.atester);
    pose("mr-dev-btn", "⇥ merger dev", n.mr); pose("mr-prod-btn", "⇥ merger prod", n.mr); pose("batch-close-btn", "✅ fermer", n.fermer);
    pose("batch-offload-btn", "⇱ nouvelle session", items.length);              // RM2823 : ne dépend d'aucun statut
  }
  async function load(force) {
    const a = attached();
    if (!a) { svc.clear(); render(); return; }
    await svc.load(a, force);
    render();
    if (ctx.afterLoad) ctx.afterLoad();                                          // RM2673 : le worklog alimente la liste des tickets
  }
  /** Le composite /refresh pousse un worklog frais (RM2763) — d'une session qu'on n'a pas quittée entre-temps. */
  function setFromRefresh(data) { if (data && String(data.rm_id) === attached()) { svc.setFromRefresh(data); render(); } }
  function setSub(k) { svc.sub = k; render(); }
  function toggle(ref, status, title, on) { svc.toggle(ref, status, title, on); renderButtons(); }
  function openItem(ref) { if (/^RM\d+$/i.test(String(ref || ""))) { if (ctx.openReview) ctx.openReview(refId(ref)); } else notify("Chantier hors ticket : " + ref); }
  const boxes = () => { const c = modal.content ? modal.content() : null; return c && c.querySelectorAll ? [...c.querySelectorAll(".bp-point input")].map(b => ({ ref: b.dataset.ref, value: b.value, checked: !!b.checked })) : []; };
  // ── lots ─────────────────────────────────────────────────────────────────
  async function openBatchPlan(mode) {
    const a = attached(); if (!a) { notify("aucune session attachée", true); return; }
    if (!svc.selection.size) return;
    const m = BATCH_MODES[mode] ? mode : "traiter", c = BATCH_MODES[m];
    let plan; try { plan = await svc.planBatch(a, m); } catch (e) { notify(e.message, true); return; }
    modal.open(c.titre + " " + plan.count + " ticket(s) — session " + a, BatchPlan(new BatchPlanViewModel(plan), { envoi: c.envoi }), onModalAction);
  }
  async function sendBatch(btn) {
    const a = attached(); if (!svc.plan || !a) return;
    if (btn) btn.disabled = true;
    try { const r = await svc.sendBatch(a, boxes()); const ecartes = (r.skipped || []).length; notify((r.mode === "atester" ? "✔ " : "▶ ") + r.count + " ticket(s) envoyés à la session " + a + (ecartes ? " · " + ecartes + " écarté(s)" : "")); modal.close(); load(true); }
    catch (e) { notify(e.message, true); } finally { if (btn) btn.disabled = false; }
  }
  async function openMrBatch(mode) {
    if (!svc.selection.size) return;
    let plan; try { plan = await svc.planMr(mode); } catch (e) { notify(e.message, true); return; }
    modal.open((mode === "prod" ? "⇥ Promouvoir en production" : "⇥ Merger dans l’intégration") + " — " + (plan.runs || []).length + " MR", MrBatch(new MrBatchViewModel(plan)), onModalAction);
  }
  async function sendMr(btn) {
    if (!svc.mrPlan) return;
    if (btn) { btn.disabled = true; btn.textContent = "⇥ merge en cours…"; }
    try {
      const r = await svc.sendMr(); const ko = r.failed || [];
      notify(ko.length ? ko.length + " merge(s) en échec sur " + r.results.length : "⇥ " + r.results.length + " MR mergée(s)", !!ko.length);
      if (ko.length && ctx.capture) ctx.capture("Merge — ÉCHEC", ko.map(k => "RM" + k.rm_ids.join(",") + " " + k.source + "→" + k.target + "\n" + (k.stdout || "") + "\n" + (k.stderr || "")).join("\n\n"));
      else modal.close();
      load(true);
    } catch (e) { notify(e.message, true); } finally { if (btn) { btn.disabled = false; btn.textContent = "⇥ merger maintenant"; } }
  }
  function openCloseBatch() { if (!svc.selection.size) return; const p = svc.closePlan(cfg()); modal.open("✅ Fermer " + p.count + " ticket(s) — résolu", ClosePlan(p), onModalAction); }
  async function sendClose(btn) {
    const p = svc.closePlanCache; if (!p || !p.count) return;
    const note = askText("Note de fermeture (commune aux " + p.count + " tickets) :", "Testé et validé."); if (note === null) return;
    if (btn) btn.disabled = true;
    const { ok, ko } = await svc.sendClose(note, (i, n) => { if (btn) btn.textContent = "✅ fermeture… (" + i + "/" + n + ")"; });
    modal.close();
    notify(ko.length ? ok.length + " fermé(s), " + ko.length + " refusé(s)" : "✅ " + ok.length + " ticket(s) fermé(s)", !!ko.length);
    if (ko.length) modal.open("Fermetures refusées (" + ko.length + ")", CloseRefused(ko), onModalAction);   // un refus porte ce qu'il faut faire
    renderButtons(); load(true);
  }
  /** RM2723 : merge d'une MR depuis le worklog — confirmation, puis la sortie du script en cas d'échec. */
  async function mergeOne(url, iid, target, btn) {
    if (!ask("Merger la MR !" + iid + (target ? " dans « " + target + " »" : "") + " ?\nLe merge passe par pm-mr (note Redmine, CF GIT PR, log du ticket).")) return;
    if (btn) { btn.disabled = true; btn.textContent = "⇥ merge…"; }
    try {
      const r = await svc.mergeOne(url);
      notify(r.ok ? "⇥ MR !" + iid + " mergée" : "Échec (rc=" + r.rc + ")", !r.ok);
      if (!r.ok && ctx.capture) ctx.capture("Merge MR !" + iid + " — ÉCHEC", (r.stdout || "") + "\n" + (r.stderr || ""));
      load(true); if (ctx.projectWorklog) ctx.projectWorklog();
    } catch (e) { notify(e.message, true); } finally { if (btn) { btn.disabled = false; btn.textContent = "⇥ merger"; } }
  }
  /** RM2823/2831 : CHEMIN PARTAGÉ — un lot part dans une session neuve, ancrée sur SON projet (worklog coché ou triage filtré). */
  async function spawnBatch(items, btn, opts) {
    const o = opts || {}; if (!items || !items.length) return;
    const T = ctx.ticket;
    if (T) await Promise.all(items.map(it => { const rm = refId(it.rm_id); return (ctx.resolve ? ctx.resolve().get(rm) : undefined) === undefined ? T.ensureResolved(rm) : Promise.resolve(); }));
    const plan = svc.offload(items, ctx.resolve ? ctx.resolve().view : {});
    if (plan.mixed) { alertBox("Ces tickets appartiennent à plusieurs projets :\n\n  " + plan.projects.join("\n  ") + "\n\nUne session s'ancre sur UN projet — restreins la sélection à un seul."); return; }
    if (!plan.anchor) { alertBox("Aucun de ces tickets n'a de projet résolu : impossible de savoir où ancrer la session."); return; }
    const retenus = new Set(plan.targets.map(t => t.rm_id)), envoyes = items.filter(it => retenus.has(refId(it.rm_id)));
    let plan2; try { plan2 = await svc.spawnPlan(attached() || plan.anchor, envoyes); } catch (e) { notify(e.message, true); return; }
    const launcher = ctx.launcher ? ctx.launcher() : { engine: "claude", model: "" };
    if (!ask(spawnConfirmLines(plan, launcher, o).join("\n"))) return;
    if (btn) btn.disabled = true;
    try {
      const body = { rm_id: plan.anchor, engine: launcher.engine, prompt: plan2.prompt }; if (launcher.model) body.model = launcher.model; if (plan.cwd) body.cwd = plan.cwd;
      const sp = await svc.spawn(body);
      notify("⇱ " + plan.targets.length + " ticket(s) → session karl-RM" + plan.anchor);
      if (ctx.warnSpawn) ctx.warnSpawn(sp);
      if (ctx.forgetTicketSessions) plan.targets.forEach(t => ctx.forgetTicketSessions(t.rm_id));
      if (o.apres) o.apres(plan);
      if (ctx.refreshSessions) await ctx.refreshSessions();
      if (ctx.attach) setTimeout(() => ctx.attach(plan.anchor), 400);
    } catch (e) { notify(e.message, true); } finally { if (btn) btn.disabled = false; }
  }
  /** RM2823 : les tickets cochés partent ailleurs et quittent la liste des tickets ouverts. */
  async function offload(btn) { if (!svc.selection.size) return; await spawnBatch(svc.selected, btn, { apres: (plan) => { if (ctx.forgetOpened) plan.targets.forEach(t => ctx.forgetOpened(t.rm_id)); svc.clearSelection(); renderButtons(); } }); }
  function onModalAction(action, n) { if (action === "send-batch") sendBatch(n); else if (action === "send-mr") sendMr(n); else if (action === "send-close") sendClose(n); else if (action === "merge-one") mergeOne(n.dataset.url, n.dataset.iid, n.dataset.target, n); }

  /** RM3114 : solder une demande. « ticketée » demande son numéro — sans lui, le rattachement
   *  serait perdu et la demande sortirait du « à traiter » sans dire où elle a atterri. */
  async function setRequestStatus(n) {
    const num = n.dataset.n, statut = n.dataset.status;
    if (!num || !statut) return;
    if (!attached()) { notify("aucune session attachée — le registre des demandes est celui d'une session", true); return; }
    let ticket = "";
    if (statut === "ticketee") {
      const ask = ctx.prompt || (typeof prompt === "function" ? prompt : null);
      ticket = String((ask && ask("Numéro du ticket qui porte cette demande (RM…) :")) || "").trim();
      if (!ticket) return;                       // renoncer n'est pas solder
      if (!/^(RM)?\d+$/i.test(ticket)) { notify("numéro de ticket attendu, par exemple RM3114", true); return; }
    }
    try {
      await svc.setRequestStatus(attached(), num, statut, ticket);
      notify("demande #" + num + " → " + statut + (ticket ? " (" + ticket.replace(/^RM/i, "RM") + ")" : ""));
      await load(true);
    } catch (e) { notify(e.message, true); }
  }

  const acts = { sub: (n) => setSub(n.dataset.key), open: (n) => openItem(n.dataset.ref), ticket: (n) => ctx.showTicket && ctx.showTicket(n.dataset.rm),
    // RM3114 : une question se lit et se tranche dans la FICHE de revue (le carnet y est rendu
    // avec ses boutons ✅/❌) — le panneau méta, lui, ne montre pas le carnet.
    review: (n) => (ctx.openReview ? ctx.openReview(n.dataset.rm) : ctx.showTicket && ctx.showTicket(n.dataset.rm)),
    request: (n) => setRequestStatus(n),
    toggle: (n) => toggle(n.dataset.ref, n.dataset.status, n.dataset.label, !!n.checked), status: (n, e) => ctx.openStatusMenu && ctx.openStatusMenu(n.dataset.ref, n, e),
    "mr-stage": (n) => ctx.openExternal && ctx.openExternal(n.dataset.url), "merge-one": (n) => mergeOne(n.dataset.url, n.dataset.iid, n.dataset.target, n) };
  const bodyH = body ? mount(body, "", { events: [["click", "[data-action]", (e, n) => { const f = acts[n.dataset.action]; if (!f) return; e.stopPropagation(); if (n.dataset.action !== "toggle") e.preventDefault(); f(n, e); }]] }) : null;
  const disposers = [];
  if (nav && nav.addEventListener) { const fn = (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (!n) return; e.preventDefault(); const a = n.dataset.action; if (a === "reload") load(true); else if (a === "batch") openBatchPlan(n.dataset.mode); else if (a === "mr") openMrBatch(n.dataset.mode); else if (a === "offload") offload(n); else if (a === "close-batch") openCloseBatch(); }; nav.addEventListener("click", fn); disposers.push(() => nav.removeEventListener("click", fn)); }
  return { load, render, setFromRefresh, setSub, toggle, openBatchPlan, sendBatch, openMrBatch, sendMr, openCloseBatch, sendClose, mergeOne, spawnBatch, offload, data: () => svc.data, pending: () => svc.pending, selection: () => svc.selected,
    unmount() { if (bodyH) bodyH.unmount(); disposers.forEach(d => d()); disposers.length = 0; } };
}
