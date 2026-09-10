#!/usr/bin/env node
// Tests de l'encart ℹ — VIEWMODELS et VUES (RM3021, scindé de test_cockpit_meta.js) : « infos » RM2605/2894, conso live RM2373/2609/2611,
// client/projet RM2614/2714, onglet tickets et ses cinq facettes RM2579/2797/2806/2888.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { settle, fakeElement, JOURNAL, S, U, R } = require("./test_cockpit_meta.helpers.js");
(async () => {
  const M = await import(path.join(DIR, "src/modules/meta/ticketMeta.js"));
  const VM = await import(path.join(DIR, "src/modules/meta/MetaViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/meta/Meta.view.js"));

  // — RM2605 / RM2894 : « infos » —
  const infos = (s, r, usage, sid) => String(V.SessionInfos(new VM.SessionInfosViewModel({ s, r, usage }, { sid, ago: () => "3min", now: Date.parse("2026-09-05T12:00") })));
  assert(/attache une session pour voir ses infos/.test(infos(undefined, undefined, undefined, null)));
  const hi = infos(S, { found: true, title: "Sujet Redmine" }, undefined, "2726");
  assert(/libellé<\/span><span class="v">Sujet Redmine/.test(hi), "RM2894 : le sujet Redmine prime"); assert(/karl-RM2726/.test(hi) && /#7 · m2 · 2026-09-05T10:00/.test(hi));
  assert(!/2726-x/.test(hi) && !/x-rm2726/.test(hi), "RM2605 : branches et worktrees ont quitté « infos »"); assert(/⚠ RM2726 aussi ouvert en session #3, #5/.test(hi), "…les conflits RESTENT visibles");
  assert(/titre transcript/.test(infos(S, null, undefined, "slug")) && /karl-slug/.test(infos(S, null, undefined, "slug")), "sans ticket : le titre du transcript");
  assert(/Session en direct/.test(hi) && /data-action="refresh-usage" data-rm="2726"/.test(hi) && /data-action="copy-infos"/.test(hi) && !/onclick=/.test(hi));
  // — RM2373/2609/2611 : conso live —
  const usage = (e, reg) => new VM.UsageViewModel(e, { registry: reg || {}, ago: () => "3min", now: Date.parse("2026-09-05T11:00") });
  assert.strictEqual(usage(undefined).kind, "loading"); assert.strictEqual(usage({ usage: null, meta: null }).kind, "unavailable"); assert.strictEqual(usage({ usage: { turns: 0, engine: "opencode" }, meta: null }).kind, "notranscript");
  assert(/transcript claude indisponible \(moteur opencode\)/.test(String(V.Usage(usage({ usage: { turns: 0, engine: "opencode" }, meta: null }), "1"))));
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
  console.log("✓ client/projet (RM2614/2714) : situé sans attendre le réseau");

  // — l'onglet tickets : facettes —
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
  console.log("\nTous les tests des vues de l'encart passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
