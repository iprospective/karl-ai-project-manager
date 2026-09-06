// models/tickets/triage — le triage ROI des tickets ouverts (RM1952/2830/2831) : filtres et lot, sans DOM. RM2889.

/** RM2830 : l'étiquette se compare NORMALISÉE ; vide = aucun filtre (et surtout pas « les tickets sans étiquette »). */
export function triageFilter(tickets, client, project, hideValid, tag) {
  const t0 = String(tag || "").toLowerCase();
  return (tickets || []).filter(function (t) {
    if (client && t.client !== client) return false;
    if (project && t.project !== project) return false;
    if (hideValid && t.awaiting_validation) return false;
    if (t0 && !((t.tags || []).some(x => String(x).toLowerCase() === t0))) return false;
    return true;
  });
}
export function triageClients(tickets) { return [...new Set((tickets || []).map(t => t.client).filter(Boolean))].sort(); }
export function triageProjects(tickets, client) { return [...new Set((tickets || []).filter(t => !client || t.client === client).map(t => t.project).filter(Boolean))].sort(); }

/** RM2831 : les lignes affichées deviennent les items d'un lot, dans l'ordre du triage, plafonnées à ce qu'on annonce. */
export function triageBatchItems(rows, max) {
  const n = Number(max) > 0 ? Number(max) : 10;
  return (rows || []).slice(0, n).map(t => ({ rm_id: String(t.rm_id), status: t.status || "", title: t.title || "", points: [] }));
}
