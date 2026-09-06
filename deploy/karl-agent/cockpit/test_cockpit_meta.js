#!/usr/bin/env node
// Tests de l'encart ℹ migré (RM2889, revue 3/3) — porte RM2605 (infos allégé), RM2606 (fiche → liste), RM2611/2609 (conso live,
// récap), RM2614/2714 (client/projet, cval, une requête par projet), RM2673 (tickets de la session, worklog), RM2797/2806 (facettes),
// RM2807 (fan-out borné), RM2888 (pastille de phase → menu de statut).
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 10));
function fakeElement() { const L = []; let inner = ""; return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true,
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async click(action, data) { const n = { dataset: { action, ...(data || {}) } }; for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => (s === "[data-action]" ? n : null) }, stopPropagation() {} }); return n; } }; }
(async () => {
  const M = await import(path.join(DIR, "src/modules/meta/ticketMeta.js"));
  const KS = await import(path.join(DIR, "src/core/store.js")); const mkStore = (name, obj) => { const s = new KS.Store(name, { ttl: 1e9, max: 1000 }); Object.entries(obj || {}).forEach(([k, v]) => s.set(k, v)); return s; };   // RM3005
  const { TicketMetaRepository } = await import(path.join(DIR, "src/modules/meta/TicketMetaRepository.js"));
  const { MetaService } = await import(path.join(DIR, "src/modules/meta/meta.service.js"));
  const VM = await import(path.join(DIR, "src/modules/meta/MetaViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/meta/Meta.view.js"));
  const { mountMeta } = await import(path.join(DIR, "src/modules/meta/meta.controller.js"));
  // — RM2673 : les tickets d'une session, toutes sources —
  const REG = { branches: ["2673-ergonomie-pm", "sans-ticket"], worktrees: ["/w/appli/envs/appli-rm2605"] };
  const WL = { todo: [{ ref: "RM2661" }], waiting: [{ ref: "RM2663" }], done: [{ ref: "RM2673" }], unknown: [{ ref: "chantier-libre" }] };
  assert.deepStrictEqual(M.ticketsOfSession("2673", REG, null), ["2673", "2605"]); assert.deepStrictEqual(M.ticketsOfSession("calymix", null, WL), ["2661", "2663", "2673"]);
  assert.deepStrictEqual(M.ticketsOfSession("2673", REG, WL), ["2673", "2605", "2661", "2663"]); assert.deepStrictEqual(M.ticketsOfSession("calymix", null, null), []);
  assert.deepStrictEqual(M.ticketsOfSession("calymix", null, { todo: [{ ref: "libre" }] }), []); assert.deepStrictEqual(M.ticketsOfSession("calymix", null, { mep: [{ ref: "RM2860" }] }), ["2860"], "RM2860 : « mep » compris");
  // — RM2797 : journal structuré ; RM2714 : cval ; formats —
  const JOURNAL = ["## 2026-08-22T20:04 — report → Redmine", "note (commit 55ca4bda)", "", "## 2026-08-22T20:08 — Protocole de test remplacé", "Tokens : 0 | Durée : 0 min", "détail sur deux lignes"].join("\n");
  const ent = M.logEntries(JOURNAL); assert.strictEqual(ent.length, 2); assert.strictEqual(ent[0].ts, "2026-08-22T20:04"); assert.strictEqual(ent[0].title, "report → Redmine"); assert(ent[1].body.includes("détail sur deux lignes") && !ent[0].body.includes("##"));
  assert.deepEqual(M.logEntries(""), []); assert.deepEqual(M.logEntries(null), []); assert.strictEqual(M.logEntries("juste du texte\nsans en-tête").length, 1); assert.strictEqual(M.logEntries("## titre sans horodatage")[0].title, "titre sans horodatage"); assert.strictEqual(M.logEntries("## titre sans horodatage")[0].ts, "");
  for (const v of ["null", "~", "None", null]) assert.strictEqual(M.cval(v), ""); assert.strictEqual(M.cval("  x  "), "x");
  assert.strictEqual(M.fmtTokens(1234567), "1.2 M"); assert.strictEqual(M.fmtTokens(1500), "2 k"); assert.strictEqual(M.fmtTokens(null), "—"); assert.strictEqual(M.fmtMin(75), "1 h 15"); assert.strictEqual(M.fmtMin(9), "9 min"); assert.strictEqual(M.tmuxName("42"), "karl-RM42"); assert.strictEqual(M.tmuxName("slug"), "karl-slug");
  assert.strictEqual(M.facetOf("conso"), "conso"); assert.strictEqual(M.facetOf("zzz"), "detail"); assert.deepStrictEqual(M.FACETS.map(f => f[0]), ["detail", "desc", "log", "conso", "workspace"]);
  console.log("✓ modèle (RM2673/2797/2714) : tickets d'une session sans doublon, journal découpé, valeurs YAML nulles filtrées");
  // — RM2605 / RM2894 : « infos » —
  const infos = (s, r, usage, sid) => String(V.SessionInfos(new VM.SessionInfosViewModel({ s, r, usage }, { sid, ago: () => "3min", now: Date.parse("2026-09-05T12:00") })));
  assert(/attache une session pour voir ses infos/.test(infos(undefined, undefined, undefined, null)));
  const S = { title: "titre transcript", registry: { seq: 7, machine: 2, created: "2026-09-05T10:00", branches: ["2726-x"], worktrees: ["/w/x-rm2726"] }, registry_conflicts: [{ rm_id: "2726", seqs: [3, 5] }] };
  const hi = infos(S, { found: true, title: "Sujet Redmine" }, undefined, "2726");
  assert(/libellé<\/span><span class="v">Sujet Redmine/.test(hi), "RM2894 : le sujet Redmine prime"); assert(/karl-RM2726/.test(hi) && /#7 · m2 · 2026-09-05T10:00/.test(hi));
  assert(!/2726-x/.test(hi) && !/x-rm2726/.test(hi), "RM2605 : branches et worktrees ont quitté « infos »"); assert(/⚠ RM2726 aussi ouvert en session #3, #5/.test(hi), "…les conflits RESTENT visibles");
  assert(/titre transcript/.test(infos(S, null, undefined, "slug")) && /karl-slug/.test(infos(S, null, undefined, "slug")), "sans ticket : le titre du transcript");
  assert(/Session en direct/.test(hi) && /data-action="refresh-usage" data-rm="2726"/.test(hi) && /data-action="copy-infos"/.test(hi) && !/onclick=/.test(hi));
  // — RM2373/2609/2611 : conso live —
  const usage = (e, reg) => new VM.UsageViewModel(e, { registry: reg || {}, ago: () => "3min", now: Date.parse("2026-09-05T11:00") });
  assert.strictEqual(usage(undefined).kind, "loading"); assert.strictEqual(usage({ usage: null, meta: null }).kind, "unavailable"); assert.strictEqual(usage({ usage: { turns: 0, engine: "opencode" }, meta: null }).kind, "notranscript");
  assert(/transcript claude indisponible \(moteur opencode\)/.test(String(V.Usage(usage({ usage: { turns: 0, engine: "opencode" }, meta: null }), "1"))));
  const U = { usage: { turns: 12, total: 600000, input: 100000, output: 50000, cache_read: 4000000, cache_creation: 30000, context_last: 100000 }, meta: { engine: "claude", model: "claude-opus-4-8", cost_usd: 3, rates: { input_per_mtok_usd: 15, output_per_mtok_usd: 75, cache_read_per_mtok_usd: 1.5 }, updated: 1757000000 } };
  const uv = usage(U, { created: "2026-09-05T10:00" }); const st = uv.stats(), hd = uv.head();
  assert.strictEqual(hd.engine, "Claude Code"); assert.strictEqual(hd.cost, "$3.00"); assert(/entrée \$15/.test(hd.ratesTip)); assert.strictEqual(st.total, "600 k"); assert.strictEqual(st.contextPct, "50% de 200k"); assert.strictEqual(st.rate, "10 k/min · $3.00/h"); assert.strictEqual(st.cache, "4.0 M / 30 k");
  const uh = String(V.Usage(uv, "42")); assert(/coût actuel/.test(uh) && /tarifs \/Mtok/.test(uh) && /600 k/.test(uh) && /\(50% de 200k\)/.test(uh) && /tours IA<\/span><span class="v">12/.test(uh) && /créée/.test(uh) && /il y a 3min/.test(uh) && !/tarif inconnu/.test(uh));
  assert(/tarif inconnu/.test(String(V.Usage(usage({ usage: U.usage, meta: { engine: "claude", cost_usd: 1 } }), "42"))), "sans tarifs : dit « tarif inconnu »");
  const rec = uv.recap("42"); assert(rec[0] === "Session RM42" && rec.includes("modèle: claude-opus-4-8") && rec.some(l => /^tokens: 600000 \(entrée 100000/.test(l)) && rec.some(l => /^contexte: 100000 \(50% de 200k\)/.test(l)) && rec.some(l => /^débit: 10000 tok\/min · \$3.00\/h/.test(l)) && rec.includes("dernière activité: il y a 3min"));
  assert.strictEqual(usage(undefined).recap("42"), null, "rien de chargé : pas de récap");
  console.log("✓ infos (RM2605/2894) et conso live (RM2609/2611) : allégé sans rien perdre, compteurs, % contexte, débit, récap");
  // — RM2614 / RM2714 : client / projet —
  const brief = (c, p, card) => String(V.ProjectBrief(new VM.ProjectBriefViewModel({ client: c, project: p, card })));
  const nu = brief("acme", "shop", null); assert(/acme/.test(nu) && /shop/.test(nu) && /data-action="project" data-key="acme\/shop"/.test(nu) && !/tickets/.test(nu), "sans fiche : ce qu'on sait déjà, pas de compteur inventé");
  const carte = { client_name: "Acme SA", client_redmine_project_id: "acme", name: "Boutique", redmine_project_url: "https://r/projects/shop", gitlab_repo: "grp/shop", default_branch: "dev", open_by_status: { en_cours: 2, a_faire: 3 }, total: 12 };
  const plein = brief("acme", "shop", carte); assert(/Acme SA/.test(plein) && /Boutique/.test(plein) && /5 ouverts \/ 12/.test(plein) && /grp\/shop/.test(plein) && /dev/.test(plein) && /https:\/\/r\/projects\/shop/.test(plein) && /rel="noopener"/.test(plein));
  assert(/1 ouvert</.test(brief("acme", "shop", { open_by_status: { en_cours: 1 } }))); assert.strictEqual(brief(null, "shop", carte), ""); assert.strictEqual(brief("acme", null, carte), ""); assert.strictEqual(brief("", "", null), "");
  const nul = brief("calicote", "prestashop", { gitlab_repo: "null", default_branch: "main", client_name: "Calicote" }); assert(!/null/.test(nul) && /Calicote/.test(nul), "un dépôt non déclaré ne s'affiche pas comme « null »");
  // une requête par projet, pas une par rendu
  const A = await import(path.join(DIR, "src/core/api.js")); let calls = []; const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => { calls.push(String(url)); return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => (/workspace-status/.test(url) ? { is_git: true, branch: "b", clean: false, dirty: 2, ahead: 1 } : { name: "Boutique" }), text: async () => "{}" }; };
  const repo = new TicketMetaRepository(); let loaded = 0;
  assert.strictEqual(repo.projectCard("acme", "shop", () => loaded++), null, "première demande : en vol"); assert.strictEqual(repo.projectCard("acme", "shop"), null, "…redemandée pendant le vol : pas de second appel");
  await settle(); assert.strictEqual(loaded, 1); assert.deepStrictEqual(repo.projectCard("acme", "shop"), { name: "Boutique" }); assert.strictEqual(calls.filter(u => /\/project\//.test(u)).length, 1, "UNE requête par projet");
  assert.strictEqual(repo.workspace("42"), undefined); assert.strictEqual(await repo.refreshWorkspace("slug"), null, "slug : pas de ticket, pas de requête"); const ws = await repo.refreshWorkspace("42"); assert(ws.is_git && repo.workspace("42") === ws);
  globalThis.fetch = realFetch;
  console.log("✓ client/projet (RM2614/2714) : situé sans attendre le réseau, une requête par projet, workspace par ticket");
  // — l'onglet tickets : facettes —
  const R = { found: true, title: "Titre", client: "acme", project: "shop", status: "ferme", priority: "high", type: "feature", completion_pct: 40, updated: "2026-09-05T10:00", redmine_url: "https://r/1", description: "# desc", log_tail: JOURNAL, active_env: { name: "prod", url: "https://p" }, test_url: "https://t", environments: [{ name: "prod", url: "https://p" }, { name: "preprod", url: "https://pp" }], git: { branch: "42-x", mr_url: "https://mr" }, parent_task: "7", depends_on: ["8", "9"], blocks: [], relates: ["10"], sub_tasks: [], metrics: { tokens_total: 5000, tokens_breakdown: { input: 1000, output: 500, cache_read: 30000, cache_creation: 100 }, cost_total_usd: 1.234, ai_time_total_minutes: 75, human_time_total_minutes: 5, updated: "2026-09-05" } };
  const pane = (e) => String(V.TicketsPane(new VM.TicketMetaViewModel(Object.assign({ tickets: ["42", "43"], current: "42", facet: "detail", resolve: { "42": R, "43": undefined }, attached: "42", worklogSeen: true, ws: undefined, card: null }, e), { now: Date.parse("2026-09-05T11:00") }), { md: (s) => "<md>" + s + "</md>", tip: (id) => ' data-tip-rm="' + id + '" title="tip"' }));
  const d = pane({});
  assert(/<button class="active" data-action="tab" data-rm="42">RM42<\/button>/.test(d) && /data-action="tab" data-rm="43"/.test(d), "un sous-onglet par ticket, l'actif marqué");
  for (const f of ["detail", "desc", "log", "conso", "workspace"]) assert(new RegExp('data-action="facet" data-facet="' + f + '"').test(d), "facette routée : " + f);
  assert(/RM42 ↗/.test(d) && /data-action="launcher" data-rm="42"/.test(d) && /data-action="review" data-rm="42"/.test(d) && /data-action="reload" data-rm="42"/.test(d) && /version<\/span>[\s\S]*2026-09-05T10:00[\s\S]*\(il y a 1 h\)/.test(d));
  assert(/data-action="status" data-rm="42">ferme ⇄/.test(d), "RM2888 : la pastille de phase ouvre le menu de statut"); assert(/data-action="reopen" data-rm="42"/.test(d), "fermé : rouvrir proposé"); assert(!/data-action="reopen"/.test(pane({ resolve: { "42": Object.assign({}, R, { status: "en_cours" }) } })));
  assert(/Client \/ projet/.test(d) && /data-action="project" data-key="acme\/shop"/.test(d)); assert(/<span class="pill ok">prod<\/span>/.test(d) && /test_url/.test(d) && /preprod/.test(d) && !/>prod<\/span><\/span><span class="v">[\s\S]*preprod[\s\S]*prod<\/span>/.test(d), "env actif une fois, les autres à part");
  assert(/Git ticket/.test(d) && /42-x/.test(d) && /href="https:\/\/mr"/.test(d)); assert(/parent :/.test(d) && /data-action="ticket" data-rm="7"/.test(d) && /data-tip-rm="8"/.test(d) && /lié :/.test(d) && !/bloque :/.test(d), "relations : RM-ids cliquables avec infobulle, listes vides absentes");
  assert(/data-action="facet" data-facet="desc">📄 description</.test(d) && /🕘 historique</.test(d) && !/<h4>Dernières activités/.test(d), "RM2797 : « détail » renvoie vers les facettes au lieu de répéter les blocs"); assert(!/onclick=/.test(d));
  assert(/📄 description \(vide\)/.test(pane({ resolve: { "42": Object.assign({}, R, { description: "" }) } })));
  const desc = pane({ facet: "desc" }); assert(/class="facetfull descfull mdview"><md># desc<\/md>/.test(desc) && !/class="facetfull desc"/.test(desc), "RM2806 : sa propre classe, pas `.desc` qui bridait"); assert(/ce ticket n'a pas de description/.test(pane({ facet: "desc", resolve: { "42": Object.assign({}, R, { description: "" }) } })));
  const log = pane({ facet: "log" }); assert(/class="facetfull"><div class="logfeed">/.test(log) && log.indexOf("20:08") < log.indexOf("20:04") && /class="logent-ts"/.test(log) && /<md>note \(commit 55ca4bda\)<\/md>/.test(log), "RM2797 : la plus récente en tête, corps en markdown");
  assert(/aucune activité enregistrée/.test(pane({ facet: "log", resolve: { "42": Object.assign({}, R, { log_tail: "" }) } }))); assert(!/<script>/.test(String(V.TicketLog(M.logEntries("## <script>x</script> — t"), { md: String }))));
  const conso = pane({ facet: "conso" }); assert(/Consommation/.test(conso) && /tokens<\/span><span class="v"[^>]*>2 k</.test(conso) && /30 k \/ 100/.test(conso) && /\$1\.23/.test(conso) && /1 h 15/.test(conso) && /5 min/.test(conso), "RM2519 : total = entrée + sortie, cache à part");
  assert(/Aucune consommation enregistrée/.test(pane({ facet: "conso", resolve: { "42": Object.assign({}, R, { metrics: {} }) } })));
  assert(/…<\/span> <span class="pill" data-action="refresh-ws" data-rm="42">/.test(pane({ facet: "workspace" }))); assert(/pas un dépôt git/.test(pane({ facet: "workspace", ws: null })));
  const wsh = pane({ facet: "workspace", ws: { is_git: true, branch: "42-x", clean: false, dirty: 3, untracked: 1, ahead: 2, behind: 4 } }); assert(/42-x/.test(wsh) && /pill warn">3 modifs/.test(wsh) && /1 untracked/.test(wsh) && /↑2/.test(wsh) && /pill dang">↓4/.test(wsh)); assert(/pill ok">clean/.test(pane({ facet: "workspace", ws: { is_git: true, clean: true } })));
  assert(/chargement…/.test(pane({ current: "43" }))); assert(/RM44 <span[^>]*>non trouvé en local/.test(pane({ tickets: ["44"], current: "44", resolve: { "44": null } })));
  // RM2673 : le message vide dit ce qui a VRAIMENT été regardé
  const empty = (a, seen) => pane({ tickets: [], current: null, attached: a, worklogSeen: seen });
  assert(/aucun ticket — attache une session ou ouvre une fiche/.test(empty(null))); assert(/ticket non PM-tracké/.test(empty("42"))); assert(/session slug — aucun ticket dans son worklog/.test(empty("calymix", true))); assert(/lecture du worklog…/.test(empty("calymix", false)));
  assert(/data-rm="99"/.test(pane({ current: "99", resolve: { "99": undefined } })), "un ticket ouvert hors session reste visible en tête");
  console.log("✓ onglet tickets (RM2579/2797/2806/2888) : sous-onglets, cinq facettes routées, détail complet, messages vides précis");
  // — le contrôleur —
  const infosEl = fakeElement(), ticketsEl = fakeElement(); const ev = []; let att = null; let wl = { rm_id: null, buckets: {} }, wlPending = null;
  const resolve = mkStore("r", { "42": R }); const inflight = {}; const usageCache = mkStore("usage");
  const T = { usageFresh: (s) => !!usageCache.get(s), usageInFlight: () => false, ensureUsage: async (s) => { ev.push(["usage", s]); usageCache.set(s, U); }, inFlight: (t) => !!inflight[t],
    ensureResolved: async (rm) => { ev.push(["resolve", rm]); inflight[rm] = true; await settle(); delete inflight[rm]; if (resolve.get(rm) === undefined) resolve.set(rm, { found: true, title: "T" + rm, status: "en_cours" }); return resolve.get(rm); }, revalidate: async () => {} };
  const svc = new MetaService({ repo: { ws: {}, cards: {}, workspace(rm) { return this.ws[rm]; }, async refreshWorkspace(rm) { ev.push(["ws", rm]); this.ws[rm] = { is_git: true, branch: "b", clean: true }; return this.ws[rm]; }, projectCard(c, p, onLoad) { const k = c + "/" + p; if (this.cards[k] !== undefined) return this.cards[k]; this.cards[k] = null; ev.push(["card", k]); setTimeout(() => { this.cards[k] = { name: "Boutique" }; onLoad && onLoad(); }, 0); return null; } }, clipboard: { writeText: async (t) => ev.push(["clip", t.split("\n")[0]]) } });
  const ctr = mountMeta({ infos: infosEl, tickets: ticketsEl }, { ticket: T, service: svc, notify: (m, e) => ev.push(["toast", m, !!e]), md: (s) => s, ago: () => "1min", tipAttr: () => "",
    resolve: () => resolve, sess: () => mkStore("sess", { "42": S, calymix: { title: "calymix", registry: { branches: ["2661-x"] } } }), usage: () => usageCache, attached: () => att, worklog: () => wl, worklogPending: () => wlPending, loadWorklog: () => ev.push("loadWorklog"),
    showRight: (t) => ev.push(["right", t]), noteOpened: (id) => ev.push(["opened", id]), gotoTicket: (rm) => ev.push(["launcher", rm]), openReview: (rm) => ev.push(["review", rm]), reload: (rm) => ev.push(["reload", rm]), openStatusMenu: (rm, n, e) => ev.push(["status", rm, !!n]), reopen: (rm) => ev.push(["reopen", rm]), openProject: (k) => ev.push(["project", k]) });
  ctr.render(); assert(/attache une session pour voir ses infos/.test(infosEl.innerHTML) && /aucun ticket — attache une session/.test(ticketsEl.innerHTML), "rien d'attaché : deux messages, pas de requête"); assert(!ev.length);
  ctr.showTicket("RM42"); assert.deepStrictEqual(ev.slice(0, 2), [["opened", "42"], ["right", "tickets"]]); assert.strictEqual(ctr.current(), "42"); assert.strictEqual(ctr.facet(), "detail"); assert(/data-rm="42">RM42/.test(ticketsEl.innerHTML) && /Titre/.test(ticketsEl.innerHTML), "ticket ouvert hors session : affiché depuis le cache");
  assert(ev.some(x => x[0] === "ws" && x[1] === "42") && ev.some(x => x[0] === "card" && x[1] === "acme/shop"), "workspace et fiche projet demandés une fois"); await settle(); assert(/Boutique/.test(ticketsEl.innerHTML), "…et la fiche arrive dans le rendu");
  ev.length = 0; ctr.render(); assert(!ev.some(x => x[0] === "card") && !ev.some(x => x[0] === "ws"), "re-rendre ne redemande rien");
  // attache : l'ancrage devient le ticket affiché ; le worklog est demandé comme source de tickets
  att = "42"; ev.length = 0; ctr.onAttach("42"); assert.strictEqual(ctr.current(), "42"); assert(ev.includes("loadWorklog"), "RM2673 : le worklog est chargé sans attendre l'onglet état"); assert(ev.some(x => x[0] === "usage" && x[1] === "42"), "conso live demandée"); await settle();
  assert(/Sujet Redmine|Titre/.test(infosEl.innerHTML) && /karl-RM42/.test(infosEl.innerHTML) && /600 k/.test(infosEl.innerHTML), "infos : session + conso rendues"); ev.length = 0; ctr.render(); assert(!ev.some(x => x[0] === "usage"), "conso fraîche : pas redemandée");
  wl = { rm_id: "42", buckets: { todo: [{ ref: "RM2661" }] } }; ev.length = 0; ctr.renderTickets(); assert(!ev.includes("loadWorklog"), "worklog vu : plus de chargement"); assert.deepStrictEqual(ctr.sessionTickets(), ["42", "2726", "2661"]); assert(/data-rm="2726"/.test(ticketsEl.innerHTML) && /data-rm="2661"/.test(ticketsEl.innerHTML));
  // RM2807 : UN .then par ticket en vol — un second rendu pendant le vol ne ré-abonne pas
  const nResolve = ev.filter(x => x[0] === "resolve").length; ctr.renderTickets(); ctr.renderTickets(); assert.strictEqual(ev.filter(x => x[0] === "resolve").length, nResolve, "fan-out borné"); await settle(); assert(/T2726/.test(ticketsEl.innerHTML) || resolve.get("2726"), "les tickets en vol arrivent");
  // gestes
  ev.length = 0; await ticketsEl.click("tab", { rm: "2661" }); assert.strictEqual(ctr.current(), "2661"); await ticketsEl.click("facet", { facet: "conso" }); assert.strictEqual(ctr.facet(), "conso"); assert(/Aucune consommation/.test(ticketsEl.innerHTML) || /Consommation/.test(ticketsEl.innerHTML));
  await ticketsEl.click("facet", { facet: "workspace" }); await settle(); assert(/Workspace/.test(ticketsEl.innerHTML) && ev.some(x => x[0] === "ws" && x[1] === "2661"), "facette workspace : état demandé à l'ouverture");
  await ticketsEl.click("ticket", { rm: "42" }); assert.strictEqual(ctr.current(), "42"); assert.strictEqual(ctr.facet(), "detail", "un RM-id cliqué rouvre sur le détail");
  for (const [a, k] of [["launcher", "launcher"], ["review", "review"], ["reload", "reload"], ["reopen", "reopen"]]) { await ticketsEl.click(a, { rm: "42" }); assert(ev.some(x => x[0] === k && x[1] === "42"), "geste " + a); }
  await ticketsEl.click("status", { rm: "42" }); assert(ev.some(x => x[0] === "status" && x[1] === "42" && x[2] === true), "menu de statut ancré sur la pastille"); await ticketsEl.click("project", { key: "acme/shop" }); assert(ev.some(x => x[0] === "project" && x[1] === "acme/shop"), "🗂 fiche → surface projet (le showProject d'origine n'existait plus)");
  await infosEl.click("copy-infos", { rm: "42" }); await settle(); assert(ev.some(x => x[0] === "clip" && x[1] === "Session RM42") && ev.some(x => x[0] === "toast" && x[1] === "Récap copié"), "RM2611 : récap copié"); ev.length = 0; await infosEl.click("refresh-usage", { rm: "42" }); await settle(); assert(ev.some(x => x[0] === "usage"), "↻ force la conso");
  usageCache.invalidate("43"); const r43 = await svc.copyRecap(null); assert(!r43.ok && /pas encore chargées/.test(r43.message)); assert(/Presse-papier indisponible/.test((await new MetaService({ repo: svc.repo, clipboard: null }).copyRecap(["x"])).message));
  // la revue / la file disent quel ticket montrer, sans rendre ; détacher vide
  ctr.setTicket("77"); assert(ctr.ticketIs("77") && ctr.ticketIs(77) && !ctr.ticketIs("42") && ctr.facet() === "detail"); ctr.setTicket(null); assert.strictEqual(ctr.current(), null);
  att = null; ctr.render(); assert(/attache une session pour voir ses infos/.test(infosEl.innerHTML) && /aucun ticket — attache une session/.test(ticketsEl.innerHTML));
  ctr.unmount(); assert.strictEqual(infosEl.listenerCount + ticketsEl.listenerCount, 0); assert.strictEqual(infosEl.innerHTML, "");
  console.log("✓ contrôleur : fiche depuis le cache puis fraîche, attache → ancrage, worklog source, fan-out borné, gestes délégués, récap");
  console.log("\nTous les tests de l'encart ℹ passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
