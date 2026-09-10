// models/files/scope — la portée qui AUTORISE la lecture d'un worktree (RM2761). Repris tel quel.
// On garde les DEUX portées quand on les connaît : le serveur autorise l'union session ∪ projet.
export function fsScope(wt, filesData, attached, projectKey) {
  const wtp = String(wt || ""), fd = filesData || {};
  const out = {};
  if (attached) out.sid = attached;
  const hit = (fd.projects || []).find(p => p && p.root && (wtp === String(p.root) || wtp.indexOf(String(p.root) + "/") === 0));
  const doc = /^doc:([^/]+)\/([^/]+)\/[^/]+$/.exec(wtp);   // RM3014 : racine documentaire désignée par projet:file
  if (hit && hit.client && hit.project) { out.client = hit.client; out.project = hit.project; }
  else if (doc) { out.client = doc[1]; out.project = doc[2]; }
  else if (fd.client && fd.project) { out.client = fd.client; out.project = fd.project; }
  else {
    const k = String(projectKey || "");
    if (k.indexOf("/") > 0) { out.client = k.split("/")[0]; out.project = k.split("/")[1]; }
  }
  return out;
}
/** Portée ⇄ étiquette `c:client/projet;s:sid`, pour voyager dans la clé d'onglet. */
export function scopeTag(scope) {
  const s = scope || {}, out = [];
  if (s.client && s.project) out.push("c:" + s.client + "/" + s.project);
  if (s.sid) out.push("s:" + s.sid);
  return out.join(";");
}
export function scopeFromTag(tag) {
  const out = {};
  String(tag || "").split(";").forEach(part => {
    if (part.indexOf("c:") === 0) { const p = part.slice(2).split("/"); if (p.length === 2 && p[0] && p[1]) { out.client = p[0]; out.project = p[1]; } }
    else if (part.indexOf("s:") === 0 && part.length > 2) out.sid = part.slice(2);
  });
  return (out.sid || out.client) ? out : null;
}
export function scopeQuery(scope) {
  const s = scope || {}, q = [];
  if (s.client && s.project) { q.push("client=" + encodeURIComponent(s.client)); q.push("project=" + encodeURIComponent(s.project)); }
  q.push("sid=" + encodeURIComponent(s.sid || ""));
  return q.join("&");
}
/** La requête d'un worktree DONNÉ : une portée explicite (capturée au clic) prime sur le contexte courant. */
export function fsQuery(wt, tag, ctx) {
  const c = ctx || {}, fd = c.filesData || {};
  const fixed = scopeFromTag(tag);
  const base = fixed ? scopeQuery(fixed)
    : (fd.client && fd.project && !c.attached)
      ? "client=" + encodeURIComponent(fd.client) + "&project=" + encodeURIComponent(fd.project)
      : "sid=" + encodeURIComponent(c.attached || "");
  return base + "&worktree=" + encodeURIComponent(wt || "");
}
