// models/sessions/SetsRepository — /session-sets, /session-set (GET/POST/DELETE) et ses actions, /resume d'une session enregistrée. RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { api, get, post } from "../../core/api.js";

const enc = encodeURIComponent;
export class SetsRepository extends Repository {
  constructor() {
    super({ name: "session-sets", ttl: 1000, max: 1, factory: new Factory({ type: "session_set" }), routes: {
      sets: "session_set.session_sets", set: "session_set.session_set", current: "session_set.current", move: "session_set.move", create: "session_set.create",
      rule: "session_set.rule", materialize: "session_set.materialize", retention: "session_set.retention", rename: "session_set.rename", estimate: "session_set.estimate",
      relaunch: "session_set.relaunch", restart: "session_set.restart", restore: "session_set.restore", history: "session_set.history", resume: "session.resume" } });
  }
  list() { return get(this.path("sets")); }
  get(group) { return get(this.path("set") + "?group=" + enc(group)); }
  /** RM2439 : sélecteur ADDITIF — rien de déjà enregistré n'est retiré. */
  add(group, sids) { return post(this.path("set"), { group, sids }); }
  /** Sans `sid` : efface le jeu entier ; avec : retire l'entrée (RM2427/RM2446). */
  remove(group, sid) { return api(this.path("set") + "?group=" + enc(group) + (sid != null ? "&sid=" + enc(sid) : ""), { method: "DELETE" }); }
  setCurrent(body) { return post(this.path("current"), body); }          // { group } ou { view } (RM2445/RM2446)
  move(body) { return post(this.path("move"), body); }                    // { sids, to, from, copy } (RM2449)
  create(body) { return post(this.path("create"), body); }                // { group, label, sids? | rule?, move_from? }
  rule(group, rule) { return post(this.path("rule"), { group, rule }); }
  materialize(group) { return post(this.path("materialize"), { group }); }
  retention(group, days) { return post(this.path("retention"), { group, days }); }
  rename(group, label) { return post(this.path("rename"), { group, label }); }
  estimate(group) { return get(this.path("estimate") + "?group=" + enc(group)); }   // RM2451
  relaunch(group, spawn) { return post(this.path("relaunch"), { group, spawn }); }
  restart(sid, group, restart) { return post(this.path("restart"), { sid, group, restart }); }
  restore(group, id) { return post(this.path("restore"), { group, id }); }           // RM2443
  history() { return get(this.path("history")); }
  /** RM2536 : la reprise passe par l'IDENTITÉ de la session (engine, session_id), jamais par le jeu qui l'affiche. */
  resume(body) { return post(this.path("resume"), body); }
}
