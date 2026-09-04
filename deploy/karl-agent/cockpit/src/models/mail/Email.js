// models/mail/Email — l'entité « email en file de triage ». RM2889, L1 (pilote).
//
// Ce que le serveur renvoie sur /mail/queue, hydraté et rendu valide UNE fois.
// Les dérivations ci-dessous sont celles que renderMailList calculait en
// plein rendu (cible de routage, confiance en %) : elles sont MÉTIER, elles
// sortent du gabarit et deviennent testables sans HTML.

import { Factory } from "../Factory.js";

export const EmailFactory = new Factory({
  type: "email",
  required: ["key"],
  defaults: { subject: "", from: "", from_name: "", date: "", folder: "", state: "à traiter",
              attachments: 0, routing: {}, draft: {}, body: "", body_truncated: false },
  coerce: { routing: r => r || {}, draft: d => d || {} },
});

/** « client/projet », « client/? » (projet non tranché — pas de choix silencieux), ou « à classer ». */
export function routingTarget(e) {
  const r = e.routing || {};
  return r.client ? r.client + (r.project ? "/" + r.project : "/?") : "à classer";
}

/** Confiance en pourcentage entier, ou "" si le serveur n'en donne pas. */
export function confidencePct(x) {
  return x && x.confidence ? Math.round(x.confidence * 100) + "%" : "";
}

/** Projet proposé pour la création : la proposition d'abord, sinon le routage. */
export function proposedProject(e) {
  const r = e.routing || {}, d = e.draft || {};
  return d.project || (r.client && r.project ? r.client + "/" + r.project : "");
}
