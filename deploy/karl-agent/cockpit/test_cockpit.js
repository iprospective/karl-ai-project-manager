#!/usr/bin/env node
// Tests du cockpit (RM2283) — sans navigateur ni dépendance :
//   1. le <script> inline de index.html est syntaxiquement valide ;
//   2. computeGroups (fonction pure, extraite par ses marqueurs >>> <<<) :
//      groupement par client/projet, fallback resolveCache, « divers »,
//      compteurs d'états, tri attention > activité récente > alpha.
// Lancer : node deploy/karl-agent/cockpit/test_cockpit.js
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const vm = require("vm");

const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");

// — 1. syntaxe de TOUS les blocs <script> inline (RM2386 : le boot de thème
//      vit dans un <script id="theme-boot"> du <head> ; une erreur de syntaxe
//      dedans casserait la page sans que rien ne l'attrape) —
const blocks = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
assert(blocks.length >= 2, "attendu au moins 2 blocs <script> (theme-boot + principal)");
blocks.forEach((b, i) => new vm.Script(b[1], { filename: `index.html<script#${i}>` }));
console.log(`✓ syntaxe des ${blocks.length} blocs <script> inline`);

// — 2. computeGroups —
const fm = />>> computeGroups[\s\S]*?(function computeGroups[\s\S]*?)\n\/\/ <<< computeGroups/.exec(html);
assert(fm, "marqueurs >>> computeGroups / <<< computeGroups introuvables");
// computeGroups référence la constante module OTHER_SETS_GROUP (RM2445) : la fournir
// au contexte isolé (sinon ReferenceError). Extraite du source pour éviter la dérive.
const otherGrp = /const OTHER_SETS_GROUP = "([^"]*)"/.exec(html)[1];
const computeGroups = vm.runInNewContext("(" + fm[1] + ")", { OTHER_SETS_GROUP: otherGrp });

// groupement : jonction directe, fallback /resolve, divers
const sessions = [
  { rm_id: "1", client: "acme", project: "shop", state: "working", created: 100 },
  { rm_id: "2", client: "acme", project: "shop", state: "idle", created: 200 },
  { rm_id: "3", state: "attention", created: 50 },              // via resolveCache
  { rm_id: "4", is_ticket: false, state: "working", created: 300 }, // non PM-tracké
];
const rcache = { "3": { found: true, client: "beta", project: "api" } };
const { keys, groups, counts } = computeGroups(sessions, rcache, true);   // tri dynamique opt-in (RM2344)

assert.deepStrictEqual(new Set(keys), new Set(["acme/shop", "beta/api", "divers"]), "clés de groupes");
assert.strictEqual(groups.get("acme/shop").length, 2, "2 sessions acme/shop");
assert.strictEqual(groups.get("beta/api")[0].rm_id, "3", "fallback resolveCache");
assert.strictEqual(groups.get("divers")[0].rm_id, "4", "non résolu → divers");
console.log("✓ groupement par client/projet (+ fallback, + divers)");

// compteurs d'états
assert.deepStrictEqual({ ...counts }, { total: 4, attention: 1, choice: 0, idle: 1, working: 2, ghost: 0 }, "compteurs");
// RM2427 : les sessions ENREGISTRÉES non démarrées s'affichent (groupées comme les
// autres) mais ne comptent ni dans `total` ni dans les états d'activité.
const gh = computeGroups([
  { rm_id: "1", client: "acme", project: "shop", state: "working", created: 100 },
  { rm_id: "2", client: "acme", project: "shop", state: "ghost", ghost: true, created: null },
  { rm_id: "3", ghost: true, state: "ghost" },
], {}, true);
assert.deepStrictEqual({ ...gh.counts }, { total: 1, attention: 0, choice: 0, idle: 0, working: 1, ghost: 2 }, "compteurs fantômes");
assert.strictEqual(gh.groups.get("acme/shop").length, 2, "le fantôme est groupé avec sa session vivante");
assert.strictEqual(gh.groups.get("divers")[0].rm_id, "3", "fantôme non résolu → divers");
console.log("✓ RM2427 : fantômes affichés, comptés à part, hors compteurs d'activité");
// RM2327 : l'état choice est compté à part et fait remonter son groupe
const cg = computeGroups([
  { rm_id: "9", client: "c", project: "p", state: "choice", created: 1 },
  { rm_id: "8", client: "d", project: "q", state: "working", created: 999 },
], {}, true);
assert.strictEqual(cg.counts.choice, 1, "compteur choice");
assert.strictEqual(cg.keys[0], "c/p", "groupe avec choice priorisé");
console.log("✓ compteurs total/attention/choice/idle/working (+ tri choice)");


// RM2537 : « hors du jeu courant » garde le chantier. Une vivante hors jeu était
// versée dans un groupe unique, perdant son en-tête client/projet — « hors du
// jeu » ne veut pas dire « sans projet ». Elle reste rangée en fin de liste.
const oc = computeGroups([
  { rm_id: "1", client: "acme", project: "shop", state: "working", created: 100, in_current: true },
  { rm_id: "2", client: "beta", project: "api", state: "idle", created: 200, in_current: false },
  { rm_id: "3", client: "gamma", project: "web", state: "idle", created: 300, in_current: false },
  { rm_id: "4", ghost: true, state: "ghost", client: "beta", project: "api", in_current: false },
], {}, true);
assert(oc.keys.includes(otherGrp + " · beta/api"), "hors jeu : un groupe par chantier");
assert(oc.keys.includes(otherGrp + " · gamma/web"), "hors jeu : chantiers distincts non fusionnés");
assert.strictEqual(oc.keys[0], "acme/shop", "le jeu courant reste en tête");
assert(oc.keys.indexOf(otherGrp + " · beta/api") > 0 &&
       oc.keys.indexOf(otherGrp + " · gamma/web") > 0, "les hors-jeu restent en fin de liste");
assert.strictEqual(oc.groups.get("beta/api").length, 1,
  "un FANTÔME n'est jamais relégué hors du jeu (il est déjà éteint)");
assert.strictEqual(oc.groups.get(otherGrp + " · beta/api")[0].rm_id, "2", "la vivante hors jeu, elle, l'est");
console.log("✓ RM2537 : hors du jeu courant, mais toujours rangé par chantier");

// tri : le groupe avec attention passe devant, même plus ancien
assert.strictEqual(keys[0], "beta/api", "groupe en attention en tête");
// puis activité récente : divers (created 300) avant acme/shop (200)
assert.strictEqual(keys[1], "divers", "activité récente ensuite");
assert.strictEqual(keys[2], "acme/shop", "le moins récent en dernier");
console.log("✓ tri attention > activité récente > alpha");

// tri alpha à égalité (pas d'attention, même created)
const eq = computeGroups([
  { rm_id: "10", client: "zeta", project: "z", state: "working", created: 10 },
  { rm_id: "11", client: "alpha", project: "a", state: "working", created: 10 },
], {}, true);
assert.deepStrictEqual([...eq.keys], ["alpha/a", "zeta/z"], "alpha à égalité");
console.log("✓ tri alphabétique à égalité");

// RM2344 : SANS l'option (défaut), ordre STABLE — alphabétique pur, l'attention
// et l'activité récente ne réordonnent plus rien.
const stable = computeGroups(sessions, rcache);
assert.deepStrictEqual([...stable.keys], ["acme/shop", "beta/api", "divers"], "défaut = alphabétique stable");
console.log("✓ RM2344 : ordre stable par défaut (tri dynamique = opt-in)");

// aucune session
const empty = computeGroups([], {});
assert.deepStrictEqual([...empty.keys], [], "aucun groupe");
assert.strictEqual(empty.counts.total, 0, "total 0");
console.log("✓ liste vide");

// — 3. mdToHtml (RM2309) —
const fmd = />>> mdToHtml[\s\S]*?(function mdToHtml[\s\S]*?)\n\/\/ <<< mdToHtml/.exec(html);
assert(fmd, "marqueurs >>> mdToHtml / <<< mdToHtml introuvables");
const mdToHtml = vm.runInNewContext("(" + fmd[1] + ")");

// sécurité : tout HTML source est échappé, aucun lien javascript:
let h = mdToHtml('<script>alert(1)</script> et <img src=x onerror=y>');
assert(!/<script|<img/.test(h) && h.includes("&lt;script&gt;"), "XSS échappé");
h = mdToHtml("[clic](javascript:alert(1)) et [ok](https://ex.te/p)");
assert(!h.includes('href="javascript:'), "javascript: refusé");
assert(h.includes('href="https://ex.te/p"') && h.includes('rel="noopener"'), "https autorisé");
console.log("✓ mdToHtml : sûreté (échappement + whitelist de liens)");

// structure : titres, listes + cases, code, gras, tableau, citation, hr, frontmatter
h = mdToHtml("---\ntitle: X\n---\n# Titre\n\n## Sous *titre*\n\ntexte **fort** et `code`\n\n- [x] fait\n- [ ] à faire\n1. un\n\n> note\n\n---\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nlet x = '<b>'\n```");
for (const frag of ['<pre class="mdfm">title: X</pre>', "<h1>Titre</h1>", "<h2>Sous <i>titre</i></h2>",
  "<b>fort</b>", "<code>code</code>", "<li>☑ fait</li>", "<li>☐ à faire</li>", "<ol><li>un</li></ol>",
  "<blockquote>note</blockquote>", "<hr>", "<th>a</th>", "<td>2</td>", "<pre>let x = '&lt;b&gt;'</pre>"])
  assert(h.includes(frag), "fragment attendu : " + frag);
assert(h.startsWith('<div class="mdview">'), "wrapper mdview");
console.log("✓ mdToHtml : titres, listes/cases, code, tableau, citation, hr, frontmatter");

// paragraphes multilignes joints, texte simple sans balisage parasite
h = mdToHtml("ligne un\nligne deux\n\nautre para");
assert(h.includes("<p>ligne un ligne deux</p>") && h.includes("<p>autre para</p>"), "paragraphes");
console.log("✓ mdToHtml : paragraphes");
// — 4. tqMatch (RM2315) : recherche mots-clés dans la file « à tester » —
const fq = />>> tqMatch[\s\S]*?(function tqMatch[\s\S]*?)\n\/\/ <<< tqMatch/.exec(html);
assert(fq, "marqueurs >>> tqMatch / <<< tqMatch introuvables");
const tqMatch = vm.runInNewContext("(" + fq[1] + ")");

const entry = {
  rm_id: "2302", title: "Améliorations ergonomiques design cockpit",
  client: "iprospective", project: "pm-ai-agents", status: "a_tester_demandeur",
  branch: "2302-ameliorations-ergonomiques-desogn-cockpit",
  env: "ai-project-management-rm2302", tags: ["cockpit", "ux"],
};
assert(tqMatch(entry, ""), "requête vide → tout passe");
assert(tqMatch(entry, "   "), "requête blanche → tout passe");
assert(tqMatch(entry, "2302"), "match sur l'id nu");
assert(tqMatch(entry, "RM2302"), "match sur l'id préfixé RM");
assert(tqMatch(entry, "COCKPIT"), "insensible à la casse");
assert(tqMatch(entry, "ameliorations"), "insensible aux accents (améliorations)");
assert(tqMatch(entry, "cockpit ergonomiques"), "multi-mots = ET (les deux présents)");
assert(!tqMatch(entry, "cockpit prestashop"), "multi-mots = ET (un mot absent → rejet)");
assert(tqMatch(entry, "pm-ai-agents"), "match sur client/projet");
assert(tqMatch(entry, "desogn"), "match sur la branche");
assert(tqMatch(entry, "ux"), "match sur un tag");
assert(!tqMatch({ rm_id: "7", title: null, tags: null }, "cockpit"), "champs nuls → pas de crash, rejet");
console.log("✓ tqMatch (RM2315) : mots-clés, casse/accents, ET multi-mots");

// — 5. nextAttentionId (RM2302) —
const fa = />>> nextAttentionId[\s\S]*?(function nextAttentionId[\s\S]*?)\n\/\/ <<< nextAttentionId/.exec(html);
assert(fa, "marqueurs >>> nextAttentionId / <<< nextAttentionId introuvables");
const nextAttentionId = vm.runInNewContext("(" + fa[1] + ")");

const flat = [
  { rm_id: "1", state: "working" },
  { rm_id: "2", state: "attention" },
  { rm_id: "3", state: "idle" },
  { rm_id: "4", state: "attention" },
];
assert.strictEqual(nextAttentionId([], null), null, "liste vide → null");
assert.strictEqual(nextAttentionId([{ rm_id: "1", state: "idle" }], null), null, "aucune attention → null");
assert.strictEqual(nextAttentionId(flat, null), "2", "rien d'attaché → première attention");
assert.strictEqual(nextAttentionId(flat, "1"), "2", "attaché hors attention → première attention");
assert.strictEqual(nextAttentionId(flat, "2"), "4", "attaché sur la 1re attention → la suivante");
assert.strictEqual(nextAttentionId(flat, "4"), "2", "dernière attention → cycle vers la première");
// RM2327 : une session « choice » (choix multiple) fait partie du cycle d'attente
assert.strictEqual(nextAttentionId([
  { rm_id: "1", state: "working" }, { rm_id: "2", state: "choice" },
], null), "2", "choice inclus dans le cycle");
console.log("✓ nextAttentionId (RM2302/RM2327) : cycle sur les sessions en attente");

// — 6. approveShortcutVisible (RM2332) : visibilité des raccourcis ✔ Oui —
const fav = />>> approveShortcutVisible[\s\S]*?(function approveShortcutVisible[\s\S]*?)\n\/\/ <<< approveShortcutVisible/.exec(html);
assert(fav, "marqueurs >>> approveShortcutVisible / <<< approveShortcutVisible introuvables");
const approveShortcutVisible = vm.runInNewContext("(" + fav[1] + ")");

const cache = { "10": { state: "attention" }, "11": { state: "working" } };
assert.strictEqual(approveShortcutVisible("10", cache), true, "attachée en attention → visible");
assert.strictEqual(approveShortcutVisible("11", cache), false, "attachée au travail → masqué");
assert.strictEqual(approveShortcutVisible("99", cache), false, "session inconnue du cache → masqué");
assert.strictEqual(approveShortcutVisible(null, cache), false, "rien d'attaché → masqué");
console.log("✓ approveShortcutVisible (RM2332) : visibilité des raccourcis ✔ Oui");

// — 5. voiceQueue (RM2329) : file d'annonces vocales —
const fv = />>> voiceQueue[\s\S]*?(function voiceQueue[\s\S]*?)\n\/\/ <<< voiceQueue/.exec(html);
assert(fv, "marqueurs >>> voiceQueue / <<< voiceQueue introuvables");
const voiceQueue = vm.runInNewContext("(" + fv[1] + ")");

let spoken = {};
const vs = [
  { rm_id: "1", state: "attention" },
  { rm_id: "2", state: "working" },
  { rm_id: "3", state: "choice" },
];
assert.deepStrictEqual([...voiceQueue(vs, spoken)], ["1", "3"], "attention + choice à annoncer");
spoken = { "1": "Question ?", "3": "Choix ?" };
assert.deepStrictEqual([...voiceQueue(vs, spoken)], [], "déjà annoncées → rien");
// la session 1 repart travailler → purgée du cache → ré-annonçable ensuite
assert.deepStrictEqual([...voiceQueue([{ rm_id: "1", state: "working" }], spoken)], [], "plus en attente → rien");
assert(!("1" in spoken), "sortie d'attente → purge du cache");
assert.deepStrictEqual([...voiceQueue([{ rm_id: "1", state: "attention" }], spoken)], ["1"], "nouvelle question → ré-annonce");
console.log("✓ voiceQueue (RM2329) : annonces sans doublon, ré-annonce après reprise");

// — 6. outlineStep (RM2330) : sauts entre messages utilisateur —
const fo = />>> outlineStep[\s\S]*?(function outlineStep[\s\S]*?)\n\/\/ <<< outlineStep/.exec(html);
assert(fo, "marqueurs >>> outlineStep / <<< outlineStep introuvables");
const outlineStep = vm.runInNewContext("(" + fo[1] + ")");

const oi = [
  { line: 2, kind: "user", text: "premier" },
  { line: 5, kind: "assistant", text: "réponse" },
  { line: 9, kind: "user", text: "deuxième" },
  { line: 14, kind: "user", text: "troisième" },
];
assert.strictEqual(outlineStep(oi, null, -1).line, 14, "depuis le direct, ↑ = dernier message user");
assert.strictEqual(outlineStep(oi, 14, -1).line, 9, "↑ = user précédent (l'assistant est sauté)");
assert.strictEqual(outlineStep(oi, 2, -1), null, "au premier, ↑ = null");
assert.strictEqual(outlineStep(oi, 9, 1).line, 14, "↓ = user suivant");
assert.strictEqual(outlineStep(oi, 14, 1), null, "au dernier, ↓ = null (retour direct géré par l'appelant)");
assert.strictEqual(outlineStep(oi, null, 1), null, "au direct, ↓ = null");
assert.strictEqual(outlineStep([{ line: 1, kind: "assistant", text: "x" }], null, -1), null, "aucun message user → null");
console.log("✓ outlineStep (RM2330) : sauts entre messages utilisateur");

// — 8. pickVoice (RM2350) : choix de la voix de synthèse —
const fpv = />>> pickVoice[\s\S]*?(function pickVoice[\s\S]*?)\n\/\/ <<< pickVoice/.exec(html);
assert(fpv, "marqueurs >>> pickVoice / <<< pickVoice introuvables");
const pickVoice = vm.runInNewContext("(" + fpv[1] + ")");

const voices = [
  { name: "eSpeak French", lang: "fr-FR", localService: true },
  { name: "Google français", lang: "fr-FR", localService: false },
  { name: "Google US English", lang: "en-US", localService: false },
];
assert.strictEqual(pickVoice(voices, "fr-FR", "").name, "Google français", "défaut = voix réseau (qualité)");
assert.strictEqual(pickVoice(voices, "fr-FR", "eSpeak French").name, "eSpeak French", "choix explicite respecté");
assert.strictEqual(pickVoice(voices, "fr-FR", "disparue").name, "Google français", "voix choisie absente → repli réseau");
assert.strictEqual(pickVoice(voices, "en-US", "").name, "Google US English", "langue anglaise");
assert.strictEqual(pickVoice([{ name: "L", lang: "fr-FR", localService: true }], "fr-FR", "").name, "L", "seule locale → prise quand même (nom)");
assert.strictEqual(pickVoice(voices, "de-DE", ""), null, "aucune voix de la langue → null");
console.log("✓ pickVoice (RM2350) : réseau prioritaire, choix explicite, replis");

// — 9. resolveTheme (RM2386) : priorité surcharge locale > conf serveur > auto —
const frt = />>> resolveTheme[\s\S]*?(function resolveTheme[\s\S]*?)\n\/\/ <<< resolveTheme/.exec(html);
assert(frt, "marqueurs >>> resolveTheme / <<< resolveTheme introuvables");
const resolveTheme = vm.runInNewContext("(" + frt[1] + ")");

// pas de surcharge locale → la conf serveur décide
assert.strictEqual(resolveTheme("", "dark", true), "dark", "conf serveur dark");
assert.strictEqual(resolveTheme("", "light", true), "light", "conf serveur light (ignore le système)");
// mode auto → préférence système
assert.strictEqual(resolveTheme("", "auto", true), "dark", "auto + système sombre");
assert.strictEqual(resolveTheme("", "auto", false), "light", "auto + système clair");
// surcharge locale prioritaire sur la conf serveur
assert.strictEqual(resolveTheme("light", "dark", true), "light", "surcharge locale > conf serveur");
assert.strictEqual(resolveTheme("auto", "dark", false), "light", "surcharge locale auto > conf serveur");
// "server" = pas de surcharge (valeur du <select>, jamais stockée mais tolérée)
assert.strictEqual(resolveTheme("server", "dark", false), "dark", "'server' = suivre la conf serveur");
// défauts / robustesse : rien de connu → auto ; valeur inconnue → auto
assert.strictEqual(resolveTheme("", "", true), "dark", "rien de connu → auto (système sombre)");
assert.strictEqual(resolveTheme("", "", false), "light", "rien de connu → auto (système clair)");
assert.strictEqual(resolveTheme("", "solarized", true), "dark", "conf inconnue → auto");
console.log("✓ resolveTheme (RM2386) : local > serveur > auto, valeurs inconnues tolérées");

// — 10. palette : les deux thèmes définissent EXACTEMENT les mêmes tokens —
// (un token oublié dans :root[data-theme="light"] hériterait de la valeur dark
//  et passerait inaperçu à l'œil sur une zone peu visitée)
const css = /<style>([\s\S]*?)<\/style>/.exec(html)[1];
const tokensOf = (sel) => {
  const blk = new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{([^}]*)\\}").exec(css);
  assert(blk, "bloc CSS introuvable : " + sel);
  return new Set([...blk[1].matchAll(/(--[a-z0-9-]+)\s*:/g)].map(m => m[1]));
};
const dark = tokensOf(':root, :root[data-theme="dark"]');
const light = tokensOf(':root[data-theme="light"]');
assert(dark.size >= 15, "palette dark trop maigre (" + dark.size + " tokens)");
assert.deepStrictEqual([...dark].sort(), [...light].sort(), "tokens dark/light désynchronisés");
console.log(`✓ palette : ${dark.size} tokens définis à l'identique en dark et en light`);

// — 11. theme-boot (RM2386) : le bloc du <head> pose data-theme dès son exécution —
// (c'est CE point qui garantit l'absence de flash : l'attribut doit être posé
//  par le simple fait d'évaluer le script, sans attendre le moindre événement)
const boot = /<script id="theme-boot">([\s\S]*?)<\/script>/.exec(html);
assert(boot, "bloc <script id=\"theme-boot\"> introuvable");

function runBoot(store, systemLight) {
  const listeners = [];
  const root = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; } };
  const ctx = {
    document: { documentElement: root },
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = v; },
      removeItem: (k) => { delete store[k]; },
    },
    window: {
      matchMedia: (q) => ({
        matches: q.includes("light") ? systemLight : !systemLight,
        addEventListener: (_ev, fn) => listeners.push(fn),
      }),
    },
  };
  ctx.window.localStorage = ctx.localStorage;
  vm.runInNewContext(boot[1], ctx);
  return { theme: () => root.getAttribute("data-theme"), fire: (light) => { systemLight = light; listeners.forEach(f => f()); }, listeners };
}

