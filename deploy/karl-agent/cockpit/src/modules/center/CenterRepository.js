// models/center/CenterRepository — ce que les vues centrales lisent. RM2889, cluster centre.
// Deux sources de fichiers : `doc` (document PM servi par /file) et `wt` (fichier
// d'un worktree servi par /fs/file, sous portée). Le commit vient du dépôt git,
// l'email de la file de triage, la fiche client et la conf du serveur.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, raw } from "../../core/api.js";
import { routeFor } from "../../core/endpoints.js";
import { fsQuery } from "../files/scope.js";
import { GitRepository } from "../git/GitRepository.js";
import { MailRepository } from "../mail/MailRepository.js";
const enc = encodeURIComponent;

export class CenterRepository extends Repository {
  constructor({ git = new GitRepository(), mail = new MailRepository() } = {}) {
    super({ name: "center", ttl: 3000, max: 20, factory: new Factory({ type: "center-view" }),
            routes: { doc: routeFor("/file"), fsFile: routeFor("/fs/file"), fsLs: routeFor("/fs/ls"), client: "project.client", conf: "project.conf",
                     contacts: "project.contacts", contact: "project.contact" } });
    this.git = git; this.mail = mail;
  }
  /** RM3131 — la page de gestion des tickets, servie par l'index (pas par un scan). */
  manage({ status, project, q, limit } = {}) {
    const p = new URLSearchParams();
    if (status) p.set("status", status);
    if (project) p.set("project", project);
    if (q) p.set("q", q);
    if (limit) p.set("limit", String(limit));
    return get("/tickets/manage" + (p.toString() ? "?" + p : ""));
  }

  /** Un document PM, en texte ; lève « erreur <status> » comme avant. */
  async docFile(path) { const r = await raw(this.path("doc") + "?path=" + enc(path)); return r.text(); }
  fsFile(wt, tag, path, ctx) { return get(this.path("fsFile") + "?" + fsQuery(wt, tag, ctx) + "&path=" + enc(path)); }
  fsLs(wt, tag, path, ctx)   { return get(this.path("fsLs") + "?" + fsQuery(wt, tag, ctx) + "&path=" + enc(path || "")); }
  commit(sid, sha)           { return this.git.show(sid, sha); }
  async email(key) {
    const r = await this.mail.queue({ key });
    const e = (r.emails || []).find(x => x && x.key === key) || (r.emails || [])[0];
    if (!e) throw new Error("email absent de la file");
    return e;
  }
  client(client) { return get(this.path("client") + "/" + enc(client)); }
  /** RM3024 — l'annuaire, cherchable par nom comme par n'importe quelle adresse. */
  contacts(q) { return get(this.path("contacts") + (q ? "?q=" + enc(q) : "")); }
  contact(ref) { return get(this.path("contact") + "/" + enc(ref)); }
  conf(scope, client, project) { return get(this.path("conf") + "?scope=" + enc(scope) + "&client=" + enc(client) + "&project=" + enc(project || "")); }
}
