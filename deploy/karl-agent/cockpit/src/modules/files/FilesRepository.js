// models/files/FilesRepository — worktrees d'une session, racines d'un projet, lecture d'un dossier/fichier/journal. RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";
const enc = encodeURIComponent;

export class FilesRepository extends Repository {
  constructor() { super({ name: "files", ttl: 5000, max: 20, factory: new Factory({ type: "fs-entry" }), routes: { worktrees: "file.worktrees", roots: "file.project_roots", ls: "file.ls", file: "file.read", log: "file.log" } }); }
  worktrees(sid) { return get(this.path("worktrees") + "/" + enc(sid)); }
  projectRoots(client, project) { return get(this.path("roots") + "/" + enc(client) + "/" + enc(project)); }
  async ls(scopeQuery, path) { const r = await get(this.path("ls") + "?" + scopeQuery + "&path=" + enc(path || "")); return (r && r.entries) || []; }
  file(scopeQuery, path) { return get(this.path("file") + "?" + scopeQuery + "&path=" + enc(path)); }
  async log(scopeQuery) { const r = await get(this.path("log") + "?" + scopeQuery); return (r && r.commits) || []; }
}
