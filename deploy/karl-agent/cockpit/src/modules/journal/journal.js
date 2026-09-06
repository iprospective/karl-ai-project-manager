// modules/journal/journal — le panneau « journal » (RM3011) : fusion serveur + front, filtres sévérité × catégorie × texte, badge. Pur.
import { LEVELS } from "../../core/log.js";

/** Les deux flux fusionnés, du plus ancien au plus récent (à horodatage égal, le serveur d'abord) ; dédoublonnés par (src, id|ts+msg). */
export function mergeEntries(server, front) {
  const key = (r) => (r.src || "server") + ":" + (r.id != null ? r.id : r.ts + "|" + r.msg);
  const seen = new Set(); const out = [];
  for (const r of [...(server || []).map(r => Object.assign({ src: "server" }, r)), ...(front || [])]) { const k = key(r); if (seen.has(k)) continue; seen.add(k); out.push(r); }
  return out.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : (a.src === "server" ? -1 : 1)));
}

/** Filtre : sévérité minimale, catégories (ensemble vide = toutes), texte (message et champs). */
export function filterEntries(entries, { level = "debug", cats = null, q = "" } = {}) {
  const min = LEVELS[level] || LEVELS.debug; const needle = String(q || "").trim().toLowerCase();
  return (entries || []).filter(r => (LEVELS[r.level] || LEVELS.info) >= min && (!cats || !cats.size || cats.has(r.cat)) && (!needle || JSON.stringify(r).toLowerCase().includes(needle)));
}

/** Les champs libres d'un enregistrement, en texte compact (`k=v k=v`), les longs tronqués. */
export function fieldsText(r, skip = ["id", "ts", "level", "cat", "msg", "src"]) {
  return Object.entries(r || {}).filter(([k, v]) => !skip.includes(k) && v !== undefined && v !== null && v !== "").map(([k, v]) => k + "=" + (typeof v === "string" ? v : JSON.stringify(v)).slice(0, 160)).join(" ");
}

/** Compteur du badge : erreurs et avertissements du FRONT arrivés depuis la dernière ouverture du panneau. */
export function badgeCount(entries, sinceId) { return (entries || []).filter(r => r.src === "front" && r.id > (sinceId || 0) && LEVELS[r.level] >= LEVELS.warn).length; }

export function fmtTs(ts) { const s = String(ts || ""); return s.length >= 19 ? s.slice(11, 19) + (s.length > 23 ? "" : "") : s; }
export function dayOf(ts) { return String(ts || "").slice(0, 10); }
