// models/testqueue/testQueue — la file « à tester » : filtre, tri, gestes possibles. RM2889.
/** Match mots-clés (RM2315) : tous les mots (ET), sans casse ni accents, sur id, titre, projet, branche, env, statut, tags. */
export function tqMatch(e, q) {
  const norm = s => String(s == null ? "" : s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const words = norm(q).split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = norm(["rm" + e.rm_id, e.title, (e.client || "") + "/" + (e.project || ""), e.branch, e.env, e.status, (e.tags || []).join(" ")].join(" "));
  return words.every(w => hay.includes(w));
}
export const projectKey = (e) => (e.client || "?") + "/" + (e.project || "?");
export function filterQueue(all, f) {
  f = f || {};
  return (all || []).filter(e => (!f.project || projectKey(e) === f.project) && (!f.status || e.status === f.status) && (!f.deployable || e.deployable) && tqMatch(e, f.q || ""));
}
export function sortQueue(queue, sort) {
  const q = queue.slice(), upd = e => e.updated || "", rid = e => Number(e.rm_id) || 0;
  if (sort === "oldest") q.sort((a, b) => upd(a) < upd(b) ? -1 : upd(a) > upd(b) ? 1 : 0);
  else if (sort === "newest") q.sort((a, b) => upd(a) > upd(b) ? -1 : upd(a) < upd(b) ? 1 : 0);
  else if (sort === "rm-desc") q.sort((a, b) => rid(b) - rid(a));
  else if (sort === "rm-asc") q.sort((a, b) => rid(a) - rid(b));
  else if (sort === "project") q.sort((a, b) => projectKey(a).localeCompare(projectKey(b)) || rid(a) - rid(b));
  return q;
}
export const projectsOf = (all) => [...new Set((all || []).map(projectKey))].sort();
/** Les gestes d'environnement d'une entrée (RM2588 : cockpit_testable EN PREMIER). */
export function envActions(e) {
  if (e.cockpit_testable) {
    return e.env_live
      ? [{ action: "cockpit-teardown", label: "🧹 démonter l'instance" }]
      : [{ action: "cockpit-create", label: "🚀 (re)lancer l'instance de test", title: "(Re)lance une instance karl-agent de la BRANCHE du ticket en HTTPS (RM2565) et pose test_url" }, { action: "cockpit-teardown", label: "🧹 démonter", title: "Nettoyer un vhost/état résiduel" }];
  }
  if (e.env && e.env_live) return [{ action: "teardown", label: "🧹 démonter" }];
  if (e.env) return [{ action: "deploy", label: "🔁 re-déployer", title: e.env_reason || "env indisponible" }];
  if (e.deployable) return [{ action: "deploy", label: "🚀 déployer" }];
  return [{ action: null, label: "🚀 indisponible", title: "workspace hors layout repos/+envs/ — normaliser d'abord (mmi-pm env migrate)" }];
}
/** Le lien d'environnement d'une entrée : instance cockpit HTTPS, env docroot, ou rien. */
export function envLink(e) {
  if (e.cockpit_testable) return e.env_live && e.test_url ? { href: e.test_url, label: e.cockpit_host || e.test_url, live: true } : { warn: e.env_reason || "instance de test non lancée", label: "instance de test" };
  if (e.test_host && e.env_live) return { href: "http://" + e.test_host + "/", label: e.test_host, live: true };
  if (e.test_host) return { warn: e.env_reason || "env indisponible", label: e.test_host };
  return null;
}
