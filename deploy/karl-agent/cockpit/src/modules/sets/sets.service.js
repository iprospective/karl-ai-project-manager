// services/sets.service — l'état des jeux de sessions (jeu courant, vue, jeu réglé, formulaire de règle, sélection, préférence de relance) et
// leurs gestes, avec les messages à afficher. Aucun DOM. RM2889.
import { SetsRepository } from "./SetsRepository.js";
import { setLabel, setWritable, slugifySet, newSetPlan, relaunchBtnState, saveSummary, viewMessage, moveSummary, relaunchSummary, spawnWarnings, ghostRelaunchText, restartMessage, retentionMessage, historyFor, sessionLabelOf } from "./sets.js";

export class SetsService {
  constructor({ repo = new SetsRepository(), storage = null } = {}) {
    this.repo = repo; this.storage = storage;
    this.current = this._read("karlSet") || "default";           // RM2442 : jeu COURANT, persisté
    this.view = "set";                                             // RM2446 : set | live | all | sessions | client:<slug>
    this.sets = []; this.facets = { clients: [], marks: [], tags: [] }; this.last = null;
    this.editing = null;                                           // RM2955 : jeu réglé par la carte (null = suit le courant)
    this.ruleFormFor = null;                                       // jeu dont on édite la règle ("__new__" = création)
    this.selMode = false; this.selected = new Set();               // RM2448
    this.spawnPref = this._read("karlSetSpawn") === "1";           // RM2395 : recréer une session neuve si la conversation est perdue
  }
  _read(k) { try { return this.storage ? this.storage.getItem(k) : null; } catch (e) { return null; } }
  _write(k, v) { try { if (this.storage) this.storage.setItem(k, v); } catch (e) { /* mode privé */ } }
  _setCurrent(name) { this.current = name; this._write("karlSet", name); }
  editedSet() { return this.editing || this.current; }
  label(name) { return setLabel(this.sets, name); }
  writable() { return setWritable(this.sets, this.current, this.view); }
  /** GET /session-sets : le serveur fait foi pour le jeu courant (RM2445), la vue et les facettes. Rend le repli si le courant a disparu. */
  async loadSets() {
    const r = await this.repo.list();
    this.sets = r.sets || []; this.last = r;
    if (r.current) this._setCurrent(r.current);
    const fallback = (this.sets.length && !this.sets.some(s => s.name === this.current)) ? this.sets[0].name : null;
    this.view = r.view || "set"; this.facets = r.facets || { clients: [], marks: [], tags: [] };
    return { r, fallback };
  }
  loadSet(group) { return this.repo.get(group || this.editedSet()); }
  async relaunchState() { return relaunchBtnState(await this.repo.get(this.current), this.view); }
  async save(sids) { return saveSummary(await this.repo.add(this.current, sids), this.label(this.current)); }
  async switchSet(name, silent) {
    const prev = this.current; this._setCurrent(name);
    try { await this.repo.setCurrent({ group: name }); this.view = "set"; return silent ? "" : "jeu courant : " + this.label(name); }
    catch (e) { this._setCurrent(prev); throw e; }
  }
  async switchView(view) {
    const prev = this.view; this.view = view;
    try { await this.repo.setCurrent({ view }); return viewMessage(view, this.label(this.current)); }
    catch (e) { this.view = prev; throw e; }
  }
  toggleSelMode() { this.selMode = !this.selMode; if (!this.selMode) this.selected.clear(); return this.selMode; }
  toggleSelected(sid) { this.selected.has(sid) ? this.selected.delete(sid) : this.selected.add(sid); }
  async move(to, move) { const r = await this.repo.move({ sids: [...this.selected], to, from: this.current, copy: !move }); this.selected.clear(); return moveSummary(r.moved, move, this.label(to)); }
  /** RM2741 : création depuis le formulaire — la nature se déduit des critères ; le jeu créé devient courant. */
  async createFromForm({ label, seed, rule }, sids) {
    const plan = newSetPlan(slugifySet(label), label, rule, sids, seed, this.sets.map(s => s.name));
    if (!plan.ok) return plan;
    const r = await this.repo.create(plan.body);
    this._setCurrent(plan.body.group); this.view = "set"; this.ruleFormFor = null;
    return { ok: true, msg: "＋ jeu " + (plan.kind === "derived" ? "dérivé " : "") + "« " + label + " » — " + r.count + " session(s)" + (plan.note ? " · " + plan.note : "") };
  }
  /** La règle s'applique au jeu dont le formulaire est ouvert (le jeu RÉGLÉ, RM2955 — pas forcément le courant). */
  async applyRule(rule) { const r = await this.repo.rule(this.editedSet(), rule); this.ruleFormFor = null; return "règle appliquée — " + r.count + " session(s)"; }
  async materialize() { const r = await this.repo.materialize(this.editedSet()); return "jeu figé — " + r.count + " session(s)"; }
  async retention(days) { await this.repo.retention(this.editedSet(), Number(days) || 0); return retentionMessage(days); }
  /** RM2448/RM2673 : nouveau jeu depuis la sélection ; `split` la retire du jeu courant (jamais proposé sur un dérivé). */
  checkNewName(label) {
    const name = slugifySet(label);
    if (!name) return { ok: false, error: "nom inexploitable — il faut au moins une lettre ou un chiffre" };
    if (this.sets.some(s => s.name === name)) return { ok: false, error: "le jeu « " + name + " » existe déjà" };
    return { ok: true, name };
  }
  async createFromSelection(label, split) {
    const chk = this.checkNewName(label); if (!chk.ok) return chk;
    const name = chk.name;
    const body = { group: name, label, sids: [...this.selected] }; if (split) body.move_from = this.current;
    const r = await this.repo.create(body);
    const msg = "＋ « " + label + " » — " + r.count + " session(s)" + ((r.moved || []).length ? ", retirée(s) de « " + this.label(this.current) + " »" : "");
    this._setCurrent(name); this.view = "set"; this.selMode = false; this.selected.clear();
    return { ok: true, msg };
  }
  warnings(r) { return spawnWarnings(r, (n) => this.label(n)); }
  async rename(label) { await this.repo.rename(this.editedSet(), label); return "jeu renommé : " + label; }
  estimate(group) { return this.repo.estimate(group); }
  async relaunch(group) { return relaunchSummary((await this.repo.relaunch(group, this.spawnPref)).counts); }
  async restart(s) { const next = s.restart === "auto" ? "idle" : "auto"; await this.repo.restart(s.rm_id, s.group || this.current, next); return restartMessage(next, sessionLabelOf(s)); }
  /** RM2427/RM2451 : retire une entrée ; rend le jeton d'annulation s'il y en a un. */
  async forget(s) { const grp = s.group || this.current; const r = await this.repo.remove(grp, s.rm_id); return { grp, label: sessionLabelOf(s), undo: r.undo, count: r.count }; }
  async undo(group, id) { await this.repo.restore(group, id); return "↩ rétabli"; }
  /** RM2446 : retire une session VIVANTE du jeu courant sans la fermer. */
  async drop(s) { const r = await this.repo.remove(this.current, s.rm_id); return { undo: r.undo, msg: "⊖ " + sessionLabelOf(s) + " retirée de « " + this.label(this.current) + " » — elle tourne toujours" }; }
  /** RM2427/2536/2949 : relance RÉELLE d'une session enregistrée par son identité ; neuve si la conversation est perdue. */
  async resumeGhost(s) {
    const g = ghostRelaunchText(s);
    const r = await this.repo.resume({ engine: s.engine || undefined, session_id: s.session_id || undefined, rm_id: s.rm_id, spawn: g.neuve || this.spawnPref });
    return { r, msg: r.spawned ? "▶ " + g.label + " recréée (session neuve)" : "▶ " + g.label + " reprise" };
  }
  async history() { const r = await this.repo.history(); return { versions: historyFor(r.versions, this.editedSet()), keep: r.keep }; }
  async restore(id) { const r = await this.repo.restore(this.editedSet(), id); return "↩ « " + this.label(this.editedSet()) + " » rétabli — " + r.count + " session(s)"; }
  setSpawnPref(on) { this.spawnPref = !!on; this._write("karlSetSpawn", on ? "1" : ""); }
  /** Efface un jeu ; si c'était le jeu réglé, la carte revient au courant (RM2955). */
  async remove(group) { const grp = group || this.editedSet(); await this.repo.remove(grp); const msg = "🗑 jeu « " + this.label(grp) + " » effacé"; if (this.editing === grp) this.editing = null; return msg; }
}