// rien en cache + système clair → clair, posé immédiatement (pas de flash)
assert.strictEqual(runBoot({}, true).theme(), "light", "boot : auto + système clair");
assert.strictEqual(runBoot({}, false).theme(), "dark", "boot : auto + système sombre");
// défaut d'instance en cache
assert.strictEqual(runBoot({ karlThemeServer: "dark" }, true).theme(), "dark", "boot : conf serveur dark");
// surcharge « ce navigateur » prioritaire
assert.strictEqual(runBoot({ karlThemeServer: "dark", karlThemeLocal: "light" }, false).theme(), "light",
  "boot : surcharge locale > conf serveur");
// mode auto : réaction à chaud au changement de thème système
const hot = runBoot({ karlThemeServer: "auto" }, false);
assert.strictEqual(hot.listeners.length, 1, "boot : écouteur prefers-color-scheme posé");
assert.strictEqual(hot.theme(), "dark", "boot : état initial sombre");
hot.fire(true);
assert.strictEqual(hot.theme(), "light", "boot : bascule à chaud vers clair");
// ...mais un thème explicite ignore le système
const fixed = runBoot({ karlThemeServer: "dark" }, false);
fixed.fire(true);
assert.strictEqual(fixed.theme(), "dark", "boot : thème explicite insensible au système");
console.log("✓ theme-boot (RM2386) : data-theme posé sans flash, auto réactif à chaud");

// — 12. contrastes WCAG AA (RM2386) : le thème clair doit rester lisible —
const hexOf = (sel) => {
  const blk = new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{([^}]*)\\}").exec(css)[1];
  return Object.fromEntries([...blk.matchAll(/(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})/g)].map(m => [m[1], m[2]]));
};
const lum = (h) => {
  h = h.replace("#", "");
  if (h.length === 3) h = [...h].map(c => c + c).join("");
  const ch = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const [r, g, b] = [0, 2, 4].map(i => ch(parseInt(h.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};
const PAIRS = [["--fg", "--bg"], ["--fg", "--panel"], ["--fg", "--panel2"],
  ["--muted", "--bg"], ["--muted", "--panel"], ["--muted", "--panel2"],
  ["--accent", "--bg"], ["--accent", "--panel"], ["--accent", "--panel2"],
  ["--ok", "--panel"], ["--warn", "--panel"], ["--danger", "--panel"],
  ["--fg-strong", "--bg"], ["--on-accent", "--accent"]];
// Le thème clair est neuf : il doit être AA (4.5:1) partout, sans exception.
const lightHex = hexOf(':root[data-theme="light"]');
for (const [fg, bg] of PAIRS) {
  const r = contrast(lightHex[fg], lightHex[bg]);
  assert(r >= 4.5, `light : ${fg} sur ${bg} = ${r.toFixed(2)}:1 < 4.5 (WCAG AA)`);
}
// Le thème sombre est historique : --muted y est à ~3.9-4.4:1 (sous AA) depuis
// toujours. On NE régresse pas au-delà de cet existant, sans le corriger ici
// (changer la teinte du thème par défaut n'est pas le périmètre de RM2386).
const darkHex = hexOf(':root, :root[data-theme="dark"]');
for (const [fg, bg] of PAIRS) {
  const r = contrast(darkHex[fg], darkHex[bg]);
  const floor = fg === "--muted" ? 3.9 : 4.5;
  assert(r >= floor, `dark : ${fg} sur ${bg} = ${r.toFixed(2)}:1 < ${floor} (régression)`);
}
console.log(`✓ contrastes : thème clair AA sur ${PAIRS.length} paires, thème sombre sans régression`);

// — effDisposition (RM2515) : disposition effective, ne vaut que sur idle, cède au live —
const fmDisp = />>> effDisposition[\s\S]*?(function effDisposition[\s\S]*?)\n\/\/ <<< effDisposition/.exec(html);
assert(fmDisp, "marqueurs >>> effDisposition / <<< effDisposition introuvables");
const effDisposition = vm.runInNewContext("(" + fmDisp[1] + ")");
assert.strictEqual(effDisposition("idle", "parke"), "parke", "idle+parké → parké");
assert.strictEqual(effDisposition("idle", "termine"), "termine", "idle+terminé → terminé");
assert.strictEqual(effDisposition("idle", null), "a_traiter", "idle sans marque → à traiter (défaut)");
assert.strictEqual(effDisposition("idle", ""), "a_traiter", "idle vide → à traiter");
assert.strictEqual(effDisposition("working", "termine"), null, "working → null (cède au live)");
assert.strictEqual(effDisposition("attention", "parke"), null, "attention → null (cède au live)");
assert.strictEqual(effDisposition("choice", "parke"), null, "choice → null (cède au live)");
console.log("✓ effDisposition (RM2515) : ne vaut que sur idle, cède aux évènements live");
// — 5. protocole ttyd du client terminal maison (RM2522) —
// karl-term.js est un fichier séparé (première dépendance front du cockpit) :
// on vérifie sa syntaxe, puis ses fonctions pures de framing, extraites par les
// mêmes marqueurs >>> / <<<.
const termSrc = fs.readFileSync(path.join(__dirname, "karl-term.js"), "utf8");
new vm.Script(termSrc, { filename: "karl-term.js" });

const pick = (name) => {
  const m = new RegExp(`>>> ${name}[\\s\\S]*?(function ${name}[\\s\\S]*?)\\n  // <<< ${name}`).exec(termSrc);
  assert(m, `marqueurs >>> ${name} / <<< ${name} introuvables dans karl-term.js`);
  return vm.runInNewContext("(" + m[1] + ")");
};
const ttydHandshake    = pick("ttydHandshake");
const ttydEncodeResize = pick("ttydEncodeResize");
const ttydEncodeInput  = pick("ttydEncodeInput");
const ttydDecode       = pick("ttydDecode");

// handshake : ttyd attend exactement ces trois clés
assert.deepStrictEqual(JSON.parse(ttydHandshake("tok", 80, 24)),
  { AuthToken: "tok", columns: 80, rows: 24 }, "handshake ttyd");
assert.strictEqual(JSON.parse(ttydHandshake(null, 80, 24)).AuthToken, "",
  "handshake sans token → chaîne vide (pas null)");

// resize : commande '1' suivie du JSON des dimensions
assert.strictEqual(ttydEncodeResize(120, 40), '1{"columns":120,"rows":40}', "framing resize");

// input : commande '0' (0x30) suivie du texte en UTF-8
const enc = (s) => new Uint8Array(Buffer.from(s, "utf8"));
const frame = ttydEncodeInput("é", enc);
assert.strictEqual(frame[0], 0x30, "input : premier octet = '0'");
assert.deepStrictEqual(Array.from(frame.slice(1)), [0xc3, 0xa9], "input : « é » en UTF-8 (2 octets)");
assert.strictEqual(ttydEncodeInput("", enc).length, 1, "input vide = commande seule");

// décodage : premier octet = commande, reste = charge utile
const dec = ttydDecode(new Uint8Array([0x30, 0x41, 0x42]));
assert.strictEqual(dec.cmd, "0", "decode : commande OUTPUT");
assert.deepStrictEqual(Array.from(dec.payload), [0x41, 0x42], "decode : charge utile");
assert.strictEqual(ttydDecode(new Uint8Array([])), null, "decode : message vide → null");
assert.strictEqual(ttydDecode(new Uint8Array([0x31])).payload.length, 0,
  "decode : commande sans charge utile");
console.log("✓ protocole ttyd (handshake, input, resize, decode)");

// — 6. palette ANSI du terminal (RM2522) —
// Retour de test : le fond était repris de --term-bg (#000, un invariant qui ne
// décrivait que le CADRE de l'ancienne iframe) et la palette ANSI était celle,
// implicite, de xterm — les gris du TUI devenaient illisibles. On vérifie
// désormais que CHAQUE couleur tient sur le fond de son thème.
const termPalette = pick("termPalette");
const termBg = { dark: hexOf(':root, :root[data-theme="dark"]')["--term-bg"],
                 light: hexOf(':root[data-theme="light"]')["--term-bg"] };
const termFg = { dark: hexOf(':root, :root[data-theme="dark"]')["--term-fg"],
                 light: hexOf(':root[data-theme="light"]')["--term-fg"] };
for (const mode of ["dark", "light"]) {
  assert(termBg[mode] && termFg[mode], `tokens --term-bg/--term-fg définis en ${mode}`);
  // le texte courant doit être confortable (AA)
  const rFg = contrast(termFg[mode], termBg[mode]);
  assert(rFg >= 4.5, `${mode} : --term-fg sur --term-bg = ${rFg.toFixed(2)}:1 < 4.5`);
  // les 16 couleurs ANSI sont décoratives : plancher 3:1 (AA « gros texte » /
  // éléments non textuels), sauf `black`/`brightBlack` qui servent de FOND à du
  // texte dans certains TUI — on exige seulement qu'ils se distinguent du fond.
  const pal = termPalette(mode === "light");
  for (const [name, hex] of Object.entries(pal)) {
    const r = contrast(hex, termBg[mode]);
    const floor = name === "black" ? 1.15 : 3;
    assert(r >= floor, `${mode} : ANSI ${name} (${hex}) sur fond = ${r.toFixed(2)}:1 < ${floor}`);
  }
}
console.log("✓ palette ANSI du terminal : contrastes tenus en dark et en light");

// — 7. hook de saisie : ne prendre la main QUE sur le chemin que xterm perd —
// Deux régressions vécues en prod (RM2522), de sens opposé :
//   a) le hook prenait la main sur tout `input` insertText, donc aussi sur les
//      caractères qu'xterm venait d'envoyer depuis le keydown → espaces et
//      « [ » en double ;
//   b) ses écouteurs, posés sur un conteneur qui survit aux remontages,
//      n'étaient jamais retirés : le hook d'une session précédente coupait la
//      propagation et réémettait sur un terminal disposé → plus AUCUN accent.
// Le second paramètre n'est donc pas l'identité de la touche mais un fait :
// xterm a-t-il émis depuis le keydown en cours ?
const shouldTakeOverInput = pick("shouldTakeOverInput");
const evt = (o) => Object.assign({ data: "a", inputType: "insertText", isComposing: false }, o);

// mesuré dans Firefox : « é » → keydown "Process", xterm n'émet rien, puis input
assert.strictEqual(shouldTakeOverInput(evt({ data: "é" }), false), true, "accent abandonné par xterm → on prend la main");
// mesuré dans Firefox : espace et « [ » → xterm émet dès le keydown, puis input
assert.strictEqual(shouldTakeOverInput(evt({ data: " " }), true), false, "espace déjà émis par xterm → ne pas doubler");
assert.strictEqual(shouldTakeOverInput(evt({ data: "[" }), true), false, "crochet déjà émis par xterm → ne pas doubler");
// composition IME réelle : chemin dédié de xterm, on ne s'en mêle pas
assert.strictEqual(shouldTakeOverInput(evt({ data: "あ", isComposing: true }), false), false, "IME → laisser xterm");
// autres types d'input (suppression, collage) : hors périmètre du hook
assert.strictEqual(shouldTakeOverInput(evt({ inputType: "deleteContentBackward" }), false), false, "suppression ignorée");
assert.strictEqual(shouldTakeOverInput(evt({ inputType: "insertFromPaste" }), false), false, "collage ignoré");
assert.strictEqual(shouldTakeOverInput(evt({ data: "" }), false), false, "data vide ignorée");

// installAccentFix lui-même, contre un conteneur et un terminal simulés : c'est
// là que se jouent le cycle de vie des écouteurs et la non-réentrance.
const mIAF = />>> installAccentFix[\s\S]*?(function installAccentFix[\s\S]*?)\n  \/\/ <<< installAccentFix/.exec(termSrc);
assert(mIAF, "marqueurs >>> installAccentFix / <<< installAccentFix introuvables");
const installAccentFix = vm.runInNewContext("(" + mIAF[1] + ")", { shouldTakeOverInput });

function fakeContainer() {
  const ls = { keydown: [], input: [] };
  return {
    addEventListener: (t, f) => ls[t].push(f),
    removeEventListener: (t, f) => { const i = ls[t].indexOf(f); if (i >= 0) ls[t].splice(i, 1); },
    count: (t) => ls[t].length,
    fire(t, ev) {                       // respecte stopImmediatePropagation
      let stop = false;
      const e = Object.assign({ stopImmediatePropagation: () => { stop = true; } }, ev);
      for (const f of ls[t].slice()) { f(e); if (stop) break; }
    },
  };
}
function fakeTerm(sent) {
  let cb = null;
  return {
    onData(f) { cb = f; return { dispose() { cb = null; } }; },
    input(d) { sent.push(d); if (cb) cb(d); },        // réémission par le hook
    keyEmit(d) { sent.push(d); if (cb) cb(d); },      // ce qu'xterm fait au keydown
  };
}
const ta = { classList: { contains: (c) => c === "xterm-helper-textarea" }, value: "" };
const key = (data) => ({ target: ta, data, inputType: "insertText", isComposing: false });

// espace : xterm émet au keydown, l'`input` qui suit ne doit rien ajouter
let sent = [], term = fakeTerm(sent), box = fakeContainer();
let uninstall = installAccentFix(box, term);
box.fire("keydown", {}); term.keyEmit(" "); box.fire("input", key(" "));
assert.deepStrictEqual(sent, [" "], "espace envoyé une seule fois");

// accent : xterm n'émet rien, le hook doit suppléer
box.fire("keydown", {}); box.fire("input", key("é"));
assert.deepStrictEqual(sent, [" ", "é"], "accent repris par le hook");

// deux accents de suite : la réémission du hook ne doit pas passer pour une
// émission d'xterm, sinon le second serait avalé
box.fire("keydown", {}); box.fire("input", key("é"));
assert.deepStrictEqual(sent, [" ", "é", "é"], "deux accents consécutifs passent tous les deux");

// désinstallation : plus un seul écouteur ne subsiste sur le conteneur
uninstall();
assert.strictEqual(box.count("keydown") + box.count("input"), 0, "écouteurs retirés au dispose");
box.fire("keydown", {}); box.fire("input", key("è"));
assert.deepStrictEqual(sent, [" ", "é", "é"], "hook désinstallé : plus aucune émission");

// le défaut de prod : un hook de session précédente laissé en place mange le
// caractère (il coupe la propagation et réémet dans le vide)
sent = []; box = fakeContainer();
const zombieSent = [], zombie = fakeTerm(zombieSent);
const uninstallZombie = installAccentFix(box, zombie);       // session 1
uninstallZombie();                                           // … proprement démontée
term = fakeTerm(sent); installAccentFix(box, term);          // session 2
box.fire("keydown", {}); box.fire("input", key("é"));
assert.deepStrictEqual(sent, ["é"], "la session vivante reçoit l'accent");
assert.deepStrictEqual(zombieSent, [], "la session démontée ne capte plus rien");
console.log("✓ hook de saisie : accents repris, pas de doublon, écouteurs libérés au démontage");
// — sortFrozen (RM2346) : gel du réordonnancement dynamique pendant l'interaction —
const fmFrz = />>> sortFrozen[\s\S]*?(function sortFrozen[\s\S]*?)\n\/\/ <<< sortFrozen/.exec(html);
assert(fmFrz, "marqueurs >>> sortFrozen / <<< sortFrozen introuvables");
const sortFrozen = vm.runInNewContext("(" + fmFrz[1] + ")");
assert.strictEqual(sortFrozen(false, true, 0), false, "ordre stable → jamais gelé");
assert.strictEqual(sortFrozen(true, true, 99999), true, "dynamique + survol → gelé");
assert.strictEqual(sortFrozen(true, false, 500), true, "dynamique + mouvement récent (<2s) → gelé");
assert.strictEqual(sortFrozen(true, false, 3000), false, "dynamique + inactif (>2s) → dégelé");
console.log("✓ sortFrozen (RM2346) : gèle le tri dynamique pendant l'interaction, stable jamais gelé");

// — ttsMode (RM2532) : bascule TTS serveur (Piper) ↔ navigateur —
const fmTts = />>> ttsMode[\s\S]*?(function ttsMode[\s\S]*?)\n\/\/ <<< ttsMode/.exec(html);
assert(fmTts, "marqueurs >>> ttsMode / <<< ttsMode introuvables");
const ttsMode = vm.runInNewContext("(" + fmTts[1] + ")");
assert.strictEqual(ttsMode({ tts: true }, true), "server", "serveur dispo + préféré → server");
assert.strictEqual(ttsMode({ tts: true }, false), "browser", "serveur dispo mais non préféré → browser");
assert.strictEqual(ttsMode({ tts: false }, true), "browser", "serveur sans tts → browser");
assert.strictEqual(ttsMode(null, true), "browser", "pas de caps (serveur muet) → browser");
console.log("✓ ttsMode (RM2532) : serveur si dispo ET préféré, sinon repli navigateur");

// — sttMode (RM2533) : bascule STT serveur (Whisper) ↔ navigateur —
const fmStt = />>> sttMode[\s\S]*?(function sttMode[\s\S]*?)\n\/\/ <<< sttMode/.exec(html);
assert(fmStt, "marqueurs >>> sttMode / <<< sttMode introuvables");
const sttMode = vm.runInNewContext("(" + fmStt[1] + ")");
assert.strictEqual(sttMode({ stt: true }, true), "server", "sidecar dispo + préféré → server");
assert.strictEqual(sttMode({ stt: true }, false), "browser", "sidecar dispo mais non préféré → browser");
assert.strictEqual(sttMode({ stt: false }, true), "browser", "serveur sans stt → browser");
assert.strictEqual(sttMode(null, true), "browser", "pas de caps (sidecar muet) → browser");
console.log("✓ sttMode (RM2533) : serveur si sidecar dispo ET préféré, sinon repli navigateur");

// — 8. composer (RM2527) : collage encadré, garde d'état, historique —
// Le collage encadré est le cœur du lot : un texte multi-ligne envoyé frappe par
// frappe fait soumettre le TUI à CHAQUE saut de ligne (un prompt de cinq lignes
// part en cinq messages tronqués). Encadré par ESC[200~ … ESC[201~, il arrive en
// une fois, et le retour de validation est émis SÉPARÉMENT.
const bracketedPaste = pick("bracketedPaste");
// composerFrames appelle bracketedPaste : le contexte d'évaluation doit la lui fournir
const mCf = />>> composerFrames[\s\S]*?(function composerFrames[\s\S]*?)\n  \/\/ <<< composerFrames/.exec(termSrc);
assert(mCf, "marqueurs >>> composerFrames / <<< composerFrames introuvables");
const composerFrames = vm.runInNewContext("(" + mCf[1] + ")", { bracketedPaste });

assert.strictEqual(bracketedPaste("bonjour"), "\x1b[200~bonjour\x1b[201~", "encadrement simple");
assert.strictEqual(bracketedPaste("a\nb"), "\x1b[200~a\nb\x1b[201~", "multi-ligne encadré d'un bloc");
// un \r à l'intérieur du collage vaut validation pour certains TUI → normalisé
assert.strictEqual(bracketedPaste("a\r\nb"), "\x1b[200~a\nb\x1b[201~", "CRLF normalisé en LF");
assert.strictEqual(bracketedPaste("a\rb"), "\x1b[200~a\nb\x1b[201~", "CR seul normalisé en LF");
assert.strictEqual(bracketedPaste(null), "\x1b[200~\x1b[201~", "null toléré");

const fr = composerFrames("ligne 1\nligne 2");
assert.strictEqual(fr.length, 2, "un collage + un retour de validation");
assert.strictEqual(fr[0], "\x1b[200~ligne 1\nligne 2\x1b[201~", "le texte part encadré");
assert.strictEqual(fr[1], "\r", "la validation est HORS du collage");
assert(!fr[0].includes("\r"), "aucun retour chariot à l'intérieur du collage");
assert.deepStrictEqual(Array.from(composerFrames("x", false)), ["\x1b[200~x\x1b[201~"], "submit=false : pas de validation");
assert.deepStrictEqual(Array.from(composerFrames("")), [], "texte vide : rien n'est émis (pas même un Entrée)");
assert.deepStrictEqual(Array.from(composerFrames(null)), [], "null : rien n'est émis");
console.log("✓ composer (RM2527) : collage encadré en un bloc, validation émise à part");

// — garde d'état : taper du texte dans un menu SÉLECTIONNE des options —
const fmCg = />>> composerGuard[\s\S]*?(function composerGuard[\s\S]*?)\n\/\/ <<< composerGuard/.exec(html);
assert(fmCg, "marqueurs >>> composerGuard / <<< composerGuard introuvables");
const composerGuard = vm.runInNewContext("(" + fmCg[1] + ")");
assert.strictEqual(composerGuard("idle").allow, true, "idle → envoi permis");
assert.strictEqual(composerGuard("working").allow, true, "working → envoi permis");
assert.strictEqual(composerGuard(undefined).allow, true, "état inconnu → on ne bloque pas");
assert.strictEqual(composerGuard("choice").allow, false, "menu ouvert → envoi retenu");
assert.strictEqual(composerGuard("attention").allow, false, "question en attente → envoi retenu");
assert(/menu/i.test(composerGuard("choice").warn), "le refus explique le menu");
assert(/question/i.test(composerGuard("attention").warn), "le refus explique la question");
assert.strictEqual(composerGuard("idle").warn, null, "aucun avertissement quand c'est permis");
console.log("✓ composer (RM2527) : garde d'état sur les menus (attention / choice)");

// — historique des envois —
const fmCh = />>> composerHistoryAdd[\s\S]*?(function composerHistoryAdd[\s\S]*?)\n\/\/ <<< composerHistoryAdd/.exec(html);
assert(fmCh, "marqueurs >>> composerHistoryAdd / <<< composerHistoryAdd introuvables");
const composerHistoryAdd = vm.runInNewContext("(" + fmCh[1] + ")");
assert.deepStrictEqual(Array.from(composerHistoryAdd([], "a")), ["a"], "premier message");
assert.deepStrictEqual(Array.from(composerHistoryAdd(["a"], "b")), ["b", "a"], "le plus récent en tête");
assert.deepStrictEqual(Array.from(composerHistoryAdd(["b", "a"], "a")), ["a", "b"], "un renvoi remonte, sans doublon");
assert.deepStrictEqual(Array.from(composerHistoryAdd(["a"], "  a  ")), ["a"], "espaces de bord ignorés");
assert.deepStrictEqual(Array.from(composerHistoryAdd(["a"], "   ")), ["a"], "message vide non retenu");
assert.deepStrictEqual(Array.from(composerHistoryAdd(null, "a")), ["a"], "liste absente tolérée");
assert.strictEqual(composerHistoryAdd(["a", "b", "c"], "d", 3).length, 3, "plafond respecté");
assert.deepStrictEqual(Array.from(composerHistoryAdd(["a", "b", "c"], "d", 3)), ["d", "a", "b"], "le plus ancien tombe");
console.log("✓ composer (RM2527) : historique sans doublon, récent en tête, plafonné");

// — 9. outline enrichi (RM2549) : décor des entrées + saut aux non résolues —
const foD = />>> outlineDecor[\s\S]*?(function outlineDecor[\s\S]*?)\n\/\/ <<< outlineDecor/.exec(html);
assert(foD, "marqueurs >>> outlineDecor / <<< outlineDecor introuvables");
const outlineDecor = vm.runInNewContext("(" + foD[1] + ")");

const dUnres = outlineDecor({ kind: "question", resolved: false });
const dRes = outlineDecor({ kind: "question", resolved: true, answer: "Option A" });
const dAns = outlineDecor({ kind: "answer" });
// le critère du ticket : couleur ET icône ET libellé — jamais l'un des trois seul
assert(dUnres.cls.includes("ounres"), "non résolue : classe de couleur dédiée");
assert.strictEqual(dUnres.icon, "⚠", "non résolue : icône distincte");
assert(/sans réponse/i.test(dUnres.tag), "non résolue : libellé en toutes lettres");
assert(dRes.cls !== dUnres.cls && dRes.icon !== dUnres.icon && dRes.tag !== dUnres.tag,
  "résolue et non résolue diffèrent sur les TROIS canaux, pas seulement la couleur");
assert(/Option A/.test(dRes.title), "une question répondue expose la réponse retenue");
assert(dAns.cls.includes("oans") && dAns.icon && /réponse/i.test(dAns.tag),
  "la réponse a son propre décor");
assert.strictEqual(outlineDecor({ kind: "user" }).cls, "ouser", "message utilisateur inchangé");
assert.strictEqual(outlineDecor({ kind: "assistant" }).icon, "⏺", "message assistant inchangé");
assert.strictEqual(outlineDecor(null).icon, "⏺", "entrée absente tolérée");
assert.strictEqual(outlineDecor({ kind: "question" }).cls, dUnres.cls,
  "resolved manquant = non résolu (on ne suppose pas une réponse)");
console.log("✓ outline (RM2549) : couleur ET icône ET libellé sur chaque état");

const foU = />>> outlineNextUnresolved[\s\S]*?(function outlineNextUnresolved[\s\S]*?)\n\/\/ <<< outlineNextUnresolved/.exec(html);
assert(foU, "marqueurs >>> outlineNextUnresolved / <<< outlineNextUnresolved introuvables");
const outlineNextUnresolved = vm.runInNewContext("(" + foU[1] + ")");
const qi = [
  { line: 0, kind: "user" },
  { line: 1, kind: "question", resolved: true },
  { line: 2, kind: "question", resolved: false },
  { line: 3, kind: "assistant" },
  { line: 4, kind: "question", resolved: false },
];
assert.strictEqual(outlineNextUnresolved(qi, null).line, 2, "depuis le direct : la première sans réponse");
assert.strictEqual(outlineNextUnresolved(qi, 2).line, 4, "puis la suivante");
assert.strictEqual(outlineNextUnresolved(qi, 4).line, 2, "après la dernière, on reboucle");
assert.strictEqual(outlineNextUnresolved(qi.filter(i => i.resolved !== false), null), null,
  "tout est répondu → rien à signaler");
assert.strictEqual(outlineNextUnresolved([], null), null, "outline vide toléré");
assert.strictEqual(outlineNextUnresolved(null, null), null, "outline absent toléré");
console.log("✓ outline (RM2549) : saut à la prochaine question sans réponse");

// la navigation en source transcript ne doit RIEN envoyer à tmux : la vue des
// autres clients attachés ne bouge pas (RM2549). Depuis RM2596, l'appel /scroll
// est GARDÉ par « source !== transcript » (l'accordéon gère la lecture inline).
const mJump = /async function jumpTo\(it\) \{[\s\S]*?\n\}/.exec(html);
assert(mJump, "jumpTo introuvable");
const gi = mJump[0].indexOf('outline.source !== "transcript"');
const si = mJump[0].indexOf("/scroll");
assert(gi >= 0 && si > gi,
  "l'appel /scroll est gardé par « source !== transcript » — transcript ne pilote pas tmux");
console.log("✓ outline (RM2549/2596) : /scroll gardé, transcript ne pilote pas tmux");

// — origine du WebSocket du terminal (RM2561) —
// Le cert auto-signé ne vaut que pour le host:port visité et un wss:// vers un
// autre port meurt SANS interstitiel : derrière le vhost, le terminal doit rester
// en même origine. Régression déjà vécue (terminal noir, cockpit intact).
const fTB = />>> termBase[\s\S]*?(function termBase[\s\S]*?)\n\/\/ <<< termBase/.exec(html);
assert(fTB, "marqueurs >>> termBase / <<< termBase introuvables");
const mkTermBase = (cfg, loc) => vm.runInNewContext("(" + fTB[1] + ")", { CFG: cfg, location: loc });

const https443 = { port: "", protocol: "https:", hostname: "karl.lxc", origin: "https://karl.lxc" };
assert.strictEqual(mkTermBase({ ttyd_base: "" }, https443)(), "https://karl.lxc/ttyd",
  "derrière le vhost : même origine (une seule exception de cert)");
assert.strictEqual(mkTermBase({ ttyd_base: "" }, { ...https443, port: "443" })(), "https://karl.lxc/ttyd",
  "port 443 explicite : même origine aussi");
assert.strictEqual(
  mkTermBase({ ttyd_base: "" },
    { port: "9876", protocol: "http:", hostname: "dev.local", origin: "http://dev.local:9876" })(),
  "http://dev.local:7681", "accès direct au port du cockpit (sans Apache) : repli sur :7681");
assert.strictEqual(mkTermBase({ ttyd_base: "https://ailleurs:1234" }, https443)(), "https://ailleurs:1234",
  "KARL_AGENT_TTYD_URL reste prioritaire");
console.log("✓ termBase (RM2561) : WebSocket en même origine derrière le vhost, repli :7681 sinon");

// — 10. colonnes repliables + onglets de droite (RM2466 volet 3) —
const fRp = />>> rightPanelReduce[\s\S]*?(function rightPanelReduce[\s\S]*?)\n\/\/ <<< rightPanelReduce/.exec(html);
assert(fRp, "marqueurs >>> rightPanelReduce / <<< rightPanelReduce introuvables");
const _rpr = vm.runInNewContext("(" + fRp[1] + ")");
// l'objet rendu vient d'un autre realm : on le recopie ici pour comparer
const rightPanelReduce = (s, a) => ({ ..._rpr(s, a) });

const replie = { tab: "outline", collapsed: true };
const ouvert = { tab: "outline", collapsed: false };
assert.deepStrictEqual(rightPanelReduce(replie, { type: "select", tab: "tickets" }),
  { tab: "tickets", collapsed: false }, "replié : sélectionner un onglet déplie dessus");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "select", tab: "tickets" }),
  { tab: "tickets", collapsed: false }, "ouvert : changer d'onglet ne replie pas");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "select", tab: "outline" }),
  { tab: "outline", collapsed: true }, "ouvert : re-sélectionner l'onglet actif replie");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "show" }),
  ouvert, "show sans onglet : déplie sans arracher l'onglet courant");
