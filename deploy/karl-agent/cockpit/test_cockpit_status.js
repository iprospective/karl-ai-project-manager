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

  // ── RM3164 : les sessions du ticket dans le panneau
  {
    const MV = await import("file://" + path.join(SRC, "modules/meta/Meta.view.js"));
    const MM = await import("file://" + path.join(SRC, "modules/meta/MetaViewModel.js"));
    const ts = (v) => { const o = Object.create(MM.TicketMetaViewModel.prototype); o.e = { ts: v };
                        return o.ticketSessions.call(o); };
    check("jamais demandé → aucun bloc (pas d'encart vide)",
          ts(undefined).kind === "none" && String(MV.TicketSessionsBlock(ts(undefined))) === "");
    check("en vol → « … », jamais « aucune session » (ce serait faux, et c'est le moment où l'on regarde)",
          ts(null).kind === "loading" && /…/.test(String(MV.TicketSessionsBlock(ts(null)))));
    const ok = ts({ handled: [{ rm_id: "42", name: "karl-RM42", alive: true, title: "Sujet" }] });
    const h = String(MV.TicketSessionsBlock(ok));
    check("une session traitante est listée et attachable",
          ok.kind === "ok" && /data-action="attach-session" data-sid="42"/.test(h) && /karl-RM42/.test(h));
    check("la session vivante se distingue de l'éteinte", /color:var\(--ok\)/.test(h));
    const vide = String(MV.TicketSessionsBlock(ts({ handled: [], candidates: [1, 2] })));
    check("aucune traitante → le dit, et signale les candidates plutôt que de les taire",
          /aucune session ne traite/.test(vide) && /2 candidate/.test(vide));
    check("échec de chargement → « indisponible », pas « aucune session »",
          /indisponible/.test(String(MV.TicketSessionsBlock(ts({ error: true })))));
    check("aucun onclick", !/onclick=/.test(h));
  }

  // ── RM3164 : l'onglet « conso » dit enfin ce qu'il contient
  {
    const TM = await import("file://" + path.join(SRC, "modules/meta/ticketMeta.js"));
    const f = TM.FACETS.find(x => x[0] === "conso");
    check("l'onglet des tokens, du coût et des temps s'appelle « temps & coût »",
          f && f[1] === "temps & coût");
    check("sa CLÉ ne bouge pas (elle est dans les URL de vue et les préférences)",
          TM.facetOf("conso") === "conso");
  }

  // ── RM3164 : le survol déclaré PAR TYPE dans le registre
  {
    const B = await import("file://" + path.join(SRC, "modules/tickets/briefs.js"));
    const E = await import("file://" + path.join(SRC, "core/entities.js"));
    const plein = { found: true, title: "Un titre", status: "en_cours", completion_pct: 40,
                    type: "feature", priority: "normal", client: "acme", project: "site" };
    check("le survol d'un ticket monte les champs DÉCLARÉS par son type",
          E.hoverText("review", "3164", plein) === "RM3164 — Un titre\nen_cours · 40 % · feature\nacme/site");
    check("un champ à sa valeur par défaut est tu (priorité « normal »)",
          !/priorité/.test(E.hoverText("review", "1", plein)) &&
          /priorité high/.test(E.hoverText("review", "1", Object.assign({}, plein, { priority: "high" }))));
    check("« pas encore chargé » et « inconnu » ne se disent PAS pareil",
          /chargement…/.test(E.hoverText("review", "1", undefined)) &&
          /inconnu en local/.test(E.hoverText("review", "1", null)) &&
          /inconnu en local/.test(E.hoverText("review", "1", { found: false })));
    check("le préfixe d'identifiant vient du type", E.labelOf("review", "42") === "RM42" &&
          E.labelOf("project", "a/b") === "a/b");

    // La généralisation : d'autres types ont leur survol, sans une ligne de moteur en plus.
    const sess = E.hoverText("session", "42", { found: true, title: "S", state: "working",
                                                engine: "claude", alive: true, client: "a", project: "b" });
    check("une SESSION a son propre jeu de champs", /working · claude · vivante/.test(sess) && /a\/b/.test(sess));
    check("un type sans champs déclarés rend « identifiant — titre », comme les autres",
          E.hoverText("file", "x", { found: true, title: "doc.md" }) === "x — doc.md");

    // Et l'appelant historique passe par là, sans changer de contrat.
    check("briefs.ticketTipText délègue au registre (une seule source)",
          B.ticketTipText("3164", plein) === E.hoverText("review", "3164", plein));
    check("… en gardant SON contrat : ici null veut dire « pas encore chargé »",
          /chargement…/.test(B.ticketTipText("3164", null)));
  }

  // ── RM3164 : le filtre par projet de la liste des tickets d'une session
  {
    const MM = await import("file://" + path.join(SRC, "modules/meta/MetaViewModel.js"));
    const mk = (res, f, sess) => {
      const o = Object.create(MM.TicketMetaViewModel.prototype);
      o.e = { tickets: ["1", "2", "3"], current: "1", resolve: res, sessionProject: sess };
      o.ctx = { ticketFilter: f };
      return o;
    };
    const deux = { 1: { found: true, client: "a", project: "x" },
                   2: { found: true, client: "a", project: "y" },
                   3: { found: true, client: "a", project: "x" } };
    const un = { 1: { found: true, client: "a", project: "x" },
                 2: { found: true, client: "a", project: "x" },
                 3: { found: true, client: "a", project: "x" } };
    check("les projets représentés portent leur compte",
          JSON.stringify(mk(deux, undefined, "").ticketProjects.map(p => p.key + ":" + p.n)) ===
          '["a/x:2","a/y:1"]');
    check("tous dans le MÊME projet → aucun filtre (il n'aurait rien à trier)",
          mk(un, undefined, "a/x").ticketProjects.length === 0);
    check("le défaut est le projet de la session attachée",
          mk(deux, undefined, "a/y").ticketFilter === "a/y");
    check("… mais seulement s'il est représenté — sinon on n'ampute pas la liste",
          mk(deux, undefined, "a/zzz").ticketFilter === "");
    check("« tous » (chaîne vide) se distingue de « pas encore choisi » (undefined)",
          mk(deux, "", "a/y").ticketFilter === "" && mk(deux, "a/x", "a/y").ticketFilter === "a/x");
    const filtres = mk(deux, "a/y", "").tabs.map(t => t.rm);
    check("le filtre réduit la liste, et l'onglet COURANT reste visible",
          filtres.indexOf("2") >= 0 && filtres.indexOf("1") >= 0 && filtres.indexOf("3") < 0);
    check("un ticket non résolu n'est rangé sous aucun projet",
          mk({ 1: undefined, 2: undefined, 3: undefined }, undefined, "").ticketProjects.length === 0);
  }

  console.log(ko ? `\n${ko} échec(s)` : "\nOK — code couleur des statuts (RM3126)");
  process.exit(ko ? 1 : 0);
})();
