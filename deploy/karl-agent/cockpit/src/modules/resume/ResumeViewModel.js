// viewmodels/sessions/ResumeViewModel — la carte « Reprendre une session », décidée. RM2889.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { rsTicketsLabel, rsClientOptions, rsProjectOptions } from "./resume.js";

/** e = { resumable, archived, needle } ; ctx = { ago } */
export class ResumeListViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get needle() { return String(this.e.needle || "").trim(); }
  get empty() { return !(this.e.resumable || []).length; }
  get emptyText() { return this.needle ? "aucune session reprenable pour « " + this.needle + " »" : "aucune session"; }
  rows() {
    const ago = this.ctx.ago || (() => "");
    return (this.e.resumable || []).map(s => { const tk = rsTicketsLabel(s.tickets); return { id: String(s.session_id), mark: s.mark || "", title: s.title || String(s.session_id).slice(0, 8) + "…", transcript: s.match === "transcript",
      where: s.client ? s.client + "/" + s.project : (s.cwd || "?"), tickets: tk, age: ago(s.mtime), live: !!s.live, tip: (s.title || "") + "\n" + (tk ? tk + "\n" : "") + (s.cwd || "") + "\nsession " + s.session_id }; });
  }
  /** RM2991 : le worklog survit au transcript — nommées, jamais cliquables. */
  archived() { return (this.e.archived || []).map(s => ({ id: String(s.session_id).slice(0, 8), updated: s.updated || "", refs: (s.tickets || []).map(t => t.title ? t.ref + " " + t.title : t.ref).join(" · ") })); }
}

/** e = { projects, client, project } — les listes des deux sélecteurs et la sélection cohérente. */
export class ResumeFiltersViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get clients() { return rsClientOptions(this.e.projects); }
  get projects() { return rsProjectOptions(this.e.projects, this.e.client || "", this.e.project || ""); }
}
