// models/worklog/worklog — le worklog d'une session (RM2466/2584/2591/2610/2695/2716/2719/2720/2786/2796/2798/2801/2823/2930)
// et ses lots : tout ce qui se calcule sans DOM. RM2889 : sorti du monolithe tel quel, en données plutôt qu'en HTML.

export const isTicketRef = (ref) => /^RM\d+$/i.test(String(ref || ""));
export const refId = (ref) => String(ref == null ? "" : ref).replace(/^RM/i, "");

/** Ordre d'affichage : ce qui reste d'abord, ce qui est fait en dernier ; les sections vides disparaissent. */
export function worklogSections(buckets) {
  const b = buckets || {};
  return [
    { key: "encours", icon: "🔨", label: "en cours", items: b.encours || [] },           // RM3323 : commencé, avant le reste
    { key: "todo", icon: "⏳", label: "reste à faire", items: b.todo || [] },
    { key: "testing", icon: "🧪", label: "à tester / valider", items: b.testing || [] },   // RM2930 : une action, avant la MEP
    { key: "mep", icon: "🚀", label: "à mettre en prod", items: b.mep || [] },             // RM2860 : le dev est fini
    { key: "waiting", icon: "⏸", label: "en attente / bloqué", items: b.waiting || [] },
    { key: "done", icon: "✅", label: "fait", items: b.done || [] },
    { key: "unknown", icon: "❔", label: "statut inconnu", items: b.unknown || [] },
  ].filter(s => s.items.length);
}
/** RM2584 : aplatit { ref → [[name, kind], …] } en [{ref, name, kind}], ordre préservé, chaîne seule tolérée. */
export function worklogDocs(docsMap) {
  const out = [];
  for (const ref of Object.keys(docsMap || {})) for (const d of (docsMap[ref] || [])) out.push({ ref, name: Array.isArray(d) ? d[0] : d, kind: Array.isArray(d) ? (d[1] || "") : "" });
  return out;
}
/** RM2610 : un onglet par bucket NON VIDE, « à faire » créé pour des branches orphelines, « documents » s'il y en a. */
export function worklogTabList(secs, docsCount, orphanCount, mrCount) {
  const tabs = [];
  for (const s of secs || []) tabs.push({ key: s.key, label: s.icon + " " + s.label, n: s.items.length });
  if (orphanCount && !tabs.some(t => t.key === "todo")) tabs.unshift({ key: "todo", label: "⏳ reste à faire", n: 0 });
  // RM3074 : le compteur ne compte QUE ce qui appelle un geste (à merger, à promouvoir) — une MR
  // promue reste consultable dans l'onglet, mais gonfler le compteur avec elle rendrait le chiffre muet.
  if (mrCount) tabs.push({ key: "mrs", label: "🔀 MR", n: mrCount });
  if (docsCount) tabs.push({ key: "documents", label: "📄 documents", n: docsCount });
  return tabs;
}

/** RM3074 — les MR d'une session, groupées par ÉTAPE du cycle. Pure.
 *
 * Trois groupes, dans l'ordre où ils appellent un geste : à merger dans l'intégration · mergées,
 * en attente de promotion · promues en production. Le second est celui qui n'existait nulle part :
 * le worklog ne listait que les MR ouvertes, si bien qu'une MR mergée dans `dev` disparaissait de
 * l'écran alors que le travail n'était pas en production. Les fermées sans merge sont écartées :
 * elles ne disent rien du cycle. */
export function mrCycle(mrs, integration) {
  const dev = String(integration || "dev");
  const groups = { open: [], integration: [], prod: [] };
  for (const m of (mrs || [])) {
    const state = String((m || {}).state || "opened").toLowerCase();
    if (state === "closed" || state === "declined") continue;
    const target = String(m.target || "").trim();
    const stage = (state === "opened" || state === "open" || state === "reopened") ? "open"
      : (target && target !== dev) ? "prod" : "integration";
    groups[stage].push(Object.assign({}, m, { stage }));
  }
  for (const k of Object.keys(groups)) groups[k].sort((a, b) => String(b.ts || "").localeCompare(String(a.ts || "")));
  return groups;
}

