#!/usr/bin/env node
/* Tests RM3036 — logique pure de browser-check (aucun Chromium requis).
 *
 * Ce qui est protégé ici, et pourquoi :
 *   1. un scénario MAL ÉCRIT échoue bruyamment. Une option mal tapée qui passe en
 *      silence produit un « ok » qui ne prouve rien : c'est pire que pas de test —
 *      c'est exactement la confiance mal placée qui a laissé passer RM3025 ;
 *   2. un contrôle NON DEMANDÉ n'est pas rendu « ok ». Le rapport ne doit affirmer que
 *      ce qui a été réellement observé ;
 *   3. la console fait échouer par DÉFAUT. Une erreur JS ne remonte nulle part ailleurs ;
 *   4. le Chromium retenu est celui du cache de recette, pas un navigateur système
 *      arbitraire : on valide avec le moteur dont on connaît la version.
 *
 * Lancer : node tools/browser-check/test_browser_check.js
 */
"use strict";
const L = require("./lib.js");

let fails = 0;
function check(nom, cond, detail) {
  console.log((cond ? "ok   " : "FAIL ") + nom + (cond || !detail ? "" : " — " + detail));
  if (!cond) fails++;
}
const nomsKO = (r) => r.checks.filter((c) => !c.ok).map((c) => c.nom);

// ── parseArgs ────────────────────────────────────────────────────────────────
let { opts, erreurs } = L.parseArgs(["--url", "https://x/y", "--click", "#add", "--expect-change", "#cart"]);
check("scénario valide : aucune erreur", erreurs.length === 0, erreurs.join(", "));
check("url lue", opts.url === "https://x/y");
check("wait par défaut", opts.wait === L.WAIT_DEFAUT);
check("drapeaux à false par défaut", opts.allowConsoleErrors === false && opts.json === false);

({ opts } = L.parseArgs(["--url", "https://x", "--allow-missing-assets"]));
check("--allow-missing-assets reconnu", opts.allowMissingAssets === true);

({ erreurs } = L.parseArgs(["--url", "https://x", "--expct-selector", ".a"]));
check("option MAL TAPÉE => erreur (jamais un silence)", erreurs.some((e) => e.includes("--expct-selector")));

({ erreurs } = L.parseArgs(["--click", "#a"]));
check("--url manquante => erreur", erreurs.some((e) => e.includes("--url")));

({ erreurs } = L.parseArgs(["--url", "https://x"]));
check("--url seule suffit (simple chargement de page)", erreurs.length === 0, erreurs.join(", "));

({ erreurs } = L.parseArgs(["--url", "https://x", "--expect-change", "#cart"]));
check("--expect-change sans --click => erreur (sans geste, rien ne peut changer)",
      erreurs.some((e) => e.includes("--expect-change")));

({ erreurs } = L.parseArgs(["--url"]));
check("valeur manquante en fin de ligne => erreur", erreurs.some((e) => e.includes("attend une valeur")));

({ erreurs } = L.parseArgs(["--url", "https://x", "--wait", "vite"]));
check("--wait non numérique => erreur (et pas un défaut silencieux)",
      erreurs.some((e) => e.includes("--wait")));
({ opts } = L.parseArgs(["--url", "https://x", "--wait", "4000"]));
check("--wait numérique retenu", opts.wait === 4000);

({ opts, erreurs } = L.parseArgs(["--help"]));
check("--help ne réclame pas --url", opts.help === true && erreurs.length === 0);

// ── pickChromium ─────────────────────────────────────────────────────────────
const HOME = "/home/dev";
check("cache puppeteer préféré au navigateur système",
      L.pickChromium(["/usr/bin/chromium", HOME + "/.cache/puppeteer/chrome-131/chrome-linux64/chrome"])
      === HOME + "/.cache/puppeteer/chrome-131/chrome-linux64/chrome");
check("headless_shell préféré à chrome dans le même cache",
      L.pickChromium([HOME + "/.cache/puppeteer/c/chrome", HOME + "/.cache/puppeteer/c/headless_shell"])
      === HOME + "/.cache/puppeteer/c/headless_shell");
