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
const blocks = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].filter(b => b[1].trim());   // inline seulement
assert.strictEqual(blocks.length, 1, "un seul bloc <script> inline : le boot de thème — tout le reste est en modules (RM2889, L6)");
blocks.forEach((b, i) => new vm.Script(b[1], { filename: `index.html<script#${i}>` }));
console.log(`✓ syntaxe des ${blocks.length} blocs <script> inline`);

// — 2. computeGroups (RM2140/2283/2427/2327/2537/2344) : MIGRÉ (RM2889, liste des sessions) — voir test_cockpit_sessions.js —

// — 3. mdToHtml (RM2309) : MIGRÉ (RM2889, src/core/markdown.js) — voir test_cockpit_doc.js —
// — 4. tqMatch (RM2315) : MIGRÉ (RM2889, file à tester) — voir test_cockpit_testqueue.js —

// — 5. nextAttentionId (RM2302) : RETIRÉ avec le bouton « ⚠ suivante » de l'en-tête (RM2889) —

// — 6. approveShortcutVisible (RM2332) : MIGRÉ (RM2889) — voir test_cockpit_sessions.js —

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
// RM3012 : le CSS est compilé (src/styles/main.scss → cockpit.css, format développé) ; on le ramène au format historique
// « une règle par ligne » pour que les assertions écrites contre <style> restent lisibles telles quelles.
const css = fs.readFileSync(path.join(__dirname, "cockpit.css"), "utf8").replace(/\{\n\s*/g, "{ ").replace(/;\n\s*/g, "; ").replace(/\n\s*\}/g, " }");
const tokensOf = (sel) => {
  const blk = new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{([^}]*)\\}").exec(css);
  assert(blk, "bloc CSS introuvable : " + sel);
  return new Set([...blk[1].matchAll(/(--[a-z0-9-]+)\s*:/g)].map(m => m[1]));
};
const dark = tokensOf(':root, :root[data-theme=dark]');     // sass écrit les valeurs d'attribut sans guillemets
const light = tokensOf(':root[data-theme=light]');
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
const lightHex = hexOf(':root[data-theme=light]');
for (const [fg, bg] of PAIRS) {
  const r = contrast(lightHex[fg], lightHex[bg]);
  assert(r >= 4.5, `light : ${fg} sur ${bg} = ${r.toFixed(2)}:1 < 4.5 (WCAG AA)`);
}
// Le thème sombre est historique : --muted y est à ~3.9-4.4:1 (sous AA) depuis
// toujours. On NE régresse pas au-delà de cet existant, sans le corriger ici
// (changer la teinte du thème par défaut n'est pas le périmètre de RM2386).
const darkHex = hexOf(':root, :root[data-theme=dark]');
for (const [fg, bg] of PAIRS) {
  const r = contrast(darkHex[fg], darkHex[bg]);
  const floor = fg === "--muted" ? 3.9 : 4.5;
  assert(r >= floor, `dark : ${fg} sur ${bg} = ${r.toFixed(2)}:1 < ${floor} (régression)`);
}
console.log(`✓ contrastes : thème clair AA sur ${PAIRS.length} paires, thème sombre sans régression`);

// — effDisposition (RM2515) : MIGRÉ (RM2889) — voir test_cockpit_sessions.js —
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
const termBg = { dark: hexOf(':root, :root[data-theme=dark]')["--term-bg"],
                 light: hexOf(':root[data-theme=light]')["--term-bg"] };
const termFg = { dark: hexOf(':root, :root[data-theme=dark]')["--term-fg"],
                 light: hexOf(':root[data-theme=light]')["--term-fg"] };
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

// — RM3286 : défilement TACTILE du terminal — xterm.js ne gère pas le toucher —
const touchScrollLinesRaw = pick("touchScrollLines");
// le résultat vient d'un autre contexte vm : on le recopie ici, sinon deepStrictEqual bute sur le prototype
const touchScrollLines = (dy, h, acc) => Object.assign({}, touchScrollLinesRaw(dy, h, acc));
assert.deepStrictEqual(touchScrollLines(50, 17, 0), { lines: 2, rest: 16, pixels: 34 }, "un glissement vers le haut descend dans l'historique");
assert.deepStrictEqual(touchScrollLines(-50, 17, 0), { lines: -2, rest: -16, pixels: -34 }, "…et l'inverse remonte, symétriquement");
assert.deepStrictEqual(touchScrollLines(5, 17, 0), { lines: 0, rest: 5, pixels: 0 }, "un micro-mouvement ne défile pas : il s'accumule");
assert.deepStrictEqual(touchScrollLines(5, 17, 13), { lines: 1, rest: 1, pixels: 17 }, "…et le reliquat finit par donner une ligne (le texte suit le doigt)");
assert.strictEqual(touchScrollLines(50, 0, 0).lines, 2, "hauteur de ligne inconnue → défaut xterm, jamais de division par zéro");
assert.deepStrictEqual(touchScrollLines(0, 17, 0), { lines: 0, rest: 0, pixels: 0 }, "doigt immobile : rien");

