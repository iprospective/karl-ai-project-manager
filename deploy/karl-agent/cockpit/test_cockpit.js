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

// — 3. mdToHtml (RM2309) : MIGRÉ (RM2889, src/core/markdown.js) — voir test_cockpit_doc.js —
// — 4. tqMatch (RM2315) : MIGRÉ (RM2889, file à tester) — voir test_cockpit_testqueue.js —

// — 5. nextAttentionId (RM2302) : RETIRÉ avec le bouton « ⚠ suivante » de l'en-tête (RM2889) —

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

// — 5. voiceQueue (RM2329) : domaine MIGRÉ (RM2889, L5) — voir test_cockpit_voice.js —

// — 6. outlineStep (RM2330) : MIGRÉ (RM2889, outline) — voir test_cockpit_outline.js —

// — 8. pickVoice (RM2350) : domaine MIGRÉ (RM2889, L5) — voir test_cockpit_voice.js —

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

// — ttsMode / sttMode (RM2532/RM2533) : domaine MIGRÉ (RM2889, L5) — voir test_cockpit_voice.js —

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

// — 9. outline enrichi (RM2549/2596) : MIGRÉ (RM2889, outline) — voir test_cockpit_outline.js —

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
// — configArgs (RM2531) : MIGRÉ (RM2889, fiche projet) — voir test_cockpit_project.js —

// — 12. pendingDecor (RM2466 volet 2) : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

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

// — 13. worklog de session (RM2466/2581/2796) : MIGRÉ (RM2889) — voir test_cockpit_worklog.js. Reste l'hôte :
assert(/id="workbody"/.test(html) && !/id="pendbody"/.test(html), "le panneau droit ne contient plus que le worklog (RM2581)");
assert(/id="workfresh"/.test(html), "le worklog affiche quand son statut a été résolu en direct (workfresh)");
console.log("✓ worklog (RM2581) : hôte du panneau en place, logique migrée");

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

// — notifications de session (RM2466) : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2586 : fil d'ariane : MIGRÉ (RM2889, explorateur) — voir test_cockpit_files.js —
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

// — sinceLabel (RM2630) : MIGRÉ (RM2889, modèle ticket) — voir test_cockpit_ticket.js —

// — worklogDocs (RM2584) : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —


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
// RM2623 : le glossaire a MIGRÉ (RM2889, test_cockpit_doc.js) ; linkify le souligne par un pont — identité ici
const linkify = grabO("linkify", { esc: escO, jarg: jargFn, glossify: (s) => s });

