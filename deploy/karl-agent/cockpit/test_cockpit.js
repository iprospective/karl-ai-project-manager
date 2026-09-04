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

// — contrôle de flux (RM2807) : PAUSE tous les FLOW_LIMIT octets écrits —
// Sans lui, la file d'écriture d'xterm grossit sans borne sur un PTY qui
// débite plus vite que le rendu (OOM Firefox constaté : 3 Go à l'attach).
const ttydFlow = pick("ttydFlow");
let stFlow = { written: 0, pause: false };
stFlow = ttydFlow(stFlow.written, 40000, 100000);
assert.deepStrictEqual({ ...stFlow }, { written: 40000, pause: false }, "flux : sous le seuil, on cumule");
stFlow = ttydFlow(stFlow.written, 59999, 100000);
assert.deepStrictEqual({ ...stFlow }, { written: 99999, pause: false }, "flux : toujours sous le seuil");
stFlow = ttydFlow(stFlow.written, 1, 100000);
assert.deepStrictEqual({ ...stFlow }, { written: 0, pause: true }, "flux : seuil atteint → PAUSE + compteur remis");
assert.deepStrictEqual({ ...ttydFlow(0, 250000, 100000) }, { written: 0, pause: true },
  "flux : un seul message énorme déclenche aussi la PAUSE");
// le client émet réellement les trames PAUSE/RESUME et le RESUME attend le drain
assert(/send\(FRAME_PAUSE\)/.test(termSrc), "la trame PAUSE ('2') est émise");
assert(/if \(flowPending === 0\) send\(FRAME_RESUME\)/.test(termSrc),
  "la trame RESUME ('3') n'est émise qu'une fois la file d'xterm drainée (callback write)");
assert(/flowWritten = 0; flowPending = 0;/.test(termSrc),
  "l'état de flux repart à zéro sur une nouvelle socket (reconnexion)");
console.log("✓ contrôle de flux ttyd (RM2807) : PAUSE au seuil, RESUME au drain");

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

// RM2952 : l'état porte désormais `manual` — le repli VOULU, distinct du repli
// par défaut. Les états attendus le disent tous explicitement.
const replie = { tab: "outline", collapsed: true, manual: false };
const ouvert = { tab: "outline", collapsed: false, manual: false };
assert.deepStrictEqual(rightPanelReduce(replie, { type: "select", tab: "tickets" }),
  { tab: "tickets", collapsed: false, manual: false }, "replié : sélectionner un onglet déplie dessus");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "select", tab: "tickets" }),
  { tab: "tickets", collapsed: false, manual: false }, "ouvert : changer d'onglet ne replie pas");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "select", tab: "outline" }),
  { tab: "outline", collapsed: true, manual: true }, "ouvert : re-sélectionner l'onglet actif replie");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "show" }),
  ouvert, "show sans onglet : déplie sans arracher l'onglet courant");
assert.deepStrictEqual(rightPanelReduce({ tab: "outline", collapsed: true }, { type: "show" }),
  ouvert, "show sans onglet depuis replié : déplie sur l'onglet mémorisé");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "show", tab: "tickets" }),
  { tab: "tickets", collapsed: false, manual: false }, "show ciblé : l'onglet demandé passe devant");
assert.deepStrictEqual(rightPanelReduce({ tab: "tickets", collapsed: false }, { type: "collapse" }),
  { tab: "tickets", collapsed: true, manual: false }, "collapse garde l'onglet en mémoire");
assert.deepStrictEqual(rightPanelReduce(replie, { type: "toggle" }), ouvert, "toggle déplie");
assert.deepStrictEqual(rightPanelReduce(ouvert, { type: "toggle" }),
  { tab: "outline", collapsed: true, manual: true }, "toggle replie");

// RM2952 — le repli VOULU tient tête aux ouvertures automatiques. Attacher une
// session déplie la colonne (`show` sans onglet), et cela arrive tout seul :
// après un spawn, une relance, au rechargement. Un panneau replié à la main se
// rouvrait donc sans cesse — le bouton de repli paraissait inopérant.
const repliVoulu = { tab: "outline", collapsed: true, manual: true };
assert.deepStrictEqual(rightPanelReduce(repliVoulu, { type: "show" }), repliVoulu,
  "repli voulu : une ouverture automatique (attache) ne le défait pas");
assert.deepStrictEqual(rightPanelReduce(repliVoulu, { type: "show", tab: "tickets" }),
  { tab: "tickets", collapsed: false, manual: false },
  "repli voulu : mais une demande CIBLÉE (ce ticket, ce fichier) déplie");
assert.deepStrictEqual(rightPanelReduce(repliVoulu, { type: "toggle" }),
  { tab: "outline", collapsed: false, manual: false },
  "repli voulu : le rouvrir à la main lève la consigne");
assert.deepStrictEqual(rightPanelReduce(repliVoulu, { type: "collapse" }), repliVoulu,
  "un repli automatique (plus de session) ne décide rien à la place de l'opérateur");
assert.deepStrictEqual(rightPanelReduce(replie, { type: "show" }), ouvert,
  "replié par DÉFAUT (jamais touché) : l'attache déplie comme avant");

// RM2579 : trois onglets, défaut « infos », migration de l'ancien « meta »
assert.deepStrictEqual(rightPanelReduce(null, {}), { tab: "infos", collapsed: true, manual: false },
  "état absent → replié sur infos (défaut RM2579)");
assert.deepStrictEqual(rightPanelReduce({ tab: "meta", collapsed: false }, {}),
  { tab: "infos", collapsed: false, manual: false }, "legacy « meta » (ancien localStorage) → infos");
assert.deepStrictEqual(rightPanelReduce({ tab: "meta", collapsed: true }, { type: "show" }),
  { tab: "infos", collapsed: false, manual: false }, "legacy « meta » migré aussi via show");
assert.deepStrictEqual(rightPanelReduce({ tab: "zzz" }, {}), { tab: "infos", collapsed: true, manual: false },
  "onglet inconnu → infos");
// « state » (🗒 état, RM2466 volet 2 mergé en parallèle) est un onglet VALIDE :
// il ne doit PAS être normalisé vers infos (régression corrigée).
assert.deepStrictEqual(rightPanelReduce({ tab: "state", collapsed: false }, {}),
  { tab: "state", collapsed: false, manual: false }, "onglet state préservé (pas de normalisation)");
assert.deepStrictEqual(rightPanelReduce({ tab: "files", collapsed: false }, {}),
  { tab: "files", collapsed: false, manual: false }, "onglet files (RM2586) est un onglet valide");
assert.deepStrictEqual(rightPanelReduce(replie, { type: "select", tab: "state" }),
  { tab: "state", collapsed: false, manual: false }, "select state : déplie sur état");
console.log("✓ colonnes (RM2466/2579/2952) : 4 onglets, défaut infos, legacy meta→infos, repli voulu respecté");

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
// RM2860 : la MEP est un travail d'une autre nature (dev fini, reste la mise en
// prod) — son propre onglet, entre ce qui reste à écrire et ce qui est fait.
const secsMep = worklogSections({ todo: [{ ref: "RM1" }], mep: [{ ref: "RM2" }, { ref: "RM3" }], done: [{ ref: "RM4" }] });
assert.deepStrictEqual(Array.from(secsMep.map(s => s.key)), ["todo", "mep", "done"],
  "l'onglet MEP se place après « reste à faire » et avant « fait »");
assert.strictEqual(secsMep.filter(s => s.key === "mep")[0].items.length, 2,
  "les tickets a_mep/en_mep sont dans la section MEP");
assert.strictEqual(worklogSections({ mep: [] }).length, 0,
  "pas de MEP en cours → pas d'onglet MEP (règle des sections vides)");
// RM2930 : « à tester / valider » n'est pas une attente mais une action, et elle
// PRÉCÈDE la MEP dans le flow — d'où sa place entre « reste à faire » et la MEP.
const secsTest = worklogSections({
  todo: [{ ref: "RM1" }], testing: [{ ref: "RM2" }, { ref: "RM3" }],
  mep: [{ ref: "RM4" }], waiting: [{ ref: "RM5" }], done: [{ ref: "RM6" }] });
assert.deepStrictEqual(Array.from(secsTest.map(s => s.key)),
  ["todo", "testing", "mep", "waiting", "done"],
  "« à tester / valider » se place après « reste à faire » et avant la MEP");
assert.strictEqual(secsTest.filter(s => s.key === "testing")[0].items.length, 2,
  "les tickets à tester/valider sont dans leur propre section");
assert.strictEqual(worklogSections({ testing: [] }).length, 0,
  "rien à tester → pas de section (règle des sections vides)");
assert(secs.every(s => s.icon && s.label), "chaque section porte une icône ET un libellé");
assert.strictEqual(worklogSections({ todo: [], waiting: [{ ref: "RM2" }], done: [] }).length, 1,
  "les sections vides disparaissent (pas de titre sans contenu)");
assert.strictEqual(worklogSections({}).length, 0, "worklog vide → aucune section");
assert.strictEqual(worklogSections(null).length, 0, "worklog absent toléré");
assert.strictEqual(worklogSections(undefined).length, 0, "buckets absents tolérés");
console.log("✓ état (RM2466) : worklog en sections, vides masquées");

// la dérive doit rester visible : sans elle on croirait que le statut affiché
// est le fait de la session courante, alors qu'une autre l'a fait avancer
// RM2796 : le signal a changé de FORME (une pastille jaune + infobulle, au lieu
// d'une seconde pastille), pas de nature — il doit toujours exister.
const mRw = /function renderWorklog\(\) \{[\s\S]*?\n\}/.exec(html);
assert(mRw, "renderWorklog introuvable");
assert(/statusPill\(it, esc\)/.test(mRw[0]),
  "un statut modifié hors de la session doit être signalé comme tel");
assert(/item\.drifted/.test(html) && /opened_status/.test(html),
  "…et la dérive doit rester lue depuis les données du worklog");
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

// — sinceLabel (RM2630) : dater la version de ticket affichée —
const fSl = />>> sinceLabel[\s\S]*?(function sinceLabel[\s\S]*?)\n\/\/ <<< sinceLabel/.exec(html);
assert(fSl, "marqueurs >>> sinceLabel / <<< sinceLabel introuvables");
const sinceLabel = vm.runInNewContext("(" + fSl[1] + ")", {});
const t0 = Date.parse("2026-08-11T12:00");
assert.strictEqual(sinceLabel("2026-08-11T12:00", t0), "à l'instant", "même minute");
assert.strictEqual(sinceLabel("2026-08-11T11:43", t0), "il y a 17 min", "minutes");
assert.strictEqual(sinceLabel("2026-08-11T09:00", t0), "il y a 3 h", "heures");
assert.strictEqual(sinceLabel("2026-08-09T12:00", t0), "il y a 2 j", "jours");
assert.strictEqual(sinceLabel("2026-08-11 11:00", t0), "il y a 1 h", "espace accepté à la place du T");
assert.strictEqual(sinceLabel("", t0), "", "horodatage absent → pas de mention");
assert.strictEqual(sinceLabel("pas une date", t0), "", "horodatage illisible → pas de mention");
console.log("✓ sinceLabel (RM2630) : âge de la version affichée, dégrade en silence");

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

// — worklogDocsHtml (RM2935) : documents du worklog cliquables —
// Les 5 formes réellement rencontrées dans `refs:`/`outputs:` des fiches (RM2352).
const worklogDocsHtml = grabO("worklogDocsHtml");
const wdh = worklogDocsHtml([
  { ref: "RM2890", name: "docs/cdc-rm2890-timesheet-heures-humaines.md", kind: "output" },
  { ref: "RM2890", name: "scripts/karl-agent.py (/approve-all, boucle)", kind: "output" },
  { ref: "RM2890", name: "https://gitlab.iprospective.fr/x/-/merge_requests/757", kind: "output" },
  { ref: "RM2890", name: "'memory: feedback_mmi_pm_skill_naming.md'", kind: "ref" },
  { ref: "hors-ticket", name: "commit sur la branche 2353-x", kind: "" },
], escO, linkify);
assert(/onclick="openFileRef\('docs\/cdc-rm2890-timesheet-heures-humaines.md'\)"/.test(wdh),
  "chemin de document → onglet Fichiers");
assert(/onclick="openFileRef\('scripts\/karl-agent.py'\)"/.test(wdh),
  "chemin suivi d'un commentaire : seul le chemin est cliquable");
assert(/<a href="https:\/\/gitlab.iprospective.fr\/x\/-\/merge_requests\/757"/.test(wdh),
  "URL de MR → lien externe");
assert(/onclick="showTicket\(2890\)"/.test(wdh), "l'en-tête de groupe ouvre la fiche du ticket");
assert(!/cursor:default/.test(wdh), "plus de cursor:default sur la ligne de document");
assert(/memory: feedback_mmi_pm_skill_naming.md/.test(wdh) && !/'memory:/.test(wdh),
  "quotes YAML retirées à l'affichage");
