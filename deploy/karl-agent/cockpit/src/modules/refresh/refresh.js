// models/refresh/refresh — la pile de refresh (RM2763), sa cadence (RM2613), les questions sans réponse (RM2598), la santé de l'agent
// et la MAJ du core (RM2571). Fonctions PURES : aucun DOM, aucun réseau. RM2889.

/** RM2763 : période propre de chaque bloc (0 = à chaque tick). */
export const REFRESH_PERIOD_MS = { sessions: 0, health: 15000, worklog: 10000, pending: 45000, dashboard: 30000, vault: 60000, envcheck: 300000, pmhealth: 300000, coreupdate: 300000 };

/** RM2613 : cadence du poll quand l'onglet est visible — 3 s si une session attend une réponse, 7 s au calme.
 *  RM3006 : quand le canal de push est vivant, le tick n'est plus qu'une réconciliation — 6 s / 30 s. */
export function pollDelay(hot, pushed) { return pushed ? (hot ? 6000 : 30000) : (hot ? 3000 : 7000); }
export const ALL_BLOCKS = ["sessions", "health", "pending", "dashboard", "vault", "envcheck", "pmhealth", "coreupdate", "worklog"];

/** RM2598 : rm_ids des sessions avec une question laissée SANS RÉPONSE (kind « stale ») ; les « live » sont déjà signalées ⚠/❓. */
export function pendStaleSet(entries) {
  const s = new Set();
  for (const e of entries || []) if (e && e.kind === "stale") s.add(String(e.rm_id));
  return s;
}

/** Un bloc est dû s'il est forcé (`includes`), jamais reçu, ou plus vieux que sa période. */
export function refreshDue(name, at, includes, now) {
  if ((includes || []).includes(name)) return true;
  const t = at[name];
  return t === undefined || (now - t) >= REFRESH_PERIOD_MS[name];
}

/**
 * Les specs `bloc:hash` du prochain composite. Le worklog n'embarque que si une session est attachée ET l'onglet visible ; changer de
 * session oublie le hash worklog (il désignait l'autre session). Rend aussi le sid worklog à mémoriser.
 */
export function buildSpecs({ hashes, at, includes, now, dashboardVisible, attached, worklogVisible, worklogSid }) {
  const specs = [], h = hashes || {};
  const due = (n) => refreshDue(n, at || {}, includes, now);
  if (due("sessions")) specs.push("sessions:" + (h.sessions || ""));
  if (due("health")) specs.push("health:" + (h.health || ""));
  if (due("pending")) specs.push("pending:" + (h.pending || ""));
  if (dashboardVisible && due("dashboard")) specs.push("dashboard:" + (h.dashboard || ""));
  if (due("vault")) specs.push("vault:" + (h.vault || ""));
  if (due("envcheck")) specs.push("envcheck:" + (h.envcheck || ""));
  if (due("pmhealth")) specs.push("pmhealth:" + (h.pmhealth || ""));   // RM3369 : lecture d'un fichier, pas un calcul
  if (due("coreupdate")) specs.push("coreupdate:" + (h.coreupdate || ""));
  let resetWorklogHash = false, sid = worklogSid;
  if (attached && worklogVisible && due("worklog")) {
    if (sid !== String(attached)) { resetWorklogHash = true; sid = String(attached); }
    specs.push("worklog:" + String(attached) + ":" + (resetWorklogHash ? "" : (h.worklog || "")));
  }
  return { specs, worklogSid: sid, resetWorklogHash };
}

/** Le bloc sessions embarque la résolution brève : semée en `partial`, jamais par-dessus une résolution riche. */
export function seedBriefs(briefs, resolveStore) {
  if (!resolveStore) return;
  Object.entries(briefs || {}).forEach(([rm, br]) => {
    const cur = resolveStore.get(rm);
    if (cur === undefined || (cur && cur.partial)) resolveStore.set(rm, Object.assign({}, br, { partial: true }));
  });
}

