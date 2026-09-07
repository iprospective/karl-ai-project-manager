// models/launcher/launcher — le lanceur (§1 résolution, RM1941 modèles, RM2873 consigne, spawn), la saisie éclair d'un ticket (§8)
// et le contexte client (RM2639) : ce qui se calcule sans DOM. RM2889.

/** RM2639 : clients uniques triés depuis /projects. */
export function clientCtxList(projects) { const seen = {}; for (const p of (projects || [])) if (p && p.client) seen[p.client] = 1; return Object.keys(seen).sort((a, b) => a.localeCompare(b)); }
/** RM2639 : `value` (client/projet) du premier projet d'un client, "" si client vide ou introuvable. */
export function clientCtxProject(projects, client) { if (!client) return ""; for (const p of (projects || [])) if (p && p.client === client) return p.value; return ""; }
/** RM1941 : les modèles du moteur courant — « défini dans le ticket » d'abord (avec la prescription si résolue), le défaut moteur, puis le catalogue ;
 *  le choix précédent survit s'il est encore valide, sinon « ticket » (sentinelle toujours sûre côté serveur). */
export function modelOptions(cfgModels, engine, resolved, prev) {
  const keys = ((cfgModels || {})[engine] || []).map(String);
  const presc = resolved && resolved.found && resolved.ai_model ? " (" + resolved.ai_model + ")" : "";
  const options = [{ value: "ticket", label: "défini dans le ticket" + presc }, { value: "", label: "défaut moteur" }].concat(keys.map(k => ({ value: k, label: k })));
  return { options, value: options.some(o => o.value === prev) ? prev : "ticket" };
}
/** La ligne sous le champ RM : ce qu'on va lancer. */
export function resolvedLine(r) {
  if (!r) return null;
  if (!r.found) return { found: false, text: "⚠ ticket non trouvé en local — prompt générique", closed: false };
  return { found: true, text: "✓ " + r.client + " / " + r.project + (r.title ? " — " + r.title : "") + (r.status ? "  [" + r.status + "]" : ""), closed: r.status === "ferme", cwd: r.cwd || "" };
}
/** Le corps de /spawn depuis le formulaire ; null (avec raison) si le RM n'est pas un entier. */
export function spawnBody(f) {
  const rm = String(f.rm || "").trim();
  if (!/^\d+$/.test(rm)) return { error: "RM id requis (entier)" };
  const body = { rm_id: rm, engine: f.engine || "claude" };
  if (f.model) body.model = f.model;
  if (String(f.cwd || "").trim()) body.cwd = String(f.cwd).trim();
  if (String(f.prompt || "").trim()) body.prompt = String(f.prompt).trim();
  return { body, rm };
}
/** Le corps de POST /tickets depuis la saisie éclair ; null si le titre manque. */
export function ticketBody(f) {
  const title = String(f.title || "").trim();
  if (!title) return { error: "Titre requis" };
  return { body: { title, project: f.project || "", type: f.type || "", priority: f.priority || "", tags: String(f.tags || "").trim(), description: String(f.description || "").trim() } };
}
export function typeOptions(cfg) { return ((cfg || {}).task_types || []).map(t => ({ value: t.value, label: t.label || t.value, selected: t.value === "feature" })); }
export function prioOptions(cfg) { return ((cfg || {}).priorities || ["low", "normal", "high", "urgent"]).map(p => ({ value: p, label: p, selected: p === "normal" })); }
export const DEFAULT_PROJECT = "iprospective/pm-ai-agents";