// installTouchScroll : le geste devient une MOLETTE (xterm choisit ensuite : l'envoyer à
// l'application qui suit la souris — tmux —, ou défiler son tampon). Cycle de vie des
// écouteurs, un seul doigt, appui simple préservé.
const mITS = />>> installTouchScroll\n(\s*function installTouchScroll[\s\S]*?)\n  \/\/ <<< installTouchScroll/.exec(termSrc);
assert(mITS, "marqueurs >>> installTouchScroll / <<< installTouchScroll introuvables");
const wheels = [];
class FakeWheelEvent { constructor(type, init) { Object.assign(this, { type }, init); } }
const installTouchScroll = vm.runInNewContext("(" + mITS[1] + ")", { touchScrollLines: touchScrollLinesRaw, WheelEvent: FakeWheelEvent });
function fakeTouchBox() {
  const ls = { touchstart: [], touchmove: [], touchend: [], touchcancel: [] };
  const screen = { dispatchEvent: (ev) => { wheels.push(ev); return true; } };
  return { clientHeight: 240, querySelector: (sel) => (sel === ".xterm-screen" ? screen : null),
    addEventListener: (t, f) => ls[t].push(f), removeEventListener: (t, f) => { const i = ls[t].indexOf(f); if (i >= 0) ls[t].splice(i, 1); },
    count: () => Object.values(ls).reduce((n, a) => n + a.length, 0),
    fire(t, ev) { for (const f of ls[t].slice()) f(ev); } };
}
const scrolled = []; let prevented = 0;
const box3286 = fakeTouchBox();
const term3286 = { rows: 24, scrollLines: (n) => scrolled.push(n) };   // 240 px / 24 lignes = 10 px la ligne
const stopTouch = installTouchScroll(box3286, term3286);
const touch = (y) => ({ touches: [{ clientY: y, clientX: 40 }], cancelable: true, preventDefault: () => prevented++ });
box3286.fire("touchstart", touch(500));
box3286.fire("touchmove", touch(497));
assert.deepStrictEqual(wheels, [], "3 px : sous une ligne, on ne défile pas et on NE CONFISQUE PAS le geste");
assert.strictEqual(prevented, 0, "…donc l'appui simple garde le focus et le clavier");
box3286.fire("touchmove", touch(470));
assert.strictEqual(wheels.length, 1, "30 px de plus → une molette");
assert.strictEqual(wheels[0].type, "wheel");
assert.strictEqual(wheels[0].deltaY, 30, "…de 3 lignes, en pixels (deltaMode 0), comme une vraie molette");
assert.strictEqual(wheels[0].deltaMode, 0);
assert.strictEqual(wheels[0].clientX, 40, "la position du doigt voyage avec : tmux s'en sert pour viser le bon pane");
assert(wheels[0].cancelable && wheels[0].bubbles, "elle doit remonter jusqu'aux écouteurs d'xterm");
assert.deepStrictEqual(scrolled, [], "on n'appelle PLUS scrollLines : dans l'écran alternatif il ne ferait rien");
assert.strictEqual(prevented, 1, "là seulement, le geste est capté (pas de défilement de page par-dessus)");
box3286.fire("touchmove", touch(500));
assert.strictEqual(wheels.length, 2, "retour vers le bas de l'écran → molette en sens inverse");
assert.strictEqual(wheels[1].deltaY, -30);
const capteApresDeuxDefilements = 2;   // chaque défilement réel capte le geste : deux jusqu'ici
box3286.fire("touchend", {});
box3286.fire("touchmove", touch(400));
assert.strictEqual(wheels.length, 2, "doigt levé : plus rien ne défile");
box3286.fire("touchstart", { touches: [{ clientY: 500 }, { clientY: 300 }] });
box3286.fire("touchmove", { touches: [{ clientY: 400 }, { clientY: 300 }], cancelable: true, preventDefault: () => prevented++ });
assert.strictEqual(wheels.length, 2, "deux doigts : c'est un pincer-zoomer, on n'y touche pas");
assert.strictEqual(prevented, capteApresDeuxDefilements, "…et on ne le bloque pas non plus (aucune capture de plus)");
// repli : sans WheelEvent (vieux moteur), on défile au moins le tampon local
const boxOld = fakeTouchBox();
const stopOld = vm.runInNewContext("(" + mITS[1] + ")", { touchScrollLines: touchScrollLinesRaw })(boxOld, term3286);
boxOld.fire("touchstart", touch(500)); boxOld.fire("touchmove", touch(470));
assert.deepStrictEqual(scrolled, [3], "WheelEvent indisponible → repli sur le tampon local, jamais d'erreur");
stopOld();
stopTouch();
assert.strictEqual(box3286.count(), 0, "écouteurs tactiles retirés au dispose (le conteneur survit aux remontages)");
console.log("✓ défilement tactile (RM3286) : le geste devient une molette (tmux la reçoit), appui simple et pincer-zoomer préservés, écouteurs libérés");
// — sortFrozen (RM2346) : MIGRÉ (RM2889) — voir test_cockpit_sessions.js —

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