assert.deepStrictEqual(rightPanelReduce({ tab: "outline", collapsed: true }, { type: "show" }),
  ouvert, "show sans onglet depuis replié : déplie sur l'onglet mémorisé");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "show", tab: "tickets" }),
  { tab: "tickets", collapsed: false }, "show ciblé : l'onglet demandé passe devant");
assert.deepStrictEqual(rightPanelReduce({ tab: "tickets", collapsed: false }, { type: "collapse" }),
  { tab: "tickets", collapsed: true }, "collapse garde l'onglet en mémoire");
assert.deepStrictEqual(rightPanelReduce(replie, { type: "toggle" }), ouvert, "toggle déplie");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "toggle" }), replie, "toggle replie");
// RM2579 : trois onglets, défaut « infos », migration de l'ancien « meta »
assert.deepStrictEqual(rightPanelReduce(null, {}), { tab: "infos", collapsed: true },
  "état absent → replié sur infos (défaut RM2579)");
assert.deepStrictEqual(rightPanelReduce({ tab: "meta", collapsed: false }, {}),
  { tab: "infos", collapsed: false }, "legacy « meta » (ancien localStorage) → infos");
assert.deepStrictEqual(rightPanelReduce({ tab: "meta", collapsed: true }, { type: "show" }),
  { tab: "infos", collapsed: false }, "legacy « meta » migré aussi via show");
assert.deepStrictEqual(rightPanelReduce({ tab: "zzz" }, {}), { tab: "infos", collapsed: true },
  "onglet inconnu → infos");
// « state » (🗒 état, RM2466 volet 2 mergé en parallèle) est un onglet VALIDE :
// il ne doit PAS être normalisé vers infos (régression corrigée).
assert.deepStrictEqual(rightPanelReduce({ tab: "state", collapsed: false }, {}),
  { tab: "state", collapsed: false }, "onglet state préservé (pas de normalisation)");
assert.deepStrictEqual(rightPanelReduce({ tab: "files", collapsed: false }, {}),
  { tab: "files", collapsed: false }, "onglet files (RM2586) est un onglet valide");
assert.deepStrictEqual(rightPanelReduce(replie, { type: "select", tab: "state" }),
  { tab: "state", collapsed: false }, "select state : déplie sur état");
console.log("✓ colonnes (RM2466/2579) : 4 onglets (dont état), défaut infos, legacy meta→infos");

// structure : les deux asides empilés ont bien fusionné en une colonne à onglets
assert(!/class="metapanel|class="outpanel|id="metapanel"|id="outpanel"/.test(html),
  "les anciens panneaux empilés (metapanel/outpanel) ne doivent plus exister");