assert(/>hors-ticket</.test(wdh) && !/showTicket\(hors/.test(wdh),
  "une référence non-RM reste du texte, sans onclick bancal");
assert(/<span class="pill">output<\/span>/.test(wdh), "le kind reste affiché en pastille");
// anti-XSS : linkify échappe, on ne doit pas ré-échapper ni laisser passer de balise
const wdhX = worklogDocsHtml([{ ref: "<b>x</b>", name: '<img src=x onerror="alert(1)">', kind: "<i>" }],
  escO, linkify);
assert(!/<img/.test(wdhX) && !/<b>x<\/b>/.test(wdhX) && !/<i>/.test(wdhX),
  "nom, ref et kind hostiles restent inertes");
assert(!/&amp;lt;/.test(wdhX), "pas de double échappement (linkify échappe déjà)");
assert.strictEqual(worklogDocsHtml([], escO, linkify), "", "liste vide → chaîne vide (le rendu bascule sur son message)");
assert.strictEqual(worklogDocsHtml(null, escO, linkify), "", "liste absente tolérée");
console.log("✓ worklogDocsHtml (RM2935) : documents du worklog cliquables et sûrs");

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

// — setEditOptions (RM2955) : la carte « Sessions enregistrées » règle N'IMPORTE
//   quel jeu, sans déplacer le jeu courant. Le sélecteur doit donc dire lequel
//   gouverne encore l'affichage et reçoit les écritures automatiques.
const fSeo = />>> setEditOptions[\s\S]*?(function setEditOptions[\s\S]*?)\n\/\/ <<< setEditOptions/.exec(html);
assert(fSeo, "marqueurs setEditOptions introuvables");
const setEditOptions = vm.runInNewContext("(" + fSeo[1] + ")");
const SETS_2955 = [
  { name: "default", label: "sessions actives", count: 12, alive: 5 },
  { name: "pm", label: "PM", count: 3, alive: 1, derived: true },
  { name: "nuit", count: 0, alive: 0 },
];
let opts = setEditOptions(SETS_2955, null, "pm");
assert.deepStrictEqual(opts.map(o => o.value), ["default", "pm", "nuit"],
  "tous les jeux sont proposés, dans leur ordre");
assert.strictEqual(opts.find(o => o.value === "pm").selected, true,
  "sans choix explicite, la carte suit le jeu courant");
assert(opts.find(o => o.value === "pm").label.includes("● courant"),
  "le jeu courant est marqué comme tel");
assert(opts.find(o => o.value === "pm").label.startsWith("⚙ "),
  "un jeu dérivé se signale : on y règle une règle, pas un contenu");
assert(!opts.find(o => o.value === "default").label.includes("● courant"),
  "les autres jeux ne portent pas la marque");
assert.strictEqual(opts.find(o => o.value === "default").label, "sessions actives (5/12)",
  "libellé + ouvertes/enregistrées");
assert.strictEqual(setEditOptions(SETS_2955, "nuit", "pm").find(o => o.selected).value, "nuit",
  "un choix explicite l'emporte sur le jeu courant");
assert(setEditOptions(SETS_2955, "nuit", "pm").find(o => o.value === "pm").label.includes("● courant"),
  "…et le jeu courant reste signalé, il n'a pas bougé");
assert.strictEqual(setEditOptions(null, null, "pm").length, 0, "aucun jeu : aucune option");
assert.strictEqual(setEditOptions([{ name: "x" }], null, "pm")[0].label, "x (0/0)",
  "jeu sans libellé ni compteurs : le slug et des zéros, jamais « undefined »");
console.log("\u2713 setEditOptions (RM2955) : la carte règle tout jeu, le courant reste signalé");

// — RM2952 : la largeur RÉGLÉE prime sur le confort par défaut —
// `max(--rpanel-w, 460px)` imposait un plancher de 460 px sur l'onglet
// conversation : la poignée ne réduisait plus rien en dessous, et le réglage
// passait pour cassé. Le défaut de 460 px vit désormais dans le `var()`.
assert(/\.rpanel\.wide \{ width: var\(--rpanel-w, 460px\); \}/.test(html),
  "onglet conversation : 460px en DÉFAUT de --rpanel-w, jamais en plancher");
assert(!/\.rpanel\.wide \{ width: max\(/.test(html),
  "plus de max() : il rendait la poignée inopérante sous 460px");
assert(/function rResetWidth\(\)[\s\S]*?removeProperty\("--rpanel-w"\)/.test(html),
  "réinitialiser RETIRE la largeur (sinon 330px figerait aussi l'onglet conversation)");
assert(!/function rResetWidth\(\)[\s\S]*?setRightWidth\(R_WIDTH_DEFAULT\)/.test(html),
  "réinitialiser n'écrit plus 330px en dur");
console.log("\u2713 largeur du panneau (RM2952) : le réglage prime, le défaut reste un défaut");

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
// RM2799 : classe propre au numéro (le curseur vient du CSS `.rmref`) — il ne
// partage plus `.pill` avec le statut, qui l'écrasait dès qu'il virait au jaune.
assert(/class="rmref"/.test(lien), "et SE VOIT comme cliquable");
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

// RM2883 : familles de statut — le filtre de la carte les propose
const ticketStatusFamily = vm.runInNewContext("(" + grab("ticketStatusFamily") + ")");
const statusFamilyTabs = vm.runInNewContext("(" + grab("statusFamilyTabs") + ")",
  { ticketStatusFamily });
// groupOpenedTickets appelle ticketStatusRank : le contexte isolé doit l'avoir
const groupOpenedTickets = vm.runInNewContext("(" + grab("groupOpenedTickets") + ")",
  { ticketStatusRank, ticketStatusFamily, statusFamilyTabs });
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

// — RM2883 : filtre par statut dans la carte des tickets ouverts —
// Aucun statut connu ne doit tomber dans « autre » : un statut ajouté un jour au
// classement d'affichage sans famille disparaîtrait du filtre en silence.
const statutsConnus = ["nouveau", "a_etudier_chiffrer", "etude_chiffrage_en_cours",
  "etude_chiffrage_a_valider", "a_faire", "en_cours", "a_tester_dev",
  "a_tester_demandeur", "a_mep", "en_mep", "en_pause", "a_corriger", "ferme"];
for (const st of statutsConnus)
  assert.notStrictEqual(ticketStatusFamily(st), "autre",
    "statut NORMS sans famille : « " + st + " » (il disparaîtrait du filtre)");
assert.strictEqual(ticketStatusFamily("statut_exotique"), "autre",
  "un statut inconnu a sa propre famille — jamais rangé d'office dans « à faire »");
assert.strictEqual(ticketStatusFamily("a_mep"), "mep",
  "à MEP n'est pas « à faire » : le dev y est fini (même distinction qu'au worklog, RM2860)");
assert.strictEqual(ticketStatusFamily("a_corriger"), "todo",
  "ce qui revient corrigé est du travail à faire");

// Seules les familles présentes ont un bouton — la colonne est étroite.
const tabs2883 = statusFamilyTabs([{ status: "en_cours" }, { status: "en_cours" },
                                   { status: "ferme" }]);
assert.strictEqual(JSON.stringify(tabs2883.map(t => [t.key, t.n])),
  JSON.stringify([["encours", 2], ["ferme", 1]]),
  "un bouton par famille présente, avec son compte");
assert.strictEqual(statusFamilyTabs([]).length, 0, "liste vide → aucun filtre proposé");
assert.strictEqual(tabs2883[0].key, "encours",
  "ordre de lecture : ce qui réclame une action avant ce qui est clos");

// Le filtre statut se cumule avec le filtre client…
const fs2883 = groupOpenedTickets(["1", "2", "3"], tkCache, null, "encours");
assert.deepStrictEqual(Array.from(fs2883.keys), ["acme/shop"], "le filtre statut réduit la liste");
assert.deepStrictEqual(Array.from(fs2883.groups.get("acme/shop").map(x => x.rm_id)), ["2"],
  "…et ne garde que les tickets de la famille");
// …mais les autres familles restent proposées, sinon on ne pourrait plus changer
// de filtre sans repasser par « tous ».
assert(fs2883.families.length > 1,
  "les familles proposées se calculent AVANT le filtre statut");
assert.deepStrictEqual(Array.from(groupOpenedTickets(["1"], tkCache, null, "encours").keys), [],
  "un filtre qui ne laisse rien rend une liste vide (le rendu le dit)");
assert(/aucun ticket dans ce filtre/.test(html),
  "…et l'interface l'annonce plutôt que de paraître vidée");

console.log("✓ tickets ouverts (RM2883) : filtre par statut, cumulable, familles présentes seules");

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
// RM2860 : l'onglet MEP se fabrique comme les autres — un bucket non vide en
// donne un, avec son compte.
const tabsMep = worklogTabList([{ key: "todo", icon: "\u23f3", label: "reste a faire", items: [1] },
                                { key: "mep", icon: "\ud83d\ude80", label: "a mettre en prod", items: [1, 2] }], 0, 0);
assert.strictEqual(JSON.stringify(tabsMep.map(t => [t.key, t.n])),
  JSON.stringify([["todo", 1], ["mep", 2]]), "onglet MEP avec son compte");
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
// RM2860 : le bucket MEP est une NOUVELLE clé — oubliée ici, elle ferait
// disparaître de l'onglet « tickets » les tickets dont le dev est fini.
assert.deepStrictEqual([...ticketsOfSession("calymix", null, { mep: [{ ref: "RM2860" }] })], ["2860"],
  "un ticket à mettre en prod reste un ticket de la session");
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
const upsertTab = grabFn("upsertTab"), closeTabAt = grabFn("closeTabAt");
// RM2775 : le rendu délègue l'infobulle à `tabTooltip` — on l'injecte dans son
// contexte isolé, sinon le rendu lève dès le premier onglet.
const renderCenterTabs = vm.runInNewContext("(" + grab("renderCenterTabs") + ")",
  { Object, tabTooltip: grabFn("tabTooltip") });
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
// RM2873 : le bloc de lancement rend aussi le choix de consigne — la fonction
// pure qui liste les modèles lui est injectée (elle est partagée avec le
// lanceur de gauche).
const promptTemplates = grabO("promptTemplates");
const promptTemplateOptions = grabO("promptTemplateOptions", { promptTemplates });
const ticketPromptFor = grabO("ticketPromptFor");
const promptFillOnChange = grabO("promptFillOnChange");
const ticketSessionsHtml = grabO("ticketSessionsHtml", { promptTemplateOptions });
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

// — RM2741 : barre du panneau « en cours » — relancer pertinent, création unifiée —
const relaunchBtnState = grabO("relaunchBtnState");
const newSetPlan = grabO("newSetPlan", { Object });
const ruleFormHtml2741 = grabO("ruleFormHtml", { esc: escFn, setFacets: { clients: [] }, Set });

const SET = { exists: true, count: 4, entries: [
  { sid: "1", alive: true }, { sid: "2", alive: false },
  { sid: "3", alive: false }, { sid: "4", alive: true }] };

assert.deepEqual(relaunchBtnState(SET, "set"), { show: true, count: 2 },
  "le compteur doit être celui des sessions ÉTEINTES, pas du jeu entier");
assert.strictEqual(relaunchBtnState(SET, "live").show, false,
  "vue « sessions ouvertes » : rien à relancer, le bouton n'a pas à s'y trouver");
assert.strictEqual(relaunchBtnState(SET, "all").show, false,
  "vue « tous les jeux » : l'affichage n'est pas le jeu, le geste écrirait ailleurs");
assert.strictEqual(relaunchBtnState(SET, "client:acme").show, false,
  "vue par client : idem, l'affichage n'est pas le jeu");
assert.strictEqual(relaunchBtnState(
  { exists: true, count: 2, entries: [{ alive: true }, { alive: true }] }, "set").show, false,
  "tout tourne déjà → rien à relancer");
assert.strictEqual(relaunchBtnState({ exists: false }, "set").show, false, "pas de jeu → pas de bouton");
assert.deepEqual(relaunchBtnState({ exists: true, count: 3 }, "set"), { show: true, count: 3 },
  "payload sans entries : on retombe sur le total plutôt que de masquer un geste utile");

// création unifiée : la nature se déduit des critères
const EXIST = ["default", "pm"];
const manual = newSetPlan("chantier", "Chantier", {}, ["1", "2"], true, EXIST);
assert.strictEqual(manual.kind, "manual", "aucun critère → jeu manuel");
assert.deepEqual(manual.body, { group: "chantier", label: "Chantier", sids: ["1", "2"] });
assert.strictEqual(manual.note, "", "rien d'ignoré ici, rien à signaler");

const emptySet2741 = newSetPlan("chantier", "Chantier", {}, ["1"], false, EXIST);
assert.deepEqual(emptySet2741.body, { group: "chantier", label: "Chantier" },
  "case décochée → jeu vide, aucune session versée");

const derived = newSetPlan("acme", "Acme", { client: "acme" }, ["1", "2"], true, EXIST);
assert.strictEqual(derived.kind, "derived", "un critère → jeu dérivé");
assert.deepEqual(derived.body, { group: "acme", label: "Acme", rule: { client: "acme" } },
  "un jeu dérivé ne reçoit PAS de sids : son contenu se calcule");
assert(/pas versées/.test(derived.note),
  "la case cochée mais sans effet doit être signalée, pas ignorée en silence");

assert.strictEqual(newSetPlan("pm", "PM", {}, [], false, EXIST).ok, false, "nom déjà pris");
assert(/existe déjà/.test(newSetPlan("pm", "PM", {}, [], false, EXIST).error));
assert.strictEqual(newSetPlan("x", "", {}, [], false, EXIST).ok, false, "nom vide refusé");
assert.strictEqual(newSetPlan("", "###", {}, [], false, EXIST).ok, false, "nom inexploitable refusé");

// le formulaire de création porte le nom, la case de peuplement et les critères
const fNew = ruleFormHtml2741({}, true, 5);
assert(/id="rf-name"/.test(fNew) && /id="rf-seed"/.test(fNew), "nom + peuplement attendus");
assert(/5 session\(s\) affichée\(s\)/.test(fNew), "le nombre de sessions affichées doit être dit");
assert(/checked/.test(fNew), "la case de peuplement est cochée par défaut");
assert(/manuel/.test(fNew) && /dérivé/.test(fNew), "les deux natures doivent être expliquées");
assert(!/id="rf-seed"/.test(ruleFormHtml2741({}, true, 0)),
  "sans session affichée, pas de case à cocher sans objet");
const fEdit = ruleFormHtml2741({ client: "acme" }, false, 5);
assert(!/id="rf-name"/.test(fEdit) && !/id="rf-seed"/.test(fEdit),
  "édition d'une règle existante : ni nom ni peuplement");
console.log("✓ barre des jeux (RM2741) : relancer restreint et compté, création unifiée");

// — RM2744 : tableau de bord — contenu atteignable, onglet permanent —
const ensureDashTab = grabO("ensureDashTab");

// l'onglet est toujours là, toujours en tête, jamais en double
let dtabs = ensureDashTab([]);
assert.equal(dtabs.length, 1, "l'onglet du tableau de bord doit exister même sans rien d'ouvert");
assert.equal(dtabs[0].kind, "dash");
assert(dtabs[0].pinned && dtabs[0].fixed, "il est épinglé et permanent");
dtabs = ensureDashTab([{ kind: "review", key: "2744", label: "RM2744", pinned: true },
                       { kind: "dash", key: "", label: "vieux libellé", pinned: true, fixed: true }]);
assert.equal(dtabs.length, 2, "pas de doublon après restauration du localStorage");
assert.equal(dtabs[0].kind, "dash", "il revient en tête");
assert.equal(dtabs[0].label, "tableau de bord", "son libellé est celui du code, pas celui du storage");
assert.equal(dtabs[1].kind, "review", "les autres onglets sont conservés dans l'ordre");

// il ne se ferme pas — et reste la destination de la fermeture des autres
const closeTabAt2744 = grabFn("closeTabAt");
const withDash = ensureDashTab([{ kind: "review", key: "2744", label: "RM2744", pinned: true }]);
const kept = closeTabAt2744(withDash, "dash:", "dash:");
assert.equal(kept.tabs.length, 2, "fermer l'onglet permanent ne doit rien fermer");
assert.equal(kept.active, "dash:", "et ne change pas l'onglet actif");
const after = closeTabAt2744(withDash, "review:2744", "review:2744");
assert.deepEqual(after.tabs.map(t => t.kind), ["dash"], "le dernier autre onglet se ferme");
assert.equal(after.active, "dash:", "on retombe sur le tableau de bord, jamais sur rien");

// rendu : icône, ni croix ni épingle sur l'onglet permanent
const dashHtml = renderCenterTabs(withDash, "dash:", escFn, jargFn);
assert(/📊/.test(dashHtml), "icône du tableau de bord attendue");
assert(!/closeTab\('dash:'\)/.test(dashHtml), "l'onglet permanent ne doit pas offrir de croix");
assert(!/togglePin\('dash:'\)/.test(dashHtml), "ni d'épingle");
assert(/closeTab\('review:2744'\)/.test(dashHtml), "les autres onglets gardent leur croix");
assert(/activateTab\('dash:'\)/.test(dashHtml), "cliquer l'onglet doit rouvrir le tableau de bord");
assert(/tableau de bord — toujours là/.test(dashHtml), "son infobulle doit dire qu'il est permanent");

// le correctif d'affichage : la colonne doit pouvoir contraindre son enfant
// scrollable (min-height:0), et le centrage ne doit pas manger le haut
assert(/\.termarea \{[^}]*min-height: 0/.test(html),
  "sans min-height:0 sur la colonne, l'enfant en overflow-y:auto ne défile pas : il déborde");
const phCss = /\.placeholder \{[^}]*\}/.exec(html)[0];
assert(/justify-content: safe center/.test(phCss),
  "un conteneur qui défile ET centre coupe le haut de son contenu : centrage sûr attendu");
assert(/\.placeholder\.dash-on \{[^}]*justify-content: flex-start/.test(html),
  "ceinture : le tableau de bord rendu aligne en haut, même sans support de `safe`");
assert(/ph\.classList\.add\("dash-on"\)/.test(html) && /ph\.classList\.remove\("dash-on"\)/.test(html),
  "la classe doit être posée ET retirée par le rendu du tableau de bord");
console.log("✓ tableau de bord (RM2744) : contenu atteignable, onglet permanent non fermable");

// — RM2748 : verrous du poste (coffre + agent SSH) —
const vaultBtnState = grabFn("vaultBtnState");
const vaultFormHtml = vm.runInNewContext("(" + grab("vaultFormHtml") + ")",
  { Object, esc: escFn });

assert.equal(vaultBtnState(null).show, false, "sans état connu, pas de bouton");
assert.equal(vaultBtnState({ daemon: true, locked: [], ssh: { keys: [{ comment: "k" }] } }).show,
  false, "tout ouvert : le bouton ne doit PAS s'afficher");
const oneLocked = vaultBtnState({ daemon: true, locked: ["vw-ipro"], ssh: { keys: [{ comment: "k" }] } });
assert(oneLocked.show, "un coffre verrouillé → bouton visible");
assert(/vw-ipro/.test(oneLocked.title), "l'infobulle nomme le coffre concerné");
assert(!/agent SSH/.test(oneLocked.title), "elle ne parle pas d'un problème qui n'existe pas");
const both = vaultBtnState({ daemon: false, locked: ["a", "b"], ssh: { keys: [] } });
assert(/coffre fermé/.test(both.title) && /agent SSH vide/.test(both.title),
  "les deux causes sont annoncées, pas seulement la première");
assert(/2 coffres/.test(vaultBtnState({ daemon: true, locked: ["a", "b"], ssh: { keys: [{}] } }).title),
  "plusieurs coffres : on compte au lieu de tout énumérer");

// contexte non sécurisé : AUCUN champ de mot de passe n'est proposé
const vltInsecure = vaultFormHtml({ daemon: true, locked: ["vw-ipro"], ssh: {} }, false);
assert(!/type="password"/.test(vltInsecure), "jamais de saisie de secret hors contexte sécurisé");
assert(/https/.test(vltInsecure), "et l'on dit quoi faire pour y remédier");

const vltForm = vaultFormHtml({
  daemon: true, default_instance: "vw-ipro", locked: ["vw-ipro"],
  instances: [{ slug: "vw-ipro", unlocked: false }, { slug: "kp-client", unlocked: true, since: "2026-08-20T10:00" }],
  ssh: { reachable: true, keys: [], candidates: ["id_rsa_root", "id_ed25519_gitlab"] },
}, true);
assert(/id="vlt-pass"/.test(vltForm) && /type="password"/.test(vltForm), "champ mot de passe attendu");
assert(/vaultUnlock\(this\)/.test(vltForm), "bouton de déverrouillage câblé");
assert(/id="vlt-inst"/.test(vltForm), "l'instance visée est transmise explicitement");
assert(/kp-client/.test(vltForm) && /2026-08-20T10:00/.test(vltForm), "l'état de chaque coffre est montré");
assert(/id="vlt-key"/.test(vltForm) && /id_rsa_root/.test(vltForm), "les clés chargeables sont proposées");
assert(/vaultSshAdd\(this\)/.test(vltForm), "bouton de chargement de clé câblé");
assert(!/value="[^"]*mot de passe/.test(vltForm), "aucun secret pré-rempli");

// tout est ouvert : le formulaire ne redemande rien
const vltOpen = vaultFormHtml({
  daemon: true, locked: [], instances: [{ slug: "vw-ipro", unlocked: true }],
  ssh: { reachable: true, keys: [{ comment: "root@web-12", type: "RSA", bits: "4096" }], candidates: [] },
}, true);
assert(!/type="password"/.test(vltOpen), "coffre ouvert et clé chargée : plus rien à saisir");
assert(/root@web-12/.test(vltOpen), "les clés déjà chargées restent lisibles");

// le bouton d'en-tête et son cycle de vie
assert(/id="lockbtn"[^>]*style="display:none"/.test(html), "le bouton part caché");
assert(/onclick="openVault\(\)"/.test(html), "et ouvre le formulaire des verrous");
assert(/loadVaultStatus\(\);/.test(html), "l'état des verrous est lu au démarrage");
assert(/vault: 60000/.test(html) && /if \(b\.vault\)/.test(html),
  "et rafraîchi périodiquement via la pile /refresh (le coffre se verrouille tout seul, RM2763)");
assert(/field\.value = "";/.test(html), "le champ est vidé après envoi — le secret ne traîne pas");
assert(!/localStorage[^\n]*(pass|secret)/i.test(html), "aucun secret ne va en stockage local");
console.log("✓ verrous du poste (RM2748) : bouton conditionnel, saisie sûre, rien de mémorisé");

// — RM2752 : un bugfix se crée avec ses étapes de reproduction, ou pas du tout —
// Le formulaire pouvait créer un bugfix sans repro ; `validate-task` le refusait
// juste après, et le ticket naissait invalide. Les étapes sont désormais un champ
// à part entière — visible SEULEMENT pour ce type, sinon c'est du bruit sur une
// feature.
const form2752 = newTicketFormHtml(
  [{ value: "feature", label: "feature" }, { value: "bugfix", label: "bugfix" }],
  ["low", "normal", "high", "urgent"],
  [{ client: "calyclay", project: "infra" }], "calyclay", "infra", escFn);
["ntf-bugbox", "ntf-bug-steps", "ntf-bug-repro"].forEach(id =>
  assert(form2752.includes('id="' + id + '"'), "champ bug manquant : " + id));
assert(/id="ntf-bugbox" style="display:none"/.test(form2752),
  "le bloc bug doit être masqué tant que le type n'est pas bugfix");
assert(/<option value="always" selected>/.test(form2752),
  "reproductibilité par défaut = always (le cas courant, pas un vide à remplir)");
assert(/onchange="ntfTypeChanged\(\)"/.test(form2752),
  "le select de type doit prévenir du changement, sinon le bloc ne s'ouvre jamais");
// les cinq valeurs de validate-task, ni plus ni moins
["always", "often", "sometimes", "rarely", "never"].forEach(v =>
  assert(form2752.includes('value="' + v + '"'), "reproductibilité manquante : " + v));

// le toggle lui-même, sur un DOM doublé
const ntfTypeChanged = grabO("ntfTypeChanged");
const mkDom = (type) => {
  const box = { style: { display: "none" } };
  const els = { "ntf-type": { value: type }, "ntf-bugbox": box };
  return { doc: { getElementById: (id) => els[id] || null }, box };
};
let d = mkDom("bugfix");
vm.runInNewContext("(" + grab("ntfTypeChanged") + ")()", { document: d.doc });
assert.strictEqual(d.box.style.display, "", "type bugfix → le bloc s'ouvre");
d = mkDom("feature");
vm.runInNewContext("(" + grab("ntfTypeChanged") + ")()", { document: d.doc });
assert.strictEqual(d.box.style.display, "none", "retour sur feature → le bloc se referme");
// robustesse : appelé avant le rendu du formulaire, il ne doit pas lever
vm.runInNewContext("(" + grab("ntfTypeChanged") + ")()", { document: { getElementById: () => null } });
console.log("✓ ticket bugfix (RM2752) : étapes de reproduction exigées, bloc réservé à ce type");

// — RM2757 : « Tickets ouverts » repliable, replié au démarrage —
const openedPanelOpen = grabO("openedPanelOpen");
const openedCountLabel = grabO("openedCountLabel");

// L'état par défaut est le cœur de la demande : la carte peut faire 40 lignes
// et repoussait la recherche et la création hors de l'écran.
assert.strictEqual(openedPanelOpen(null), false, "jamais visité → replié");
assert.strictEqual(openedPanelOpen(undefined), false, "storage indisponible → replié");
assert.strictEqual(openedPanelOpen(""), false, "valeur vide → replié");
assert.strictEqual(openedPanelOpen("0"), false, "replié par l'utilisateur → replié");
assert.strictEqual(openedPanelOpen("1"), true,
  "déplié par l'utilisateur → rouvert (sinon la carte se referme contre lui)");

// Repliée, l'en-tête doit dire s'il y a matière à ouvrir.
assert.strictEqual(openedCountLabel(12), "(12)", "le compte est visible sans ouvrir");
assert.strictEqual(openedCountLabel(1), "(1)");
assert.strictEqual(openedCountLabel(0), "(vide)", "zéro se dit, il ne se tait pas");
assert.strictEqual(openedCountLabel(null), "(vide)", "compte absent → « vide », pas un blanc");
assert.strictEqual(openedCountLabel("7"), "(7)", "compte en chaîne toléré");
// RM2883 : avec un filtre actif, l'en-tête dit ce qu'on voit ET le total — sans
// les deux, « (3) » sur une pile de quarante se lit comme une liste vidée.
assert.strictEqual(openedCountLabel(3, 40), "(3 / 40)", "filtre actif : vu / total");
assert.strictEqual(openedCountLabel(40, 40), "(40)", "sans filtre : le total seul");
assert.strictEqual(openedCountLabel(0, 40), "(vide)",
  "un filtre qui ne laisse rien se dit « vide », pas « 0 / 40 »");

// Le câblage HTML : sans lui, les fonctions pures ci-dessus ne servent à rien.
assert(/<details class="card" id="openedcard" ontoggle="openedToggled\(this\)">/.test(html),
  "la carte doit être un <details> qui mémorise le geste");
assert(/id="opened-count"/.test(html), "l'en-tête doit porter le compteur");
assert(!/<details class="card" id="openedcard"[^>]*\bopen\b/.test(html),
  "pas d'attribut open en dur : l'état initial vient du localStorage");
// Le « ? » d'aide est DANS le summary : sans stopPropagation, le consulter
// replierait la carte — un clic qui fait deux choses dont une non voulue.
const sumOpened = /<summary>Tickets ouverts[\s\S]*?<\/summary>/.exec(html);
assert(sumOpened, "summary de la carte introuvable");
assert(/event\.stopPropagation\(\)/.test(sumOpened[0]) && /event\.preventDefault\(\)/.test(sumOpened[0]),
  "le bouton d'aide ne doit pas replier la carte");
console.log("✓ tickets ouverts (RM2757) : carte repliable, repliée au départ, compte visible");

// — RM2759 : ouvrir au centre un fichier, un dossier, un commit, un email —
const viewKey = grabO("viewKey");
const parseViewKey = grabO("parseViewKey");
const viewTabLabel = grabO("viewTabLabel");
// RM2861 : le corps du fichier est rendu par fileBodyHtml, partagé avec les
// panneaux — la vue centrale ne fait plus qu'y ajouter son en-tête.
const fileBodyHtml = grabO("fileBodyHtml");
const fileViewHtml = grabO("fileViewHtml", { fileBodyHtml });
const dirViewHtml = grabO("dirViewHtml");
const mailViewHtml = grabO("mailViewHtml");
const viewErrorHtml = grabO("viewErrorHtml");

// La clé doit survivre à un rechargement ET aux caractères d'un vrai chemin :
// c'est elle, seule, qui rouvre la vue quand plus rien n'est attaché.
assert.deepEqual(parseViewKey(viewKey(["wt", "/a/b", "src/x.py"])), ["wt", "/a/b", "src/x.py"]);
assert.deepEqual(parseViewKey(viewKey(["doc", "", "projects/c/p/docs/cdc.md"])),
  ["doc", "", "projects/c/p/docs/cdc.md"], "une partie vide reste une partie");
assert.deepEqual(parseViewKey(viewKey(["wt", "/w", "un|pipe & espace.txt"])),
  ["wt", "/w", "un|pipe & espace.txt"], "un « | » dans le chemin ne coupe pas la clé");
assert.deepEqual(parseViewKey(""), [], "clé vide → aucune partie");
assert.deepEqual(parseViewKey("%ZZ"), ["%ZZ"], "clé illisible : rendue telle quelle, pas d'exception");

// Libellés : courts, mais reconnaissables entre dix onglets.
assert.strictEqual(viewTabLabel("file", ["wt", "/w", "a/b/cdc.md"]), "cdc.md");
assert.strictEqual(viewTabLabel("file", ["doc", "", "projects/c/p/docs/cdc.md"]), "cdc.md");
assert.strictEqual(viewTabLabel("dir", ["wt", "/w", "src/api"]), "api/");
assert.strictEqual(viewTabLabel("dir", ["wt", "/w", ""]), "racine/", "la racine se nomme");
assert.strictEqual(viewTabLabel("commit", ["2759", "abcdef1234567890"]), "abcdef12");
assert.strictEqual(viewTabLabel("mail", ["k1"], "Devis pour le site vitrine"), "Devis pour le site vitrine");
assert.strictEqual(viewTabLabel("mail", ["k1"], "x".repeat(40)).length, 30,
  "un sujet trop long est coupé, avec son ellipse");

// Fichier : markdown rendu, le reste préformaté — et la taille visible.
const fvMd = fileViewHtml({ path: "docs/cdc.md", markdown: true, size: 2048, content: "# Titre" },
  escO, (x) => "<MD>" + x + "</MD>");
assert(fvMd.includes("<MD># Titre</MD>"), "un .md passe par le rendu markdown");
assert(fvMd.includes("2 Ko"), "la taille est affichée");
const fvTxt = fileViewHtml({ path: "a.py", markdown: false, content: "<script>x</script>" },
  escO, (x) => "<MD>" + x + "</MD>");
assert(!fvTxt.includes("<script>"), "le contenu non-markdown est échappé");
assert(fvTxt.includes("&lt;script&gt;"), "…et lisible tel quel");

// Dossier : navigable, sinon ce n'est qu'une capture d'écran.
const dv = dirViewHtml({ src: "wt", wt: "/w/repo", path: "src", rootName: "repo",
  entries: [{ name: "api", dir: true }, { name: "main.py", dir: false, size: 512 }] }, escO, jargFn);
assert(/openCenterDir\('wt','\/w\/repo','src\/api',''\)/.test(dv), "un sous-dossier s'ouvre au centre (avec sa portée — RM2761)");
assert(/openCenterFile\('wt','\/w\/repo','src\/main.py',''\)/.test(dv), "un fichier aussi");
assert(dv.includes("repo") && dv.includes("src"), "le fil d'Ariane situe où on est");
assert(/openCenterDir\('wt','\/w\/repo','',''\)/.test(dv), "…et permet de remonter à la racine");
assert(dirViewHtml({ entries: [] }, escO, jargFn).includes("dossier vide"),
  "un dossier vide le dit");

// Email : le corps entier, et ce qui manque se dit.
const mv = mailViewHtml({ subject: "Devis", from: "a@b.fr", from_name: "Alice",
  date: "2026-08-20", body: "Bonjour\nà tous", body_truncated: true, state: "à traiter" }, escO);
assert(mv.includes("Bonjour"), "le corps est rendu");
assert(mv.includes("tronqué à la relève"), "une troncature amont est signalée");
assert(mv.includes("Alice") && mv.includes("a@b.fr"), "l'expéditeur est identifiable");
assert(mailViewHtml({ subject: "x" }, escO).includes("corps non disponible"),
  "sans corps, la vue le dit au lieu d'afficher un blanc");
assert(mailViewHtml({}, escO).includes("(sans sujet)"), "un email sans sujet reste ouvrable");

// Source disparue : un onglet épinglé survit à ce qu'il montrait.
const ev = viewErrorHtml("Commit indisponible", "erreur 404", escO);
assert(ev.includes("Commit indisponible") && ev.includes("erreur 404"), "l'erreur exacte est reprise");
assert(ev.includes("session fermée"), "…avec l'explication la plus probable");

// Le câblage : sans lui, les fonctions pures ci-dessus ne s'affichent nulle part.
assert(/<div id="viewpane"/.test(html), "le panneau central doit avoir sa vue générique");
["file", "dir", "commit", "mail"].forEach(k =>
  assert(new RegExp('t\\.kind === "' + k + '"').test(html), "activateTab ne rouvre pas les " + k));
const iconLine = /const icon = \{[\s\S]*?\};/.exec(html);
["file:", "dir:", "commit:", "mail:"].forEach(k =>
  assert(iconLine && iconLine[0].includes(k), "icône d'onglet manquante : " + k));
// Les vues existantes doivent céder la place — sans ça, deux panneaux se superposent
["function attach(rmId) {", "function openReview(rm) {", "async function openProjectView(key) {",
 "function openNewTicket() {", "function openDashboard() {"].forEach(sig => {
  const i = html.indexOf(sig);
  assert(i > 0, "ouvreur introuvable : " + sig);
  assert(html.slice(i, i + 700).includes("closeCenterView()"),
    "cet ouvreur ne referme pas la vue centrale : " + sig);
});
// …et réciproquement : une fermeture ne doit pas rappeler le tableau de bord
// par-dessus une vue centrale ouverte.
assert(/!currentProjectView && !centerView/.test(html),
  "closeNewTicket doit tenir compte de la vue centrale");
console.log("✓ vues centrales (RM2759) : fichier, dossier, commit, email — clé rouvrable, sources absentes annoncées");

// — RM2760 : panneau « projets » —
const groupProjectsByClient = grabO("groupProjectsByClient");
const liveByProject = grabO("liveByProject");
const projectsPanelHtml = grabO("projectsPanelHtml");

const PJ2760 = [
  { client: "calicote", project: "prestashop", value: "calicote/prestashop" },
  { client: "abatik", project: "infra", value: "abatik/infra" },
  { client: "calicote", project: "infra", value: "calicote/infra" },
  { client: "abatik", project: "site", value: "abatik/site" },
];

// Groupement : clients triés, projets triés dans chaque client.
const g2760 = groupProjectsByClient(PJ2760, "");
assert.deepEqual(g2760.map(g => g.client), ["abatik", "calicote"], "clients par ordre alphabétique");
assert.deepEqual(g2760[0].projects.map(p => p.project), ["infra", "site"], "projets triés aussi");
assert.deepEqual(groupProjectsByClient([], "").length, 0, "aucune donnée → aucun groupe");
assert.deepEqual(groupProjectsByClient(null, "").length, 0, "liste absente tolérée");
assert.deepEqual(groupProjectsByClient([{ client: "x" }], "").length, 0,
  "une entrée sans projet n'invente pas un groupe");

// Filtre : sur le client, il ramène TOUS ses projets ; sur un projet, seulement lui.
const gc2760 = groupProjectsByClient(PJ2760, "abatik");
assert.deepEqual(gc2760.map(g => g.client), ["abatik"]);
assert.strictEqual(gc2760[0].projects.length, 2, "filtrer un client garde tous ses projets");
const gp2760 = groupProjectsByClient(PJ2760, "infra");
assert.deepEqual(gp2760.map(g => g.client), ["abatik", "calicote"],
  "chercher « infra » montre les infra de TOUS les clients, pas la première trouvée");
assert.deepEqual(gp2760[1].projects.map(p => p.project), ["infra"], "…et rien d'autre chez eux");
assert.strictEqual(groupProjectsByClient(PJ2760, "CALICOTE").length, 1, "filtre insensible à la casse");
assert.strictEqual(groupProjectsByClient(PJ2760, "zzz").length, 0, "filtre sans résultat → rien");

// Sessions vivantes par projet : un fantôme ne tourne pas.
const sess2760 = [
  { rm_id: "1", client: "abatik", project: "infra" },
  { rm_id: "2", client: "abatik", project: "infra" },
  { rm_id: "3", ghost: true, client: "abatik", project: "infra" },
  { rm_id: "4" },                                  // résolu par le cache
  { rm_id: "5" },                                  // non résolu : ignoré
];
const rc2760 = { "4": { found: true, client: "calicote", project: "infra" } };
assert.deepEqual(liveByProject(sess2760, rc2760), { "abatik/infra": 2, "calicote/infra": 1 },
  "une session enregistrée non démarrée (ghost) n'est pas comptée comme active");
assert.deepEqual(liveByProject(null, null), {}, "aucune session → aucun compte");

// Rendu : replié par défaut, déplié pour le contexte, tout déplié sous filtre.
const hAll2760 = projectsPanelHtml(g2760, { live: {}, open: {}, client: "", filtre: "" }, escO, jargFn);
assert(hAll2760.includes("▸ abatik"), "sans contexte ni filtre, un client est replié");
assert(!/openProjectView\('abatik\/infra'\)/.test(hAll2760), "…et ses projets ne sont pas rendus");
const hCtx2760 = projectsPanelHtml(g2760, { live: {}, open: {}, client: "abatik", filtre: "" }, escO, jargFn);
assert(hCtx2760.includes("▾ abatik") && /openProjectView\('abatik\/infra'\)/.test(hCtx2760),
  "le client du contexte est déplié d'emblée");
assert(hCtx2760.includes("ctx"), "…et signalé comme tel");
assert(hCtx2760.includes("▸ calicote"), "les autres restent repliés");
const hFil2760 = projectsPanelHtml(g2760, { live: {}, open: {}, client: "", filtre: "infra" }, escO, jargFn);
assert(/openProjectView\('calicote\/infra'\)/.test(hFil2760),
  "sous filtre, tout est déplié — replier ce qu'on vient de chercher serait absurde");
const hOpen2760 = projectsPanelHtml(g2760, { live: {}, open: { calicote: true }, client: "", filtre: "" }, escO, jargFn);
assert(/openProjectView\('calicote\/prestashop'\)/.test(hOpen2760), "un client déplié à la main s'ouvre");
const hLive2760 = projectsPanelHtml(g2760, { live: { "abatik/infra": 3 }, open: {}, client: "abatik", filtre: "" },
  escO, jargFn);
assert(hLive2760.includes("3 ▶"), "le nombre de sess2760 vivantes est affiché");
assert(projectsPanelHtml([], { filtre: "zz" }, escO, jargFn).includes("aucun client ni projet ne correspond"),
  "un filtre sans résultat le dit — au lieu d'un panneau vide");
assert(projectsPanelHtml([], {}, escO, jargFn).includes("aucun projet"),
  "…et l'absence de données a son propre message");

// Le câblage : un panneau que rien n'ouvre n'existe pas.
assert(/data-panel="projects"/.test(html), "l'onglet gauche doit exister");
assert(/<div class="lpanel" id="lp-projects">/.test(html), "…avec son panneau");
assert(/projects: \(\) => loadProjectsPanel\(\)/.test(html), "…et son chargeur");
console.log("✓ panneau projets (RM2760) : groupé par client, filtré, fiche au centre");

// ── RM2675 : glossaire de projet — lecture du tableau et filtre ───────────────
// Ce qu'on protège : le sous-onglet « vocabulaire » n'ajoute qu'UNE chose au rendu markdown
// déjà existant — la recherche. Si le filtre ne trouve pas un terme par son ALIAS, la colonne
// alias ne sert à rien et le sous-onglet non plus.
const gr = />>> glossaireRows[\s\S]*?(function glossaireRows[\s\S]*?)\n\/\/ <<< glossaireRows/.exec(html);
assert(gr, "marqueurs >>> glossaireRows introuvables");
const glossaireRows = vm.runInNewContext("(" + gr[1] + ")");
const gf = />>> glossaireFiltre[\s\S]*?(function glossaireFiltre[\s\S]*?)\n\/\/ <<< glossaireFiltre/.exec(html);
assert(gf, "marqueurs >>> glossaireFiltre introuvables");
const glossaireFiltre = vm.runInNewContext("(" + gf[1] + ")");

const MD2675 = [
  "---", "wiki_sync: true", "---", "", "# Glossaire — calyclay/calymix", "",
  "| Terme | Définition | Contexte d'usage | Alias |",
  "|---|---|---|---|",
  "| HFOV | Champ horizontal d'une optique. | 24 mm ⇒ 74°. | horizontal field of view |",
  "| rampe | Barre portant la rangée de guillotines. | 75 vannes × 40 mm. | — |",
].join("\n");
const rows2675 = glossaireRows(MD2675);
assert(rows2675.length === 2, "le frontmatter, le titre et le séparateur ne sont PAS des termes");
assert(rows2675[0].terme === "HFOV" && rows2675[0].alias.includes("field of view"),
  "les 4 colonnes sont lues");
assert(glossaireRows("").length === 0 && glossaireRows(null).length === 0,
  "glossaire vide ou absent toléré");
assert(glossaireRows("| a | b |")[0].contexte === "" , "une ligne courte est complétée, pas rejetée");

assert(glossaireFiltre(rows2675, "").length === 2, "filtre vide = tout");
assert(glossaireFiltre(rows2675, "RAMP").length === 1, "le filtre est insensible à la casse");
assert(glossaireFiltre(rows2675, "field of view")[0].terme === "HFOV",
  "on trouve un terme par son ALIAS — sinon la colonne alias est inutile");
assert(glossaireFiltre(rows2675, "guillotines")[0].terme === "rampe",
  "…et par le CONTEXTE, pas seulement par le terme");
assert(glossaireFiltre(rows2675, "zzz").length === 0, "un filtre sans résultat rend une liste vide");

// Le câblage : un sous-onglet que rien n'affiche n'existe pas.
assert(/onclick="vocabShow\(true\)"/.test(html), "le sous-onglet vocabulaire doit être cliquable");
assert(/function vocabShow/.test(html) && /function vocabBodyHtml/.test(html),
  "…avec son chargeur et son corps");
assert(/glossaire\.md/.test(html), "…et il doit chercher docs/glossaire.md");
console.log("✓ glossaire de projet (RM2675) : tableau lu, filtre sur terme/définition/contexte/alias");
// — RM2761 : la vue centrale porte SA portée (sinon « worktree hors du périmètre ») —
const fsScope = grabFn("fsScope");
const scopeSrc = grab("scopeTag");     // 4 fonctions dans le même bloc
const scopeCtx = vm.runInNewContext(
  scopeSrc + "; ({scopeTag, scopeFromTag, scopeQuery})",
  { encodeURIComponent, String, Object });
const { scopeTag, scopeFromTag, scopeQuery } = scopeCtx;

const FD = { projects: [{ root: "/ws/ipro/pm", client: "ipro", project: "pm" }] };
let sc = fsScope("/ws/ipro/pm/envs/pm-rm42", FD, "karl-RM42", null);
assert.equal(sc.client, "ipro"); assert.equal(sc.project, "pm");
assert.equal(sc.sid, "karl-RM42",
  "les DEUX portées sont gardées : le serveur autorise l'union session ∪ projet");
assert.deepEqual(fsScope("/ailleurs/scratch", FD, "karl-RM42", null), { sid: "karl-RM42" },
  "un worktree hors projet ne doit garder QUE le sid — sinon on perdrait le seul droit qui l'autorise");
assert.deepEqual(fsScope("/x", { client: "acme", project: "shop" }, null, null),
  { client: "acme", project: "shop" }, "sans session, la portée projet du panneau suffit");
assert.deepEqual(fsScope("/x", {}, null, "acme/shop"), { client: "acme", project: "shop" },
  "à défaut, la fiche projet ouverte donne la portée");
assert.deepEqual(fsScope("/x", {}, null, null), {}, "rien de connu → aucune portée inventée");

assert.equal(scopeTag({ client: "ipro", project: "pm", sid: "karl-RM42" }), "c:ipro/pm;s:karl-RM42");
assert.deepEqual(scopeFromTag("c:ipro/pm;s:karl-RM42"), { client: "ipro", project: "pm", sid: "karl-RM42" });
assert.deepEqual(scopeFromTag("s:karl-RM42"), { sid: "karl-RM42" });
assert.equal(scopeFromTag(""), null, "clé d'onglet d'avant RM2761 → repli sur le contexte courant");
assert.equal(scopeFromTag("c:incomplet"), null, "portée projet tronquée : ignorée, pas devinée");
assert.equal(scopeQuery({ client: "ipro", project: "pm", sid: "" }),
  "client=ipro&project=pm&sid=", "la requête porte les deux moitiés (sid vide accepté)");

// la portée survit à l'aller-retour par la clé d'onglet (localStorage)
const vkey = grabFn("viewKey"), pkey = grabFn("parseViewKey");
const tag2761 = scopeTag({ client: "ipro", project: "pm", sid: "karl-RM42" });
const rt = pkey(vkey(["wt", "/ws/ipro/pm/envs/pm-rm42", "docs/a.md", tag2761]));
assert.deepEqual(rt, ["wt", "/ws/ipro/pm/envs/pm-rm42", "docs/a.md", tag2761],
  "clé d'onglet : la portée doit revenir intacte (séparateurs : ; et /)");

// un dossier ouvert au centre reste navigable : chaque lien emporte la portée
const dirViewHtml2761 = grabFn("dirViewHtml");
const dh2761 = dirViewHtml2761({ src: "wt", wt: "/ws/ipro/pm", path: "docs", rootName: "pm",
  tag: tag2761, entries: [{ name: "sous", dir: true }, { name: "a.md", size: 10 }] },
  escFn, jargFn);
assert((dh2761.match(/c:ipro\/pm;s:karl-RM42/g) || []).length >= 3,
  "fil d'ariane, sous-dossiers et fichiers doivent tous porter la portée");
assert(/openCenterFile\('wt','\/ws\/ipro\/pm','docs\/a\.md','c:ipro/.test(dh2761),
  "le fichier s'ouvre avec la portée en 4e argument");

// les boutons « ⤢ au centre » capturent la portée AU RENDU (avant tout detach)
assert(/openCenterFile\('wt'," \+ jarg\(fileNav\.wt\) \+ "," \+ jarg\(fpath\) \+ ","/.test(html),
  "le bouton fichier doit passer une 4e valeur : la portée");
assert(/scopeTag\(fsScope\(fileNav\.wt, filesData, attached, currentProjectView\)\)/.test(html),
  "et la calculer depuis le contexte encore vivant");
assert(/openCenterFile\(p\[0\], p\[1\], p\[2\], p\[3\]\)/.test(html),
  "la réactivation d'onglet doit rejouer la portée mémorisée");
assert(/const fixed = scopeFromTag\(tag\);/.test(html),
  "_fsq doit préférer la portée explicite au contexte courant (vidé par centerViewPane)");
console.log("✓ portée des vues centrales (RM2761) : capturée au clic, transportée, rejouée");

// — RM2768 : fiche client et confs au centre —
const clientViewHtml = grabO("clientViewHtml");
const confViewHtml = grabO("confViewHtml");

const CLI2768 = {
  client: "calicote", name: "Calicote", status: "active", type: "client",
  created: "2026-05-19", redmine_project_id: "calicote",
  redmine_project_url: "https://r.test/projects/calicote",
  contacts: [
    { first_name: "Sandrine", last_name: "Roche", email: "s@calicote.test",
      role: "owner", title: "Gérante" },
    { name: "Mathieu", email: "m@ipro.test", role: "owner", internal: true },
  ],
  defaults: { priority: "normal", team: [{ username: "iprospective" }] },
  projects: [{ project: "prestashop", value: "calicote/prestashop" }],
  projects_used: ["iprospective/nc-clients"],
  docs: [{ name: "overview.md", path: "projects/clients/calicote/client/overview.md" }],
};
const cv = clientViewHtml(CLI2768, escO, jargFn);
assert(cv.includes("Calicote") && cv.includes("calicote"), "identité et slug");
assert(cv.includes("Sandrine Roche") && cv.includes("Gérante"),
  "un contact se lit par son nom ET sa fonction");
assert(cv.includes("interne"), "un contact interne est signalé comme tel");
assert(/openProjectView\('calicote\/prestashop'\)/.test(cv),
  "les projets du client mènent à leur fiche");
assert(cv.includes("Projets utilisés") && cv.includes("iprospective/nc-clients"),
  "le partage cross-client est visible, il ne se devine pas dans le YAML");
assert(/openCenterFile\('doc','','projects\/clients\/calicote\/client\/overview\.md'\)/.test(cv),
  "les docs du client s'ouvrent au centre");
assert(cv.includes('href="https://r.test/projects/calicote"'), "lien Redmine cliquable");
// tolérance : une fiche squelettique reste servie
const cvMin = clientViewHtml({ client: "x" }, escO, jargFn);
assert(cvMin.includes("aucun projet"), "un client sans projet le dit");
assert(!cvMin.includes("Contacts"), "…et n'invente pas de section vide");
assert(clientViewHtml(null, escO, jargFn).includes("client"), "données absentes tolérées");

// Conf : rendue telle quelle, et échappée.
const cf = confViewHtml({ label: "calicote/prestashop", name: "meta.yml",
  content: "slug: x\nrepos:\n  - <b>a</b>\n" }, escO);
assert(cf.includes("calicote/prestashop") && cf.includes("meta.yml"), "on sait ce qu'on lit");
assert(cf.includes("&lt;b&gt;a&lt;/b&gt;"), "le contenu est échappé, jamais interprété");
assert(cf.includes("slug: x"), "…et rendu tel quel, sans reformatage");
assert(cf.includes("mmi-pm"), "la lecture seule renvoie à l'outillage qui, lui, écrit");
assert(confViewHtml({}, escO).includes("meta.yml"), "conf vide : un titre, pas une erreur");

// Les icônes du panneau : présentes, et sans effet de bord sur le pliage.
const gIco = groupProjectsByClient(PJ2760, "");
const hIco = projectsPanelHtml(gIco, { live: {}, open: {}, client: "abatik", filtre: "" },
  escO, jargFn);
assert(/openCenterClient\('abatik'\)/.test(hIco), "icône fiche client");
assert(/openCenterConf\('client','abatik',''\)/.test(hIco), "icône conf client");
assert(/openCenterConf\('project','abatik','infra'\)/.test(hIco), "icône conf projet");
// le piège : la ligne du client EST le bouton de pliage
const ligneClient = /<div class="oline"[^>]*pjToggle\('abatik'\)[\s\S]*?<\/div>/.exec(hIco);
assert(ligneClient, "ligne client introuvable");
assert((ligneClient[0].match(/event\.stopPropagation\(\)/g) || []).length === 2,
  "chaque icône du client doit stopper la propagation, sinon elle replie le client");
assert(/onclick="event\.stopPropagation\(\);openCenterConf\('project'/.test(hIco),
  "l'icône d'un projet ne doit pas déclencher l'ouverture de sa fiche");
// et l'onglet doit savoir se rouvrir
["client", "conf"].forEach(k =>
  assert(new RegExp('t\\.kind === "' + k + '"').test(html), "activateTab ne rouvre pas les " + k));
console.log("✓ fiche client et confs (RM2768) : contacts, partage, meta.yml — icônes sans effet de bord");

// — RM2770 : recherche multi-source et filtres —
const searchQuery = grabO("searchQuery");
const searchRowMeta = grabO("searchRowMeta");

// La source par défaut ne doit RIEN changer à la requête d'avant.
assert.strictEqual(searchQuery("abc", { source: "local" }, ""), "/tickets/search?q=abc",
  "source locale = requête historique, sans paramètre superflu");
assert(searchQuery("x", { source: "redmine" }, "").includes("source=redmine"));
assert(searchQuery("x", { source: "both" }, "").includes("source=both"));
// Le filtre explicite prime sur le contexte global : sinon le cockpit
// contredirait en silence le client qu'on vient de choisir.
assert(searchQuery("x", { client: "abatik" }, "calicote").includes("client=abatik"),
  "le filtre explicite prime sur le contexte client");
assert(searchQuery("x", {}, "calicote").includes("client=calicote"),
  "…mais sans filtre, le contexte s'applique toujours (RM2639)");
assert(!searchQuery("x", {}, "").includes("client="), "aucun client → aucun filtre client");
const qFull = searchQuery("mep", { source: "both", client: "c", project: "p", status: "a_faire" }, "");
["q=mep", "client=c", "project=p", "status=a_faire", "source=both"].forEach(frag =>
  assert(qFull.includes(frag), "paramètre manquant : " + frag));
assert(searchQuery("a b&c", {}, "").includes("q=a%20b%26c"), "la requête est encodée");
assert.strictEqual(searchQuery(null, null, null), "/tickets/search?q=", "entrées molles tolérées");

// La ligne de contexte : ce qui décide du geste suivant doit être écrit.
assert.strictEqual(searchRowMeta({ client: "c", project: "p", status: "a_faire" }),
  "c / p · a_faire", "un résultat local reste sobre — pas de bruit");
const meta2770 = searchRowMeta({ rm_id: "9", origin: "redmine", synced: false,
  status: "Nouveau", redmine_project: "Projet X", assigned_to: "Karl" });
assert(meta2770.includes("⚠ pas en local"),
  "un ticket que le local ignore DOIT le dire — c'est ce qu'on est venu chercher");
assert(meta2770.includes("Projet X"), "…et à défaut de client/projet PM, son projet Redmine");
assert(meta2770.includes("→ Karl"), "…et son assignation, qui vient de Redmine seul");
assert(searchRowMeta({ client: "c", project: "p", origin: "both", synced: true })
  .includes("🌐 Redmine"), "un ticket vu des deux côtés le signale sans alarmer");
assert(!searchRowMeta({ client: "c", project: "p", origin: "both", synced: true })
  .includes("pas en local"), "…et surtout pas comme absent");
assert.strictEqual(searchRowMeta(null), "— · ?", "résultat vide : pas d'exception");

// Câblage : les trois sources et les filtres doivent exister dans la page.
["sf-source", "sf-client", "sf-project", "sf-status", "sf-warn"].forEach(id =>
  assert(html.includes('id="' + id + '"'), "élément manquant : " + id));
["local", "redmine", "both"].forEach(v =>
  assert(new RegExp('<option value="' + v + '"').test(html), "source manquante : " + v));
assert(/<select id="sf-source"[\s\S]*?<option value="local"/.test(html),
  "« local » doit être la première option, donc le défaut");
assert(/r\.redmine_error/.test(html),
  "l'erreur Redmine doit être affichée à côté des résultats, pas à leur place");
console.log("✓ recherche multi-source (RM2770) : local par défaut, filtres, absents signalés");

// — RM2774 : la barre centrale tient sur deux lignes —
const barre2774 = /<div class="tabbar">[\s\S]*?<div class="termwrap">/.exec(html);
assert(barre2774, "barre centrale introuvable");
const b2774 = barre2774[0];
// L'ordre compte : les onglets d'abord, puis la ligne titre + actions.
assert(b2774.indexOf('id="ctabs"') < b2774.indexOf('class="tabbar2"'),
  "les onglets doivent précéder la seconde ligne");
assert(b2774.indexOf('class="tabbar2"') < b2774.indexOf('id="curtitle"')
  && b2774.indexOf('class="tabbar2"') < b2774.indexOf('id="tabactions"'),
  "titre et actions doivent être DANS la seconde ligne, pas à côté");
// Sans direction column, les deux « lignes » se remettraient côte à côte.
assert(/\.tabbar \{[^}]*flex-direction: column/.test(html),
  ".tabbar doit empiler ses deux lignes");
assert(/\.tabbar2 \{[^}]*display: flex/.test(html),
  ".tabbar2 doit aligner titre et actions sur une ligne");
// Le bridage à 62 % n'a plus lieu d'être : les onglets ont la largeur entière.
const ctabsCss = /\.ctabs \{[^}]*\}/.exec(html);
assert(ctabsCss && !/max-width/.test(ctabsCss[0]),
  "les onglets ne doivent plus être bridés en largeur");
// …et rien ne doit avoir bougé du contenu : mêmes actions, même condition d'affichage.
assert(/<div class="tabactions" id="tabactions" style="display:none">/.test(html),
  "les actions restent masquées hors session attachée");
["yesbtn", "autoyes", "micbtn", "readbtn", "monbtn", "layoutsel", "reattach"].forEach(id =>
  assert(b2774.includes('id="' + id + '"'), "action perdue au déplacement : " + id));
console.log("✓ barre centrale (RM2774) : onglets pleine largeur, titre et actions dessous");

// — RM2775 : l'infobulle d'un onglet dit ce que son libellé ne peut pas dire —
const tabTooltip = grabO("tabTooltip");
const parse2775 = parseViewKey;
const RC2775 = {
  "2744": { found: true, title: "Tableau de bord : contenu coupé en haut" },
  "2673": { found: true, title: "Améliorations ergonomiques PM" },
  "9999": { found: false },
};

// Le cas de la demande : survoler « RM2744 » ne doit plus afficher « RM2744 ».
const tipTicket = tabTooltip({ kind: "review", key: "2744", label: "RM2744" }, RC2775, parse2775);
assert(tipTicket.includes("Tableau de bord : contenu coupé"),
  "l'infobulle d'un ticket doit porter son titre");
assert(tipTicket.startsWith("RM2744 — "), "…sans perdre l'identifiant, qui situe");
// Titre pas encore résolu : ne rien inventer, et surtout pas de tiret orphelin.
const tipInconnu = tabTooltip({ kind: "review", key: "9999", label: "RM9999" }, RC2775, parse2775);
assert.strictEqual(tipInconnu, "RM9999", "un titre inconnu ne laisse pas de tiret vide");
assert(!/undefined|null/.test(tipInconnu), "…ni de « undefined »");
assert.strictEqual(tabTooltip({ kind: "review", key: "2744", label: "RM2744" }, {}, parse2775),
  "RM2744", "cache vide toléré");

// Session : titre si connu, forme lisible sinon.
assert(tabTooltip({ kind: "session", key: "2673" }, RC2775, parse2775)
  .includes("Améliorations ergonomiques"), "une session ancrée sur un ticket porte son titre");
assert.strictEqual(tabTooltip({ kind: "session", key: "calymix" }, RC2775, parse2775),
  "session calymix", "une session à slug reste lisible");

// Les vues centrales : c'est là que le libellé est le plus tronqué.
assert(tabTooltip({ kind: "file", key: viewKey(["wt", "/w/repo", "src/api/handlers.py"]) },
  RC2775, parse2775).includes("src/api/handlers.py"), "un fichier montre son chemin entier");
assert(tabTooltip({ kind: "dir", key: viewKey(["wt", "/w/repo", "src/api"]) }, RC2775, parse2775)
  .includes("src/api"), "un dossier aussi");
assert(tabTooltip({ kind: "dir", key: viewKey(["wt", "/w/repo", ""]) }, RC2775, parse2775)
  .includes("racine"), "…y compris la racine, qui se nomme");
const tipCommit = tabTooltip({ kind: "commit", key: viewKey(["2749", "abcdef1234567890"]) },
  RC2775, parse2775);
assert(tipCommit.includes("abcdef1234567890"), "un commit montre son sha ENTIER (le libellé le coupe à 8)");
assert(tipCommit.includes("2749"), "…et la session qui le sert");
assert(tabTooltip({ kind: "mail", key: "k1", label: "Devis pour le site vitrine et…" },
  RC2775, parse2775).includes("Devis pour le site"), "un email montre son sujet");
assert(tabTooltip({ kind: "conf", key: viewKey(["project", "calicote", "presta"]) },
  RC2775, parse2775).includes("calicote/presta"), "une conf projet dit de quel projet");
assert(tabTooltip({ kind: "client", key: viewKey(["calicote"]) }, RC2775, parse2775)
  .includes("calicote"), "une fiche client dit lequel");
assert.strictEqual(tabTooltip({ kind: "dash", key: "" }, RC2775, parse2775), "tableau de bord");
assert.strictEqual(tabTooltip({}, RC2775, parse2775), "", "onglet vide : pas d'exception");
assert.strictEqual(tabTooltip(null, null, null), "", "entrées molles tolérées");

// Le rendu doit utiliser l'infobulle, et garder les mentions de fonctionnement.
const htmlTabs = renderCenterTabs(
  [{ kind: "dash", key: "", label: "tableau de bord", pinned: true, fixed: true },
   { kind: "review", key: "2744", label: "RM2744", pinned: true },
   { kind: "review", key: "2673", label: "RM2673", pinned: false }],
  "review:2744", escO, jargFn, RC2775, parse2775);
assert(htmlTabs.includes("Tableau de bord : contenu coupé"),
  "le titre du ticket arrive bien dans le title= de l'onglet");
assert(htmlTabs.includes("toujours là"), "l'onglet permanent garde sa mention");
assert(htmlTabs.includes("non épinglé"), "…et le temporaire la sienne");
assert(htmlTabs.includes('<span class="lbl">RM2744</span>'),
  "le LIBELLÉ affiché ne change pas — seule l'infobulle s'enrichit");
console.log("✓ infobulle d'onglet (RM2775) : le titre, le chemin, le sha entier — jamais un tiret vide");

// — RM2776 : historique de navigation —
const histVisit = grabO("histVisit", { Array, Object });
const histStep = grabO("histStep", { Array });
const histCloseTarget = grabO("histCloseTarget", { Array });
const histListHtml = grabO("histListHtml", { Array });

// Visiter : modèle du navigateur.
let h2776 = { items: [], idx: -1 };
h2776 = histVisit(h2776, { id: "session:2673", kind: "session", label: "2673" }, 40);
h2776 = histVisit(h2776, { id: "review:2744", kind: "review", label: "RM2744" }, 40);
assert.deepEqual(h2776.items.map(e => e.id), ["session:2673", "review:2744"]);
assert.strictEqual(h2776.idx, 1, "on est sur la dernière visitée");
// Revisiter la vue courante ne doit pas empiler : deux clics sur le même onglet
// bloqueraient sinon le retour arrière.
const h2 = histVisit(h2776, { id: "review:2744", kind: "review", label: "RM2744 (bis)" }, 40);
assert.strictEqual(h2.items.length, 2, "revisiter la vue courante n'empile pas");
assert.strictEqual(h2.items[1].label, "RM2744 (bis)", "…mais rafraîchit son libellé");
assert.strictEqual(histVisit(h2776, {}, 40).items.length, 2, "entrée sans id ignorée");
assert.deepEqual(histVisit(null, { id: "a:1" }, 40).items.map(e => e.id), ["a:1"],
  "état absent toléré");
// Plafond : on garde les plus RÉCENTES.
let plein2776 = { items: [], idx: -1 };
for (let i = 0; i < 10; i++) plein2776 = histVisit(plein2776, { id: "review:" + i }, 4);
assert.deepEqual(plein2776.items.map(e => e.id), ["review:6", "review:7", "review:8", "review:9"],
  "le plafond coupe les plus anciennes");
assert.strictEqual(plein2776.idx, 3, "l'index suit la troncature");

// Le cas de la demande : fermer la fiche ouverte depuis une session y ramène.
const ouvertes2776 = new Set(["session:2673", "review:2744", "dash:"]);
const isOpen2776 = (id) => ouvertes2776.has(id);
assert.strictEqual(histCloseTarget(h2776, "review:2744", isOpen2776), "session:2673",
  "fermer la fiche ramène à la session d'où on venait, pas au voisin de barre");
// Une vue fermée entre-temps ne doit pas être proposée.
const ouvertes2 = new Set(["dash:"]);
let h3 = histVisit(h2776, { id: "dash:", kind: "dash", label: "tableau de bord" }, 40);
assert.strictEqual(histCloseTarget(h3, "dash:", (id) => ouvertes2.has(id)), null,
  "aucune destination valide → null, l'appelant retombe sur le voisin (comportement d'avant)");
assert.strictEqual(histCloseTarget({ items: [], idx: -1 }, "x:1", isOpen2776), null,
  "historique vide → repli");
assert.strictEqual(histCloseTarget(h2776, "review:2744", null), "session:2673",
  "sans test d'ouverture, la dernière autre visitée fait l'affaire");

// Retour arrière / avant, en sautant les vues fermées.
const parcours2776 = { items: [{ id: "a:1" }, { id: "b:2" }, { id: "c:3" }], idx: 2 };
assert.strictEqual(histStep(parcours2776, -1, () => true).entry.id, "b:2", "← recule d'un cran");
assert.strictEqual(histStep(parcours2776, -1, (id) => id !== "b:2").entry.id, "a:1",
  "une vue fermée est SAUTÉE, pas rouverte");
assert.strictEqual(histStep(parcours2776, 1, () => true).entry, null, "→ en bout de liste : rien");
assert.strictEqual(histStep({ items: [{ id: "a:1" }], idx: 0 }, -1, () => true).entry, null,
  "au début, ← ne fait rien");
assert.strictEqual(histStep(parcours2776, -1, () => false).entry, null,
  "tout fermé → aucune destination");
assert.strictEqual(histStep({ ...parcours2776, idx: 0 }, 1, () => true).entry.id, "b:2",
  "→ ré-avance après un retour");

// La liste du header.
const listeHtml2776 = histListHtml(
  { items: [{ id: "session:2673", kind: "session", label: "2673" },
            { id: "review:2744", kind: "review", label: "RM2744" }], idx: 1 },
  (id) => id !== "session:2673", escO, jargFn);
assert(listeHtml2776.indexOf("RM2744") < listeHtml2776.indexOf("2673"),
  "la plus récente est en tête");
assert(/histGoTo\('review:2744'\)/.test(listeHtml2776), "une vue ouverte est cliquable");
assert(!/histGoTo\('session:2673'\)/.test(listeHtml2776), "une vue fermée ne l'est pas");
assert(listeHtml2776.includes("fermée"), "…et le dit, au lieu de disparaître de l'historique");
assert(listeHtml2776.includes("ici"), "la vue courante est repérée");
assert(histListHtml({ items: [], idx: -1 }, null, escO, jargFn).includes("aucune vue visitée"),
  "historique vide : un message, pas un panneau blanc");

// Câblage : boutons du header et point d'entrée unique.
["histback", "histfwd", "histbtn", "histbox"].forEach(id =>
  assert(html.includes('id="' + id + '"'), "élément manquant : " + id));
assert(/function noteTab[\s\S]{0,600}histVisit\(/.test(html),
  "l'historique doit être alimenté par noteTab — le seul passage obligé des vues");
assert(/navSuspend/.test(html), "un retour arrière ne doit pas s'empiler lui-même");
assert(/const fermaitLaVueAffichee/.test(html),
  "fermer un onglet NON affiché ne doit pas changer l'écran");
console.log("✓ historique de navigation (RM2776) : retour d'où l'on vient, ←/→, liste du header");

// — RM2786 : n'offrir que les actions qui ont du sens —
const batchButtons = grabO("batchButtons", { Object, Set, String });
const closeBatchPlan = grabO("closeBatchPlan", { Object, Set, String });
const ticketVerdicts = grabO("ticketVerdicts", { Set, String });

// La règle vient du serveur : le front la LIT, il ne la redéclare pas.
const CFG2786 = {
  batch_modes: {
    traiter: { statuses: ["a_corriger", "a_etudier_chiffrer", "a_faire", "a_tester_dev",
                          "en_cours", "etude_chiffrage_en_cours", "nouveau"], skip: { ferme: "fermé" } },
    atester: { statuses: ["a_corriger", "a_faire", "a_tester_dev", "en_cours"],
               skip: { a_tester_demandeur: "déjà en test chez toi" } },
    etudier: { statuses: ["a_etudier_chiffrer", "etude_chiffrage_en_cours", "nouveau"],
               skip: { a_faire: "déjà chiffré" } },
  },
  closable_statuses: ["a_mep", "a_tester_demandeur", "a_tester_dev", "en_mep"],
  statuses: ["nouveau", "a_etudier_chiffrer", "etude_chiffrage_en_cours",
             "etude_chiffrage_a_valider", "a_faire", "en_cours", "a_corriger",
             "a_tester_dev", "a_tester_demandeur", "a_mep", "en_mep", "en_pause", "ferme"],
};
const SEL2786 = [
  { rm_id: "1", status: "nouveau" },
  { rm_id: "2", status: "en_cours" },
  { rm_id: "3", status: "a_tester_demandeur" },
];

// Les compteurs disent ce qui va PARTIR, pas le total coché.
const nb = batchButtons(SEL2786, ["RM2"], CFG2786);
assert.strictEqual(nb.etudier, 1, "« analyser » ne compte que le ticket à étudier");
assert.strictEqual(nb.traiter, 2, "« traiter » ne compte pas le ticket déjà livré");
assert.strictEqual(nb.atester, 1, "« à tester » ne compte pas ce qui n'est pas en cours");
assert.strictEqual(nb.fermer, 1, "« fermer » ne compte que le livré");
assert.strictEqual(nb.mr, 1, "« merger » ne compte que les tickets qui ONT une MR ouverte");
// Le cas signalé : merger sans MR ne doit pas s'afficher.
assert.strictEqual(batchButtons(SEL2786, [], CFG2786).mr, 0,
  "aucune MR ouverte → aucun bouton merger");
assert.strictEqual(batchButtons(SEL2786, ["2"], CFG2786).mr, 1,
  "une ref sans préfixe RM est reconnue aussi");
// Lot homogène déjà livré : plus rien à faire faire à l'agent.
const livre = batchButtons([{ rm_id: "9", status: "a_tester_demandeur" }], [], CFG2786);
assert.strictEqual(livre.traiter + livre.atester + livre.etudier, 0,
  "sur un ticket déjà chez le demandeur, ni traiter ni à tester ni analyser");
assert.strictEqual(livre.fermer, 1, "…seule la fermeture reste");
// Statut inconnu : on n'ampute rien.
const inconnu2786 = batchButtons([{ rm_id: "1", status: "zzz_2786" }], [], CFG2786);
assert(inconnu2786.traiter === 1 && inconnu2786.fermer === 1,
  "un statut inconnu laisse les actions proposées (le plan écartera avec sa raison)");
assert.deepEqual(batchButtons([], [], CFG2786),
  { traiter: 0, atester: 0, etudier: 0, fermer: 0, mr: 0 }, "sélection vide → rien");
assert.doesNotThrow(() => batchButtons(null, null, null), "entrées molles tolérées");

// Fermeture en lot : chaque écarté porte sa raison.
const planClose = closeBatchPlan(SEL2786, CFG2786);
assert.strictEqual(planClose.count, 1, "un seul fermable");
assert.deepEqual(planClose.todo.map(t => t.rm_id), ["3"]);
assert.strictEqual(planClose.skipped.length, 2, "les deux autres sont écartés");
assert(planClose.skipped.every(t => t.why), "…chacun AVEC sa raison, jamais en silence");
assert(planClose.skipped.find(t => t.rm_id === "2").why.includes("livré"),
  "la raison dit pourquoi ce ticket-là ne se ferme pas");
assert.strictEqual(closeBatchPlan([{ rm_id: "7", status: "zzz" }], CFG2786).skipped[0].why
  .includes("zzz"), true, "un statut inconnu est écarté en le NOMMANT");

// Verdicts de la fiche : un verdict porte sur du travail livré.
assert.deepEqual(ticketVerdicts("en_cours", CFG2786), [],
  "aucun verdict sur un ticket en cours — fermer ce qui n'est pas fait n'a pas de sens");
assert.strictEqual(ticketVerdicts("a_tester_demandeur", CFG2786).length, 3,
  "les trois verdicts sur un ticket livré");
assert.deepEqual(ticketVerdicts("a_mep", CFG2786).map(v => v.kind), ["valider", "renvoyer"],
  "une MEP déjà demandée ne se re-demande pas");
assert.strictEqual(ticketVerdicts("statut_inconnu_2786", CFG2786).length, 3,
  "statut inconnu : on n'ampute rien");
assert.strictEqual(ticketVerdicts("", CFG2786).length, 3, "statut absent : idem");

// Câblage : les deux nouveaux boutons et la source unique de la règle.
["batch-etudier-btn", "batch-close-btn"].forEach(id =>
  assert(html.includes('id="' + id + '"'), "bouton manquant : " + id));
assert(/BATCH_MODES = \{[\s\S]*?etudier:/.test(html), "le mode `etudier` doit être connu du front");
assert(/batchButtons\(items, refs, CFG\)/.test(html),
  "l'affichage doit passer par la règle, pas par batchSel.size");
assert(!/b\.textContent = "▶ traiter \(" \+ batchSel\.size/.test(html),
  "l'ancien compteur (total coché) ne doit plus exister");
console.log("✓ actions pertinentes (RM2786) : analyser, fermer, et rien qui ne puisse agir");

// — RM2787 : depuis combien de temps une session s'est-elle tue —
const agoHM = grabO("agoHM", { Date, Math, String });
const maintenant2787 = Math.floor(Date.now() / 1000);
assert.strictEqual(agoHM(maintenant2787 - 42), "42s", "sous la minute : les secondes");
assert.strictEqual(agoHM(maintenant2787 - 12 * 60), "12min", "sous l'heure : les minutes");
// Le cœur de la demande : « 2h » couvrait cinquante-neuf minutes d'incertitude.
assert.strictEqual(agoHM(maintenant2787 - (2 * 3600 + 14 * 60)), "2h14",
  "au-delà de l'heure : heures ET minutes");
assert.strictEqual(agoHM(maintenant2787 - (2 * 3600 + 4 * 60)), "2h04",
  "les minutes sont sur deux chiffres — « 2h4 » se lit mal");
assert.strictEqual(agoHM(maintenant2787 - 3 * 3600), "3h",
  "une heure pile ne s'encombre pas d'un « 00 »");
assert.strictEqual(agoHM(maintenant2787 - 3 * 86400), "3j", "au-delà du jour, les jours");
assert.strictEqual(agoHM(maintenant2787 + 500), "0s", "une date future ne rend pas un négatif");
assert.strictEqual(agoHM(0), "", "absence d'horodatage → rien, pas « il y a 56 ans »");
assert.strictEqual(agoHM(null), "", "…y compris null");
// Le câblage : la donnée doit venir du serveur et être posée sur la tuile.
assert(/#\{session_name\}/.test(fs.readFileSync(
  path.join(__dirname, "..", "..", "..", "scripts", "karl-agent.py"), "utf8")),
  "le format tmux doit rester lisible côté serveur");
// RM2793 : la tuile délègue à `quietHtml`, qui préfère le dernier message réel
// à l'activité tmux (laquelle comptait les récapitulatifs automatiques).
assert(/quietHtml\(s, esc\)/.test(html),
  "la tuile doit afficher le silence de la session");
assert(/dernière sortie il y a/.test(html),
  "l'infobulle doit NOMMER la durée — « dernier message » promettrait autre chose");
assert(/ago\(s\.created\)/.test(html),
  "l'âge d'ouverture reste : les deux durées ne disent pas la même chose");
console.log("✓ silence d'une session (RM2787) : heures et minutes, distinct de l'âge d'ouverture");

// — RM2793 : le silence ne se remet pas à zéro sur un recap automatique —
const quietSince = grabO("quietSince");
const quietHtml = grabO("quietHtml", { quietSince: grabO("quietSince"), agoHM });

// Le dernier MESSAGE prime : c'est lui qui exclut les récapitulatifs auto.
assert.deepEqual(quietSince({ last_msg: 100, activity: 900 }), { ts: 100, exact: true },
  "le dernier message prime sur l'activité tmux, même plus récente");
assert.deepEqual(quietSince({ activity: 900 }), { ts: 900, exact: false },
  "sans transcript exploitable, l'activité tmux reste la mesure");
assert.deepEqual(quietSince({}), { ts: null, exact: false }, "aucune source → rien à afficher");
assert.deepEqual(quietSince(null), { ts: null, exact: false }, "session absente tolérée");

// Le rendu doit DIRE laquelle des deux mesures il montre : « dernier message »
// et « dernière sortie » ne recouvrent pas la même chose.
const qExact = quietHtml({ last_msg: Math.floor(Date.now() / 1000) - 3600 }, escO);
assert(/Dernier message il y a/.test(qExact), "mesure exacte : l'infobulle le dit");
assert(/récapitulatifs automatiques ne comptent pas/.test(qExact),
  "…et rappelle ce qui en est exclu");
assert(/⏳1h/.test(qExact), "la durée est affichée");
assert(!/~/.test(qExact), "aucune marque d'approximation sur une mesure exacte");
const qApprox = quietHtml({ activity: Math.floor(Date.now() / 1000) - 3600 }, escO);
assert(/Dernière sortie du terminal/.test(qApprox), "repli : l'infobulle le dit aussi");
assert(/⏳1h~/.test(qApprox), "…et la durée porte un « ~ », l'approximation se voit");
assert.strictEqual(quietHtml({}, escO), "", "rien à mesurer → rien d'affiché");
assert.strictEqual(quietHtml(null, escO), "", "session absente tolérée");
// Le câblage : la tuile passe par le helper, plus par s.activity en direct.
assert(/quietHtml\(s, esc\)/.test(html), "la tuile doit utiliser le helper");
assert(!/s\.activity \? '<span class="tquiet"/.test(html),
  "l'ancien affichage direct de l'activité tmux ne doit plus exister");
assert(/dernier message il y a/.test(html), "l'infobulle de tuile nomme la mesure");
console.log("✓ silence réel (RM2793) : les recaps automatiques ne remettent plus le compteur à zéro");

// — RM2795 : la marque d'épinglage, la même partout —
const pinMark = grabO("pinMark");
const TABS2795 = [
  { kind: "dash", key: "", label: "tableau de bord", pinned: true, fixed: true },
  { kind: "review", key: "2744", label: "RM2744", pinned: true },
  { kind: "session", key: "2673", label: "2673", pinned: false },
  { kind: "project", key: "calicote/infra", label: "calicote/infra", pinned: true },
];
assert(pinMark(TABS2795, "review", "2744").includes("📌"), "un ticket épinglé porte la marque");
assert(pinMark(TABS2795, "project", "calicote/infra").includes("📌"), "un projet épinglé aussi");
assert.strictEqual(pinMark(TABS2795, "session", "2673"), "",
  "un onglet ouvert mais NON épinglé n'est pas marqué — c'est l'épingle qu'on signale");
assert.strictEqual(pinMark(TABS2795, "review", "9999"), "", "un objet sans onglet n'est pas marqué");
assert.strictEqual(pinMark(TABS2795, "session", "2744"), "",
  "le type compte : une session et un ticket de même id sont deux objets");
// L'onglet permanent est épinglé par construction : le marquer n'aurait aucun sens.
assert.strictEqual(pinMark(TABS2795, "dash", ""), "",
  "l'onglet permanent n'est pas une épingle qu'on choisit");
assert.strictEqual(pinMark([], "review", "1"), "", "aucun onglet → aucune marque");
assert.strictEqual(pinMark(null, "review", "1"), "", "liste absente tolérée");
assert.strictEqual(pinMark(TABS2795, "review", 2744), "".length ? "" : pinMark(TABS2795, "review", "2744"),
  "un id numérique vaut son équivalent texte");
assert(/title="Épinglé dans les onglets/.test(pinMark(TABS2795, "review", "2744")),
  "l'infobulle dit ce que la marque signifie");

// Les cinq surfaces doivent appeler la MÊME fonction — cinq variantes d'un même
// signal, ce serait cinq signaux.
const surfaces2795 = [
  ['pinOf("session", s.rm_id)', "tuiles de session"],
  ['pinOf("review", rm)', "revues ouvertes"],
  ['pinOf("review", t.rm_id)', "résultats de recherche"],
  ['pinOf("review", e.rm_id)', "file à tester"],
  ['pinOf("review", it.rm_id)', "tickets ouverts"],
];
surfaces2795.forEach(([frag, quoi]) =>
  assert(html.includes(frag), "marque absente : " + quoi));
assert(/pin\("project", p\.value\)/.test(html), "marque absente : panneau projets");
assert(/pinOf\("review", String\(it\.ref/.test(html), "marque absente : worklog");
// …et l'état doit suivre le geste, sans attendre le prochain poll.
assert(/function togglePin[\s\S]{0,400}renderPinMarks\(\)/.test(html),
  "détacher un onglet doit rafraîchir les listes tout de suite");
assert(/opts && opts\.pin\) renderPinMarks/.test(html),
  "…et épingler à l'ouverture aussi");
// Le panneau projets reçoit la marque en option : sans elle, il rend comme avant.
const sansPin = projectsPanelHtml(groupProjectsByClient(PJ2760, ""),
  { live: {}, open: {}, client: "abatik", filtre: "" }, escO, jargFn);
assert(!/📌/.test(sansPin), "sans fonction de marque, le rendu est inchangé (rétrocompat)");
const avecPin = projectsPanelHtml(groupProjectsByClient(PJ2760, ""),
  { live: {}, open: {}, client: "abatik", filtre: "",
    pin: (k, v) => pinMark([{ kind: "project", key: "abatik/infra", pinned: true }], k, v) },
  escO, jargFn);
assert(/📌/.test(avecPin), "avec la marque, le projet épinglé la porte");
console.log("✓ marque d'épinglage (RM2795) : la même icône dans les listes, à jour au clic");

// — RM2796 : une seule pastille de statut, la dérive dans la couleur —
const statusPill = grabO("statusPill");
const neutre2796 = statusPill({ status: "en_cours" }, escO);
assert.strictEqual(neutre2796, '<span class="pill">en_cours</span>',
  "sans dérive : une pastille nue, aucune infobulle à lire pour rien");
const derive2796 = statusPill(
  { status: "a_tester_demandeur", opened_status: "en_cours", drifted: true }, escO);
assert(/class="pill warn"/.test(derive2796), "dérive : la couleur porte le signal");
assert(/>a_tester_demandeur</.test(derive2796), "le statut COURANT est ce qui s'affiche");
assert(!/en_cours →/.test(derive2796.replace(/title="[^"]*"/, "")),
  "l'ancien statut ne s'affiche plus dans la pastille — il ne s'y lisait pas");
assert(/title="[^"]*en_cours → a_tester_demandeur/.test(derive2796),
  "…il passe dans l'infobulle, avec le nouveau");
// Cas limites : rien ne doit produire de pastille bavarde ou fausse.
assert(!/warn/.test(statusPill({ status: "en_cours", opened_status: "en_cours", drifted: true }, escO)),
  "un « changement » vers le même statut n'est pas une dérive");
assert(!/warn/.test(statusPill({ status: "a_faire", drifted: true }, escO)),
  "dérive annoncée sans ancien statut : pas de promesse qu'on ne peut pas tenir");
assert.strictEqual(statusPill({}, escO), '<span class="pill">?</span>',
  "item vide : un statut inconnu se dit, il ne disparaît pas");
assert.strictEqual(statusPill(null, escO), '<span class="pill">?</span>', "item absent toléré");
assert(!/<b>/.test(statusPill({ status: "<b>x</b>" }, escO)), "le statut est échappé");
// Câblage : l'ancienne double pastille ne doit plus exister.
assert(/statusPill\(it, esc\)/.test(html), "le worklog doit passer par la fonction");
assert(!/const drift = it\.drifted/.test(html), "l'ancienne seconde pastille doit avoir disparu");
console.log("✓ statut du worklog (RM2796) : une pastille, la dérive en couleur et au survol");

// — RM2797 : description et historique en facettes, l'historique structuré —
const logEntries = grabO("logEntries");
const logHtml = grabO("logHtml");

const JOURNAL = [
  "## 2026-08-22T20:04 — report → Redmine",
  "note (commit 55ca4bda)",
  "",
  "## 2026-08-22T20:08 — Protocole de test remplacé",
  "Tokens : 0 | Durée : 0 min",
  "détail sur deux lignes",
].join("\n");

const ent2797 = logEntries(JOURNAL);
assert.strictEqual(ent2797.length, 2, "une entrée par en-tête ##");
assert.strictEqual(ent2797[0].ts, "2026-08-22T20:04", "l'horodatage est isolé");
assert.strictEqual(ent2797[0].title, "report → Redmine", "…et le titre aussi");
assert(ent2797[1].body.includes("détail sur deux lignes"), "le corps garde ses lignes");
assert(!ent2797[0].body.includes("##"), "l'en-tête ne se retrouve pas dans le corps");
// Robustesse : un journal n'est pas toujours bien formé.
assert.deepEqual(logEntries(""), [], "journal vide → aucune entrée");
assert.deepEqual(logEntries(null), [], "journal absent toléré");
const sansEntete = logEntries("juste du texte\nsans en-tête");
assert.strictEqual(sansEntete.length, 1, "un journal sans en-tête n'est pas perdu");
assert(sansEntete[0].body.includes("juste du texte"), "…son contenu est conservé");
assert.strictEqual(logEntries("## titre sans horodatage")[0].title, "titre sans horodatage",
  "un en-tête sans horodatage garde son titre");
assert.strictEqual(logEntries("## titre sans horodatage")[0].ts, "",
  "…et n'invente pas de date");

// Rendu : la plus récente en tête — on ouvre l'historique pour voir ce qui vient
// de se passer, pas pour relire le début.
const lh = logHtml(ent2797, escO, (x) => "<MD>" + x + "</MD>");
assert(lh.indexOf("20:08") < lh.indexOf("20:04"), "la plus récente est en tête");
assert(/<MD>/.test(lh), "le corps passe par le rendu markdown, plus par un bloc préformaté");
assert(/class="logent-ts"/.test(lh), "l'horodatage est distingué du titre");
assert(logHtml([], escO, String).includes("aucune activité"),
  "sans activité, un message — pas un cadre vide");
assert(logHtml(null, escO, String).includes("aucune activité"), "liste absente tolérée");
assert(!/<script>/.test(logHtml(logEntries("## <script>x</script> — t"), escO, String)),
  "les en-têtes sont échappés");

// Câblage : les deux facettes existent, et « détail » ne répète plus les blocs.
assert(/\["desc", "description"\]/.test(html), "facette description absente");
assert(/\["log", "historique"\]/.test(html), "facette historique absente");
assert(/facet === "desc"/.test(html) && /facet === "log"/.test(html),
  "les facettes doivent être routées");
assert(!/<h4>Dernières activités<\/h4><div class="logtail">/.test(html),
  "le bloc bridé de 130 px ne doit plus exister dans « détail »");
assert(/setTicketFacet\(\\?'desc\\?'\)/.test(html) && /setTicketFacet\(\\?'log\\?'\)/.test(html),
  "« détail » doit renvoyer vers les deux facettes");
assert(/\.facetfull \{[^}]*max-height: none/.test(html),
  "une facette doit pouvoir occuper toute la hauteur");
// RM2806 : …et l'annoncer ne suffit pas — cf. le bloc RM2806 plus bas, qui
// vérifie que la facette n'emprunte plus la classe qui écrasait cette règle.
console.log("✓ fiche ticket (RM2797) : description et historique en facettes, journal structuré");

// — RM2798 : le worklog groupé par client / projet —
const groupWorklogItems = grabO("groupWorklogItems", { Map });
const worklogGroupedHtml = grabO("worklogGroupedHtml", { Map, groupWorklogItems: grabO("groupWorklogItems", { Map }) });

const WL2798 = [
  { ref: "RM1", client: "calicote", project: "presta" },
  { ref: "RM2", client: "abatik", project: "infra" },
  { ref: "RM3", client: "calicote", project: "presta" },
  { ref: "RM4" },                                    // chantier libre
];
const g2798 = groupWorklogItems(WL2798);
// L'ordre des GROUPES est celui de leur première apparition — pas alphabétique :
// c'est un rendu, pas un tri, et la session a son propre ordre de travail.
assert.deepEqual(g2798.map(x => x.key), ["calicote / presta", "abatik / infra", "hors projet"],
  "groupes dans l'ordre d'apparition, « hors projet » en dernier");
assert.deepEqual(g2798[0].items.map(i => i.ref), ["RM1", "RM3"],
  "l'ordre DANS un groupe reste celui de la session");
assert.strictEqual(g2798[2].items[0].ref, "RM4", "un ticket sans projet n'est pas perdu");
// Cas partiels : ne jamais fabriquer un « client / » ou un « / projet ».
assert.strictEqual(groupWorklogItems([{ ref: "A", project: "infra" }])[0].key, "infra",
  "projet seul : pas de séparateur orphelin");
assert.strictEqual(groupWorklogItems([{ ref: "A", client: "abatik" }])[0].key, "abatik",
  "client seul : idem");
assert.deepEqual(groupWorklogItems([]), [], "aucun item → aucun groupe");
assert.deepEqual(groupWorklogItems(null), [], "liste absente tolérée");

// Rendu : un seul groupe ne s'annonce pas.
const rendu = (it) => "<i>" + it.ref + "</i>";
const mono = worklogGroupedHtml(
  [{ ref: "RM1", client: "c", project: "p" }, { ref: "RM2", client: "c", project: "p" }],
  rendu, escO);
assert.strictEqual(mono, "<i>RM1</i><i>RM2</i>",
  "un worklog mono-projet n'affiche aucun en-tête — il coûterait une ligne pour rien");
const multi = worklogGroupedHtml(WL2798, rendu, escO);
assert(/class="wlghead">calicote \/ presta/.test(multi), "en-tête du groupe");
assert(/<span class="gcnt">2<\/span>/.test(multi), "…avec son compte");
assert(multi.indexOf("calicote") < multi.indexOf("abatik"), "ordre d'apparition conservé");
assert(multi.indexOf("hors projet") > multi.indexOf("abatik"), "« hors projet » ferme la marche");
assert.strictEqual(worklogGroupedHtml([], rendu, escO), "", "aucun item → rien");
// Câblage : le rendu des buckets doit passer par le groupement.
assert(/worklogGroupedHtml\(s\.items, itemHtml, esc\)/.test(html),
  "chaque bucket doit être groupé");
assert(!/bucketHtml\[s\.key\] = s\.items\.map\(itemHtml\)\.join/.test(html),
  "l'ancien rendu à plat ne doit plus exister");
console.log("✓ worklog groupé (RM2798) : par client/projet, ordre de session préservé");

// — RM2799 : hiérarchie de lecture — la section, puis le numéro, puis le statut —
// Le groupe doit être une SECTION : sans délimitation, son en-tête se lisait
// comme une ligne de plus.
const cssGroup2799 = /\.wlgroup \{[^}]*\}/.exec(html);
assert(cssGroup2799, ".wlgroup introuvable");
assert(/border:/.test(cssGroup2799[0]) && /background:/.test(cssGroup2799[0]),
  "un groupe doit se distinguer par un fond ET une bordure");
const cssHead2799 = /\.wlghead \{[^}]*\}/.exec(html);
assert(/background:/.test(cssHead2799[0]) && /border-bottom:/.test(cssHead2799[0]),
  "l'en-tête doit appartenir à la section, pas flotter au-dessus");

// Le numéro identifie la ligne : il doit primer sur le statut, y compris jaune.
const cssRef2799 = /\.rmref \{[^}]*\}/.exec(html);
assert(cssRef2799, ".rmref introuvable — le numéro doit avoir son propre style");
const cssPill2799 = /\n  \.pill \{[^}]*\}/.exec(html);
const taille = (css) => parseFloat((/font-size: ([\d.]+)px/.exec(css) || [])[1]);
assert(taille(cssRef2799[0]) > taille(cssPill2799[0]),
  "le numéro doit être PLUS GRAND que la pastille de statut");
