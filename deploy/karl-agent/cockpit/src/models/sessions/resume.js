// models/sessions/resume — « Reprendre une session » (RM1939/2834/2991/2418) : filtres, requête, libellés, ancrage. RM2889.

/** RM2834 : les clients proposés viennent des projets connus — dédoublonnés, triés. */
export function rsClientOptions(projects) {
  const out = [];
  for (const p of projects || []) if (p && p.client && out.indexOf(p.client) < 0) out.push(p.client);
  return out.sort();
}
/** RM2834 : les projets d'UN client, et la sélection courante — abandonnée si elle appartient à un autre client. */
export function rsProjectOptions(projects, client, current) {
  const list = (projects || []).filter(p => p && p.client && p.project && (!client || p.client === client));
  const options = list.map(p => ({ value: p.value || (p.client + "/" + p.project), label: client ? p.project : (p.client + "/" + p.project) }))
                      .sort((a, b) => a.value < b.value ? -1 : a.value > b.value ? 1 : 0);
  const cur = String(current || "");
  return { options, value: options.some(o => o.value === cur) ? cur : "" };
}
/** RM2991 : la requête /resumable. Un projet vaut client+projet ; le transcript ne se balaie JAMAIS sans mots-clés. */
export function rsQuery(f) {
  f = f || {};
  const q = [];
  if (f.engine) q.push("engine=" + encodeURIComponent(f.engine));
  if (f.project) { const parts = String(f.project).split("/"); q.push("client=" + encodeURIComponent(parts[0]), "project=" + encodeURIComponent(parts[1] || "")); }
  else if (f.client) q.push("client=" + encodeURIComponent(f.client));
  if (f.status) q.push("status=" + f.status);
  const needle = String(f.q || "").trim();
  if (needle) { q.push("q=" + encodeURIComponent(needle)); if (f.deep) q.push("deep=1"); }
  return q.length ? "?" + q.join("&") : "";
}
/** RM2991 : « RM2703 » ne dit pas de quoi il s'agissait — le sujet, tronqué court. */
export function rsTicketsLabel(tickets, max) {
  const lim = max || 42;
  return (tickets || []).map(t => { const id = "RM" + t.rm_id, ti = String(t.title || "").trim(); if (!ti) return id; return id + " " + (ti.length > lim ? ti.slice(0, lim - 1) + "…" : ti); }).join(" · ");
}
/** RM2144 : l'ancrage proposé à la reprise — le dernier ticket de la session, sinon ce que porte le lanceur. */
export function resumeAnchorDefault(s, launcherRm) { return (s && s.tickets && s.tickets.length) ? String(s.tickets[s.tickets.length - 1].rm_id) : String(launcherRm || "").trim(); }
/** Normalise et valide un ancrage saisi : « RM42 » → 42 ; slug [a-z0-9_-] ; vide = slug auto côté serveur. null si invalide. */
export function normalizeAnchor(raw) {
  let rm = String(raw == null ? "" : raw).trim();
  if (/^rm\d+$/i.test(rm)) rm = rm.replace(/^rm/i, "");
  if (!rm) return "";
  if (!/^\d+$/.test(rm) && !/^[a-z0-9][a-z0-9_-]{1,40}$/.test(rm)) return null;
  return rm;
}