/** Combien de MR appellent encore un geste (à merger + à promouvoir). Pure. */
export function mrTodoCount(mrs, integration) {
  const g = mrCycle(mrs, integration);
  return g.open.length + g.integration.length;
}

export const MR_GROUPS = [
  { key: "open", icon: "⇥", label: "à merger dans l'intégration",
    hint: "la MR du ticket est ouverte : elle attend d'être mergée" },
  { key: "integration", icon: "✓", label: "mergées — à promouvoir en production",
    hint: "le travail est dans l'intégration ; la promotion se fait par LOT (dev → main), pas MR par MR" },
  { key: "prod", icon: "★", label: "promues en production",
    hint: "plus rien à faire côté MR" },
];
/** RM2466 volet 1 : gravité d'un événement — le niveau reste écrit à côté de l'icône. */
export function notifyDecor(level) {
  if (level === "critical") return { icon: "🔴", cls: "oq ounres", label: "critical" };
  if (level === "info") return { icon: "ℹ️", cls: "", label: "info" };
  return { icon: "⚠️", cls: "oq", label: "warn" };
}
/** RM2466 volet 2 : deux natures d'attente — jamais la couleur seule. */
export function pendingDecor(entry) {
  if (entry && entry.kind === "live") return { icon: entry.state === "choice" ? "❓" : "⚠", tag: "bloquée", cls: "oq ounres", title: "La session attend une réponse MAINTENANT — elle ne peut pas avancer" };
  return { icon: "🕓", tag: "sans réponse", cls: "oq", title: "Question posée puis laissée sans réponse — la session, elle, a continué" };
}
/** RM2798 : groupes par client / projet dans l'ordre d'apparition, « hors projet » en dernier — un RENDU, pas un tri.
 *  RM2852 : `session` = { client, project } de la session courante. Les groupes sont alors
 *  rangés par PROXIMITÉ — le projet de la session, puis les projets du même client, puis le
 *  reste — l'ordre d'apparition restant le départage à l'intérieur de chaque rang. Sans
 *  session résolue, l'ordre est exactement celui d'avant. */
