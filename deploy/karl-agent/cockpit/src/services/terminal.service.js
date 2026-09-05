// services/terminal.service — historique du composer (ce navigateur), envoi (client maison ou repli serveur), captures. RM2889.
import { TerminalRepository } from "../models/terminal/TerminalRepository.js";
import { composerHistoryAdd, CMP_HIST_MAX, histKey } from "../models/terminal/terminal.js";

export class TerminalService {
  constructor({ repo = new TerminalRepository(), storage = null } = {}) { this.repo = repo; this.storage = storage; }
  history(rmId) { try { return JSON.parse((this.storage && this.storage.getItem(histKey(rmId))) || "[]") || []; } catch (e) { return []; } }
  remember(rmId, text) { const list = composerHistoryAdd(this.history(rmId), text, CMP_HIST_MAX); try { if (this.storage) this.storage.setItem(histKey(rmId), JSON.stringify(list)); } catch (e) { /* mode privé */ } return list; }
  /** L'envoi emprunte la socket du client maison (même PTY qu'une frappe) ; sans lui, le serveur (/send). Rend { ok, message }. */
  async send(session, sid, text) {
    if (session && session.send) { const ok = session.send(text); return ok ? { ok: true } : { ok: false, message: "Terminal déconnecté — message conservé dans le champ" }; }
    try { await this.repo.send(sid, text); return { ok: true }; } catch (e) { return { ok: false, message: e.message }; }
  }
  capture(sid) { return this.repo.capture(sid, 300); }
  buffer() { return this.repo.buffer(); }
  memdebug(payload) { return this.repo.memdebug(payload).catch(() => {}); }
}