assert(/font-weight: 600/.test(cssRef2799[0]), "…et plus gras");
assert(/color: var\(--accent\)/.test(cssRef2799[0]), "…et en couleur d'accent");
assert(/font-family: var\(--mono\)/.test(cssRef2799[0]),
  "…en chasse fixe : un identifiant se lit comme un identifiant");
// Le signal de dérive ne doit pas disparaître pour autant.
assert(/class="pill warn"/.test(statusPill(
  { status: "a_mep", opened_status: "en_cours", drifted: true }, escO)),
  "le statut jaune reste le signal de dérive — il cesse d'écraser, il ne s'efface pas");
// Le numéro reste un point d'entrée vers la fiche.
const ref2799 = worklogRefHtml("RM2799", escId, () => ' title="x"');
assert(/showTicket\(2799\)/.test(ref2799), "le numéro reste cliquable");
assert(/title="x"/.test(ref2799), "…et garde son infobulle");
assert(!/class="pill"/.test(ref2799), "…sans reprendre le style de la pastille");
console.log("✓ lisibilité du worklog (RM2799) : sections délimitées, numéro qui prime sur le statut");

// — RM2801 : l'état de la MR sur la ligne du ticket —
const mrStageHtml = grabO("mrStageHtml");
// Un ticket sans MR ne rend RIEN : l'absence n'est pas un état à afficher sur
// chaque ligne d'une colonne étroite.
assert.strictEqual(mrStageHtml(null, escO, jargFn), "", "pas de MR → rien");
assert.strictEqual(mrStageHtml({}, escO, jargFn), "", "étape absente → rien");
assert.strictEqual(mrStageHtml({ stage: "inconnue" }, escO, jargFn), "",
  "étape inconnue → rien plutôt qu'un badge muet");