// jarg : argument onclick sûr (guillemets simples, jamais de " qui casse l'attribut)
assert.strictEqual(jargFn("a/b.py"), "'a/b.py'", "chemin simple entre quotes simples");
assert(!/"/.test(jargFn('x"y')), "un \" dans la valeur ne ferme pas l'attribut");
assert.strictEqual(jargFn("l'a"), "'l\\'a'", "apostrophe échappée");

// outMatch / hlq : MIGRÉS (RM2889, outline) — voir test_cockpit_outline.js

// linkify : RM → showTicket, chemin → openFileRef ('...'), URL → <a>, reste échappé
const lk = linkify("fix RM42 dans scripts/karl-agent.py cf https://x.io/p et <b>");
assert(/onclick="showTicket\(42\)"/.test(lk) && />RM42</.test(lk), "RM42 cliquable → showTicket");
assert(/onclick="openFileRef\('scripts\/karl-agent.py'\)"/.test(lk), "chemin cliquable → openFileRef (quotes simples)");
assert(/<a href="https:\/\/x.io\/p"/.test(lk), "URL cliquable");
assert(!/<b>/.test(lk) && /&lt;b&gt;/.test(lk), "reste du texte échappé (anti-XSS)");
console.log("✓ conversation (RM2596) : recherche, surlignage, refs cliquables, onclick sûr");

// — worklogDocsHtml (RM2935) : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2623/RM2634 : glossaire du jargon : MIGRÉ (RM2889) — voir test_cockpit_doc.js —

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

// — outByKind (RM2601) : MIGRÉ (RM2889, outline) — voir test_cockpit_outline.js —

// — vue git (RM2602) : domaine MIGRÉ (RM2889, L4) — voir test_cockpit_git.js —

// — RM2605 : tickets cliquables du worklog : MIGRÉ (RM2889) — voir test_cockpit_worklog.js —

// — RM2605 : « infos » allégé : MIGRÉ (RM2889, encart ℹ) — voir test_cockpit_meta.js —

// — RM2606/RM2883 : tickets ouverts (liste, ordre, familles, groupes) : MIGRÉ (RM2889, panneau 🎫) — voir test_cockpit_tickets.js —

// le badge de l'onglet et l'alimentation depuis les deux portes d'entrée
assert(/id="ln-tickets"/.test(html), "l'onglet tickets porte un compteur");
const metaCtrl = fs.readFileSync(path.join(__dirname, "src/controllers/meta.controller.js"), "utf8");
assert(/ctx\.noteOpened\(id\)/.test(metaCtrl), "ouvrir une fiche alimente la liste (contrôleur migré, RM2889)");
const revCtrl = fs.readFileSync(path.join(__dirname, "src/controllers/review.controller.js"), "utf8");
assert(/ctx\.noteOpened\(rm\)/.test(revCtrl), "ouvrir une revue aussi (contrôleur migré, RM2889)");
assert(/karlOpenedTickets/.test(fs.readFileSync(path.join(__dirname, "src/services/tickets.service.js"), "utf8")), "la liste survit au rechargement (localStorage, service migré)");
console.log("✓ tickets ouverts (RM2606) : compteur, deux portes d'entrée, persistance");

// — worklogTabList (RM2610) : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2611 : MIGRÉ (RM2889, modèle ticket) — voir test_cockpit_ticket.js —

// — pollDelay (RM2613) : cadence adaptative + pause en arriere-plan —
const fPd613 = />>> pollDelay[\s\S]*?(function pollDelay[\s\S]*?)\n\/\/ <<< pollDelay/.exec(html);
assert(fPd613, "marqueurs pollDelay introuvables");
const pollDelay = vm.runInNewContext("(" + fPd613[1] + ")");
assert.strictEqual(pollDelay(true), 3000, "attention -> 3s");
assert.strictEqual(pollDelay(false), 7000, "calme -> 7s");
assert(/visibilitychange/.test(html) && /document\.hidden/.test(html), "pollers gates sur la visibilite (RM2613)");
assert(/setInterval\([^)]*document\.hidden/.test(html) || /if \(!document\.hidden\)/.test(html), "au moins un poller saute quand cache");
console.log("\u2713 pollDelay (RM2613) : cadence adaptative, pause en arriere-plan");

// — RM2614 : client/projet du ticket : MIGRÉ (RM2889, encart ℹ) — voir test_cockpit_meta.js —

// — RM2619 : infobulles : MIGRÉ (RM2889, panneau 🎫) — voir test_cockpit_tickets.js —

// — RM2622 : doc du projet dans l'onglet fichiers : MIGRÉ (RM2889) — voir test_cockpit_files.js —

// — RM2384 : mcBanner MIGRÉ (RM2889, modèle ticket) — voir test_cockpit_ticket.js —

// — RM2458 / RM2708 : santé du poste — domaine MIGRÉ (RM2889, L5), voir test_cockpit_env.js —

// — RM2659 : racines groupées par projet : MIGRÉ (RM2889) — voir test_cockpit_files.js —

// — RM1952 : triage ROI : MIGRÉ (RM2889, panneau 🎫) — voir test_cockpit_tickets.js —

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

// — RM2673 : tickets de la session (toutes sources) : MIGRÉ (RM2889, encart ℹ) — voir test_cockpit_meta.js —

// — RM2673 : repli du panneau fichiers sur le projet courant : MIGRÉ (RM2889) — voir test_cockpit_files.js —

// — RM2695 : avancement d'un ticket : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2696 : worklog PROJET — MIGRÉ (RM2889, fiche projet) — voir test_cockpit_project.js —
// — RM2716/RM2723 : lot du worklog, ligne de MR : MIGRÉS (RM2889) — voir test_cockpit_worklog.js —


// — RM2697 / RM2698 : tableau de bord — domaine MIGRÉ (RM2889, L4), voir test_cockpit_dashboard.js —

console.log("OK — tous les tests cockpit passent");

// — renderMailList (RM2671) : domaine MIGRÉ (RM2889, L1) — voir test_cockpit_mail.js —

// — onglets du panneau central (RM2672) : temporaire unique, épinglage, fermeture —
// onglets : domaine MIGRÉ (RM2889, cluster centre) — voir test_cockpit_center.js
const grabFn = (name) => vm.runInNewContext("(" + grab(name) + ")", { Object });
// formulaire « nouveau ticket » (RM2672/RM2726/RM2752) : surface MIGRÉE — voir test_cockpit_newticket.js

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

// — RM2719 : portée restreinte : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

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

// — RM2720/RM2723 : modes de lot, lot de merges, ligne de MR : MIGRÉS (RM2889) — voir test_cockpit_worklog.js —

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

// — RM2726 : sessions du ticket / consignes : MIGRÉ (RM2889) — voir test_cockpit_review.js —

// — RM2726 : création de ticket — MIGRÉ (RM2889), voir test_cockpit_newticket.js —

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

// — RM2744 : tableau de bord — contenu atteignable (onglet permanent : MIGRÉ, test_cockpit_center.js) —
// RM2889 : le rendu du tableau de bord vit dans src/ ; c'est boot.js qui pose ET
// retire la classe (toggle), à chaque `shown` du contrôleur.
const bootSrc = fs.readFileSync(path.join(__dirname, "src/boot.js"), "utf8");
assert(/ph\.classList\.toggle\("dash-on", on\)/.test(bootSrc),
  "la classe doit être posée ET retirée par le rendu du tableau de bord");
console.log("✓ tableau de bord (RM2744) : contenu atteignable, onglet permanent non fermable");

// — RM2748 : verrous du poste — domaine MIGRÉ (RM2889, L5), voir test_cockpit_env.js —

// — RM2752 : bugfix avec étapes de reproduction — MIGRÉ (RM2889), voir test_cockpit_newticket.js —

// — RM2757 : carte repliable : logique MIGRÉE (RM2889, test_cockpit_tickets.js) ; reste ici le câblage HTML —
// Le câblage HTML : sans lui, les fonctions pures ci-dessus ne servent à rien.
assert(/<details class="card" id="openedcard">/.test(html), "la carte doit être un <details> (le contrôleur migré mémorise le geste au toggle)");
assert(/listen\(opened, "toggle"/.test(fs.readFileSync(path.join(__dirname, "src/controllers/tickets.controller.js"), "utf8")), "…et il l'écoute");
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

// — RM2759 : MIGRÉ (RM2889, cluster centre) — voir test_cockpit_center.js —

// — RM2760 : panneau « projets » — domaine MIGRÉ (RM2889, L4), voir test_cockpit_projects.js —
// Le câblage : un panneau que rien n'ouvre n'existe pas.
assert(/data-panel="projects"/.test(html), "l'onglet gauche doit exister");
assert(/<div class="lpanel" id="lp-projects"><\/div>/.test(html), "…avec son panneau (hôte monté par boot.js)");
assert(/projects: \(\) => karlCall\("projects", "refresh"\)/.test(html), "…et son chargeur");

// ── RM2675 : glossaire de projet (lecture, filtre) : MIGRÉ (RM2889) — voir test_cockpit_doc.js. Reste le câblage :
// Le câblage : un sous-onglet que rien n'affiche n'existe pas.
assert(/data-action="vocab" data-on="1"/.test(fs.readFileSync(path.join(__dirname, "src/views/files/Files.view.js"), "utf8")), "le sous-onglet vocabulaire doit être cliquable (vue migrée)");
assert(/glossaire\.md/.test(fs.readFileSync(path.join(__dirname, "src/services/files.service.js"), "utf8")), "…et il doit chercher docs/glossaire.md (service migré)");
console.log("✓ glossaire de projet (RM2675) : tableau lu, filtre sur terme/définition/contexte/alias");
// — RM2761 : MIGRÉ (RM2889, cluster centre) — voir test_cockpit_center.js —

// — RM2768 : MIGRÉ (RM2889, cluster centre) — voir test_cockpit_center.js —



// — RM2770 : recherche multi-source et filtres : MIGRÉ (RM2889) — voir test_cockpit_search.js. Reste l'hôte HTML :
// Câblage : les trois sources et les filtres doivent exister dans la page.
["sf-source", "sf-client", "sf-project", "sf-status", "sf-warn"].forEach(id =>
  assert(html.includes('id="' + id + '"'), "élément manquant : " + id));
["local", "redmine", "both"].forEach(v =>
  assert(new RegExp('<option value="' + v + '"').test(html), "source manquante : " + v));
assert(/<select id="sf-source"[\s\S]*?<option value="local"/.test(html),
  "« local » doit être la première option, donc le défaut");
assert(/redmine_error/.test(fs.readFileSync(path.join(__dirname, "src/controllers/search.controller.js"), "utf8")),
  "l'erreur Redmine doit être affichée à côté des résultats, pas à leur place (contrôleur migré)");
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

// — RM2775 : MIGRÉ (RM2889, cluster centre) — voir test_cockpit_center.js —

// — RM2776 : MIGRÉ (RM2889, cluster centre) — voir test_cockpit_center.js —

// — RM2786 : n'offrir que les actions qui ont du sens —
// batchButtons / closeBatchPlan : MIGRÉS (RM2889, worklog) — voir test_cockpit_worklog.js. Reste l'hôte :
["batch-etudier-btn", "batch-close-btn"].forEach(id =>
  assert(html.includes('id="' + id + '"'), "bouton manquant : " + id));
console.log("✓ actions pertinentes (RM2786) : boutons hôtes en place, règle migrée");

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

// — RM2795 : la marque d'épinglage (pinMark : MIGRÉ, test_cockpit_center.js) —
// Les cinq surfaces doivent appeler la MÊME fonction — cinq variantes d'un même
// signal, ce serait cinq signaux.
const surfaces2795 = [
  ['pinOf("session", s.rm_id)', "tuiles de session"],
  ['pinOf("review", rm)', "revues ouvertes"],
];
surfaces2795.forEach(([frag, quoi]) =>
  assert(html.includes(frag), "marque absente : " + quoi));
// RM2889 : la recherche est migrée — sa vue reçoit la marque du routeur par le contrôleur
assert(/raw\(pin\("review", r\.rm\)\)/.test(fs.readFileSync(path.join(__dirname, "src/views/tickets/Search.view.js"), "utf8")),
  "marque absente : résultats de recherche (migrés)");
// RM2889 : les tickets ouverts sont migrés — la vue reçoit la marque du routeur (pinOf) par le contrôleur
assert(/raw\(pin\("review", it\.rm\)\)/.test(fs.readFileSync(path.join(__dirname, "src/views/tickets/TicketsPanel.view.js"), "utf8")),
  "marque absente : tickets ouverts (migrés)");
// RM2889 : la file à tester est migrée — sa marque vient du routeur, prêtée au ViewModel
assert(/this\.ctx\.pin\("review", e\.rm_id\)/.test(fs.readFileSync(path.join(__dirname, "src/viewmodels/testqueue/TestQueueViewModel.js"), "utf8")),
  "marque absente : file à tester (migrée)");
assert(/pin\("project", p\.value\)/.test(fs.readFileSync(path.join(__dirname, "src/viewmodels/projects/ProjectsPanelViewModel.js"), "utf8")),
  "marque absente : panneau projets (migré RM2889)");
assert(/raw\(pin\("review", it\.rm\)\)/.test(fs.readFileSync(path.join(__dirname, "src/views/worklog/Worklog.view.js"), "utf8")), "marque absente : worklog (migré)");
// …et l'état doit suivre le geste, sans attendre le prochain poll.
// RM2889 : l'épinglage vit dans le routeur du centre ; c'est lui qui prévient les listes
const centerSrc = fs.readFileSync(path.join(__dirname, "src/controllers/center.controller.js"), "utf8");
assert(/function togglePin[\s\S]{0,400}ctx\.onPinChange\(\)/.test(centerSrc),
  "détacher un onglet doit rafraîchir les listes tout de suite");
assert(/opts && opts\.pin && ctx\.onPinChange\) ctx\.onPinChange\(\)/.test(centerSrc),
  "…et épingler à l'ouverture aussi");
// Le panneau projets reçoit la marque en option : porté dans test_cockpit_projects.js (RM2889).
console.log("✓ marque d'épinglage (RM2795) : la même icône dans les listes, à jour au clic");

// — RM2796 : pastille de statut : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2797 : description et historique en facettes : MIGRÉ (RM2889, encart ℹ) — voir test_cockpit_meta.js.
// Reste au monolithe la feuille de style : une facette doit pouvoir occuper toute la hauteur.
assert(/\.facetfull \{[^}]*max-height: none/.test(html),
  "une facette doit pouvoir occuper toute la hauteur");
console.log("✓ fiche ticket (RM2797) : style des facettes pleine hauteur conservé");

// — RM2798 : worklog groupé : MIGRÉ (RM2889) — voir test_cockpit_worklog.js —

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
// La dérive et le numéro cliquable : MIGRÉS (RM2889) — voir test_cockpit_worklog.js
console.log("✓ lisibilité du worklog (RM2799) : sections délimitées, numéro qui prime sur le statut");

// — RM2801 : étape de MR : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2806 : la facette description n'emprunte plus le style du bloc encadré —
// Le piège corrigé ici est un piège de CASCADE : `.facetfull { max-height: none }`
// existait bien, mais `.desc { max-height: 160px }` est déclarée plus loin, à
// spécificité égale — elle gagnait, et la bride annoncée levée ne l'a jamais été.
// Un test qui se contenterait de chercher `max-height: none` dans la page serait
// passé au vert sur du code inerte : on vérifie donc que la facette n'utilise
// plus la classe en conflit.
// La facette elle-même a MIGRÉ (RM2889, test_cockpit_meta.js vérifie ses classes) ; la cascade CSS reste ici.
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
    rightVisible: () => true,
    // RM2889 : le tableau de bord est un domaine migré ; la pile lui parle par le pont
    karlCall: (dom, fn) => { if (dom === "worklog" && fn === "setFromRefresh") calls.worklog++; return dom === "dashboard" && fn === "visible" ? false : undefined; },   // RM2889 : le bloc worklog part au contrôleur migré
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

// (icônes et infobulles des onglets pm/settings : MIGRÉS — test_cockpit_center.js)
// (réactivation, fermetures croisées, openCenterPanel : MIGRÉS — test_cockpit_center.js)

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

// — RM2823 : embarquer un lot ailleurs : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js. Reste l'hôte :
assert(/id="batch-offload-btn"/.test(html), "le bouton d'embarquement doit exister");
console.log("✓ embarquer un lot ailleurs (RM2823) : bouton hôte en place, logique migrée");
// — RM2818 : alerter avant d'ouvrir une 2e session sur un ticket déjà pris —
// Texte d'alerte, garde et spawn depuis la fiche : MIGRÉS (RM2889, test_cockpit_review.js).
// Le lanceur de gauche (spawn) reste au monolithe et doit passer par la garde (pont).
{
  const i = html.indexOf("async function spawn(");
  assert(i > 0, "fonction introuvable : spawn");
  assert(/confirmSecondSession\(/.test(html.slice(i, i + 2200)), "spawn doit passer par confirmSecondSession");
}
console.log("✓ 2e session sur un ticket pris (RM2818) : le lanceur de gauche passe aussi par la garde");
// — RM2819 : MIGRÉ (RM2889, cluster centre) — voir test_cockpit_center.js —

// — RM2834 : filtre client de « Reprendre une session » : MIGRÉ (RM2889) — voir test_cockpit_resume.js. Reste l'hôte :
assert(/<select id="rs-client"/.test(html) && /<select id="rs-project"/.test(html), "les sélecteurs client / projet doivent exister dans la carte");
console.log("✓ reprise de session (RM2834) : hôte HTML en place, logique migrée");

// — RM2830 : filtrer par étiquette (recherche, triage, jeux dérivés) —
// L'étiquette ne sert à rien si elle ne sert pas à CHOISIR quoi faire.
// searchQuery : MIGRÉ (RM2889) — voir test_cockpit_search.js

// Le triage filtre sur la même notion : MIGRÉ (RM2889) — voir test_cockpit_tickets.js

// searchRowMeta (étiquettes visibles) : MIGRÉ (RM2889) — voir test_cockpit_search.js

// Câblage : menu d'étiquettes alimenté par le serveur, jamais écrit en dur
assert(/<select id="sf-tag"/.test(html), "filtre étiquette dans la recherche");
assert(/<select id="tr-tag"/.test(html), "filtre étiquette dans le triage ROI");
assert(/"search\.tags"/.test(fs.readFileSync(path.join(__dirname, "src/models/tickets/SearchRepository.js"), "utf8")), "les étiquettes proposées viennent de GET /tags (dépôt migré)");
assert(/rf-tag/.test(html), "le formulaire de jeu dérivé propose le critère étiquette");
console.log("✓ étiquettes dans le cockpit (RM2830) : recherche, triage, jeux dérivés");

// — RM2831 : constituer un lot par domaine et ouvrir une session dessus —
// RM2823 sortait des tickets d'une session polluée, un par un. Ici on les
// rassemble par ÉTIQUETTE : la liste filtrée est déjà le lot.
// triageBatchItems : MIGRÉ (RM2889) — voir test_cockpit_tickets.js

// Le chemin de lancement est CELUI de RM2823 : une seule fonction (worklog.spawnBatch), empruntée par le triage
assert(/spawnBatch: \(items, btn, opts\) => worklogCtl\.spawnBatch/.test(fs.readFileSync(path.join(__dirname, "src/boot.js"), "utf8")),
  "le geste du triage passe par le chemin partagé du worklog — sinon deux comportements divergeraient");
assert(/id="tr-spawn"/.test(html), "le bouton du triage doit exister");
console.log("✓ lot par domaine (RM2831) : la liste filtrée devient une session, par le chemin de RM2823");

// — RM2832 : étiquettes sur la fiche : MIGRÉ (RM2889) — voir test_cockpit_review.js —

// — RM2833 : rôle suggéré par étiquette : MIGRÉ (RM2889) — voir test_cockpit_review.js —

// — RM2861 : un fichier ouvert (fileBodyHtml : MIGRÉ, test_cockpit_center.js) —
// Câblage : le rendu vivait en DOUBLE (panneau droit RM2586, vue projet RM2590).
// Les deux doivent passer par la fonction, sinon l'un des deux garde le défaut.
// RM2889 : la fiche projet est migrée — elle reçoit le rendu commun en prêt (fileBody) ;
// seul l'onglet fichiers de droite l'appelle encore depuis le monolithe.
assert(/raw\(fileBody\(f\.raw\)\)/.test(fs.readFileSync(path.join(__dirname, "src/views/files/Files.view.js"), "utf8")),
  "l'onglet fichiers (migré) passe par le rendu commun qu'on lui prête");
assert(/raw\(fileBody\(f\)\)/.test(fs.readFileSync(path.join(__dirname, "src/views/projects/ProjectPane.view.js"), "utf8")),
  "…et la fiche projet aussi, par le rendu qu'on lui prête");

assert(!/class="desc">' \+ mdToHtml\(f\.content\)/.test(html),
  "plus aucun contenu de fichier rendu dans le bloc encadré");
console.log("✓ fichier ouvert (RM2861) : pleine hauteur, un seul rendu pour les trois vues");

// — RM2873 : consigne depuis la fiche : MIGRÉ (RM2889) — voir test_cockpit_review.js —

// ── RM2888 : changer le statut depuis la fiche et le worklog ────────────────
// Menu, invites, gardes : MIGRÉS (RM2889) — voir test_cockpit_review.js. Restent au monolithe
// les deux points d'entrée (fiche ℹ et worklog), qui appellent le pont openStatusMenu.
const metaView2888 = fs.readFileSync(path.join(__dirname, "src/views/tickets/Meta.view.js"), "utf8");
assert(/data-action="status" data-rm=/.test(metaView2888),
  "la fiche du ticket ouvre le menu depuis sa pastille de phase (vue migrée, RM2889)");
assert(/data-action="status" data-ref=/.test(fs.readFileSync(path.join(__dirname, "src/views/worklog/Worklog.view.js"), "utf8")),
  "le worklog aussi : c'est le second point d'entrée demandé (vue migrée)");
console.log("✓ câblage (RM2888) : fiche + worklog appellent le menu de statut migré");

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
// 6. …et il suit la vue : le titre du centre (routeur, RM2889) rejoue les effets de bord
//    prêtés par le monolithe à chaque changement de vue — renderRTitle en tête.
assert(/function curTitleSideEffects\(\) \{\s*\n\s*renderRTitle\(\);/.test(html),
  "renderRTitle doit être appelé à tout changement de vue (curTitleSideEffects)");
assert(/if \(ctx\.afterTitle\) ctx\.afterTitle\(\);/.test(fs.readFileSync(path.join(__dirname, "src/controllers/center.controller.js"), "utf8")),
  "…et le routeur du centre les rejoue après chaque titre");
console.log("✓ libellé de session (RM2894) : en-tête au-dessus des onglets, 3 sources, échappement");

// ── RM2807 : fan-out exponentiel de renderTickets / renderOpened ─────────────
// Deux sites bouclent sur une LISTE de tickets et se RE-RENDENT à chaque
// résolution : `list.forEach(t => { if (resolveCache[t] === undefined)
// ensureResolved(t).then(render) })`. Sans garde, chaque rendu ré-abonne un
// NOUVEAU .then(render) à chaque ticket encore en vol → le nombre de rendus
// DOUBLE par ticket résolu (2^N ; 20 tickets = 1 048 576 rendus). Chaque rendu
// reconstruit tout l'innerHTML (+ handlers onclick tracés par le ramasse-cycles) :
// CPU à fond, event-loop saturé, RAM native qui explose — la fuite Firefox RM2807
// (prouvée au profil : PromiseReactionJob → renderTickets → set innerHTML).
// La garde `!resolveInflight[t]` limite à UN .then(render) par ticket → N+1 rendus.
// On vérifie qu'elle n'est retirée d'AUCUN des deux sites.
{
  const nonGarde = html.match(/resolveCache\[t\] === undefined\)\s*ensureResolved\(t\)\.then/g) || [];
  assert(nonGarde.length === 0,
    "RM2807 : fan-out NON gardé (" + nonGarde.length + " site[s]) — il manque `&& !resolveInFlight(t)`");
  const garde = html.match(/resolveCache\[t\] === undefined && !resolveInFlight\(t\)\)\s*ensureResolved\(t\)\.then/g) || [];
  // renderOpened a MIGRÉ à son tour (RM2889, panneau 🎫) : sa garde lit l'état en vol par la façade ticket
  assert(/!T\.inFlight\(t\)\)\s*T\.ensureResolved\(t\)\.then\(renderOpened\)/.test(fs.readFileSync(path.join(__dirname, "src/controllers/tickets.controller.js"), "utf8")), "RM2807 : garde absente du contrôleur du panneau tickets");
  // renderTickets a MIGRÉ (RM2889) : sa garde lit l'état en vol par la façade ticket
  assert(/!T\.inFlight\(t\)\)\s*T\.ensureResolved\(t\)\.then/.test(metaCtrl), "RM2807 : garde absente du contrôleur de l'encart");
  // …et la garde doit EXISTER : sa table a migré avec le dépôt ticket (RM2889), le monolithe
  // la lit par un pont — une référence orpheline lèverait une ReferenceError au premier ticket non résolu.
  assert(/function resolveInFlight\(rm\)/.test(html), "RM2807 : le pont resolveInFlight manque");
  assert(/inFlight: \(rm\) =>/.test(fs.readFileSync(path.join(__dirname, "src/boot.js"), "utf8")), "RM2807 : la façade ticket n'expose pas inFlight");
  console.log("✓ fan-out tickets borné (RM2807) : garde !resolveInflight aux 2 sites");
}

// ── RM2991 : recherche de session dans le panneau de reprise : MIGRÉ (RM2889) — voir test_cockpit_resume.js ──
