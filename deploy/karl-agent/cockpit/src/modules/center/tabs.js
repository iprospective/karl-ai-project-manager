// models/center/tabs — les onglets du centre, sans DOM. RM2889, cluster centre.
// Repris tels quels : RM2672 (temporaire unique, épinglage), RM2744 (onglet
// permanent), RM2775 (infobulle), RM2795 (marque), RM2819 (session éteinte).

export function tabId(kind, key) { return kind + ":" + (key == null ? "" : key); }

/** L'onglet permanent du tableau de bord : toujours en tête, jamais fermable. */
export function ensureDashTab(tabs) {
  const rest = (tabs || []).filter(t => t && t.kind !== "dash");
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

/** L'infobulle dit ce que le libellé ne peut pas dire (RM2775). `parse` = parseViewKey. */
export function tabTooltip(t, rcache, parse) {
  const tab = t || {};
  const cache = rcache || {};
  const parts = parse ? parse(tab.key || "") : [];
  const key = String(tab.key == null ? "" : tab.key);
  const lbl = String(tab.label || "");
  const resolu = (id) => { const r = cache[String(id)]; return (r && r.found && r.title) ? String(r.title) : ""; };
  const avec = (tete, suite) => suite ? tete + " — " + suite : tete;
  switch (tab.kind) {
    case "review":   return avec("RM" + key, resolu(key));
    case "session":  return avec(/^\d+$/.test(key) ? "session RM" + key : "session " + key, resolu(key));
    case "project":  return avec("fiche projet", key);
    case "client":   return avec("fiche client", parts[0] || key);
    case "conf":     return avec("configuration", parts[0] === "project" ? (parts[1] || "") + "/" + (parts[2] || "") : (parts[1] || ""));
    case "file":     return avec("fichier", parts[2] || parts[1] || lbl);
    case "dir":      return avec("dossier", parts[2] || "racine du dépôt");
    case "commit":   return avec("commit " + (parts[1] || lbl), parts[0] ? "session " + parts[0] : "");
    case "mail":     return avec("email", lbl);
    case "newticket": return "nouveau ticket";
    case "dash":     return "tableau de bord";
    case "pm":       return "commandes PM";
    case "settings": return "réglages du cockpit";
    case "journal":  return "journal (serveur + navigateur)";
    default:         return lbl || key;
  }
}

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

export const ICONS = { session: "▶", review: "🧪", project: "📁", newticket: "＋", dash: "📊",
  file: "📄", dir: "🗂", commit: "⎇", mail: "📧", client: "🏢", conf: "⚙", pm: "⚙", settings: "🔧", journal: "📜" };
