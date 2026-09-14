// models/worklog/WorklogRepository — /worklog/<sid>, /worklog/batch, /mr/batch, /mr/merge, /spawn. RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class WorklogRepository extends Repository {
  constructor() { super({ name: "worklog", ttl: 10000, max: 20, factory: new Factory({ type: "worklog" }), routes: { worklog: "worklog.worklog", batch: "worklog.batch", mrBatch: "worklog.mr.batch", mrMerge: "worklog.mr.merge", request: "worklog.request", anteriority: "worklog.anteriority", spawn: "session.spawn" } }); }
  /** force=1 : contourne la garde de fraîcheur serveur (60 s) pour un ⟳ manuel. */
  load(sid, force) { return get(this.path("worklog") + "/" + encodeURIComponent(sid) + (force ? "?force=1" : "")); }
  batch(body) { return post(this.path("batch"), body); }
  /** RM3114 : solder une demande du registre — l'écriture reste côté outil PM. */
  request(body) { return post(this.path("request"), body); }
  /** RM3148/RM3174 : ce sujet a-t-il déjà un ticket ? L'accès réseau vit ICI, comme tout le reste —
   *  le service porte l'état et la décision, le dépôt parle au serveur. */
  anteriority(q, limit = 6) {
    return get(this.path("anteriority") + "?q=" + encodeURIComponent(q)
               + "&limit=" + encodeURIComponent(limit));
  }
  mrBatch(body) { return post(this.path("mrBatch"), body); }
  mrMerge(url) { return post(this.path("mrMerge"), { url, confirm: true }); }
  spawn(body) { return post(this.path("spawn"), body); }
}