// — composerGuard / composerHistoryAdd (RM2527) : MIGRÉS (RM2889, terminal) — voir test_cockpit_terminal.js —

// — 9. outline enrichi (RM2549/2596) : MIGRÉ (RM2889, outline) — voir test_cockpit_outline.js —

// — termBase (RM2561) : MIGRÉ (RM2889, terminal) — voir test_cockpit_terminal.js —

// — 10. réducteur de la colonne de droite (RM2466/2579/2952) : MIGRÉ (RM2889, layout) — voir test_cockpit_layout.js —

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
assert(/main\.lcollapsed \{\s*grid-template-columns: 34px 1fr;\s*\}/.test(css),
  "la colonne gauche se replie vers la gauche (largeur réduite, pas masquée)");
assert(/\.rpanel\.collapsed \{\s*width: 34px;\s*\}/.test(css),
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
const mTabs = /export const TABS = \[([^\]]*)\]/.exec(fs.readFileSync(path.join(__dirname, "src/modules/layout/panels.js"), "utf8"));
assert(mTabs, "whitelist TABS de la colonne de droite introuvable (modèle migré)");
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

// — titleLink (RM2585) : MIGRÉ (RM2889, liens) — voir test_cockpit_shell.js —

// — sinceLabel (RM2630) : MIGRÉ (RM2889, modèle ticket) — voir test_cockpit_ticket.js —

// — worklogDocs (RM2584) : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —


// — RM2596 : linkify / jarg : MIGRÉS (RM2889, liens + core/html) — voir test_cockpit_shell.js et test_cockpit_core.js —

// — worklogDocsHtml (RM2935) : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2623/RM2634 : glossaire du jargon : MIGRÉ (RM2889) — voir test_cockpit_doc.js —

// — RM2639 : contexte client (pré-filtre global du cockpit) —
// clientCtxList / clientCtxProject : MIGRÉS (RM2889, lanceur) — voir test_cockpit_launcher.js ; sessionInClient : MIGRÉ (RM2889, liste des sessions) — voir test_cockpit_sessions.js

// — pendStaleSet (RM2598) : MIGRÉ (RM2889, pile /refresh) — voir test_cockpit_refresh.js —

// — clampWidth (RM2599) : MIGRÉ (RM2889, layout) — voir test_cockpit_layout.js —

// — setEditOptions (RM2955) : MIGRÉ (RM2889, jeux de sessions) — voir test_cockpit_sets.js —

// — RM2952 : la largeur RÉGLÉE prime sur le confort par défaut —
// `max(--rpanel-w, 460px)` imposait un plancher de 460 px sur l'onglet
// conversation : la poignée ne réduisait plus rien en dessous, et le réglage
// passait pour cassé. Le défaut de 460 px vit désormais dans le `var()`.
assert(/\.rpanel\.wide \{\s*width: var\(--rpanel-w, 460px\);\s*\}/.test(css),
  "onglet conversation : 460px en DÉFAUT de --rpanel-w, jamais en plancher");