// Les trois étapes se distinguent, et disent ce qu'elles attendent.
const ouv = mrStageHtml({ stage: "open", url: "https://g/mr/1", count: 1,
  mrs: [{ iid: "1", state: "opened", target: "dev" }] }, escO, jargFn);
assert(/⇥ MR/.test(ouv) && /pill warn/.test(ouv), "MR ouverte : signalée comme un reste à faire");
assert(/à merger/.test(ouv), "…et l'infobulle dit quoi en faire");
const integ = mrStageHtml({ stage: "integration", url: "u", count: 1, mrs: [] }, escO, jargFn);
assert(/✓ dev/.test(integ) && /pill ok/.test(integ), "mergée dans l'intégration");
// La promotion est une MR de LOT, hors ticket : l'infobulle le dit, sinon
// « ✓ dev » se lirait comme une promotion oubliée.
assert(/par lot \(dev → main\)/.test(integ), "…et ce qui reste à faire est dit");
const prod = mrStageHtml({ stage: "prod", url: "u", count: 1, mrs: [] }, escO, jargFn);
assert(/✓ prod/.test(prod), "promue en production");
// Plusieurs MR : le détail au survol, pas sur la ligne.
const multi2801 = mrStageHtml({ stage: "prod", url: "u", count: 2,
  mrs: [{ iid: "1", state: "merged", target: "dev", repo: "a/b" },
        { iid: "2", state: "merged", target: "main" }] }, escO, jargFn);
