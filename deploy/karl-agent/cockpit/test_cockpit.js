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
// autres clients attachés ne bouge pas (critère du ticket).
const mJump = /async function jumpTo\(it\) \{[\s\S]*?\n\}/.exec(html);
assert(mJump, "jumpTo introuvable");
const branche = /if \(outline\.source === "transcript"\) \{[\s\S]*?return;/.exec(mJump[0]);
assert(branche, "branche transcript de jumpTo introuvable");
assert(!/\/scroll/.test(branche[0]),
  "source transcript : aucun appel /scroll — la vue des autres clients ne doit pas bouger");
console.log("✓ outline (RM2549) : lecture ancrée dans le cockpit, sans piloter tmux");

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

console.log("OK — tous les tests cockpit passent");