assert(!/\.rpanel\.wide \{\s*width: max\(/.test(css),
  "plus de max() : il rendait la poignée inopérante sous 460px");
const layoutCtl = fs.readFileSync(path.join(__dirname, "src/modules/layout/layout.controller.js"), "utf8");
assert(/function resetWidth\(\)[^\n]*removeProperty\("--rpanel-w"\)/.test(layoutCtl),
  "réinitialiser RETIRE la largeur (sinon 330px figerait aussi l'onglet conversation) — contrôleur migré");
assert(!/function resetWidth\(\)[^\n]*R_WIDTH_DEFAULT/.test(layoutCtl), "réinitialiser n'écrit plus 330px en dur");
console.log("\u2713 largeur du panneau (RM2952) : le réglage prime, le défaut reste un défaut");

// — outByKind (RM2601) : MIGRÉ (RM2889, outline) — voir test_cockpit_outline.js —

// — vue git (RM2602) : domaine MIGRÉ (RM2889, L4) — voir test_cockpit_git.js —

// — RM2605 : tickets cliquables du worklog : MIGRÉ (RM2889) — voir test_cockpit_worklog.js —

// — RM2605 : « infos » allégé : MIGRÉ (RM2889, encart ℹ) — voir test_cockpit_meta.js —

// — RM2606/RM2883 : tickets ouverts (liste, ordre, familles, groupes) : MIGRÉ (RM2889, panneau 🎫) — voir test_cockpit_tickets.js —

// le badge de l'onglet et l'alimentation depuis les deux portes d'entrée
assert(/id="ln-tickets"/.test(html), "l'onglet tickets porte un compteur");
const metaCtrl = fs.readFileSync(path.join(__dirname, "src/modules/meta/meta.controller.js"), "utf8");
assert(/ctx\.noteOpened\(id\)/.test(metaCtrl), "ouvrir une fiche alimente la liste (contrôleur migré, RM2889)");
const revCtrl = fs.readFileSync(path.join(__dirname, "src/modules/review/review.controller.js"), "utf8");
assert(/ctx\.noteOpened\(rm\)/.test(revCtrl), "ouvrir une revue aussi (contrôleur migré, RM2889)");
assert(/karlOpenedTickets/.test(fs.readFileSync(path.join(__dirname, "src/modules/tickets/tickets.service.js"), "utf8")), "la liste survit au rechargement (localStorage, service migré)");
console.log("✓ tickets ouverts (RM2606) : compteur, deux portes d'entrée, persistance");

// — worklogTabList (RM2610) : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2611 : MIGRÉ (RM2889, modèle ticket) — voir test_cockpit_ticket.js —

// — pollDelay (RM2613) : MIGRÉ (RM2889, pile /refresh) — voir test_cockpit_refresh.js —

// — RM2614 : client/projet du ticket : MIGRÉ (RM2889, encart ℹ) — voir test_cockpit_meta.js —

// — RM2619 : infobulles : MIGRÉ (RM2889, panneau 🎫) — voir test_cockpit_tickets.js —

// — RM2622 : doc du projet dans l'onglet fichiers : MIGRÉ (RM2889) — voir test_cockpit_files.js —

// — RM2384 : mcBanner MIGRÉ (RM2889, modèle ticket) — voir test_cockpit_ticket.js —

// — RM2458 / RM2708 : santé du poste — domaine MIGRÉ (RM2889, L5), voir test_cockpit_env.js —

// — RM2659 : racines groupées par projet : MIGRÉ (RM2889) — voir test_cockpit_files.js —

// — RM1952 : triage ROI : MIGRÉ (RM2889, panneau 🎫) — voir test_cockpit_tickets.js —

// — RM2673 : écriture dans un jeu, tickets du worklog, fichiers sans session —
// setWritable, 💾 / ⊖ / ⟳ / → déplacer / scinder selon le jeu (RM2673) : MIGRÉS (RM2889, jeux de sessions) — voir test_cockpit_sets.js et test_cockpit_sessions.js

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

// — RM2718 : pastille du statut de session : MIGRÉE (RM2889, liens) — voir test_cockpit_shell.js —

// — RM2719 : portée restreinte : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2720 : actions PM d'un ticket, chips de session : MIGRÉS (RM2889, actions) — voir test_cockpit_actions.js —

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
assert(/@keyframes updpulse \{[\s\S]*?\} \}/.test(css), "@keyframes updpulse introuvable");
// pas de kblink ici : il fond à opacity .25, ce qui rend un bouton TEXTUEL
// illisible la moitié du temps — et celui-ci reste affiché tant que la MAJ n'est
// pas appliquée.
assert(!/animation:\s*kblink/.test(mUpd[1]), "#updbtn ne doit pas fondre en opacité (kblink)");
assert(!/opacity/.test(/@keyframes updpulse \{([\s\S]*?)\} \}/.exec(css)[1]),
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

// — RM2741 : barre du panneau « en cours » (relaunchBtnState, newSetPlan, ruleFormHtml) : MIGRÉ (RM2889) — voir test_cockpit_sets.js —

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
assert(/listen\(opened, "toggle"/.test(fs.readFileSync(path.join(__dirname, "src/modules/tickets/tickets.controller.js"), "utf8")), "…et il l'écoute");
assert(/id="opened-count"/.test(html), "l'en-tête doit porter le compteur");
assert(!/<details class="card" id="openedcard"[^>]*\bopen\b/.test(html),
  "pas d'attribut open en dur : l'état initial vient du localStorage");
// Le « ? » d'aide est DANS le summary : sans stopPropagation, le consulter
// replierait la carte — un clic qui fait deux choses dont une non voulue.
const sumOpened = /<summary>Tickets ouverts[\s\S]*?<\/summary>/.exec(html);
assert(sumOpened, "summary de la carte introuvable");
assert(/data-cmd="help" data-arg="tickets" data-stop/.test(sumOpened[0]),
  "le bouton d'aide ne doit pas replier la carte");
console.log("✓ tickets ouverts (RM2757) : carte repliable, repliée au départ, compte visible");

// — RM2759 : MIGRÉ (RM2889, cluster centre) — voir test_cockpit_center.js —

// — RM2760 : panneau « projets » — domaine MIGRÉ (RM2889, L4), voir test_cockpit_projects.js —
// Le câblage : un panneau que rien n'ouvre n'existe pas.
assert(/data-panel="projects"/.test(html), "l'onglet gauche doit exister");
assert(/<div class="lpanel" id="lp-projects"><\/div>/.test(html), "…avec son panneau (hôte monté par boot.js)");
assert(/projects: \(\) => projects\.refresh\(\)/.test(fs.readFileSync(path.join(__dirname, "src/boot.js"), "utf8")), "…et son chargeur (panneaux gauche migrés : boot.js)");

// ── RM2675 : glossaire de projet (lecture, filtre) : MIGRÉ (RM2889) — voir test_cockpit_doc.js. Reste le câblage :
// Le câblage : un sous-onglet que rien n'affiche n'existe pas.
assert(/data-action="vocab" data-on="1"/.test(fs.readFileSync(path.join(__dirname, "src/modules/files/Files.view.js"), "utf8")), "le sous-onglet vocabulaire doit être cliquable (vue migrée)");
assert(/glossaire\.md/.test(fs.readFileSync(path.join(__dirname, "src/modules/files/files.service.js"), "utf8")), "…et il doit chercher docs/glossaire.md (service migré)");
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
assert(/redmine_error/.test(fs.readFileSync(path.join(__dirname, "src/modules/search/search.controller.js"), "utf8")),
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
assert(/\.tabbar \{[^}]*flex-direction: column/.test(css),
  ".tabbar doit empiler ses deux lignes");
assert(/\.tabbar2 \{[^}]*display: flex/.test(css),
  ".tabbar2 doit aligner titre et actions sur une ligne");
// Le bridage à 62 % n'a plus lieu d'être : les onglets ont la largeur entière.
const ctabsCss = /\.ctabs \{[^}]*\}/.exec(css);
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

// — RM2787/RM2793 : silence d'une session (agoHM, quietSince, quietHtml, infobulle) : MIGRÉS (RM2889) — voir test_cockpit_sessions.js —

// — RM2795 : la marque d'épinglage (pinMark : MIGRÉ, test_cockpit_center.js) —
// Les cinq surfaces doivent appeler la MÊME fonction — cinq variantes d'un même
// signal, ce serait cinq signaux.
// RM2889 : la liste des sessions est migrée — tuiles et revues ouvertes reçoivent la marque du routeur par le contrôleur
const sessionsView2795 = fs.readFileSync(path.join(__dirname, "src/modules/sessions/Sessions.view.js"), "utf8");
assert(/raw\(pin\("session", s\.rm_id\)\)/.test(sessionsView2795), "marque absente : tuiles de session (migrées)");
assert(/raw\(pin\("review", v\.rm\)\)/.test(sessionsView2795), "marque absente : revues ouvertes (migrées)");
// RM2889 : la recherche est migrée — sa vue reçoit la marque du routeur par le contrôleur
assert(/raw\(pin\("review", r\.rm\)\)/.test(fs.readFileSync(path.join(__dirname, "src/modules/search/Search.view.js"), "utf8")),
  "marque absente : résultats de recherche (migrés)");
// RM2889 : les tickets ouverts sont migrés — la vue reçoit la marque du routeur (pinOf) par le contrôleur
assert(/raw\(pin\("review", it\.rm\)\)/.test(fs.readFileSync(path.join(__dirname, "src/modules/tickets/TicketsPanel.view.js"), "utf8")),
  "marque absente : tickets ouverts (migrés)");
// RM2889 : la file à tester est migrée — sa marque vient du routeur, prêtée au ViewModel
assert(/this\.ctx\.pin\("review", e\.rm_id\)/.test(fs.readFileSync(path.join(__dirname, "src/modules/testqueue/TestQueueViewModel.js"), "utf8")),
  "marque absente : file à tester (migrée)");
assert(/pin\("project", p\.value\)/.test(fs.readFileSync(path.join(__dirname, "src/modules/projects/ProjectsPanelViewModel.js"), "utf8")),
  "marque absente : panneau projets (migré RM2889)");
assert(/raw\(pin\("review", it\.rm\)\)/.test(fs.readFileSync(path.join(__dirname, "src/modules/worklog/Worklog.view.js"), "utf8")), "marque absente : worklog (migré)");
// …et l'état doit suivre le geste, sans attendre le prochain poll.
// RM2889 : l'épinglage vit dans le routeur du centre ; c'est lui qui prévient les listes
const centerSrc = fs.readFileSync(path.join(__dirname, "src/modules/center/center.controller.js"), "utf8");
assert(/function togglePin[\s\S]{0,400}ctx\.onPinChange\(\)/.test(centerSrc),
  "détacher un onglet doit rafraîchir les listes tout de suite");
assert(/opts && opts\.pin && ctx\.onPinChange\) ctx\.onPinChange\(\)/.test(centerSrc),
  "…et épingler à l'ouverture aussi");
// Le panneau projets reçoit la marque en option : porté dans test_cockpit_projects.js (RM2889).
console.log("✓ marque d'épinglage (RM2795) : la même icône dans les listes, à jour au clic");

// — RM2796 : pastille de statut : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js —

// — RM2797 : description et historique en facettes : MIGRÉ (RM2889, encart ℹ) — voir test_cockpit_meta.js.
// Reste au monolithe la feuille de style : une facette doit pouvoir occuper toute la hauteur.
assert(/\.facetfull \{[^}]*max-height: none/.test(css),
  "une facette doit pouvoir occuper toute la hauteur");
console.log("✓ fiche ticket (RM2797) : style des facettes pleine hauteur conservé");

// — RM2798 : worklog groupé : MIGRÉ (RM2889) — voir test_cockpit_worklog.js —

// — RM2799 : hiérarchie de lecture — la section, puis le numéro, puis le statut —
// Le groupe doit être une SECTION : sans délimitation, son en-tête se lisait
// comme une ligne de plus.
const cssGroup2799 = /\.wlgroup \{[^}]*\}/.exec(css);
assert(cssGroup2799, ".wlgroup introuvable");
assert(/border:/.test(cssGroup2799[0]) && /background:/.test(cssGroup2799[0]),
  "un groupe doit se distinguer par un fond ET une bordure");
