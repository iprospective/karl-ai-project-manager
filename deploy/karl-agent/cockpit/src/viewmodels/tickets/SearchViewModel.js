// viewmodels/tickets/SearchViewModel — les résultats de recherche et les filtres, décidés. RM2889.
import { EntityViewModel } from "../EntityViewModel.js";
import { searchRowMeta, isAbsent, sfClients, sfProjects, tagOptions } from "../../models/tickets/search.js";

/** e = { results, error, base (URL Redmine) } */
export class SearchResultsViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get error() { return this.e.error ? "⚠ " + this.e.error : ""; }
  get empty() { return !(this.e.results || []).length; }
  rows() {
    const base = this.e.base || "";
    return (this.e.results || []).map(t => { const absent = isAbsent(t); return { rm: String(t.rm_id), title: t.title || "(sans titre)", meta: searchRowMeta(t), absent, url: absent && base ? base + "/issues/" + t.rm_id : "",
      tip: absent ? "Pas encore de fichier local — clic : ouvrir RM" + t.rm_id + " dans Redmine" + (base ? "" : " (URL Redmine non configurée)") : "Clic : préparer une session sur RM" + t.rm_id }; });
  }
}
/** e = { projects, client, project, ctxClient, statuses, tags } — le client du filtre, sinon le contexte, décide des projets. */
export class SearchFiltersViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get clients() { return sfClients(this.e.projects); }
  get projects() { return sfProjects(this.e.projects, this.e.client || this.e.ctxClient || "", this.e.project); }
  get statuses() { return (this.e.statuses || []).map(String); }
  get tags() { return tagOptions(this.e.tags); }
}
