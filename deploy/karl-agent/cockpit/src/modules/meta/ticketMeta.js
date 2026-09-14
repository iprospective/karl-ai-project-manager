// models/tickets/ticketMeta — l'encart ℹ (colonne de droite « infos » + « tickets ») : ce qui se
// calcule sans DOM ni réseau. RM2889 (revue 3/3). Porte RM2173/2579/2673/2797/2614/2714/2860.

/** Les facettes d'un ticket dans l'encart, dans l'ordre d'affichage (RM2579, RM2797). */
// RM3164 : « conso » s'appelle « temps & coût » — l'onglet portait déjà les tokens, le COÛT et
// les temps IA/humain, mais son nom ne disait que la moitié : on ne l'ouvrait pas pour chercher
// un temps. La clé ne bouge pas (elle est dans les URL de vue et les préférences).
export const FACETS = [["detail", "détail"], ["desc", "description"], ["log", "historique"], ["conso", "temps & coût"], ["workspace", "workspace"]];
export function facetOf(f) { return FACETS.some(x => x[0] === f) ? f : "detail"; }

export const ENGINE_LABEL = { claude: "Claude Code", opencode: "opencode", vibe: "vibe" };

/** Le nom tmux d'une session : karl-RM<id> pour un ticket, karl-<slug> sinon. */
export function tmuxName(id) { return (/^\d+$/.test(String(id)) ? "karl-RM" : "karl-") + id; }

/** RM2614/RM2714 : un champ YAML vide remonte en CHAÎNE "null" / "~" / "None" — sans ce filtre, la fiche affichait « dépôt : null ». */
export function cval(v) {
  const s = String(v == null ? "" : v).trim();
  return (s && s !== "null" && s !== "~" && s !== "None") ? s : "";
}

export function fmtTokens(n) {
  if (n == null) return "—";
  n = Number(n);
  return n >= 1e6 ? (n / 1e6).toFixed(1) + " M" : n >= 1e3 ? Math.round(n / 1e3) + " k" : String(n);
}
export function fmtMin(m) {
  if (m == null) return "—";
  m = Math.round(Number(m));
  return m >= 60 ? Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0") : m + " min";
}

// RM2673 : les tickets qu'une session traite, TOUTES sources confondues — l'ancrage (sid numérique),
// le registre pm_session (branches `<id>-slug`, worktrees `…-rm<id>`) et le WORKLOG de la session
// (RM2068). Le worklog est la seule source d'une session lancée sur un SLUG. L'ordre reste celui de
// la proximité au travail en cours : ancrage, registre, puis worklog (reste à faire avant fait ; RM2860 : « mep » compris).
export function ticketsOfSession(sid, registry, buckets) {
  const out = [];
  const add = id => { if (id && out.indexOf(id) < 0) out.push(id); };
  if (/^\d+$/.test(String(sid == null ? "" : sid))) add(String(sid));
  const reg = registry || {};
  (reg.branches || []).forEach(b => { const m = /^(\d+)-/.exec(String(b)); if (m) add(m[1]); });
  (reg.worktrees || []).forEach(w => { const m = /-rm(\d+)$/.exec(String(w)); if (m) add(m[1]); });
  for (const k of ["todo", "mep", "waiting", "unknown", "done"])
    for (const it of ((buckets || {})[k] || [])) {
      const m = /^RM(\d+)$/i.exec(String((it && it.ref) || ""));
      if (m) add(m[1]);
    }
  return out;
}

// RM2797 : découpe le journal d'un ticket en entrées `## <horodatage> — <titre>`. Servi en markdown
// structuré, l'afficher en préformaté jetait cette structure.
export function logEntries(text) {
  const lignes = String(text || "").split("\n");
  const out = [];
  let cur = null;
  for (const l of lignes) {
    if (l.startsWith("## ")) {
      if (cur) out.push(cur);
      const titre = l.slice(3).trim();
      const m = /^(\S+)\s+—\s+(.*)$/.exec(titre);
      cur = { ts: m ? m[1] : "", title: m ? m[2] : titre, body: [] };
    } else if (cur) {
      cur.body.push(l);
    } else if (l.trim()) {
      cur = { ts: "", title: "", body: [l] };     // journal sans en-tête : rien n'est perdu
    }
  }
  if (cur) out.push(cur);
  return out.map(e => ({ ts: e.ts, title: e.title, body: e.body.join("\n").trim() }))
            .filter(e => e.ts || e.title || e.body);
}
