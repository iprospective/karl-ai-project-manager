// models/center/viewKey — la clé d'un onglet SUFFIT à rouvrir sa vue (RM2759). Repris tel quel.
export function viewKey(parts) {
  return (parts || []).map(p => encodeURIComponent(String(p == null ? "" : p))).join("|");
}
export function parseViewKey(key) {
  const s = String(key == null ? "" : key);
  if (!s) return [];
  return s.split("|").map(p => { try { return decodeURIComponent(p); } catch (e) { return p; } });
}
/** Nom d'onglet : court, mais reconnaissable entre dix. */
export function viewTabLabel(kind, parts, hint) {
  const p = parts || [];
  const base = x => String(x || "").replace(/\/+$/, "").split("/").pop();
  if (kind === "file") return base(p[2]) || base(p[1]) || "fichier";
  if (kind === "dir") return (base(p[2]) || "racine") + "/";
  if (kind === "commit") return String(p[1] || "").slice(0, 8) || "commit";
  if (kind === "mail") { const t = String(hint || p[1] || "email").trim(); return t.length > 30 ? t.slice(0, 29) + "…" : t; }
  return String(hint || "vue");
}
