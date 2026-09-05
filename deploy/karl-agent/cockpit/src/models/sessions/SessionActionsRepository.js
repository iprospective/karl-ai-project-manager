// models/sessions/SessionActionsRepository — /send, /monitor, /unmonitor, /layout, /disposition, /kill. RM2889.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { post } from "../../core/api.js";

export class SessionActionsRepository extends Repository {
  constructor() { super({ name: "session-actions", ttl: 1000, max: 1, factory: new Factory({ type: "session" }), routes: { send: "session.send", monitor: "session.monitor", unmonitor: "session.unmonitor", layout: "session.layout", disposition: "session.disposition", kill: "session.kill" } }); }
  send(sid, msg, enter) { return post(this.path("send"), { rm_id: sid, msg, enter: enter !== false }); }
  monitor(sid, preset) { return post(this.path("monitor"), { rm_id: sid, preset }); }
  unmonitor(sid) { return post(this.path("unmonitor"), { rm_id: sid }); }
  layout(sid, layout) { return post(this.path("layout"), { rm_id: sid, layout }); }
  disposition(sid, disposition) { return post(this.path("disposition"), { rm_id: String(sid), disposition }); }
  kill(sid) { return post(this.path("kill"), { rm_id: String(sid) }); }
}
