// controllers/doc.controller — la modale doc (#docmodal) : document du projet rendu (RM2309), aide intégrée
// (RM2593), glossaire du jargon (RM2623/2634), envoi au centre (RM2759) ; et les termes soulignés (.gloss)
// partout dans la page, par délégation. RM2889.
//
// Le monolithe (plans de lot du worklog) écrit encore lui-même dans #doctitle/#doccontent et pose la classe
// `show` : la modale reste son hôte, il la referme par le pont closeDoc.
import { html, raw } from "../../core/html.js";
import { mdToHtml } from "../../core/markdown.js";
import { HelpService } from "./help.service.js";
import { GlossaryViewModel, HelpViewModel } from "./GlossaryViewModel.js";
import { GlossaryPanel, GlossaryList, HelpPage } from "./Doc.view.js";
import { glossify, glossNorm } from "./glossary.js";
import { paint as paintInto } from "../../core/dom.js";

export function mountDocModal(el, ctx = {}) {
  const svc = ctx.service || new HelpService();
  const q = (sel) => (el && el.querySelector ? el.querySelector(sel) : null);
  const state = { current: null, mode: null, help: null, custom: null };   // current : { path, name } d'un document (RM2759) ; custom : écran prêté (lots)
  const title = (t) => { const n = q("#doctitle"); if (n) n.textContent = t; };
  const content = () => q("#doccontent");
  const toCenterBtn = (on) => { const b = q("#doc2center"); if (b) b.style.display = on ? "" : "none"; };
  const show = (on) => { if (el && el.classList) el.classList.toggle("show", !!on); };
  const paint = (frag, mode) => { const c = content(); if (!c) return; c.className = ""; paintInto(c, frag); state.mode = mode; };
  /** Un écran prêté (récapitulatif de lot du worklog…) : titre, contenu, et ses gestes routés à `onAction(action, node, ev)`. */
  function openCustom(title_, frag, onAction) { state.current = null; toCenterBtn(false); title(title_); paint(frag, "custom"); state.custom = onAction || null; show(true); }
  const contentEl = () => content();
  /** RM2309 : captures et sorties de scripts = texte brut mono, jamais rendues — « sélectionne puis Ctrl+C ». */
  function openPlain(title_, txt) { state.current = null; state.custom = null; toCenterBtn(false); title(title_ + " — sélectionne puis Ctrl+C"); const c = content(); if (c) { c.className = "plain"; c.textContent = String(txt == null ? "" : txt); } state.mode = "plain"; show(true); }

  function closeDoc() { show(false); }
  function docToCenter() { if (!state.current) return; const d = state.current; closeDoc(); if (ctx.openCenterFile) ctx.openCenterFile("doc", "", d.path); }
  async function openDoc(path, name) {
    state.current = { path, name }; toCenterBtn(true); title(name);
    paint(html`chargement…`, "doc"); show(true);
    try { const text = await svc.doc(path); if (state.current && state.current.path === path) paint(raw(mdToHtml(text)), "doc"); }   // RM2309 : les .md sont rendus, tout est échappé avant
    catch (e) { paint(html`erreur : ${e.message}`, "doc"); }
  }
  async function openHelp(topic) {
    state.current = null; toCenterBtn(false); title("❓ Aide");
    paint(html`chargement…`, "help"); show(true);
    try { const page = await svc.page(topic); state.help = new HelpViewModel(page); paint(HelpPage(state.help, { md: mdToHtml }), "help"); }
    catch (e) { paint(html`erreur : ${e.message}`, "help"); }
  }
  function renderGlossary(query, focus) {
    const vm = new GlossaryViewModel({ query, focus });
    const list = q("#glosslist"), cnt = q("#glosscount");
    if (list) paintInto(list, GlossaryList(vm)); if (cnt) cnt.textContent = vm.count;
    if (focus && list && list.querySelector) { const row = list.querySelector(".glossrow.glosshi"); if (row && row.scrollIntoView) row.scrollIntoView({ block: "center" }); }
    return vm;
  }
  function openGlossary(term) {
    state.current = null; toCenterBtn(false); title("📖 Glossaire du jargon");
    const focus = (term && glossNorm(term)) ? term : null;
    paint(GlossaryPanel(new GlossaryViewModel({ query: "", focus })), "glossary"); show(true);
    renderGlossary("", focus);
    if (!focus) { const s = q("#glosssearch"); if (s && s.focus) { try { s.focus(); } catch (e) { /* hors DOM */ } } }
  }

  // ── câblage ──────────────────────────────────────────────────────────────
  const disposers = [];
  const listen = (node, type, fn) => { if (node && node.addEventListener) { node.addEventListener(type, fn); disposers.push(() => node.removeEventListener(type, fn)); } };
  listen(el, "click", (e) => {
    if (e.target === el) { closeDoc(); return; }                                  // clic sur le voile
    const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null;
    if (n) { const a = n.dataset.action; if (a === "close") closeDoc(); else if (a === "to-center") docToCenter(); else if (a === "help") openHelp(n.dataset.topic); else if (state.mode === "custom" && state.custom) state.custom(a, n, e); return; }
    // liens markdown internes de l'aide (href = id de topic) → navigation d'aide interne
    const a = e.target && e.target.closest ? e.target.closest(".helpbody a[href]") : null;
    if (a && state.help && state.help.isTopic(a.getAttribute("href"))) { e.preventDefault(); openHelp(a.getAttribute("href")); }
  });
  listen(el, "input", (e) => { const t = e.target; if (t && t.id === "glosssearch") renderGlossary(t.value, null); });
  // RM2623 : un terme souligné (.gloss), où qu'il soit dans la page → le glossaire ouvert dessus
  listen(ctx.root, "click", (e) => { const t = e.target; const g = t && t.closest ? t.closest(".gloss") : null; if (g) { e.preventDefault(); e.stopPropagation(); openGlossary(g.getAttribute("data-term")); } });

  return { openDoc, closeDoc, openHelp, openGlossary, docToCenter, renderGlossary, openCustom, openPlain, contentEl, md: mdToHtml, glossify: (s) => glossify(s), current: () => state.current, mode: () => state.mode, state,
    unmount() { disposers.forEach(d => d()); disposers.length = 0; } };
}
