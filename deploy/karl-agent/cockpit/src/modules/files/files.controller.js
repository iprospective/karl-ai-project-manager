// controllers/files.controller — l'onglet 📂 fichiers de la colonne de droite (RM2586/2622/2659/2673/2675/2759/2861). RM2889.
//
// Hôtes : `body` (#filesbody), `count` (#filescnt), `nav` (la barre ⟳). L'état (données du contexte, navigation) vit dans le
// service ; le contexte de lecture (session attachée, fiche de ticket, fiche projet, jeu courant) est prêté par le monolithe
// et le routeur, comme le rendu commun d'un fichier (RM2861), la portée d'un worktree et l'ouverture au centre (RM2759).
import { mount } from "../../core/dom.js";
import { html } from "../../core/html.js";
import { FilesService } from "./files.service.js";
import { FilesViewModel, VocabViewModel } from "./FilesViewModel.js";
import { FilesPane } from "./Files.view.js";
import { filesContext, filesCtxKey } from "./explorer.js";

export function mountFiles({ body, count, nav } = {}, ctx = {}) {
  const svc = ctx.service || new FilesService();
  const notify = ctx.notify || (() => {});
  const attached = () => { const a = ctx.attached ? ctx.attached() : null; return a == null ? null : String(a); };
  const context = () => filesContext({ attached: attached(), currentReview: ctx.reviewCurrent ? ctx.reviewCurrent() : null, resolveCache: ctx.resolve ? ctx.resolve() : {}, currentProjectView: ctx.projectKey ? ctx.projectKey() : null, sets: ctx.sets ? ctx.sets() : [], currentSet: ctx.currentSet ? ctx.currentSet() : null });
  const deps = { fileBody: ctx.fileBody || (() => ""), vocab: () => new VocabViewModel({ md: svc.nav.vocabMd, q: svc.nav.vocabQ }) };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const paint = (frag) => { if (bodyH) bodyH.update(frag); };

  function render() {
    const vm = new FilesViewModel({ data: svc.data, nav: svc.nav, attached: attached() }, { scopeTag: ctx.scopeTagOf });
    if (count) count.textContent = vm.count;
    if (vm.nav.vocab && !vm.hasGloss) svc.nav.vocab = false;              // projet sans glossaire : pas d'onglet fantôme
    paint(FilesPane(vm, deps));
    return vm;
  }
  /** RM2673 : (re)charge quand — et seulement quand — le contexte change. */
  function ensure() { if (svc.data.ctxKey !== filesCtxKey(context())) load(); }
  async function load(force) {
    const c = context();
    let r;
    try { r = await svc.load(c, force); }
    catch (e) { paint(html`<div class="empty">${e.message}</div>`); return; }
    if (r.kind === "none") { paint(html`<div class="empty">attache une session, ou ouvre une fiche de ticket ou de projet — les fichiers du projet suivront.</div>`); return; }
    if (r.kind === "empty") { paint(c.kind === "session" ? html`<div class="empty">aucun worktree ni projet pour cette session (rien de branché).</div>` : html`<div class="empty">aucune racine lisible pour ${c.client + "/" + c.project}.</div>`); return; }
    await loadDir(svc.nav.wt, svc.nav.path);
  }
  async function loadDir(wt, path) { const err = await svc.loadDir(attached(), wt, path || ""); if (err) notify(err.message, true); render(); }
  async function open(name) { try { await svc.open(attached(), name); } catch (e) { notify(e.message, true); return; } render(); }
  async function toggleCommits() { await svc.toggleCommits(attached()); render(); }
  async function vocabShow(on) { const err = await svc.vocabShow(attached(), on); if (err) notify(err.message, true); render(); }
  /** La saisie du filtre vit hors du DOM ; le champ re-rendu retrouve son curseur. */
  function vocabFilter(q, el) { svc.nav.vocabQ = String(q || ""); const pos = el && el.selectionStart != null ? el.selectionStart : null; render(); const nb = body && body.querySelector ? body.querySelector("#vocab-q") : null; if (nb && nb.focus) { nb.focus(); if (pos != null && nb.setSelectionRange) nb.setSelectionRange(pos, pos); } }
  /** Plus de session : on oublie ses worktrees ; le prochain dépliage (ou `ensure`) recharge sur le projet courant. */
  function reset() { svc.reset(); paint(html`<div class="empty">chargement au dépliage…</div>`); }
  /** RM2596 : depuis une référence de fichier dans un message → l'onglet, le bon dossier, le fichier s'il existe. */
  async function openRef(path) {
    if (ctx.showRight) ctx.showRight("files");
    await load();
    if (!svc.nav.wt) { notify("Aucun worktree pour naviguer vers « " + path + " »", true); return; }
    const parts = String(path).split("/"); const file = parts.pop(); const dir = parts.join("/");
    await loadDir(svc.nav.wt, dir);
    if (svc.nav.entries.some(e => !e.dir && e.name === file)) await open(file);
    else notify("« " + path + " » introuvable dans " + String(svc.nav.wt || "").split("/").pop() + " — navigue à la main", true);
  }
  const acts = { dir: (n) => loadDir(n.dataset.wt, n.dataset.path), open: (n) => open(n.dataset.name), back: () => loadDir(svc.nav.wt, svc.nav.path), commits: () => toggleCommits(),
    commit: (n) => ctx.center && ctx.center.openCommit(attached(), n.dataset.hash), vocab: (n) => vocabShow(n.dataset.on === "1"),
    "center-file": (n) => ctx.center && ctx.center.openFile("wt", n.dataset.wt, n.dataset.path, n.dataset.tag), "center-dir": (n) => ctx.center && ctx.center.openDir("wt", n.dataset.wt, n.dataset.path, n.dataset.tag), reload: () => load(true) };
  const bodyH = body ? mount(body, '<div class="empty">chargement…</div>', { events: [["click", "[data-action]", (e, n) => { const f = acts[n.dataset.action]; if (f) { e.preventDefault(); e.stopPropagation(); f(n); } }], ["input", "#vocab-q", (e, n) => vocabFilter(n.value, n)]] }) : null;
  const disposers = [];
  if (nav && nav.addEventListener) { const fn = (e) => { const n = e.target && e.target.closest ? e.target.closest("[data-action]") : null; if (n && acts[n.dataset.action]) { e.preventDefault(); acts[n.dataset.action](n); } }; nav.addEventListener("click", fn); disposers.push(() => nav.removeEventListener("click", fn)); }
  return { ensure, load, loadDir, open, toggleCommits, vocabShow, vocabFilter, render, reset, openRef, context, data: () => svc.data, nav: () => svc.nav,
    unmount() { if (bodyH) bodyH.unmount(); disposers.forEach(d => d()); disposers.length = 0; } };
}
