/* browser-check — LOGIQUE PURE (RM3036).
 *
 * Aucune E/S ici : ni fichier, ni réseau, ni navigateur. Tout ce qui se décide sans
 * Chromium est décidé ici, donc testable sans Chromium — c'est exactement le point
 * faible qui a laissé passer l'incident RM3025 : on ne teste pas ce qu'on ne peut pas
 * lancer. L'entrée `browser-check.js` observe la page et délègue le VERDICT à ce module.
 */
"use strict";

/** Options reconnues : nom long → clé interne, et si l'option consomme une valeur. */
const OPTIONS = {
  "--url": ["url", true],
  "--expect-selector": ["expectSelector", true],
  "--click": ["click", true],
  "--expect-text": ["expectText", true],
  "--expect-change": ["expectChange", true],
  "--wait": ["wait", true],
  "--screenshot": ["screenshot", true],
  "--allow-console-errors": ["allowConsoleErrors", false],
  "--allow-missing-assets": ["allowMissingAssets", false],
  "--json": ["json", false],
  "--help": ["help", false],
  "-h": ["help", false],
};

const WAIT_DEFAUT = 1500;

/**
 * Analyse la ligne de commande (argv SANS `node` ni le nom du script).
 * Une option inconnue est une ERREUR, pas un silence : un scénario mal tapé qui « passe »
 * est pire que pas de test du tout — il fait croire à une validation.
 *
 * @returns {{opts: object, erreurs: string[]}}
 */
function parseArgs(argv) {
  const opts = { wait: WAIT_DEFAUT, allowConsoleErrors: false, allowMissingAssets: false,
                 json: false, help: false };
  const erreurs = [];
  for (let i = 0; i < argv.length; i++) {
    const brut = argv[i];
    const spec = OPTIONS[brut];
    if (!spec) {
      erreurs.push("option inconnue : " + brut);
      continue;
    }
    const [cle, prendValeur] = spec;
    if (!prendValeur) {
      opts[cle] = true;
      continue;
    }
    if (i + 1 >= argv.length) {
      erreurs.push(brut + " attend une valeur");
      continue;
    }
    const val = argv[++i];
    if (cle === "wait") {
      const n = parseInt(val, 10);
      if (isNaN(n) || n < 0) {
        erreurs.push("--wait attend un entier de millisecondes, reçu : " + val);
      } else {
        opts.wait = n;
      }
    } else {
      opts[cle] = val;
    }
  }
  if (!opts.help && !opts.url) {
    erreurs.push("--url est obligatoire");
  }
  // --expect-change n'a de sens qu'après un geste : sans clic, il compare une page à
  // elle-même et « échoue » toujours. Mieux vaut le dire que rendre un faux rouge.
  if (opts.expectChange && !opts.click) {
    erreurs.push("--expect-change exige --click (sans geste, rien ne peut changer)");
  }
  return { opts, erreurs };
}

/**
 * Choisit le binaire Chromium parmi les chemins trouvés sur la machine.
 * Priorité au cache puppeteer/playwright (la version avec laquelle on a déjà validé),
 * le navigateur système en dernier recours. `headless_shell` avant `chrome` : plus léger,
 * même moteur.
 */
function pickChromium(chemins) {
  const l = (chemins || []).filter(Boolean);
  const rang = (p) => {
    const cache = /[\\/]\.cache[\\/](puppeteer|ms-playwright)[\\/]/.test(p) ? 0 : 10;
    const shell = /headless_shell$/.test(p) ? 0 : 1;
    return cache + shell;
  };
  const tri = l.slice().sort((a, b) => rang(a) - rang(b) || a.localeCompare(b));
  return tri.length ? tri[0] : null;
}

/**
 * Pilotes de navigateur reconnus, par ordre de préférence.
 * playwright d'abord : c'est lui qui est déjà en cache sur les postes de recette
 * (~/.cache/ms-playwright) et qui a servi à diagnostiquer RM3025. puppeteer reste
 * accepté — le scénario s'écrit pareil, seul le nom de l'attente réseau change.
 */
const PILOTES = ["playwright-core", "puppeteer-core", "playwright", "puppeteer"];

/** Parmi les pilotes réellement installés, celui qu'on utilise. */
function pickDriver(disponibles) {
  const dispo = new Set(disponibles || []);
  return PILOTES.find((p) => dispo.has(p)) || null;
}

