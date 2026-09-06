// modules/memory/MemoryViewModel — ce que le panneau « mémoire » et son bloc de réglages présentent. Inerte. RM3007.
import { INTERVALS, rowsFor, fmtHeap } from "./memory.js";

export class MemoryViewModel {
  /** e = { probe, on, interval } */
  constructor({ probe, on, interval }) { this.probe = probe; this.on = !!on; this.interval = interval || 10; }
  get intervals() { return INTERVALS.map(s => ({ value: s, label: s + " s", selected: s === this.interval })); }
  get rows() { return this.probe ? rowsFor(this.probe) : []; }
  get alerts() { return this.probe ? this.probe.alerts() : []; }
  get samples() { return this.probe ? this.probe.history.length : 0; }
  get latest() { return this.probe ? this.probe.latest : null; }
  get total() { return this.latest ? this.latest.total : null; }
  get heapText() { return this.latest ? fmtHeap(this.latest.heap) : ""; }
  get stateText() { return this.on ? `active — un échantillon toutes les ${this.interval} s, ${this.samples} retenu(s)` : "désactivée — coût nul"; }
  get sinceText() { const h = this.probe ? this.probe.history : []; if (h.length < 2) return ""; const min = Math.round((h[h.length - 1].t - h[0].t) / 60000); return min >= 1 ? `sur ${min} min` : "sur moins d'une minute"; }
}