const asides = html.match(/<aside\b/g) || [];
assert.strictEqual(asides.length, 1, "une seule colonne de droite, pas un empilement");
const onglets = (html.match(/data-rpanel="/g) || []).length;
const corps = (html.match(/class="rp" id="rp-/g) || []).length;
assert.strictEqual(onglets, corps, "chaque onglet de droite a son panneau, et réciproquement");
assert(/id="ltoggle"/.test(html) && /id="rtoggle"/.test(html),
  "chaque colonne a son bouton de repli");
assert(/main\.lcollapsed \{ grid-template-columns: 34px 1fr; \}/.test(html),
  "la colonne gauche se replie vers la gauche (largeur réduite, pas masquée)");
assert(/\.rpanel\.collapsed \{ width: 34px; \}/.test(html),
  "la colonne droite se replie vers la droite");
console.log("✓ colonnes (RM2466) : structure fusionnée, chaque colonne repliable vers son bord");

// — 11. bouton d'envoi du composer (RM2527) : lisible, et pas pleine largeur —
// Il porte `.primary` pour l'accent, mais `button.primary` est le GROS bouton de
// formulaire du lanceur. Sans surcharge il s'étale sur toute la largeur, et
// redéfinir `color` SANS `background` donne du texte accent sur fond accent.
const blocOf = (sel) => {
  const m = new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{([^}]*)\\}").exec(css);
  assert(m, `règle CSS ${sel} introuvable`);
  return m[1];
};
const base = blocOf("button.primary");
assert(/width:\s*100%/.test(base) && /background:\s*var\(--accent\)/.test(base),
  "prérequis du test : button.primary reste le gros bouton pleine largeur à fond accent");
const mp = blocOf(".mini.primary");
assert(/width:\s*auto/.test(mp) && /margin-top:\s*0/.test(mp),
  "le bouton d'envoi doit annuler la géométrie du gros bouton (sinon : pleine largeur)");
// ancré sur un début de déclaration : sinon `border-color:` passe pour `color:`
const mpFg = /(?:^|;)\s*color:\s*var\((--[a-z0-9-]+)\)/.exec(mp);
const mpBg = /(?:^|;)\s*background:\s*var\((--[a-z0-9-]+)\)/.exec(mp);
assert(mpFg && mpBg, "le bouton d'envoi doit poser SON fond avec sa couleur de texte");
for (const [nom, hex] of [["light", lightHex], ["dark", darkHex]]) {
  const r = contrast(hex[mpFg[1]], hex[mpBg[1]]);
  assert(r >= 4.5, `${nom} : libellé du bouton d'envoi ${mpFg[1]} sur ${mpBg[1]} = ${r.toFixed(2)}:1 < 4.5 (illisible)`);
}
console.log("✓ composer (RM2527) : bouton d'envoi compact et lisible sur son fond");
// — configArgs (RM2531) : args /pm/run pour l'édition de conf projet/client —
const fCA = />>> configArgs[\s\S]*?(function configArgs[\s\S]*?)\n\/\/ <<< configArgs/.exec(html);
assert(fCA, "marqueurs >>> configArgs / <<< configArgs introuvables");
const configArgs = vm.runInNewContext("(" + fCA[1] + ")", {});

// (spread { ...res } : normalise le realm du vm.runInNewContext pour deepStrictEqual)
// projet : client+project + champs non vides ; les vides sont omis
assert.deepStrictEqual(
  { ...configArgs("project", "iprospective/pm-ai-agents",
    { name: "Nouveau", redmine: "pm-ai-agents", repo: "", branch: "  " }) },
  { client: "iprospective", project: "pm-ai-agents", name: "Nouveau", redmine_project_id: "pm-ai-agents" },
  "projet : champs vides/espaces omis, non vides trim");
// projet : repo + branche pris en compte
assert.deepStrictEqual(
  { ...configArgs("project", "c/p", { name: "", redmine: "", repo: "g/r", branch: "dev" }) },
  { client: "c", project: "p", gitlab_repo: "g/r", default_branch: "dev" },
  "projet : gitlab_repo + default_branch");
// client : pas de project, pas de gitlab même si fournis
assert.deepStrictEqual(
  { ...configArgs("client", "acme/shop", { name: "Acme", redmine: "acme-parent", repo: "x/y", branch: "main" }) },
  { client: "acme", name: "Acme", redmine_project_id: "acme-parent" },
  "client : ni project ni gitlab, seulement name + redmine");
// aucun champ conf → null (rien à faire)
assert.strictEqual(configArgs("project", "c/p", { name: "", redmine: "", repo: "", branch: "" }), null,
  "aucun champ → null");
assert.strictEqual(configArgs("client", "c/p", {}), null, "client sans champ → null");
console.log("✓ configArgs (RM2531) : args /pm/run, champs vides omis, gitlab réservé au projet");

// — 12. panneau « en attente de toi » (RM2466 volet 2) —
const fPd = />>> pendingDecor[\s\S]*?(function pendingDecor[\s\S]*?)\n\/\/ <<< pendingDecor/.exec(html);
assert(fPd, "marqueurs >>> pendingDecor / <<< pendingDecor introuvables");
const pendingDecor = vm.runInNewContext("(" + fPd[1] + ")");

const dLive = pendingDecor({ kind: "live", state: "attention" });
const dChoice = pendingDecor({ kind: "live", state: "choice" });
const dStale = pendingDecor({ kind: "stale" });
assert(dLive.cls.includes("ounres") && !dStale.cls.includes("ounres"),
  "une session BLOQUÉE est signalée plus fort qu'une question qui traîne");
assert(dLive.icon !== dStale.icon && dLive.tag !== dStale.tag,
  "les deux natures diffèrent par l'icône ET le libellé, pas seulement la couleur");
assert(dChoice.icon !== dLive.icon, "menu de choix et question oui/non ont leur icône");
assert(/bloqu/i.test(dLive.tag) && /sans réponse/i.test(dStale.tag),
  "les libellés disent en toutes lettres de quoi il s'agit");
assert(pendingDecor(null).tag && pendingDecor(undefined).icon, "entrée absente tolérée");
console.log("✓ état (RM2466) : bloquée vs sans réponse, distinguées sur trois canaux");

// RM2581 : le panneau droit est recentré sur la SESSION — la section « en attente,
// toutes sessions » a été retirée ; l'onglet devient le worklog (renommé).
assert(/rp-state/.test(html) && /data-rpanel="state"/.test(html),
  "l'onglet worklog a son bouton et son panneau (id « state » conservé)");
assert(/🗒 worklog/.test(html), "l'onglet « état » est renommé « worklog » (RM2581)");
assert(!/id="pendbody"/.test(html) && !/id="rn-pending"/.test(html),
  "la section « en attente (toutes sessions) » et son badge ont été retirés du panneau droit");
const onglets2 = (html.match(/data-rpanel="/g) || []).length;
const corps2 = (html.match(/class="rp" id="rp-/g) || []).length;
assert.strictEqual(onglets2, corps2, "chaque onglet de droite a toujours son panneau");
console.log("✓ worklog (RM2581) : panneau droit recentré sur la session, onglet renommé");

// — 13. worklog de session dans le panneau état (RM2466 volet 2, étape 2) —
const fWs = />>> worklogSections[\s\S]*?(function worklogSections[\s\S]*?)\n\/\/ <<< worklogSections/.exec(html);
assert(fWs, "marqueurs >>> worklogSections / <<< worklogSections introuvables");
const worklogSections = vm.runInNewContext("(" + fWs[1] + ")");

const secs = worklogSections({ todo: [{ ref: "RM1" }], waiting: [{ ref: "RM2" }], done: [{ ref: "RM3" }] });
assert.deepStrictEqual(Array.from(secs.map(s => s.key)), ["todo", "waiting", "done"],
  "ce qui reste d'abord, ce qui est fait en dernier");
assert(secs.every(s => s.icon && s.label), "chaque section porte une icône ET un libellé");
assert.strictEqual(worklogSections({ todo: [], waiting: [{ ref: "RM2" }], done: [] }).length, 1,
  "les sections vides disparaissent (pas de titre sans contenu)");
assert.strictEqual(worklogSections({}).length, 0, "worklog vide → aucune section");
assert.strictEqual(worklogSections(null).length, 0, "worklog absent toléré");
assert.strictEqual(worklogSections(undefined).length, 0, "buckets absents tolérés");
console.log("✓ état (RM2466) : worklog en sections, vides masquées");

// la dérive doit rester visible : sans elle on croirait que le statut affiché
// est le fait de la session courante, alors qu'une autre l'a fait avancer
const mRw = /function renderWorklog\(\) \{[\s\S]*?\n\}/.exec(html);
assert(mRw, "renderWorklog introuvable");
assert(/it\.drifted/.test(mRw[0]) && /opened_status/.test(mRw[0]),
  "un statut modifié hors de la session doit être signalé comme tel");
assert(/id="workbody"/.test(html) && !/id="pendbody"/.test(html),
  "le panneau droit ne contient plus que le worklog (RM2581)");
// RM2581 : signal de fraîcheur de la résolution live
assert(/id="workfresh"/.test(html) && /checked_ts/.test(mRw[0]),
  "le worklog affiche quand son statut a été résolu en direct (workfresh/checked_ts)");
console.log("✓ worklog (RM2581) : dérive signalée, statut live, fraîcheur affichée");

// tout onglet présent dans la barre DOIT être accepté par la normalisation.
// Incident vécu : une whitelist ajoutée par un ticket ignorait l'onglet ajouté
// par un ticket concurrent — le merge combinait nav et panneaux, mais l'onglet
// était normalisé vers un autre et devenait inactivable EN PROD. Chaque branche
// passait ses propres tests ; seule l'union était cassée.
const navTabs = [...html.matchAll(/data-rpanel="([a-z]+)"/g)].map(m => m[1]);
const mTabs = /const TABS = \[([^\]]*)\]/.exec(html);
assert(mTabs, "whitelist TABS de la colonne de droite introuvable");
const whitelist = (mTabs[1].match(/"([a-z]+)"/g) || []).map(s => s.replace(/"/g, ""));
assert(navTabs.length, "aucun onglet trouvé dans la barre de droite");
for (const tab of navTabs) {
  assert(whitelist.includes(tab),
    `onglet « ${tab} » présent dans la barre mais absent de TABS → inactivable en prod`);
}
console.log(`✓ colonne droite : les ${navTabs.length} onglets de la barre sont tous activables`);

// — notifications de session dans le panneau (RM2466 volet 1 × volet 2) —
const fNd = />>> notifyDecor[\s\S]*?(function notifyDecor[\s\S]*?)\n\/\/ <<< notifyDecor/.exec(html);
assert(fNd, "marqueurs >>> notifyDecor / <<< notifyDecor introuvables");
const notifyDecor = vm.runInNewContext("(" + fNd[1] + ")");
const nc = notifyDecor("critical"), nw = notifyDecor("warn"), ni = notifyDecor("info");
assert(nc.icon !== nw.icon && nw.icon !== ni.icon, "chaque gravité a son icône");
assert(nc.label === "critical" && nw.label === "warn" && ni.label === "info",
  "le niveau reste écrit en toutes lettres, pas seulement en couleur");
assert(nc.cls.includes("ounres") && !ni.cls.includes("ounres"),
  "seul le critique est mis en avant visuellement");
assert.strictEqual(notifyDecor(undefined).label, "warn", "niveau absent → warn, jamais silencieux");
const mRw2 = /function renderWorklog\(\) \{[\s\S]*?\n\}/.exec(html);
assert(/notifications/.test(mRw2[0]), "le panneau affiche les notifications de session");
// robuste au libellé de la section (renommée par RM2581) : ce qui compte est
// que les notifications PRÉFIXENT le rendu, dans les deux sorties de la fonction
const prefixes = mRw2[0].match(/(?:body\.innerHTML|let h) = notes \+/g) || [];
assert.strictEqual(prefixes.length, 2,
  "les incidents doivent préfixer le worklog, dans les deux branches du rendu");
console.log("✓ état (RM2466) : notifications de session rendues avant le travail");

// — filesCrumbs (RM2586) : fil d'ariane de l'explorateur de fichiers —
const fFc = />>> filesCrumbs[\s\S]*?(function filesCrumbs[\s\S]*?)\n\/\/ <<< filesCrumbs/.exec(html);
assert(fFc, "marqueurs >>> filesCrumbs / <<< filesCrumbs introuvables");
const filesCrumbs = vm.runInNewContext("(" + fFc[1] + ")");
assert.strictEqual(JSON.stringify(filesCrumbs("")), JSON.stringify([{ name: "/", path: "" }]),
  "racine : un seul élément « / »");
assert.strictEqual(JSON.stringify(filesCrumbs("src/app")),
  JSON.stringify([{ name: "/", path: "" }, { name: "src", path: "src" }, { name: "app", path: "src/app" }]),
  "fil d'ariane cumulatif (chemins cumulés)");
assert.strictEqual(JSON.stringify(filesCrumbs("a//b/").map(c => c.path)), JSON.stringify(["", "a", "a/b"]),
  "slashes superflus tolérés");
console.log("✓ fichiers (RM2586) : fil d'ariane cumulatif");
// l'onglet fichiers a bien son bouton ET son panneau (équilibre onglets/panneaux déjà vérifié)
assert(/data-rpanel="files"/.test(html) && /id="rp-files"/.test(html), "onglet fichiers câblé (RM2586)");

// — titleLink (RM2585) : titre de ticket cliquable + lien externe Redmine —
const fTl = />>> titleLink[\s\S]*?(function titleLink[\s\S]*?)\n\/\/ <<< titleLink/.exec(html);
assert(fTl, "marqueurs >>> titleLink / <<< titleLink introuvables");
const escFn = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const mkTl = cfg => vm.runInNewContext("(" + fTl[1] + ")", { esc: escFn, CFG: cfg });
const tl = mkTl({ redmine_url: "https://r.x" });
let tlo = tl("2585", "Mon <b>ticket</b>");
assert(/showTicket\(2585\)/.test(tlo) && /event\.stopPropagation/.test(tlo),
  "titre numérique : clic → showTicket, sans déclencher la tuile");
assert(/href="https:\/\/r\.x\/issues\/2585"/.test(tlo) && /class="rmext"/.test(tlo),
  "lien externe ↗ construit depuis CFG.redmine_url");
assert(tlo.includes("Mon &lt;b&gt;ticket&lt;/b&gt;") && !/<b>/.test(tlo), "titre échappé (anti-XSS)");
assert.strictEqual(mkTl({})("chantier-x", "Truc"), "Truc", "ref non ticket (slug) → texte simple");
assert.strictEqual(tl(null, "x"), "x", "ref absente → texte simple");
tlo = mkTl({})("42", "T");
assert(/showTicket\(42\)/.test(tlo) && !/rmext/.test(tlo), "sans base Redmine : cliquable, mais pas de ↗");
console.log("✓ titleLink (RM2585) : titre → fiche + lien Redmine, échappé, dégrade proprement");

// — worklogDocs (RM2584) : aplatissement des documents/outputs des tickets —
const fWd = />>> worklogDocs[\s\S]*?(function worklogDocs[\s\S]*?)\n\/\/ <<< worklogDocs/.exec(html);
assert(fWd, "marqueurs >>> worklogDocs / <<< worklogDocs introuvables");
const worklogDocs = vm.runInNewContext("(" + fWd[1] + ")");
const wd = worklogDocs({ RM1: [["a.py", "output"], ["b.md", "output"]], RM2: [["c", ""]] });
assert.strictEqual(wd.length, 3, "aplatit tous les documents de tous les tickets");
assert.strictEqual(JSON.stringify(wd[0]), JSON.stringify({ ref: "RM1", name: "a.py", kind: "output" }),
  "chaque entrée porte ref + name + kind");
assert.strictEqual(worklogDocs({ RM3: ["str-seul"] })[0].name, "str-seul", "entrée chaîne tolérée (name seul)");
assert.strictEqual([...worklogDocs({})].length, 0, "map vide → liste vide");
assert.strictEqual([...worklogDocs(null)].length, 0, "map absente tolérée");
console.log("✓ worklogDocs (RM2584) : documents aplatis par ticket");

// — RM2596 : recherche / surlignage / linkify de la conversation —
const escO = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const mJarg = /function jarg\(s\) \{[\s\S]*?\n\}/.exec(html);
assert(mJarg, "jarg introuvable");
const jargFn = vm.runInNewContext("(" + mJarg[0] + ")", {});
function grabO(name, ctx) {
  const m = new RegExp(">>> " + name + "[\\s\\S]*?(function " + name + "[\\s\\S]*?)\\n// <<< " + name).exec(html);
  assert(m, "marqueurs " + name + " introuvables");
  return vm.runInNewContext("(" + m[1] + ")", ctx || {});
}
const outMatch = grabO("outMatch");
const hlq = grabO("hlq", { esc: escO });
// RM2623 : glossaire — extraction + build partagé (linkify dépend de glossify)
const mGloss = /const GLOSSARY = (\[[\s\S]*?\n\]);/.exec(html);
assert(mGloss, "GLOSSARY introuvable");
const GLOSSARY = vm.runInNewContext("(" + mGloss[1] + ")");
const glossNorm = grabO("glossNorm");
const buildGloss = grabO("buildGloss", { glossNorm });
const glossMatch = grabO("glossMatch");
const GLOSS = buildGloss(GLOSSARY);
const glossify = grabO("glossify", { esc: escO, glossNorm, GLOSS });
const linkify = grabO("linkify", { esc: escO, jarg: jargFn, glossify });

// jarg : argument onclick sûr (guillemets simples, jamais de " qui casse l'attribut)
assert.strictEqual(jargFn("a/b.py"), "'a/b.py'", "chemin simple entre quotes simples");
assert(!/"/.test(jargFn('x"y')), "un \" dans la valeur ne ferme pas l'attribut");
assert.strictEqual(jargFn("l'a"), "'l\\'a'", "apostrophe échappée");

// outMatch : filtre insensible à la casse sur text OU full ; vide → tout
const oitems = [{ line: 1, text: "corrige RM123", full: "le bug RM123" }, { line: 2, text: "autre", full: "rien" }];
assert.strictEqual(outMatch(oitems, "rm123").length, 1, "insensible à la casse");
assert.strictEqual(outMatch(oitems, "bug")[0].line, 1, "cherche aussi dans full");
assert.strictEqual(outMatch(oitems, "").length, 2, "requête vide → tout");
assert.strictEqual(outMatch(oitems, "zzz").length, 0, "aucun match → []");

// hlq : échappe + surligne, sûr
assert.strictEqual(hlq("a <b> RM1", ""), "a &lt;b&gt; RM1", "sans requête : simple échappement");
assert(/<mark>RM1<\/mark>/.test(hlq("voir RM1", "rm1")), "surligne (insensible casse)");
assert(!/<b>/.test(hlq("<b>x</b>", "x")), "HTML source échappé");

// linkify : RM → showTicket, chemin → openFileRef ('...'), URL → <a>, reste échappé
const lk = linkify("fix RM42 dans scripts/karl-agent.py cf https://x.io/p et <b>");
assert(/onclick="showTicket\(42\)"/.test(lk) && />RM42</.test(lk), "RM42 cliquable → showTicket");
assert(/onclick="openFileRef\('scripts\/karl-agent.py'\)"/.test(lk), "chemin cliquable → openFileRef (quotes simples)");
assert(/<a href="https:\/\/x.io\/p"/.test(lk), "URL cliquable");
assert(!/<b>/.test(lk) && /&lt;b&gt;/.test(lk), "reste du texte échappé (anti-XSS)");
console.log("✓ conversation (RM2596) : recherche, surlignage, refs cliquables, onclick sûr");

// — RM2623 : glossaire cliquable du jargon —
assert.strictEqual(glossNorm("  Worktree, "), "worktree", "glossNorm: minuscule + ponctuation de bord retirée");
assert.strictEqual(glossNorm("serve-check"), "serve-check", "glossNorm garde le trait d'union interne");
assert(GLOSS.map["worktrees"] && GLOSS.map["worktrees"].t === "worktree", "alias/pluriel → terme canonique dans map");
assert.strictEqual(GLOSS.surfaces.indexOf("scope"), -1, "terme inline:false absent des surfaces (pas de soulignage auto)");
assert(GLOSS.surfaces[0].length >= GLOSS.surfaces[GLOSS.surfaces.length - 1].length, "surfaces triées du plus long au plus court");
// glossMatch : recherche terme / alias / définition, tri alpha, requête vide → tout
assert(glossMatch("worktree", GLOSSARY).some(e => e.t === "worktree"), "glossMatch trouve par terme");
assert(glossMatch("bac à sable", GLOSSARY).some(e => e.t === "sandbox"), "glossMatch trouve par définition");
assert.strictEqual(glossMatch("zzznope", GLOSSARY).length, 0, "glossMatch : aucun match → []");
assert.strictEqual(glossMatch("", GLOSSARY).length, GLOSSARY.length, "glossMatch : requête vide → tout");
// glossify : enveloppe le terme (frontière de mot), data-term canonique, def en title, sûr
const gy = glossify(escO("un worktree ici"));
assert(/<span class="gloss" data-term="worktree"/.test(gy), "glossify enveloppe le terme connu");
assert(/title="Copie de travail Git/.test(gy), "glossify met la définition en title");
assert.strictEqual(glossify(escO("reworktreeX")), "reworktreeX", "pas de match en milieu de mot (frontières)");
assert(!/gloss/.test(glossify(escO("un scope large"))), "terme inline:false non souligné dans le texte");
assert(/data-term="worktree"/.test(glossify(escO("des worktrees"))), "pluriel reconnu → data-term canonique");
assert(!/<b>/.test(glossify(escO("<b>worktree</b>"))) && /&lt;b&gt;/.test(glossify(escO("<b>worktree</b>"))), "opère sur du texte déjà échappé (anti-XSS)");
console.log("✓ glossaire (RM2623) : normalisation, index, recherche, soulignage inline sûr");

// — RM2634 : glossaire enrichi — regroupement par catégories —
const glossGroups = grabO("glossGroups");
const gg = glossGroups(GLOSSARY);
assert(gg.length >= 5, "plusieurs catégories rendues");
assert(gg.every(g => g.items.length > 0), "aucun groupe vide");
assert(gg.reduce((n, g) => n + g.items.length, 0) === GLOSSARY.length, "toutes les entrées reparties, aucune perdue");
const cats = gg.map(g => g.cat);
assert(cats.indexOf("git") >= 0 && cats.indexOf("git") < cats.indexOf("gen"), "ordre fixe : git avant Général");
const gitg = gg.find(g => g.cat === "git");
const names = gitg.items.map(i => i.t);
assert(JSON.stringify(names) === JSON.stringify(names.slice().sort((a, b) => a.localeCompare(b))), "groupe trié alpha");
const filtered = glossGroups(glossMatch("git", GLOSSARY));
assert(filtered.length >= 1 && filtered.every(g => g.items.length > 0), "sur recherche : groupes filtrés, jamais vides");
assert.strictEqual(glossGroups([{ t: "x", d: "y" }])[0].cat, "gen", "entrée sans catégorie → Général");
assert.strictEqual(glossGroups([{ t: "z", d: "w", c: "zzz" }])[0].cat, "zzz", "catégorie inconnue conservée (rejetée en fin), jamais perdue");
console.log("✓ glossaire enrichi (RM2634) : catégories ordonnées, tri alpha, filtrage, rien de perdu");

// — RM2639 : contexte client (pré-filtre global du cockpit) —
const clientCtxList = grabO("clientCtxList");
const clientCtxProject = grabO("clientCtxProject");
const sessionInClient = grabO("sessionInClient");
const PJ = [
  { client: "iprospective", project: "pm-ai-agents", value: "iprospective/pm-ai-agents" },
  { client: "acme", project: "site", value: "acme/site" },
  { client: "iprospective", project: "infra", value: "iprospective/infra" },
];
assert.deepStrictEqual([...clientCtxList(PJ)], ["acme", "iprospective"], "clients uniques, triés alpha");
assert.deepStrictEqual([...clientCtxList([])], [], "aucun projet → []");
assert.strictEqual(clientCtxProject(PJ, "iprospective"), "iprospective/pm-ai-agents", "1er projet du client");
assert.strictEqual(clientCtxProject(PJ, "inconnu"), "", "client introuvable → ''");
assert.strictEqual(clientCtxProject(PJ, ""), "", "client vide → ''");
assert.strictEqual(sessionInClient({ client: "acme", state: "working" }, null, ""), true, "ctx vide → visible");
assert.strictEqual(sessionInClient({ client: "acme", state: "working" }, null, "acme"), true, "même client → visible");
assert.strictEqual(sessionInClient({ client: "bob", state: "working" }, null, "acme"), false, "autre client, non en attente → masqué");
assert.strictEqual(sessionInClient({ client: "bob", state: "attention" }, null, "acme"), true, "autre client mais en attente → jamais masqué (RM2445)");
assert.strictEqual(sessionInClient({ client: "bob", state: "choice" }, null, "acme"), true, "autre client mais choix → jamais masqué");
assert.strictEqual(sessionInClient({ state: "working" }, { found: true, client: "acme" }, "acme"), true, "client résolu via resolveCache");
console.log("✓ contexte client (RM2639) : liste, projet par défaut, filtre (attente jamais masquée)");

// — pendStaleSet (RM2598) : sessions avec question sans réponse (badge gauche) —
const fPs = />>> pendStaleSet[\s\S]*?(function pendStaleSet[\s\S]*?)\n\/\/ <<< pendStaleSet/.exec(html);
assert(fPs, "marqueurs pendStaleSet introuvables");
const pendStaleSet = vm.runInNewContext("(" + fPs[1] + ")", { Set });
const ps = pendStaleSet([{ rm_id: "1", kind: "live" }, { rm_id: "2", kind: "stale" }, { rm_id: "3", kind: "stale" }]);
assert(!ps.has("1") && ps.has("2") && ps.has("3"), "ne garde que les stale (live déjà signalés ⚠/❓)");
assert.strictEqual(pendStaleSet([]).size, 0, "vide → Set vide");
assert.strictEqual(pendStaleSet(null).size, 0, "null toléré");
console.log("\u2713 pendStaleSet (RM2598) : questions sans réponse, live exclues");

// — clampWidth (RM2599) : largeur du panneau de droite bornée —
const fCw = />>> clampWidth[\s\S]*?(function clampWidth[\s\S]*?)\n\/\/ <<< clampWidth/.exec(html);
assert(fCw, "marqueurs clampWidth introuvables");
const clampWidth = vm.runInNewContext("(" + fCw[1] + ")", { R_WIDTH_DEFAULT: 330, Math, Number, isFinite });
assert.strictEqual(clampWidth(500), 500, "valeur dans les bornes conservee");
assert.strictEqual(clampWidth(100), 240, "sous le min -> 240");
assert.strictEqual(clampWidth(2000), 900, "au-dessus du max -> 900");
assert.strictEqual(clampWidth("abc"), 330, "non numerique -> defaut");
console.log("\u2713 clampWidth (RM2599) : largeur bornee [240,900], defaut si invalide");

// — outByKind (RM2601) : filtre de vue de la conversation —
const fBk = />>> outByKind[\s\S]*?(function outByKind[\s\S]*?)\n\/\/ <<< outByKind/.exec(html);
assert(fBk, "marqueurs outByKind introuvables");
const outByKind = vm.runInNewContext("(" + fBk[1] + ")");
const its2 = [{ kind: "user" }, { kind: "question" }, { kind: "answer" }, {}];
assert.strictEqual(outByKind(its2, "all").length, 4, "all -> tout");
assert.strictEqual(outByKind(its2, "user").length, 1, "moi -> user seulement");
assert.strictEqual(outByKind(its2, "question").length, 1, "questions seulement");
assert.strictEqual(outByKind([], "user").length, 0, "vide tolere");
console.log("\u2713 outByKind (RM2601) : filtres tout / moi / questions");

// — vue git (RM2602) : lecture des commits et des diffs —
const fGd = />>> gitDiffLine[\s\S]*?(function gitDiffLine[\s\S]*?)\n\/\/ <<< gitDiffLine/.exec(html);
assert(fGd, "marqueurs >>> gitDiffLine introuvables");
const gitDiffLine = vm.runInNewContext("(" + fGd[1] + ")");
assert.strictEqual(gitDiffLine("+ajout"), "add", "ligne ajoutée");
assert.strictEqual(gitDiffLine("-retrait"), "del", "ligne retirée");
assert.strictEqual(gitDiffLine("@@ -1,4 +1,9 @@"), "hunk", "en-tête de section");
assert.strictEqual(gitDiffLine(" contexte"), "", "ligne de contexte non colorée");
// le piège : +++/--- sont des en-têtes de FICHIER, pas du contenu modifié
assert.strictEqual(gitDiffLine("+++ b/x.py"), "fh", "+++ est un en-tête, pas un ajout");
assert.strictEqual(gitDiffLine("--- a/x.py"), "fh", "--- est un en-tête, pas un retrait");
assert.strictEqual(gitDiffLine("diff --git a/x b/x"), "fh", "ligne diff --git");
assert.strictEqual(gitDiffLine(null), "", "ligne absente tolérée");
console.log("✓ git (RM2602) : coloration du patch, en-têtes non confondus avec du contenu");

const fGs = />>> gitStatLabel[\s\S]*?(function gitStatLabel[\s\S]*?)\n\/\/ <<< gitStatLabel/.exec(html);
assert(fGs, "marqueurs >>> gitStatLabel introuvables");
const gitStatLabel = vm.runInNewContext("(" + fGs[1] + ")");
assert(/2 fichiers/.test(gitStatLabel({ count: 2, added: 5, removed: 3, files: [] })), "pluriel");
assert(/1 fichier ·/.test(gitStatLabel({ count: 1, added: 1, removed: 0, files: [] })), "singulier");
assert(/1 binaire/.test(gitStatLabel({ count: 1, added: 0, removed: 0, files: [{ binary: true }] })),
  "un binaire est signalé — sinon « +0 −0 » ferait croire qu'il n'a pas changé");
assert(gitStatLabel(null).length, "stats absentes tolérées");
console.log("✓ git (RM2602) : résumé de diff, binaires signalés");

// aucune ACTION git ne doit être exposée : ce lot est en lecture seule
const mGit = /\/git\/[a-z]+\//g;
const routes = [...new Set((html.match(mGit) || []))];
assert(routes.every(r => ["/git/log/", "/git/show/", "/git/diff/"].includes(r)),
  "le front n'appelle que des routes git de LECTURE : " + routes.join(" "));
assert(!/\/git\/(checkout|reset|stash|revert|commit|push)/.test(html),
  "aucune action git ne doit être appelable depuis le cockpit");
console.log("✓ git (RM2602) : lecture seule, aucune action exposée");

// — RM2605 : chaque information dans le bon onglet, tickets cliquables —
const fWr = />>> worklogRefHtml[\s\S]*?(function worklogRefHtml[\s\S]*?)\n\/\/ <<< worklogRefHtml/.exec(html);
assert(fWr, "marqueurs >>> worklogRefHtml introuvables");
const worklogRefHtml = vm.runInNewContext("(" + fWr[1] + ")");
const escId = s => String(s);
const lien = worklogRefHtml("RM2467", escId, () => "");
assert(/showTicket\(2467\)/.test(lien), "un ticket ouvre sa fiche");
assert(/pill/.test(lien) && /cursor:pointer/.test(lien), "et SE VOIT comme cliquable");
assert(/event\.stopPropagation/.test(lien),
  "le clic sur le lien ne doit pas aussi déclencher celui de la ligne");
const libre = worklogRefHtml("pisceen-facettes", escId, () => "");
assert(!/showTicket/.test(libre) && /<b>/.test(libre),
  "un chantier hors ticket n'est pas un lien : il n'a pas de fiche");
assert(worklogRefHtml(null, escId, () => "").length >= 0, "réf absente tolérée");
console.log("✓ worklog (RM2605) : tickets cliquables, chantiers libres non");

const fGb = />>> gitBranchesHtml[\s\S]*?(function gitBranchesHtml[\s\S]*?)\n\/\/ <<< gitBranchesHtml/.exec(html);
assert(fGb, "marqueurs >>> gitBranchesHtml introuvables");
const gitBranchesHtml = vm.runInNewContext("(" + fGb[1] + ")");
const brs = gitBranchesHtml(["2605-x", "dev"], "2605-x", escId);
assert(/2605-x/.test(brs) && /dev/.test(brs), "les branches de la session sont listées");
assert(/pill ok[^>]*>2605-x/.test(brs) || /class="pill ok"/.test(brs),
  "la branche COURANTE est distinguée — sinon on ne sait pas laquelle on regarde");
assert.strictEqual(gitBranchesHtml([], null, escId), "", "aucune branche → rien, pas un cadre vide");
assert.strictEqual(gitBranchesHtml(null, null, escId), "", "branches absentes tolérées");
console.log("✓ git (RM2605) : branches dans l'onglet git, la courante distinguée");

// ce qui quitte « infos » ne doit pas disparaître : les conflits restent
const mReg = /function registryHtml\([\s\S]*?\n\}/.exec(html);
assert(mReg, "registryHtml introuvable");
assert(!/reg\.branches/.test(mReg[0]), "les branches ont quitté « infos »");
assert(!/reg\.worktrees/.test(mReg[0]), "les worktrees ont quitté « infos » (l'onglet fichiers les sert)");
assert(/registry_conflicts|conf\.forEach/.test(mReg[0]),
  "les conflits de session RESTENT visibles — ils ne partent nulle part ailleurs");
console.log("✓ infos (RM2605) : allégé, sans rien perdre");

// — RM2606 : tickets ouverts dans l'onglet de gauche —
const grab = (name) => {
  const m = new RegExp(">>> " + name + "[\\s\\S]*?(function " + name + "[\\s\\S]*?)\\n// <<< " + name).exec(html);
  assert(m, "marqueurs >>> " + name + " introuvables");
  return m[1];
};
const openedAdd = vm.runInNewContext("(" + grab("openedAdd") + ")");
assert.deepStrictEqual(Array.from(openedAdd([], "2606")), ["2606"], "premier ticket");
assert.deepStrictEqual(Array.from(openedAdd(["2605"], "2606")), ["2606", "2605"], "le dernier ouvert en tête");
assert.deepStrictEqual(Array.from(openedAdd(["2605", "2606"], "2605")), ["2605", "2606"],
  "rouvrir remonte sans dupliquer");
assert.deepStrictEqual(Array.from(openedAdd([], "abc")), [], "une réf non numérique n'entre pas");
assert.deepStrictEqual(Array.from(openedAdd(null, "1")), ["1"], "liste absente tolérée");
assert.strictEqual(openedAdd(["1", "2", "3"], "4", 3).length, 3, "plafond respecté");
assert.deepStrictEqual(Array.from(openedAdd(["1", "2", "3"], "4", 3)), ["4", "1", "2"],
  "le plus ancien tombe");
console.log("✓ tickets ouverts (RM2606) : sans doublon, récent en tête, plafonné");

const ticketStatusRank = vm.runInNewContext("(" + grab("ticketStatusRank") + ")");
assert(ticketStatusRank("a_corriger") < ticketStatusRank("en_cours"),
  "ce qui revient corrigé passe avant ce qui est en cours");
assert(ticketStatusRank("en_cours") < ticketStatusRank("a_faire"), "en cours avant à faire");
assert(ticketStatusRank("a_faire") < ticketStatusRank("ferme"), "fermé en dernier");
assert(ticketStatusRank("statut_exotique") < ticketStatusRank("ferme"),
  "un statut inconnu se voit, il n'est pas rangé avec les fermés");
console.log("✓ tickets ouverts (RM2606) : ordre de lecture, pas alphabétique");

// groupOpenedTickets appelle ticketStatusRank : le contexte isolé doit l'avoir
const groupOpenedTickets = vm.runInNewContext("(" + grab("groupOpenedTickets") + ")",
  { ticketStatusRank });
const tkCache = {
  "1": { found: true, client: "acme", project: "shop", title: "A", status: "ferme" },
  "2": { found: true, client: "acme", project: "shop", title: "B", status: "en_cours" },
  "3": { found: true, client: "beta", project: "api", title: "C", status: "a_faire" },
};
const g = groupOpenedTickets(["1", "2", "3", "9"], tkCache, null);
assert.deepStrictEqual(Array.from(g.keys), ["acme/shop", "beta/api", "…"],
  "groupé par client/projet, le non résolu en dernier");
assert.deepStrictEqual(Array.from(g.groups.get("acme/shop").map(x => x.rm_id)), ["2", "1"],
  "dans un groupe, l'urgence de statut ordonne");
assert.deepStrictEqual(Array.from(g.clients), ["acme", "beta"], "clients proposés au filtre");
assert(g.groups.get("…")[0].resolved === false,
  "un ticket pas encore résolu reste visible plutôt que de disparaître");
const f = groupOpenedTickets(["1", "2", "3"], tkCache, "beta");
assert.deepStrictEqual(Array.from(f.keys), ["beta/api"], "le filtre client réduit la liste");
assert.deepStrictEqual(Array.from(groupOpenedTickets([], {}, null).keys), [], "liste vide tolérée");
assert.deepStrictEqual(Array.from(groupOpenedTickets(null, null, null).keys), [], "entrées absentes tolérées");
console.log("✓ tickets ouverts (RM2606) : groupés par projet, filtrés par client");

// le badge de l'onglet et l'alimentation depuis les deux portes d'entrée
assert(/id="ln-tickets"/.test(html), "l'onglet tickets porte un compteur");
const mShow = /function showTicket\(id\) \{[\s\S]*?\n\}/.exec(html);
assert(mShow && /noteOpenedTicket/.test(mShow[0]), "ouvrir une fiche alimente la liste");
const mRev = /function openReview\(rm\) \{[\s\S]*?\n\}/.exec(html);
assert(mRev && /noteOpenedTicket/.test(mRev[0]), "ouvrir une revue aussi");
assert(/karlOpenedTickets/.test(html), "la liste survit au rechargement (localStorage)");
console.log("✓ tickets ouverts (RM2606) : compteur, deux portes d'entrée, persistance");

// — worklogTabList (RM2610) : sous-onglets par statut du worklog —
const fWt = />>> worklogTabList[\s\S]*?(function worklogTabList[\s\S]*?)\n\/\/ <<< worklogTabList/.exec(html);
assert(fWt, "marqueurs worklogTabList introuvables");
const worklogTabList = vm.runInNewContext("(" + fWt[1] + ")");
const secs2 = [{ key: "todo", icon: "\u23f3", label: "reste a faire", items: [1, 2] }, { key: "done", icon: "\u2705", label: "fait", items: [1] }];
let tabs2 = worklogTabList(secs2, 3, 0).map(t => [t.key, t.n]);
assert.strictEqual(JSON.stringify(tabs2), JSON.stringify([["todo", 2], ["done", 1], ["documents", 3]]), "un onglet par bucket non vide + documents");
assert.strictEqual(worklogTabList([], 0, 0).length, 0, "rien -> aucun onglet");
assert.strictEqual(worklogTabList([], 2, 0)[0].key, "documents", "documents seuls");
// branches orphelines sans bucket todo -> cree un onglet a faire en tete
const tabs3 = worklogTabList([{ key: "done", icon: "x", label: "fait", items: [1] }], 0, 2);
assert.strictEqual(tabs3[0].key, "todo", "orphelines -> onglet a faire cree");
console.log("\u2713 worklogTabList (RM2610) : onglets par statut, documents, orphelines");

// — RM2611 : fenêtre de contexte par modèle + % + débit —
const grab611 = (n) => { const mm = new RegExp(">>> "+n+"[\\s\\S]*?(function "+n+"[\\s\\S]*?)\\n\\/\\/ <<< "+n).exec(html); assert(mm, n+" introuvable"); return vm.runInNewContext("("+mm[1]+")", { Number, Math, isFinite }); };
const modelWindow = grab611("modelWindow");
const ctxPct611 = grab611("ctxPct");
const throughput = grab611("throughput");
assert.strictEqual(modelWindow("claude-x", { context_window: 1000000 }, 50000), 1000000, "override pricing.yml prioritaire");
assert.strictEqual(modelWindow("claude-x", null, 868000), 1000000, "contexte >200k -> fenetre 1M deduite");
assert.strictEqual(modelWindow("claude-opus-4-8", null, 5000), 200000, "defaut claude 200k");
assert.strictEqual(modelWindow("gpt-x", null, 5000), null, "non-claude inconnu -> null");
assert.strictEqual(ctxPct611(100000, 200000), 50, "50%");
assert.strictEqual(ctxPct611(868000, 1000000), 87, "arrondi");
assert.strictEqual(ctxPct611(1000, null), null, "sans fenetre -> null");
const tp611 = throughput(600000, 3.0, 0, 3600000);
assert(tp611 && tp611.tpm === 10000 && Math.abs(tp611.uph - 3.0) < 1e-9, "debit moyen (10000 tok/min, $3/h)");
assert.strictEqual(throughput(100, 1, 0, 10000), null, "duree < 30s -> null");
console.log("\u2713 infos (RM2611) : fenetre par modele (1M deduit), % contexte, debit");

// — pollDelay (RM2613) : cadence adaptative + pause en arriere-plan —
const fPd613 = />>> pollDelay[\s\S]*?(function pollDelay[\s\S]*?)\n\/\/ <<< pollDelay/.exec(html);
assert(fPd613, "marqueurs pollDelay introuvables");
const pollDelay = vm.runInNewContext("(" + fPd613[1] + ")");
assert.strictEqual(pollDelay(true), 3000, "attention -> 3s");
assert.strictEqual(pollDelay(false), 7000, "calme -> 7s");
assert(/visibilitychange/.test(html) && /document\.hidden/.test(html), "pollers gates sur la visibilite (RM2613)");
assert(/setInterval\([^)]*document\.hidden/.test(html) || /if \(!document\.hidden\)/.test(html), "au moins un poller saute quand cache");
console.log("\u2713 pollDelay (RM2613) : cadence adaptative, pause en arriere-plan");

// — RM2614 : situer un ticket dans son client / projet —
const fPb = />>> projectBriefHtml[\s\S]*?(function projectBriefHtml[\s\S]*?)\n\/\/ <<< projectBriefHtml/.exec(html);
assert(fPb, "marqueurs >>> projectBriefHtml introuvables");
// RM2714 : `cval` (nettoyeur des valeurs YAML « null ») est désormais une
// fonction GLOBALE — elle doit être fournie au sandbox, sinon on rejouerait le
// bug qu'on vient de corriger : un identifiant hors de portée.
const mCval = />>> cval[\s\S]*?(function cval[\s\S]*?)\n\/\/ <<< cval/.exec(html);
assert(mCval, "marqueurs >>> cval introuvables");
const cval = vm.runInNewContext("(" + mCval[1] + ")");
const projectBriefHtml = vm.runInNewContext("(" + fPb[1] + ")", { cval });
assert.strictEqual(cval("null"), "", "cval : la CHAÎNE « null » vaut vide (piège YAML)");
assert.strictEqual(cval("~"), "", "cval : « ~ » aussi");
assert.strictEqual(cval("None"), "", "cval : « None » aussi");
assert.strictEqual(cval(null), "", "cval : null réel");
assert.strictEqual(cval("  x  "), "x", "cval : trim");
const e = s => String(s);
const j = s => '"' + String(s) + '"';

// tant que la fiche projet n'est pas chargée, on affiche ce qu'on SAIT déjà
const nu = projectBriefHtml("acme", "shop", null, e, j);
assert(/acme/.test(nu) && /shop/.test(nu), "client et projet viennent du ticket, sans attendre le réseau");
assert(/showProject\("acme\/shop"\)/.test(nu), "le lien vers la fiche projet est là d'emblée");
assert(!/tickets/.test(nu), "pas de compteur inventé tant que la fiche n'est pas chargée");

const carte = {
  client_name: "Acme SA", client_redmine_project_id: "acme",
  name: "Boutique", redmine_project_url: "https://r/projects/shop",
  gitlab_repo: "grp/shop", default_branch: "dev",
  open_by_status: { en_cours: 2, a_faire: 3 }, total: 12,
};
const plein = projectBriefHtml("acme", "shop", carte, e, j);
assert(/Acme SA/.test(plein) && /Boutique/.test(plein), "les noms lisibles priment sur les slugs");
assert(/5 ouverts \/ 12/.test(plein), "le compte d'ouverts situe le projet d'un coup d'œil");
assert(/grp\/shop/.test(plein) && /dev/.test(plein), "dépôt et branche par défaut affichés");
assert(/https:\/\/r\/projects\/shop/.test(plein) && /rel="noopener"/.test(plein),
  "lien Redmine du projet, ouvert sans fuite d'opener");

const un = projectBriefHtml("acme", "shop", { open_by_status: { en_cours: 1 } }, e, j);
assert(/1 ouvert</.test(un), "singulier respecté");

// un ticket non résolu ne doit pas produire un cadre vide
assert.strictEqual(projectBriefHtml(null, "shop", carte, e, j), "", "sans client : rien");
assert.strictEqual(projectBriefHtml("acme", null, carte, e, j), "", "sans projet : rien");
assert.strictEqual(projectBriefHtml("", "", null, e, j), "", "les deux vides : rien");
// vu sur un projet RÉEL : un champ YAML vide remonte en chaîne "null"
const nul = projectBriefHtml("calicote", "prestashop",
  { gitlab_repo: "null", default_branch: "main", client_name: "Calicote" }, e, j);
assert(!/null/.test(nul), "un dépôt non déclaré ne s'affiche pas comme « null »");
assert(/Calicote/.test(nul), "le reste de la fiche s'affiche normalement");
console.log("✓ ticket (RM2614) : client/projet situés, liens vers le détail");

// la fiche projet ne doit être demandée qu'une fois par projet
const mEns = /function ensureProjectCard\([\s\S]*?\n\}/.exec(html);
assert(mEns, "ensureProjectCard introuvable");
assert(/projCardCache\[cle\] !== undefined/.test(mEns[0]),
  "un projet déjà demandé n'est pas rechargé à chaque rendu de fiche");
console.log("✓ ticket (RM2614) : une requête par projet, pas une par rendu");

// — RM2619 : cache des tickets + infobulle au survol —
const grabT = (name) => {
  const m = new RegExp(">>> " + name + "[\\s\\S]*?(function " + name + "[\\s\\S]*?)\\n// <<< " + name).exec(html);
  assert(m, "marqueurs >>> " + name + " introuvables");
  return vm.runInNewContext("(" + m[1] + ")");
};
const ticketTipText = grabT("ticketTipText");

const tip = ticketTipText("2619", {
  found: true, title: "Cache des tickets", status: "en_cours", completion_pct: 40,
  type: "feature", priority: "high", client: "iprospective", project: "pm-ai-agents" });
assert(/RM2619 — Cache des tickets/.test(tip), "libellé en tête");
assert(/en_cours/.test(tip) && /40 %/.test(tip), "statut et avancement");
assert(/iprospective\/pm-ai-agents/.test(tip), "projet indiqué");
assert(/priorité high/.test(tip), "une priorité non ordinaire est signalée");
assert(!/priorité normal/.test(ticketTipText("1", { found: true, priority: "normal" })),
  "une priorité normale n'encombre pas l'infobulle");

// une attente ne doit pas se lire comme une absence d'information
assert(/chargement/.test(ticketTipText("42", null)), "cache pas encore rempli : on le dit");
assert(/inconnu/.test(ticketTipText("42", { found: false })), "ticket inconnu : on le dit aussi");
assert(/sans titre/.test(ticketTipText("42", { found: true, title: "" })), "titre vide toléré");
assert(/0 %/.test(ticketTipText("42", { found: true, completion_pct: 0 })),
  "0 % s'affiche — c'est une information, pas une absence");
console.log("✓ infobulle (RM2619) : libellé, statut, %, projet ; attente distinguée de l'inconnu");

const pendingBriefIds = grabT("pendingBriefIds");
assert.deepStrictEqual(Array.from(pendingBriefIds(["1", "2"], {}, new Set())), ["1", "2"],
  "tout ce qui manque est demandé");
assert.deepStrictEqual(Array.from(pendingBriefIds(["1", "2"], { "1": {} }, new Set())), ["2"],
  "ce qui est déjà en cache n'est pas redemandé");
assert.deepStrictEqual(Array.from(pendingBriefIds(["1", "2"], {}, new Set(["1"]))), ["2"],
  "ce qui est déjà en vol non plus");
assert.deepStrictEqual(Array.from(pendingBriefIds(["3", "3", "3"], {}, new Set())), ["3"],
  "un même id affiché dix fois ne fait pas dix demandes");
assert.deepStrictEqual(Array.from(pendingBriefIds(["abc", "", null, "12"], {}, new Set())), ["12"],
  "les réfs non numériques sont écartées");
assert.deepStrictEqual(Array.from(pendingBriefIds(null, null, null)), [], "entrées absentes tolérées");
// un ticket introuvable est mis en cache comme tel : sans ça, on le redemande sans fin
assert.deepStrictEqual(Array.from(pendingBriefIds(["9"], { "9": { found: false } }, new Set())), [],
  "un ticket connu comme introuvable n'est pas redemandé en boucle");
console.log("✓ infobulle (RM2619) : demandes regroupées, jamais en boucle");

assert(/\/tickets\/brief\?ids=/.test(html), "le cockpit interroge l'endpoint de lot");
assert(/data-tip-rm/.test(html), "les éléments porteurs d'un RM-id sont repérables pour la mise à jour");
const mRt = /function refreshTips\(\) \{[\s\S]*?\n\}/.exec(html);
assert(mRt && /setAttribute\("title"/.test(mRt[0]),
  "quand le cache se remplit, les infobulles déjà posées suivent");
console.log("✓ infobulle (RM2619) : endpoint de lot, mise à jour en place");

// — RM2622 : la doc du projet dans l'onglet fichiers —
const mFr = />>> fileRootLabel[\s\S]*?(function fileRootLabel[\s\S]*?)\n\/\/ <<< fileRootLabel/.exec(html);
assert(mFr, "marqueurs >>> fileRootLabel introuvables");
const fileRootLabel = vm.runInNewContext("(" + mFr[1] + ")");
const doc = fileRootLabel({ kind: "doc", name: "docs", docs: 15, label: "documents du projet", path: "/p/docs" });
assert(doc.icon === "📄", "la doc porte une icône propre");
assert(/15 fichiers/.test(doc.tip), "le nombre de documents situe le dossier");
assert(/documents du projet/.test(doc.tip), "le libellé dit ce que c'est");
const code = fileRootLabel({ kind: "code", name: "presta-rm2401", path: "/w/x" });
assert(!code.icon && code.name === "presta-rm2401", "un worktree de code reste présenté comme avant");
assert.strictEqual(fileRootLabel(null).name, "?", "entrée absente tolérée");
console.log("✓ fichiers (RM2622) : doc et code distingués");

// un dossier de doc n'a ni branche ni commits : pas de cadre git trompeur
const mRf = /function renderFiles\(\) \{[\s\S]*?\n\}/.exec(html);
assert(mRf, "renderFiles introuvable");
assert(/cur\.kind === "doc"/.test(mRf[0]), "le rendu traite la doc à part");
assert(mRf[0].indexOf('cur.kind === "doc"') < mRf[0].indexOf("cur.is_git"),
  "la branche doc est testée AVANT le cadre git, qui ne s'applique pas");
console.log("✓ fichiers (RM2622) : pas de cadre git sur un dossier sans dépôt");

// — RM2384 : bannière de cohérence git (mergeabilité) dans la fiche de revue —
const mcBanner = grabO("mcBanner", { esc: escO });
assert.strictEqual(mcBanner(null), "", "mc absent → pas de bannière");
assert.strictEqual(mcBanner({}), "", "mc sans verdict → pas de bannière");
const bOk = mcBanner({ verdict: { level: "ok", headline: "Branche à jour, merge propre" } });
assert(/class="mcbanner mc-ok"/.test(bOk) && /✅/.test(bOk), "niveau ok → classe + icône vertes");
assert(/Branche à jour/.test(bOk) && !/mc-advice/.test(bOk), "titre rendu, pas de conseil sans advice");
const bBlock = mcBanner({
  mr_url: "https://gitlab.x/mr/1",
  verdict: { level: "block", headline: "Conflit de merge avec dev (2 fichier(s))",
             detail: "CHANGELOG.md, src/app.py",
             advice: "merge dev dans la branche, résous, pousse" } });
assert(/class="mcbanner mc-block"/.test(bBlock) && /⛔/.test(bBlock), "conflit → bannière rouge");
assert(/mc-advice[^>]*>→ /.test(bBlock), "la remédiation est mise en avant (→)");
assert(/CHANGELOG.md/.test(bBlock), "les fichiers en conflit apparaissent");
assert(/href="https:\/\/gitlab\.x\/mr\/1"/.test(bBlock), "le lien MR est proposé quand il existe");
const bXss = mcBanner({ verdict: { level: "warn", headline: "en retard <b>x</b>" } });
assert(/&lt;b&gt;/.test(bXss) && !/<b>/.test(bXss), "le titre est échappé (anti-XSS)");
const bUnk = mcBanner({ verdict: {} });
assert(/mc-unknown/.test(bUnk) && /❔/.test(bUnk), "verdict sans niveau → unknown, jamais une classe cassée");
console.log("✓ mcBanner (RM2384) : niveaux, remédiation, lien MR, échappement");

// — RM2458 : rendu de la page de santé du poste —
// RM2708 : envStatusHtml compose désormais avec quatre fonctions pures — on les
// évalue dans UN sandbox partagé, sinon chacune serait aveugle aux autres.
const envCtx = { esc: escO, jarg: jargFn };
for (const n of ["envStatusTabs", "envStatusDefaultTab", "envStatusSections",
                 "envStatusBadge", "envStatusGroupHtml", "envStatusHtml"]) {
  envCtx[n] = grabO(n, envCtx);
}
const envStatusHtml = envCtx.envStatusHtml;
assert(/état indisponible/.test(envStatusHtml(null)), "rapport absent → message, pas de crash");
const rep = {
  generated_at: "2026-08-12T20:00:00",
  summary: { counts: { ok: 3, info: 0, warn: 1, error: 1 } },
  groups: [
    { name: "Outils & dépendances", checks: [
      { label: "bw", level: "error", detail: "binaire introuvable", fix: "npm i -g @bitwarden/cli" },
      { label: "git", level: "ok", detail: "git version 2.43.0" } ] },
    { name: "Git / GitLab", checks: [
      { label: "repo pisceen/infra-core [main]", level: "error", detail: "9 non poussés, 3 en retard",
        fix: "cd /w && git pull --rebase --autostash" } ] },
  ],
};
// RM2708 : une famille à la fois → on force l'onglet pour les assertions de rendu
const esh = envStatusHtml(rep, "Outils & dépendances")
  + envStatusHtml(rep, "Git / GitLab");
assert(/es-row es-error/.test(esh) && /es-row es-ok/.test(esh), "les niveaux deviennent des classes colorées");
assert(/binaire introuvable/.test(esh) && /es-fix">npm i -g @bitwarden\/cli/.test(esh),
  "la ligne rouge montre le détail ET la commande de remédiation");
assert(/onclick="esCopy\(this\)"/.test(esh), "chaque remédiation a son bouton copier (sans arg dans l'onclick)");
assert(esh.indexOf('<code class="es-fix">') < esh.indexOf('esCopy'),
  "la commande vit dans le <code> AVANT le bouton (esCopy lit le voisin) — pas dans l'attribut");
assert(/es-when">2026-08-12T20:00:00/.test(esh), "l'horodatage du diagnostic est affiché");
const xss = envStatusHtml({ groups: [{ name: "X", checks: [{ label: "a<b>", level: "warn", detail: "<script>", fix: "x&y" }] }] });
assert(/a&lt;b&gt;/.test(xss) && !/<script>/.test(xss) && /x&amp;y/.test(xss), "label/détail/fix échappés (anti-XSS)");
console.log("✓ envStatusHtml (RM2458) : niveaux colorés, remédiation copiable, échappement");

// — RM2708 : familles en onglets, dépôts en sections par client —
const G6 = [
  { name: "Outils & dépendances", checks: [{ label: "git", level: "ok" }] },
  { name: "Git / GitLab", checks: [{ label: "PAT", level: "warn" }, { label: "push", level: "ok" }] },
  { name: "Repos", checks: [
    { label: "repo calicote/presta [main]", level: "ok", section: "calicote" },
    { label: "repo calicote/dolibarr [dev]", level: "ok", section: "calicote" },
    { label: "repo pisceen/presta [main]", level: "error", detail: "9 non poussés", section: "pisceen" },
    { label: "repo perso/maths [main]", level: "warn", section: "perso" },
    { label: "repos PM", level: "info", detail: "liste tronquée à 120 repos" } ] },
];
const tabs2708 = envCtx.envStatusTabs(G6);
assert.deepStrictEqual([...tabs2708.map(t => t.name)],
  ["Outils & dépendances", "Git / GitLab", "Repos"], "un onglet par famille, dans l'ordre du serveur");
assert.deepStrictEqual({ ...tabs2708[2] }, { name: "Repos", warn: 1, error: 1, n: 5 },
  "chaque onglet porte ses compteurs de défauts (visibles sans cliquer)");
assert.strictEqual(envCtx.envStatusDefaultTab(tabs2708), "Repos",
  "on ouvre sur la première famille EN ERREUR, pas sur la première tout court");
assert.strictEqual(envCtx.envStatusDefaultTab([{ name: "A", warn: 2, error: 0 }, { name: "B", warn: 0, error: 0 }]),
  "A", "à défaut d'erreur, la première en avertissement");
assert.strictEqual(envCtx.envStatusDefaultTab([{ name: "A" }, { name: "B" }]), "A",
  "tout est vert → la première famille");
assert.strictEqual(envCtx.envStatusDefaultTab([]), "", "aucune famille toléré");
// sections : défauts en tête, sans-section d'abord (lignes de service)
const secs2708 = envCtx.envStatusSections(G6[2].checks);
assert.deepStrictEqual([...secs2708.map(s => s.name)], ["", "pisceen", "perso", "calicote"],
  "lignes hors client en tête, puis les sections EN DÉFAUT, puis le reste par ordre alpha");
assert.strictEqual(secs2708[3].checks.length, 2, "les dépôts d'un client sont regroupés");
assert.strictEqual(envCtx.envStatusSections([]).length, 0, "aucune ligne → aucune section");
// rendu : replié quand tout va bien, déplié quand ça coince
const rep2 = { summary: { counts: {} }, groups: G6 };
const hRepos = envStatusHtml(rep2, "Repos");
assert(/<details class="es-sec" open><summary>pisceen/.test(hRepos),
  "une section en erreur est DÉPLIÉE — c'est ce qu'on vient voir");
assert(/<details class="es-sec"><summary>calicote/.test(hRepos),
  "une section sans défaut est repliée (20 clients, presque tous sans rien à signaler)");
assert(/liste tronquée à 120 repos/.test(hRepos) && !/<summary><\/summary>/.test(hRepos),
  "les lignes sans client restent visibles, sans section fantôme");
assert(!/repo calicote\/presta/.test(envStatusHtml(rep2, "Git / GitLab")),
  "un onglet ne montre QUE sa famille");
assert(/es-badge es-error">✗ 1/.test(hRepos) && /es-badge es-warn">! 1/.test(hRepos),
  "les pastilles de défaut sont rendues sur les onglets");
assert(/onclick="setEnvTab\('Repos'\)"/.test(hRepos),
  "l'onglet se change par setEnvTab, argument passé en guillemets simples (jarg)");
// une famille à plat (sans section) ne fabrique aucun <details>
assert(!/es-sec/.test(envStatusHtml(rep2, "Outils & dépendances")),
  "une famille sans section reste une liste à plat");
console.log("✓ santé du poste (RM2708) : onglets par famille, dépôts sectionnés par client");

// — RM2659 : les racines de la session, groupées par projet —
// Une session touche parfois plusieurs projets (7 sur 62 au registre) : le
// panneau doit les distinguer au lieu de supposer qu'il n'y en a qu'un.
const mFg = />>> filesGroups[\s\S]*?(function filesGroups[\s\S]*?)\n\/\/ <<< filesGroups/.exec(html);
assert(mFg, "marqueurs >>> filesGroups introuvables");
const filesGroups = vm.runInNewContext("(" + mFg[1] + ")");
const P1 = { root: "/w/appli", name: "appli", client: "ca", project: "appli",
             docs: [{ path: "/pm/ca/appli/docs", name: "docs", label: "documents du projet", docs: 4 }] };
const P2 = { root: "/w/infra", name: "infra", client: "cb", project: "infra", docs: [] };
const W = [{ path: "/w/appli/envs/appli-rm42", name: "appli-rm42", exists: true },
           { path: "/w/infra/envs/infra-rm7", name: "infra-rm7", exists: true }];
let gs = filesGroups([P1, P2], W);
assert.strictEqual(gs.length, 2, "deux projets → deux groupes");
assert.deepStrictEqual(Array.from(gs.map(g => g.label)), ["appli", "infra"],
  "l'ordre du serveur est conservé");
assert.strictEqual(gs[0].roots[0].kind, "root", "la racine du workspace vient en premier");
assert.strictEqual(gs[0].roots[0].path, "/w/appli", "…et c'est bien la racine, pas un worktree");
assert(gs[0].roots.some(r => r.kind === "doc" && r.name === "docs"), "la doc du projet suit");
assert(gs[0].roots.some(r => r.path === "/w/appli/envs/appli-rm42"),
  "le worktree de la session est rattaché à SON projet");
assert(!gs[0].roots.some(r => r.path === "/w/infra/envs/infra-rm7"),
  "et pas à l'autre projet");
// un seul projet : c'est le cas courant (84 % des sessions)
gs = filesGroups([P1], [W[0]]);
assert.strictEqual(gs.length, 1, "un seul projet → un seul groupe");
// un worktree hors de toute racine connue ne doit pas disparaître
gs = filesGroups([P1], [{ path: "/ailleurs/vieux-layout", name: "vieux", exists: true }]);
assert.strictEqual(gs.length, 2, "un worktree orphelin forme son propre groupe");
assert.strictEqual(gs[1].label, "hors projet", "…nommé pour ce qu'il est");
assert.strictEqual(gs[1].roots[0].name, "vieux", "…et il est bien dedans");
// un worktree disparu du disque n'est pas proposé
gs = filesGroups([P1], [{ path: "/w/appli/envs/x", name: "x", exists: false }]);
assert(!gs[0].roots.some(r => r.name === "x"), "un worktree absent du disque n'est pas listé");
// pas de préfixe accidentel : /w/appli ne doit pas capturer /w/appli-autre
gs = filesGroups([P1], [{ path: "/w/appli-autre/envs/y", name: "y", exists: true }]);
assert.strictEqual(gs.length, 2, "un chemin voisin n'est pas avalé par la racine");
// entrées vides / absentes : le panneau ne doit pas tomber
assert.strictEqual(filesGroups(null, null).length, 0, "aucune donnée → aucun groupe");
assert.strictEqual(filesGroups([{ name: "sans racine" }], []).length, 0,
  "un projet sans racine est ignoré plutôt que rendu à moitié");
console.log("✓ fichiers (RM2659) : racines groupées par projet, multi-projets couvert");
const mGo = />>> filesGroupOf[\s\S]*?(function filesGroupOf[\s\S]*?)\n\/\/ <<< filesGroupOf/.exec(html);
assert(mGo, "marqueurs >>> filesGroupOf introuvables");
const filesGroupOf = vm.runInNewContext("(" + mGo[1] + ")");
const G = filesGroups([P1, P2], W);
assert.strictEqual(filesGroupOf(G, "/w/infra").label, "infra",
  "le groupe actif suit la racine ouverte");
assert.strictEqual(filesGroupOf(G, "/w/appli/envs/appli-rm42").label, "appli",
  "…y compris depuis un worktree");
assert.strictEqual(filesGroupOf(G, "/inconnu").label, "appli",
  "un chemin inconnu retombe sur le premier groupe, pas sur rien");
assert.strictEqual(filesGroupOf([], "/x"), null, "sans groupe, pas de groupe actif");
console.log("✓ fichiers (RM2659) : le projet actif suit ce qu'on lit");
// la racine du projet a son icône et se distingue d'un worktree
const rootLbl = fileRootLabel({ kind: "root", name: "ai-project-management",
                                label: "racine du workspace", path: "/w/x" });
assert.strictEqual(rootLbl.icon, "🏠", "la racine du projet porte sa propre icône");
assert(/racine du workspace/.test(rootLbl.tip), "l'infobulle dit ce que c'est");
// le rendu : barre des projets seulement s'il y en a plusieurs
const mRf2 = /function renderFiles\(\) \{[\s\S]*?\n\}/.exec(html);
assert(/groups\.length > 1/.test(mRf2[0]),
  "la barre des projets n'apparaît qu'à partir de deux projets");
const mLf = /async function loadFiles\([\s\S]*?\n\}/.exec(html);
assert(/filesGroups\(/.test(mLf[0]),
  "le panneau s'appuie sur les racines, pas sur les seuls worktrees");
console.log("✓ fichiers (RM2659) : barre projet conditionnelle, panneau non vide sans worktree");

// — RM1952 : triage ROI des tickets ouverts —
const triageFilter = grabO("triageFilter");
const triageRowHtml = grabO("triageRowHtml", { esc: escO });
const TT = [
  { rm_id: 1, client: "iprospective", project: "atlas", awaiting_validation: false },
  { rm_id: 2, client: "iprospective", project: "infra", awaiting_validation: true },
  { rm_id: 3, client: "calicote", project: "prestashop", awaiting_validation: false },
];
assert.strictEqual(triageFilter(TT, "", "", false).length, 3, "sans filtre → tout");
assert.strictEqual(triageFilter(TT, "iprospective", "", false).length, 2, "filtre client");
assert.strictEqual(triageFilter(TT, "iprospective", "infra", false).length, 1, "filtre client+projet");
assert.strictEqual(triageFilter(TT, "", "", true).length, 2, "masquer la validation retire les a_tester_*");
assert.strictEqual([...triageFilter(null, "", "", false)].length, 0, "liste absente tolérée");
// rendu d'une ligne : score, RM cliquable (numérique), badges, échappement
assert.strictEqual(triageRowHtml(null, 1), "", "entrée absente → vide");
const row = triageRowHtml({ rm_id: 42, title: "Fix <b>x</b>", status: "nouveau", priority: "high",
  score: 200, time_minutes: 90, unblocks: 3, blocked: true, blocked_by: [7, 8], awaiting_validation: false }, 1);
assert(/onclick="showTicket\(42\)"/.test(row), "clic → showTicket avec id numérique (pas d'injection)");
assert(/tr-score[^>]*>200</.test(row) && />RM42</.test(row), "score et RM affichés");
assert(/🔓 3/.test(row) && /tr-blocked/.test(row), "badges débloque + bloqué");
assert(/bloqué par : 7, 8/.test(row), "l'infobulle liste les bloqueurs");
assert(/Fix &lt;b&gt;x&lt;\/b&gt;/.test(row) && !/<b>/.test(row), "titre échappé (anti-XSS)");
assert(/90 min/.test(row), "estimation de temps affichée");
const rv = triageRowHtml({ rm_id: 9, title: "v", status: "a_mep", priority: "normal", score: 5, awaiting_validation: true }, 2);
assert(/⏳/.test(rv) && !/🔓/.test(rv), "en validation → ⏳ ; pas de badge débloque sans unblocks");
console.log("✓ triage (RM1952) : filtres, score, débloquants/bloqués, échappement");

// — RM2673 : écriture dans un jeu, tickets du worklog, fichiers sans session —
const setWritable = grabO("setWritable");
const SETS = [
  { name: "default", label: "default" },
  { name: "pm", label: "PM", derived: true, rule: { client: "iprospective", project: "pm-ai-agents" } },
];
assert.strictEqual(setWritable(SETS, "default", "set"), true, "jeu manuel → écriture possible");
assert.strictEqual(setWritable(SETS, "pm", "set"), false, "jeu dérivé → aucune écriture");
assert.strictEqual(setWritable(SETS, "pm", "live"), false,
  "le jeu dérivé reste la cible en vue « sessions ouvertes » — le bouton ne doit pas revenir");
assert.strictEqual(setWritable(SETS, "pm", "all"), false, "…ni en vue « tous les jeux »");
assert.strictEqual(setWritable(SETS, "default", "client:acme"), false,
  "une vue par client ne désigne aucun jeu (RM2536)");
assert.strictEqual(setWritable(SETS, "inconnu", "set"), true,
  "jeu pas encore chargé : on n'interdit pas à l'aveugle");
assert.strictEqual(setWritable(null, "pm", null), true, "cache vide toléré");
// les trois gestes partagent la même question
const mRss2673 = /async function refreshSessionSets\(\)[\s\S]*?\n\}/.exec(html);
assert(/setWritable\(setsCache, currentSet, currentView\)/.test(mRss2673[0]),
  "le bouton d'enregistrement s'appuie sur setWritable");
const mGhost2673 = /const inSet = ([^;]+);/.exec(html);
assert(/setWritable\(/.test(mGhost2673[1]), "⊖ et ⟳ des tuiles grises aussi");
const mSetList2673 = /async function loadSessionSet\(\)[\s\S]*?\n\}/.exec(html);
assert(/r\.derived \? "" :/.test(mSetList2673[0]),
  "la liste des entrées n'offre ni ⊖ ni ⟳ sur un jeu dérivé");
// une session VIVANTE appartient aussi aux jeux dérivés (RM2537) : son ⊖ doit
// tomber sous la même règle que celui des tuiles grises
const mLive2673 = /\(s\.sets \|\| \[\]\)\.includes\(currentSet\)([^?]*)\?/.exec(html);
assert(mLive2673 && /setWritable\(/.test(mLive2673[1]),
  "⊖ d'une session vivante : masqué quand le jeu courant est dérivé");
// déplacer / scinder touchent eux aussi les entrées d'un jeu
const mMove2673 = /const canMove = ([^;]+);/.exec(html);
assert(mMove2673 && /setWritable\(/.test(mMove2673[1]),
  "« → déplacer » exige un jeu source inscriptible");
assert(/s\.name !== currentSet && !s\.derived/.test(html),
  "…et les destinations dérivées ne sont pas proposées");
const mSplit2673 = /const split = ([^;]+);/.exec(html);
assert(mSplit2673 && /setWritable\(/.test(mSplit2673[1]),
  "la scission n'est pas proposée depuis un jeu dérivé");
console.log("✓ jeux (RM2673) : aucun geste d'écriture offert sur un jeu dérivé, quelle que soit la vue");

const ticketsOfSession = grabO("ticketsOfSession");
const REG = { branches: ["2673-ergonomie-pm", "sans-ticket"], worktrees: ["/w/appli/envs/appli-rm2605"] };
const WL = { todo: [{ ref: "RM2661" }], waiting: [{ ref: "RM2663" }], done: [{ ref: "RM2673" }],
             unknown: [{ ref: "chantier-libre" }] };
assert.deepStrictEqual([...ticketsOfSession("2673", REG, null)], ["2673", "2605"],
  "ancrage puis registre (branche déjà connue, non dupliquée)");
assert.deepStrictEqual([...ticketsOfSession("calymix", null, WL)], ["2661", "2663", "2673"],
  "session slug : ses tickets viennent du worklog, reste-à-faire d'abord");
assert.deepStrictEqual([...ticketsOfSession("2673", REG, WL)], ["2673", "2605", "2661", "2663"],
  "toutes sources fusionnées, sans doublon, dans l'ordre de proximité");
assert.deepStrictEqual([...ticketsOfSession("calymix", null, null)], [],
  "rien de connu → aucune invention");
assert.deepStrictEqual([...ticketsOfSession("calymix", null, { todo: [{ ref: "libre" }] })], [],
  "un chantier hors ticket n'est pas un RM-id");
const mRt2673 = /function renderTickets\(\)[\s\S]*?\n\}/.exec(html);
assert(/loadWorklog\(\)/.test(mRt2673[0]),
  "l'onglet tickets charge le worklog lui-même (il ne dépend pas de l'onglet état)");
assert(/aucun ticket dans son worklog/.test(mRt2673[0]),
  "le message vide ne parle du worklog qu'une fois celui-ci lu");
console.log("✓ tickets (RM2673) : le worklog de session compte comme source, sans doublon");

const filesContext = grabO("filesContext");
const filesCtxKey = grabO("filesCtxKey");
assert.deepStrictEqual(Object.assign({}, filesContext({ attached: "2673", currentReview: "10" })),
  { kind: "session", sid: "2673" }, "session attachée : elle prime sur tout");
const fcTicket = filesContext({ currentReview: "2605",
  resolveCache: { 2605: { found: true, client: "acme", project: "shop" } } });
assert.strictEqual(fcTicket.kind + " " + fcTicket.client + "/" + fcTicket.project, "project acme/shop",
  "fiche de ticket ouverte → son projet");
assert(/RM2605/.test(fcTicket.from), "…et le panneau peut dire d'où ça vient");
assert.strictEqual(filesContext({ currentProjectView: "beta/api" }).project, "api",
  "fiche projet ouverte → ce projet");
assert.strictEqual(filesContext({ currentSet: "pm", sets: SETS }).project, "pm-ai-agents",
  "à défaut, la règle du jeu courant désigne un projet");
assert.strictEqual(filesContext({ currentSet: "default", sets: SETS }).kind, "none",
  "un jeu manuel ne désigne aucun projet : on ne devine pas");
assert.strictEqual(filesContext({ currentReview: "9", resolveCache: { 9: { found: false } } }).kind, "none",
  "ticket non résolu → pas de projet inventé");
assert.strictEqual(filesContext(null).kind, "none", "contexte absent toléré");
assert.strictEqual(filesCtxKey({ kind: "session", sid: "7" }), "s:7", "clé de session");
assert.strictEqual(filesCtxKey({ kind: "project", client: "a", project: "b" }), "p:a/b", "clé de projet");
assert.strictEqual(filesCtxKey({ kind: "none" }), "none", "clé du vide");
const mLf3 = /async function loadFiles\([\s\S]*?\n\}/.exec(html);
assert(/project-roots\//.test(mLf3[0]),
  "sans session, le panneau lit la racine + la doc du projet (endpoint léger)");
assert(!/attache une session pour parcourir/.test(html),
  "plus de cul-de-sac « attache une session » quand un projet est identifié");
// la doc d'un projet sans workspace résolu ne disparaît pas avec la racine
const gsDoc = filesGroups([{ client: "a", project: "b", docs: [{ path: "/pm/b/docs", name: "docs" }] }], []);
assert.strictEqual(gsDoc.length, 1, "projet sans racine mais avec doc → groupe conservé");
assert.strictEqual(gsDoc[0].roots[0].kind, "doc", "…et c'est bien sa doc qu'on lit");
assert.strictEqual(filesGroups([{ client: "a", project: "b", docs: [] }],
  [{ path: "/ailleurs/x", name: "x", exists: true }])[0].label, "hors projet",
  "une racine vide n'aspire pas les worktrees des autres");
console.log("✓ fichiers (RM2673) : repli sur le projet courant, provenance affichée");

// — RM2695 : avancement d'un ticket dans le worklog —
const worklogProgressHtml = grabO("worklogProgressHtml");
const wpNone = worklogProgressHtml({ ref: "RM1", status: "en_cours" }, escO);
assert.strictEqual(wpNone, "",
  "un ticket sans checklist ne rend RIEN — « 0/0 » se lirait comme un ticket vide");
assert.strictEqual(worklogProgressHtml(null, escO), "", "item absent toléré");
assert.strictEqual(worklogProgressHtml({ checklist: { done: 0, total: 0, items: [] } }, escO), "",
  "checklist vide = pas de checklist");
const wp = worklogProgressHtml({ checklist: { done: 3, total: 6, items: ["reste A", "reste B"] } }, escO);
assert(/>3\/6 ✓</.test(wp), "le compteur x/y est affiché");
assert(/☐ reste A/.test(wp) && /☐ reste B/.test(wp), "les critères RESTANTS sont listés");
assert(!/pill ok/.test(wp), "tant que ce n'est pas fini, pas de pastille verte");
const wpDone = worklogProgressHtml({ checklist: { done: 6, total: 6, items: [] } }, escO);
assert(/pill ok/.test(wpDone) && />6\/6 ✓</.test(wpDone),
  "tout coché → pastille verte, et rien à lister (ce qui est fait se compte)");
const wpZero = worklogProgressHtml({ checklist: { done: 0, total: 4, items: ["a"] } }, escO);
assert(/pill warn/.test(wpZero), "aucun critère coché → pastille d'alerte");
const wpTrunc = worklogProgressHtml({ checklist: { done: 0, total: 60, items: ["a"], truncated: true } }, escO);
assert(/…/.test(wpTrunc), "une liste tronquée le DIT (pas de silence sur ce qui manque)");
// sous-tâches : leur statut, pas juste leur numéro
const wpSub = worklogProgressHtml({ sub_tasks: [{ rm_id: "2696", status: "a_faire", title: "T2" }] }, escO);
assert(/RM2696 · a_faire/.test(wpSub), "une sous-tâche porte son statut");
assert(/title="sous-tâche — T2"/.test(wpSub), "…et son titre en infobulle");
// échappement (le texte d'un critère vient de la description du ticket)
const wpXss = worklogProgressHtml({ checklist: { done: 0, total: 1, items: ["<img src=x onerror=1>"] },
  sub_tasks: [{ rm_id: "1<b>", status: "a<b>", title: "t<b>" }] }, escO);
assert(!/<img/.test(wpXss) && /&lt;img/.test(wpXss), "le texte d'un critère est échappé");
assert(!/<b>/.test(wpXss), "id, statut et titre de sous-tâche échappés aussi");
// le rendu du worklog appelle bien l'avancement
const mItem = /const itemHtml = \(it\) => \{[\s\S]*?\n  \};/.exec(html);
assert(mItem && /worklogProgressHtml\(it, esc\)/.test(mItem[0]),
  "chaque ligne du worklog rend l'avancement de son ticket");
console.log("✓ worklog (RM2695) : avancement par ticket, critères restants, sous-tâches");

// — RM2696 : worklog PROJET (toutes sessions confondues) —
// RM2723 : la ligne de MR est désormais une fonction partagée (session + projet).
const mrLineHtml = grabO("mrLineHtml");
const projWorklogHtml = grabO("projWorklogHtml", { mrLineHtml });
assert(/rien en cours sur ce projet/.test(projWorklogHtml(null, escO, jargFn)),
  "projet sans activité → message, pas de crash");
const GRP = {
  key: "acme/shop",
  counts: { sessions_live: 1, sessions: 2, active: 2, waiting: 1, orphans: 1, mrs: 1, requests: 1 },
  tickets: [
    { rm_id: "11", status: "en_cours", title: "orphelin", bucket: "active",
      sessions: [], has_live_session: false },
    { rm_id: "10", status: "en_cours", title: "suivi", bucket: "active",
      sessions: ["70"], has_live_session: true, checklist: { done: 1, total: 2, items: ["b"] } },
    { rm_id: "12", status: "a_tester_demandeur", title: "en attente", bucket: "waiting",
      sessions: ["71"], has_live_session: false },
  ],
  mrs: [{ iid: "9", ref: "RM12", target: "dev", url: "https://x/9", alive: false }],
  requests: [{ text: "une demande", n: 1 }],
  sessions: [{ sid: "70", alive: true, title: "T" }, { sid: "71", alive: false, title: "U" }],
};
const pw = projWorklogHtml(GRP, escO, jargFn);
assert(/1 session\(s\) ouverte\(s\)/.test(pw) && /15|2 en cours/.test(pw), "bandeau de compteurs");
assert(/💤 à reprendre/.test(pw), "un ticket actif sans session vivante est SIGNALÉ (le cas qu'on perd de vue)");
assert(pw.indexOf("RM11") < pw.indexOf("RM10"), "…et il passe avant les tickets suivis");
assert(/>1\/2 ✓</.test(pw), "l'avancement (RM2695) est repris dans la vue projet");
assert(/🔀 MR à merger \(1\)/.test(pw) && /!9/.test(pw), "les MR non mergées sont listées");
assert(/session éteinte/.test(pw), "une MR laissée par une session éteinte le dit");
assert(/📥 demandes non ticketées \(1\)/.test(pw), "les demandes non ticketées remontent");
assert(/a_tester_demandeur : 1/.test(pw), "les attentes sont comptées par statut (le geste diffère)");
assert(/onclick="attach\('70'\)"/.test(pw), "les sessions sont attachables (arg en guillemets simples, jarg)");
assert(/onclick="showTicket\(11\)"/.test(pw), "un ticket ouvre sa fiche (id numérique, pas d'injection)");
// plafond d'affichage : borné ET annoncé
const many = { counts: {}, tickets: Array.from({ length: 33 }, (_, i) =>
  ({ rm_id: String(200 + i), status: "a_tester_demandeur", title: "t", bucket: "waiting",
     sessions: [], has_live_session: false })), mrs: [], requests: [], sessions: [] };
const pwMany = projWorklogHtml(many, escO, jargFn);
assert((pwMany.match(/class="r-id"/g) || []).length === 20, "la liste est bornée à 20 lignes");
assert(/… et 13 autre\(s\)/.test(pwMany), "…et la troncature est ANNONCÉE (jamais muette)");
// échappement : titres et textes viennent des tickets et des demandes
const pwXss = projWorklogHtml({ counts: {}, tickets: [{ rm_id: "1", status: "<b>s", title: "<img src=x>",
  bucket: "active", sessions: ["<b>"], has_live_session: false }],
  mrs: [], requests: [{ text: "<script>" }], sessions: [] }, escO, jargFn);
assert(!/<img/.test(pwXss) && !/<script>/.test(pwXss) && /&lt;img/.test(pwXss),
  "titre, statut, session et demande échappés (anti-XSS)");
console.log("✓ worklog projet (RM2696) : orphelins en tête, MR pendantes, attentes comptées");


// — RM2716 : sélection de tickets du worklog → traitement en série —
const batchPlanHtml = grabO("batchPlanHtml");
const PLAN = {
  count: 2,
  todo: [{ rm_id: "10", status: "a_faire", title: "dev", instruction: "traiter puis livrer" },
         { rm_id: "11", status: "a_etudier_chiffrer", title: "étude", instruction: "étudier et chiffrer" }],
  skipped: [{ rm_id: "12", status: "a_tester_demandeur", title: "chez toi",
              reason: "attend TON verdict, pas celui de l'agent" }],
};
const bp = batchPlanHtml(PLAN, escO);
assert(/▶ à traiter \(2\)/.test(bp), "le récapitulatif compte ce qui va partir");
assert(/1\.<\/b> <span class="r-id">RM10/.test(bp), "les tickets sont numérotés dans l'ordre d'exécution");
assert(/traiter puis livrer/.test(bp) && /étudier et chiffrer/.test(bp),
  "chaque ticket affiche l'action qui sera demandée");
assert(/⊘ écartés \(1\)/.test(bp) && /attend TON verdict/.test(bp),
  "les écartés sont listés AVEC leur raison — rien n'est retiré en silence");
assert(!/au-delà de 10/.test(bp), "pas d'avertissement de volume sur un petit lot");
const bpBig = batchPlanHtml({ todo: Array.from({ length: 12 }, (_, i) =>
  ({ rm_id: String(i), status: "a_faire", instruction: "traiter" })), skipped: [] }, escO);
assert(/au-delà de 10/.test(bpBig), "au-delà de 10 tickets, l'avertissement de volume s'affiche");
const bpEmpty = batchPlanHtml({ todo: [], skipped: [] }, escO);
assert(/aucun ticket actionnable/.test(bpEmpty), "sélection sans actionnable : dit clairement qu'il n'y a rien");
assert(/à traiter \(0\)/.test(batchPlanHtml(null, escO)), "plan absent toléré");
const bpXss = batchPlanHtml({ todo: [{ rm_id: "1<b>", status: "<img src=x>", title: "<script>",
  instruction: "<b>i" }], skipped: [{ rm_id: "2", reason: "<script>" }] }, escO);
assert(!/<img|<script>/.test(bpXss), "titre, statut, instruction et raison échappés (anti-XSS)");
// la case à cocher ne détourne pas le clic de la ligne, et n'existe que sur un ticket
const mItem2716 = /const itemHtml = \(it\) => \{[\s\S]*?\n  \};/.exec(html);
assert(/event\.stopPropagation\(\);batchToggle\(/.test(mItem2716[0]),
  "cocher ne doit pas ouvrir la fiche du ticket");
assert(/\/\^RM\\d\+\$\/i\.test/.test(mItem2716[0]),
  "seul un TICKET est sélectionnable (un chantier libre n'a pas de protocole)");
// l'envoi passe par le récapitulatif : jamais d'appel direct sans dry_run d'abord
const mOpen = /async function openBatchPlan\([\s\S]*?\n\}/.exec(html);
assert(mOpen, "openBatchPlan introuvable");
assert(/dry_run: true/.test(mOpen[0]), "le récapitulatif s'obtient en dry_run (aucun envoi)");
const mSend = /async function sendBatch\([\s\S]*?\n\}/.exec(html);
assert(/batchPlanCache/.test(mSend[0]),
  "l'envoi n'est possible qu'après avoir chargé — donc affiché — le récapitulatif");
console.log("✓ lot worklog (RM2716) : récapitulatif avant envoi, écartés motivés, garde de volume");


// — RM2697 : tableau de bord « ce qui requiert mon attention » —
const attentionRows = grabO("attentionRows", { tmuxNameOf: sid => String(sid) });
const attentionHtml = grabO("attentionHtml");
const OV = { projects: [
  { client: "acme", project: "shop", counts: {},
    tickets: [{ rm_id: "10", status: "a_tester_demandeur", title: "livré", bucket: "waiting" },
              { rm_id: "11", status: "en_cours", title: "en cours", bucket: "active" },
              { rm_id: "12", status: "a_mep", title: "à déployer", bucket: "waiting" }],
    mrs: [{ iid: "9", ref: "RM11", url: "https://x/9", alive: false }],
    requests: [{ text: "une demande" }],
    sessions: [{ sid: "70", alive: true, title: "S70" }] },
] };
const SESS = { "70": { state: "idle", client: "acme", project: "shop", title: "S70" },
               "71": { state: "attention", client: "acme", project: "shop", title: "S71" } };
const rows = attentionRows(OV, SESS, { stale: [] });
assert.deepStrictEqual([...rows.map(r => r.kind)],
  ["question", "test", "mr", "mep", "idle", "request"],
  "l'ordre suit le COÛT de l'attente, pas le projet");
assert.strictEqual(rows[0].verb, "réponds", "une session qui attend une réponse passe avant tout");
assert.strictEqual(rows[1].rm_id, "10", "puis ce qui attend TON verdict");
assert(rows[2].text.includes("session éteinte"), "une MR d'une session éteinte le dit");
assert.strictEqual(rows[4].kind, "idle", "une session au repos avec du travail actif remonte");
assert(/1 ticket\(s\) en cours/.test(rows[4].text), "…en disant combien de travail reste");
// une question restée sans réponse (RM2598) compte comme attente, même sans état ⚠
const stale = attentionRows({ projects: [] }, { "80": { client: "a", project: "b", title: "S" } }, { stale: ["80"] });
assert.strictEqual(stale.length === 1 && stale[0].icon, "🕓", "question laissée sans réponse : signalée");
// filtres
assert.strictEqual(attentionRows(OV, SESS, { client: "autre" }).length, 0, "filtre client");
assert.strictEqual(attentionRows(OV, SESS, { project: "shop" }).length, rows.length, "filtre projet");
assert.deepStrictEqual([...attentionRows(null, null, {})], [], "données absentes tolérées");
// une session au repos SANS travail actif n'encombre pas
const calme = attentionRows({ projects: [{ client: "a", project: "b", tickets: [], mrs: [],
  requests: [], sessions: [{ sid: "9", alive: true }] }] }, {}, {});
assert.strictEqual(calme.length, 0, "pas de ligne pour une session au repos sans rien à faire");
// rendu
const dh = attentionHtml(rows, escO, jargFn);
assert(/dash-sec/.test(dh) && /une session attend ta réponse/.test(dh), "les lignes sont groupées par nature d'attente");
assert(/onclick="attach\('71'\)"/.test(dh), "une session s'attache en un clic");
assert(/onclick="openReview\('10'\)"/.test(dh), "un ticket ouvre sa fiche");
assert(/window\.open\('https:\/\/x\/9'/.test(dh), "une MR s'ouvre sur la forge");
assert(/rien n’attend de toi/.test(attentionHtml([], escO, jargFn)),
  "rien à faire est une bonne nouvelle, pas un écran mort");
// volume : sur ce poste la liste brute fait 175 lignes — un tableau de bord qui
// les afficherait toutes rejouerait le problème qu'il corrige
const many2697 = Array.from({ length: 40 }, (_, i) =>
  ({ rank: 2, kind: "test", icon: "🧪", verb: "teste", client: "a", project: "b",
     rm_id: String(1000 + i), text: "t", since: "2026-08-" + String(10 + (i % 20)).padStart(2, "0") }));
const dhMany = attentionHtml(many2697, escO, jargFn);
assert.strictEqual((dhMany.match(/dash-row/g) || []).length, 5, "au plus 5 lignes par nature d'attente");
assert(/… et 35 autre/.test(dhMany), "…et le reste est ANNONCÉ, jamais coupé en silence");
assert(/dash-chip[^>]*>🧪 40</.test(dhMany), "le compte RÉEL reste visible en tête (vue d'ensemble)");
assert(/\(40\)/.test(dhMany), "chaque section porte son total, pas le nombre affiché");
// ancienneté : ce qui attend depuis le plus longtemps passe devant
const parAge = attentionRows({ projects: [{ client: "a", project: "b", mrs: [], requests: [], sessions: [],
  tickets: [{ rm_id: "2", status: "a_tester_demandeur", title: "récent", updated: "2026-08-17" },
            { rm_id: "1", status: "a_tester_demandeur", title: "vieux", updated: "2026-06-01" }] }] }, {}, {});
assert.deepStrictEqual([...parAge.map(r => r.rm_id)], ["1", "2"],
  "dans une nature, le plus ancien d'abord — trier par numéro trierait au hasard");
assert(/2026-06-01/.test(attentionHtml(parAge, escO, jargFn)), "la date d'attente est affichée");
const dhXss = attentionHtml([{ rank: 1, kind: "test", icon: "🧪", verb: "<b>v", client: "<img src=x>",
  project: "p", rm_id: "1", text: "<script>" }], escO, jargFn);
assert(!/<img|<script>|<b>v/.test(dhXss), "verbe, client et texte échappés (anti-XSS)");
console.log("✓ dashboard (RM2697) : tri par nature d'attente, verbes d'action, écran vide parlant");

// — RM2698 : alertes de dérive, en tête du tableau de bord —
const alertsHtml = grabO("alertsHtml");
assert.strictEqual(alertsHtml({ alerts: [] }, escO, jargFn), "",
  "rien à signaler ⇒ RIEN d'affiché (une bannière permanente cesse d'être lue)");
assert.strictEqual(alertsHtml(null, escO, jargFn), "", "données absentes tolérées");
const AL = { total: 30, hidden: 18, alerts: [
  { kind: "verdict", key: "t:4", age_days: 48.2, rm_id: "4", client: "acme", project: "shop",
    label: "livré, attend ton verdict", title: "un titre" },
  { kind: "mr", key: "m:r:9", age_days: 29, iid: "9", url: "https://x/9", client: "acme",
    project: "shop", label: "MR ouverte, pas mergée" },
] };
const ah = alertsHtml(AL, escO, jargFn);
assert(/⚠ dérives \(30\)/.test(ah), "l'en-tête porte le TOTAL, pas le nombre affiché");
assert(/48 j/.test(ah) && /29 j/.test(ah), "chaque alerte porte son âge — sans lui, on ne priorise pas");
assert(/… et 18 dérive/.test(ah), "ce qui est masqué est annoncé, avec le renvoi aux réglages");
assert(/onclick="snoozeAlert\('t:4'\)"/.test(ah), "chaque alerte se REPORTE (jamais de suppression)");
assert(/⏳ 7 j/.test(ah), "le report est daté et explicite");
assert(/onclick="openReview\('4'\)"/.test(ah), "le ticket s'ouvre en un clic");
assert(/href="https:\/\/x\/9"/.test(ah), "une MR renvoie à la forge");
const ahXss = alertsHtml({ alerts: [{ kind: "mr", key: "<b>k", age_days: 1, client: "<img src=x>",
  project: "p", label: "<script>", title: "<b>t" }] }, escO, jargFn);
assert(!/<img|<script>|<b>t/.test(ahXss), "client, label et titre échappés (anti-XSS)");
// les alertes passent AVANT l'état dans le rendu du tableau de bord
const mRd = /function renderDashboard\(\)[\s\S]*?\n\}/.exec(html);
assert(mRd && mRd[0].indexOf("alertsHtml") < mRd[0].indexOf("attentionHtml"),
  "la dérive s'affiche avant l'état courant");
console.log("✓ alertes (RM2698) : datées, bornées, reportables, silencieuses quand tout va bien");

console.log("OK — tous les tests cockpit passent");

// — renderMailList (RM2671) : file de triage des emails —
const fml = />>> renderMailList[\s\S]*?(function renderMailList[\s\S]*?)\n\/\/ <<< renderMailList/.exec(html);
assert(fml, "marqueurs >>> renderMailList / <<< renderMailList introuvables");
const renderMailList = vm.runInNewContext("(" + fml[1] + ")", {});
// escFn / jargFn sont déjà définis plus haut dans ce fichier (RM2612/RM2623) :
// on les réutilise tels quels, pour tester avec les MÊMES échappements que la page.

assert(/file vide/.test(renderMailList([], null, escFn, jargFn)), "file vide non signalée");

const mails = [
  { key: "aaa1", subject: "Panne de caisse", from_name: "CalyClay", from: "a@b.fr",
    date: "2026-08-17T09:00", folder: "INBOX.Clients", state: "à traiter", attachments: 2,
    routing: { client: "calyclay", project: null, source: "contacts", confidence: 0.8 } },
  { key: "bbb2", subject: "Re: suite", from: "c@d.fr", date: "2026-08-16T09:00",
    state: "créé", created_rm: 2710, rm_id: 2661, routing: {} },
  { key: "ccc3", subject: "Merci", from: "e@f.fr", date: "2026-08-15T09:00",
    state: "écarté", dismissed: { reason: "accusé de réception" }, routing: {} },
];
let out = renderMailList(mails, null, escFn, jargFn);
assert(/calyclay\/\?/.test(out), "client sans projet doit rester « /? » (pas de choix silencieux)");
assert(/80%/.test(out) && /contacts/.test(out), "confiance et source absentes");
assert(/📎2/.test(out), "pièces jointes non signalées");
assert(/↩ RM2661/.test(out), "réponse à un fil non signalée");
assert(/→ RM2710/.test(out), "ticket créé non signalé");
assert(/accusé de réception/.test(out), "motif d'écartement absent");
assert(!/Créer le ticket/.test(out), "les actions ne doivent apparaître que sur l'email déplié");

// — email déplié : formulaire pré-rempli et éditable, actions présentes —
const open = [Object.assign({}, mails[0], {
  body: "Bonjour,\nça plante.", body_truncated: true,
  draft: { title: "Caisse HS", project: "calyclay/dolibarr", priority: "high",
           description: "Le TPE ne répond plus.", confidence: 0.75, actionable: true,
           warnings: ["projet hors liste (x) → écarté"] },
})];
out = renderMailList(open, "aaa1", escFn, jargFn);
assert(/id="ml-title" value="Caisse HS"/.test(out), "titre non pré-rempli");
assert(/id="ml-project" value="calyclay\/dolibarr"/.test(out), "projet non pré-rempli");
assert(/<option selected>high<\/option>|selected>high/.test(out), "priorité non pré-sélectionnée");
assert(/projet hors liste/.test(out), "avertissement de la proposition non affiché");
assert(/tronqué à la relève/.test(out), "troncature du corps non signalée");
["Rédiger", "Créer le ticket", "Note sur…", "Reclasser", "Écarter"].forEach(a =>
  assert(out.includes(a), "action manquante : " + a));

// — RM2588/mémoire : un argument chaîne passé en onclick doit être en quotes SIMPLES
//   (jarg), sinon l'attribut se referme et le handler meurt au clic —
assert(/onclick="mailToggle\('aaa1'\)"/.test(out), "clé non passée via jarg dans onclick");
assert(!/onclick="[^"]*\{&quot;/.test(out), "objet JSON injecté dans un onclick");

// — échappement : un sujet hostile ne doit pas sortir tel quel —
out = renderMailList([{ key: "ddd4", subject: '<img src=x onerror=alert(1)>',
                        from: "x@y.fr", date: "2026-08-14", state: "à traiter", routing: {} }],
                     null, escFn, jargFn);
assert(!/<img/.test(out) && /&lt;img/.test(out), "sujet non échappé");
console.log("✓ emails (RM2671) : file, routage affiché, formulaire pré-rempli, échappement");

// — onglets du panneau central (RM2672) : temporaire unique, épinglage, fermeture —
// `grab` (défini plus haut) rend la SOURCE de la fonction : on l'évalue ici.
const grabFn = (name) => vm.runInNewContext("(" + grab(name) + ")", { Object });
const upsertTab = grabFn("upsertTab"), closeTabAt = grabFn("closeTabAt"),
      renderCenterTabs = grabFn("renderCenterTabs");
// RM2726 : le formulaire délègue le choix de la cible à clientProjectPickerHtml,
// qui délègue lui-même les radios — on monte la chaîne dans le contexte isolé.
const newTicketFormHtml = vm.runInNewContext("(" + grab("newTicketFormHtml") + ")",
  { Object, clientProjectPickerHtml: vm.runInNewContext("(" + grab("clientProjectPickerHtml") + ")",
      { Object, Array, Set, projectRadiosHtml: grabFn("projectRadiosHtml") }) });

let st = { tabs: [], active: null };
st = upsertTab(st.tabs, "session", "2668", "RM2668");
assert.equal(st.tabs.length, 1); assert.equal(st.active, "session:2668");
assert.equal(st.tabs[0].pinned, false, "un onglet est temporaire par défaut");

// règle du temporaire unique : la vue suivante REMPLACE le temporaire précédent
st = upsertTab(st.tabs, "review", "2670", "RM2670");
assert.deepEqual(st.tabs.map(t => t.kind), ["review"], "le temporaire précédent doit céder la place");

// épinglé : il reste, et le temporaire vient à côté
st = upsertTab(st.tabs, "review", "2670", "RM2670", { pin: true });
st = upsertTab(st.tabs, "project", "calyclay/infra", "calyclay/infra");
assert.deepEqual(st.tabs.map(t => t.kind), ["review", "project"], "un onglet épinglé survit");
st = upsertTab(st.tabs, "newticket", "", "nouveau ticket");
assert.deepEqual(st.tabs.map(t => t.kind), ["review", "newticket"], "un seul temporaire à la fois");

// ré-ouvrir un onglet existant l'active sans le dupliquer
const before = st.tabs.length;
st = upsertTab(st.tabs, "review", "2670", "RM2670");
assert.equal(st.tabs.length, before, "pas de doublon d'onglet");
assert.equal(st.active, "review:2670");

// fermeture : voisin de gauche, puis de droite, puis plus rien
let c = closeTabAt(st.tabs, "review:2670", "review:2670");
assert.equal(c.active, "newticket:", "à défaut de voisin gauche, on prend le droit");
c = closeTabAt(c.tabs, "newticket:", "newticket:");
assert.equal(c.tabs.length, 0); assert.equal(c.active, null, "plus d'onglet → aucune vue active");
c = closeTabAt([{ kind: "review", key: "1" }], "review:404", "review:1");
assert.equal(c.tabs.length, 1, "fermer un onglet inconnu ne casse rien");

// rendu : actif, épinglé, échappement, et onclick en quotes simples (jarg)
const tabsHtml = renderCenterTabs(
  [{ kind: "review", key: "2670", label: "RM2670", pinned: true },
   { kind: "project", key: "x/y", label: '<b>x</b>', pinned: false }],
  "review:2670", escFn, jargFn);
assert(/class="ctab active"/.test(tabsHtml), "onglet actif non marqué");
assert(/📌/.test(tabsHtml) && /⇧/.test(tabsHtml), "état d'épinglage non rendu");
assert(/ctab temp/.test(tabsHtml), "onglet temporaire non signalé");
assert(!/<b>x<\/b>/.test(tabsHtml) && /&lt;b&gt;/.test(tabsHtml), "libellé non échappé");
assert(/onclick="activateTab\('review:2670'\)"/.test(tabsHtml), "id non passé via jarg");
assert(/event\.stopPropagation\(\);closeTab/.test(tabsHtml), "la croix doit stopper la propagation");

// formulaire pleine page : les champs qui manquaient à la carte repliée
const form = newTicketFormHtml([{ value: "feature", label: "feature" }, { value: "bugfix", label: "bugfix" }],
                               ["low", "normal", "high", "urgent"],
                               [{ client: "calyclay", project: "infra" }], "calyclay", "infra", escFn);
["ntf-title", "ntf-client", "ntf-projects", "ntf-type", "ntf-prio", "ntf-tags", "ntf-desc",
 "ntf-agent-test", "ntf-env", "ntf-human", "ntf-ai", "ntf-diff"].forEach(id =>
  assert(form.includes('id="' + id + '"'), "champ manquant : " + id));
assert(/<option value="feature" selected>/.test(form), "type feature non présélectionné");
assert(/<option value="normal" selected>/.test(form), "priorité normal non présélectionnée");
assert(/value="calyclay\/infra" checked/.test(form), "la cible du ticket n'est pas proposée");
assert(/rows="12"/.test(form), "la description doit être confortable (pleine page)");
console.log("✓ onglets centraux (RM2672) : temporaire unique, épinglage, fermeture, formulaire complet");

// — RM2718 : pastille du statut de session ([WIP] / [A TESTER] / [DONE]) —
const markPillHtml2718 = grabO("markPillHtml");
assert(/pill warn">WIP</.test(markPillHtml2718("wip")), "WIP : pastille d'attention");
assert(/pill test">À TESTER</.test(markPillHtml2718("test")), "test : pastille « À TESTER »");
assert(/pill ok">DONE</.test(markPillHtml2718("done")), "DONE : pastille ok");
assert.strictEqual(markPillHtml2718(null), "", "pas de marqueur → pas de pastille");
assert.strictEqual(markPillHtml2718("zzz"), "", "statut inconnu → rien d'inventé");
assert.strictEqual(markPillHtml2718("constructor"), "",
  "une clé héritée d'Object ne doit pas produire de pastille");
assert(markPillHtml2718("test").endsWith("</span> "),
  "la pastille garde son espace de séparation avec le titre");
console.log("✓ pastille de statut de session (RM2718) : trois statuts, rien d'inventé");

// — RM2719 : portée restreinte — les points d'un ticket, cochables avant envoi —
const bpPts = batchPlanHtml({ todo: [{ rm_id: "10", status: "a_faire", title: "dev",
  instruction: "traiter puis livrer", points: ["critère A", "critère B"] }], skipped: [] }, escO);
assert(/class="bp-point"/.test(bpPts), "les points du ticket sont rendus");
assert((bpPts.match(/type="checkbox" checked/g) || []).length === 2,
  "chaque point est coché par défaut : l'état de départ = ticket entier");
assert(/data-ref="10"/.test(bpPts), "chaque case porte le ticket auquel elle appartient");
assert(/value="critère A"/.test(bpPts), "la case porte le libellé exact du point (c'est lui qui part)");
assert(/aucun coché = ticket écarté/.test(bpPts),
  "la conséquence de tout décocher doit être écrite, pas devinée");
const bpNoPts = batchPlanHtml({ todo: [{ rm_id: "10", status: "a_faire", instruction: "traiter" }],
                                skipped: [] }, escO);
assert(!/bp-point/.test(bpNoPts), "un ticket sans critère ne rend aucune case (pas de bloc vide)");
const bpPtsXss = batchPlanHtml({ todo: [{ rm_id: "1", status: "a_faire",
  instruction: "x", points: ['<img src=x onerror=1> "guillemet"'] }], skipped: [] }, escO);
assert(!/<img/.test(bpPtsXss), "un libellé de critère est échappé dans le texte");
assert(!/value="[^"]*"guillemet/.test(bpPtsXss), "…et dans l'attribut value (sinon l'attribut se ferme)");
console.log("✓ portée restreinte d'un ticket (RM2719) : points cochables, échappés, conséquence écrite");
const bpTrunc = batchPlanHtml({ todo: [{ rm_id: "10", status: "a_faire", instruction: "traiter",
  points: ["critère A"], points_truncated: true }], skipped: [] }, escO);
assert(/liste de critères incomplète/.test(bpTrunc),
  "une liste de critères tronquée doit se dire : sinon elle se lit comme complète");
assert(!/liste de critères incomplète/.test(bpPts), "…et ne s'affiche pas quand elle est complète");
console.log("✓ portée restreinte (RM2719) : une liste de critères incomplète est annoncée");

// — RM2720 : les actions PM portent sur un TICKET, plus sur la session —
const pmActionTarget = grabO("pmActionTarget");
const SESS2720 = { "123": { rm_id: "123" }, "77": { rm_id: "77" }, "88": { rm_id: "88", ghost: true } };
const tOwn = pmActionTarget("123", SESS2720, "77");
assert.strictEqual(tOwn.sid, "123", "la session DU ticket est la cible naturelle");
assert.strictEqual(tOwn.own, true, "…et elle est signalée comme telle (pas de confirmation à demander)");
const tFallback = pmActionTarget("999", SESS2720, "77");
assert.strictEqual(tFallback.sid, "77", "sans session du ticket, repli sur la session attachée");
assert.strictEqual(tFallback.own, false, "…mais le repli n'est pas la session du ticket");
assert(/pas la session du ticket/.test(tFallback.why),
  "le repli doit être DIT : injecter une consigne ailleurs n'est pas neutre");
assert.strictEqual(pmActionTarget("999", SESS2720, null).sid, null,
  "sans session vivante : aucune cible (le bouton se désactive)");
assert(/aucune session/.test(pmActionTarget("999", SESS2720, null).why), "…avec sa raison");
assert.strictEqual(pmActionTarget("88", SESS2720, null).sid, null,
  "un fantôme (tuile grise, aucun processus) n'est pas une cible");
assert.strictEqual(pmActionTarget("999", {}, "77").sid, null,
  "une session attachée absente du cache n'est pas une cible");

// la barre de session ne rend plus les actions de ticket
const mChips = /function renderChips\(\)[\s\S]*?\n\}/.exec(html);
assert(mChips, "renderChips introuvable");
assert(/if \(a\.ticket_only\) continue;/.test(mChips[0]),
  "les actions ticket_only ne doivent plus être rendues au niveau session");
assert(!/isTicket/.test(mChips[0]),
  "plus de distinction session-ticket / session-slug dans la barre (elle n'a plus lieu d'être)");
// sendAction sait viser un ticket ET une session distincts
const mSend2720 = /async function sendAction\([\s\S]*?\n\}/.exec(html);
assert(mSend2720, "sendAction introuvable");
assert(/async function sendAction\(a, btn, id, sid\)/.test(mSend2720[0]),
  "sendAction doit distinguer le ticket visé de la session destinataire");
assert(/replaceAll\("\{id\}", rid\)/.test(mSend2720[0]), "{id} vaut le TICKET, plus la session");
console.log("✓ actions PM sur le ticket (RM2720) : cible résolue, repli annoncé, barre session nettoyée");

// — RM2720 : le second mode de lot se lit dans l'écran de confirmation —
const mModes = /const BATCH_MODES = (\{[\s\S]*?\n\});/.exec(html);
assert(mModes, "BATCH_MODES (cockpit) introuvable");
const MODES2720 = vm.runInNewContext("(" + mModes[1] + ")");
assert(MODES2720.atester && MODES2720.traiter, "deux modes de lot");
assert.notStrictEqual(MODES2720.atester.envoi, MODES2720.traiter.envoi,
  "le bouton d'envoi doit dire lequel des deux part");
assert.strictEqual(MODES2720.atester.points, false,
  "pas de portée par points en mode « à tester » : on ne livre pas la moitié d'un ticket");
console.log("✓ lot « à tester » (RM2720) : mode distinct, énoncé dans l'écran de confirmation");

// — RM2722 : badge d'anomalies du poste (contrôle de démarrage) —
const envWarnBadge = grabO("envWarnBadge");
assert.strictEqual(envWarnBadge({ items: [], count: 0, worst: "ok" }, escO), "",
  "poste sain : AUCUN badge (un indicateur permanent ne se lit plus)");
assert.strictEqual(envWarnBadge(null, escO), "", "données absentes tolérées");
const ewWarn = envWarnBadge({ worst: "warn", items: [
  { family: "SSH", label: "agent SSH", level: "warn", detail: "agent joignable mais VIDE" }] }, escO);
assert(/>🩺 1</.test(ewWarn), "le badge porte le NOMBRE d'anomalies");
assert(/pill ew-warn/.test(ewWarn), "niveau warn : couleur d'avertissement");
assert(/agent joignable mais VIDE/.test(ewWarn),
  "le survol dit QUOI — sans ça il faut ouvrir le panneau pour savoir quoi réparer");
const ewErr = envWarnBadge({ worst: "error", items: [
  { family: "Secrets", label: "vault-agentd", level: "error", detail: "socket absent" },
  { family: "SSH", label: "agent SSH", level: "warn", detail: "vide" }] }, escO);
assert(/pill ew-error/.test(ewErr), "une erreur l'emporte sur un avertissement");
assert(/>🩺 2</.test(ewErr), "…et les deux sont comptées");
const ewMany = envWarnBadge({ worst: "warn", items: Array.from({ length: 12 }, (_, i) =>
  ({ family: "Outils & dépendances", label: "outil" + i, level: "warn", detail: "absent" })) }, escO);
assert(/>🩺 12</.test(ewMany), "le compte reste exact même si le survol est tronqué");
assert(/et 4 autre\(s\)/.test(ewMany), "…et la troncature du survol est annoncée");
const ewXss = envWarnBadge({ worst: "warn", items: [
  { family: "SSH", label: '"><img src=x>', level: "warn", detail: "x" }] }, escO);
assert(!/<img/.test(ewXss), "le détail d'un check est échappé dans l'attribut title");
console.log("✓ badge d'anomalies du poste (RM2722) : silencieux si sain, compté, expliqué au survol");

// — RM2720 (suite) : écran de confirmation d'un lot de merges —
const mrBatchHtml = grabO("mrBatchHtml");
const PLAN_DEV = { mode: "dev", live: [], skipped: [], runs: [
  { rm_ids: ["10"], source: "10-x", target: "dev" },
  { rm_ids: ["11"], source: "11-y", target: "dev" }] };
const mbDev = mrBatchHtml(PLAN_DEV, escO);
assert(/10-x → dev/.test(mbDev), "chaque MR dit d'OÙ vers OÙ elle merge");
assert(!/promotion emporte/.test(mbDev), "pas d'avertissement de promotion sur un merge d'intégration");
const mbProd = mrBatchHtml({ mode: "prod", live: [], skipped: [],
  runs: [{ rm_ids: ["10", "11"], source: "dev", target: "main" }] }, escO);
assert(/emporte TOUT/.test(mbProd),
  "une promotion emporte plus que les tickets cochés : ça doit être écrit avant le clic");
assert(/dev → main/.test(mbProd), "…et la promotion dit sa source et sa cible");
const mbLive = mrBatchHtml({ mode: "dev", live: ["11"], skipped: [],
  runs: [{ rm_ids: ["11"], source: "11-y", target: "dev" }] }, escO);
assert(/session encore vivante/.test(mbLive) && /RM11/.test(mbLive),
  "merger sous les pieds d'un agent au travail doit se voir AVANT");
const mbSkip = mrBatchHtml({ mode: "dev", live: [], runs: [],
  skipped: [{ rm_id: "13", reason: "aucune branche au frontmatter" }] }, escO);
assert(/⊘ écartés \(1\)/.test(mbSkip) && /aucune branche/.test(mbSkip),
  "un ticket écarté porte sa raison");
assert(/rien à merger/.test(mbSkip), "un plan vide le dit");
assert(/à merger/.test(mrBatchHtml(null, escO)), "plan absent toléré");
const mbXss = mrBatchHtml({ mode: "dev", live: [], skipped: [],
  runs: [{ rm_ids: ["1"], source: "<img src=x>", target: "dev" }] }, escO);
assert(!/<img/.test(mbXss), "un nom de branche est échappé");
console.log("✓ lot de merges (RM2720) : cible dite, promotion avertie, session vivante signalée");

// — RM2723 : bouton « merger » sur chaque MR du worklog —
const mrOk = mrLineHtml({ iid: 571, ref: "RM2720", target: "dev",
  url: "https://gl.x/g/p/-/merge_requests/571" }, escO, jargFn);
assert(/!571/.test(mrOk) && /RM2720/.test(mrOk), "la ligne garde ce qu'elle disait");
assert(/⇥ merger<\/button>/.test(mrOk), "…et porte le bouton de merge");
assert(/onclick="mergeOneMr\('https:\/\/gl\.x\/g\/p\/-\/merge_requests\/571'/.test(mrOk),
  "la MR est désignée par son URL (un iid nu exigerait un dépôt — RM2541)");
assert(!/onclick="[^"]*"[^"]*"/.test(mrOk.replace(/title="[^"]*"/g, "")),
  "l'attribut onclick ne doit contenir aucun guillemet double non échappé");
assert(/ouvrir ↗/.test(mrOk), "le lien d'ouverture reste");
const mrNoUrl = mrLineHtml({ iid: 12, target: "dev" }, escO, jargFn);
assert(!/mergeOneMr/.test(mrNoUrl),
  "sans URL, pas de bouton : rien à quoi rattacher le merge");
assert(/!12/.test(mrNoUrl), "…mais la ligne s'affiche quand même");
const mrDead = mrLineHtml({ iid: 3, url: "https://gl.x/g/p/-/merge_requests/3", alive: false },
  escO, jargFn);
assert(/session éteinte/.test(mrDead), "l'état de la session qui l'a ouverte est conservé");
const mrXss = mrLineHtml({ iid: '<img src=x>', ref: '"><b>', target: "<i>",
  url: "https://gl.x/g/p/-/merge_requests/9" }, escO, jargFn);
// (la ligne contient un <b> légitime — on cherche les charges injectées)
assert(!/<img|<i>/.test(mrXss),
  "iid, ref et cible sont échappés — y compris dans l'argument onclick, où jarg "
  + "ne protège que du guillemet SIMPLE (l'attribut, lui, est en double)");
const mrQuote = mrLineHtml({ iid: 'a"b', url: "https://gl.x/a/b/-/merge_requests/1" }, escO, jargFn);
assert(!/onclick="mergeOneMr\([^"]*"[^"]*"/.test(mrQuote),
  "un guillemet double dans un libellé ne doit pas fermer l'attribut onclick");
assert(/⇥ merger/.test(mrLineHtml({ iid: 1, url: "https://gl.x/a/b/-/merge_requests/1" }, escO, jargFn)),
  "une MR sans cible connue reste mergeable");
console.log("✓ ligne de MR (RM2723) : rendu unique session+projet, merge à l'URL, pas de bouton sans URL");

// — RM2721 : « ⬆ MAJ dispo » doit se remarquer, et rester lisible sans animation —
// Le bouton vivait avec le style `.mini` de ses six voisins du header : rien ne le
// distinguait de « voix » ou « glossaire ». Deux niveaux exigés — un habillage
// permanent (--warn) ET une pulsation — le second étant désactivable.
const mUpd = /#updbtn \{([^}]*)\}/.exec(css);
assert(mUpd, "règle CSS #updbtn (RM2721) introuvable");
assert(/animation:\s*updpulse/.test(mUpd[1]), "#updbtn doit pulser (animation updpulse)");
for (const prop of ["color", "border-color", "background"]) {
  assert(new RegExp(prop + ":\\s*var\\(--warn").test(mUpd[1]),
    `#updbtn : ${prop} doit venir d'un token --warn* (jamais une couleur en dur)`);
}
assert(/@keyframes updpulse \{[\s\S]*?\}\s*\n\s*\}/.test(css), "@keyframes updpulse introuvable");
// pas de kblink ici : il fond à opacity .25, ce qui rend un bouton TEXTUEL
// illisible la moitié du temps — et celui-ci reste affiché tant que la MAJ n'est
// pas appliquée.
assert(!/animation:\s*kblink/.test(mUpd[1]), "#updbtn ne doit pas fondre en opacité (kblink)");
assert(!/opacity/.test(/@keyframes updpulse \{([\s\S]*?)\n  \}/.exec(css)[1]),
  "updpulse ne doit pas jouer sur l'opacité (le texte doit rester lisible)");
// mouvement réduit : l'animation tombe, l'habillage --warn reste (le bouton doit
// encore se distinguer sur une capture d'écran ou pour qui coupe les animations).
const mRm = /@media \(prefers-reduced-motion: reduce\) \{ #updbtn \{([^}]*)\}/.exec(css);
assert(mRm, "#updbtn : prefers-reduced-motion non respecté (RM2721)");
assert(/animation:\s*none/.test(mRm[1]), "mouvement réduit → animation: none");
// les tokens existent dans les DEUX thèmes (le test 10 verrouille déjà la parité,
// on vérifie ici qu'ils sont bien nés et pas juste référencés)
for (const t of ["--warn-soft", "--warn-soft-hover"]) {
  assert(dark.has(t) && light.has(t), `token ${t} manquant (dark et/ou light)`);
}
// et aucun autre `.mini` du header n'a été emporté au passage
assert(!/button\.mini \{[^}]*animation/.test(css), "aucune animation ne doit toucher tous les .mini");
console.log("✓ MAJ dispo (RM2721) : pulsation + habillage --warn permanent, mouvement réduit respecté");

// — RM2726 : la fiche du ticket dit où il est traité, et sait l'y lancer —
const ticketSessionsHtml = grabO("ticketSessionsHtml");
const taskPromptText = grabO("taskPromptText");

// formulation des prompts : une seule source pour le lanceur ET la fiche
assert.strictEqual(taskPromptText("traiter", "2726", "iprospective", "pm-ai-agents"),
  "traite la tâche RM2726 du client iprospective projet pm-ai-agents");
assert.strictEqual(taskPromptText("traiter", "2726", "", ""), "traite la tâche RM2726",
  "sans client/projet résolus, l'ancrage se réduit au RM-id");
assert.strictEqual(taskPromptText("traiter", "abc"), "", "un sid non numérique n'est pas un ticket");
assert.strictEqual(taskPromptText("zzz", "2726"), "", "template inconnu → aucune consigne inventée");
assert(/relis le \.log\.md/.test(taskPromptText("continuer", "2726")), "template continuer perdu");
assert(/SANS rien modifier/.test(taskPromptText("etat", "2726")),
  "l'état du ticket doit rester en lecture seule");

// aucune session : on le dit, et il reste le lancement
const tsNone = ticketSessionsHtml({ rm_id: "2726", handled: [], candidates: [],
                                    live: false, own_alive: false }, escFn, jargFn);
assert(/aucune session ne traite ce ticket/.test(tsNone), "l'absence de session doit être dite");
assert(/spawnTicketSession\('2726'/.test(tsNone), "le lancement d'une nouvelle session doit rester offert");
assert(!/disabled/.test(tsNone), "sans session d'ancrage vivante, le lancement n'est pas désactivé");
assert(/aucune autre session vivante/.test(tsNone), "sans destination, il faut le dire");

// sessions qui le traitent : source affichée, ouverture pour les vivantes seulement
const tsData = {
  rm_id: "2726", client: "iprospective", project: "pm-ai-agents", live: true, own_alive: true,
  handled: [
    { sid: "2726", alive: true, reasons: ["ancrage"], title: "[WIP] fiche", same_project: true },
    { sid: "vieille", alive: false, reasons: ["registre"], title: "hier", same_project: true },
  ],
  candidates: [
    { sid: "cockpit", alive: true, title: "cockpit", same_project: true,
      client: "iprospective", project: "pm-ai-agents" },
    { sid: "presta", alive: true, title: "presta", same_project: false,
      client: "acme", project: "boutique" },
  ],
};
const tsOut = ticketSessionsHtml(tsData, escFn, jargFn);
assert(/karl-RM2726/.test(tsOut) && /karl-vieille/.test(tsOut), "les sessions doivent être nommées");
assert(/ancrage/.test(tsOut) && /registre/.test(tsOut), "la source doit être affichée");
assert(/attach\('2726'\)/.test(tsOut), "une session vivante doit pouvoir s'ouvrir");
assert(!/attach\('vieille'\)/.test(tsOut), "une session éteinte n'a rien à ouvrir");
assert(/éteinte/.test(tsOut), "une session éteinte doit être dite telle");
assert(/disabled/.test(tsOut), "session d'ancrage vivante → pas de second /spawn (409)");
assert(/<optgroup label="iprospective\/pm-ai-agents">[\s\S]*cockpit/.test(tsOut),
  "les sessions du projet du ticket doivent être groupées en tête");
assert(tsOut.indexOf('label="iprospective/pm-ai-agents"') < tsOut.indexOf('label="autres projets"'),
  "le bon projet passe avant les autres");
assert(/acme\/boutique/.test(tsOut), "une session d'un autre projet doit annoncer lequel");
assert(/sendTicketToSession\('2726'/.test(tsOut), "l'envoi dans une session existante doit être offert");

// chargement : pas de liste vide trompeuse tant que la réponse n'est pas là
assert(/recherche des sessions/.test(ticketSessionsHtml(null, escFn, jargFn)),
  "avant réponse, on annonce la recherche — pas « aucune session »");

// échappement : le titre d'une session est libre (il vient d'un transcript)
const tsEsc = ticketSessionsHtml({ rm_id: "2726", handled: [
  { sid: "x", alive: true, reasons: ["worklog"], title: '<img src=x onerror=alert(1)>' }],
  candidates: [], live: true, own_alive: false }, escFn, jargFn);
assert(!/<img/.test(tsEsc) && /&lt;img/.test(tsEsc), "titre de session non échappé");
console.log("✓ sessions du ticket (RM2726) : source affichée, ouverture, envoi ciblé, lancement");

// — RM2726 : création de ticket — filtre client, puis radios des projets —
const projectRadiosHtml = grabFn("projectRadiosHtml");
const clientProjectPickerHtml = vm.runInNewContext("(" + grab("clientProjectPickerHtml") + ")",
  { Object, Array, Set, projectRadiosHtml });
const PROJ = [
  { client: "acme", project: "boutique" }, { client: "acme", project: "infra" },
  { client: "iprospective", project: "pm-ai-agents" }, { client: "vide", project: "" },
];
const pick2726 = clientProjectPickerHtml(PROJ, "acme", "infra", escFn);
assert(/id="ntf-client"/.test(pick2726) && /id="ntf-projects"/.test(pick2726), "filtre client + zone projets");
assert(/<option value="acme" selected>/.test(pick2726), "le client courant doit être sélectionné");
assert(/value="acme\/infra" checked/.test(pick2726), "le projet courant doit être coché");
assert(!/pm-ai-agents/.test(pick2726), "seuls les projets DU client filtré sont proposés");
assert(/onchange="ntfClientChanged\(\)"/.test(pick2726), "changer de client doit re-rendre les projets");

const pickDefault = clientProjectPickerHtml(PROJ, "inconnu", "", escFn);
assert(/<option value="acme" selected>/.test(pickDefault),
  "client inconnu → premier client, pas de sélection vide");
assert(/value="acme\/boutique" checked/.test(pickDefault),
  "aucun projet demandé → le premier du client est coché");
assert.strictEqual((pickDefault.match(/checked/g) || []).length, 1,
  "un seul projet coché à la fois");

assert(/aucun projet pour ce client/.test(projectRadiosHtml(PROJ, "vide", "", escFn)),
  "un client sans projet doit le dire (le formulaire refusera l'envoi)");
assert(/aucun projet connu/.test(clientProjectPickerHtml([], "", "", escFn)),
  "catalogue vide : on le dit plutôt que de rendre un choix fantôme");

const pickEsc = projectRadiosHtml([{ client: 'a"b', project: 'p"q' }], 'a"b', "", escFn);
assert(!/value="a"b/.test(pickEsc), "client/projet non échappés dans l'attribut value");
console.log("✓ création de ticket (RM2726) : filtre client, radios projet, défauts sûrs");
