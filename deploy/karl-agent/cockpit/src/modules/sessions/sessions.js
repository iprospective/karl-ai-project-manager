// models/sessions/sessions — la liste des sessions « en cours » : groupement, compteurs, tri, repli, silences. RM2889.
// Fonctions PURES déplacées d'index.html (marqueurs >>> <<< historiques) : aucun DOM ici, tout est testé sous node nu.
import { modelWindow as _MW, ctxPct as _PCT, fmtWin as _FW } from "../ticket/ticketFormat.js";   // RM3084


/** RM2445 : préfixe des groupes « vivantes d'un autre jeu » (RM2537 : suivi du chantier). */
export const OTHER_SETS_GROUP = "⋯ hors du jeu courant";

/** Groupement par client/projet (jonction directe, repli resolveCache, « divers »), compteurs d'états, ordre des groupes. */
export function computeGroups(sessions, rcache, dynamic) {
  const groups = new Map();
  const counts = { total: 0, attention: 0, choice: 0, idle: 0, working: 0, ghost: 0 };
  for (const s of sessions) {
    // RM2445 : une session VIVANTE d'un autre jeu n'est jamais masquée — elle est rangée à part (et badgée de son jeu).
    // RM2537 : « hors du jeu » ≠ « sans projet » : le client/projet reste dans la clé (groupes en fin de liste, cf. `last`).
    const r = rcache[s.rm_id];
    let key = (s.client && s.project) ? s.client + "/" + s.project
            : (r && r.found) ? r.client + "/" + r.project : "divers";
    if (!s.ghost && s.in_current === false) key = OTHER_SETS_GROUP + " · " + key;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(s);
    // RM2427 : une session ENREGISTRÉE non démarrée s'affiche mais ne tourne pas — comptée à part, hors compteurs d'activité.
    if (s.ghost) { counts.ghost++; continue; }
    counts.total++;
    if (s.state === "attention") counts.attention++;
    else if (s.state === "choice") counts.choice++;   // RM2327 : choix multiple
    else if (s.state === "idle") counts.idle++;
    else counts.working++;
  }
  // RM2344 : ordre STABLE par défaut (alphabétique pur). Le tri dynamique (⚠/❓ en tête puis activité récente —
  // RM2140/RM2283) ne s'applique QUE si `dynamic` est vrai.
  const att = g => g.some(s => s.state === "attention" || s.state === "choice") ? 1 : 0;
  const rec = g => Math.max(0, ...g.map(s => s.created || 0));
  const last = k => k.startsWith(OTHER_SETS_GROUP) ? 1 : 0;   // RM2537 : un groupe par chantier
  const keys = [...groups.keys()].sort((a, b) => (last(a) - last(b)) || (dynamic
    ? (att(groups.get(b)) - att(groups.get(a)) || rec(groups.get(b)) - rec(groups.get(a)) || a.localeCompare(b))
    : a.localeCompare(b)));
  return { keys, groups, counts };
}

/** RM2639 : la session appartient-elle au contexte client ? ctx vide → oui ; en attente (attention/choice) → jamais masquée (RM2445). */
export function sessionInClient(s, r, ctx) {
  if (!ctx) return true;
  const c = (s && s.client) || (r && r.found && r.client) || null;
  if (c === ctx) return true;
  return !!(s && (s.state === "attention" || s.state === "choice"));
}

/** RM2515 : disposition EFFECTIVE — ne vaut que sur `idle` (cède au live), « a_traiter » par défaut. */
export function effDisposition(state, disposition) {
  if (state !== "idle") return null;
  return disposition || "a_traiter";
}

/** RM2346 : en tri dynamique, gel du réordonnancement pendant l'interaction (survol, ou souris bougée < 2 s). Stable → jamais gelé. */
export function sortFrozen(dynSort, hot, msSinceMove) { return !!dynSort && (hot || msSinceMove < 2000); }

/** RM2515 : « terminé » (idle marqué à fermer) coule en bas ; sinon ordre stable par id. Trie EN PLACE, comme l'original. */
export function orderSessions(sessions) {
  const done = s => effDisposition(s.state, s.disposition) === "termine" ? 1 : 0;
  return sessions.sort((a, b) => (done(a) - done(b)) || (Number(a.rm_id) - Number(b.rm_id)));
}

/** RM2448/RM2537 : un groupe est-il replié ? « !clé » = dépli explicite d'un sous-groupe hors jeu, qui vainc le pli du préfixe. */
export function isCollapsed(collapsed, key) {
  if (collapsed.has("!" + key)) return false;
  return collapsed.has(key) || (key.startsWith(OTHER_SETS_GROUP) && collapsed.has(OTHER_SETS_GROUP));
}
/** Bascule le pli d'un groupe dans l'ensemble (muté), et le rend. */
export function toggleCollapsed(collapsed, key) {
  isCollapsed(collapsed, key) ? (collapsed.delete(key), collapsed.add("!" + key)) : (collapsed.delete("!" + key), collapsed.add(key));
  return collapsed;
}
/** L'ensemble replié par défaut : le préfixe « hors du jeu » seul. */
export function defaultCollapsed() { return new Set([OTHER_SETS_GROUP]); }

