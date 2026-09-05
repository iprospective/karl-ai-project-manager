// models/terminal/TerminalRepository — /send (repli sans client maison), /capture, /buffer, /memdebug. RM2889.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { post, raw } from "../../core/api.js";

export class TerminalRepository extends Repository {
  constructor() { super({ name: "terminal", ttl: 1000, max: 1, factory: new Factory({ type: "terminal" }), routes: { send: "session.send", capture: "terminal.capture", buffer: "terminal.buffer", memdebug: "terminal.memdebug" } }); }
  send(sid, msg) { return post(this.path("send"), { rm_id: sid, msg, enter: true }); }
  async capture(sid, lines) { const r = await raw(this.path("capture") + "/" + encodeURIComponent(sid) + "?lines=" + (lines || 300)); return r.text(); }
  /** null quand aucune copie n'attend côté tmux (404). */
  async buffer() { try { const r = await raw(this.path("buffer")); return r.text(); } catch (e) { if (e && e.status === 404) return null; throw e; } }
  memdebug(payload) { return post(this.path("memdebug"), payload); }
}
