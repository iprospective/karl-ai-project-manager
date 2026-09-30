#!/usr/bin/env node
/* browser-check — valider une page au NAVIGATEUR avant de livrer du front (RM3036).
 *
 * Comble un trou d'outillage réel. Le 2026-09-08 (RM3025), une modification front est
 * partie en production sans passage navigateur et a cassé l'ajout au panier. Deux causes
 * qu'aucun test unitaire ne pouvait voir : un endpoint en 500 (visible seulement à
 * l'exécution HTTP) et un bundle d'assets non régénéré (visible seulement à l'assemblage
 * dans la page). Un seul chargement de page les attrapait.
 *
 * Ce script fait les quatre choses que NORMS `testing` § 7 exige d'un site public :
 * charger la page, exécuter le geste, lire la console, constater l'effet dans l'interface.
 *
 * Usage :
 *   node browser-check.js --url https://site/page [options]
 *     --expect-selector "<css>"     échoue si le sélecteur est absent
 *     --click "<css>"               clique, puis attend --wait ms
 *     --expect-text "<texte>"       échoue si le texte est absent de la page rendue
 *     --expect-change "<css>"       échoue si le contenu de ce sélecteur n'a PAS changé
 *                                   après le clic (le compteur panier qui passe 0 → 1)
 *     --wait <ms>                   attente après le clic (défaut 1500)
 *     --screenshot <fichier.png>    capture pleine page, y compris en cas d'échec
 *     --allow-console-errors        n'échoue pas sur une erreur JS (à justifier)
 *     --allow-missing-assets        n'échoue pas sur un 404 de ressource (à justifier)
 *     --json                        sortie machine
 *
 *   Mode PARCOURS (RM3359) — un tunnel de commande ne se joue pas en un clic :
 *     --scenario <fichier.json>     suite d'étapes : goto, remplir, choisir, cliquer,
 *                                   attendre, verifier-selecteur, verifier-texte,
 *                                   verifier-change, capture
 *     --param cle=valeur            paramètre du scénario ({{cle}}), répétable
 *     --secret-env cle=VARIABLE     paramètre lu dans l'ENVIRONNEMENT — un mot de passe ne
 *                                   s'écrit ni dans le scénario ni sur la ligne de commande,
 *                                   que `ps` laisse lire à tout le système
 *
 * Sortie : code 0 si tout passe, 1 sinon — utilisable tel quel dans un protocole de test.
 *
 * Pilote : playwright-core ou puppeteer-core, celui qui est installé (`npm i` dans ce
 * dossier). Chromium : pris dans le cache local (puppeteer / playwright / système). Rien n'est
 * téléchargé. Si aucun binaire n'est présent, le script le DIT et sort en échec plutôt
 * que de laisser croire à une validation qui n'a pas eu lieu.
 *
 * Le verdict vit dans lib.js (pur, testé par test_browser_check.js) ; ce fichier-ci ne
 * fait qu'observer la page et rendre compte.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const os = require("os");
const L = require("./lib.js");
const SC = require("./scenario.js");

// L'aide, c'est l'en-tête du fichier : une seule source, jamais désynchronisée.
const AIDE = fs.readFileSync(__filename, "utf8")
  .split("*/")[0].replace(/^#!.*\n/, "").replace(/^\/\*+ ?| ?\* ?/gm, "").trim();

/** Tous les Chromium présents sur la machine — on ne télécharge rien depuis un test. */
function chromiumsPresents() {
  const trouves = [];
  const racines = [
    path.join(os.homedir(), ".cache", "puppeteer"),
    path.join(os.homedir(), ".cache", "ms-playwright"),
  ];
  for (const racine of racines) {
    const pile = [racine];
    while (pile.length) {
      let entrees = [];
      const dir = pile.pop();
      try {
        entrees = fs.readdirSync(dir, { withFileTypes: true });
      } catch (e) {
        continue;                       // dossier absent ou illisible : rien à y voir
      }
      for (const e of entrees) {
        const complet = path.join(dir, e.name);
        if (e.isDirectory()) pile.push(complet);
        else if (e.name === "chrome" || e.name === "headless_shell") trouves.push(complet);
      }
    }
  }
  for (const p of ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]) {
    if (fs.existsSync(p)) trouves.push(p);
  }
  return trouves;
}

/**
 * Ouvre un navigateur, quel que soit le pilote installé.
 * playwright expose `chromium.launch`, puppeteer `launch` — c'est la seule vraie
 * différence ; le reste du scénario s'écrit à l'identique.
 */
async function lancer(pilote, mod, exe) {
  const commun = { executablePath: exe, args: ["--no-sandbox", "--disable-dev-shm-usage"] };
  if (pilote.indexOf("playwright") === 0) {
    return mod.chromium.launch({ ...commun, headless: true });
  }
  return mod.launch({ ...commun, headless: "new" });
}

