// controllers/sets.controller — les JEUX de sessions : la barre du panneau « en cours » (sélecteur vues/jeux RM2446/2452, ＋ jeu RM2741,
// 🗑, sélection RM2448, déplacement RM2449, 💾 RM2439, ▶ relancer RM2451/2741) et la carte « Sessions enregistrées » (RM2395/2427/2443/2450/
// 2452/2673/2955 : règle, entrées ⟳/⏸/⊖, rétention, préférence de relance, versions, effacement), plus les gestes prêtés à la liste (⊖ d'une
// vivante, relance/retrait/politique d'une tuile grise) et les avertissements de lancement (RM2450/2951). RM2889.
//
// Hôtes : `bar` (#setbar : #set-picker, #btn-set-save, #btn-set-del, #btn-sel, #sel-target, #btn-sel-move, #btn-relaunch, ＋ jeu) et `card`
// (#sessions-set-card : #set-edit-picker, ＋ jeu, #sessions-set-body). Le monolithe prête le toast (simple et avec action), confirm/prompt,
// l'attache et le rafraîchissement de la liste ; la liste migrée prête les sessions AFFICHÉES (ordered).
import { SetsService } from "../services/sets.service.js";
import { SetCardViewModel, HistoryViewModel } from "../viewmodels/sessions/SetsViewModel.js";
import { PickerOptions, TargetOptions, EditPickerOptions, SetCard, History, Loading, ErrorBox } from "../views/sessions/Sets.view.js";
import { setEditOptions, pickerGroups, barState, selButtonState, setWritable, ruleFromValues, moveConfirmText, relaunchConfirmText, ghostRelaunchText, materializeConfirmText, splitConfirmText, restoreConfirmText, deleteConfirmText } from "../models/sessions/sets.js";

