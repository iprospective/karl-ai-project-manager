// controllers/launcher.controller — le lanceur de session (§1 résolution, RM1941 modèles, RM2873 consigne, RM2818 garde, spawn),
// la saisie éclair d'un ticket (§8) et le contexte client (RM2639, pré-filtre global de ce navigateur). RM2889.
//
// Hôtes : `card` (#lp-sessions .card : rm, resolved, engine, model, cwd, ptpl, prompt, spawnbtn), `ntcard` (nt-*), `clientctx`
// (le <select> du header). Le monolithe prête CFG, la consigne (revue), la garde de 2e session, le toast, la capture, le runner
// PM (réouverture RM2285), l'attache, les sessions/santé, et ce que le contexte client déclenche ailleurs (onContext).
import { LauncherService } from "./launcher.service.js";
import { LauncherViewModel } from "./LauncherViewModel.js";
import { ResolvedLine, Options } from "./Launcher.view.js";
import { spawnBody, ticketBody, clientCtxProject, DEFAULT_PROJECT } from "./launcher.js";
import { paint } from "../../core/dom.js";

export function mountLauncher({ card, ntcard, clientctx } = {}, ctx = {}) {
  const svc = ctx.service || new LauncherService({ storage: ctx.storage });
  const notify = ctx.notify || (() => {});
  const askText = ctx.prompt || ((m, d) => window.prompt(m, d));
  const cfg = () => (ctx.cfg ? ctx.cfg() : null) || {};
  const q = (root, sel) => (root && root.querySelector ? root.querySelector(sel) : null);
  const el = { rm: () => q(card, "#rm"), resolved: () => q(card, "#resolved"), engine: () => q(card, "#engine"), model: () => q(card, "#model"), cwd: () => q(card, "#cwd"), tpl: () => q(card, "#ptpl"), prompt: () => q(card, "#prompt"), spawn: () => q(card, "#spawnbtn"),
    ntTitle: () => q(ntcard, "#nt-title"), ntProject: () => q(ntcard, "#nt-project"), ntType: () => q(ntcard, "#nt-type"), ntPrio: () => q(ntcard, "#nt-prio"), ntTags: () => q(ntcard, "#nt-tags"), ntDesc: () => q(ntcard, "#nt-desc"), ntBtn: () => q(ntcard, "#nt-btn") };
  const val = (e) => (e ? String(e.value || "") : "");
  const vm = () => new LauncherViewModel({ resolved: svc.resolved, cfg: cfg(), engine: val(el.engine()) || "claude", prevModel: val(el.model()), projects: svc.projects, clientContext: svc.clientContext });
  let resolveTimer = null;

  // ── §1 : résolution rm_id → client/projet/cwd/prompt ──
  function paintResolved() {
    const e = el.resolved(); if (!e) return;
    const line = vm().line;
    e.className = line && !line.found ? "resolved nf" : "resolved";
    paint(e, ResolvedLine(line));
    if (line && line.found && line.cwd && el.cwd()) el.cwd().value = line.cwd;
  }
  async function resolve() {
    const rm = val(el.rm()).trim();
    await svc.resolve(rm);
    paintResolved(); applyTemplate(); populateModels();                        // rafraîchit « défini dans le ticket (…) »
    return svc.resolved;
  }
  const resolveSoon = () => { clearTimeout(resolveTimer); resolveTimer = setTimeout(resolve, 300); };
  function populateModels() { const sel = el.model(); if (!sel) return; const m = vm().models; paint(sel, Options(m.options, m.value)); sel.value = m.value; }
  /** RM2726/2873 : la consigne vit dans le modèle des consignes (prêté par la revue) — même texte que la fiche. */
  function applyTemplate() {
    const ta = el.prompt(); if (!ta || !ctx.promptText) return;
    const r = svc.resolved && svc.resolved.found ? svc.resolved : null;
    const txt = ctx.promptText(val(el.tpl()), val(el.rm()).trim(), r && r.client, r && r.project, r && r.role_hint);
    ta.value = ctx.promptFill ? ctx.promptFill(val(el.tpl()), ta.value, txt) : txt;
  }
  /** Poser un ticket dans le lanceur (fiche ℹ, recherche, création) et le résoudre. */
  function setRm(rm, opts) { const i = el.rm(); if (i) i.value = rm; const p = resolve(); if (opts && opts.switchPanel && ctx.switchPanel) ctx.switchPanel("sessions"); if (opts && opts.scroll && i && i.scrollIntoView) i.scrollIntoView({ block: "nearest", behavior: "smooth" }); return p; }
  /** RM2173 : depuis un RM-id → lanceur pré-rempli, et rattache si la session tourne déjà (RM2427 : jamais une fantôme). */
  async function goto(rm) { setRm(rm, { switchPanel: true }); if (await svc.isRunning(rm) && ctx.attach) ctx.attach(rm); }
  async function spawn() {
    const sb = spawnBody({ rm: val(el.rm()), engine: val(el.engine()), model: val(el.model()), cwd: val(el.cwd()), prompt: val(el.prompt()) });
    if (sb.error) { notify(sb.error, true); return; }
    if (ctx.confirmSecondSession && !(await ctx.confirmSecondSession(sb.rm))) return;      // RM2818
    const btn = el.spawn(); if (btn) { btn.disabled = true; btn.textContent = "Lancement…"; }
    try {
      const sp = await svc.spawn(sb.body);
      notify("Session karl-RM" + sb.rm + " lancée");
      if (ctx.warnSpawn) ctx.warnSpawn(sp);                                        // RM2450 jeu plein · RM2951 moteur bloqué
      if (el.prompt()) el.prompt().value = "";
      if (ctx.afterSpawn) await ctx.afterSpawn();
      if (ctx.attach) setTimeout(() => ctx.attach(sb.rm), 400);
    } catch (e) { notify(e.message, true); }
    finally { if (btn) { btn.disabled = false; btn.textContent = "▶ Lancer & attacher"; } }
  }
  /** RM2285 : rouvrir un ticket fermé (ferme → a_faire), motif requis, par pm-task-status-update. */
  async function reopen(rm) {
    rm = String(rm);
    const note = askText("RM" + rm + " → a_faire (réouverture)\nMotif de la réouverture (requis) :", ""); if (note === null) return;
    if (!note.trim()) { notify("Motif requis", true); return; }
    try {
      const r = await ctx.run("task-status", { rm_id: rm, status: "a_faire", note: note.trim() }, { confirm: true });
      notify(r.ok ? "RM" + rm + " rouvert → a_faire" : "Échec réouverture (rc=" + r.rc + ")", !r.ok);
      if (!r.ok && ctx.capture) ctx.capture("Réouverture RM" + rm + " — ÉCHEC", (r.stdout || "") + "\n" + (r.stderr || ""));
    } catch (e) { notify(e.message, true); }
    finally { if (ctx.afterStatus) await ctx.afterStatus(rm); if (val(el.rm()).trim() === rm) resolve(); }   // re-résout partout (RM2229)
  }
  // ── §8 : saisie éclair d'un ticket ──
  function fillTicketForm() {
    const v = vm();
    if (el.ntType() && !(el.ntType().options && el.ntType().options.length)) paint(el.ntType(), Options(v.types));
    if (el.ntPrio() && !(el.ntPrio().options && el.ntPrio().options.length)) paint(el.ntPrio(), Options(v.priorities));
  }
  async function createTicket() {
    const tb = ticketBody({ title: val(el.ntTitle()), project: val(el.ntProject()), type: val(el.ntType()), priority: val(el.ntPrio()), tags: val(el.ntTags()), description: val(el.ntDesc()) });
    if (tb.error) { notify(tb.error, true); return; }
    const btn = el.ntBtn(); if (btn) { btn.disabled = true; btn.textContent = "Création…"; }
    try {
      const r = await svc.createTicket(tb.body);
      notify("Ticket RM" + r.rm_id + " créé");
      setRm(r.rm_id);                                                              // pré-remplit le lanceur
      [el.ntTitle(), el.ntTags(), el.ntDesc()].forEach(e => { if (e) e.value = ""; });
      if (ntcard && "open" in ntcard) ntcard.open = false;
      if (ctx.afterCreate) ctx.afterCreate(r);
    } catch (e) { notify(e.message, true); }
    finally { if (btn) { btn.disabled = false; btn.textContent = "Créer le ticket"; } }
  }
  // ── projets connus et contexte client (RM2639) ──
  function paintProjects() {
    const sel = el.ntProject(); if (sel) { const prev = sel.value; paint(sel, Options(svc.projects.map(p => ({ value: p.value, label: p.value })), null)); const proj = clientCtxProject(svc.projects, svc.clientContext); sel.value = svc.projects.some(p => p.value === prev) ? prev : (proj || (svc.projects.some(p => p.value === DEFAULT_PROJECT) ? DEFAULT_PROJECT : (svc.projects[0] || {}).value || "")); }
    if (clientctx) { paint(clientctx, Options(vm().clients.map(c => ({ value: c, label: c })), svc.clientContext, "Tous les clients")); clientctx.value = svc.clientContext; }
  }
  async function loadProjects() {
    try { await svc.loadProjects(); } catch (e) { return; }                        // silencieux : le lanceur reste utilisable sans liste
    paintProjects();
    if (ctx.onProjects) ctx.onProjects(svc.projects);
    if (svc.clientContext && ctx.onContext) ctx.onContext(svc.clientContext, clientCtxProject(svc.projects, svc.clientContext), true);   // pré-filtre appliqué au chargement
  }
  /** Le contexte change : ce navigateur le retient ; les formulaires suivent sans se figer ; le reste du cockpit est prévenu. */
  function setClientContext(c) {
    svc.setClientContext(c);
    if (clientctx) clientctx.value = svc.clientContext;
    const proj = clientCtxProject(svc.projects, svc.clientContext);
    if (proj && el.ntProject()) el.ntProject().value = proj;
    if (ctx.onContext) ctx.onContext(svc.clientContext, proj, false);
  }
  const disposers = [];
  const listen = (node, type, fn) => { if (node && node.addEventListener) { node.addEventListener(type, fn); disposers.push(() => node.removeEventListener(type, fn)); } };
  listen(card, "input", (e) => { if (e.target && e.target.id === "rm") resolveSoon(); });
  listen(card, "keydown", (e) => { if (e.target && e.target.id === "rm" && e.key === "Enter") spawn(); });
  listen(card, "change", (e) => { const id = (e.target && e.target.id) || ""; if (id === "engine") populateModels(); else if (id === "ptpl") applyTemplate(); });
  listen(card, "click", (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (!n) return; e.preventDefault(); if (n.dataset.action === "spawn") spawn(); else if (n.dataset.action === "reopen") reopen(val(el.rm()).trim()); });
  listen(ntcard, "click", (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (n && n.dataset.action === "create") { e.preventDefault(); createTicket(); } });
  listen(clientctx, "change", (e) => setClientContext(e.target.value));
  if (ctx.onContext && svc.clientContext) ctx.onContext(svc.clientContext, "", true);   // le contexte restauré est connu du reste dès le montage
  return { resolve, setRm, goto, spawn, reopen, createTicket, populateModels, applyTemplate, fillTicketForm, loadProjects, setClientContext, projects: () => svc.projects, clientContext: () => svc.clientContext, resolved: () => svc.resolved, rm: () => val(el.rm()).trim(),
    unmount() { clearTimeout(resolveTimer); disposers.forEach(d => d()); disposers.length = 0; } };
}
