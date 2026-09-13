// models/terminal/terminal — le terminal (RM2522 client maison / repli iframe, RM2561 origine du WebSocket, RM2807 opt-in) et le
// composer (RM2527 garde d'état, historique) : ce qui se calcule sans DOM. RM2889.

/** Le client xterm maison est le DÉFAUT ; `karl_noxterm=1` fait repli sur l'iframe (RM3124).
 *
 * Il avait été passé en opt-in par RM2807, « le temps de l'enquête mémoire ». L'enquête a
 * conclu : le coupable était un fan-out exponentiel ailleurs (2^N → N+1, garde
 * `!resolveInflight`), pas ce client — innocenté, mais jamais remis par défaut. L'oubli
 * rendait le terminal inutilisable À DISTANCE : seule l'iframe servait, et elle ne sait
 * viser que `hostname:7681`, un port du bridge LXC jamais exposé publiquement.
 */
export function termAvailable(storage, win) {
  try { if (storage && storage.getItem("karl_noxterm") === "1") return false; } catch (e) { /* stockage bloqué : on garde le défaut */ }
  return !!(win && win.KarlTerm && win.Terminal);
}
/** Le repli iframe est-il seulement joignable d'ici ? (RM3124)
 *
 * Non en accès proxifié : l'UI ttyd native exige la RACINE de son serveur — elle fetch
 * « /token » en absolu et ne survit pas au préfixe `/ttyd/`. Elle a donc besoin du port
 * dédié 7681, qui n'écoute que sur le bridge LXC. Le dire vaut mieux que de poser une
 * URL morte : le navigateur ne rend alors qu'un « impossible de se connecter » qui
 * n'apprend rien.
 */
export function iframeReachable(loc) { const p = loc && loc.port; return !(p === "" || p === "80" || p === "443"); }
/** RM2561 : servi par le vhost (port implicite), le WebSocket passe par le proxy de MÊME ORIGINE /ttyd ; en accès direct, repli :7681. */
export function termBase(cfg, loc) {
  if (cfg && cfg.ttyd_base) return cfg.ttyd_base;
  const proxied = loc.port === "" || loc.port === "80" || loc.port === "443";
  return proxied ? loc.origin + "/ttyd" : loc.protocol + "//" + loc.hostname + ":7681";
}
/** L'URL de l'iframe ttyd de repli. */
export function ttydUrl(cfg, loc, rmId) { const base = (cfg && cfg.ttyd_base) || (loc.protocol + "//" + loc.hostname + ":7681"); return base.replace(/\/+$/, "") + "/?arg=" + encodeURIComponent(rmId); }
/** RM2527 : un envoi texte pendant qu'un menu est ouvert SÉLECTIONNE des options — on refuse au clavier, on exige un geste explicite. */
export function composerGuard(state) {
  if (state === "choice") return { allow: false, warn: "Un menu de choix est ouvert dans la session : ton texte sélectionnerait des options au lieu de s'écrire." };
  if (state === "attention") return { allow: false, warn: "La session attend une réponse à une question : ton texte pourrait valider une option au lieu de s'écrire." };
  return { allow: true, warn: null };
}
/** Historique des envois : le plus récent en tête, sans doublon, plafonné. */
export function composerHistoryAdd(list, text, max) { const t = String(text == null ? "" : text).trim(); if (!t) return (list || []).slice(); const out = (list || []).filter(x => x !== t); out.unshift(t); return out.slice(0, max || 30); }
export const CMP_HIST_MAX = 30;
export const histKey = (rmId) => "karlComposerHist:" + rmId;
/** Les libellés du composer selon la garde. */
export function composerLabels(g) {
  return g.allow ? { btn: "Envoyer ⏎", title: "Envoyer à la session attachée (Entrée)", hint: "Entrée envoie · Maj+Entrée saute la ligne · ↑ historique · Échap rend la main au terminal" }
                 : { btn: "Envoyer quand même", title: "La touche Entrée est neutralisée tant qu'un menu est ouvert — ce bouton force l'envoi", hint: "Entrée neutralisée — réponds dans le terminal, ou force l'envoi" };
}
export function truncate(s, n) { s = String(s == null ? "" : s); return s.length > n ? s.slice(0, n) + "…" : s; }
/** RM2700 : le cookie de session même-origine posé depuis le token d'appareil, pour le gate Apache de /ttyd. */
export function sessionCookie(token, secure) { return "karl_session=" + encodeURIComponent(token) + "; Path=/; SameSite=Strict" + (secure ? "; Secure" : ""); }
