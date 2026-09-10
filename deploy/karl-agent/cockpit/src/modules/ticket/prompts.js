// models/tickets/prompts — consignes de lancement et texte d'alerte (RM2726, RM2833, RM2873, RM2818). Repris tels quels.
export function promptTemplates() {
  return [{ value: "traiter", label: "Traiter la tâche" }, { value: "continuer", label: "Continuer la tâche" }, { value: "chiffrer", label: "Étudier / chiffrer" },
          { value: "etat", label: "État du ticket" }, { value: "reviewer", label: "Reviewer" }, { value: "libre", label: "Libre (saisie manuelle)" }];
}
/** « libre » ne touche à rien ; un modèle qu'on ne sait pas calculer ne VIDE pas le champ. */
export function promptFillOnChange(tpl, current, computed) {
  if (String(tpl) === "libre") return String(current || "");
  return computed ? String(computed) : String(current || "");
}
/** L'état du champ de consigne de la fiche : un re-rendu garde la saisie, changer de ticket repart propre. */
export function ticketPromptFor(prev, rm, deflt) {
  const p = prev || {}, id = String(rm == null ? "" : rm);
  if (String(p.rm || "") === id && p.text) return { rm: id, tpl: p.tpl || "traiter", text: p.text };
  return { rm: id, tpl: "traiter", text: String(deflt || "") };
}
export function taskPromptText(tpl, rm, client, project, hint) {
  const id = String(rm == null ? "" : rm).trim();
  if (!/^\d+$/.test(id)) return "";
  const cp = (client && project) ? (" du client " + client + " projet " + project) : "";
  const h = (hint && hint.role) ? " (rôle suggéré par ses étiquettes : " + hint.role + " — lis " + (hint.file || ("agents/worker-" + hint.role + ".md")) + ")" : "";
  if (tpl === "traiter") return "traite la tâche RM" + id + cp + h;
  if (tpl === "continuer") return "continue la tâche RM" + id + cp + " : relis le .log.md et reprends où tu t'es arrêté";
  if (tpl === "chiffrer") return "étudie et chiffre la tâche RM" + id + cp + h;
  if (tpl === "etat") return "fais un état du ticket RM" + id + cp + " : relis la tâche, son .log.md et ses outputs, et donne un point synthétique (avancement, reste à faire, blocages, prochaine étape) SANS rien modifier ni changer de statut";
  if (tpl === "reviewer") return "review la tâche RM" + id;
  return "";
}
export function roleHintLine(hint) { const h = hint || {}; if (!h.role) return ""; return " (rôle suggéré : " + h.role + " — " + (h.file || ("agents/worker-" + h.role + ".md")) + ")"; }
/** Ce que l'alerte de doublon DIT : sid, titre, état de chaque session qui travaille déjà le ticket. */
export function duplicateSessionText(rm, busy, eff) {
  const b = busy || { alive: [], stopped: [] };
  const ligne = (r) => "  · " + (r.is_ticket === false ? r.sid : "RM" + r.sid) + (r.title ? " — " + r.title : "") +
    " [" + (r.state || "?") + (eff && eff(r.state, r.disposition) === "parke" ? ", parké" : "") + "]" + ((r.reasons && r.reasons.length) ? " (" + r.reasons.join(", ") + ")" : "");
  const out = ["RM" + rm + " est déjà pris en charge par " + (b.alive.length > 1 ? b.alive.length + " sessions ouvertes :" : "une session ouverte :"), ""];
  b.alive.forEach(r => out.push(ligne(r)));
  if (b.stopped.length) { out.push("", "Également, non terminée mais éteinte (relançable) :"); b.stopped.forEach(r => out.push(ligne(r))); }
  return out.join("\n");
}
