// models/sessions/unseen — les sessions « à voir » (RM3236) : celles qui ont FINI leur tour pendant qu'on regardait ailleurs.
// Fonctions PURES, aucun DOM : testées sous node nu (test_cockpit_sessions.unseen.js).
//
// Le bandeau « à traiter » (RM2346) ne réagit qu'aux QUESTIONS (attention/choice). Une session qui termine son tour
// (working → idle) ne disait rien — c'est pourtant le cas le plus fréquent, et on la laissait attendre sans le savoir.

/** États où une session attend quelqu'un : tour fini, question OUI/NON, choix multiple. */
export const WAITING = new Set(["idle", "attention", "choice"]);

const k = (rm) => String(rm);

/**
 * Nouvel état « à voir » après un passage du registre /sessions.
 *
 * - `prev`   : Map rm → dernier état observé (MUTÉE : c'est la mémoire des transitions).
 * - `unseen` : Set des rm à voir (non muté — on rend un nouveau Set).
 * - `watching(rm)` : vrai si l'utilisateur REGARDE cette session (attachée ET onglet visible).
 *
 * Une session devient à voir en passant de `working` à un état d'attente sans être regardée. Elle cesse de l'être
 * quand on la regarde, quand elle se remet à travailler d'elle-même (auto-oui, relance), ou quand elle disparaît.
 * Sans état précédent connu (premier chargement), on ne marque RIEN : on ignore ce qui a déjà été vu.
 */
export function trackUnseen(prev, unseen, sessions, watching) {
  const next = new Set(unseen);
  const alive = new Set();
  for (const s of sessions || []) {
    if (!s || s.ghost) continue;
    const id = k(s.rm_id), st = s.state || "idle", before = prev.get(id);
    alive.add(id);
    prev.set(id, st);
    if (watching(s.rm_id)) { next.delete(id); continue; }
    if (!WAITING.has(st)) { next.delete(id); continue; }              // repart d'elle-même : plus rien à voir
    if (before === "working") next.add(id);                           // la transition qui compte : elle vient de finir
  }
  for (const id of [...prev.keys()]) if (!alive.has(id)) prev.delete(id);
  for (const id of [...next]) if (!alive.has(id)) next.delete(id);   // fermée, tuée, sortie du jeu
  return next;
}

/** Relecture tolérante du stockage : un JSON illisible vaut « rien à voir », jamais une erreur. */
export function parseUnseen(raw) {
  try { const a = JSON.parse(raw || "[]"); return new Set(Array.isArray(a) ? a.map(k) : []); }
  catch (e) { return new Set(); }
}

/** Nombre de sessions à voir dans un groupe (un groupe replié cache ses tuiles, donc leur clignotement). */
export function unseenIn(group, unseen) { return (group || []).filter(s => s && !s.ghost && unseen.has(k(s.rm_id))).length; }