assert(/!1 merged → dev/.test(multi2801) && /!2 merged → main/.test(multi2801),
  "chaque MR est détaillée dans l'infobulle");
assert(/2 MR/.test(multi2801), "…et le nombre est annoncé");
assert(!/!1/.test(multi2801.replace(/title="[^"]*"/, "")),
  "le détail reste DANS l'infobulle — la ligne n'a pas la place");
// Le badge mène à la MR, sans déclencher le clic de la ligne.
assert(/window\.open\('https:\/\/g\/mr\/1'/.test(ouv), "le badge ouvre la MR");
assert(/event\.stopPropagation/.test(ouv), "…sans ouvrir aussi la fiche du ticket");
assert(!/window\.open/.test(mrStageHtml({ stage: "prod", count: 1, mrs: [] }, escO, jargFn)),
  "sans URL connue, pas de lien mort");
// Câblage : la ligne du worklog doit porter le badge.
assert(/mrStageHtml\(\(worklog\.mr_stage \|\| \{\}\)\[it\.ref\], esc, jarg\)/.test(html),
  "chaque ligne de ticket doit afficher l'étape de sa MR");
console.log("✓ étape de MR (RM2801) : ouverte, intégration, production — sur la ligne du ticket");

// — RM2806 : la facette description n'emprunte plus le style du bloc encadré —
// Le piège corrigé ici est un piège de CASCADE : `.facetfull { max-height: none }`
// existait bien, mais `.desc { max-height: 160px }` est déclarée plus loin, à
// spécificité égale — elle gagnait, et la bride annoncée levée ne l'a jamais été.
// Un test qui se contenterait de chercher `max-height: none` dans la page serait
// passé au vert sur du code inerte : on vérifie donc que la facette n'utilise
// plus la classe en conflit.
const mDescFacet = /function _ticketDescHtml\([\s\S]*?\n\}/.exec(html);
assert(mDescFacet, "_ticketDescHtml introuvable");
assert(!/class="facetfull desc"/.test(mDescFacet[0]),
  "la facette ne doit plus reprendre `.desc` — c'est elle qui bridait à 160 px");
assert(/descfull/.test(mDescFacet[0]), "…mais une classe qui lui est propre");
assert(/mdview/.test(mDescFacet[0]), "…et le rendu markdown standard");
const cssDescFull = /\.descfull \{[^}]*\}/.exec(html);
assert(cssDescFull, ".descfull introuvable");
assert(/background: none/.test(cssDescFull[0]) && /border: 0/.test(cssDescFull[0]),
  "ni fond ni bordure : la description occupe la zone, elle n'est pas encadrée");
assert(/max-height: none/.test(cssDescFull[0]) && /overflow: visible/.test(cssDescFull[0]),
  "aucune bride : c'est la colonne qui défile");
// …et le bloc encadré d'origine doit rester intact là où il sert encore.
const cssDesc2806 = /\n  \.desc \{[^}]*\}/.exec(html);
assert(cssDesc2806 && /max-height: 160px/.test(cssDesc2806[0]),
  "le bloc `.desc` d'origine n'a pas à changer : il sert ailleurs");