const cssHead2799 = /\.wlghead \{[^}]*\}/.exec(css);
assert(/background:/.test(cssHead2799[0]) && /border-bottom:/.test(cssHead2799[0]),
  "l'en-tête doit appartenir à la section, pas flotter au-dessus");

// Le numéro identifie la ligne : il doit primer sur le statut, y compris jaune.
const cssRef2799 = /\.rmref \{[^}]*\}/.exec(css);
assert(cssRef2799, ".rmref introuvable — le numéro doit avoir son propre style");
const cssPill2799 = /\n\.pill \{[^}]*\}/.exec(css);
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
const cssDescFull = /\.descfull \{[^}]*\}/.exec(css);
assert(cssDescFull, ".descfull introuvable");
assert(/background: none/.test(cssDescFull[0]) && /border: 0/.test(cssDescFull[0]),
  "ni fond ni bordure : la description occupe la zone, elle n'est pas encadrée");
assert(/max-height: none/.test(cssDescFull[0]) && /overflow: visible/.test(cssDescFull[0]),
  "aucune bride : c'est la colonne qui défile");
// …et le bloc encadré d'origine doit rester intact là où il sert encore.
const cssDesc2806 = /\n\.desc \{[^}]*\}/.exec(css);
assert(cssDesc2806 && /max-height: 160px/.test(cssDesc2806[0]),
  "le bloc `.desc` d'origine n'a pas à changer : il sert ailleurs");
