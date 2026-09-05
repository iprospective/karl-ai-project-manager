// models/tickets/briefs — l'infobulle d'un RM-id (RM2619) : texte et demandes à grouper, sans DOM. RM2889.

/** Tant que le cache n'a pas répondu, on le DIT (« chargement… ») plutôt que de rendre une bulle vide. */
export function ticketTipText(id, brief) {
  const b = brief || null;
  if (!b) return "RM" + id + " — chargement…";
  if (!b.found) return "RM" + id + " — inconnu en local";
  const bits = [];
  if (b.status) bits.push(b.status);
  if (b.completion_pct !== null && b.completion_pct !== undefined) bits.push(b.completion_pct + " %");
  if (b.type) bits.push(b.type);
  if (b.priority && b.priority !== "normal") bits.push("priorité " + b.priority);
  const ou = (b.client && b.project) ? b.client + "/" + b.project : (b.client || "");
  return "RM" + id + " — " + (b.title || "(sans titre)") + (bits.length ? "\n" + bits.join(" · ") : "") + (ou ? "\n" + ou : "");
}

/** Ids à demander : inconnus ET pas déjà en vol — sans ce filtre, chaque rendu redemandait tout ce qui était à l'écran. */
export function pendingBriefIds(ids, cache, inflight) {
  const vus = new Set(), out = [];
  for (const raw of (ids || [])) {
    const id = String(raw == null ? "" : raw).trim();
    if (!/^\d+$/.test(id) || vus.has(id)) continue;
    vus.add(id);
    if ((cache || {})[id] !== undefined) continue;
    if ((inflight || new Set()).has(id)) continue;
    out.push(id);
  }
  return out;
}
