// models/tickets/search — la recherche de tickets (RM2770 multi-source, RM2639 contexte client, RM2830 étiquettes) : sans DOM. RM2889.
import { route } from "../../core/endpoints.js";

/** La requête. Le filtre explicite PRIME sur le contexte client global : sinon le cockpit contredirait en silence le client choisi. */
export function searchQuery(q, f, ctxClient) {
  const o = f || {};
  const p = ["q=" + encodeURIComponent(q || "")];
  const client = o.client || ctxClient || "";
  if (client) p.push("client=" + encodeURIComponent(client));
  if (o.project) p.push("project=" + encodeURIComponent(o.project));
  if (o.status) p.push("status=" + encodeURIComponent(o.status));
  if (o.tag) p.push("tag=" + encodeURIComponent(o.tag));
  const src = o.source || "local";
  if (src !== "local") p.push("source=" + encodeURIComponent(src));
  return route("search.tickets") + "?" + p.join("&");
}
/** La ligne de contexte d'un résultat : un ticket vu côté Redmine et absent en local DOIT le dire — ça décide du geste suivant. */
export function searchRowMeta(t) {
  const r = t || {};
  const où = (r.client && r.project) ? r.client + " / " + r.project : (r.redmine_project || "—");
  const bits = [où, r.status || "?"];
  if (r.origin === "redmine" && !r.synced) bits.push("⚠ pas en local");
  else if (r.origin === "redmine" || r.origin === "both") bits.push("🌐 Redmine");
  if (r.assigned_to) bits.push("→ " + r.assigned_to);
  const tags = (r.tags || []).filter(Boolean);
  if (tags.length) bits.push("🏷 " + tags.join(", "));
  return bits.join(" · ");
}
/** RM2770 : un ticket que Redmine connaît mais que le local ignore n'a rien à faire dans le lanceur — il vit chez Redmine. */
export function isAbsent(t) { return !!(t && t.origin === "redmine" && !t.synced); }
export function sfClients(projects) { const seen = {}; for (const p of (projects || [])) if (p && p.client) seen[p.client] = 1; return Object.keys(seen).sort((a, b) => a.localeCompare(b)); }
/** Le sélecteur de projet ne montre QUE les projets du client choisi ; la valeur courante survit si elle en fait partie. */
export function sfProjects(projects, client, current) {
  const items = (projects || []).filter(p => p && p.project && (!client || p.client === client)).map(p => p.project);
  return { options: items, value: items.includes(String(current || "")) ? String(current) : "" };
}
/** RM2830 : les étiquettes proposées sont celles qui EXISTENT, avec leur nombre d'usages. */
export function tagOptions(tags) { return (tags || []).map(t => ({ value: String(t.tag), label: t.tag + " (" + t.count + ")" })); }