/** RM2787 : délai en heures ET minutes (« 2h14 ») ; sous l'heure les minutes, au-delà du jour les jours. */
export function agoHM(ts) {
  if (!ts) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "min";
  if (s < 86400) {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return m ? h + "h" + String(m).padStart(2, "0") : h + "h";
  }
  return Math.floor(s / 86400) + "j";
}
/** Délai tronqué à l'unité (identique au `ago` historique). */
export function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "min";
  if (s < 86400) return Math.floor(s / 3600) + "h";
  return Math.floor(s / 86400) + "j";
}

/** RM2793 : depuis quand la session se tait — le dernier vrai MESSAGE prime (les récapitulatifs automatiques n'en sont pas),
 *  l'activité tmux est un repli approximatif. */
export function quietSince(s) {
  const sess = s || {};
  if (sess.last_msg) return { ts: sess.last_msg, exact: true };
  if (sess.activity) return { ts: sess.activity, exact: false };
  return { ts: null, exact: false };
}

/** RM2787/RM2793 : le silence prêt à afficher — texte (« ⏳2h14 », « ~ » si approximatif) et infobulle qui NOMME la mesure. */
export function quietInfo(s) {
  const q = quietSince(s); if (!q.ts) return null;
  const d = agoHM(q.ts);
  return { d, exact: q.exact, text: "⏳" + d + (q.exact ? "" : "~"),
    title: q.exact ? "Dernier message il y a " + d + " (les récapitulatifs automatiques ne comptent pas)" : "Dernière sortie du terminal il y a " + d + " — transcript indisponible pour cette session" };
}

/** RM2327/RM2699 : durée restante lisible d'un auto-oui (epoch s → « 12 min », « 1 h 59 min ») — minutes TRONQUÉES. */
export function autoYesLeft(until) {
  const s = Math.max(0, Math.round(until - Date.now() / 1000));
  return s >= 3600 ? Math.floor(s / 3600) + " h " + Math.floor((s % 3600) / 60) + " min" : Math.max(1, Math.round(s / 60)) + " min";
}

/** RM2332 : « ✔ Oui » (barre du terminal + header) visible quand la session AFFICHÉE attend une réponse. */
export function approveShortcutVisible(attached, cache) { return !!attached && ((cache[attached] || {}).state === "attention"); }

/** Identifiant affiché : RM<id> pour un ticket, le slug tel quel sinon (RM2144). */
export function displayId(s, sid) { const id = String(sid == null ? (s || {}).rm_id : sid); return (s && s.is_ticket === false) ? id : "RM" + id; }

/** Nom tmux d'une session (karl-RM<id> ou karl-<slug>). */
export function tmuxName(id) { return (/^\d+$/.test(String(id)) ? "karl-RM" : "karl-") + id; }

/** RM2439/RM2949 : politique de reprise d'une session enregistrée, en clair. */
export function restartTip(policy) {
  return policy === "auto"
    ? "Redémarre toute seule au lancement de karl-agent (clic : la mettre en attente)"
    : "Attend un clic pour démarrer (clic : la faire redémarrer toute seule)";
}

/** Infobulle d'une tuile vivante (`r` = entrée resolveCache éventuelle) — RM2787/RM2793 : silence nommé. */
export function tabTip(s, r) {
  let t = s.tmux || tmuxName(s.rm_id);
  if (r && r.found) t = "RM" + s.rm_id + " — " + (r.title || "") + "\n" + r.client + "/" + r.project +
    (r.type ? " · " + r.type : "") + (r.status ? " · " + r.status : "");
  if (s.created) t += "\nouvert il y a " + ago(s.created);
  if (s.last_msg) t += "\ndernier message il y a " + agoHM(s.last_msg);    // RM2793
  else if (s.activity) t += "\ndernière sortie il y a " + agoHM(s.activity);   // RM2787
  if (s.attached) t += " · attaché";
  if (s.state === "attention") t += "\n⚠ demande une réponse OUI/NON (permission/question)";
  else if (s.state === "choice") t += "\n❓ question à choix multiple — réponds dans le terminal";
  else if (s.state === "idle") t += "\n💤 au repos (tour fini ou en attente de consigne)";
  (s.registry_conflicts || []).forEach(c => { t += "\n⚠ RM" + c.rm_id + " aussi ouvert en session " + c.seqs.map(x => "#" + x).join(", "); });
  const ctx = contextLine(s);            // RM3084 : le contexte se lit au survol, même loin de tout palier
  if (ctx) t += "\n" + ctx;
  return t;
}