// Le piège de cascade, une seconde fois : `.descfull` ne doit pas redéclarer ce
// que `.mdview` porte, sous peine de reproduire le conflit qu'on vient de régler.
assert(!/font-size/.test(cssDescFull[0]) && !/line-height/.test(cssDescFull[0]),
  "`.descfull` ne redéclare pas ce que `.mdview` porte déjà");
console.log("✓ facette description (RM2806) : plus de cadre ni de bride, la colonne défile");
// — pile de refresh (RM2763) : specs par période, dispatch par bloc, briefs —
const mRefresh = />>> refresh[\s\S]*?(const REFRESH_PERIOD_MS[\s\S]*?)\n\/\/ <<< refresh/.exec(html);
assert(mRefresh, "marqueurs >>> refresh / <<< refresh introuvables");
(async () => {
  const calls = { api: [], health: [], ko: [], sessions: [], worklog: 0 };
  const ctx = {
    Date, Object, Promise, JSON, encodeURIComponent,
    attached: null, worklog: null,
    rightVisible: () => true, dashVisible: () => false,
    resolveCache: {}, resolveAt: {},
    pendStale: null, pendStaleSet: (e) => new Set((e || []).map(x => x.rm_id)),
    api: async (u) => { calls.api.push(u); return ctx._resp; },
    renderHealth: (h) => calls.health.push(h),
    renderHealthKo: (m) => calls.ko.push(m),
    renderSessions: (s) => calls.sessions.push(s),
    renderWorklog: () => { calls.worklog++; },
  };
  vm.createContext(ctx);
  vm.runInContext(mRefresh[1], ctx, { filename: "refresh-block" });

  // specs : sessions à chaque tick (période 0), worklog seulement si attaché
  let specs = vm.runInContext("refreshSpecs([])", ctx);
  assert.deepStrictEqual([...specs], ["sessions:", "health:", "pending:", "vault:", "envcheck:", "coreupdate:"],
    "1er tick : tous les blocs dus, sauf worklog (détaché) et dashboard (non visible)");
  ctx.attached = "2763";
  specs = vm.runInContext("refreshSpecs([])", ctx);
  assert.strictEqual([...specs].pop(), "worklog:2763:", "attaché : le worklog embarque");

  // fetch : dispatch des blocs reçus + mémorisation des hashs
  ctx._resp = { blocks: {
    sessions: { hash: "s1", data: { sessions: [{ rm_id: "2763" }], briefs: { 2763: { found: true, title: "T" } } } },
    health: { hash: "h1", data: { sessions: 1, tmux: true } },
    worklog: { hash: "w1", data: { rm_id: "2763", found: true } },
    pending: { hash: "p1", data: { entries: [{ rm_id: "2763", kind: "stale" }] } },
  }, skipped: [], errors: {} };
  await vm.runInContext("refreshFetch([])", ctx);
  assert.strictEqual(calls.api.length, 1, "UNE requête composite");
  assert.strictEqual(calls.sessions.length, 1, "bloc sessions dispatché");
  assert.strictEqual(calls.health.length, 1, "bloc health dispatché");
  assert.strictEqual(calls.worklog, 1, "bloc worklog dispatché");
  assert(ctx.resolveCache["2763"] && ctx.resolveCache["2763"].partial, "brief semé en partial");
  assert(ctx.pendStale && ctx.pendStale.has("2763"), "bloc pending dispatché (pendStale recalculé)");

  // tick suivant AVANT les périodes health/worklog : seul sessions repart, avec son hash
  specs = vm.runInContext("refreshSpecs([])", ctx);
  assert.deepStrictEqual([...specs], ["sessions:s1"], "périodes respectées + hash mémorisé");
  // une action force un bloc hors période
  specs = vm.runInContext('refreshSpecs(["health"])', ctx);
  assert(specs.includes("health:h1"), "include force le bloc avec son hash");

  // blocs inchangés (skipped) : aucun re-rendu
  ctx._resp = { blocks: {}, skipped: ["sessions"], errors: {} };
  await vm.runInContext("refreshFetch([])", ctx);
  assert.strictEqual(calls.sessions.length, 1, "inchangé → pas de re-rendu");

  // worklog d'une session quittée entre-temps : jeté ; échec réseau → dot ko
  ctx._resp = { blocks: { worklog: { hash: "w2", data: { rm_id: "999", found: true } } }, skipped: [], errors: {} };
  await vm.runInContext('refreshFetch(["worklog"])', ctx);
  assert.strictEqual(calls.worklog, 1, "worklog d'une autre session jeté");
  ctx.api = async () => { throw new Error("down"); };
  await vm.runInContext("refreshFetch([])", ctx);
  assert.strictEqual(calls.ko.length, 1, "échec réseau → renderHealthKo");

  // seedBriefs ne dégrade jamais une résolution riche
  ctx.resolveCache["42"] = { found: true, title: "riche", cwd: "/x" };
  vm.runInContext('seedBriefs({ 42: { found: true, title: "brief" } })', ctx);
  assert.strictEqual(ctx.resolveCache["42"].title, "riche", "une entrée riche n'est pas écrasée");
  console.log("✓ pile de refresh (RM2763) : specs par période, dispatch par bloc, briefs partial");
})().catch((e) => { console.error("✗ pile de refresh (RM2763) :", e.message); process.exit(1); });

// — RM2816 : « commandes pm » et « réglages » quittent la colonne de gauche —
// Deux surfaces d'action (pas de consultation) qui prenaient deux onglets sur
// huit à la barre de gauche, dans une colonne trop étroite pour leurs
// formulaires. Elles passent au menu du haut et s'ouvrent au centre.
const nav2816 = /<nav class="lnav">[\s\S]*?<\/nav>/.exec(html);
assert(nav2816, "barre d'onglets de la colonne gauche introuvable");
assert(!/data-panel="pm"/.test(nav2816[0]) && !/data-panel="settings"/.test(nav2816[0]),
  "les deux onglets ne doivent plus être dans la colonne de gauche");
const head2816 = /<header>[\s\S]*?<\/header>/.exec(html)[0];
assert(/openCenterPanel\('pm'\)/.test(head2816) && /openCenterPanel\('settings'\)/.test(head2816),
  "les deux entrées doivent vivre dans le menu principal du haut");
// Le contenu déménage tel quel : une carte oubliée derrière serait invisible.
const pane2816 = /<div id="panelpane"[\s\S]*?<!-- \/#panelpane -->/.exec(html);
assert(pane2816, "conteneur central des panneaux (#panelpane) introuvable");
["pmcard", "authcard", "userscard", "voicecard", "themecard", "rightcard",
 "sessprefcard", "reglages-card"].forEach(id =>
  assert(pane2816[0].includes('id="' + id + '"'), "carte perdue au déplacement : " + id));
assert(pane2816[0].includes('id="cp-pm"') && pane2816[0].includes('id="cp-settings"'),
  "les deux panneaux centraux doivent être distincts (un visible à la fois)");
const left2816 = /<section class="left">[\s\S]*?<\/section>/.exec(html)[0];
assert(!left2816.includes('id="panelpane"') && !left2816.includes('id="pmcard"')
  && !left2816.includes('id="reglages-card"'),
  "plus rien de ces panneaux ne doit rester dans la colonne de gauche");
// …et il est bien dans la zone centrale, avec les autres vues.
const termarea2816 = /<div class="termarea">[\s\S]*?<div id="panelpane"/.exec(html);
assert(termarea2816, "#panelpane doit vivre dans la zone centrale (.termarea)");
const loaders2816 = /const PANEL_LOADERS = \{[^}]*\}/.exec(html)[0];
assert(!/\bpm:/.test(loaders2816) && !/\bsettings:/.test(loaders2816),
  "les loaders de la colonne gauche ne doivent plus référencer pm/settings");

// L'onglet central : icône propre à chaque panneau, infobulle qui dit la surface.
assert.strictEqual(tabTooltip({ kind: "pm", key: "", label: "commandes pm" }, {}, parseViewKey),
  "commandes PM", "infobulle de l'onglet commandes pm");
assert.strictEqual(tabTooltip({ kind: "settings", key: "", label: "réglages" }, {}, parseViewKey),
  "réglages du cockpit", "infobulle de l'onglet réglages");
const tabs2816 = renderCenterTabs(
  [{ kind: "pm", key: "", label: "commandes pm", pinned: true },
   { kind: "settings", key: "", label: "réglages", pinned: false }],
  "settings:", escFn, jargFn, {}, parseViewKey);
assert(/<span>⚙<\/span><span class="lbl">commandes pm<\/span>/.test(tabs2816),
  "l'onglet commandes pm garde son icône");
assert(/<span>🔧<\/span><span class="lbl">réglages<\/span>/.test(tabs2816),
  "l'onglet réglages garde son icône");
assert(!/•<\/span><span class="lbl">réglages/.test(tabs2816), "pas d'icône générique");

// Réactiver l'onglet (clic, restauration au boot) rouvre le panneau central.
const act2816 = /(function activateTab\([\s\S]*?\n\})/.exec(html);
assert(act2816, "activateTab introuvable");
const ctx2816 = { centerTabs: [{ kind: "pm", key: "" }, { kind: "settings", key: "" }],
                  calls: [], parseViewKey };
["attach", "openReview", "openProjectView", "openNewTicket", "openDashboard",
 "openCenterFile", "openCenterDir", "openCenterCommit", "openCenterMail",
 "openCenterClient", "openCenterConf"].forEach(n => { ctx2816[n] = () => ctx2816.calls.push(n); });
