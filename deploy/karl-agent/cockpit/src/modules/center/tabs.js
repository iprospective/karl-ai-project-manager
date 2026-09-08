// models/center/tabs — les onglets du centre, sans DOM. RM2889, cluster centre.
// Repris tels quels : RM2672 (temporaire unique, épinglage), RM2744 (onglet
// permanent), RM2775 (infobulle), RM2795 (marque), RM2819 (session éteinte).

import { entity, tooltipOf, entityTypes, iconOf } from "../../core/entities.js";

export function tabId(kind, key) { return kind + ":" + (key == null ? "" : key); }

/** L'onglet permanent du tableau de bord : toujours en tête, jamais fermable. */
export function ensureDashTab(tabs) {
  const rest = (tabs || []).filter(t => t && !entity(t.kind).fixed);
  return [{ kind: "dash", key: "", label: "tableau de bord", pinned: true, fixed: true }].concat(rest);
}

/** UN SEUL onglet non épinglé à la fois : la vue suivante le remplace. */
export function upsertTab(tabs, kind, key, label, opts) {
  opts = opts || {};
  const id = kind + ":" + (key == null ? "" : key);
  const out = tabs.slice();
  const i = out.findIndex(t => t.kind + ":" + (t.key == null ? "" : t.key) === id);
  if (i >= 0) {
    if (label) out[i] = Object.assign({}, out[i], { label });
    if (opts.pin) out[i] = Object.assign({}, out[i], { pinned: true });
    return { tabs: out, active: id };
  }
  const tab = { kind, key: key == null ? "" : key, label: label || id, pinned: !!opts.pin };
  if (!tab.pinned) {
    for (let j = out.length - 1; j >= 0; j--) if (!out[j].pinned) out.splice(j, 1);
  }
  out.push(tab);
  return { tabs: out, active: id };
}

/** Fermeture : voisin de gauche, puis de droite, puis plus rien. L'onglet fixe ne se ferme pas. */
export function closeTabAt(tabs, id, activeId) {
  const i = tabs.findIndex(t => t.kind + ":" + (t.key == null ? "" : t.key) === id);
  if (i < 0) return { tabs: tabs.slice(), active: activeId };
  if (tabs[i].fixed) return { tabs: tabs.slice(), active: activeId };
  const out = tabs.slice(); out.splice(i, 1);
  let active = activeId;
  if (activeId === id) {
    const n = out[i - 1] || out[i] || null;
    active = n ? n.kind + ":" + (n.key == null ? "" : n.key) : null;
  }
  return { tabs: out, active };
}

/** L'infobulle dit ce que le libellé ne peut pas dire (RM2775) — chaque type la formule dans le registre (RM3002). `parse` = parseViewKey. */
export function tabTooltip(t, rcache, parse) { return tooltipOf(t, rcache, parse); }

/** La marque d'épinglage, la même partout (RM2795) : l'onglet permanent n'en porte pas. */
export function pinMark(tabs, kind, key) {
  const id = kind + ":" + (key == null ? "" : key);
  const pin = (tabs || []).some(t => t && t.pinned && !t.fixed && (t.kind + ":" + (t.key == null ? "" : t.key)) === id);
  return pin ? '<span class="pinmark" title="Épinglé dans les onglets du panneau central">📌</span>' : "";
}

/** Cliquer l'onglet d'une session : vivante → attach ; enregistrée → relance ; sinon on le dit (RM2819). */
export function sessionTabAction(sid, sessions) {
  const key = String(sid == null ? "" : sid);
  const list = Array.isArray(sessions) ? sessions : Object.values(sessions || {});
  const match = list.filter(s => s && String(s.rm_id) === key);
  const vivante = match.find(s => !s.ghost);
  if (vivante) return { action: "attach", session: vivante };
  if (match.length) return { action: "relaunch", session: match[0] };
  return { action: "missing", session: null };
}

/** Icônes par type — lues dans le registre (RM3002) ; gardé pour les appelants historiques. */
export const ICONS = Object.fromEntries(entityTypes().map(t => [t, iconOf(t)]));