// Le piège de cascade, une seconde fois : `.descfull` ne doit pas redéclarer ce
// que `.mdview` porte, sous peine de reproduire le conflit qu'on vient de régler.
assert(!/font-size/.test(cssDescFull[0]) && !/line-height/.test(cssDescFull[0]),
  "`.descfull` ne redéclare pas ce que `.mdview` porte déjà");
console.log("✓ facette description (RM2806) : plus de cadre ni de bride, la colonne défile");
// — pile de refresh (RM2763) : MIGRÉE (RM2889) — voir test_cockpit_refresh.js —

// — RM2816 : « commandes pm » et « réglages » quittent la colonne de gauche —
// Deux surfaces d'action (pas de consultation) qui prenaient deux onglets sur
// huit à la barre de gauche, dans une colonne trop étroite pour leurs
// formulaires. Elles passent au menu du haut et s'ouvrent au centre.
const nav2816 = /<nav class="lnav">[\s\S]*?<\/nav>/.exec(html);
assert(nav2816, "barre d'onglets de la colonne gauche introuvable");
assert(!/data-panel="pm"/.test(nav2816[0]) && !/data-panel="settings"/.test(nav2816[0]),
  "les deux onglets ne doivent plus être dans la colonne de gauche");
const head2816 = /<header>[\s\S]*?<\/header>/.exec(html)[0];
assert(/data-cmd="panel" data-arg="pm"/.test(head2816) && /data-cmd="panel" data-arg="settings"/.test(head2816),
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
const loaders2816 = /panelLoaders: \{[^}]*\}/.exec(fs.readFileSync(path.join(__dirname, "src/boot.js"), "utf8"))[0];   // RM2889 : chargeurs des panneaux gauche dans boot.js
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
assert(/<button class="mini" id="updbtn" style="display:none"/.test(html) && !/id="updbtn"[^>]*\son\w+=/.test(html),
  "le bouton MAJ garde son comportement (masqué par défaut ; le clic est posé par le contrôleur migré — RM2889)");