check("cache playwright reconnu comme cache de recette",
      L.pickChromium(["/usr/bin/google-chrome", HOME + "/.cache/ms-playwright/chromium-1140/chrome-linux/chrome"])
      === HOME + "/.cache/ms-playwright/chromium-1140/chrome-linux/chrome");
check("système accepté en dernier recours", L.pickChromium(["/usr/bin/chromium"]) === "/usr/bin/chromium");
check("aucun binaire => null (le script doit REFUSER, pas improviser)",
      L.pickChromium([]) === null && L.pickChromium(null) === null);
check("choix déterministe (deux caches équivalents)",
      L.pickChromium(["/h/.cache/puppeteer/b/chrome", "/h/.cache/puppeteer/a/chrome"])
      === L.pickChromium(["/h/.cache/puppeteer/a/chrome", "/h/.cache/puppeteer/b/chrome"]));

// ── evaluate : le verdict ────────────────────────────────────────────────────
const SCENARIO = { url: "u", click: "#add", expectChange: "#cart", expectSelector: "#add",
                   expectText: "Ajouté", allowConsoleErrors: false, wait: 1500 };
let r = L.evaluate(SCENARIO, {
  status: 200, selectorFound: true, clickable: true, clicked: true,
  avant: "0", apres: "1", textFound: true, consoleErrors: [],
});
check("scénario nominal : tout passe", r.ok, nomsKO(r).join(", "));
check("…et les 8 contrôles sont rendus (page, sélecteur, cliquable, clic, effet, texte, assets, JS)",
      r.checks.length === 8, String(r.checks.length));

// (1) la page qui ne répond pas — le cas RM3025 n° 1
r = L.evaluate({ url: "u" }, { status: 500, consoleErrors: [] });
check("HTTP 500 => ÉCHEC", !r.ok && nomsKO(r).some((n) => n.includes("répond")));
r = L.evaluate({ url: "u" }, { status: null, consoleErrors: [] });
check("page injoignable (status null) => ÉCHEC", !r.ok);
r = L.evaluate({ url: "u" }, { status: 301, consoleErrors: [] });
check("redirection 3xx => OK (la page répond)", r.ok, nomsKO(r).join(", "));
r = L.evaluate({ url: "u" }, { status: 404, consoleErrors: [] });
check("404 => ÉCHEC", !r.ok);

// (2) la console — le cas RM3025 n° 2 (bundle non régénéré)
r = L.evaluate({ url: "u" }, { status: 200, consoleErrors: ["addpalier is not a function"] });
check("erreur JS => ÉCHEC PAR DÉFAUT", !r.ok && nomsKO(r).some((n) => n.includes("console")));
check("…et l'erreur est CITÉE dans le rapport",
      r.checks.some((c) => (c.detail || "").includes("addpalier")));
r = L.evaluate({ url: "u", allowConsoleErrors: true }, { status: 200, consoleErrors: ["bruit tiers"] });
check("--allow-console-errors : toléré, mais le rapport le DIT",
      r.ok && r.checks.some((c) => c.nom.includes("erreurs JS tolérées")));

// asset manquant : le bundle CCC non régénéré de RM3025 se voit ICI, pas dans les erreurs JS
const ASSET = "Failed to load resource: the server responded with a status of 404 (Not Found)";
let cl = L.classerErreurs([ASSET, "x is not a function", "net::ERR_ABORTED"]);
check("classement : 404 et net::ERR_ comptés comme ressources", cl.assets.length === 2, JSON.stringify(cl));
check("classement : le plantage JS reste une erreur JS", cl.js.length === 1 && cl.js[0].includes("not a function"));
check("classement : liste vide tolérée", L.classerErreurs(null).js.length === 0);

r = L.evaluate({ url: "u" }, { status: 200, consoleErrors: [ASSET] });
check("ressource 404 => ÉCHEC (déploiement incomplet)",
      !r.ok && nomsKO(r).some((n) => n.includes("ressources se chargent")));
check("…et ce n'est PAS imputé aux erreurs JS",
      r.checks.some((c) => c.nom === "aucune erreur JS en console" && c.ok));
