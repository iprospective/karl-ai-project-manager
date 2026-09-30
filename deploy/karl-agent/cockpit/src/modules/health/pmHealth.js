// models/health/pmHealth — la santé du SYSTÈME PM, côté front (RM3369). Pur.
//
// Le badge d'en-tête ne compte QUE les soucis majeurs (`error`). C'est la même
// discipline que le badge du poste : un compteur qui affiche un chiffre tous les
// jours ne se regarde plus, et le jour où il compte quelque chose de grave,
// personne ne le voit. Les avertissements voyagent avec le rapport et se lisent
// dans la page ; ils ne font pas monter le nombre.

/** Le badge : combien, de quelle couleur, et ce que dit le survol. */
export function healthBadgeState(check) {
  const c = check || {};
  const items = c.items || [];
  const major = Number(c.major || 0);
  if (!major) return { show: false, count: 0, cls: "", title: "", pending: items.length };
  const graves = items.filter(i => i.level === "error");
  const lignes = graves.slice(0, 8).map(i => "• " + (i.family || "") + " — " + (i.label || "")
                                          + (i.detail ? " : " + i.detail : ""));
  if (graves.length > 8) lignes.push("… et " + (graves.length - 8) + " autre(s)");
  const autres = items.length - graves.length;
  if (autres > 0) lignes.push("(+ " + autres + " avertissement(s) dans le détail)");
  return {
    show: true, count: major, cls: "ew-error", pending: items.length,
    title: major + " souci(s) majeur(s) du système PM — clic : ouvrir le détail\n"
           + lignes.join("\n"),
  };
}

/** Ce que la page annonce en tête : ce qui va mal, dit en français. */
export function healthHeadline(status) {
  const s = status || {};
  const counts = (s.summary && s.summary.counts) || {};
  const err = Number(counts.error || 0), warn = Number(counts.warn || 0);
  if (s.error) return s.error;
  if (!s.groups || !s.groups.length) return "aucun rapport de santé n'a encore été produit";
  if (!err && !warn) return "rien à signaler";
  const bouts = [];
  if (err) bouts.push(err + " souci(s) majeur(s)");
  if (warn) bouts.push(warn + " avertissement(s)");
  return bouts.join(" · ");
}

/** L'âge d'un rapport, lisible. Le serveur date en secondes epoch. */
export function healthAge(generatedAt, now) {
  const t = Number(generatedAt || 0);
  if (!t) return "";
  const s = Math.max(0, Math.round(((now === undefined ? Date.now() : now) / 1000) - t));
  if (s < 90) return "il y a " + s + " s";
  if (s < 5400) return "il y a " + Math.floor(s / 60) + " min";
  if (s < 172800) return "il y a " + Math.floor(s / 3600) + " h";
  return "il y a " + Math.floor(s / 86400) + " j";
}
