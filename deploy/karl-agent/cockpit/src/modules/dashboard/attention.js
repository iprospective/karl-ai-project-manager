// models/dashboard/attention — ce qui requiert l'attention, classé. RM2889, L4.
// attentionRows repris tel quel (RM2697) ; tmuxNameOf devient un paramètre
// (`opts.nameOf`) au lieu d'une globale — une fonction pure n'en capture pas.

/** Le nom tmux d'une session, sans DOM. */
export function tmuxNameOf(sid) { return (/^\d+$/.test(String(sid)) ? "RM" : "") + String(sid); }

// Rangs = coût de l'attente, du plus cher au moins cher :
//   1 une session ATTEND une réponse ; 2 un ticket attend TON verdict ; 3 une MR
//   attend un merge ; 4 un ticket attend sa mise en production ; 5 une session au
//   repos a encore du travail devant elle ; 6 une demande n'est pas encore ticketée.
// Chaque ligne porte un VERBE : « réponds », « teste », « merge »…
export function attentionRows(overview, sessions, opts) {
  const o = overview || {}, sess = sessions || {}, cfg = opts || {};
  const nameOf = cfg.nameOf || tmuxNameOf;
  const fc = cfg.client || "", fp = cfg.project || "";
  const rows = [];
  const keep = (cl, pr) => (!fc || cl === fc) && (!fp || pr === fp);
  for (const sid of Object.keys(sess)) {
    const s = sess[sid] || {};
    if (!keep(s.client || "", s.project || "")) continue;
    const waiting = s.state === "attention" || s.state === "choice";
    if (!waiting && !(cfg.stale || []).includes(String(sid))) continue;
    rows.push({ rank: 1, kind: "question", icon: waiting ? "⚠" : "🕓",
                verb: "réponds", sid: String(sid), client: s.client || "", project: s.project || "",
                text: (s.title || nameOf(sid)) + (waiting ? "" : " — question laissée sans réponse") });
  }
  for (const g of (o.projects || [])) {
    if (!keep(g.client, g.project)) continue;
    for (const t of (g.tickets || [])) {
      if (t.status === "a_tester_demandeur") {
        rows.push({ rank: 2, kind: "test", icon: "🧪", verb: "teste", rm_id: t.rm_id,
                    client: g.client, project: g.project, text: t.title || "", since: t.updated || "" });
      } else if (t.status === "a_mep" || t.status === "en_mep") {
        rows.push({ rank: 4, kind: "mep", icon: "🚀", verb: "déploie", rm_id: t.rm_id,
                    client: g.client, project: g.project, text: t.title || "", since: t.updated || "" });
      }
    }
    for (const m of (g.mrs || [])) {
      rows.push({ rank: 3, kind: "mr", icon: "🔀", verb: "merge", iid: m.iid, url: m.url,
                  rm_id: String(m.ref || "").replace(/^RM/, "") || null,
                  client: g.client, project: g.project,
                  text: "!" + m.iid + (m.ref ? " — " + m.ref : "") + (m.alive === false ? " (session éteinte)" : "") });
    }
    const actifs = (g.tickets || []).filter(t => t.bucket === "active").length;
    if (actifs) {
      for (const s of (g.sessions || [])) {
        if (!s.alive) continue;
        const st = (sess[s.sid] || {}).state;
        if (st && st !== "idle") continue;
        rows.push({ rank: 5, kind: "idle", icon: "💤", verb: "relance", sid: String(s.sid),
                    client: g.client, project: g.project,
                    text: (s.title || String(s.sid)) + " — " + actifs + " ticket(s) en cours" });
      }
    }
    for (const r of (g.requests || [])) {
      rows.push({ rank: 6, kind: "request", icon: "📥", verb: "ticketise",
                  client: g.client, project: g.project, text: String(r.text || "") });
    }
  }
  // Dans une même nature, ce qui attend depuis le PLUS LONGTEMPS passe devant.
  rows.sort((a, b) => (a.rank - b.rank)
    || String(a.since || "9999").localeCompare(String(b.since || "9999"))
    || (a.client + "/" + a.project).localeCompare(b.client + "/" + b.project)
    || String(a.rm_id || a.sid || a.iid || "").localeCompare(String(b.rm_id || b.sid || b.iid || "")));
  return rows;
}
