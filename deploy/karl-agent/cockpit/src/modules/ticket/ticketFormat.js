// models/tickets/ticketFormat — dérivations pures autour d'un ticket / d'une session. RM2889. Reprises telles quelles.
/** « il y a X » depuis un horodatage ISO minute — pour dater la version montrée (RM2630). */
export function sinceLabel(iso, now) {
  if (!iso) return "";
  const t = Date.parse(String(iso).replace(" ", "T"));
  if (isNaN(t)) return "";
  const min = Math.floor(((now === undefined ? Date.now() : now) - t) / 60000);
  if (min < 1) return "à l'instant";
  if (min < 60) return "il y a " + min + " min";
  const h = Math.floor(min / 60);
  if (h < 24) return "il y a " + h + " h";
  return "il y a " + Math.floor(h / 24) + " j";
}
/** RM3084 — fenêtres MAXIMALES connues, par famille de modèle. « Maximales » est le point : un même
 *  modèle est servi en 200k ou en 1M et bascule d'une variante à l'autre EN COURS de session. Annoncer
 *  la plus grande fait au pire croire à un peu trop de marge ; annoncer la plus petite affiche 99 %
 *  quand on en est à 20 %, déclenche une compaction inutile et brûle la crédibilité du signal.
 *  La source de vérité reste `pm.pricing.yml` (`context_window`) ; cette table est le repli. */
export const MODEL_WINDOWS = [
  [/opus-5|fable-5|mythos-5|sonnet-5/i, 1000000],
  [/opus-4|sonnet-4|haiku-4/i, 200000],
];

/** Fenêtre de contexte d'un modèle (RM2611, corrigée RM3084) : le PLUS GRAND entre ce que disent les
 *  tarifs et ce que la table sait de la famille. `null` si le modèle est inconnu — aucun pourcentage
 *  vaut mieux qu'un pourcentage faux. */
export function modelWindow(model, rates, contextLast) {
  const name = String(model || "");
  const declared = rates && rates.context_window ? Number(rates.context_window) : 0;
  const known = /\[1m\]/i.test(name) ? 1000000
    : (MODEL_WINDOWS.find(([rx]) => rx.test(name)) || [null, 0])[1];
  const best = Math.max(declared, known);
  if (best) return best;
  // Modèle jamais vu : au moins ne pas rapporter une occupation à une fenêtre plus petite qu'elle.
  const seen = Number(contextLast) || 0;
  if (seen > 200000) return 1000000;
  return /claude/i.test(name) ? 200000 : null;
}
export function ctxPct(contextLast, window) { if (!window || !contextLast) return null; return Math.round((Number(contextLast) / Number(window)) * 100); }
/** Débit moyen depuis la création : {tpm, uph} ou null si durée < 30 s. */
export function throughput(total, cost, createdMs, nowMs) {
  const dur = (Number(nowMs) - Number(createdMs)) / 1000;
  if (!isFinite(dur) || dur < 30) return null;
  return { tpm: Math.round(Number(total || 0) / (dur / 60)), uph: Number(cost || 0) / (dur / 3600) };
}
export function fmtUsd(x) { x = Number(x) || 0; return "$" + (Math.abs(x) < 1 ? x.toFixed(3) : x.toFixed(2)); }
export function fmtRate(r) { return r != null ? "$" + r : "?"; }
export function fmtWin(w) { w = Number(w) || 0; return w >= 1e6 ? (Math.round(w / 1e5) / 10) + "M" : Math.round(w / 1000) + "k"; }
/** Disposition EFFECTIVE d'une session (RM2515) : ne vaut que sur idle. */
export function effDisposition(state, disposition) { if (state !== "idle") return null; return disposition || "a_traiter"; }
/** Qui s'occupe DÉJÀ de ce ticket sans avoir fini (RM2818) : « terminé » ne compte pas, « parké » si. */
export function ticketBusySessions(payload, eff = effDisposition) {
  const rows = ((payload || {}).handled) || [];
  const busy = rows.filter(r => r && eff(r.state, r.disposition) !== "termine");
  return { alive: busy.filter(r => r.alive), stopped: busy.filter(r => !r.alive) };
}
