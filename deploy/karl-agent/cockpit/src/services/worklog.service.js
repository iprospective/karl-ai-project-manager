// services/worklog.service — l'état du worklog de la session attachée, la sélection et les lots. RM2889.
import { WorklogRepository } from "../models/worklog/WorklogRepository.js";
import { batchButtons, closeBatchPlan, offloadPlan, BATCH_MODES, refId, scopeItems } from "../models/worklog/worklog.js";

export class WorklogService {
  constructor({ repo = new WorklogRepository(), run = null } = {}) { this.repo = repo; this._run = run; this.data = { found: false, buckets: {} }; this.pending = null; this.sub = "todo"; this.selection = new Map(); this.points = {}; this.plan = null; this.mrPlan = null; this.closePlanCache = null; }
  /** Une requête à la fois par session ; `rm_id` même en échec, sinon l'onglet tickets redemanderait sans fin (RM2673). */
  async load(sid, force) {
    this.pending = String(sid);
    try { this.data = await this.repo.load(sid, force); }
    catch (e) { this.data = { rm_id: String(sid), found: false, buckets: {}, error: e.message }; }
    this.pending = null; return this.data;
  }
  clear() { this.data = { found: false, buckets: {} }; }
  /** Le composite /refresh pousse un worklog frais (RM2763). */
  setFromRefresh(data) { this.data = data || this.data; }
  // ── sélection (RM2716/2719) ──
  toggle(ref, status, title, on) { ref = String(ref); if (on) { const wp = this.points[ref] || {}; this.selection.set(ref, { rm_id: refId(ref), status, title, points: wp.points || [], points_truncated: !!wp.points_truncated }); } else this.selection.delete(ref); }
  clearSelection() { this.selection.clear(); }
  get selected() { return [...this.selection.values()]; }
  buttons(cfg) { return batchButtons(this.selected, ((this.data && this.data.mrs_pending) || []).map(m => m && m.ref).filter(Boolean), cfg); }
  // ── lots ──
  async planBatch(sid, mode) {
    const m = BATCH_MODES[mode] ? mode : "traiter", cfg = BATCH_MODES[m];
    this.plan = await this.repo.batch({ rm_id: sid, mode: m, items: this.selected.map(it => cfg.points ? it : Object.assign({}, it, { points: [], points_truncated: false })), dry_run: true, allow_large: true });
    this.plan.mode = this.plan.mode || m; return this.plan;
  }
  async sendBatch(sid, boxes) {
    const r = await this.repo.batch({ rm_id: sid, mode: this.plan.mode || "traiter", items: scopeItems(this.selected, boxes), allow_large: this.plan.count > 10 });
    this.clearSelection(); return r;
  }
  async planMr(mode) { this.mrPlan = await this.repo.mrBatch({ mode, items: this.selected.map(it => ({ rm_id: it.rm_id })), dry_run: true, allow_large: true }); this.mrPlan.mode = this.mrPlan.mode || mode; return this.mrPlan; }
  sendMr() { return this.repo.mrBatch({ mode: this.mrPlan.mode, confirm: true, allow_large: true, items: (this.mrPlan.todo || []).map(t => ({ rm_id: t.rm_id })) }); }
  closePlan(cfg) { this.closePlanCache = closeBatchPlan(this.selected, cfg); return this.closePlanCache; }
  /** RM2786 : chaque fermeture passe par pm-task-status-update ; un refus reste ouvert et est rendu avec sa raison. */
  async sendClose(note, onStep) {
    const ok = [], ko = [];
    for (const t of this.closePlanCache.todo) {
      if (onStep) onStep(ok.length + ko.length + 1, this.closePlanCache.count);
      try { const r = await this._run("task-status", { rm_id: t.rm_id, status: "ferme", close_reason: "resolu", note: note || "Testé et validé." }, { confirm: true }); if (r.ok) ok.push(t.rm_id); else ko.push({ rm_id: t.rm_id, why: ((r.stderr || r.stdout || "").trim().split("\n").pop() || "refus") }); }
      catch (e) { ko.push({ rm_id: t.rm_id, why: e.message }); }
    }
    this.clearSelection(); return { ok, ko };
  }
  mergeOne(url) { return this.repo.mrMerge(url); }
  /** RM2823/2831 : le plan d'embarquement, une fois les projets résolus. */
  offload(items, rcache) { return offloadPlan(items, rcache); }
  /** La consigne vient du serveur (dry_run de « ▶ traiter »), la session de /spawn : rien n'est réinventé. */
  async spawnPlan(anchorOrSid, envoyes) { return this.repo.batch({ rm_id: anchorOrSid, mode: "traiter", items: envoyes, dry_run: true, allow_large: true }); }
  spawn(body) { return this.repo.spawn(body); }
}