/** « Réseau calme » ne porte pas le même nom des deux côtés. */
function waitUntil(pilote) {
  return String(pilote || "").indexOf("playwright") === 0 ? "networkidle" : "networkidle2";
}

/**
 * Sépare les erreurs de console en deux familles, parce qu'elles n'ont pas le même sens.
 *
 *   · ASSET MANQUANT (404 sur un .js/.css/une image) : le déploiement est incomplet.
 *     C'est littéralement le second bug de RM3025 — le bundle CCC n'avait pas été
 *     régénéré. Le navigateur le crie ; encore faut-il l'écouter à part.
 *   · ERREUR JS : le code chargé plante.
 *
 * Les confondre, c'est se retrouver à passer `--allow-console-errors` pour faire taire
 * une image manquante… et masquer du même coup un vrai plantage.
 */
function classerErreurs(erreurs) {
  const js = [];
  const assets = [];
  for (const e of erreurs || []) {
    (/failed to load resource|net::ERR_|ERR_ABORTED/i.test(String(e)) ? assets : js).push(String(e));
  }
  return { js, assets };
}

/**
 * Rend le VERDICT à partir du scénario demandé et de ce qui a été observé dans la page.
 *
 * `observe` : {status, selectorFound, clickable, textFound, avant, apres, consoleErrors[]}
 * Une clé absente = contrôle non demandé, donc non rendu. On ne fabrique pas de « ok »
 * pour un contrôle qui n'a pas eu lieu.
 *
 * @returns {{checks: [{nom, ok, detail}], ok: boolean}}
 */
function evaluate(opts, observe) {
  const o = observe || {};
  const checks = [];
  const add = (nom, ok, detail) => checks.push({ nom, ok: !!ok, detail: detail || "" });

  // 1. la page RÉPOND — un fichier déployé n'est pas une page qui s'affiche (RM3025 : 500)
  add("la page répond en 2xx/3xx",
      typeof o.status === "number" && o.status >= 200 && o.status < 400,
      "HTTP " + o.status);

  if (opts.expectSelector) {
    add("sélecteur présent : " + opts.expectSelector, o.selectorFound === true);
  }
  // 2. le GESTE est réellement exécuté, pas lu dans le source
  if (opts.click) {
    add("élément cliquable : " + opts.click, o.clickable === true);
    if (o.clickable === true) {
      add("clic effectué", o.clicked === true);
    }
  }
  // 3. l'EFFET est constaté DANS L'INTERFACE, pas déduit de la base
  if (opts.expectChange) {
    add("le contenu de « " + opts.expectChange + " » a changé",
        o.avant !== o.apres,
        "avant=" + JSON.stringify(o.avant === undefined ? null : o.avant)
        + " après=" + JSON.stringify(o.apres === undefined ? null : o.apres));
  }
  if (opts.expectText) {
    add("texte présent : " + opts.expectText, o.textFound === true);
  }
  // 4. la CONSOLE est lue — rien d'autre ne rapporte ces deux pannes-là (RM3025)
  const { js, assets } = classerErreurs(o.consoleErrors);
  if (assets.length && opts.allowMissingAssets) {
    add("ressources manquantes tolérées (--allow-missing-assets)", true, assets.slice(0, 3).join(" | "));
  } else {
    add("toutes les ressources se chargent (assets déployés / bundle régénéré)",
        assets.length === 0, assets.slice(0, 3).join(" | "));
  }
  if (js.length && opts.allowConsoleErrors) {
    add("erreurs JS tolérées (--allow-console-errors)", true, js.slice(0, 3).join(" | "));
  } else {
    add("aucune erreur JS en console", js.length === 0, js.slice(0, 3).join(" | "));
  }

  return { checks, ok: checks.every((c) => c.ok) };
}

/** Rendu console : une ligne par contrôle, verdict en dernier. */
function formatReport(res) {
  const lignes = res.checks.map(
    (c) => (c.ok ? "ok   " : "FAIL ") + c.nom + (c.ok || !c.detail ? "" : " — " + c.detail)
  );
  lignes.push("", res.ok ? "OK" : "ÉCHEC — ne pas livrer");
  return lignes.join("\n");
}

module.exports = { OPTIONS, WAIT_DEFAUT, PILOTES, parseArgs, pickChromium, pickDriver,
                   waitUntil, classerErreurs, evaluate, formatReport };
