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
