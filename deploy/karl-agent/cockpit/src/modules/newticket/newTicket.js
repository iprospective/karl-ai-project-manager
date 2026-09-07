// models/tickets/newTicket — la cible et le corps d'un ticket à créer. RM2889, surface « nouveau ticket ».
// RM2726 : la valeur d'un projet reste « client/projet » — c'est ce que POST /tickets
// attend, recomposer la paire à l'envoi serait un endroit de plus où se tromper.

/** Les clients connus, triés. */
export function clientsOf(projects) {
  return Array.from(new Set((projects || []).filter(p => p && p.client && p.project).map(p => p.client))).sort();
}
/** Les projets d'UN client, triés. */
export function projectsOf(projects, client) {
  return (projects || []).filter(p => p && p.client === client && p.project).map(p => p.project).sort();
}
/** Client retenu : le courant s'il existe, sinon le premier — jamais une sélection vide. */
export function pickClient(projects, cur) { const cs = clientsOf(projects); return cs.indexOf(cur) >= 0 ? cur : (cs[0] || ""); }
/** Projet coché : le courant s'il est du client, sinon le premier. */
export function pickProject(projects, client, cur) { const ps = projectsOf(projects, client); return ps.indexOf(cur) >= 0 ? cur : (ps[0] || ""); }

export const REPRO = ["always", "often", "sometimes", "rarely", "never"];
export const AGENT_TEST = ["default", "oui", "non", "demander"];
export const DIFFICULTY = ["low", "medium", "high", "critical"];

/** Le corps envoyé au serveur, ou l'erreur à dire ICI plutôt que de laisser le serveur refuser (RM2752). */
export function buildTicketBody(v) {
  const g = (k) => String(v[k] == null ? "" : v[k]);
  const title = g("title").trim();
  if (!title) return { error: "Titre requis" };
  if (!g("project")) return { error: "Projet requis — ce client n’a aucun projet" };
  const body = { title, project: g("project"), type: g("type"), priority: g("priority"), tags: g("tags").trim(), description: g("description").trim(),
    agent_test: g("agent_test"), target_env: g("target_env").trim(), est_human_minutes: g("est_human_minutes"), est_ai_minutes: g("est_ai_minutes"), difficulty: g("difficulty") };
  if (body.type === "bugfix") {
    const steps = g("bug_steps").trim();
    if (!steps) return { error: "Étapes de reproduction requises pour un bugfix" };
    body.bug_steps = steps; body.bug_reproducibility = g("bug_reproducibility") || "always";
  }
  return { body };
}