ctx2816.openCenterPanel = (n) => ctx2816.calls.push("panel:" + n);
vm.runInNewContext(act2816[1] + "\nactivateTab('pm:');activateTab('settings:');", ctx2816);
assert.deepStrictEqual(ctx2816.calls, ["panel:pm", "panel:settings"],
  "réactiver l'onglet doit rouvrir le panneau central correspondant");

// Le panneau central cède la place aux autres vues, et réciproquement.
["function attach(", "function openReview(", "async function openProjectView(",
 "function openNewTicket(", "function centerViewPane(", "function openDashboard("].forEach(sig => {
  const i = html.indexOf(sig);
  assert(i > 0, "fonction introuvable : " + sig);
  const corps = html.slice(i, i + 1400);
  assert(corps.includes("closeCenterPanel()"), sig + " doit fermer le panneau central");
});
// …et son propre ouvreur ferme les autres.
const ocp2816 = /function openCenterPanel\([\s\S]*?\n\}/.exec(html);
assert(ocp2816, "openCenterPanel introuvable");
["closeCenterView()", "closeNewTicket()", "closeProjectView()", "noteTab(", "renderCurTitle()"]
  .forEach(s => assert(ocp2816[0].includes(s), "openCenterPanel doit appeler " + s));
// Le retour au tableau de bord ne doit pas passer par-dessus un panneau ouvert.
["function closeNewTicket(", "function closeProjectView("].forEach(sig => {
  const i = html.indexOf(sig);
  const corps = html.slice(i, i + 700);
  assert(/!centerPanel/.test(corps), sig + " doit tenir compte du panneau central ouvert");
});
// Démarrage « auth requise sans jeton » : on atterrit toujours sur les réglages.
assert(/CFG\.auth_required && !token\(\)[\s\S]{0,200}openCenterPanel\("settings"\)/.test(html),
  "auth requise sans jeton doit ouvrir les réglages au centre");
console.log("✓ commandes pm & réglages (RM2816) : menu du haut, contenu en onglet central");

// — RM2821 : « ⬆ MAJ dispo » en bout de rangée —
// Bouton intermittent (il n'apparaît que quand une MAJ existe) : au milieu de la
// barre, son apparition décalait tous les suivants juste au moment où on visait
// autre chose. Dernier de la rangée, il ne pousse plus personne.
const head2821 = /<header>[\s\S]*?<\/header>/.exec(html)[0];
const btns2821 = [...head2821.matchAll(/<button[^>]*\bid="([^"]+)"/g)].map(m => m[1]);
assert(btns2821.includes("updbtn"), "le bouton MAJ doit rester dans le header");
assert.strictEqual(btns2821[btns2821.length - 1], "updbtn",
  "« MAJ dispo » doit être le DERNIER bouton du header (ordre : " + btns2821.join(", ") + ")");
// Rien d'autre ne bouge : même déclencheur, même clic, même infobulle.
assert(/<button class="mini" id="updbtn" style="display:none" onclick="showCoreUpdate\(\)"/.test(html),
  "le bouton MAJ garde son comportement (masqué par défaut, showCoreUpdate au clic)");
assert(/id="updbtn"[\s\S]{0,200}Une mise à jour du code PM est disponible/.test(html),
  "…et son infobulle");
console.log("✓ MAJ dispo (RM2821) : dernier bouton du header, son apparition ne décale plus rien");

// — RM2823 : sortir des tickets d'une session vers une session dédiée —
// Une session est ancrée sur UN projet ; le fil, lui, ramasse des tickets
// d'ailleurs. Le lot part alors dans une session neuve, ancrée sur LEUR projet.
const offloadPlan = grabO("offloadPlan");
const RC2823 = {
  "10": { found: true, client: "acme", project: "boutique", cwd: "/w/acme/boutique" },
  "11": { found: true, client: "acme", project: "boutique", cwd: "/w/acme/boutique" },
  "20": { found: true, client: "beta", project: "api", cwd: "/w/beta/api" },
  "30": { found: false },
};
const homogene = offloadPlan([{ rm_id: "10" }, { rm_id: "11" }], RC2823);
assert.strictEqual(homogene.mixed, false, "même projet → pas de mélange");
assert.strictEqual(homogene.targets.map(t => t.rm_id).join(","), "10,11", "les deux partent");
assert.strictEqual(homogene.client, "acme", "client du lot");
assert.strictEqual(homogene.project, "boutique", "projet du lot");
assert.strictEqual(homogene.cwd, "/w/acme/boutique", "cwd repris du ticket, pas deviné");
assert.strictEqual(homogene.anchor, "10", "l'ancrage est le premier ticket du lot");

const melange = offloadPlan([{ rm_id: "10" }, { rm_id: "20" }], RC2823);
assert.strictEqual(melange.mixed, true, "deux projets → refus : la session n'aurait pas d'ancrage");
assert.strictEqual(melange.projects.slice().sort().join(" "), "acme/boutique beta/api",
  "…et le refus doit NOMMER les projets en présence");

const inconnu = offloadPlan([{ rm_id: "10" }, { rm_id: "30" }], RC2823);
assert.strictEqual(inconnu.blocked.map(t => t.rm_id).join(","), "30",
  "ticket sans projet résolu : il reste sur place");
assert.strictEqual(inconnu.targets.map(t => t.rm_id).join(","), "10", "…et n'empêche pas les autres de partir");
assert.strictEqual(inconnu.mixed, false, "un ticket non résolu n'est pas un second projet");
assert.strictEqual(offloadPlan([], RC2823).targets.length, 0, "sélection vide");
assert.strictEqual(offloadPlan([{ rm_id: "30" }], RC2823).anchor, null,
  "aucun ticket embarquable → pas d'ancrage, donc rien à lancer");
// un ticket coché sous la forme « RM10 » (référence de worklog) doit être compris
assert.strictEqual(offloadPlan([{ rm_id: "RM10" }], RC2823).anchor, "10",
  "la référence RM<id> est normalisée");

// Câblage
assert(/id="batch-offload-btn"/.test(html), "le bouton d'embarquement doit exister");
const off2823 = /async function offloadToNewSession\([\s\S]*?\n\}/.exec(html);
assert(off2823, "offloadToNewSession introuvable");
// RM2831 a factorisé le lancement : la garantie porte désormais sur le chemin
// partagé, que ce geste emprunte.
const shared2823 = /async function spawnBatchSession\([\s\S]*?\n\}/.exec(html);
assert(shared2823, "chemin partagé de lancement introuvable");
assert(/\/worklog\/batch/.test(shared2823[0]) && /dry_run/.test(shared2823[0]),
  "la consigne doit venir du serveur (dry_run), pas d'un second générateur dans le front");
