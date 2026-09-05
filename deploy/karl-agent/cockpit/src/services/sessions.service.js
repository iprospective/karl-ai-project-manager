// services/sessions.service — l'état de la liste « en cours » propre à CE navigateur (tri, plis, gel) et les gestes Oui / auto-oui. RM2889.
import { SessionsRepository } from "../models/sessions/SessionsRepository.js";
import { computeGroups, sessionInClient, sortFrozen, orderSessions, isCollapsed, toggleCollapsed, defaultCollapsed, approveAllMessage, approveMessage, autoYesLeft } from "../models/sessions/sessions.js";

export class SessionsService {
  constructor({ repo = new SessionsRepository(), storage = null, now = () => Date.now() } = {}) {
    this.repo = repo; this.storage = storage; this.now = now;
    this.dynSort = this._read("karlDynSort") === "1";                                    // RM2344 : stable par défaut
    this.collapsed = defaultCollapsed();                                                    // RM2448/RM2537
    try { const raw = this._read("karlCollapsed"); if (raw !== null && raw !== undefined) this.collapsed = new Set(JSON.parse(raw)); } catch (e) { /* JSON illisible : défaut */ }
    this.hot = false; this.lastMove = 0;                                                    // RM2346 : gel pendant l'interaction
  }
  _read(k) { try { return this.storage ? this.storage.getItem(k) : null; } catch (e) { return null; } }
  _write(k, v) { try { if (this.storage) this.storage.setItem(k, v); } catch (e) { /* mode privé */ } }
  /** RM2344 : préférence de tri ; rend le message à afficher. */
  setDynSort(on) { this.dynSort = !!on; this._write("karlDynSort", this.dynSort ? "1" : "0"); return this.dynSort ? "Tri dynamique activé (⚠ et activité en tête)" : "Ordre stable (alphabétique) — rien ne bouge"; }
  enter() { this.hot = true; } leave() { this.hot = false; } moved() { this.lastMove = this.now(); }
  frozen() { return sortFrozen(this.dynSort, this.hot, this.now() - this.lastMove); }
  isCollapsed(key) { return isCollapsed(this.collapsed, key); }
  toggleGroup(key) { toggleCollapsed(this.collapsed, key); this._write("karlCollapsed", JSON.stringify([...this.collapsed])); }
  /** Ce que la liste affiche : ordre RM2515, groupes, compteurs, groupes visibles dans le contexte client (RM2639), sessions à plat (RM2302). */
  compute(sessions, rcache, clientContext) {
    orderSessions(sessions);
    const { keys, groups, counts } = computeGroups(sessions, rcache, this.dynSort && !this.frozen());
    const visKeys = clientContext ? keys.filter(k => groups.get(k).some(s => sessionInClient(s, rcache[s.rm_id], clientContext))) : keys;
    return { keys, groups, counts, visKeys, hidden: keys.length - visKeys.length, ordered: keys.flatMap(k => groups.get(k)) };
  }
  async approve(rm) { const r = await this.repo.approve(rm); return approveMessage(rm, r); }
  async approveAll() { const r = await this.repo.approveAll(); return { n: ((r || {}).approved || []).length, msg: approveAllMessage(r) }; }
  async autoYes(rm, minutes) { const r = await this.repo.autoYes(rm, minutes); return r.auto_yes_until ? "⏱✔ auto-oui armé pour " + autoYesLeft(r.auto_yes_until) + " — la session répondra Oui seule" : "auto-oui désarmé"; }
}
