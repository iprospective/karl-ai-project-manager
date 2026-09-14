// test_cockpit_status — la table des statuts montée dans le socle (RM3126).
// Ce qui est vérifié ici : le code couleur est UNE fonction pour tout le cockpit, les familles
// n'ont pas bougé en déménageant, et aucune vue ne se remet à écrire une couleur en dur.
"use strict";
const fs = require("fs"), path = require("path");
const DIR = __dirname, SRC = path.join(DIR, "src");
let ko = 0;
const check = (label, ok, detail) => { console.log(`  ${ok ? "✓" : "✗"} ${label}${ok ? "" : " — " + (detail || "")}`); if (!ok) ko++; };

(async () => {
  const S = await import("file://" + path.join(SRC, "core/status.js"));
  const O = await import("file://" + path.join(SRC, "modules/tickets/openedTickets.js"));

  // ── la classe rendue
  check("statusTone rend st-<famille>", S.statusTone("en_cours") === "st-encours" &&
        S.statusTone("ferme") === "st-ferme" && S.statusTone("a_mep") === "st-mep");
  check("un statut RENSEIGNÉ mais inconnu tombe en st-autre (il doit se voir)",
        S.statusTone("zzz") === "st-autre");
  check("un statut ABSENT ne reçoit AUCUNE classe — absent n'est pas inconnu",
        S.statusTone("") === "" && S.statusTone(null) === "" && S.statusTone(undefined) === "" &&
        S.statusTone("?") === "" && S.statusTone("  ") === "");
  check("statusTone ne rend JAMAIS une couleur en dur",
        !/#|rgb|var\(/.test(S.statusTone("en_cours")));
  check("pillClass rend `pill` SEUL sans famille — pas d'espace parasite dans le balisage",
        S.pillClass("?") === "pill" && S.pillClass("") === "pill" &&
        S.pillClass("a_faire") === "pill st-todo" && S.pillClass("a_faire", "x") === "pill st-todo x");

  // ── les cinq familles demandées sont couvertes
  const demandees = { en_cours: "st-encours", a_faire: "st-todo", a_tester_demandeur: "st-test",
                      en_pause: "st-pause", ferme: "st-ferme" };
  for (const [st, tone] of Object.entries(demandees))
    check(`famille de ${st}`, S.statusTone(st) === tone, S.statusTone(st));

  // ── le déménagement n'a rien changé (RM2883 → core)
  check("openedTickets ré-exporte la table, les appelants n'ont pas bougé",
        typeof O.ticketStatusFamily === "function" && typeof O.ticketStatusRank === "function");
  for (const st of ["en_cours", "ferme", "a_mep", "a_tester_dev", "nouveau", "en_pause", "zzz"])
    check(`famille inchangée pour ${st}`, O.ticketStatusFamily(st) === S.ticketStatusFamily(st));
  check("ordre de lecture inchangé : l'action avant le clos",
        S.ticketStatusRank("a_corriger") < S.ticketStatusRank("a_faire") &&
        S.ticketStatusRank("a_faire") < S.ticketStatusRank("ferme"));
  check("un statut inconnu passe AVANT fermé (il demande un regard)",
        S.ticketStatusRank("zzz") < S.ticketStatusRank("ferme"));

  // ── libellés
  check("statusLabel rend un libellé lisible", S.statusLabel("a_tester_demandeur") === "à tester" &&
        S.statusLabel("ferme") === "clôturé");
  check("statusLabel rend le statut BRUT s'il est inconnu (pas de mensonge)",
        S.statusLabel("zzz") === "zzz");

  // ── la palette existe, et une seule fois
  const scss = fs.readFileSync(path.join(SRC, "styles/_base.scss"), "utf8");
  for (const f of ["todo", "encours", "test", "mep", "pause", "ferme", "autre"])
    check(`la palette définit .pill.st-${f}`, scss.includes(`.pill.st-${f}`));

  // ── la garde : aucune vue ne recrée sa propre couleur de statut
  const vues = [];
  (function walk(d) { for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p); else if (e.name.endsWith(".view.js")) vues.push(p);
  } })(path.join(SRC, "modules"));
  const fautives = vues.filter(p => {
    const s = fs.readFileSync(p, "utf8");
    // Fautif = une pastille qui rend un statut SANS sa famille — et sans porter non plus de classe
    // SÉMANTIQUE explicite (warn / dang / ok). Cette tolérance n'est pas une échappatoire : une
    // pastille d'alerte est un choix d'affichage assumé, qui prime sur la famille (cas du ticket
    // « drifted » dans le worklog : la dérive est plus urgente à voir que la phase).
    return /class="pill(?![^"]*(?:statusTone|warn|dang|ok))[^"]*"[^>]*>\$\{[a-z]+\.status/.test(s) ||
           /class="\$\{pillClass\([^)]*\)\}"/.test(s) === false && /\$\{[a-z]+\.status\}<\/span>/.test(s) && !/pillClass/.test(s);
  }).map(p => path.relative(SRC, p));
  check("aucune vue ne rend un statut en pastille SANS sa famille", !fautives.length,
        fautives.join(", "));

  // ── les vues touchées se chargent (RM2889 : une ES qui casse au boot est silencieuse)
  for (const rel of ["meta/Meta.view.js", "projects/ProjectPane.view.js", "review/Review.view.js",
                     "tickets/TicketsPanel.view.js", "worklog/Worklog.view.js"]) {
    try { await import("file://" + path.join(SRC, "modules", rel)); check(`${rel} se charge`, true); }
    catch (e) { check(`${rel} se charge`, false, e.message); }
  }

  // ── RM3126/F005 : le titre du ticket courant, entre la liste et les onglets
  const MVM = await import("file://" + path.join(SRC, "modules/meta/MetaViewModel.js"));
  const mk = (r) => Object.assign(Object.create(MVM.TicketsViewModel ? MVM.TicketsViewModel.prototype : {}),
                                  { r, list: [1], sel: 1 });
  const vmOk = mk({ found: true, title: "Un titre de ticket" });
  const vmVide = mk(undefined), vmAbsent = mk({ found: false });
  check("le titre du ticket courant est exposé", Object.getOwnPropertyDescriptor(
    Object.getPrototypeOf(vmOk), "currentTitle") ? vmOk.currentTitle === "Un titre de ticket" : true);
  check("pas de titre tant qu'il n'est pas chargé (pas de clignotement)",
        Object.getOwnPropertyDescriptor(Object.getPrototypeOf(vmVide), "currentTitle")
          ? vmVide.currentTitle === "" && vmAbsent.currentTitle === "" : true);
  const vue = fs.readFileSync(path.join(SRC, "modules/meta/Meta.view.js"), "utf8");
  const iListe = vue.indexOf('data-action="tab"'), iTitre = vue.indexOf('class="rtitle"'),
        iOnglets = vue.indexOf('class="rsub facets"');
  check("le titre est ENTRE la liste des tickets et les onglets (l'ordre demandé)",
        iListe > 0 && iTitre > iListe && iOnglets > iTitre, `${iListe}/${iTitre}/${iOnglets}`);
  const css = fs.readFileSync(path.join(DIR, "cockpit.css"), "utf8");
  check("la ligne de titre est stylée et bornée", /\.rtitle/.test(css) && /line-clamp/.test(css));

  // ── RM3126/F002 : le provider du ticket, avec ses secondaires
  {
    const MV = await import("file://" + path.join(SRC, "modules/meta/Meta.view.js"));
    const MM = await import("file://" + path.join(SRC, "modules/meta/MetaViewModel.js"));
    const mk = (prov) => new MM.ProjectBriefViewModel(
      { client: "matnat", project: "infra", card: {}, provider: prov });
    const avec = String(MV.ProjectBrief(mk({ name: "redmine-ipro", type: "redmine",
                                             url: "https://t", secondaries: ["redmine-matnat"] })));
    check("le provider du ticket est affiché", /redmine-ipro/.test(avec));
    check("les secondaires déclarés le sont aussi — c'est là que ça compte",
          /\+ redmine-matnat/.test(avec));
    check("l'infobulle dit le type et l'URL de l'instance",
          /instance de gestion des tickets \(redmine\)/.test(avec) && /https:\/\/t/.test(avec));
    check("aucune ligne « provider » quand le serveur ne l'a pas résolu — on ne devine pas",
          !/provider/.test(String(MV.ProjectBrief(mk(null)))) &&
          !/provider/.test(String(MV.ProjectBrief(mk({})))));
  }

  console.log(ko ? `\n${ko} échec(s)` : "\nOK — code couleur des statuts (RM3126)");
  process.exit(ko ? 1 : 0);
})();
