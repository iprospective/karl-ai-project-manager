// controllers/terminal.controller — le terminal de la session attachée (RM2522 client maison, repli iframe ttyd, RM2700 cookie de
// gate, RM2807 sonde mémoire opt-in) et le composer (RM2527 : saisie hors clavier du terminal, garde d'état, historique),
// copier / récupérer une copie (RM2168/2631). RM2889.
//
// Hôtes : `host` (#termhost), `frame` (#term), `composer` (#composer : cmpwarn, cmptext, cmphistbtn, cpbtn, bufbtn, cmphint, cmpsend, cmphist).
// Le monolithe prête CFG, le token, la session attachée et son état live, les toasts, la modale texte (capture).
import { mount, paint } from "../../core/dom.js";
import { TerminalService } from "./terminal.service.js";
import { ComposerViewModel } from "./ComposerViewModel.js";
import { ComposerWarn, ComposerHistory } from "./Composer.view.js";
import { termAvailable, termBase, ttydUrl, composerGuard, truncate, sessionCookie, iframeReachable } from "./terminal.js";

export function mountTerminal({ host, frame, composer } = {}, ctx = {}) {
  const svc = ctx.service || new TerminalService({ storage: ctx.storage });
  const notify = ctx.notify || (() => {});
  const win = ctx.win || (typeof window !== "undefined" ? window : {});
  const loc = () => ctx.location || win.location || { port: "", protocol: "http:", hostname: "localhost", origin: "http://localhost" };
  const cfg = () => (ctx.cfg ? ctx.cfg() : null) || {};
  const attached = () => { const a = ctx.attached ? ctx.attached() : null; return a == null ? null : String(a); };
  const sessState = () => { const a = attached(); const s = a && ctx.sess ? ctx.sess().get(a) : null; return s ? s.state : undefined; };
  const q = (sel) => (composer && composer.querySelector ? composer.querySelector(sel) : null);
  const state = { session: null, histPos: -1, draft: "", probe: null };
  const fit = () => { if (state.session && state.session.fit) setTimeout(() => { try { state.session.fit(); } catch (e) { /* démonté */ } }, 0); };

  // ── terminal (RM2522/2700/2807) ───────────────────────────────────────────
  function mountTerm(rmId) {
    const c = cfg(), l = loc();
    // RM2700 : le WebSocket (et l'iframe) ne portent pas X-Karl-Token ; le gate Apache valide un cookie même-origine posé depuis le token d'appareil
    if (c.auth_required && ctx.token && ctx.token()) { try { if (ctx.setCookie) ctx.setCookie(sessionCookie(ctx.token(), l.protocol === "https:")); } catch (e) { /* cookies bloqués : le gate refusera */ } }
    if (!termAvailable(ctx.storage, win)) {                                   // repli : iframe ttyd
      // RM3124 : à distance ce repli ne peut PAS aboutir (port 7681 du bridge LXC).
      // On le dit, plutôt que de laisser le navigateur afficher « impossible de se
      // connecter à …:7681 », qui n'apprend rien à qui le lit.
      if (!iframeReachable(l)) {
        if (host) host.style.display = "none";
        if (frame) { frame.src = "about:blank"; frame.style.display = "none"; }
        notify("Terminal indisponible : le client intégré ne s'est pas chargé, et le repli exige le port 7681 du conteneur, injoignable depuis l'extérieur. Recharge la page (Ctrl+Maj+R) ; si cela persiste, retire `karl_noxterm` du stockage local.", "error");
        composerShow(true); return "unreachable";
      }
      if (host) host.style.display = "none";
      if (frame) { frame.style.display = "block"; frame.src = ttydUrl(c, l, rmId); }
      composerShow(true); return "iframe";
    }
    unmountTerm();
    if (host) host.style.display = "block";
    state.session = win.KarlTerm.attach(host, String(rmId), { base: termBase(c, l) });
    memProbeStart(rmId); composerShow(true); fit(); return "xterm";
  }
  function unmountTerm() {
    memProbeStop();
    if (state.session) { try { state.session.dispose(); } catch (e) { /* déjà fermé */ } state.session = null; }
    if (host) { paint(host, ""); host.style.display = "none"; }
    if (frame) { frame.src = "about:blank"; frame.style.display = "none"; }
    composerShow(false);
  }
  /** RM2807 : sonde mémoire opt-in (`karl_memdebug=1`), toutes les 2 s, best-effort. */
  function memProbeSample(rmId) {
    try {
      const t = state.session && state.session.term, core = (t && t._core) || {}, wb = core._writeBuffer || {}, st = (state.session && state.session.stats) ? state.session.stats() : {};
      svc.memdebug({ rm: String(rmId), dom_all: ctx.domCount ? ctx.domCount() : -1, dom_term: host && host.getElementsByTagName ? host.getElementsByTagName("*").length : -1,
        buf_len: (t && t.buffer && t.buffer.active) ? t.buffer.active.length : -1, wq_len: Array.isArray(wb._writeBuffer) ? wb._writeBuffer.length : -1, wq_bytes: typeof wb._pendingData === "number" ? wb._pendingData : -1,
        heap: (win.performance && win.performance.memory && win.performance.memory.usedJSHeapSize) || -1, writes: st.writes, write_bytes: st.writeBytes, max_write: st.maxWrite, data: st.data, resizes: st.resizes, fits: st.fits, ro_fires: st.roFires, theme_fires: st.themeFires, cols: st.cols, rows: st.rows });
    } catch (e) { /* sonde best-effort */ }
  }
  function memProbeStart(rmId) { let on = false; try { on = !!ctx.storage && ctx.storage.getItem("karl_memdebug") === "1"; } catch (e) { on = false; } if (!on || state.probe) return; state.probe = setInterval(() => memProbeSample(rmId), 2000); }
  function memProbeStop() { if (state.probe) { clearInterval(state.probe); state.probe = null; } }
  // ── composer (RM2527) ─────────────────────────────────────────────────────
  const vm = () => new ComposerViewModel({ state: sessState(), history: svc.history(attached()) });
  function composerShow(on) {
    if (composer) composer.style.display = on ? "flex" : "none";
    if (!on) { const h = q("#cmphist"); if (h) h.style.display = "none"; const ta = q("#cmptext"); if (ta) ta.value = ""; }
    state.histPos = -1; state.draft = "";
    composerRefresh(); fit();                                                    // le terminal cède la hauteur
  }
  /** L'état live de la session → garde + libellés ; appelée à chaque /refresh. */
  function composerRefresh() {
    if (!composer || composer.style.display === "none") return;
    const v = vm(), warn = q("#cmpwarn"), btn = q("#cmpsend"), hint = q("#cmphint");
    if (warn) { warn.style.display = v.warn ? "block" : "none"; paint(warn, ComposerWarn(v)); }
    if (btn) { btn.textContent = v.labels.btn; btn.title = v.labels.title; }
    if (hint) hint.textContent = v.labels.hint;
  }
  /** RM3159 — le prompt de relance : réglable côté serveur, écrit dans le champ, puis envoyé.
   *
   *  Il passe par le champ et par `composerSend` À DESSEIN : la demande reste visible, l'historique
   *  la garde, et les gardes d'envoi (agent occupé, question en attente) s'appliquent comme à toute
   *  frappe. Un bouton qui court-circuiterait tout cela serait un automate — ce n'est pas ce qu'on
   *  veut ici : on écrit une demande, quelqu'un la lit.
   */
  async function relance() {
    const a = attached(); if (!a) { notify("Aucune session attachée", true); return; }
    let texte = "";
    try { texte = await svc.relancePrompt(); }
    catch (e) { notify("Prompt de relance illisible : " + e.message, true); return; }
    if (!texte.trim()) { notify("Prompt de relance vide — à renseigner dans Réglages → Sessions", true); return; }
    const ta = q("#cmptext");
    if (ta) { ta.value = texte; ta.focus(); }
    await composerSend();
  }

  async function composerSend(force) {
    const ta = q("#cmptext"), text = ta ? ta.value : ""; if (!text.trim()) return;
    const a = attached(); if (!a) { notify("Aucune session attachée", true); return; }
    const g = composerGuard(sessState());
    if (!g.allow && !force) { composerRefresh(); notify(g.warn, true); return; }
    const r = await svc.send(state.session, a, text);
    if (!r.ok) { notify(r.message, true); return; }
    svc.remember(a, text);
    if (ta) ta.value = ""; state.histPos = -1; state.draft = "";
    historyRender(); notify("Envoyé : " + truncate(text, 60));
  }
  function historyToggle() { const box = q("#cmphist"); if (!box) return; const on = box.style.display === "none"; box.style.display = on ? "block" : "none"; const b = q("#cmphistbtn"); if (b) b.textContent = on ? "historique ▴" : "historique ▾"; if (on) historyRender(); }
  function historyRender() { const box = q("#cmphist"); if (!box || box.style.display === "none") return; if (histH) histH.update(ComposerHistory(vm())); }
  /** ↑/↓ : seulement dans un champ VIDE (ou déjà en navigation), pour ne pas piéger le curseur pendant la composition. */
  function historyStep(dir) {
    const ta = q("#cmptext"), list = svc.history(attached()); if (!ta || !list.length) return false;
    if (state.histPos === -1) { if (ta.value.trim()) return false; state.draft = ta.value; }
    const next = state.histPos + dir; if (next < -1 || next >= list.length) return true;
    state.histPos = next; ta.value = next === -1 ? state.draft : list[next]; if (ta.setSelectionRange) ta.setSelectionRange(ta.value.length, ta.value.length); return true;
  }
  function composerKey(ev) {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.ctrlKey && !ev.altKey) { ev.preventDefault(); composerSend(); return; }   // la garde décide ; jamais forcé au clavier
    if (ev.key === "Escape") { ev.preventDefault(); if (state.session && state.session.term && state.session.term.focus) state.session.term.focus(); return; }
    if (ev.key === "ArrowUp" && historyStep(1)) { ev.preventDefault(); return; }
    if (ev.key === "ArrowDown" && historyStep(-1)) { ev.preventDefault(); }
  }
  function pick(i) { const ta = q("#cmptext"), list = svc.history(attached()); if (!ta || list[i] == null) return; ta.value = list[i]; if (ta.focus) ta.focus(); if (ta.setSelectionRange) ta.setSelectionRange(ta.value.length, ta.value.length); }
  // ── copier / récupérer (RM2168/2631) : presse-papier, sinon la modale texte pour sélection manuelle ──
  async function writeClip(txt) { if (ctx.clipboard) { try { await ctx.clipboard.writeText(txt); return true; } catch (e) { /* repli */ } } return ctx.copyFallback ? !!ctx.copyFallback(txt) : false; }
  async function copyCapture(showModal) {
    const a = attached(); if (!a) return;
    try { const txt = await svc.capture(a); if (showModal) { ctx.capture && ctx.capture("Capture karl-" + a, txt); return; } if (await writeClip(txt)) notify("📋 Copié — 300 dernières lignes, collables partout (Ctrl+V)"); else if (ctx.capture) ctx.capture("Capture karl-" + a, txt); }
    catch (e) { notify(e.message, true); }
  }
  async function pullBuffer() {
    try { const txt = await svc.buffer(); if (txt === null) { notify("Aucune copie en attente côté tmux — copie d'abord dans le terminal", true); return; } if (await writeClip(txt)) notify("📥 Copie du terminal récupérée — collable partout (Ctrl+V)"); else if (ctx.capture) ctx.capture("Copie tmux", txt); }
    catch (e) { notify(e.message, true); }
  }
  const histEl = q("#cmphist");
  const histH = histEl ? mount(histEl, "", { events: [["click", ".hitem", (e, n) => pick(Number(n.dataset.i))]] }) : null;
  const disposers = [];
  const listen = (el, type, fn) => { if (el && el.addEventListener) { el.addEventListener(type, fn); disposers.push(() => el.removeEventListener(type, fn)); } };
  listen(composer, "keydown", (e) => { if (e.target && e.target.id === "cmptext") composerKey(e); });
  listen(composer, "click", (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (!n) return; const a = n.dataset.action; if (a === "send") composerSend(!composerGuard(sessState()).allow); else if (a === "history") historyToggle(); else if (a === "copy") copyCapture(!!e.altKey); else if (a === "pull") pullBuffer(); else if (a === "relance") relance(); });
  return { mountTerm, unmountTerm, fit, session: () => state.session, composerShow, composerRefresh, composerSend, relance, composerKey, historyToggle, historyStep, copyCapture, pullBuffer, writeClip, state,
    unmount() { unmountTerm(); if (histH) histH.unmount(); disposers.forEach(d => d()); disposers.length = 0; } };
}
