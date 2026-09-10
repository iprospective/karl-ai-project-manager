// models/projects/projectConfig — la conf structurée (meta.yml) projet / client (RM2531). Repris tel quel.
/** Args pour /pm/run : client (+ project), et chaque champ NON VIDE ; null si rien à faire. */
export function configArgs(scope, key, fields) {
  const parts = String(key || "").split("/");
  const args = { client: parts[0] };
  if (scope === "project") args.project = parts[1];
  let n = 0;
  const put = (k, v) => { if (v != null && String(v).trim() !== "") { args[k] = String(v).trim(); n++; } };
  put("name", fields.name);
  put("redmine_project_id", fields.redmine);
  if (scope === "project") { put("gitlab_repo", fields.repo); put("default_branch", fields.branch); }
  return n ? args : null;
}
/** Préremplissage du formulaire depuis la fiche chargée. */
export function configPrefill(scope, d) {
  d = d || {};
  return scope === "project"
    ? { name: d.name, redmine: d.redmine_project_id, repo: d.gitlab_repo, branch: d.default_branch }
    : { name: d.client_name, redmine: d.client_redmine_project_id };
}
/** Fil d'ariane d'un chemin relatif (racine « / »). */
export function crumbs(path) {
  const out = [{ name: "/", path: "" }]; let acc = "";
  for (const seg of String(path || "").split("/").filter(Boolean)) { acc = acc ? acc + "/" + seg : seg; out.push({ name: seg, path: acc }); }
  return out;
}
