#!/usr/bin/env node
// Tests RM3175 — les trois onglets Critères · Implémentation · Déploiement de la fiche du ticket (panneau de droite).
// Ce qu'on protège : la PROVENANCE des critères est dite (elle décide où cocher, RM2882), un onglet vide dit quoi faire
// au lieu de rester blanc, l'ordre des gestes de MEP est conservé, et le texte venu des tickets est échappé.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { R } = require("./test_cockpit_meta.helpers.js");
let n = 0; const ok = (c, m) => { assert(c, m); n++; };
(async () => {
  const M = await import(path.join(DIR, "src/modules/meta/ticketMeta.js"));
  const VM = await import(path.join(DIR, "src/modules/meta/MetaViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/meta/Meta.view.js"));
  const deps = { md: (s) => "<md>" + s + "</md>", tip: () => "" };
  const pane = (facet, extra) => String(V.TicketsPane(new VM.TicketMetaViewModel({ tickets: ["42"], current: "42", facet,
    resolve: { "42": Object.assign({}, R, extra) }, attached: "42", worklogSeen: true, ws: undefined, card: null }, { now: Date.parse("2026-09-19T11:00") }), deps));

  ok(M.FACETS.map(f => f[0]).slice(0, 4).join() === "detail,criteria,impl,deploy", "les trois onglets suivent « détail »");
  ok(M.facetOf("criteria") === "criteria" && M.facetOf("impl") === "impl" && M.facetOf("deploy") === "deploy", "facetOf les reconnaît");
  const barre = pane("detail");
  ok(/data-facet="criteria">critères</.test(barre) && /data-facet="impl">implémentation</.test(barre) && /data-facet="deploy">déploiement</.test(barre), "la barre de facettes les affiche");

  // — critères —
  const migre = { acceptance: { source: "acceptance", items: [{ done: true, label: "premier" }, { done: false, label: "second <b>gras</b>" }] } };
  let h = pane("criteria", migre);
  ok(/Critères d'acceptation/.test(h) && /\(1\/2\)/.test(h), "compte coché / total");
  ok(/champ dédié \(CF 33\)/.test(h) && /task-acceptance 42 --check N/.test(h), "ticket migré : on dit de cocher avec pm-task-acceptance");
  ok(/<li class="done"><span class="cbox">☑<\/span> premier/.test(h) && /<li class=""><span class="cbox">☐<\/span> second/.test(h), "chaque critère avec sa case");
  ok(/second &lt;b&gt;gras&lt;\/b&gt;/.test(h) && !/<b>gras<\/b>/.test(h), "le libellé venu du ticket est échappé");
  h = pane("criteria", { acceptance: { source: "description", items: [{ done: false, label: "x" }] } });
  ok(/ticket non migré/.test(h) && /task-description-update 42 --check N/.test(h), "ticket non migré : on renvoie vers la description");
  h = pane("criteria", { acceptance: { source: null, items: [] } });
  ok(/aucun critère posé/.test(h), "sans critère : un message, pas un onglet blanc");
  ok(/aucun critère posé/.test(pane("criteria", { acceptance: undefined })), "un /resolve ancien (sans le champ) ne casse pas l'onglet");

  // — implémentation —
  h = pane("impl", { implementation: "## Points d'insertion\n- a.py:f" });
  ok(/<md>## Points d'insertion/.test(h), "l'implémentation est rendue en markdown");
  ok(/aucune proposition d'implémentation/.test(pane("impl", { implementation: "" })) && /task-implementation/.test(pane("impl", {})), "vide : on dit comment la rédiger");

  // — déploiement —
  h = pane("deploy", { deploy_actions: ["core update", "rejouer la migration"], test_protocol: { text: "| A1 | test |", source: "cf" } });
  ok(/Actions au déploiement <span[^>]*>\(2\)/.test(h), "le nombre de gestes");
  ok(h.indexOf("core update") < h.indexOf("rejouer la migration") && /<ol class="crit"><li>core update<\/li>/.test(h), "les gestes dans LEUR ordre, numérotés");
  ok(/Protocole de test/.test(h) && /<md>\| A1 \| test \|<\/md>/.test(h), "puis la recette");
  h = pane("deploy", { deploy_actions: [], test_protocol: null });
  ok(/aucune action au déploiement/.test(h) && /pas de protocole de test/.test(h), "vide des deux côtés : deux messages clairs");

  console.log("OK — onglets critères · implémentation · déploiement : " + n + " assertions (RM3175)");
})().catch(e => { console.error("ÉCHEC :", e && e.message); process.exit(1); });