assert(/id="updbtn"[\s\S]{0,200}Une mise à jour du code PM est disponible/.test(html),
  "…et son infobulle");
console.log("✓ MAJ dispo (RM2821) : dernier bouton du header, son apparition ne décale plus rien");

// — RM2823 : embarquer un lot ailleurs : MIGRÉ (RM2889, worklog) — voir test_cockpit_worklog.js. Reste l'hôte :
assert(/id="batch-offload-btn"/.test(html), "le bouton d'embarquement doit exister");
console.log("✓ embarquer un lot ailleurs (RM2823) : bouton hôte en place, logique migrée");
// — RM2818 : alerter avant d'ouvrir une 2e session sur un ticket déjà pris —
// Texte d'alerte, garde et spawn depuis la fiche : MIGRÉS (RM2889, test_cockpit_review.js).
// Le lanceur de gauche (spawn) reste au monolithe et doit passer par la garde (pont).
assert(/ctx\.confirmSecondSession && !\(await ctx\.confirmSecondSession\(sb\.rm\)\)/.test(fs.readFileSync(path.join(__dirname, "src/modules/launcher/launcher.controller.js"), "utf8")),
  "spawn (lanceur migré) doit passer par la garde confirmSecondSession");
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
assert(/"search\.tags"/.test(fs.readFileSync(path.join(__dirname, "src/modules/search/SearchRepository.js"), "utf8")), "les étiquettes proposées viennent de GET /tags (dépôt migré)");
assert(/"rf-tag"/.test(fs.readFileSync(path.join(__dirname, "src/modules/sets/Sets.view.js"), "utf8")), "le formulaire de jeu dérivé propose le critère étiquette (vue migrée RM2889)");
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
assert(/raw\(fileBody\(f\.raw\)\)/.test(fs.readFileSync(path.join(__dirname, "src/modules/files/Files.view.js"), "utf8")),
  "l'onglet fichiers (migré) passe par le rendu commun qu'on lui prête");
assert(/raw\(fileBody\(f\)\)/.test(fs.readFileSync(path.join(__dirname, "src/modules/projects/ProjectPane.view.js"), "utf8")),
  "…et la fiche projet aussi, par le rendu qu'on lui prête");

assert(!/class="desc">' \+ mdToHtml\(f\.content\)/.test(html),
  "plus aucun contenu de fichier rendu dans le bloc encadré");
console.log("✓ fichier ouvert (RM2861) : pleine hauteur, un seul rendu pour les trois vues");

// — RM2873 : consigne depuis la fiche : MIGRÉ (RM2889) — voir test_cockpit_review.js —

// ── RM2888 : changer le statut depuis la fiche et le worklog ────────────────
// Menu, invites, gardes : MIGRÉS (RM2889) — voir test_cockpit_review.js. Restent au monolithe
// les deux points d'entrée (fiche ℹ et worklog), qui appellent le pont openStatusMenu.
const metaView2888 = fs.readFileSync(path.join(__dirname, "src/modules/meta/Meta.view.js"), "utf8");
assert(/data-action="status" data-rm=/.test(metaView2888),
  "la fiche du ticket ouvre le menu depuis sa pastille de phase (vue migrée, RM2889)");
assert(/data-action="status" data-ref=/.test(fs.readFileSync(path.join(__dirname, "src/modules/worklog/Worklog.view.js"), "utf8")),
  "le worklog aussi : c'est le second point d'entrée demandé (vue migrée)");
console.log("✓ câblage (RM2888) : fiche + worklog appellent le menu de statut migré");