/** Charge la page, joue le scénario, et rapporte CE QUI A ÉTÉ OBSERVÉ (aucun verdict ici). */
async function observer(pilote, mod, exe, opts) {
  const obs = { consoleErrors: [] };
  const navigateur = await lancer(pilote, mod, exe);
  try {
    const page = await navigateur.newPage();
    page.on("console", (m) => { if (m.type() === "error") obs.consoleErrors.push(m.text()); });
    page.on("pageerror", (e) => obs.consoleErrors.push(String((e && e.message) || e)));

    const rep = await page.goto(opts.url, { waitUntil: L.waitUntil(pilote), timeout: 30000 });
    obs.status = rep ? rep.status() : null;

    if (opts.expectSelector) {
      obs.selectorFound = !!(await page.$(opts.expectSelector));
    }
    if (opts.expectChange) {
      obs.avant = await page.$eval(opts.expectChange, (el) => el.textContent.trim()).catch(() => null);
    }
    if (opts.click) {
      const cible = await page.$(opts.click);
      obs.clickable = !!cible;
      if (cible) {
        await cible.click();
        await new Promise((r) => setTimeout(r, opts.wait));
        obs.clicked = true;
      }
    }
    if (opts.expectChange) {
      obs.apres = await page.$eval(opts.expectChange, (el) => el.textContent.trim()).catch(() => null);
    }
    if (opts.expectText) {
      obs.textFound = (await page.content()).includes(opts.expectText);
    }
    if (opts.screenshot) {
      await page.screenshot({ path: opts.screenshot, fullPage: true });
      obs.screenshot = opts.screenshot;
    }
  } finally {
    await navigateur.close();
  }
  return obs;
}

/** Joue un parcours validé ; rend un résultat par étape. L'ordre est le seul contrat. */
async function jouerScenario(pilote, mod, exe, plan, opts) {
  const navigateur = await lancer(pilote, mod, exe);
  const resultats = [];
  const erreursJs = [];
  try {
    const page = await navigateur.newPage();
    page.on("console", (m) => { if (m.type() === "error") erreursJs.push(m.text()); });
    page.on("pageerror", (e) => erreursJs.push(String((e && e.message) || e)));

    const memoire = {};   // états relevés par `memoriser`, comparés par `verifier-change`
    for (const etape of plan.etapes) {
      let obs = {};
      try {
        obs = await jouerEtape(page, etape, pilote, opts, memoire);
      } catch (e) {
        obs = { ok: false, detail: String((e && e.message) || e) };
      }
      const r = SC.verdictEtape(etape, obs);
      resultats.push(r);
      if (!r.ok) {
        // On s'ARRÊTE à la première étape ratée : la suite d'un tunnel n'a aucun sens si on
        // n'est pas connecté, et enchaîner produirait quinze échecs pour une seule cause.
        if (opts.screenshot !== false) {
          const f = `echec-etape-${etape.numero}.png`;
          await page.screenshot({ path: f, fullPage: true }).catch(() => {});
          r.capture = f;
        }
        break;
      }
    }
  } finally {
    await navigateur.close();
  }
  return { resultats, erreursJs };
}

/** Exécute UNE étape et rapporte ce qui a été observé — aucun verdict ici. */
async function jouerEtape(page, etape, pilote, opts, memoire) {
  switch (etape.action) {
    case "goto": {
      const rep = await page.goto(etape.url, { waitUntil: L.waitUntil(pilote), timeout: 30000 });
      const code = rep ? rep.status() : null;
      return { ok: typeof code === "number" && code >= 200 && code < 400, detail: "HTTP " + code };
    }
    case "remplir": {
      const el = await page.$(etape.selecteur);
      if (!el) return { ok: false, detail: "champ introuvable" };
      await el.click({ clickCount: 3 }).catch(() => {});
      await el.type(String(etape.valeur));
      return { ok: true };
    }
    case "choisir": {
      const el = await page.$(etape.selecteur);
      if (!el) return { ok: false, detail: "liste introuvable" };
      await page.select(etape.selecteur, String(etape.valeur));
      return { ok: true };
    }
    case "cliquer": {
      const el = await page.$(etape.selecteur);
      if (!el) return { ok: false, detail: "élément introuvable" };
      await el.click();
      await new Promise((r) => setTimeout(r, Number(etape.apres || 1200)));
      return { ok: true };
    }
    case "attendre":
      await new Promise((r) => setTimeout(r, Number(etape.ms)));
      return { ok: true };
    case "attendre-selecteur":
      try {
        await page.waitForSelector(etape.selecteur, { timeout: Number(etape.ms || 10000) });
        return { ok: true };
      } catch (e) {
        return { ok: false, detail: "toujours absent après attente" };
      }
    case "verifier-selecteur":
      return { ok: !!(await page.$(etape.selecteur)), detail: "sélecteur absent" };
    case "verifier-texte":
      return { ok: (await page.content()).includes(etape.texte), detail: "texte absent de la page" };
    case "memoriser": {
      const v = await page.$eval(etape.selecteur, (el) => el.textContent.trim()).catch(() => null);
      memoire[etape.selecteur] = v;
      return { ok: v !== null, detail: "élément introuvable : rien à mémoriser" };
    }
    case "verifier-change": {
      // « a changé » suppose un AVANT : il vient d'une étape `memoriser` sur le même sélecteur.
      // Sans elle on ne compare rien, et on le dit plutôt que de conclure au hasard.
      const apres = await page.$eval(etape.selecteur, (el) => el.textContent.trim()).catch(() => null);
      return { avant: memoire[etape.selecteur], apres };
    }
    case "capture":
      await page.screenshot({ path: etape.fichier, fullPage: true });
      return { ok: true };
    default:
      return { ok: false, detail: "action non exécutable" };
  }
}