export function mountSets({ bar, card } = {}, ctx = {}) {
  const svc = ctx.service || new SetsService({ storage: ctx.storage });
  const notify = ctx.notify || (() => {});
  const notifyAction = ctx.notifyAction || ((m) => notify(m));
  const confirm = ctx.confirm || ((m) => window.confirm(m));
  const prompt = ctx.prompt || ((m, d) => window.prompt(m, d));
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const ordered = () => (ctx.ordered ? ctx.ordered() : []) || [];
  const refreshSessions = () => { if (ctx.refreshSessions) ctx.refreshSessions(); };
  const q = (root, sel) => (root && root.querySelector ? root.querySelector(sel) : null);
  const el = { picker: () => q(bar, "#set-picker"), save: () => q(bar, "#btn-set-save"), del: () => q(bar, "#btn-set-del"), sel: () => q(bar, "#btn-sel"), target: () => q(bar, "#sel-target"), move: () => q(bar, "#btn-sel-move"), relaunchBtn: () => q(bar, "#btn-relaunch"),
    editPicker: () => q(card, "#set-edit-picker"), body: () => q(card, "#sessions-set-body"), history: () => q(card, "#set-history") };
  const show = (n, on) => { if (n) n.style.display = on ? "" : "none"; };
  const fail = (e) => notify(e.message, true);

  // ── barre « en cours » ──
  /** RM2741 : « ▶ relancer » — visible en vue du jeu seulement, compte les éteintes. */
  async function refreshSet() {
    const btn = el.relaunchBtn(); if (!btn) return;
    try { const st = await svc.relaunchState(); btn.textContent = "▶ relancer (" + st.count + ")"; show(btn, st.show); }
    catch (e) { show(btn, false); }
  }
  /** RM2442/2445/2446/2452 : la liste des jeux → sélecteur (vues, clients, jeux) et boutons de la barre. */
  async function refreshSets() {
    const sel = el.picker();
    try {
      const { r, fallback } = await svc.loadSets();
      if (fallback) switchSet(fallback, true);                                   // le jeu courant a pu être effacé ailleurs
      if (sel) { sel.innerHTML = String(PickerOptions(pickerGroups(r, svc.sets, svc.current, svc.view))); show(sel, true); }
      paintBar();
      refreshSet();                                                              // RM2741 : la VUE vient d'être relue
    } catch (e) { svc.sets = []; show(sel, false); }
  }
  function paintBar() {
    const st = barState({ sets: svc.sets, current: svc.current, view: svc.view, selMode: svc.selMode, selectedCount: svc.selected.size });
    const save = el.save(); if (save) { show(save, st.saveShown); save.textContent = st.saveLabel; save.title = st.saveTitle; }
    const del = el.del(); if (del) del.title = st.delTitle;
    const tgt = el.target(); if (tgt) { tgt.innerHTML = String(TargetOptions(st.targets)); show(tgt, st.canMove); }
    show(el.move(), st.canMove);
    paintSelBtn();
  }
  function paintSelBtn() { const b = el.sel(); if (!b) return; const s = selButtonState(svc.selMode); b.textContent = s.text; b.title = s.title; if (b.classList) b.classList.toggle("active", svc.selMode); }
  const all = async () => { refreshSessions(); await refreshSets(); refreshSet(); load(); };
  /** RM2439 : « j'enregistre ce que je vois » — les sid affichés, fantômes compris. */
  async function save(btn) {
    if (btn) btn.disabled = true;
    try { notify(await svc.save(ordered().map(s => s.rm_id))); refreshSets(); refreshSet(); load(); } catch (e) { fail(e); }
    finally { if (btn) btn.disabled = false; }
  }
  async function switchSet(name, silent) { try { const m = await svc.switchSet(name, silent); if (m) notify(m); } catch (e) { fail(e); return; } all(); }
  async function switchView(view) { try { notify(await svc.switchView(view)); } catch (e) { fail(e); return; } all(); }
  function onSetPick(v) { if (!v) return; if (v.startsWith("view:")) switchView(v.slice(5)); else switchSet(v.slice(4)); }
  function toggleSelMode() { svc.toggleSelMode(); paintSelBtn(); refreshSets(); refreshSessions(); }   // le bouton d'écriture change de rôle
  async function moveSelection() {
    const tgt = el.target(), to = tgt && tgt.value;
    if (!to) { notify("aucun jeu de destination", true); return; }
    if (!svc.selected.size) { notify("aucune session sélectionnée", true); return; }
    const move = confirm(moveConfirmText(svc.selected.size, svc.label(to), svc.label(svc.current)));
    try { notify(await svc.move(to, move)); refreshSessions(); await refreshSets(); refreshSet(); load(); } catch (e) { fail(e); }
  }
  // ── carte « Sessions enregistrées » ──
  function paintEditPicker() { const sel = el.editPicker(); if (!sel) return; const opts = setEditOptions(svc.sets, svc.editing, svc.current); sel.innerHTML = String(EditPickerOptions(opts)); show(sel, opts.length); }
  async function load() {
    const body = el.body(); if (!body) return;
    try {
      paintEditPicker();                                                         // RM2955 : de quel jeu parle cette carte
      const r = await svc.loadSet();
      body.innerHTML = String(SetCard(new SetCardViewModel({ r, edited: svc.editedSet(), current: svc.current, sets: svc.sets, ruleFormFor: svc.ruleFormFor, facets: svc.facets, shownCount: ordered().length, spawnPref: svc.spawnPref })));
    } catch (e) { body.innerHTML = String(ErrorBox(e.message)); }
  }
  function setEditPick(name) { svc.editing = name || null; svc.ruleFormFor = null; load(); }   // ne bascule PAS le jeu courant (RM2446)
  function openRuleForm(group) { svc.ruleFormFor = group; load(); }
  function closeRuleForm() { svc.ruleFormFor = null; load(); }
  function readForm() {
    const g = (id) => { const n = q(card, "#" + id); return n ? String(n.value || "") : ""; };
    return { values: { client: g("rf-client"), project: g("rf-project"), mark: g("rf-mark"), tag: g("rf-tag"), tickets: g("rf-tickets") }, label: g("rf-name").trim(), seed: (q(card, "#rf-seed") || {}).checked === true };
  }
  /** RM2741 : règle vide = refus à l'ÉDITION, jeu manuel à la CRÉATION. */
  async function applyRuleForm(isNew) {
    const f = readForm(), rule = ruleFromValues(f.values);
    if (!isNew && !Object.keys(rule).length) { notify("règle vide : elle désignerait toutes les sessions", true); return; }
    try {
      if (isNew) { const res = await svc.createFromForm({ label: f.label, seed: f.seed, rule }, ordered().map(s => s.rm_id)); if (!res.ok) { notify(res.error, true); return; } notify(res.msg); }
      else notify(await svc.applyRule(rule));
      refreshSessions(); await refreshSets(); refreshSet(); load();
    } catch (e) { fail(e); }
  }
  async function materialize() { if (!confirm(materializeConfirmText(svc.label(svc.editedSet())))) return; try { notify(await svc.materialize()); await refreshSets(); refreshSet(); load(); } catch (e) { fail(e); } }
  async function setRetention(days) { try { notify(await svc.retention(days)); refreshSessions(); load(); } catch (e) { fail(e); } }
  /** RM2448/RM2673 : « ＋ jeu (n) » — nouveau jeu depuis la sélection ; la scission n'est proposée que si le jeu courant s'écrit. */
  async function createFromSelection() {
    if (!svc.selected.size) { notify("aucune session sélectionnée", true); return; }
    const label = (prompt("Nom du nouveau jeu (" + svc.selected.size + " session(s) retenue(s)) :") || "").trim();
    if (!label) return;
    const chk = svc.checkNewName(label); if (!chk.ok) { notify(chk.error, true); return; }
    const split = svc.writable() && confirm(splitConfirmText(svc.label(svc.current)));
    try { const res = await svc.createFromSelection(label, split); if (!res.ok) { notify(res.error, true); return; } notify(res.msg); paintSelBtn(); refreshSessions(); await refreshSets(); refreshSet(); load(); } catch (e) { fail(e); }
  }
  /** RM2450/RM2951 : point de passage unique de ce qu'un lancement doit signaler. */
  function warnSpawn(r) { svc.warnings(r).forEach(m => notify(m, true)); }
  async function rename() { const label = (prompt("Nouveau libellé du jeu :", svc.label(svc.editedSet())) || "").trim(); if (!label) return; try { notify(await svc.rename(label)); await refreshSets(); load(); } catch (e) { fail(e); } }
  /** RM2451/RM2955 : relance du jeu COURANT (barre) ou RÉGLÉ (carte) — le prix est dit avant. */
  async function relaunch(btn, fromCard) {
    const grp = fromCard ? svc.editedSet() : svc.current;
    try {
      const e = await svc.estimate(grp);
      if (!e.relaunchable) { notify("rien à relancer dans « " + svc.label(grp) + " »"); return; }
      if (!confirm(relaunchConfirmText(e, svc.label(grp)))) return;
    } catch (err) { /* estimation indisponible : on n'empêche pas le geste */ }
    if (btn) btn.disabled = true;
    try { const s = await svc.relaunch(grp); notify(s.msg, s.failed); later(() => { refreshSessions(); load(); }, 1200); } catch (e) { fail(e); }
    finally { if (btn) btn.disabled = false; }
  }
  async function toggleRestart(s) { try { notify(await svc.restart(s)); refreshSessions(); load(); } catch (e) { fail(e); } }
  /** RM2427/RM2451 : retire une entrée, et propose d'annuler (RM2443). */
  async function forgetGhost(s) {
    try {
      const f = await svc.forget(s); refreshSessions(); refreshSet(); load();
      if (f.undo) notifyAction("⊖ " + f.label + " retirée de « " + svc.label(f.grp) + " »", "annuler", () => undo(f.grp, f.undo));
      else notify("⊖ " + f.label + " retirée (" + f.count + " restante(s))");
    } catch (e) { fail(e); }
  }
  async function undo(group, id) { try { notify(await svc.undo(group, id)); refreshSessions(); refreshSets(); refreshSet(); load(); } catch (e) { fail(e); } }
  /** RM2446 : ⊖ d'une vivante — sort du jeu, ne ferme rien. */
  async function dropFromSet(s) {
    try { const d = await svc.drop(s); refreshSessions(); refreshSets(); refreshSet(); load(); if (d.undo) notifyAction(d.msg, "annuler", () => undo(svc.current, d.undo)); else notify(d.msg); } catch (e) { fail(e); }
  }
  /** RM2427/2536/2949 : relance d'UNE session enregistrée (clic sur sa tuile grise). */
  async function relaunchGhost(s) {
    const g = ghostRelaunchText(s);
    if (!confirm(g.text)) return;
    notify(g.start);
    try { const res = await svc.resumeGhost(s); notify(res.msg); warnSpawn(res.r); later(() => { refreshSessions(); if (ctx.attach) ctx.attach(s.rm_id); }, 1200); }
    catch (e) { notify("relance impossible : " + e.message, true); }
  }
  async function toggleHistory() {
    const h = el.history(); if (!h) return;
    if (h.innerHTML) { h.innerHTML = ""; return; }                              // second clic : on replie
    h.innerHTML = String(Loading());
    try { const r = await svc.history(); h.innerHTML = String(History(new HistoryViewModel({ versions: r.versions, keep: r.keep, label: svc.label(svc.editedSet()) }))); }
    catch (e) { h.innerHTML = String(ErrorBox(e.message)); }
  }
  async function restore(id) {
    if (!confirm(restoreConfirmText(svc.label(svc.editedSet())))) return;
    try { notify(await svc.restore(id)); const h = el.history(); if (h) h.innerHTML = ""; refreshSessions(); await refreshSets(); refreshSet(); load(); } catch (e) { fail(e); }
  }
  function setSpawnPref(on) { svc.setSpawnPref(on); }
  /** 🗑 : la barre efface le jeu COURANT, la carte le jeu RÉGLÉ (RM2955 : deux notions). */
  async function deleteSet(btn, fromCard) {
    const grp = fromCard ? svc.editedSet() : svc.current;
    if (!confirm(deleteConfirmText(svc.label(grp)))) return;
    if (btn) btn.disabled = true;
    try { notify(await svc.remove(grp)); await refreshSets(); refreshSet(); load(); } catch (e) { fail(e); }
    finally { if (btn) btn.disabled = false; }
  }
  const entry = (n) => ({ rm_id: n.dataset.sid, is_ticket: /^\d+$/.test(n.dataset.sid), restart: n.dataset.restart, group: svc.editedSet() });
  // ── écouteurs (délégation ; un unmount les retire) ──
  const disposers = [];
  const listen = (node, type, fn) => { if (node && node.addEventListener) { node.addEventListener(type, fn); disposers.push(() => node.removeEventListener(type, fn)); } };
  const act = (e) => (e.target && e.target.closest ? e.target.closest("[data-action]") : null);
  listen(bar, "click", (e) => { const n = act(e); if (!n) return; const a = n.dataset.action;
    if (a === "new-set") openRuleForm("__new__"); else if (a === "delete") deleteSet(n, false); else if (a === "sel") toggleSelMode(); else if (a === "move") moveSelection();
    else if (a === "save") (svc.selMode ? createFromSelection() : save(n)); else if (a === "relaunch") relaunch(n, false); });
  listen(bar, "change", (e) => { if (e.target && e.target.id === "set-picker") onSetPick(e.target.value); });
  listen(card, "click", (e) => { const n = act(e); if (!n) return; const a = n.dataset.action;
    if (a === "new-set") openRuleForm("__new__"); else if (a === "rule-apply") applyRuleForm(n.dataset.new === "1"); else if (a === "rule-cancel") closeRuleForm(); else if (a === "rule-edit") openRuleForm(svc.editedSet());
    else if (a === "materialize") materialize(); else if (a === "rename") rename(); else if (a === "entry-forget") forgetGhost(entry(n)); else if (a === "entry-restart") toggleRestart(entry(n));
    else if (a === "relaunch-card") relaunch(n, true); else if (a === "history") toggleHistory(); else if (a === "delete") deleteSet(n, true); else if (a === "restore") restore(n.dataset.id); });
  listen(card, "change", (e) => { const t = e.target; if (!t) return; if (t.id === "set-edit-picker") setEditPick(t.value); else if (t.dataset && t.dataset.action === "retention") setRetention(t.value); else if (t.dataset && t.dataset.action === "spawn-pref") setSpawnPref(t.checked); });
  return { refreshSets, refreshSet, load, switchSet, switchView, onSetPick, toggleSelMode, moveSelection, openRuleForm, closeRuleForm, applyRuleForm, materialize, setRetention, createFromSelection, warnSpawn, rename, relaunch, toggleRestart, forgetGhost, undo, dropFromSet, relaunchGhost, toggleHistory, restore, setSpawnPref, deleteSet, setEditPick,
    sets: () => svc.sets, current: () => svc.current, view: () => svc.view, editedSet: () => svc.editedSet(), label: (n) => svc.label(n), writable: setWritable, selection: () => ({ on: svc.selMode, set: svc.selected }), spawnPref: () => svc.spawnPref, svc,
    unmount() { disposers.forEach(d => d()); disposers.length = 0; } };
}
