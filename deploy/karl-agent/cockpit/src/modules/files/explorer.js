// models/files/explorer — l'explorateur de fichiers (RM2586/2622/2659/2673) : ce qui se calcule sans DOM. RM2889.

/** Fil d'ariane cumulatif d'un chemin : racine « / » puis chaque segment avec son chemin cumulé. Slashes superflus tolérés. */
export function filesCrumbs(path) {
  const out = [{ name: "/", path: "" }];
  let acc = "";
  for (const seg of String(path || "").split("/").filter(Boolean)) { acc = acc ? acc + "/" + seg : seg; out.push({ name: seg, path: acc }); }
  return out;
}
/** RM2673 : QUOI lire. Une session attachée montre ses racines ; sinon le PROJET courant — fiche de ticket ouverte, fiche projet,
 *  ou règle du jeu courant. `from` DIT d'où vient ce qu'on affiche. Une vue par client ne désigne aucun projet : on ne devine pas. */
export function filesContext(ctx) {
  const c = ctx || {};
  if (c.attached) return { scope: "session", sid: String(c.attached) };
  const r = c.currentReview ? (c.resolveCache || {})[c.currentReview] : null;
  if (r && r.found && r.client && r.project) return { scope: "project", client: r.client, project: r.project, from: "ticket RM" + c.currentReview };
  const parts = String(c.currentProjectView || "").split("/");
  if (parts.length === 2 && parts[0] && parts[1]) return { scope: "project", client: parts[0], project: parts[1], from: "fiche projet" };
  const cur = (c.sets || []).find(s => s && s.name === c.currentSet);
  const rule = (cur && cur.rule) || null;
  if (rule && rule.client && rule.project) return { scope: "project", client: rule.client, project: rule.project, from: "jeu « " + (cur.label || cur.name) + " »" };
  return { scope: "none" };
}
/** Identité du contexte affiché — pour ne recharger que lorsqu'il change VRAIMENT (le poll repasse toutes les quelques secondes). */
export function filesCtxKey(ctx) {
  const c = ctx || {};
  if (c.scope === "session") return "s:" + c.sid;
  if (c.scope === "project") return "p:" + c.client + "/" + c.project;
  return "none";
}
/** RM2622 : la doc du projet n'est PAS un worktree — icône, libellé et infobulle propres. */
export function fileRootLabel(w) {
  const r = w || {};
  if (r.kind === "doc") return { icon: "📄", name: r.name === "docs" ? "docs" : "fiches", tip: (r.label || "documentation du projet") + (r.docs ? " — " + r.docs + " fichier" + (r.docs > 1 ? "s" : "") : "") + "\n" + (r.path || "") };
  if (r.kind === "root") return { icon: "🏠", name: r.name || "racine", tip: (r.label || "racine du workspace") + "\n" + (r.path || "") };
  return { icon: "", name: r.name || "?", tip: r.path || "" };
}
/** RM2659 : les racines lisibles, GROUPÉES PAR PROJET — racine du workspace, sa doc, puis les worktrees ouverts dedans.
 *  Un worktree hors de toute racine connue forme un groupe « hors projet ». RM2673 : un projet sans workspace garde sa DOC. */
export function filesGroups(projects, worktrees) {
  const gs = (projects || []).filter(p => p && (p.root || (p.docs || []).length)).map(p => ({
    key: (p.client || "") + "/" + (p.project || ""), label: p.project || p.name || "?", client: p.client || "", project: p.project || "", root: p.root || "",
    roots: (p.root ? [Object.assign({}, p, { path: p.root, kind: "root", label: "racine du workspace" })] : []).concat((p.docs || []).map(d => ({ path: d.path, name: d.name, kind: "doc", label: d.label, docs: d.docs }))),
  }));
  const orphans = [];
  for (const w of (worktrees || [])) {
    if (!w || w.exists === false || !w.path) continue;
    const g = gs.find(x => x.root && String(w.path).indexOf(x.root + "/") === 0);   // `x.root` vide ne rattache rien
    (g ? g.roots : orphans).push(Object.assign({}, w, { kind: "code" }));
  }
  if (orphans.length) gs.push({ key: "", label: "hors projet", client: "", project: "", root: "", roots: orphans });
  return gs.filter(g => g.roots.length);
}
/** Le groupe auquel appartient la racine courante — sinon le premier. */
export function filesGroupOf(groups, path) { const gs = groups || []; return gs.find(g => (g.roots || []).some(r => r.path === path)) || gs[0] || null; }
/** RM2622/RM2659 : la racine d'abord, puis le code, la doc en dernier — trois natures. */
export function sortRoots(wts) { const rang = w => (w.kind === "root" ? 0 : w.kind === "doc" ? 2 : 1); return (wts || []).slice().sort((x, y) => rang(x) - rang(y)); }
export function fmtKo(size) { return (Math.round((size || 0) / 102.4) / 10) + " Ko"; }
export function freshNav(wt) { return { wt: wt || null, path: "", entries: [], commits: null, file: null, showCommits: false, vocab: false, vocabQ: "", vocabMd: null }; }