export function groupWorklogItems(items, session) {
  const HORS = "hors projet", ordre = [], par = new Map(), rang = new Map();
  const sCl = (session && session.client) || "", sPr = (session && session.project) || "";
  for (const it of (items || [])) {
    const cl = (it && it.client) || "", pr = (it && it.project) || "";
    const key = (cl && pr) ? cl + " / " + pr : (pr || cl || HORS);
    if (!par.has(key)) {
      par.set(key, []); ordre.push(key);
      // 0 = le projet de la session · 1 = un autre projet du même client · 2 = le reste.
      // « hors projet » garde son rang de queue, qui prime (il n'a ni client ni projet).
      rang.set(key, key === HORS ? 3
        : (sPr && pr === sPr && (!sCl || cl === sCl)) ? 0
          : (sCl && cl === sCl) ? 1 : 2);
    }
    par.get(key).push(it);
  }
  const rangDe = k => (sPr || sCl) ? rang.get(k) : (k === HORS ? 3 : 0);
  // Tri STABLE (spec ES2019) : à rang égal, l'ordre d'apparition est conservé.
  return ordre.slice().sort((a, b) => rangDe(a) - rangDe(b)).map(k => ({ key: k, items: par.get(k) }));
}
/** RM2801 : où en est la MR du ticket ; null sans MR (l'absence n'est pas un état à afficher). */
export function mrStage(st) {
  const d = st || {};
  const etapes = { open: { txt: "⇥ MR", cls: "warn", quoi: "MR ouverte, à merger" },
    integration: { txt: "✓ dev", cls: "ok", quoi: "mergée dans l'intégration — la promotion en production se fait par lot (dev → main), hors MR du ticket" },
    prod: { txt: "✓ prod", cls: "ok", quoi: "promue en production" } };
  const e = etapes[d.stage]; if (!e) return null;
  const detail = (d.mrs || []).map(m => "!" + (m.iid || "?") + " " + (m.state || "?") + (m.target ? " → " + m.target : "") + (m.repo ? " (" + m.repo + ")" : "")).join("\n");
  return { txt: e.txt, cls: e.cls, url: d.url || "", tip: e.quoi + (detail ? "\n" + detail : "") + (d.count > 1 ? "\n(" + d.count + " MR — l'étape la plus avancée est affichée)" : "") };
}
/** RM2796 : UNE pastille — le statut courant ; la dérive (modifié par une AUTRE session) en couleur, son détail au survol. */
export function statusInfo(it) {
  const item = it || {}, st = String(item.status || "?"), from = String(item.opened_status || "");
  if (!item.drifted || !from || from === st) return { status: st, drifted: false, tip: "" };
  return { status: st, drifted: true, tip: "Statut modifié hors de cette session : " + from + " → " + st };
}
/** RM2695 : l'avancement DANS un ticket — critères restants et sous-tâches ; null sans checklist ni sous-tâche (jamais « 0/0 »). */
export function worklogProgress(it) {
  const c = (it && it.checklist) || null, subs = ((it && it.sub_tasks) || []).map(s => ({ rm: String(s.rm_id), status: s.status || "", title: s.title || "" }));
  const check = (c && c.total) ? { done: c.done || 0, total: c.total, cls: (c.done || 0) >= c.total ? "ok" : ((c.done || 0) ? "" : "warn"), items: (c.items || []).slice(), truncated: !!c.truncated } : null;
  return (check || subs.length) ? { check, subs } : null;
}
/** RM2591 : chaque ticket regroupé avec SA branche (RM<id> ← « <id>-<slug> »). */
export function branchesByRm(branches) { const by = {}; for (const b of (branches || [])) { const m = /^(\d+)-/.exec(String(b)); if (m) (by["RM" + m[1]] = by["RM" + m[1]] || []).push(b); } return by; }

