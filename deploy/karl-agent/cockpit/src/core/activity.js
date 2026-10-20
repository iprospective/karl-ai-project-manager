// core/activity — ce qui tourne en ce moment, et depuis combien de temps (RM3497).
//
// Une opération brève ne mérite pas qu'on affiche quoi que ce soit ; une opération
// longue, si. Mais la question n'est pas « cet appel est-il long ? » — c'est
// « suis-je en train d'attendre ? ». Quinze appels de 150 ms font deux secondes et
// demie d'attente qu'aucun seuil par appel ne verrait passer : le suivi est donc
// AGRÉGÉ, et le seuil s'applique à la rafale, pas à ses éléments.
//
// Aucun DOM ici : le module compte et prévient, l'affichage est ailleurs.

/** Au-delà de cette attente CONTINUE, on le montre. En deçà, on se tait. */
export const SEUIL_MS = 250;

let suivant = 1;
const encours = new Map();      // id → {libelle, debut}
let depuis = 0;                 // début de la rafale courante (0 = rien ne tourne)
const abonnes = new Set();
let minuteur = null;
let horloge = { now: () => Date.now(), set: (f, d) => setTimeout(f, d), clear: (t) => clearTimeout(t) };

/** Injecte une horloge (tests). Les natifs sont enveloppés : détachés, ils lèvent. */
export function configurerActivite(h) {
  horloge = Object.assign({}, horloge, h || {});
  return horloge;
}

function etat() {
  const n = encours.size;
  const attente = n && depuis ? horloge.now() - depuis : 0;
  // Le plus ANCIEN en cours : c'est lui qu'on attend, les autres sont arrivés depuis.
  let plus_vieux = null;
  for (const o of encours.values()) {
    if (!plus_vieux || o.debut < plus_vieux.debut) plus_vieux = o;
  }
  return {
    actif: n > 0 && attente >= SEUIL_MS,
    nombre: n,
    attente,
    libelle: (plus_vieux && plus_vieux.libelle) || "",
  };
}

function prevenir() {
  const e = etat();
  for (const f of abonnes) {
    try { f(e); } catch (_) { /* un abonné qui lève ne doit pas bloquer les autres */ }
  }
}

function armer() {
  if (minuteur || !encours.size) return;
  const reste = Math.max(0, SEUIL_MS - (horloge.now() - depuis));
  minuteur = horloge.set(() => { minuteur = null; prevenir(); }, reste);
}

function desarmer() {
  if (minuteur) { horloge.clear(minuteur); minuteur = null; }
}

/** Déclare une opération en cours. Rend la fonction qui la termine. */
export function debut(libelle = "") {
  const id = suivant++;
  if (!encours.size) depuis = horloge.now();
  encours.set(id, { libelle: String(libelle || ""), debut: horloge.now() });
  armer();
  let fini = false;
  return () => {
    if (fini) return;             // terminer deux fois ne doit rien casser
    fini = true;
    encours.delete(id);
    if (!encours.size) {
      // La rafale est finie : l'attente repart de zéro à la prochaine opération.
      depuis = 0;
      desarmer();
    }
    prevenir();
  };
}

/** Enveloppe une promesse : l'opération se termine qu'elle réussisse ou non. */
export function suivre(promesse, libelle) {
  const fin = debut(libelle);
  return Promise.resolve(promesse).finally(fin);
}

/** S'abonner aux changements. Rend la fonction de désabonnement. */
export function abonner(f) {
  abonnes.add(f);
  try { f(etat()); } catch (_) { /* idem */ }
  return () => abonnes.delete(f);
}

/** L'état courant, pour un affichage qui s'initialise. */
export function activite() { return etat(); }

/** Remet à zéro — tests seulement. */
export function _reinitialiser() {
  desarmer();
  encours.clear();
  depuis = 0;
  abonnes.clear();
}
