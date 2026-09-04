// services/mail.service — les gestes de la file de triage. RM2889, L1 (pilote).
//
// Combine le repository un cran au-dessus : chaque geste envoie, invalide,
// et rend un RÉSULTAT lisible {ok, message} — la règle « dernière ligne non
// vide de stdout/stderr, sinon le libellé » vient de mailAction et ne change
// pas. Aucun DOM, aucun balisage : le contrôleur décide quoi en faire.

import { MailRepository } from "../models/mail/MailRepository.js";

export class MailService {
  constructor(repo = new MailRepository()) { this.repo = repo; }

  queue(opts) { return this.repo.queue(opts); }

  /** Un geste serveur : POST, invalidation, message. Ne lève pas — rend {ok:false}. */
  async act(kind, body, label) {
    try {
      const r = await this.repo.send(kind, body || {});
      const last = (r.stdout || r.stderr || "").trim().split("\n").filter(Boolean).pop();
      return { ok: !!r.ok, message: r.ok ? (last || label) : "Échec : " + (last || label) };
    } catch (e) {
      return { ok: false, message: e.message };
    }
  }

  fetch()                 { return this.act("fetch", {}, "Relever"); }
  route()                 { return this.act("route", {}, "Router"); }
  draft(key, fullBody)    { return this.act("draft", { key, full_body: !!fullBody, force: true }, "Rédiger"); }
  create(key, fields)     { return this.act("create", { key, ...fields }, "Créer"); }
  noteOn(key, rm)         { return this.act("create", { key, note_on: String(rm).replace(/\D/g, "") }, "Note"); }
  reroute(key, to)        { return this.act("reroute", { key, to: String(to).trim() }, "Reclasser"); }
  dismiss(key, reason)    { return this.act("dismiss", { key, reason }, "Écarter"); }

  subscribe(fn) { return this.repo.subscribe(fn); }
}
