// models/projects/projectGroups — grouper, filtrer, compter. RM2889, L4. Repris tel quel (RM2760).

/** Groupe et FILTRE : un filtre sur le client ramène tous ses projets, un filtre
 *  sur un projet ne ramène que lui — chercher « infra » montre les infra de tous. */
export function groupProjectsByClient(projects, filtre) {
  const q = String(filtre || "").trim().toLowerCase();
  const map = new Map();
  for (const p of (projects || [])) {
    if (!p || !p.client || !p.project) continue;
    const surClient = p.client.toLowerCase().includes(q);
    if (q && !surClient && !p.project.toLowerCase().includes(q)) continue;
    if (!map.has(p.client)) map.set(p.client, []);
    map.get(p.client).push({ client: p.client, project: p.project, value: p.value || (p.client + "/" + p.project) });
  }
  return [...map.entries()]
    .map(([client, items]) => ({ client, projects: items.slice().sort((a, b) => a.project.localeCompare(b.project)) }))
    .sort((a, b) => a.client.localeCompare(b.client));
}

/** Sessions VIVANTES par client/projet. Un `ghost` (enregistré, non démarré) ne compte pas. */
export function liveByProject(sessions, rcache) {
  const out = {};
  for (const s of (sessions || [])) {
    if (!s || s.ghost) continue;
    const r = (rcache || {})[s.rm_id];
    const cl = s.client || (r && r.found ? r.client : null);
    const pr = s.project || (r && r.found ? r.project : null);
    if (!cl || !pr) continue;
    const k = cl + "/" + pr;
    out[k] = (out[k] || 0) + 1;
  }
  return out;
}
