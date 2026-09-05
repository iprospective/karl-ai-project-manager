// models/tickets/SearchRepository — /tickets/search (local, Redmine, les deux) et /tags. RM2889.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get } from "../../core/api.js";
import { searchQuery } from "./search.js";

export class SearchRepository extends Repository {
  constructor() { super({ name: "ticket-search", ttl: 5000, max: 20, factory: new Factory({ type: "ticket-hit" }), routes: { tags: "search.tags" } }); }
  async search(q, filters, ctxClient) { const r = await get(searchQuery(q, filters, ctxClient)); return { results: (r && r.results) || [], redmine_error: (r && r.redmine_error) || "" }; }
  async tags() { const r = await get(this.path("tags")); return (r && r.tags) || []; }
}
