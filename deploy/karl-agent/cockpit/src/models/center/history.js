// models/center/history — l'historique de navigation du centre (RM2776). Repris tel quel.
export const NAV_MAX = 40;

/** Visiter tronque ce qui était « en avant » ; revisiter la vue courante n'empile pas. */
export function histVisit(state, entry, max) {
  const st = state && Array.isArray(state.items) ? state : { items: [], idx: -1 };
  const e = entry || {};
  if (!e.id) return { items: st.items.slice(), idx: st.idx };
  const cur = st.items[st.idx];
  if (cur && cur.id === e.id) {
    const items = st.items.slice();
    items[st.idx] = Object.assign({}, cur, e);
    return { items, idx: st.idx };
  }
  const items = st.items.slice(0, st.idx + 1);
  items.push({ id: e.id, kind: e.kind || "", label: e.label || e.id });
  const trop = items.length - (max || NAV_MAX);
  if (trop > 0) items.splice(0, trop);
  return { items, idx: items.length - 1 };
}

/** Déplacement : une vue fermée entre-temps est SAUTÉE, pas rouverte. */
export function histStep(state, delta, isOpen) {
  const st = state && Array.isArray(state.items) ? state : { items: [], idx: -1 };
  const pas = delta < 0 ? -1 : 1;
  let i = st.idx;
  while (true) {
    i += pas;
    if (i < 0 || i >= st.items.length) return { idx: st.idx, entry: null };
    const e = st.items[i];
    if (!isOpen || isOpen(e.id)) return { idx: i, entry: e };
  }
}

/** Où atterrir en fermant `closedId` : la dernière vue visitée AVANT elle, encore ouverte. */
export function histCloseTarget(state, closedId, isOpen) {
  const st = state && Array.isArray(state.items) ? state : { items: [], idx: -1 };
  const depart = st.idx >= 0 ? st.idx : st.items.length - 1;
  for (let i = depart; i >= 0; i--) {
    const e = st.items[i];
    if (!e || e.id === closedId) continue;
    if (!isOpen || isOpen(e.id)) return e.id;
  }
  return null;
}
