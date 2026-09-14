#!/usr/bin/env node
// Tests du cluster centre — VIEWMODELS et VUES (RM3020, scindé de test_cockpit_center.js) : barre d'onglets, liste de l'historique, fichier,
// dossier navigable (portée dans les liens), email, erreur, fiche client et conf — gestes en data-action, zéro onclick.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { esc, fakeElement, RC } = require("./test_cockpit_center.helpers.js");
(async () => {
  const K = await import(path.join(DIR, "src/modules/center/viewKey.js"));
  const SC = await import(path.join(DIR, "src/modules/files/scope.js"));
  const VM = await import(path.join(DIR, "src/modules/center/CenterViewModels.js"));
  const V = await import(path.join(DIR, "src/modules/center/Center.view.js"));

  const tabsHtml = String(V.Tabs(new VM.TabsViewModel({ tabs: [{ kind: "review", key: "2670", label: "RM2670", pinned: true }, { kind: "project", key: "x/y", label: "<b>x</b>", pinned: false }, { kind: "dash", key: "", label: "tableau de bord", pinned: true, fixed: true }], active: "review:2670" }, { resolve: RC })));
  assert(/class="ctab active"/.test(tabsHtml) && /📌/.test(tabsHtml) && /⇧/.test(tabsHtml) && /ctab temp/.test(tabsHtml) && !/<b>x<\/b>/.test(tabsHtml) && /&lt;b&gt;/.test(tabsHtml));
  assert(/data-action="activate" data-id="review:2670"/.test(tabsHtml) && /data-action="close" data-id="review:2670"/.test(tabsHtml) && !/onclick=/.test(tabsHtml), "gestes en data-action, zéro onclick");
  assert(/📊/.test(tabsHtml) && !/data-action="close" data-id="dash:"/.test(tabsHtml) && !/data-action="pin" data-id="dash:"/.test(tabsHtml) && /toujours là/.test(tabsHtml), "l'onglet permanent : ni croix ni épingle");
  console.log("✓ infobulles et barre d'onglets (RM2775/2744) : titres, icônes, permanent sans croix");

  const lh = String(V.History(new VM.HistoryViewModel({ items: [{ id: "session:2673", kind: "session", label: "2673" }, { id: "review:2744", kind: "review", label: "RM2744" }], idx: 1 }, { isOpen: (id) => id !== "session:2673" })));
  assert(lh.indexOf("RM2744") < lh.indexOf("2673")); assert(/data-action="goto" data-id="review:2744"/.test(lh)); assert(!/data-action="goto" data-id="session:2673"/.test(lh)); assert(lh.includes("fermée") && lh.includes("ici"));
  assert(String(V.History(new VM.HistoryViewModel({ items: [], idx: -1 }, {}))).includes("aucune vue visitée"));
  console.log("✓ liste de l'historique (RM2776)");

  const md = (x) => "<MD>" + x + "</MD>";
  const fvMd = String(V.FileView(new VM.FileViewModel({ path: "docs/cdc.md", markdown: true, size: 2048, content: "# Titre" }, { md }))); assert(fvMd.includes("<MD># Titre</MD>") && fvMd.includes("2 Ko"));
  const fvTxt = String(V.FileView(new VM.FileViewModel({ path: "a.py", markdown: false, content: "<script>x</script>" }, { md }))); assert(!fvTxt.includes("<script>") && fvTxt.includes("&lt;script&gt;"));
  // RM2861 : le corps, un seul rendu, pleine hauteur, jamais `.desc`
  const vMd = String(V.FileBody(new VM.FileViewModel({ markdown: true, content: "# titre" }, { md: (t) => "<md>" + t + "</md>" })));
  assert(/facetfull/.test(vMd) && /descfull/.test(vMd) && /mdview/.test(vMd) && !/class="[^"]*\bdesc\b/.test(vMd) && /<md># titre<\/md>/.test(vMd));
  const vTxt = String(V.FileBody(new VM.FileViewModel({ markdown: false, content: "a < b & c" }, { md }))); assert(/max-height:none/.test(vTxt) && /a &lt; b &amp; c/.test(vTxt) && !/<md>/.test(vTxt));
  assert(String(V.FileBody(new VM.FileViewModel(null, { md }))) !== "" && !/undefined/.test(String(V.FileBody(new VM.FileViewModel({ markdown: false }, { md })))));
  const dv = String(V.DirView(new VM.DirViewModel({ src: "wt", wt: "/w/repo", path: "src", rootName: "repo", entries: [{ name: "api", dir: true }, { name: "main.py", dir: false, size: 512 }] })));
  assert(/data-action="open-dir" data-src="wt" data-wt="\/w\/repo" data-path="src\/api" data-tag=""/.test(dv) && /data-action="open-file"[^>]*data-path="src\/main.py"/.test(dv) && dv.includes("repo") && /data-action="open-dir"[^>]*data-path=""/.test(dv) && !/onclick=/.test(dv));
  assert(String(V.DirView(new VM.DirViewModel({ entries: [] }))).includes("dossier vide"));
  const mv = String(V.MailView(new VM.EmailViewModel({ subject: "Devis", from: "a@b.fr", from_name: "Alice", date: "2026-08-20", body: "Bonjour\nà tous", body_truncated: true, state: "à traiter" })));
  assert(mv.includes("Bonjour") && mv.includes("tronqué à la relève") && mv.includes("Alice") && mv.includes("a@b.fr")); assert(String(V.MailView(new VM.EmailViewModel({ subject: "x" }))).includes("corps non disponible")); assert(String(V.MailView(new VM.EmailViewModel({}))).includes("(sans sujet)"));
  const ev = String(V.ViewError("Commit indisponible", "erreur 404")); assert(ev.includes("Commit indisponible") && ev.includes("erreur 404") && ev.includes("session fermée"));
  console.log("✓ vues centrales (RM2759/2861) : clés, libellés, fichier, dossier navigable, email, erreur");

  const tag = SC.scopeTag({ client: "ipro", project: "pm", sid: "karl-RM42" });
  const dh = String(V.DirView(new VM.DirViewModel({ src: "wt", wt: "/ws/ipro/pm", path: "docs", rootName: "pm", tag, entries: [{ name: "sous", dir: true }, { name: "a.md", size: 10 }] })));
  assert((dh.match(/c:ipro\/pm;s:karl-RM42/g) || []).length >= 3, "fil d'ariane, sous-dossiers et fichiers portent la portée");
  console.log("✓ portée dans les liens (RM2761)");

  // — RM2768 : fiche client et conf —
  const CLI = { client: "calicote", name: "Calicote", status: "active", type: "client", created: "2026-05-19", redmine_project_id: "calicote", redmine_project_url: "https://r.test/projects/calicote",
    contacts: [{ first_name: "Sandrine", last_name: "Roche", email: "s@calicote.test", role: "owner", title: "Gérante" }, { name: "Mathieu", email: "m@ipro.test", role: "owner", internal: true }],
    defaults: { priority: "normal", team: [{ username: "iprospective" }] }, projects: [{ project: "prestashop", value: "calicote/prestashop" }], projects_used: ["iprospective/nc-clients"], docs: [{ name: "overview.md", path: "projects/clients/calicote/client/overview.md" }] };
  // RM3132 : la fiche client est à ONGLETS — l'en-tête est commun, le reste se demande.
  const cvTab = (tab, ctx) => String(V.ClientView(new VM.ClientViewModel(CLI, ctx), tab));
  const cv = cvTab("resume"), cvProj = cvTab("projets");
  assert(cv.includes("Calicote") && cv.includes("calicote") && cv.includes("Sandrine Roche") && cv.includes("Gérante") && cv.includes("interne"));
  assert(/data-action="open-project" data-value="calicote\/prestashop"/.test(cvProj) &&
         cvProj.includes("Projets utilisés") && cvProj.includes("iprospective/nc-clients"),
         "RM3132 : les projets sont dans LEUR onglet");
  assert(!/data-action="open-project"/.test(cv), "… et plus dans le résumé");
  assert(/data-action="ctab" data-tab="sessions"/.test(cv), "la barre d'onglets est rendue");
  assert(/aucune session en cours/.test(cvTab("sessions")), "onglet sessions : état vide explicite");
  assert(/data-action="attach" data-sid="42"/.test(cvTab("sessions", { sessions: [{ rm_id: "42", project: "p", state: "working" }] })),
         "les sessions du client sont prêtées par le centre, pas inventées");
  assert(/data-action="open-file" data-src="doc" data-wt="" data-path="projects\/clients\/calicote\/client\/overview\.md"/.test(cv) && cv.includes('href="https://r.test/projects/calicote"') && !/onclick=/.test(cv));
  // RM3132 : « aucun projet » vit désormais dans l'onglet projets — le résumé, lui, reste sobre.
  const cvMin = String(V.ClientView(new VM.ClientViewModel({ client: "x" }), "projets"));
  assert(cvMin.includes("aucun projet") && !cvMin.includes("Contacts")); assert(String(V.ClientView(new VM.ClientViewModel(null))).includes("client"));
  const cf = String(V.ConfView({ label: "calicote/prestashop", name: "meta.yml", content: "slug: x\nrepos:\n  - <b>a</b>\n" }));
  assert(cf.includes("calicote/prestashop") && cf.includes("meta.yml") && cf.includes("&lt;b&gt;a&lt;/b&gt;") && cf.includes("slug: x") && cf.includes("mmi-pm")); assert(String(V.ConfView({})).includes("meta.yml"));
  console.log("✓ fiche client et conf (RM2768) : contacts, partage, docs au centre, conf telle quelle");
  console.log("\nTous les tests des vues du centre passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
