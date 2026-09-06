// controllers/review.controller — la surface « revue » du centre : trois gestes. RM2889.
//
// Troisième surface enregistrée auprès du routeur. Le contexte prête ce que le monolithe
// possède encore : le runner PM, l'encart ℹ (metaTicket, renderMeta), la liste des
// sessions, l'attache, la recherche par étiquette, le lanceur (moteur/modèle), la file
// « à tester » (entrée, gestes d'env), le modèle ticket (résolution, mergecheck, sessions).
// La consigne saisie sur la fiche vit ICI, hors du DOM : la fiche se re-rend sur
// événement, un textarea re-rendu perdrait la saisie (RM2873).
import { mount } from "../../core/dom.js";
import { html, raw } from "../../core/html.js";
import { ReviewService } from "./review.service.js";
import { ReviewViewModel, StatusMenuViewModel } from "./ReviewViewModel.js";
import { ReviewPane, StatusMenu } from "./Review.view.js";
import { statusPromptSpec } from "../ticket/ticketStatus.js";
import { promptFillOnChange, ticketPromptFor, taskPromptText, roleHintLine, duplicateSessionText } from "../ticket/prompts.js";

export function mountReview(el, ctx = {}) {
  const T = ctx.ticket;                                   // façade du modèle ticket (boot.js)
  const svc = ctx.service || new ReviewService({ repo: T.repo, run: ctx.run, eff: ctx.eff });
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const ask = ctx.confirm || ((m) => window.confirm(m));
  const prompt = ctx.prompt || ((m, d) => window.prompt(m, d));
  const state = { tabs: [], current: null, prompt: { rm: null, tpl: "traiter", text: "" } };
  const resolved = (rm) => (ctx.resolve ? ctx.resolve().get(rm) : null) || null;
  const stores = () => T.repo.s;   // RM3005 : stores ticket.mergecheck / ticket.sessions du dépôt

  // ── la consigne de la fiche (RM2873) ──────────────────────────────────────
  const promptDefault = (rm, tpl) => { const r = resolved(rm) || {}; return taskPromptText(tpl || "traiter", rm, r.client, r.project, r.role_hint); };
  const promptSync = (rm) => { state.prompt = ticketPromptFor(state.prompt, rm, promptDefault(rm, "traiter")); return state.prompt; };
  const promptText = (rm) => (String(state.prompt.rm || "") === String(rm) && state.prompt.text) ? state.prompt.text : promptDefault(rm, "traiter");

  // ── rendu ────────────────────────────────────────────────────────────────
  function render() {
    const rm = state.current; if (!rm) return;
    const c = stores(); const mcE = c.mc.get(rm);
    const vm = new ReviewViewModel({ r: resolved(rm), q: ctx.tq ? ctx.tq.entry(rm) : undefined, tqLoaded: ctx.tq ? ctx.tq.loaded() : false, tqSize: ctx.tq ? ctx.tq.size() : 0,
      mc: mcE && mcE.mc, ts: c.ts.get(rm), cfg: ctx.cfg ? ctx.cfg() : {}, pmTarget: ctx.pmTarget ? ctx.pmTarget(rm) : null }, { rm, prompt: promptSync(rm) });
    handle.update(ReviewPane(vm, { md: ctx.md || (s => s), titleLink: ctx.titleLink || ((r, t) => String(t || "")), mcBanner: T.mcBanner }));
  }
  const refreshAll = () => { render(); if (ctx.renderMeta) ctx.renderMeta(); if (ctx.center) ctx.center.title(); };

  // ── ouvrir / fermer ──────────────────────────────────────────────────────
  function open(rm) {
    rm = String(rm);
    if (ctx.noteOpened) ctx.noteOpened(rm);                 // RM2606 : la revue est une consultation aussi
    if (ctx.center) ctx.center.yield("review");
    if (!state.tabs.includes(rm)) state.tabs.push(rm);
    state.current = rm;
    if (ctx.setMeta) ctx.setMeta(rm);                         // encart ℹ : ce ticket, facette détail
    if (ctx.show) ctx.show(true);
    if (ctx.center) ctx.center.note("review", rm, "RM" + rm);
    if (ctx.showRight) ctx.showRight("tickets");
    refreshAll();
    if (ctx.filesEnsure) ctx.filesEnsure();
    const still = () => state.current === rm;
    T.ensureResolved(rm).then(() => { if (still()) { refreshAll(); if (ctx.filesEnsure) ctx.filesEnsure(); } });
    T.revalidate(rm, () => { if (still()) refreshAll(); });   // RM2630 : le pire endroit pour lire du périmé
    T.ensureMergecheck(rm).then(() => { if (still()) render(); });
    T.ensureTicketSessions(rm, true).then(() => { if (still()) render(); });   // RM2726 : forcé
    if (ctx.tq && ctx.tq.entry(rm) === undefined) ctx.tq.load();
    if (ctx.refreshSessions) ctx.refreshSessions();
  }
  function close(rm) {
    rm = rm == null ? state.current : String(rm);
    state.tabs = state.tabs.filter(x => x !== rm);
    if (state.current === rm) {
      state.current = null;
      if (ctx.setMeta) ctx.setMeta(null);
      if (ctx.show) ctx.show(false);
      if (ctx.center) ctx.center.fallback();
      if (ctx.renderMeta) ctx.renderMeta();
    }
    if (ctx.center) ctx.center.title();
    if (ctx.refreshSessions) ctx.refreshSessions();
  }
  /** Une autre surface prend le centre : la revue cède sans fermer ses onglets. */
  function yieldTo() { if (state.current) { state.current = null; if (ctx.show) ctx.show(false); } }

  // ── statuts et verdicts (RM2786, RM2888) ─────────────────────────────────
  const failed = (title, r) => { if (!r.ok && ctx.capture) ctx.capture(title + " — ÉCHEC", (r.stdout || "") + "\n" + (r.stderr || "")); };
  async function afterStatusChange(rm) {
    await T.ensureResolved(rm, true);
    if (ctx.metaIs && ctx.metaIs(rm) && ctx.renderMeta) ctx.renderMeta();
    if (state.current === rm) render();
    if (ctx.afterStatus) ctx.afterStatus(rm);
  }
  async function verdict(rm, kind, btn) {
    rm = String(rm); const v = svc.verdictSpec(kind);
    const note = prompt("RM" + rm + " → " + v.status + "\n" + v.label + " :", v.def || "");
    if (note === null) return;
    if (!note && !v.def) { notify("Motif requis", true); return; }
    if (btn) btn.disabled = true;
    try { const r = await svc.verdict(rm, kind, note, ask, notify); notify(r.ok ? "RM" + rm + " → " + v.status : "Échec (rc=" + r.rc + ")", !r.ok); failed(r.delivery_failed ? "Livraison RM" + rm : "Verdict RM" + rm, r); }
    catch (e) { notify(e.message, true); }
    finally { await T.ensureResolved(rm, true); if (ctx.tq) ctx.tq.load(); if (state.current === rm) render(); }
  }
  async function applyStatus(rm, target, needsReason, reasons, needsNote) {
    rm = String(rm); const spec = statusPromptSpec(target, needsReason, reasons, needsNote);
    const note = prompt("RM" + rm + " → " + target + "\n" + spec.note_label, "");
    if (note === null) return;
    if (spec.needs_note && !note.trim()) { notify("Note requise pour cette transition", true); return; }
    let reason = null;
    if (spec.needs_reason) { reason = prompt("RM" + rm + " → " + target + "\nMotif de fermeture (" + spec.reasons.join(" | ") + ") :", spec.default_reason); if (reason === null) return; if (!reason.trim()) { notify("Motif de fermeture requis", true); return; } reason = reason.trim(); }
    try { const r = await svc.applyStatus(rm, target, { note, reason }, ask, notify); notify(r.ok ? "RM" + rm + " → " + target : "Échec (rc=" + r.rc + ")", !r.ok); failed(r.delivery_failed ? "Livraison RM" + rm : "Statut RM" + rm + " → " + target, r); }
    catch (e) { notify(e.message, true); }
    finally { await afterStatusChange(rm); }
  }
  // Popover ancré (même mécanique que le menu de disposition) : la liste est chargée APRÈS ouverture.
  let menu = null;
  function closeStatusMenu() { if (menu) { menu.unmount(); if (menu.el.remove) menu.el.remove(); menu = null; } }
  async function openStatusMenu(ref, anchor, ev) {
    if (ev && ev.stopPropagation) ev.stopPropagation();
    closeStatusMenu();
    const rm = String(ref).replace(/^RM/i, "");
    const box = ctx.popover ? ctx.popover() : null; if (!box) return;
    menu = mount(box, html`<button disabled>chargement…</button>`, { events: [["click", "button[data-st]", (e, b) => { if (e.stopPropagation) e.stopPropagation(); const d = menu && menu.data; closeStatusMenu(); applyStatus(rm, b.dataset.st, !!b.dataset.reason, (d && d.close_reasons) || [], !!b.dataset.note); }]] });
    const place = () => ctx.place && ctx.place(box, anchor);
    place();
    const arm = () => setTimeout(() => ctx.onOutsideClick && ctx.onOutsideClick(closeStatusMenu), 0);
    let data;
    try { data = await svc.transitions(rm); } catch (e) { if (menu) menu.update(html`<button disabled>${e.message || "transitions indisponibles"}</button>`); place(); arm(); return; }
    if (!menu) return;                                      // refermé entre-temps
    menu.data = data; menu.update(StatusMenu(new StatusMenuViewModel(data))); place(); arm();
  }

  // ── sessions du ticket : lancer, envoyer, rejoindre (RM2726, RM2818, RM2873) ─
  async function confirmSecondSession(rm) {
    const busy = await svc.busyFor(rm);
    if (!busy.alive.length) return true;
    if (ask(duplicateSessionText(rm, busy, ctx.eff) + "\n\nRejoindre cette session plutôt que d'en ouvrir une seconde ?\n(OK : rejoindre  ·  Annuler : voir l'autre option)")) { if (ctx.attach) ctx.attach(busy.alive[0].sid); return false; }
    return ask("Ouvrir QUAND MÊME une seconde session sur RM" + rm + " ?\n\nDeux agents travailleraient le même ticket : même branche, même worktree, même statut Redmine — et le second écrase les décisions du premier sans le savoir.");
  }
  async function spawnTicket(rm, btn) {
    rm = String(rm);
    if (!await confirmSecondSession(rm)) return;
    const r = resolved(rm) || {}, lm = ctx.launcher ? ctx.launcher() : {}, engine = lm.engine || "claude", model = lm.model || "", cwd = r.cwd || "";
    const text = promptText(rm);
    if (!ask("Lancer une nouvelle session pour RM" + rm + " ?" + roleHintLine(r.role_hint) + "\n\nmoteur : " + engine + (model ? "  ·  modèle : " + model : "") + "\ncwd : " + (cwd || "(défaut du serveur)") + "\n\n" + text)) return;
    if (btn) btn.disabled = true;
    try {
      const body = { rm_id: rm, engine, prompt: text }; if (model) body.model = model; if (cwd) body.cwd = cwd;
      const sp = await svc.spawnTicket(body);
      notify("Session karl-RM" + rm + " lancée"); if (ctx.warnSpawn) ctx.warnSpawn(sp);
      stores().ts.invalidate(rm);
      if (ctx.refreshSessions) await ctx.refreshSessions();
      setTimeout(() => ctx.attach && ctx.attach(rm), 400);
    } catch (e) { notify(e.message, true); }
    finally { if (btn) btn.disabled = false; }
  }
  async function sendToSession(rm, btn) {
    rm = String(rm);
    const sel = handle.el.querySelector ? handle.el.querySelector("#ts-target") : null, sid = sel ? sel.value : "";
    if (!sid) { notify("aucune session choisie", true); return; }
    const c = ((stores().ts.get(rm) || {}).candidates || []).find(x => String(x.sid) === sid) || {};
    const msg = promptText(rm);
    const warn = c.same_project ? "" : "\n\n⚠ cette session travaille sur " + (c.client || "?") + "/" + (c.project || "?") + ", pas sur le projet du ticket.";
    if (!ask("Envoyer dans la session " + sid + (c.title ? " (" + c.title + ")" : "") + " :\n\n" + msg + warn)) return;
    if (btn) btn.disabled = true;
    try { await svc.sendToSession(sid, msg); notify("RM" + rm + " envoyé à " + sid); stores().ts.invalidate(rm); if (ctx.attach) ctx.attach(sid); }
    catch (e) { notify(e.message, true); } finally { if (btn) btn.disabled = false; }
  }

  const gestures = {
    reload: () => T.reload(state.current), close: () => close(state.current), tag: (n) => ctx.filterByTag && ctx.filterByTag(n.dataset.tag),
    verdict: (n) => verdict(n.dataset.rm, n.dataset.kind, n), pm: (n) => ctx.sendPmAction && ctx.sendPmAction(Number(n.dataset.i), n.dataset.rm, n),
    attach: (n) => ctx.attach && ctx.attach(n.dataset.sid), spawn: (n) => spawnTicket(n.dataset.rm, n), send: (n) => sendToSession(n.dataset.rm, n),
    "env-deploy": (n) => ctx.tq && ctx.tq.deploy(n.dataset.rm, n), "env-teardown": (n) => ctx.tq && ctx.tq.teardown(n.dataset.rm, n), "env-shared": (n) => ctx.tq && ctx.tq.deployShared(n.dataset.rm, n),
  };
  const handle = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => { const g = gestures[n.dataset.action]; if (g) return g(n); }],
    ["change", "[data-prompt]", (ev, n) => { if (n.dataset.prompt === "tpl") { const ta = handle.el.querySelector ? handle.el.querySelector("#ts-prompt") : null; state.prompt.tpl = n.value; state.prompt.text = promptFillOnChange(n.value, ta ? ta.value : state.prompt.text, promptDefault(state.prompt.rm, n.value)); if (ta) ta.value = state.prompt.text; } }],
    ["input", "[data-prompt]", (ev, n) => { if (n.dataset.prompt === "text") state.prompt.text = n.value; }],
  ] });
  return Object.assign(handle, { open, close, yieldTo, current: () => state.current, tabs: () => state.tabs.slice(), render, verdict, openStatusMenu, closeStatusMenu, applyStatus, confirmSecondSession, spawnTicket, promptText, state,
    titleHtml: (titleLink) => { if (!state.current) return ""; const r = resolved(state.current); return String(html`🧪 <span class="tid">RM${state.current}</span><span class="ttitle">${raw(titleLink(state.current, r && r.found ? r.title : ""))}</span>`); } });}