r = L.evaluate({ url: "u", allowConsoleErrors: true }, { status: 200, consoleErrors: [ASSET] });
check("--allow-console-errors ne fait PAS taire un asset manquant", !r.ok);
r = L.evaluate({ url: "u", allowMissingAssets: true }, { status: 200, consoleErrors: [ASSET, "boom"] });
check("--allow-missing-assets ne fait PAS taire un plantage JS",
      !r.ok && nomsKO(r).length === 1 && nomsKO(r)[0].includes("JS"));

// (3) le geste et son effet
r = L.evaluate({ url: "u", click: "#add" }, { status: 200, clickable: false, consoleErrors: [] });
check("élément à cliquer absent => ÉCHEC", !r.ok && nomsKO(r).some((n) => n.includes("cliquable")));
check("…et on n'affirme pas avoir cliqué", !r.checks.some((c) => c.nom === "clic effectué"));
r = L.evaluate({ url: "u", click: "#add", expectChange: "#cart" },
               { status: 200, clickable: true, clicked: true, avant: "0", apres: "0", consoleErrors: [] });
check("panier inchangé après le clic => ÉCHEC", !r.ok && nomsKO(r).some((n) => n.includes("changé")));
check("…avec le avant/après lisible dans le détail",
      r.checks.some((c) => (c.detail || "").includes('avant="0"') && (c.detail || "").includes('après="0"')));
r = L.evaluate({ url: "u", click: "#add", expectChange: "#cart" },
               { status: 200, clickable: true, clicked: true, avant: null, apres: null, consoleErrors: [] });
check("sélecteur d'effet introuvable des deux côtés => ÉCHEC (rien de constaté)", !r.ok);

// (4) on ne rend jamais « ok » un contrôle non demandé
r = L.evaluate({ url: "u" }, { status: 200, consoleErrors: [] });
check("scénario minimal : 3 contrôles seulement (page + assets + JS)", r.checks.length === 3, String(r.checks.length));
check("…aucun contrôle de sélecteur inventé", !r.checks.some((c) => c.nom.includes("sélecteur")));
r = L.evaluate({ url: "u", expectText: "Ajouté" }, { status: 200, consoleErrors: [] });
check("texte demandé mais non observé => ÉCHEC (pas de « ok » par défaut)",
      !r.ok && nomsKO(r).some((n) => n.includes("texte")));
r = L.evaluate({ url: "u", expectSelector: "#x" }, { status: 200, consoleErrors: [] });
check("sélecteur demandé mais non observé => ÉCHEC", !r.ok);
r = L.evaluate({ url: "u" }, {});
check("observation vide => ÉCHEC (l'absence de preuve n'est pas une preuve)", !r.ok);

// ── formatReport ─────────────────────────────────────────────────────────────
const txt = L.formatReport(L.evaluate({ url: "u" }, { status: 500, consoleErrors: [] }));
check("rapport d'échec : verdict explicite", txt.trim().endsWith("ÉCHEC — ne pas livrer"), txt);
check("rapport d'échec : la ligne fautive est marquée FAIL", txt.includes("FAIL la page répond"));

// ── pilote : le scénario s'écrit pareil, seule l'attente réseau change de nom ──
check("playwright préféré (c'est lui qui est en cache sur les postes de recette)",
      L.pickDriver(["puppeteer-core", "playwright-core"]) === "playwright-core");
check("puppeteer accepté s'il est seul", L.pickDriver(["puppeteer-core"]) === "puppeteer-core");
check("aucun pilote => null (le script doit REFUSER de conclure)", L.pickDriver([]) === null);
check("un module non reconnu n'est pas pris pour un pilote", L.pickDriver(["cheerio"]) === null);
check("attente réseau : nom playwright", L.waitUntil("playwright-core") === "networkidle");
check("attente réseau : nom puppeteer", L.waitUntil("puppeteer-core") === "networkidle2");
const txtOk = L.formatReport(L.evaluate({ url: "u" }, { status: 200, consoleErrors: [] }));
check("rapport de succès : verdict OK", txtOk.trim().endsWith("OK"));

console.log();
if (fails) {
  console.log("ÉCHEC (" + fails + ")");
  process.exit(1);
}
console.log("== OK ==");
