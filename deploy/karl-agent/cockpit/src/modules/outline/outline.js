// models/outline/outline — l'outline de conversation (RM2330/2549/2596/2601) : ce qui se calcule sans DOM. RM2889.

/** Les entrées servies par /outline : la clé de position est `line` (scrollback tmux) ou `n` (transcript). */
export function normalizeItems(items) { return (items || []).map(it => (it && it.line == null && it.n != null) ? Object.assign({}, it, { line: it.n }) : it); }

/** RM2596 : filtre les entrées sur une requête (texte OU corps complet), insensible à la casse ; vide → tout. */
export function outMatch(items, q) {
  q = String(q || "").trim().toLowerCase();
  if (!q) return items || [];
  return (items || []).filter(it => String(it.text || "").toLowerCase().includes(q) || String(it.full || "").toLowerCase().includes(q));
}
/** RM2601 : filtre de VUE — tout / moi (user) / questions. */
export function outByKind(items, filter) {
  if (filter === "user") return (items || []).filter(it => it && it.kind === "user");
  if (filter === "question") return (items || []).filter(it => it && it.kind === "question");
  return items || [];
}
export const OUT_FILTERS = ["all", "user", "question"];

/** RM2330 : cible de saut parmi les messages UTILISATEUR. dir=-1 : dernier user strictement AVANT pos (pos null =
 *  depuis la fin) ; dir=+1 : premier strictement APRÈS pos (null si pos null — déjà au direct). */
export function outlineStep(items, pos, dir) {
  const users = (items || []).filter(it => it.kind === "user");
  if (!users.length) return null;
  if (dir < 0) { const before = users.filter(it => it.line < (pos == null ? Infinity : pos)); return before.length ? before[before.length - 1] : null; }
  if (pos == null) return null;
  return users.find(it => it.line > pos) || null;
}

/** RM2549 : décor d'une entrée. Un état n'est jamais porté par la SEULE couleur : icône + libellé l'accompagnent. */
export function outlineDecor(it) {
  const kind = it && it.kind;
  if (kind === "question") {
    return (it && it.resolved)
      ? { icon: "❓", tag: "question", cls: "oq", label: "Question posée", title: "Question posée — réponse retenue : " + (it.answer || "?") }
      : { icon: "⚠", tag: "sans réponse", cls: "oq ounres", label: "Question sans réponse", title: "Question restée SANS RÉPONSE" };
  }
  if (kind === "answer") return { icon: "↩", tag: "réponse", cls: "oans", label: "Réponse retenue", title: "La réponse que tu as retenue" };
  if (kind === "user") return { icon: "🗣", tag: "", cls: "ouser", label: "Ton message", title: "Ton message" };
  return { icon: "⏺", tag: "", cls: "", label: "Assistant", title: "Assistant" };
}

/** RM2549 : question suivante restée sans réponse ; reboucle au début une fois la dernière dépassée. */
export function outlineNextUnresolved(items, pos) {
  const pending = (items || []).filter(it => it.kind === "question" && !it.resolved);
  if (!pending.length) return null;
  if (pos == null) return pending[0];
  return pending.find(it => it.line > pos) || pending[0];
}

/** Le texte complet d'une entrée, avec l'issue d'une question. */
export function outlineFull(it) {
  return (it.full || it.text)
    + (it.kind === "question" && it.resolved ? "\n\n→ Réponse retenue : " + it.answer : "")
    + (it.kind === "question" && !it.resolved ? "\n\n⚠ Cette question est restée SANS RÉPONSE." : "");
}
