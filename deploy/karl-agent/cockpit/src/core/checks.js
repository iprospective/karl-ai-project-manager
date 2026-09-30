// core/checks — LA présentation d'un rapport « familles → lignes » (RM3369).
//
// Ces trois fonctions vivaient dans `modules/env/envStatus.js` et n'étaient donc
// lisibles que par la santé du POSTE. La santé du SYSTÈME PM (RM3369) rend
// exactement la même forme — des familles, des lignes `level`/`label`/`detail`/`fix`
// — et les redéclarer aurait donné deux tables qui divergent au premier ajout.
// Même geste qu'en RM3126 pour la table des statuts : on monte dans le socle,
// l'origine ré-exporte, aucun appelant n'a à bouger.

/** Un onglet par famille, avec ses compteurs de défauts — visibles SANS cliquer. */
export function checkTabs(groups) {
  return (groups || []).map(function (g) {
    let warn = 0, error = 0;
    (g.checks || []).forEach(function (c) { if (c.level === "warn") warn++; else if (c.level === "error") error++; });
    return { name: g.name || "", warn: warn, error: error, n: (g.checks || []).length };
  });
}

/** La page s'ouvre sur ce qui ne va pas : erreur, sinon avertissement, sinon la première. */
export function checkDefaultTab(tabs) {
  const ts = tabs || [];
  const bad = ts.find(t => t.error) || ts.find(t => t.warn) || ts[0];
  return bad ? bad.name : "";
}

/** Lignes d'une famille par `section` : sans-section en tête, puis EN DÉFAUT, puis alpha. */
export function checkSections(checks) {
  const rank = { ok: 0, info: 0, warn: 1, error: 2 };
  const bySec = new Map();
  for (const c of checks || []) {
    const k = c && c.section ? String(c.section) : "";
    if (!bySec.has(k)) bySec.set(k, { name: k, checks: [], worst: 0 });
    const s = bySec.get(k);
    s.checks.push(c);
    s.worst = Math.max(s.worst, rank[(c && c.level) || "info"] || 0);
  }
  const out = [...bySec.values()];
  out.sort((a, b) => (a.name === "" ? -1 : b.name === "" ? 1 : 0) || (b.worst - a.worst) || a.name.localeCompare(b.name));
  return out;
}
