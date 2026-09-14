// models/tickets/openedTickets — la carte « Tickets ouverts » (RM2606/2637/2757/2883) : ce qui se calcule sans DOM. RM2889.

// RM3126 : la table des statuts est montée dans le socle (core/status) pour que les quatre autres
// vues qui affichent un statut y accèdent aussi. Ré-exportée ici : aucun appelant n'a à bouger.
export { ticketStatusRank, ticketStatusFamily } from "../../core/status.js";
import { ticketStatusFamily, ticketStatusRank } from "../../core/status.js";

/** RM2757 : la carte s'ouvre-t-elle au chargement ? Repliée tant que l'utilisateur n'a rien dit ; un choix explicite prime. */
export function openedPanelOpen(saved) { return String(saved) === "1"; }

/** Ce que l'en-tête dit quand la carte est REPLIÉE. RM2883 : avec un filtre actif, « vu / total ». */
export function openedCountLabel(n, total) {
  const k = Number(n), t = Number(total);
  if (!Number.isFinite(k) || k <= 0) return "(vide)";
  if (Number.isFinite(t) && t > k) return "(" + k + " / " + t + ")";
  return "(" + k + ")";
}

/** Ouvrir un ticket le remonte en tête, sans doublon, plafonné (comme l'historique du composer, RM2527). */
export function openedAdd(list, id, max) {
  const s = String(id == null ? "" : id).trim();
  if (!/^\d+$/.test(s)) return (list || []).slice();
  const out = (list || []).map(String).filter(x => x !== s);
  out.unshift(s);
  return out.slice(0, max || 40);
}

/** Les filtres à PROPOSER, avec leur compte : une famille absente n'a pas de bouton (la colonne est étroite). */
export function statusFamilyTabs(items) {
  const LABELS = [["todo", "à faire"], ["encours", "en cours"], ["test", "à tester"], ["mep", "à MEP"], ["pause", "en pause"], ["ferme", "fermé"], ["autre", "autre"]];
  const n = {};
  for (const it of items || []) { const f = ticketStatusFamily(it && it.status); n[f] = (n[f] || 0) + 1; }
  return LABELS.filter(([k]) => n[k]).map(([k, label]) => ({ key: k, label, n: n[k] }));
}

/** Groupe les tickets ouverts par projet, chaque groupe trié par urgence de statut. `client` filtre ; un ticket non
 *  encore résolu reste affiché (sous « … »). Les familles se calculent AVANT le filtre statut (sinon plus de bouton pour en changer). */
export function groupOpenedTickets(ids, cache, client, family) {
  const groups = new Map(), clients = new Set(), all = [];
  for (const id of (ids || [])) {
    const r = (cache || {})[id] || null;
    if (r && r.found && r.client) clients.add(r.client);
    if (client && (!r || !r.found || r.client !== client)) continue;
    all.push({ status: (r && r.status) || "?" });
    if (family && ticketStatusFamily((r && r.status) || "?") !== family) continue;
    const key = (r && r.found && r.client) ? r.client + "/" + (r.project || "?") : "…";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ rm_id: String(id), title: (r && r.title) || "", status: (r && r.status) || "?", client: (r && r.client) || null, project: (r && r.project) || null, resolved: !!(r && r.found) });
  }
  for (const items of groups.values()) items.sort((a, b) => ticketStatusRank(a.status) - ticketStatusRank(b.status) || Number(b.rm_id) - Number(a.rm_id));
  const keys = [...groups.keys()].sort((a, b) => (a === "…") - (b === "…") || a.localeCompare(b));
  return { keys, groups, clients: [...clients].sort(), families: statusFamilyTabs(all) };
}