/** RM2889 : la pastille de santé — le « tmux ok » vit dans 🩺 poste, l'en-tête ne garde que la joignabilité. */
export function healthState(h) { return { cls: "dot ok", title: "agent joignable · " + (h || {}).sessions + " session(s)", text: "" }; }
/** RM3000 : la version servie par /health face à celle du front — un écart = cache navigateur périmé ou déploiement partiel. */
export function versionMismatch(serverVersion, frontVersion) {
  if (!serverVersion || serverVersion === "?" || !frontVersion || serverVersion === frontVersion) return "";
  return "serveur v" + serverVersion + " ≠ front v" + frontVersion + " — recharger (Ctrl+F5) ou finir le déploiement";
}
export function healthKo(msg) { return { cls: "dot ko", title: "", text: "injoignable — " + msg }; }

/** RM2571 : le bouton « ⬆ MAJ dispo » — visible seulement si une MAJ existe ; l'infobulle dit d'où à où. */
export function coreUpdateState(d) {
  const u = d || {}; if (!u.available) return { on: false, text: "", title: "" };
  const l = (u.local || "").slice(0, 7), r = (u.remote || "").slice(0, 7);
  return { on: true, text: "⬆ MAJ dispo", title: "Mise à jour du code PM disponible sur « " + u.branch + " » : " + l + " → " + r + (u.stale ? " (état périmé : " + u.error + ")" : "") + " — clic pour la commande à lancer" };
}
/** RM2571 : la question posée avant de lancer. Le cockpit APPLIQUE la mise à jour quand la règle
 *  sudoers NOPASSWD est posée (`can_update`) ; sinon il dit la commande à lancer au terminal. */
export function coreUpdateText(d) {
  const u = d || {}; const l = (u.local || "?").slice(0, 7), r = (u.remote || "?").slice(0, 7);
  const tete = "Mise à jour du code PM disponible\n\nbranche : " + u.branch + "\ninstallé : " + l + "\ndisponible : " + r + "\n" + (u.checked_at ? "vérifié : " + u.checked_at + "\n" : "");
  if (!u.can_update) {
    return tete + "\nLe cockpit ne peut pas l'appliquer : la règle sudoers NOPASSWD du core update n'est pas posée sur cette instance.\n" +
      "À lancer dans un terminal (mot de passe sudo demandé) :\n\n  mmi-pm core-update\n\n(règle 2 de deploy/mmi-pm.sudoers.example — install-mmi-pm --print-sudoers)";
  }
  return tete + "\nLancer la mise à jour maintenant ?\n\nkarl-agent redémarre si son propre code a changé — le suivi continue, le cockpit se reconnecte tout seul.";
}
/** RM2571 : l'état du bouton pendant un run — libellé, infobulle, et s'il reste cliquable. */
export function coreUpdateRunState(d) {
  const r = d || {}; const n = (r.lines || []).length;
  if (r.running) return { on: true, busy: true, text: "⏳ MAJ en cours", title: "Mise à jour lancée " + (r.started_at || "") + (r.by ? " par " + r.by : "") + " — " + n + " ligne(s) de journal" };
  if (!r.started_at) return { on: false, busy: false, text: "", title: "" };
  return { on: true, busy: false, text: "✓ MAJ terminée", title: "Dernière mise à jour terminée (" + (r.started_at || "") + ") — clic pour relire le journal" };
}
/** RM2571 : le compte rendu d'un run — les dernières lignes du journal, telles quelles. */
export function coreUpdateLogText(d) {
  const r = d || {}; const lines = r.lines || [];
  const tete = (r.running ? "Mise à jour EN COURS" : "Mise à jour terminée") + (r.started_at ? " (lancée " + r.started_at + (r.by ? " par " + r.by : "") + ")" : "") + "\n\n";
  if (!lines.length) return tete + "(journal vide pour l'instant)";
  return tete + lines.slice(-40).join("\n");
}
