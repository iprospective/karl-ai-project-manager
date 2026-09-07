// models/sessions/sets — les JEUX de sessions (RM2395/2442/2445/2446/2447/2448/2449/2450/2451/2452/2536/2537/2673/2741/2955) : options des
// sélecteurs, nature d'un jeu créé, état du bouton « relancer », écriture possible, textes des confirmations et des toasts. Pur, sans DOM. RM2889.

/** RM2955 — options du sélecteur de la carte : le jeu COURANT est marqué, un jeu dérivé se signale (⚙). */
export function setEditOptions(sets, editing, current) {
  const cible = editing || current;
  return (sets || []).map(s => ({
    value: s.name,
    label: (s.derived ? "⚙ " : "") + (s.label || s.name) + " (" + (s.alive || 0) + "/" + (s.count || 0) + ")" + (s.name === current ? " ● courant" : ""),
    selected: s.name === cible,
  }));
}
/** Libellé d'un jeu (le slug reste la clé). */
export function setLabel(sets, name) { return ((sets || []).find(s => s && s.name === name) || {}).label || name; }
/** slug = clé du store (immuable, ^[a-z0-9][a-z0-9._-]{0,31}$) ; le libellé reste libre. */
export function slugifySet(label) {
  return String(label || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9._-]+/g, "-").replace(/^[^a-z0-9]+/, "").replace(/-+$/, "").slice(0, 32);
}
/** RM2741 — « ▶ relancer » n'a de sens qu'en vue du jeu, et compte ce qui sera relancé (les éteintes) ; sans `entries`, le total. */
export function relaunchBtnState(set, view) {
  const s = set || {};
  if (!s.exists || String(view || "set") !== "set") return { show: false, count: 0 };
  const entries = s.entries || [];
  const count = entries.length ? entries.filter(e => !(e && e.alive)).length : (s.count || 0);
  return { show: count > 0, count };
}
/** RM2673 — le jeu courant accepte-t-il une écriture manuelle ? Jamais sur un jeu DÉRIVÉ (400/404 serveur), jamais dans une vue par client (RM2536). */
export function setWritable(sets, name, view) {
  if (/^client:/.test(String(view == null ? "" : view))) return false;
  const cur = (sets || []).find(s => s && s.name === name);
  return !(cur && cur.derived);
}
/** RM2741 — la nature du jeu créé se DÉDUIT du formulaire : aucun critère → manuel (semé si demandé) ; un critère → dérivé (rien versé, et on le dit). */
export function newSetPlan(name, label, rule, sids, seed, existing) {
  if (!label) return { ok: false, error: "donne un nom au jeu" };
  if (!name) return { ok: false, error: "nom inexploitable — il faut au moins une lettre ou un chiffre" };
  if ((existing || []).indexOf(name) >= 0) return { ok: false, error: "le jeu « " + name + " » existe déjà" };
  const has = !!(rule && Object.keys(rule).length);
  const list = (sids || []).slice();
  const body = { group: name, label: label };
  if (has) body.rule = rule;
  else if (seed && list.length) body.sids = list;
  return { ok: true, kind: has ? "derived" : "manual", body, note: (has && seed && list.length) ? "règle renseignée : le contenu se calcule — les sessions affichées ne sont pas versées" : "" };
}
/** Les valeurs du formulaire → la règle (champs vides omis ; tickets séparés par des virgules). */
export function ruleFromValues(v) {
  v = v || {}; const rule = {};
  if (v.client) rule.client = v.client;
  if (v.project) rule.project = v.project;
  if (v.mark) rule.mark = v.mark;
  if (v.tag) rule.tag = v.tag;   // RM2830
  const tk = String(v.tickets || "").split(",").map(x => x.trim()).filter(Boolean);
  if (tk.length) rule.tickets = tk;
  return rule;
}
/** Résumé lisible d'une règle (« client=acme tickets=1,2 »). */
export function ruleSummary(rule) { return Object.entries(rule || {}).map(([k, v]) => k + "=" + (Array.isArray(v) ? v.join(",") : v)).join(" "); }

