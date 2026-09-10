// modules/doc/helpSpots — le registre des ZONES du cockpit et leur repère « ? ». RM3075.
//
// Le cockpit a une aide complète (help/*.md) et un glossaire ; ce qui manquait est le chemin
// INVERSE : depuis une zone de l'écran, savoir à quoi elle sert sans deviner quel chapitre la
// couvre. Une phrase au survol, la bonne page au clic.
//
// UN registre, pas des chaînes éparpillées dans vingt vues : c'est lui qui rend la garde possible
// (`test_cockpit_helpspots.js` vérifie que chaque `topic` existe et que chaque `anchor` est un
// titre réel de la page). Un repère qui pointe une page disparue est pire que pas de repère.
//
//   id     : identifiant stable de la zone (sert au test et au DOM)
//   sel    : où poser le repère — le premier élément trouvé gagne (plusieurs sélecteurs séparés par « , » possibles)
//   where  : "h2" (dans le titre du bloc) · "summary" · "first" (au début du conteneur)
//   tip    : LA phrase — ce que la zone sert à faire, pas ce qu'elle contient
//   topic  : page d'aide (`help/NN-<topic>.md`, préfixe d'ordre retiré)
//   anchor : titre de section dans cette page (facultatif) — le contrôleur y fait défiler

import { html } from "../../core/html.js";

export const HELP_SPOTS = [
  { id: "sessions-list", sel: "#hcnt", where: "first", topic: "sessions",
    tip: "Les sessions ouvertes : leur état, leur âge, ce qu'elles attendent — et la jauge de contexte de chacune." },
  { id: "sessions-launch", sel: "#launchcard", where: "h2", topic: "sessions",
    tip: "Ouvrir une session sur un ticket ou un dossier, avec son moteur et son modèle." },
  { id: "sessions-resume", sel: "#rescard", where: "h2", topic: "sessions",
    tip: "Reprendre une conversation passée là où elle s'était arrêtée." },
  { id: "sessions-sets", sel: "#sessions-set-card", where: "h2", topic: "sessions",
    tip: "Les jeux de sessions : des lots qu'on rouvre ensemble d'un clic." },
  { id: "tickets-search", sel: "#searchcard", where: "h2", topic: "tickets",
    tip: "Chercher un ticket par numéro, titre ou mot-clé, dans tous les projets." },
  { id: "tickets-triage", sel: "#triagecard", where: "summary", topic: "tickets",
    tip: "Les tickets qui attendent une décision de ta part avant d'être planifiés." },
  { id: "worklog", sel: "#rp-state", where: "first", topic: "worklog",
    tip: "Le tableau de bord de la session : ce qu'elle a ouvert, ce qui attend, ce qui reste à faire.",
    anchor: "Le tableau de bord de la session" },
  { id: "right-tabs", sel: ".rnav", where: "first", topic: "onglets",
    tip: "Les onglets de la colonne de droite : chacun regarde la session sous un angle." },
  { id: "composer", sel: "#composer", where: "first", topic: "composer",
    tip: "Écrire à la session attachée sans passer par le terminal : brouillon, envoi, modèles." },
  { id: "testqueue", sel: "#tqcard", where: "h2", topic: "tests",
    tip: "Ce qui est livré et attend ton test, ticket par ticket." },
  { id: "journal", sel: "#journalcard", where: "h2", topic: "journal",
    tip: "Le journal du serveur et du front : ce que le cockpit a fait, et ce qu'il a refusé." },
  { id: "cdc", sel: "#cdccard", where: "h2", topic: "cdc",
    tip: "Le cahier des charges vivant du projet : fonctionnalités, décisions, questions ouvertes." },
];

export const SPOT_ATTR = "data-helpspot";
/** Préférence locale (ce navigateur) — les repères sont AFFICHÉS par défaut : leur raison d'être
 *  est de se faire remarquer par qui ne connaît pas encore l'écran. */
export const SPOT_KEY = "karlHelpSpots";

export function spotsEnabled(storage) {
  try { return storage ? storage.getItem(SPOT_KEY) !== "0" : true; } catch (e) { return true; }
}

export function setSpotsEnabled(storage, on) {
  try { if (storage) storage.setItem(SPOT_KEY, on ? "1" : "0"); } catch (e) { /* navigation privée : la préférence ne survit pas, le cockpit si */ }
  return !!on;
}

export function spotById(id) { return HELP_SPOTS.find(s => s.id === id) || null; }

/** L'ordre des `topic` cités, dédupliqué — sert à la garde de test et à rien d'autre. */
export function spotTopics() { return [...new Set(HELP_SPOTS.map(s => s.topic))]; }

/** Le repère : un BOUTON (il se tabule et s'annonce), rendu par le micro-framework — donc échappé,
 *  comme tout ce qui entre dans le DOM (garde de `test_cockpit_core`). */
export function spotFrag(spot) {
  return html`<button class="helpq hspot" data-helpspot="${spot.id}" type="button" title="${spot.tip + "\n(clic : l'aide de cette zone)"}" aria-label="${"Aide : " + spot.tip}">?</button>`;
}
/** La même chose en chaîne — pour les tests et les vues qui composent du `html` ailleurs. */
export function spotHtml(spot) { return String(spotFrag(spot)); }

/** Où insérer, pour une zone donnée : l'élément hôte, ou null s'il n'est pas (encore) à l'écran. Pure vis-à-vis du DOM passé. */
export function spotHost(doc, spot) {
  const root = doc.querySelector(spot.sel);
  if (!root) return null;
  if (spot.where === "h2") return root.querySelector("h2") || root;
  if (spot.where === "summary") return root.querySelector("summary") || root;
  return root;
}
