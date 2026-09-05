// models/sessions/ResumeRepository — sessions reprenables (/resumable), reprise (/resume), déplacement (/move-session). RM2889.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get, post } from "../../core/api.js";

export class ResumeRepository extends Repository {
  constructor() { super({ name: "resume", ttl: 5000, max: 20, factory: new Factory({ type: "resumable-session" }), routes: { list: "search.resumable", resume: "session.resume", move: "session.move_session" } }); }
  async search(qs) { const r = await get(this.path("list") + (qs || "")); return { resumable: (r && r.resumable) || [], archived: (r && r.archived) || [] }; }
  resume(body) { return post(this.path("resume"), body); }
  move(sessionId, client, project) { return post(this.path("move"), { session_id: sessionId, client, project }); }
}