async function main() {
  const { opts, erreurs } = L.parseArgs(process.argv.slice(2));
  if (opts.help) {
    console.log(AIDE);
    process.exit(0);
  }
  if (erreurs.length) {
    console.error("browser-check :\n  " + erreurs.join("\n  ") + "\n\n" + AIDE);
    process.exit(2);
  }

  const installes = L.PILOTES.filter((nom) => {
    try {
      require.resolve(nom);
      return true;
    } catch (e) {
      return false;
    }
  });
  const pilote = L.pickDriver(installes);
  if (!pilote) {
    console.error("browser-check : aucun pilote de navigateur (" + L.PILOTES.join(", ") + ").\n"
      + "  cd tools/browser-check && npm i\n"
      + "  AUCUNE validation navigateur n'a eu lieu — ne pas livrer sur la foi de ce script.");
    process.exit(1);
  }
  const mod = require(pilote);
  const exe = L.pickChromium(chromiumsPresents());
  if (!exe) {
    console.error("browser-check : aucun Chromium trouvé (caches puppeteer / ms-playwright, /usr/bin).\n"
      + "  AUCUNE validation navigateur n'a eu lieu — ne pas livrer sur la foi de ce script.");
    process.exit(1);
  }

  // ── mode PARCOURS ────────────────────────────────────────────────────────────
  if (opts.scenario) {
    let brut;
    try {
      brut = JSON.parse(fs.readFileSync(opts.scenario, "utf8"));
    } catch (e) {
      console.error("browser-check : scénario illisible (" + opts.scenario + ") — "
        + String((e && e.message) || e));
      process.exit(2);
    }
    // Les secrets viennent de l'ENVIRONNEMENT, jamais de la ligne de commande : celle-ci est
    // lisible par tout le système. Une variable absente est une erreur, pas une chaîne vide —
    // un mot de passe vide donnerait « identifiants invalides » et on chercherait ailleurs.
    const params = Object.assign({}, opts.params || {});
    const secrets = [];
    for (const [cle, variable] of Object.entries(opts.secretsEnv || {})) {
      const v = process.env[variable];
      if (v === undefined || v === "") {
        console.error(`browser-check : la variable d'environnement ${variable} (paramètre « ${cle} ») est vide`);
        process.exit(2);
      }
      params[cle] = v;
      secrets.push(v);
    }
    const plan = SC.preparer(brut, params);
    if (plan.erreurs.length) {
      // Rien n'est joué tant que TOUT n'est pas valide : s'arrêter au milieu d'un tunnel
      // laisse un panier à moitié rempli et une base sale.
      console.error("browser-check : scénario invalide —\n  " + plan.erreurs.join("\n  "));
      process.exit(2);
    }

    const { resultats, erreursJs } = await jouerScenario(pilote, mod, exe, plan, opts);
    const { js, assets } = L.classerErreurs(erreursJs);
    if (assets.length && !opts.allowMissingAssets) {
      resultats.push({ nom: "ressources chargées", ok: false, detail: assets.slice(0, 3).join(" | ") });
    }
    if (js.length && !opts.allowConsoleErrors) {
      resultats.push({ nom: "aucune erreur JS", ok: false, detail: js.slice(0, 3).join(" | ") });
    }
    const v = SC.verdict(resultats);
    const rendu = (txt) => SC.masquer(txt, secrets);
    if (opts.json) {
      console.log(rendu(JSON.stringify({ scenario: plan.nom, ...v }, null, 2)));
    } else {
      console.log(rendu(plan.nom + " :"));
      for (const r of v.etapes) {
        console.log(rendu("  " + (r.ok ? "ok   " : "FAIL ") + r.nom
          + (r.ok || !r.detail ? "" : " — " + r.detail) + (r.capture ? "  [" + r.capture + "]" : "")));
      }
      console.log(v.ok ? "\nOK" : "\nÉCHEC à l'étape « " + v.echec.nom + " » — ne pas livrer");
    }
    process.exit(v.ok ? 0 : 1);
  }

  let obs;
  try {
    obs = await observer(pilote, mod, exe, opts);
  } catch (e) {
    // La page n'a pas pu être jouée : c'est un échec du scénario, pas un plantage d'outil.
    obs = { status: null, consoleErrors: ["scénario interrompu : " + String((e && e.message) || e)] };
  }
  const res = L.evaluate(opts, obs);

  if (opts.json) {
    console.log(JSON.stringify({ url: opts.url, pilote, chromium: exe, observe: obs, ...res }, null, 2));
  } else {
    console.log(L.formatReport(res));
    if (obs.screenshot) console.log("capture : " + obs.screenshot);
  }
  process.exit(res.ok ? 0 : 1);
}

main().catch((e) => { console.error("browser-check :", e); process.exit(1); });
