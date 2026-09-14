// core/status — LA table des statuts de ticket : famille, ordre de lecture, couleur (RM3126).
//
// Elle vivait dans `modules/tickets/openedTickets.js` (RM2883) et n'était donc lisible que par ce
// module ; les quatre autres vues qui affichent un statut (revue, worklog, projets, panneau de droite)
// le rendaient chacune en pastille grise. D'où la demande : « code couleur des tickets par statut, à
// répercuter PARTOUT ». Monter la table dans le socle est la condition pour que « partout » soit tenable
// — sinon chaque vue se refait sa propre table, et elles divergent au premier statut ajouté.
//
// `openedTickets.js` ré-exporte les deux fonctions d'origine : aucun appelant n'a à bouger.

/** Ordre de LECTURE, pas alphabétique : ce qui réclame une action d'abord, ce qui est clos en dernier ;
 *  l'inconnu avant « fermé » (il demande un regard, un ticket clos non). */
export function ticketStatusRank(status) {
  const ordre = ["a_corriger", "en_cours", "a_tester_demandeur", "a_tester_dev", "a_mep",
                 "a_tester_preprod", "a_mep_prod", "en_mep", "a_faire",
                 "etude_chiffrage_a_valider", "etude_chiffrage_en_cours", "a_etudier_chiffrer",
                 "nouveau", "en_pause"];
  const s = String(status || "").toLowerCase();
  if (s === "ferme" || s === "fermé") return 99;
  const i = ordre.indexOf(s);
  return i < 0 ? 98 : i;
}

/** RM2883 : la FAMILLE d'un statut. Un statut inconnu tombe dans « autre », jamais d'office dans
 *  « à faire » — un ticket mal rangé doit se voir, pas se fondre dans la masse. */
export function ticketStatusFamily(status) {
  const s = String(status || "").toLowerCase();
  if (s === "ferme" || s === "fermé") return "ferme";
  if (s === "en_pause") return "pause";
  if (s === "a_mep" || s === "a_tester_preprod" || s === "a_mep_prod" || s === "en_mep") return "mep";
  if (s === "a_tester_dev" || s === "a_tester_demandeur") return "test";
  if (s === "en_cours" || s === "etude_chiffrage_en_cours") return "encours";
  if (["nouveau", "a_faire", "a_etudier_chiffrer", "etude_chiffrage_a_valider",
       "a_corriger"].indexOf(s) >= 0) return "todo";
  return "autre";
}

/** Libellés des familles, dans l'ordre de lecture — sert aux filtres comme aux légendes. */
export const STATUS_FAMILIES = Object.freeze([
  ["todo", "à faire"], ["encours", "en cours"], ["test", "à tester"],
  ["mep", "à MEP"], ["pause", "en pause"], ["ferme", "clôturé"], ["autre", "autre"],
]);

/** La classe CSS d'un statut — `st-<famille>`, à poser sur la pastille.
 *
 *  Une CLASSE, pas une couleur en dur : la palette vit dans la feuille de style (_entities.scss),
 *  donc elle suit le thème et se change en un endroit. Une vue qui écrirait `style="color:…"`
 *  recréerait exactement la divergence que ce module supprime.
 */
export function statusTone(status) {
  // Un statut ABSENT n'est pas un statut INCONNU. Rien (chantier libre, ligne sans phase) ne
  // reçoit aucune classe : pas d'information, pas de couleur. `st-autre` — la teinte d'alerte —
  // est réservée à un statut RENSEIGNÉ qu'on ne sait pas classer, c'est-à-dire à un ticket
  // réellement mal rangé. Confondre les deux ferait crier au rouge sur des lignes parfaitement
  // normales, et la teinte d'alerte cesserait d'alerter.
  const s = String(status == null ? "" : status).trim();
  if (!s || s === "?" || s === "—") return "";
  return "st-" + ticketStatusFamily(s);
}

/** Le libellé lisible d'un statut (`a_tester_demandeur` → « à tester »), pour les surfaces étroites.
 *  Rend le statut brut si on ne le connaît pas : mieux vaut un mot technique qu'un mensonge. */
export function statusLabel(status) {
  const f = ticketStatusFamily(status);
  if (f === "autre") return String(status || "");
  return (STATUS_FAMILIES.find(([k]) => k === f) || [, ""])[1];
}

/** La classe COMPLÈTE d'une pastille de statut — `pill` seul quand il n'y a pas de famille.
 *
 *  Existe pour que les vues n'aient pas à écrire `class="pill ${statusTone(x)}"` : cette forme
 *  laisse une espace parasite (`class="pill "`) dès que la famille est vide, ce qui pollue le
 *  balisage et fait échouer les tests qui le verrouillent au caractère près.
 */
export function pillClass(status, extra) {
  return ["pill", statusTone(status), extra || ""].filter(Boolean).join(" ");
}
