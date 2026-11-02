// models/tickets/briefs — l'infobulle d'un RM-id (RM2619) : texte et demandes à grouper, sans DOM. RM2889.
import { hoverText } from "../../core/entities.js";

/** Tant que le cache n'a pas répondu, on le DIT (« chargement… ») plutôt que de rendre une bulle vide. */
/** Le survol d'un RM-id. RM3164 : le contenu est désormais DÉCLARÉ par le type « review » dans
 *  le registre d'entités (`core/entities.js :: hoverFields`), et monté par `hoverText` — c'est la
 *  généralisation demandée, ce texte n'était écrit que pour les tickets.
 *
 *  Le contrat d'appel ne change pas : ici `null` veut dire « pas encore chargé » (c'est ce que
 *  rend le cache), là où le moteur réserve `null` à « inconnu ». On normalise plutôt que de
 *  changer le cache — l'inverse ferait annoncer « inconnu en local » pendant chaque chargement.
 */
export function ticketTipText(id, brief) {
  return hoverText("review", id, brief == null ? undefined : brief);
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
