// controllers/git.controller — l'onglet git : trois gestes. RM2889, L4.
//
// Le contexte prête ce que le monolithe possède encore : la session attachée,
// les branches de son registre, l'ouverture au centre, la notification.

import { mount } from "../core/dom.js";
import { html } from "../core/html.js";
import { GitService } from "../services/git.service.js";
import { GitLogViewModel } from "../viewmodels/git/GitLogViewModel.js";
import { GitPatchViewModel } from "../viewmodels/git/GitPatchViewModel.js";
import { GitPanel, GitPatch, GitDetail } from "../views/git/GitPanel.view.js";

export function mountGitPanel(el, ctx = {}) {
  const svc = ctx.service || new GitService();
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const attached = () => (ctx.attached ? ctx.attached() : null);
  const state = { log: null, sel: null, loading: false, detail: null, sid: null };

  const vm = () => state.log && new GitLogViewModel(state.log, { sel: state.sel, branches: ctx.branchesOf ? ctx.branchesOf(state.sid) : [] });
  const paint = (body) => handle.update(GitPanel({ vm: vm(), detail: state.detail, body }));

  async function refresh(force) {
    const sid = attached();
    if (!sid || state.loading) return;
    state.loading = true; state.sid = sid;
    try { state.log = await svc.log(sid, force); state.detail = null; paint(); }
    catch (e) { paint(html`<div class="empty">${e.message}</div>`); }
    finally { state.loading = false; }
  }
  /** Session changée : on oublie tout, on repeint vide. */
  function reset() { Object.assign(state, { log: null, sel: null, detail: null, sid: null }); paint(); }

  async function show(sha) {
    const sid = attached(); if (!sid) return;
    state.sel = sha; paint();
    try {
      const r = await svc.show(sid, sha);
      state.detail = GitDetail(html`${(r.commit || {}).short || sha} — ${((r.message || "").split("\n")[0]).slice(0, 90)}`, GitPatch(new GitPatchViewModel(r)));
      paint(); if (handle.el.scrollTop !== undefined) handle.el.scrollTop = 0;
    } catch (e) { notify(e.message, true); }
  }
  async function diff(mode) {
    const sid = attached(); if (!sid) { notify("Aucune session attachée"); return; }
    try {
      const r = await svc.diff(sid, mode);
      const titre = mode === "worktree" ? "Travail non commité" : "Ce que la branche apporte à " + (r.base || "?");
      paint(GitDetail(html`${titre}`, !new GitPatchViewModel(r).empty ? GitPatch(new GitPatchViewModel(r)) : html`<div class="empty">aucune différence</div>`));
    } catch (e) { notify(e.message, true); }
  }

  const gestures = {
    refresh: () => refresh(true), "diff-branch": () => diff("branch"), "diff-worktree": () => diff("worktree"),
    close: () => refresh(true), show: (sha) => show(sha),
    center: (sha) => ctx.openCenter && ctx.openCenter(state.sid, sha),
  };
  const handle = mount(el, "", { events: [["click", "[data-action]", (ev, btn) => {
    const g = gestures[btn.dataset.action]; if (!g) return;
    if (btn.dataset.action === "center" && ev.stopPropagation) ev.stopPropagation();
    return g(btn.dataset.sha);
  }]] });
  paint();
  return Object.assign(handle, { refresh, reset, state });
}
