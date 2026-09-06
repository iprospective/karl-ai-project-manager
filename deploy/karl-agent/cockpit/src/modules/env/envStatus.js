// models/env/envStatus — la santé du poste, classée. RM2889, L5. Repris tel quel (RM2458, RM2708).

/** Un onglet par famille, avec ses compteurs de défauts — visibles SANS cliquer. */
export function envStatusTabs(groups) {
  return (groups || []).map(function (g) {
    let warn = 0, error = 0;
    (g.checks || []).forEach(function (c) { if (c.level === "warn") warn++; else if (c.level === "error") error++; });
    return { name: g.name || "", warn: warn, error: error, n: (g.checks || []).length };
  });
}

/** La page s'ouvre sur ce qui ne va pas : erreur, sinon avertissement, sinon la première. */
export function envStatusDefaultTab(tabs) {
  const ts = tabs || [];
  const bad = ts.find(t => t.error) || ts.find(t => t.warn) || ts[0];
  return bad ? bad.name : "";
}

/** Lignes d'une famille par `section` : sans-section en tête, puis EN DÉFAUT, puis alpha. */
export function envStatusSections(checks) {
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

/** Le bouton d'en-tête : montré seulement s'il y a un geste à faire, et son libellé DIT lequel. */
export function vaultBtnState(st) {
  if (!st) return { show: false, label: "", title: "" };
  const locked = st.locked || [];
  const keys = (st.ssh && st.ssh.keys) || [];
  const why = [];
  if (!st.daemon) why.push("coffre fermé (agent non démarré)");
  else if (locked.length === 1) why.push("coffre « " + locked[0] + " » verrouillé");
  else if (locked.length > 1) why.push(locked.length + " coffres verrouillés");
  if (!keys.length) why.push("agent SSH vide");
  if (!why.length) return { show: false, label: "", title: "" };
  return { show: true, label: "🔓 déverrouiller", title: why.join(" · ") + " — clic pour saisir le mot de passe" };
}