// — RM2894 : libellé de la session en en-tête du panneau de droite : MIGRÉ (RM2889) — voir test_cockpit_sessions.js —

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
  // RM3005 : plus de `.then(render)` du tout — la garde in-flight reste, le re-rendu vient d'UN abonnement au store de résolution
  { const tk = fs.readFileSync(path.join(__dirname, "src/modules/tickets/tickets.controller.js"), "utf8"); assert(/!T\.inFlight\(t\)\)\s*T\.ensureResolved\(t\);/.test(tk) && /resolve\(\)\.subscribe\(/.test(tk) && !/ensureResolved\([^)]*\)\.then/.test(tk), "RM2807/RM3005 : garde in-flight + abonnement au store attendus dans le panneau tickets"); }
  // renderTickets a MIGRÉ (RM2889) : sa garde lit l'état en vol par la façade ticket
  // RM3140 : l'encart ne résout plus ticket par ticket — la liste part en UNE requête brève, et le
  // re-rendu vient toujours de l'abonnement au store. La garde anti fan-out devient donc inutile là :
  // il n'y a plus de boucle à garder. Ce qui doit rester vrai, c'est qu'aucun `.then(render)` par
  // ticket ne revienne, et que rien ne reboucle sur `ensureResolved` dans un rendu.
  assert(/T\.ensureBriefs\(probe\.list\)/.test(metaCtrl) && /resolve\(\)\.subscribe\(/.test(metaCtrl)
         && !/ensureResolved\(t\)/.test(metaCtrl) && !/forEach\(t => \{[^}]*ensureResolved/.test(metaCtrl),
    "RM3140/RM3005 : la liste de l'encart se résout en UN lot, et le re-rendu vient de l'abonnement");
  // …et la garde doit EXISTER : sa table a migré avec le dépôt ticket (RM2889), le monolithe
  // la lit par un pont — une référence orpheline lèverait une ReferenceError au premier ticket non résolu.
  // RM2889 L6 : plus de script inline — les deux sites lisent la garde sur la façade ticket (boot.js)
  assert(/inFlight: \(rm\) =>/.test(fs.readFileSync(path.join(__dirname, "src/boot.js"), "utf8")), "RM2807 : la façade ticket n'expose pas inFlight");
  console.log("✓ fan-out tickets borné (RM2807) : garde !resolveInflight aux 2 sites");
}

// ── RM2991 : recherche de session dans le panneau de reprise : MIGRÉ (RM2889) — voir test_cockpit_resume.js ──

// ── RM3150 : les portes du cockpit — icône seule, nom au survol, groupées à gauche ──
// Ce qu'on veut tenir dans le temps : que la barre ne reprenne pas du poids bouton par bouton,
// et qu'une icône sans libellé garde son nom quelque part — sinon elle devient un rébus.
{
  const grp = /<span class="hgo">([\s\S]*?)<\/span>\s*(?:<!--|<button|<select)/.exec(html);
  assert(grp, "RM3150 : le groupe des portes existe");
  const bloc = grp[1];
  const attendus = ["histback", "histfwd", "histbtn", "helpbtn", "setbtn", "journalbtn", "contactsbtn"];
  for (const id of attendus) assert(new RegExp('id="' + id + '"').test(bloc), "RM3150 : « " + id + " » est dans le groupe");
  // l'ORDRE demandé : historique, aide, réglages, journal, annuaire (les flèches restent avec l'historique)
  const ordre = ["histbtn", "helpbtn", "setbtn", "journalbtn", "contactsbtn"].map(id => bloc.indexOf('id="' + id + '"'));
  assert(ordre.every((v, i) => i === 0 || v > ordre[i - 1]), "RM3150 : l'ordre demandé est tenu");
  // le groupe vient AVANT le reste de la barre : « tout à gauche »
  assert(html.indexOf('class="hgo"') < html.indexOf('id="monitorbtn"'), "RM3150 : groupé à gauche, avant les actions");
  for (const m of bloc.matchAll(/<button[^>]*id="(\w+)"[^>]*>([\s\S]*?)<\/button>/g)) {
    const [, id, dedans] = m;
    const texte = dedans.replace(/<span[\s\S]*?<\/span>/g, "").trim();   // le badge n'est pas un libellé
    assert(texte.length > 0 && texte.length <= 2, "RM3150 : « " + id + " » ne porte que son icône (" + texte + ")");
  }
  // le nom doit rester atteignable au survol : un title qui ne dit que la description ferait un rébus
  const noms = { histbtn: /Historique/, helpbtn: /Aide/, setbtn: /Réglages/, journalbtn: /Journal/, contactsbtn: /Annuaire/,
                 histback: /Précédent/, histfwd: /Suivant/ };
  for (const [id, re] of Object.entries(noms)) {
    const b = new RegExp('<button[^>]*id="' + id + '"[^>]*title="([^"]*)"').exec(bloc)
           || new RegExp('<button[^>]*id="' + id + '"[\\s\\S]*?title="([^"]*)"').exec(bloc);
    assert(b && re.test(b[1]), "RM3150 : le nom de « " + id + " » apparaît au survol");
  }
  assert(!/\son(click|change)=/.test(bloc), "RM3150 : aucun handler en attribut");
  const css = fs.readFileSync(path.join(__dirname, "cockpit.css"), "utf8");
  assert(/header \.hgo \.nbadge/.test(css), "RM3150 : le compteur reste lisible sur une icône seule");
  console.log("✓ portes du cockpit (RM3150) : icône seule, nom au survol, groupées à gauche, ordre tenu");
}
