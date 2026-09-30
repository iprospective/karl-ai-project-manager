// models/env/envStatus — la santé du poste, classée. RM2889, L5. Repris tel quel (RM2458, RM2708).

// Les trois fonctions de présentation sont montées dans le socle (core/checks.js,
// RM3369) : la santé du SYSTÈME PM rend la même forme de rapport. Ré-exportées
// ici sous leurs noms d'origine — aucun appelant n'a bougé.
export { checkTabs as envStatusTabs, checkDefaultTab as envStatusDefaultTab,
         checkSections as envStatusSections } from "../../core/checks.js";

/** Le bouton d'en-tête : montré seulement s'il y a un geste à faire, et son libellé DIT lequel. */
export function vaultBtnState(st) {
  if (!st) return { show: false, label: "", title: "" };
  const locked = st.locked || [];
  const keys = (st.ssh && st.ssh.keys) || [];
  const why = [];
  if (!st.daemon) why.push("coffre fermé (agent non démarré)");
  else if (locked.length === 1) why.push("coffre « " + locked[0] + " » verrouillé");
  else if (locked.length > 1) why.push(locked.length + " coffres verrouillés");
  if (!keys.length) why.push("agent SSH vide");
  if (!why.length) return { show: false, label: "", title: "" };
  return { show: true, label: "🔓 déverrouiller", title: why.join(" · ") + " — clic pour saisir le mot de passe" };
}
