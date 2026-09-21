#!/usr/bin/env node
// Tests RM3256 — une seule description des champs d'un ticket, deux vues qui la consomment.
//
// Le registre d'entités (RM3002) composait quatre niveaux depuis une unique `sections()` par type… et
// n'avait AUCUN consommateur : le panneau de droite et la fiche du centre décrivaient chacun le même
// ticket dans leur coin. Ces tests tiennent l'inverse : les deux rendent les MÊMES sections, depuis le
// même ViewModel, et aucune des deux vues ne réécrit ces champs à la main.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
let n = 0; const ok = (c, m) => { assert(c, m); n++; };
(async () => {
  const E = await import(path.join(DIR, "src/core/entities.js"));
  const RVM = await import(path.join(DIR, "src/modules/review/ReviewViewModel.js"));
  const RV = await import(path.join(DIR, "src/modules/review/Review.view.js"));
  const MV = await import(path.join(DIR, "src/modules/meta/Meta.view.js"));
  const MVM = await import(path.join(DIR, "src/modules/meta/MetaViewModel.js"));

  const R = { found: true, title: "Titre", client: "acme", project: "shop", status: "a_tester_dev", type: "feature",
    priority: "high", completion_pct: 40, tags: ["front"], redmine_url: "https://r", git: { branch: "42-x", mr_url: "https://mr" },
    test_protocol: { text: "| A1 | x |", source: "cf" }, description: "desc", log_tail: "log", relates: ["7"],
    environments: [{ name: "prod", url: "https://p" }], active_env: { name: "preprod", url: "https://pp" }, test_url: "https://t" };
  const secs = (level) => (new RVM.ReviewViewModel({ r: R }, { rm: "42", now: Date.now() }).sections() || [])
    .filter(s => (level === "full") || (s.level || "panel") !== "full").map(s => s.id);

  const vmPanel = new MVM.TicketMetaViewModel({ tickets: ["42"], current: "42", facet: "detail", resolve: { "42": R },
    attached: "42", worklogSeen: true, ws: undefined, card: null }, { now: Date.now() });
  const panneau = String(MV.TicketsPane(vmPanel, { md: (s) => s, tip: () => "" }));
  const fiche = String(RV.ReviewPane(new RVM.ReviewViewModel({ r: R, q: null, cfg: { statuses: [] } }, { rm: "42", now: Date.now() }),
    { md: (s) => s, titleLink: (rm, t) => t, mcBanner: () => "" }));

  const rendues = (h) => (h.match(/data-sec="([a-z]+)"/g) || []).map(x => x.slice(10, -1));
  ok(rendues(panneau).length > 0, "le panneau rend des sections du registre — il en est le premier consommateur");
  ok(rendues(fiche).length > 0, "la fiche du centre aussi");
  for (const id of secs("panel")) ok(rendues(panneau).includes(id), "le panneau porte la section « " + id + " »");
  for (const id of secs("full")) ok(rendues(fiche).includes(id), "la fiche porte la section « " + id + " »");
  ok(secs("full").length > secs("panel").length, "le niveau « full » en porte plus que « panel » (description, historique)");
  ok(!rendues(panneau).includes("description"), "… et le panneau ne charge pas la description dans ses 330 px (elle a sa facette)");

  // La donnée elle-même arrive bien des deux côtés — une section vide ne prouverait rien.
  ok(/42-x/.test(panneau) && /42-x/.test(fiche), "la branche du ticket est dans les deux vues");
  ok(/preprod/.test(panneau) && /preprod/.test(fiche), "l'environnement actif aussi");

  // La garde de non-régression : les vues ne redécrivent pas ces champs à la main.
  const src = (f) => fs.readFileSync(path.join(DIR, f), "utf8");
  const meta = src("src/modules/meta/Meta.view.js"), rev = src("src/modules/review/Review.view.js");
  ok(/renderEntity\(/.test(meta) && /renderEntity\(/.test(rev), "les deux vues passent par renderEntity");
  for (const [f, s, quoi] of [["Meta.view.js", meta, "<h4>Git ticket</h4>"], ["Meta.view.js", meta, "<h4>Environnement (selon phase)</h4>"],
                              ["Review.view.js", rev, "📋 Protocole de test"], ["Review.view.js", rev, "📝 Description du ticket"],
                              ["Review.view.js", rev, "<h4>Environnements du projet</h4>"]])
    ok(!s.includes(quoi), f + " ne réécrit plus « " + quoi + " »");

  console.log("OK — une seule description des champs du ticket : " + n + " assertions (RM3256)");
})().catch(e => { console.error("ÉCHEC :", e && e.message); process.exit(1); });
