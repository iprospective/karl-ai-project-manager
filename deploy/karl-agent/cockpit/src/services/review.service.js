// services/review.service — verdicts, statuts, lancement : les gestes de la revue. RM2889.
// Les gardes NORMS (checklist non cochée, merge gate RM2319) sont franchies EXPLICITEMENT :
// on montre le motif et on demande (`ask`, injecté) — jamais d'office, jamais avalées.
import { VERDICTS, gateKind } from "../models/tickets/ticketStatus.js";
import { ticketBusySessions } from "../models/tickets/ticketFormat.js";

export class ReviewService {
  constructor({ repo, run, eff } = {}) { this.repo = repo; this._run = run; this.eff = eff; }
  /** task-status en franchissant les gardes avec l'accord de l'opérateur. Rend le résultat du runner. */
  async runGated(rm, args, target, ask, notify) {
    let r = await this._run("task-status", args, { confirm: true });
    const out = () => (r.stdout || "") + (r.stderr || "");
    if (!r.ok && gateKind(out()) === "checklist") {
      if (ask("RM" + rm + " : des items de checklist ne sont pas cochés dans la description.\nForcer quand même " + target + " (items hors périmètre / différés) ?")) {
        args.allow_unchecked = true; r = await this._run("task-status", args, { confirm: true });
      }
    }
    if (!r.ok && gateKind(out()) === "merge") {
      if (ask("RM" + rm + " : la branche du ticket n'est pas mergée dans dev.\nLivrer maintenant (MR + merge dans dev) puis passer " + target + " ?")) {
        if (notify) notify("RM" + rm + " : livraison (MR + merge)…");
        const d = await this.repo.deliver(rm);
        if (d.ok) r = await this._run("task-status", args, { confirm: true });
        else return { ok: false, rc: d.rc, stdout: d.stdout, stderr: d.stderr, delivery_failed: true };
      }
    }
    return r;
  }
  verdictSpec(kind) { return VERDICTS[kind]; }
  async verdict(rm, kind, note, ask, notify) {
    const v = VERDICTS[kind];
    const args = Object.assign({ rm_id: String(rm), status: v.status, note: note || v.def }, v.extra);
    return this.runGated(rm, args, v.status, ask, notify);
  }
  async applyStatus(rm, target, { note, reason }, ask, notify) {
    const args = { rm_id: String(rm), status: target };
    if (note && note.trim()) args.note = note.trim();
    if (reason) args.close_reason = reason;
    const r = await this.runGated(rm, args, target, ask, notify);
    this.repo.invalidateTransitions(rm);
    return r;
  }
  transitions(rm) { return this.repo.transitions(rm); }
  /** Qui travaille déjà le ticket — RELU (force) : un cache périmé dirait « libre » à tort (RM2818). */
  async busyFor(rm) { return ticketBusySessions(await this.repo.ensureTicketSessions(String(rm), true), this.eff); }
  spawnTicket(body) { return this.repo.spawn(body); }
  sendToSession(sid, msg) { return this.repo.send(sid, msg); }
}