assert(/\/spawn/.test(shared2823[0]), "…et la session être créée par l'endpoint existant");
assert(/spawnBatchSession\(/.test(off2823[0]), "le geste du worklog emprunte ce chemin");
assert(/openedForget\(/.test(off2823[0]),
  "les tickets embarqués quittent la liste des tickets ouverts de la session d'origine");
console.log("✓ embarquer un lot ailleurs (RM2823) : un seul projet, consigne du serveur, session neuve");
// — RM2818 : alerter avant d'ouvrir une 2e session sur un ticket déjà pris —
// Deux agents sur le même ticket, c'est un worktree, une branche et un statut
// Redmine disputés — et on ne s'en aperçoit qu'après. Le serveur refuse déjà
// (409) une seconde session ANCRÉE ; ce qui passait sans bruit, c'est le ticket
// traité par une session ancrée AILLEURS (registre, worklog) — le cas courant.
const _effDisp2818 = grabO("effDisposition");
const ticketBusySessions = grabO("ticketBusySessions", { effDisposition: _effDisp2818 });
const P2818 = { handled: [
  { sid: "2700", alive: true,  state: "working", disposition: "",        title: "en cours" },
  { sid: "cockpit", alive: true, state: "idle",  disposition: "termine", title: "fini" },
  { sid: "vieille", alive: false, state: "ghost", disposition: "",       title: "hier" },
  { sid: "parke", alive: true,  state: "idle",   disposition: "parke",   title: "parké" },
] };
const b2818 = ticketBusySessions(P2818);
assert.deepStrictEqual(b2818.alive.map(s => s.sid), ["2700", "parke"],
  "vivantes non terminées : celle qui travaille et celle qui est parkée (parké ≠ terminé)");
assert.deepStrictEqual(b2818.stopped.map(s => s.sid), ["vieille"],
  "éteinte non terminée : signalée, mais elle n'occupe rien");
assert(!b2818.alive.some(s => s.sid === "cockpit"),
  "une session MARQUÉE terminée ne doit rien déclencher — c'est tout l'intérêt du marquage");
const vide2818 = (p) => { const r = ticketBusySessions(p); return !r.alive.length && !r.stopped.length; };
assert(vide2818(null), "payload absent → rien");
assert(vide2818({}), "payload sans handled → rien");
assert(vide2818({ handled: [] }),
  "aucune session : aucune alerte, le cas nominal reste sans friction");
// `state` prime sur la marque : une session qui travaille n'est jamais « terminée »
assert.deepStrictEqual(
  ticketBusySessions({ handled: [{ sid: "x", alive: true, state: "attention", disposition: "termine" }] })
    .alive.map(s => s.sid), ["x"],
  "une session qui attend une réponse compte, quelle que soit sa marque");

// Le texte d'alerte doit NOMMER ce qu'il a trouvé (sinon on confirme à l'aveugle)
const dupText = grabO("duplicateSessionText", { effDisposition: _effDisp2818 });
const txt2818 = dupText("2816", b2818);
assert(txt2818.includes("2700") && txt2818.includes("parke"), "les sessions vivantes sont nommées");
assert(txt2818.includes("RM2816"), "le ticket est nommé");
assert(/éteinte/i.test(txt2818), "les sessions éteintes sont mentionnées, pas tues");

// Câblage : les DEUX points de lancement passent par la garde
["async function spawnTicketSession(", "async function spawn("].forEach(sig => {
  const i = html.indexOf(sig);
  assert(i > 0, "fonction introuvable : " + sig);
  const corps = html.slice(i, i + 2200);
  assert(/confirmSecondSession\(/.test(corps), sig + " doit passer par confirmSecondSession");
});
const css2818 = /async function confirmSecondSession\([\s\S]*?\n\}/.exec(html);
assert(css2818, "confirmSecondSession introuvable");
assert(/ensureTicketSessions\(.*true\)/.test(css2818[0]),
  "l'état des sessions du ticket doit être RELU (un cache périmé dirait « libre » à tort)");
assert(/attach\(/.test(css2818[0]), "…et proposer de REJOINDRE la session existante");
console.log("✓ 2e session sur un ticket pris (RM2818) : alerte nommée, rejoindre plutôt que doubler");
// — RM2819 : cliquer l'onglet d'une session éteinte doit la RELANCER —
// Un onglet épinglé survit à ce qu'il montrait : la session peut être vivante,
// seulement enregistrée (fantôme), ou avoir disparu. On attachait dans les trois
// cas — terminal vide dans deux d'entre eux, sans rien dire.
const sessionTabAction = grabO("sessionTabAction");
const S2819 = [
  { rm_id: "100", state: "working" },
  { rm_id: "200", ghost: true, engine: "claude", session_id: "abc", resumable: true },
  // même id, deux entrées (un fantôme du jeu + la session relancée) : la vivante prime
  { rm_id: "300", ghost: true }, { rm_id: "300", state: "idle" },
];
assert.strictEqual(sessionTabAction("100", S2819).action, "attach", "session vivante → attach");
const r2819 = sessionTabAction("200", S2819);
assert.strictEqual(r2819.action, "relaunch", "session enregistrée non démarrée → relance");
assert.strictEqual(r2819.session.session_id, "abc",
  "…avec SON entrée : relaunchGhost a besoin de engine/session_id");
assert.strictEqual(sessionTabAction("300", S2819).action, "attach",
  "un fantôme homonyme ne doit pas masquer la session vivante");
assert.strictEqual(sessionTabAction("999", S2819).action, "missing", "inconnue → on le dit");
assert.strictEqual(sessionTabAction("100", {}).action, "missing", "cache vide → inconnue");
// sessCache est un objet {rm_id: session}, la réponse /sessions un tableau : les deux passent
const parCle = { "200": { rm_id: "200", ghost: true } };
assert.strictEqual(sessionTabAction("200", parCle).action, "relaunch",
  "la fonction accepte le cache indexé comme la liste");
assert.strictEqual(sessionTabAction(200, parCle).action, "relaunch", "id numérique accepté");

// Câblage : l'onglet passe par le routeur, plus par attach() en direct.
const act2819 = /(function activateTab\([\s\S]*?\n\})/.exec(html)[1];
assert(/t\.kind === "session"\) openSessionTab\(/.test(act2819),
  "activateTab doit router la session vers openSessionTab");
const ost2819 = /async function openSessionTab\([\s\S]*?\n\}/.exec(html);
assert(ost2819, "openSessionTab introuvable");
// Le cache ne voit que le jeu courant : ne pas conclure à la disparition sans redemander.
assert(/\/sessions\?ghosts=1/.test(ost2819[0]),
  "openSessionTab doit relire la liste COMPLÈTE avant de conclure à l'absence");
assert(/relaunchGhost\(/.test(ost2819[0]), "…et déléguer la relance au chemin existant");
assert(/toastAction\(/.test(ost2819[0]), "…et proposer de fermer l'onglet d'une session disparue");
console.log("✓ onglet de session éteinte (RM2819) : relance au clic, jamais un terminal vide");

// — RM2834 : filtre par client dans « Reprendre une session » —
// La liste des projets était PLATE : tous les clients mêlés, des dizaines
// d'entrées. Le client filtre désormais les projets — et changer de client ne
// doit jamais laisser sélectionné le projet d'un autre.
const rsProjectOptions = grabO("rsProjectOptions");
const PR2834 = [
  { client: "acme", project: "shop", value: "acme/shop" },
  { client: "acme", project: "bo", value: "acme/bo" },
  { client: "beta", project: "api", value: "beta/api" },
  { client: "", project: "", value: "" },            // entrée incomplète : ignorée
];
const r1 = rsProjectOptions(PR2834, "acme", "acme/shop");
assert.strictEqual(r1.options.map(o => o.value).join(","), "acme/bo,acme/shop",
  "seuls les projets du client, triés");
assert.strictEqual(r1.value, "acme/shop", "un projet du client reste sélectionné");
const r2 = rsProjectOptions(PR2834, "acme", "beta/api");
assert.strictEqual(r2.value, "", "changer de client abandonne le projet d'un autre client");
const r3 = rsProjectOptions(PR2834, "", "beta/api");
assert.strictEqual(r3.options.map(o => o.value).join(","), "acme/bo,acme/shop,beta/api",
  "sans client : tous les projets");
assert.strictEqual(r3.value, "beta/api", "…et la sélection courante est conservée");
assert.strictEqual(rsProjectOptions(PR2834, "inconnu", "acme/shop").options.length, 0,
  "client sans projet connu → aucune option (et pas une liste complète trompeuse)");
assert.strictEqual(rsProjectOptions(null, "acme", "").options.length, 0, "liste absente");

// Les clients proposés viennent des projets connus, dédoublonnés et triés
const rsClients = grabO("rsClientOptions");
assert.strictEqual(rsClients(PR2834).join(","), "acme,beta", "clients distincts, triés");
assert.strictEqual(rsClients([]).length, 0, "aucun projet → aucun client");

// Câblage
assert(/<select id="rs-client"/.test(html), "le sélecteur client doit exister dans la carte");
assert(/id="rs-client"[^>]*onchange="rsClientChanged\(\)"/.test(html),
  "changer de client doit refiltrer les projets, pas seulement recharger");
const lr2834 = /async function loadResumable\([\s\S]*?\n\}/.exec(html)[0];
assert(/rs-client/.test(lr2834),
  "loadResumable doit envoyer le client — un client seul liste TOUS ses projets");
assert(/client=/.test(lr2834), "…sous forme de filtre client=");
console.log("✓ reprise de session (RM2834) : filtre client, qui filtre les projets");

// — RM2830 : filtrer par étiquette (recherche, triage, jeux dérivés) —
// L'étiquette ne sert à rien si elle ne sert pas à CHOISIR quoi faire.
const searchQuery2830 = grabO("searchQuery");
assert(/tag=refacto/.test(searchQuery2830("x", { tag: "refacto" }, "")),
  "la recherche doit transmettre l'étiquette au serveur");
assert(!/tag=/.test(searchQuery2830("x", {}, "")), "…et ne rien ajouter quand aucune n'est choisie");

// Le triage filtre sur la même notion, sans confondre « aucune étiquette » et « toutes »
const triageFilter2830 = grabO("triageFilter");
const T2830 = [
  { rm_id: "1", client: "a", project: "p", tags: ["front", "refacto"] },
  { rm_id: "2", client: "a", project: "p", tags: ["bdd"] },
  { rm_id: "3", client: "a", project: "p" },
];
assert.strictEqual(triageFilter2830(T2830, "", "", false, "front").map(t => t.rm_id).join(","), "1",
  "filtre par étiquette");
assert.strictEqual(triageFilter2830(T2830, "", "", false, "").length, 3,
  "aucune étiquette choisie → tout, y compris les tickets sans étiquette");
assert.strictEqual(triageFilter2830(T2830, "", "", false, "Front").map(t => t.rm_id).join(","), "1",
  "la casse ne change rien (même vocabulaire qu'à l'écriture)");
assert.strictEqual(triageFilter2830(T2830, "a", "p", false, "bdd").map(t => t.rm_id).join(","), "2",
  "cumulable avec client/projet");

// Les étiquettes se VOIENT sur la ligne de résultat, sinon on filtre à l'aveugle
const rowMeta2830 = grabO("searchRowMeta");
assert(/refacto/.test(rowMeta2830({ client: "a", project: "p", status: "a_faire", tags: ["refacto"] })),
  "les étiquettes d'un ticket apparaissent dans sa ligne");
assert(!/·\s*·/.test(rowMeta2830({ client: "a", project: "p", status: "a_faire" })),
  "aucune étiquette : pas de séparateur orphelin");

// Câblage : menu d'étiquettes alimenté par le serveur, jamais écrit en dur
assert(/<select id="sf-tag"/.test(html), "filtre étiquette dans la recherche");
assert(/<select id="tr-tag"/.test(html), "filtre étiquette dans le triage ROI");
const lt2830 = /async function loadTags\([\s\S]*?\n\}/.exec(html);
assert(lt2830 && /\/tags/.test(lt2830[0]), "les étiquettes proposées viennent de GET /tags");
assert(/rf-tag/.test(html), "le formulaire de jeu dérivé propose le critère étiquette");
console.log("✓ étiquettes dans le cockpit (RM2830) : recherche, triage, jeux dérivés");

// — RM2831 : constituer un lot par domaine et ouvrir une session dessus —
// RM2823 sortait des tickets d'une session polluée, un par un. Ici on les
// rassemble par ÉTIQUETTE : la liste filtrée est déjà le lot.
const triageBatchItems = grabO("triageBatchItems");
const TB = [
  { rm_id: "10", status: "a_faire", title: "un", client: "a", project: "p" },
  { rm_id: "11", status: "en_cours", title: "deux", client: "a", project: "p" },
  { rm_id: "12", status: "ferme", title: "trois", client: "a", project: "p" },
];
const items2831 = triageBatchItems(TB, 10);
assert.strictEqual(items2831.map(i => i.rm_id).join(","), "10,11,12",
  "les lignes affichées deviennent les items du lot, dans l'ordre du triage");
assert.strictEqual(items2831[0].status, "a_faire",
  "le statut voyage : c'est lui qui décide de l'action côté serveur");
assert.strictEqual(items2831[0].title, "un", "…et le titre, pour l'écran de confirmation");
assert.strictEqual(triageBatchItems(TB, 2).length, 2,
  "plafonné à ce qu'on annonce — une file trop longue déborde le contexte de l'agent");
assert.strictEqual(triageBatchItems([], 10).length, 0, "liste vide");
assert.strictEqual(triageBatchItems(null, 10).length, 0, "liste absente");

// Le chemin de lancement est CELUI de RM2823 : une seule fonction, pas deux
const sbs = /async function spawnBatchSession\([\s\S]*?\n\}/.exec(html);
assert(sbs, "spawnBatchSession introuvable (chemin partagé RM2823/RM2831)");
assert(/offloadPlan\(/.test(sbs[0]) && /\/worklog\/batch/.test(sbs[0]) && /\/spawn/.test(sbs[0]),
  "le chemin partagé garde le plan, la consigne du serveur et /spawn");
const off2831 = /async function offloadToNewSession\([\s\S]*?\n\}/.exec(html);
assert(/spawnBatchSession\(/.test(off2831[0]),
  "le geste du worklog (RM2823) passe par le chemin partagé");
const tri2831 = /async function triageSpawnSession\([\s\S]*?\n\}/.exec(html);
assert(tri2831 && /spawnBatchSession\(/.test(tri2831[0]),
  "le geste du triage aussi — sinon deux comportements divergeraient");
assert(/id="tr-spawn"/.test(html), "le bouton du triage doit exister");
console.log("✓ lot par domaine (RM2831) : la liste filtrée devient une session, par le chemin de RM2823");

// — RM2832 : les étiquettes se VOIENT (fiche) et se comptent (conso) —
const tagPills = grabO("tagPillsHtml");
const h2832 = tagPills(["front", "refacto"], escFn, jargFn);
assert(/front/.test(h2832) && /refacto/.test(h2832), "chaque étiquette est rendue");
assert(/🏷/.test(h2832), "…avec la marque qui les identifie d'un coup d'œil");
assert(/filterByTag\(/.test(h2832),
  "cliquer une étiquette doit mener aux tickets qui la portent — sinon elle est décorative");
assert.strictEqual(tagPills([], escFn, jargFn), "", "aucune étiquette : rien, pas un cadre vide");
assert.strictEqual(tagPills(null, escFn, jargFn), "", "liste absente : idem");
// Le risque réel dans un attribut : en SORTIR. Un guillemet double doit être
// neutralisé (helper `jarg`, RM2579), et le texte affiché échappé comme ailleurs.
const piege2832 = tagPills(['a" onclick="alert(1)'], escFn, jargFn);
assert(!/onclick="alert/.test(piege2832), "une étiquette ne peut pas sortir de l'attribut");
assert(/&quot;/.test(piege2832), "…le guillemet est neutralisé, pas laissé tel quel");
assert(/&lt;b&gt;/.test(tagPills(["<b>"], escFn, jargFn)), "le texte affiché est échappé");
// la fiche l'utilise
const rrp2832 = html.indexOf("function renderReviewPane(");
assert(rrp2832 > 0 && /tagPillsHtml\(/.test(html.slice(rrp2832, rrp2832 + 3000)),
  "la fiche du ticket doit afficher les étiquettes");
console.log("✓ étiquettes visibles (RM2832) : sur la fiche, cliquables, et ventilées en conso");

// — RM2833 : l'étiquette propose un rôle d'agent (elle ne l'impose pas) —
const roleHintLine = grabO("roleHintLine");
assert.strictEqual(
  roleHintLine({ role: "db", why: "étiquette « bdd » → rôle db", file: "agents/worker-db.md" }),
  " (rôle suggéré : db — agents/worker-db.md)",
  "la suggestion se lit dans l'écran de lancement");
assert.strictEqual(roleHintLine(null), "", "aucune suggestion : rien à afficher");
assert.strictEqual(roleHintLine({}), "", "suggestion vide : rien non plus");

// La consigne envoyée à l'agent nomme le rôle — c'est elle qui lui fait charger
// le bon fichier d'instructions.
const tpt2833 = grabO("taskPromptText");
const p2833 = tpt2833("traiter", "42", "acme", "shop", { role: "db", file: "agents/worker-db.md" });
assert(/RM42/.test(p2833) && /acme/.test(p2833), "l'ancrage ticket/projet est préservé");
assert(/worker-db\.md/.test(p2833), "…et le rôle suggéré est cité à l'agent");
assert(!/worker-/.test(tpt2833("traiter", "42", "acme", "shop")),
  "sans suggestion, la consigne est celle d'avant — aucune régression");
assert(!/worker-/.test(tpt2833("reviewer", "42", "acme", "shop", { role: "db" })),
  "une review n'est pas routée par étiquette : son rôle est la review");
console.log("✓ routage par étiquette (RM2833) : rôle suggéré, jamais imposé");

// — RM2861 : un fichier ouvert s'affiche en pleine hauteur —
// Le Markdown partait dans `.desc`, le bloc « description encadrée » plafonné à
// 160 px : on lisait un fichier par une fenêtre, dans un panneau qui défile déjà.
const mdStub = (t) => "<md>" + t + "</md>";
const vMd = fileBodyHtml({ markdown: true, content: "# titre" }, escO, mdStub);
assert(/facetfull/.test(vMd) && /descfull/.test(vMd) && /mdview/.test(vMd),
  "le Markdown prend les classes pleine hauteur (RM2797/2806)");
assert(!/class="[^"]*\bdesc\b/.test(vMd),
  "…et PAS `.desc` : déclarée plus loin dans la feuille, elle regagnerait et le correctif serait inerte (RM2806)");
assert(/<md># titre<\/md>/.test(vMd), "le rendu Markdown reste stylé, pas du texte brut");

const vTxt = fileBodyHtml({ markdown: false, content: "a < b & c" }, escO, mdStub);
assert(/max-height:none/.test(vTxt), "le fichier non-markdown reste sans plafond");
assert(/a &lt; b &amp; c/.test(vTxt), "…et son contenu est échappé (ce n'est pas du HTML)");
assert(!/<md>/.test(vTxt), "un fichier non-markdown ne passe pas par le rendu Markdown");
assert(fileBodyHtml(null, escO, mdStub) !== "", "fichier absent toléré");
assert(!/undefined/.test(fileBodyHtml({ markdown: false }, escO, mdStub)),
  "contenu absent → vide, jamais « undefined » à l'écran");

// Câblage : le rendu vivait en DOUBLE (panneau droit RM2586, vue projet RM2590).
// Les deux doivent passer par la fonction, sinon l'un des deux garde le défaut.
assert.strictEqual((html.match(/fileBodyHtml\(f, esc, mdToHtml\)/g) || []).length, 2,
  "les deux panneaux de fichier passent par le rendu commun");
assert(/fileBodyHtml\(d, esc, md\)/.test(html),
  "…et la vue centrale aussi : un seul endroit décide comment un fichier s'affiche");
assert(!/class="desc">' \+ mdToHtml\(f\.content\)/.test(html),
  "plus aucun contenu de fichier rendu dans le bloc encadré");
console.log("✓ fichier ouvert (RM2861) : pleine hauteur, un seul rendu pour les trois vues");

// — RM2873 : consigne choisie et éditable depuis la fiche du ticket —
// Le lanceur de gauche offrait un modèle de consigne et un champ ; la fiche
// lançait avec une consigne imposée, visible seulement dans la confirmation.

// La liste des modèles n'existe qu'à UN endroit : une liste en dur dans le HTML
// de gauche aurait divergé de celle de la fiche au premier ajout.
const tpls2873 = promptTemplates();
assert(tpls2873.length >= 5 && tpls2873.every(t => t.value && t.label),
  "chaque modèle a une valeur ET un libellé");
assert.strictEqual(tpls2873[tpls2873.length - 1].value, "libre",
  "« libre » ferme la marche : c'est le mode de saisie manuelle");
assert(tpls2873.every(t => t.value === "libre" || taskPromptText(t.value, "42")),
  "tout modèle proposé produit une consigne (sauf « libre »)");
const optsHtml = promptTemplateOptions("chiffrer", escFn);
assert(/<option value="chiffrer" selected>/.test(optsHtml), "le modèle retenu est marqué");
assert.strictEqual((optsHtml.match(/selected/g) || []).length, 1, "un seul modèle retenu");
assert(!/<option value="traiter"[^>]*>Traiter la tâche<\/option>[\s\S]*<option value="traiter"/.test(html),
  "le <select> de gauche ne re-déclare pas la liste en dur");
assert(/getElementById\("ptpl"\)\.innerHTML = promptTemplateOptions\(/.test(html),
  "…il est peuplé depuis la source unique");

// La règle de remplissage est la même des deux côtés.
assert.strictEqual(promptFillOnChange("libre", "ma consigne à moi", "traite la tâche RM42"),
  "ma consigne à moi", "« libre » n'écrase jamais la saisie");
assert.strictEqual(promptFillOnChange("traiter", "vieux texte", "traite la tâche RM42"),
  "traite la tâche RM42", "changer de modèle remplace le texte");
assert.strictEqual(promptFillOnChange("traiter", "déjà tapé", ""), "déjà tapé",
  "un modèle qu'on ne sait pas calculer ne VIDE pas le champ");

// L'état du champ suit le ticket affiché — et survit à un re-rendu de la fiche.
const st1 = ticketPromptFor(null, "42", "traite la tâche RM42");
assert.strictEqual(st1.text, "traite la tâche RM42", "consigne par défaut au premier rendu");
const st2 = ticketPromptFor({ rm: "42", tpl: "libre", text: "fais autre chose" }, "42", "traite la tâche RM42");
assert.strictEqual(st2.text, "fais autre chose",
  "un re-rendu de la fiche ne perd pas la saisie en cours (renderReviewPane est appelé sur événement)");
assert.strictEqual(st2.tpl, "libre", "…ni le modèle choisi");
const st3 = ticketPromptFor({ rm: "42", tpl: "libre", text: "fais autre chose" }, "43", "traite la tâche RM43");
assert.strictEqual(st3.text, "traite la tâche RM43",
  "changer de ticket repart d'une consigne propre — sinon on lance RM43 avec la consigne de RM42");

// Le bloc de la fiche rend bien le sélecteur et le champ, pré-remplis.
const tsPr = ticketSessionsHtml({ rm_id: "42", handled: [], candidates: [], own_alive: false },
  escFn, jargFn, { tpl: "chiffrer", text: "étudie et chiffre la tâche RM42" });
assert(/id="ts-tpl"/.test(tsPr) && /id="ts-prompt"/.test(tsPr),
  "la fiche offre le modèle de consigne ET le champ");
assert(/<option value="chiffrer" selected>/.test(tsPr), "le modèle en cours est celui affiché");
assert(/étudie et chiffre la tâche RM42<\/textarea>/.test(tsPr), "le champ est pré-rempli");
assert(/oninput="tsPromptEdited\(/.test(tsPr), "la saisie est mémorisée hors du DOM");

// Câblage : les deux gestes du bloc utilisent la consigne affichée.
const mSpawn2873 = /async function spawnTicketSession[\s\S]*?\n\}/.exec(html);
assert(/tsPrompt\.text/.test(mSpawn2873[0]),
  "le lancement utilise la consigne éditée, plus une consigne imposée");
const mSend2873 = /async function sendTicketToSession[\s\S]*?\n\}/.exec(html);
assert(/tsPrompt\.text/.test(mSend2873[0]),
  "l'envoi dans une session existante aussi : un champ au-dessus d'un bouton qui l'ignore serait un piège");
console.log("✓ consigne depuis la fiche (RM2873) : modèle + champ éditable, partagés avec le lanceur");

// ── RM2888 : changer le statut depuis la fiche et le worklog ────────────────
// Le menu ne doit RIEN savoir du workflow : il rend ce que le serveur envoie.
// Un test qui vérifierait « en_cours propose a_tester_dev » recopierait la règle
// NORMS dans le harnais — exactement ce que le ticket interdit.
const statusMenuHtml = grabO("statusMenuHtml");
const stData = {
  status: "en_cours", redmine_checked: true,
  transitions: [
    { status: "a_tester_dev", condition: "dev terminé", redmine_ok: true, needs_close_reason: false },
    { status: "a_mep", condition: "validé", redmine_ok: false, needs_close_reason: false },
    { status: "ferme", condition: "close_reason requis", redmine_ok: true, needs_close_reason: true },
  ],
};
const stHtml = statusMenuHtml(stData, escO);
assert(/data-st="a_tester_dev"/.test(stHtml), "chaque transition servie devient un bouton");
assert(/data-st="a_mep"[^>]*disabled/.test(stHtml),
  "une transition que CE compte ne peut pas poser reste visible, mais désactivée");
assert(/Redmine refusera/.test(stHtml),
  "…et dit pourquoi : sinon le bouton grisé passe pour un bug");
assert(/data-st="ferme"[^>]*data-reason="1"/.test(stHtml),
  "la fermeture est marquée comme exigeant un motif, AVANT de soumettre");
assert(!/⚠ transitions NORMS seules/.test(stHtml),
  "pas d'avertissement quand le workflow Redmine a bien été interrogé");

// Redmine injoignable : on n'ampute rien, on prévient. Une panne de l'API ne doit
// pas rendre le geste inatteignable — c'est le mode dégradé de --list-next.
const stDeg = statusMenuHtml(
  { status: "a_faire", redmine_checked: false,
    transitions: [{ status: "en_cours", condition: "prise en charge", redmine_ok: null,
                    needs_close_reason: false }] }, escO);
assert(/data-st="en_cours"/.test(stDeg) && !/disabled/.test(/data-st="en_cours"[^>]*>/.exec(stDeg)[0]),
  "sans vérification live, la transition reste proposable");
assert(/⚠ transitions NORMS seules/.test(stDeg), "…et l'UI dit que le contrôle des droits manque");

// Statut terminal / liste vide : dire « rien à faire ici », pas un menu muet.
assert(/aucune transition/.test(statusMenuHtml({ status: "ferme", transitions: [] }, escO)),
  "une liste vide s'explique au lieu de s'afficher creuse");
assert(/aucune transition/.test(statusMenuHtml(null, escO)), "données absentes tolérées");
console.log("✓ menu de statut (RM2888) : le serveur décide, l'UI rend — refus et mode dégradé compris");

// Ce qu'il faut demander avant de soumettre. La règle vient du serveur
// (needs_close_reason / needs_note), jamais d'un test sur le nom du statut.
const statusPromptSpec = grabO("statusPromptSpec");
const spFerme = statusPromptSpec("ferme", true, ["abandonne", "resolu", "doublon"], false);
assert.strictEqual(spFerme.needs_reason, true, "fermeture : motif réclamé");
assert.strictEqual(spFerme.default_reason, "resolu",
  "« resolu » est proposé par défaut — le cas courant, mais modifiable");
assert(/facultatif/.test(spFerme.note_label), "la note reste facultative si rien ne l'exige");
const spReopen = statusPromptSpec("a_faire", false, [], true);
assert.strictEqual(spReopen.needs_note, true, "réouverture : la note est exigée par le workflow");
assert(/requise/.test(spReopen.note_label), "…et l'invite le dit, au lieu de refuser après coup");
const spPlain = statusPromptSpec("en_cours", false, [], false);
assert.strictEqual(spPlain.needs_reason, false, "une transition ordinaire ne réclame rien");
assert.strictEqual(statusPromptSpec("ferme", true, [], false).default_reason, "",
  "aucun motif servi : pas de valeur inventée");
console.log("✓ invites de statut (RM2888) : motif et note exigés par le serveur, pas devinés");

// Câblage : les deux points d'entrée demandés (fiche + worklog) appellent le menu,
// et la mécanique de gardes n'est plus dupliquée dans la console de test.
const mDetail2888 = /function _ticketDetailHtml[\s\S]*?\n\}/.exec(html);
assert(/openStatusMenu\(/.test(mDetail2888[0]),
  "la fiche du ticket ouvre le menu depuis sa pastille de phase");
const mRw2888 = /function renderWorklog\(\) \{[\s\S]*?\n\}/.exec(html);
assert(/openStatusMenu\(/.test(mRw2888[0]),
  "le worklog aussi : c'est le second point d'entrée demandé");
assert(/event\.stopPropagation\(\);openStatusMenu/.test(mRw2888[0]),
  "…sans ouvrir la fiche par-dessus le menu");
const mTq2888 = /async function tqVerdict[\s\S]*?\n\}/.exec(html);
assert(/runTaskStatusGated\(/.test(mTq2888[0]) && !/allow_unchecked = true/.test(mTq2888[0]),
  "la console de test partage la mécanique de gardes au lieu de la recopier");
const mGate2888 = /async function runTaskStatusGated[\s\S]*?\n\}/.exec(html);
assert(/checklist non coché/.test(mGate2888[0]) && /non mergée|RM2319/.test(mGate2888[0]),
  "les deux gardes NORMS restent franchissables explicitement, jamais d'office");
// La garde qui compte : le menu se construit UNIQUEMENT à partir des données du
// serveur. Un nom de statut écrit en dur dedans serait le début de la seconde
// table que le ticket interdit. (Ailleurs dans le front, citer un statut reste
// légitime — `ticketVerdicts` ou `_TQ_VERDICTS` visent un statut précis.)
const mMenu2888 = />>> statusMenuHtml[\s\S]*?<<< statusMenuHtml/.exec(html)[0];
const mOpen2888 = /async function openStatusMenu[\s\S]*?\n\}/.exec(html)[0];
const STATUTS_NORMS = ["nouveau", "a_etudier_chiffrer", "etude_chiffrage_en_cours",
  "etude_chiffrage_a_valider", "a_faire", "en_cours", "a_tester_dev", "a_tester_demandeur",
  "a_mep", "en_mep", "en_pause", "a_corriger", "ferme"];
for (const st of STATUTS_NORMS) {
  assert(!mMenu2888.includes('"' + st + '"') && !mMenu2888.includes("'" + st + "'"),
    "statusMenuHtml ne doit citer aucun statut en dur (trouvé : " + st + ")");
  assert(!mOpen2888.includes('"' + st + '"') && !mOpen2888.includes("'" + st + "'"),
    "openStatusMenu ne doit citer aucun statut en dur (trouvé : " + st + ")");
}
console.log("✓ câblage (RM2888) : fiche + worklog, gardes partagées, zéro règle recopiée");

// — RM2894 : libellé de la session en en-tête du panneau de droite —
const mRt2894 = />>> rTitleHtml[\s\S]*?(function rTitleHtml[\s\S]*?)\n\/\/ <<< rTitleHtml/.exec(html);
assert(mRt2894, "marqueurs >>> rTitleHtml / <<< rTitleHtml introuvables");
const rTitleHtml2894 = vm.runInNewContext("(" + mRt2894[1] + ")", {});
const escT2894 = s => String(s).replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// 1. session de ticket : le sujet Redmine prime sur le titre du transcript
let h2894 = rTitleHtml2894("2894", { title: "titre transcript" },
                   { found: true, title: "Sujet Redmine" }, escT2894);
assert(/RM2894/.test(h2894), "l'identifiant d'un ticket est préfixé RM");
assert(/Sujet Redmine/.test(h2894) && !/titre transcript/.test(h2894),
  "le sujet Redmine prime quand le ticket est résolu");

// 2. session ancrée sur un slug : pas de RM, et le titre du transcript sert de libellé
h2894 = rTitleHtml2894("calicote-presta", { is_ticket: false, title: "MEP productcheck" }, null, escT2894);
assert(!/RM/.test(h2894), "une session slug ne s'invente pas un RM-id");
assert(/calicote-presta/.test(h2894) && /MEP productcheck/.test(h2894),
  "le titre du transcript nomme la session à défaut de ticket");

// 3. rien à afficher : on le DIT — retomber sur le nom tmux répéterait l'id
h2894 = rTitleHtml2894("2894", {}, { found: false }, escT2894);
assert(/sans libellé/.test(h2894), "l'absence de libellé est affichée telle quelle");
assert(!/karl-/.test(h2894), "…et surtout pas remplacée par le nom tmux");

// 4. le libellé vient de l'extérieur : il est échappé
h2894 = rTitleHtml2894("2894", { title: '<img src=x onerror="alert(1)">' }, null, escT2894);
assert(!/<img/.test(h2894) && /&lt;img/.test(h2894), "le libellé est échappé");

// 5. l'en-tête est bien AU-DESSUS des onglets dans le document (la demande)
assert(html.indexOf('id="rtitle"') > 0 && html.indexOf('id="rtitle"') < html.indexOf('<nav class="rnav">'),
  "l'en-tête doit précéder la barre d'onglets .rnav");
// 6. …et il suit la vue : renderCurTitle est le point d'entrée commun
assert(/function renderCurTitle\(\) \{\s*\n\s*renderRTitle\(\);/.test(html),
  "renderRTitle doit être appelé par renderCurTitle (tout changement de vue)");
console.log("✓ libellé de session (RM2894) : en-tête au-dessus des onglets, 3 sources, échappement");
