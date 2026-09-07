// models/center/viewKey — la clé d'un onglet SUFFIT à rouvrir sa vue (RM2759). Le libellé court vient du registre des types (RM3002).
import { tabLabelOf } from "../../core/entities.js";
export function viewKey(parts) {
  return (parts || []).map(p => encodeURIComponent(String(p == null ? "" : p))).join("|");
}
export function parseViewKey(key) {
  const s = String(key == null ? "" : key);
  if (!s) return [];
  return s.split("|").map(p => { try { return decodeURIComponent(p); } catch (e) { return p; } });
}
/** Nom d'onglet : court, mais reconnaissable entre dix. */
export function viewTabLabel(kind, parts, hint) { return tabLabelOf(kind, parts, hint); }