/** RM2446/2452/2954 — les groupes d'options du sélecteur de la barre : les VUES d'abord, les clients ayant des sessions, puis les jeux. */
export function pickerGroups(r, sets, current, view) {
  r = r || {};
  const vopt = (v, txt) => ({ value: "view:" + v, label: txt, selected: view === v });
  const groups = [{ label: "vues", options: [
    vopt("live", "▶ sessions ouvertes (" + (r.live_count || 0) + ")"),
    vopt("all", "⧉ tous les jeux (" + (r.all_count || 0) + ")"),
    vopt("sessions", "🗂 toutes les sessions (" + (r.sessions_count || 0) + ")"),
  ] }];
  const cviews = (r.client_views || []).map(c => ({ value: "view:" + c.view, label: "👤 " + c.label + " (" + c.count + ")", selected: view === c.view }));
  if (cviews.length) groups.push({ label: "clients", options: cviews });
  groups.push({ label: "jeux", options: (sets || []).length
    ? sets.map(s => ({ value: "set:" + s.name, label: s.label + " (" + (s.alive || 0) + "/" + s.count + ")", selected: view === "set" && s.name === current }))   // RM2447 : ouvertes / enregistrées
    : [{ value: "set:default", label: "default (0)", selected: false }] });
  return groups;
}
/** RM2448/2449/2452/2673/2741 — l'état des boutons de la barre : 💾 (ou « ＋ jeu (n) » en sélection), 🗑, destinations et « → déplacer ». */
export function barState({ sets, current, view, selMode, selectedCount }) {
  const label = setLabel(sets, current);
  const derivedNow = !setWritable(sets, current, view);
  const others = (sets || []).filter(s => s.name !== current && !s.derived);   // RM2673 : ni depuis ni vers un jeu dérivé
  return {
    saveShown: !(derivedNow && !selMode),
    saveLabel: selMode ? "＋ jeu (" + selectedCount + ")" : "💾 → " + label,
    saveTitle: selMode ? "Créer un jeu avec les " + selectedCount + " session(s) sélectionnée(s)"
      : "Ajoute les sessions AFFICHÉES au jeu « " + label + " ». N'efface jamais une session déjà enregistrée (RM2439) : pour en retirer une, ⊖ sur sa tuile",
    delTitle: "Supprimer le jeu « " + label + " » (les sessions continuent de tourner)",
    targets: others.map(s => ({ value: s.name, label: "vers " + s.label + " (" + s.count + ")" })),
    canMove: !!(selMode && others.length && setWritable(sets, current, view)),
  };
}
/** RM2741 : le bouton de sélection — icône seule, le title porte le sens. */
export function selButtonState(on) {
  return { text: on ? "✓" : "☑", title: on ? "Terminer la sélection" : "Sélection : choisir des sessions une à une — pour en faire un nouveau jeu, ou scinder le jeu courant" };
}
/** (RM)sid d'une entrée ou d'une session. */
export function sessionLabelOf(s) { return ((s && s.is_ticket === false) ? "" : "RM") + (s || {}).rm_id; }
export function entryLabel(sid) { return (/^\d+$/.test(String(sid)) ? "RM" : "") + sid; }
/** RM2949 : l'état d'une entrée se juge sur la conversation vérifiée par le serveur. */
export function entryState(e) { return e.alive ? "🟢 active" : (e.resumable ? "🟡 reprenable" : "🔴 perdue"); }
/** RM2439 : message après « 💾 ». */
export function saveSummary(r, label) {
  const n = ((r || {}).added || []).length;
  return (r || {}).count ? "💾 " + r.count + " session(s) dans « " + label + " »" + (n ? " (+" + n + " nouvelle" + (n > 1 ? "s" : "") + ")" : " (rien de neuf)") : "Aucune session à enregistrer";
}
export function viewMessage(view, currentLabel) { return view === "live" ? "vue : sessions ouvertes" : view === "all" ? "vue : tous les jeux" : "vue : jeu « " + currentLabel + " »"; }
/** RM2449 : déplacer ou copier — la question, puis le résumé. */
export function moveConfirmText(n, toLabel, fromLabel) { return n + " session(s) → « " + toLabel + " »\n\nOK = les DÉPLACER (retirées de « " + fromLabel + " »)\nAnnuler = les COPIER (elles restent dans les deux jeux)"; }
export function moveSummary(moved, move, toLabel) { return (move ? "→ " : "⧉ ") + (moved || []).length + " session(s) " + (move ? "déplacée(s) vers « " : "copiée(s) vers « ") + toLabel + " »"; }
/** RM2451 : dire le prix AVANT de relancer un jeu. */
export function relaunchConfirmText(e, label) {
  const kt = Math.round((e.tokens_est || 0) / 1000);
  return "Relancer " + e.relaunchable + " session(s) de « " + label + " » ?\n\nChacune rouvre un TUI et relit sa conversation : ~" + kt + " k tokens de contexte" +
    (e.usd_est ? ", de l'ordre de " + e.usd_est + " $" : "") + ".\n" + (e.already_live ? e.already_live + " déjà active(s), ignorée(s). " : "") + (e.lost ? e.lost + " sans conversation mémorisée (échouera). " : "");
}
export function relaunchSummary(counts) {
  const c = counts || {}, parts = [];
  if (c.resumed) parts.push(c.resumed + " reprise(s)"); if (c.skipped) parts.push(c.skipped + " déjà active(s)"); if (c.spawned) parts.push(c.spawned + " recréée(s)"); if (c.failed) parts.push(c.failed + " échec(s)");
  return { msg: "▶ " + (parts.join(" · ") || "rien à relancer"), failed: !!c.failed };
}
/** RM2450/RM2951 : tout ce qu'un lancement (spawn OU reprise) doit signaler — jeu plein, moteur bloqué. */
export function spawnWarnings(r, labelOf) {
  const out = []; const s = r && r.set;
  if (s && s.joined === false && s.reason === "plein") out.push("⚠ le jeu « " + labelOf(s.group) + " » est plein (" + s.max + ") : la session tourne mais n'y a PAS été enregistrée");
  if (r && r.blocked) out.push("⚠ " + r.blocked);
  return out;
}
/** RM2427/RM2536/RM2949 : la question posée avant de relancer UNE session enregistrée. */
export function ghostRelaunchText(s) {
  const label = sessionLabelOf(s), neuve = !s.resumable;
  const lines = [(neuve ? "Ouvrir une session NEUVE pour " : "Relancer la session ") + label + " ?", ""];
  if (s.engine) lines.push("moteur : " + s.engine); if (s.cwd) lines.push("dossier : " + s.cwd); if (s.model) lines.push("modèle : " + s.model);
  lines.push("", neuve ? "La conversation enregistrée n'existe plus (purgée) : rien à reprendre.\nUne session neuve démarrera dans ce dossier, SANS le contexte d'avant." : "La conversation enregistrée sera reprise.");
  return { neuve, label, text: lines.join("\n"), start: "▶ " + (neuve ? "session neuve pour " : "relance de ") + label + "…" };
}
export function restartMessage(next, label) { return next === "auto" ? "⟳ " + label + " redémarrera toute seule" : "⏸ " + label + " attendra un clic"; }
export function retentionMessage(days) { return Number(days) ? "les sessions inactives depuis " + days + " j sont masquées (jamais supprimées)" : "plus rien n'est masqué"; }
/** RM2443 : les versions archivées qui contiennent le jeu réglé. */
export function historyFor(versions, name) { return (versions || []).filter(v => (v.sets || []).some(s => s.name === name)).map(v => ({ id: v.id, at: v.at, count: ((v.sets || []).find(x => x.name === name) || {}).count })); }
export function materializeConfirmText(label) { return "Figer « " + label + " » en jeu manuel ?\n\nSon contenu actuel est conservé, mais il cessera d'absorber les nouvelles sessions qui satisfont la règle."; }
export function splitConfirmText(label) { return "Les RETIRER du jeu « " + label + " » (scinder) ?\n\nOK = scinder · Annuler = les garder dans les deux jeux"; }
export function restoreConfirmText(label) { return "Rétablir « " + label + " » dans cet état ?\n\nLes autres jeux ne sont pas touchés, et l'état actuel est archivé : l'opération est annulable."; }
export function deleteConfirmText(label) { return "Supprimer le jeu « " + label + " » ?\n\nLes sessions CONTINUENT de tourner ; les autres jeux ne sont pas touchés."; }