/** RM3084 — « contexte : 197k / 1M (20 %) · opus-5 », ou "" si le transcript n'en dit rien.
 *  Les fonctions de format sont injectées (mêmes que la jauge et l'encart infos : une seule vérité). */
export function contextLine(s, fns) {
  const f = fns || {};
  const ctx = Number((s || {}).context || 0);
  if (!ctx) return "";
  const win = (f.modelWindow || _MW)(s.model, s.rates, ctx);
  const pct = (f.ctxPct || _PCT)(ctx, win);
  const fw = f.fmtWin || _FW;
  return "contexte : " + fw(ctx) + (win ? " / " + fw(win) : "") + (pct != null ? " (" + pct + " %)" : "")
    + (s.model ? " · " + String(s.model).replace(/^claude-/, "") : "");
}

/** Infobulle d'une tuile grise (RM2427/RM2949 : dire l'état réel de la conversation et ce que le clic fera). */
export function ghostTip(s, selMode) {
  return (selMode ? "Clic : retenir cette session pour un déplacement ou un nouveau jeu\n" : "") +
    "Session enregistrée — non démarrée\n" + (s.engine ? "moteur : " + s.engine + "\n" : "") + (s.cwd ? "dossier : " + s.cwd + "\n" : "") +
    (s.resumable ? "conversation mémorisée\n(clic : reprendre cette session)" : "conversation perdue (purgée)\n(clic : ouvrir une session neuve dans ce dossier)");
}

/** Message du toast après « ✔ tout » (RM2327). */
export function approveAllMessage(r) {
  const list = (r && r.approved) || [];
  return list.length ? "✔ Oui envoyé à " + list.length + " session(s) : " + list.map(a => (/^\d+$/.test(a.rm_id) ? "RM" : "") + a.rm_id).join(", ")
    : "Aucune session ne posait de question";
}
/** Message du toast après « ✔ Oui » sur une session. */
export function approveMessage(rmId, r) {
  return "✔ Oui envoyé à " + (/^\d+$/.test(String(rmId)) ? "RM" + rmId : rmId) + ((r || {}).sent === "y" ? " (y + Entrée)" : " (option 1)");
}

/** RM3082 — jauge de contexte d'une session : ce que la tuile a besoin de savoir, ou `null`.
 *
 * Le pourcentage se lit contre la FENÊTRE DU MODÈLE (`modelWindow`, la règle de l'encart méta —
 * une seule vérité sur « 76 % »). Sous le premier palier : `null`, donc silence total — un signal
 * permanent qui parle tout le temps ne se lit plus quand il compte.
 *
 * `thresholds` = { warn, high, crit } en % (réglables, cf. conf sessions.context_*_pct).
 * Rend { pct, level: "warn"|"high"|"crit", label, title, width }.
 */
export function contextGauge(session, thresholds, ctxPctFn, modelWindowFn, fmtWinFn) {
  const s = session || {}, ctx = Number(s.context || 0);
  if (!ctx) return null;                                   // pas de tour lu dans la queue : rien, jamais de chiffre faux
  const win = modelWindowFn(s.model, s.rates, ctx);
  const pct = ctxPctFn(ctx, win);
  if (pct == null) return null;                            // modèle inconnu → pas de fenêtre → pas de jauge
  const th = thresholds || {};
  const warn = Number(th.warn || 50), high = Number(th.high || 75), crit = Number(th.crit || 90);
  const level = pct >= crit ? "crit" : pct >= high ? "high" : pct >= warn ? "warn" : "";
  if (!level) return null;
  const quoi = level === "crit" ? "la conversation va être compactée : consigne (think) puis repars sur une session neuve"
    : level === "high" ? "il reste peu de marge avant compaction"
    : "la moitié de la fenêtre est occupée";
  return { pct, level, label: pct + " %", width: Math.min(100, pct),
    title: "contexte : " + fmtWinFn(ctx) + " / " + fmtWinFn(win) + " (" + pct + " %)"
      + (s.model ? "\nmodèle : " + s.model : "") + "\n" + quoi };
}

/** RM3082 — le palier a-t-il MONTÉ depuis le dernier rendu ? C'est ce franchissement, et lui seul,
 * qui mérite une animation : l'état permanent se lit sans bouger. Pure ; `seen` est muté (Map). */
export function contextCrossed(rmId, level, seen) {
  const RANK = { "": 0, warn: 1, high: 2, crit: 3 };
  const key = String(rmId), before = seen.get(key) || "";
  if (RANK[level] === RANK[before]) return false;
  seen.set(key, level);
  return RANK[level] > RANK[before] && !!level;
}
