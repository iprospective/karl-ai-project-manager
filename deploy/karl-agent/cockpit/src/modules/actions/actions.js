// models/sessions/actions — les actions d'une session (RM1893 §2 chips, RM2720 actions PM d'un ticket, RM2515 dispositions) : sans DOM. RM2889.

/** RM2720 : À QUI envoyer une action PM d'un ticket — la session du ticket, sinon la session attachée (et on le DIT), sinon rien. */
export function pmActionTarget(rm, sessions, attached) {
  const alive = (sid) => { const s = (sessions || {})[String(sid)]; return !!(s && !s.ghost); };
  if (alive(rm)) return { sid: String(rm), own: true, why: "→ session du ticket RM" + rm };
  if (attached && alive(attached)) return { sid: String(attached), own: false, why: "→ session attachée (" + attached + ") — ce n’est pas la session du ticket" };
  return { sid: null, own: false, why: "aucune session vivante où envoyer cette action" };
}
/** La consigne envoyée : `{id}` vaut le TICKET visé (RM2720), plus la session. */
export function actionMessage(a, rid) { return String((a && a.text) || "").replaceAll("{id}", String(rid == null ? "" : rid)); }
/**
 * §2 : les chips de la barre de session — les actions `ticket_only` vivent sur la fiche du
 * ticket, pas ici (RM2720).
 *
 * RM3418 : rendus en BLOCS par groupe (« Dev », « Session »…) au lieu d'une rangée continue
 * où les groupes se confondaient. `hidden` (conf d'instance) retire une action partout :
 * ce qu'une norme impose déjà (commit+push) ou qu'un panneau montre mieux (git status) n'a
 * pas à occuper la barre. `line` ne s'applique qu'en mobile : les autres passent sous « … ».
 */
export function chipBlocks(actions, attached, { hidden = [], line = null } = {}) {
  const blocs = [];
  (actions || []).forEach((a, i) => {
    if (!a || a.ticket_only) return;
    const cle = a.key || "";
    if (cle && (hidden || []).includes(cle)) return;
    const nom = a.group || "";
    let bloc = blocs.find(b => b.group === nom);
    if (!bloc) { bloc = { group: nom, chips: [] }; blocs.push(bloc); }
    bloc.chips.push({
      i, key: cle, label: a.label || "",
      extra: !!line && !line.includes(cle),
      title: actionMessage(a, attached) + (a.enter === false ? "\n(texte injecté sans Enter — complète dans le terminal)" : ""),
    });
  });
  return blocs.filter(b => b.chips.length);
}
/** Rangée à plat — conservée pour le bureau et les appels historiques. */
export function chipList(actions, attached, opts) {
  const out = [];
  chipBlocks(actions, attached, opts).forEach(b => {
    if (b.group) out.push({ group: b.group });
    b.chips.forEach(c => out.push(c));
  });
  return out;
}
/** RM2720 : les actions PM d'un ticket, dans l'ordre du catalogue (l'index est celui qu'attend sendPmAction). */
export function pmActions(actions) { return (actions || []).filter(a => a && a.ticket_only); }
/** RM2515 : les dispositions d'une session — à traiter / parké / terminé. */
export const DISPOSITIONS = [["a_traiter", "🟡 à traiter"], ["parke", "🔖 en pause"], ["termine", "✅ terminé"]];
export function dispositionItems(current) { const cur = current || "a_traiter"; return DISPOSITIONS.map(([v, l]) => ({ value: v, label: l, on: v === cur })); }
export function tmuxLabel(rmId) { return /^\d+$/.test(String(rmId)) ? "karl-RM" + rmId : "karl-" + rmId; }
