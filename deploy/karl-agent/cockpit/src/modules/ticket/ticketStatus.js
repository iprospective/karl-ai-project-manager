// models/tickets/ticketStatus — verdicts, invites, gardes (RM2786, RM2888). Repris tels quels ; AUCUN statut en dur.
/** Quels verdicts ont un sens pour ce statut : un verdict porte sur du travail LIVRÉ ; statut inconnu → tout. */
export function ticketVerdicts(status, cfg) {
  const st = String(status || "").toLowerCase();
  const closables = new Set((cfg && cfg.closable_statuses) || []);
  const connu = st && ((cfg && (cfg.statuses || [])).indexOf(st) >= 0);
  const tous = [{ kind: "valider", label: "✅ testé OK → fermer" }, { kind: "mep", label: "🚧 testé OK → demander la MEP" }, { kind: "renvoyer", label: "↩ KO → renvoyer en correction" }];
  if (!connu) return tous;
  if (!closables.has(st)) return [];
  return (st === "a_mep" || st === "en_mep") ? tous.filter(v => v.kind !== "mep") : tous;
}
export const VERDICTS = {
  valider:  { status: "ferme", label: "Compte-rendu de validation", extra: { close_reason: "resolu" }, def: "Validé via la console de test du cockpit." },
  mep:      { status: "a_mep", label: "Note pour la demande de MEP", extra: {}, def: "Testé OK — demande de mise en production (via console de test cockpit)." },
  renvoyer: { status: "a_corriger", label: "Motif du renvoi (requis)", extra: {}, def: null },
};
/** Ce qu'il faut demander avant de soumettre : la règle vient du serveur (`needs_*`), pas du nom du statut. */
export function statusPromptSpec(target, needsReason, reasons, needsNote) {
  const list = (reasons || []).slice();
  return { needs_reason: !!needsReason, needs_note: !!needsNote, reasons: list,
    default_reason: list.indexOf("resolu") >= 0 ? "resolu" : (list[0] || ""),
    note_label: needsNote ? "Note (requise par le workflow) :" : "Note (compte-rendu, facultatif) :" };
}
/** Quelle garde NORMS a refusé la transition, d'après la sortie de task-status. */
export function gateKind(out) {
  const s = String(out || "");
  if (/checklist non coché/.test(s)) return "checklist";
  if (/non mergée|RM2319/.test(s)) return "merge";
  return null;
}