// ── lots (RM2716/2720/2786/2823) ──────────────────────────────────────────────
/** RM2720/2786 : deux modes de lot, un seul écran — ce qui part se lit dans le titre comme dans le bouton. */
export const BATCH_MODES = {
  traiter: { titre: "▶ Traiter", envoi: "▶ envoyer à la session", points: true },
  atester: { titre: "✔ Passer à tester", envoi: "✔ livrer et passer à tester", points: false },
  etudier: { titre: "🔍 Analyser (étude + chiffrage)", envoi: "🔍 envoyer à la session", points: false },   // on ne chiffre pas la moitié d'un ticket
};
/** RM2786 : quels boutons de lot afficher, et avec quel compte. La RÈGLE vient des tables du serveur ; un statut inconnu compte partout. */
export function batchButtons(items, mrRefs, cfg) {
  const conf = cfg || {}, modes = conf.batch_modes || {}, closables = new Set(conf.closable_statuses || []), connus = new Set(closables);
  for (const m of Object.values(modes)) { (m.statuses || []).forEach(v => connus.add(v)); Object.keys(m.skip || {}).forEach(v => connus.add(v)); }
  const mrs = new Set((mrRefs || []).map(r => String(r).replace(/^RM/, "")));
  const out = { traiter: 0, atester: 0, etudier: 0, fermer: 0, mr: 0 };
  for (const it of (items || [])) {
    const st = String((it && it.status) || "").toLowerCase(), rm = String((it && it.rm_id) || "").replace(/^RM/, ""), inconnu = !connus.has(st);
    for (const name of ["traiter", "atester", "etudier"]) { const m = modes[name]; if (inconnu || (m && (m.statuses || []).indexOf(st) >= 0)) out[name]++; }
    if (inconnu || closables.has(st)) out.fermer++;
    if (mrs.has(rm)) out.mr++;
  }
  return out;
}
/** RM2786 : qui peut être fermé, qui est écarté AVEC sa raison — les statuts fermables viennent du serveur. */
export function closeBatchPlan(items, cfg) {
  const closables = new Set((cfg || {}).closable_statuses || []);
  const raisons = { nouveau: "pas encore pris en charge : rien à fermer", a_etudier_chiffrer: "à étudier : rien n'a encore été livré", etude_chiffrage_en_cours: "étude en cours",
    etude_chiffrage_a_valider: "étude rendue : elle se valide, elle ne se ferme pas ici",
    etude_chiffrage_a_corriger: "étude renvoyée : elle se reprend, elle ne se ferme pas ici", a_faire: "pas encore traité", en_cours: "en cours de réalisation : rien n'a été livré",
    a_corriger: "renvoyé en correction", en_pause: "en pause", ferme: "déjà fermé", annule: "annulé" };
  const todo = [], skipped = [];
  for (const it of (items || [])) {
    const st = String((it && it.status) || "").toLowerCase();
    const e = { rm_id: String((it && it.rm_id) || "").replace(/^RM/, ""), title: (it && it.title) || "", status: st || "?" };
    if (closables.has(st)) todo.push(e); else skipped.push(Object.assign({}, e, { why: raisons[st] || "statut " + (st || "?") + " : hors du champ d'une fermeture" }));
  }
  return { todo, skipped, count: todo.length };
}
/** RM2823 : que devient une sélection qu'on veut sortir de la session ? UN projet, sinon on le dit avant ; un ticket non résolu reste sur place. */
export function offloadPlan(items, rcache) {
  const cache = rcache || {}, targets = [], blocked = [], vus = [];
  for (const it of items || []) {
    const rm = refId(it && it.rm_id); if (!rm) continue;
    const r = cache[rm];
    if (!r || !r.found || !r.client || !r.project) { blocked.push({ rm_id: rm }); continue; }
    const cle = r.client + "/" + r.project; if (vus.indexOf(cle) < 0) vus.push(cle);
    targets.push({ rm_id: rm, client: r.client, project: r.project, cwd: r.cwd || "", title: r.title || "" });
  }
  const mixed = vus.length > 1, first = targets[0] || null;
  return { targets, blocked, mixed, projects: vus, client: mixed || !first ? null : first.client, project: mixed || !first ? null : first.project,
    cwd: mixed || !first ? "" : (targets.find(t => t.cwd) || {}).cwd || "", anchor: mixed || !first ? null : first.rm_id };
}
/** RM2719 : la portée retenue (points cochés) — un ticket dont tous les points restent cochés part entier. */
export function scopeItems(selection, boxes) {
  const byRef = {};
  for (const b of boxes || []) { const ref = b.ref; if (!ref) continue; const e = byRef[ref] = byRef[ref] || { all: [], kept: [] }; e.all.push(b.value); if (b.checked) e.kept.push(b.value); }
  return (selection || []).map(it => { const e = byRef[String(it.rm_id)]; if (!e || e.kept.length === e.all.length) return it; return Object.assign({}, it, { scope: e.kept }); });
}
/** Le texte de confirmation d'un lot qui part dans une session neuve (RM2823/2831). */
export function spawnConfirmLines(plan, launcher, o) {
  const lignes = [(o.titre || "Ouvrir une nouvelle session") + " pour " + plan.targets.length + " ticket(s) ?", "", "projet : " + plan.client + " / " + plan.project, "ancrage : RM" + plan.anchor,
    "cwd : " + (plan.cwd || "(défaut du serveur)"), "moteur : " + launcher.engine + (launcher.model ? "  ·  modèle : " + launcher.model : ""), "", "tickets : " + plan.targets.map(t => "RM" + t.rm_id).join(", ")];
  if (plan.blocked.length) lignes.push("", "⊘ écartés (projet non résolu) : " + plan.blocked.map(t => "RM" + t.rm_id).join(", "));
  if (o.reste) lignes.push("", o.reste);
  lignes.push("", "La consigne de prise en charge est celle de « ▶ traiter ».");
  return lignes;
}
