// models/mail/MailRepository — accès à la file de triage. RM2889, L1 (pilote).
//
// Sept routes, nommées dans core/endpoints.js ; aucun DOM. Les gestes du
// script mail (relever, router, rédiger, créer, reclasser, écarter) sont des
// POST dont la réponse porte {ok, stdout, stderr} : le repository la rend
// telle quelle, c'est le service qui en tire un message.

import { Repository } from "../Repository.js";
import { get } from "../../core/api.js";
import { EmailFactory } from "./Email.js";

export class MailRepository extends Repository {
  constructor() {
    super({
      name: "mail", factory: EmailFactory, ttl: 5000, max: 50,
      routes: { list: "mail.queue", fetch: "mail.fetch", route: "mail.route", draft: "mail.draft",
                create: "mail.create", reroute: "mail.route_set", dismiss: "mail.dismiss" },
    });
  }

  /** La file : {emails: [Email], pending: n}. `done` inclut les traités ; `key` déplie un email. */
  async queue({ done = false, key = null } = {}) {
    const qs = "?done=" + (done ? "1" : "0") + (key ? "&key=" + encodeURIComponent(key) : "");
    return this.store.ensure(`queue${qs}`, async () => {
      const d = await get(this.path("list") + qs);
      return { emails: this.factory.many(d.emails || []), pending: d.pending || 0 };
    });
  }
}
