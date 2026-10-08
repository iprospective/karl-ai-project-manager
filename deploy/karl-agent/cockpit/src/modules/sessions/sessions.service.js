// services/sessions.service — l'état de la liste « en cours » propre à CE navigateur (tri, plis, gel) et les gestes Oui / auto-oui. RM2889.
import { SessionsRepository } from "./SessionsRepository.js";
import { trackUnseen, parseUnseen } from "./unseen.js";                                     // RM3236
import { computeGroups, sessionInClient, sortFrozen, orderSessions, isCollapsed, toggleCollapsed, defaultCollapsed, approveAllMessage, approveMessage, autoYesLeft, filtreGroupes, FILTRES, FILTRE_LABEL } from "./sessions.js";

export class SessionsService {
  constructor({ repo = new SessionsRepository(), storage = null, now = () => Date.now() } = {}) {
    this.repo = repo; this.storage = storage; this.now = now;
    this.dynSort = this._read("karlDynSort") === "1";                                    // RM2344 : stable par défaut
    this.collapsed = defaultCollapsed();                                                    // RM2448/RM2537
    try { const raw = this._read("karlCollapsed"); if (raw !== null && raw !== undefined) this.collapsed = new Set(JSON.parse(raw)); } catch (e) { /* JSON illisible : défaut */ }
    this.hot = false; this.lastMove = 0;                                                    // RM2346 : gel pendant l'interaction
    // RM3236 : les sessions « à voir ». L'ensemble survit au rechargement ; la mémoire des états, non — après un
    // rechargement on ne marque donc rien de neuf avant d'avoir vu une vraie transition working → attente.
    this.prevStates = new Map();
    this.unseen = parseUnseen(this._read("karlUnseen"));
    // RM3302 : le filtre de lecture, propre à CE navigateur et retenu entre deux visites. Une valeur
    // périmée (filtre supprimé depuis) est relue comme « aucun filtre » plutôt que de vider la liste.
    const f = this._read("karlSessFiltre");
    this.filtre = FILTRES.includes(f) ? f : "";
  }
  /** RM3236 : met à jour les sessions à voir depuis un passage du registre ; `watching(rm)` = on la regarde. */
  trackUnseen(sessions, watching) {
    const next = trackUnseen(this.prevStates, this.unseen, sessions, watching);
    const changed = next.size !== this.unseen.size || [...next].some(x => !this.unseen.has(x));
    this.unseen = next;
    if (changed) this._write("karlUnseen", JSON.stringify([...next]));
    return next;
  }
  /** RM3236 : on est allé la voir — le clignotement s'arrête et le compteur descend tout de suite, sans attendre le rafraîchissement. */
  markSeen(rm) {
    if (!this.unseen.delete(String(rm))) return false;
    this._write("karlUnseen", JSON.stringify([...this.unseen]));
    return true;
  }
  _read(k) { try { return this.storage ? this.storage.getItem(k) : null; } catch (e) { return null; } }
  _write(k, v) { try { if (this.storage) this.storage.setItem(k, v); } catch (e) { /* mode privé */ } }
  /** RM3302 : bascule le filtre (même valeur = on l'enlève) ; rend le message à afficher. */
  setFiltre(f) {
    this.filtre = (FILTRES.includes(f) && f !== this.filtre) ? f : "";
    this._write("karlSessFiltre", this.filtre);
    return this.filtre ? "Filtre « " + FILTRE_LABEL[this.filtre] + " » — second clic pour tout revoir"
                       : "Filtre retiré — toutes les sessions";
  }
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
    // RM3302 : le filtre s'applique APRÈS les compteurs — ceux-ci restent globaux, sinon cliquer
    // « à voir » ramènerait tous les autres compteurs à zéro et on ne saurait plus quoi cliquer.
    const fg = filtreGroupes(visKeys, groups, this.filtre, this.unseen);
    const montres = fg.keys.reduce((n, k) => n + fg.groups.get(k).length, 0);
    const total = visKeys.reduce((n, k) => n + groups.get(k).length, 0);
    return { keys, groups, counts, visKeys: fg.keys, groupsVis: fg.groups,
             hidden: keys.length - visKeys.length, filtre: this.filtre, filtres: total - montres,
             ordered: fg.keys.flatMap(k => fg.groups.get(k)) };
  }
  async approve(rm) { const r = await this.repo.approve(rm); return approveMessage(rm, r); }
  async approveAll() { const r = await this.repo.approveAll(); return { n: ((r || {}).approved || []).length, msg: approveAllMessage(r) }; }
  /** RM3249 : compacte la conversation de la session ; rend le message à afficher. */
  async compact(rm) { const r = await this.repo.compact(rm); return "🗜 compaction lancée sur " + rm + " (" + ((r || {}).cmd || "?") + ") — la session reprend avec un résumé"; }
  async autoYes(rm, minutes) { const r = await this.repo.autoYes(rm, minutes); return r.auto_yes_until ? "⏱✔ auto-oui armé pour " + autoYesLeft(r.auto_yes_until) + " — la session répondra Oui seule" : "auto-oui désarmé"; }
}
