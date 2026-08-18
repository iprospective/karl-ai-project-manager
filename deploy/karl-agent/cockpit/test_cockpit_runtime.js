#!/usr/bin/env node
// Tests RM2714 — le cockpit s'EXÉCUTE (pas seulement : il compile).
//
// test_cockpit.js vérifie la syntaxe et les fonctions pures, une par une, dans
// des sandboxes isolés. Aucun de ces filets n'attrape le défaut qui a cassé la
// production : un identifiant appelé HORS de la portée où il est déclaré
// (`const val = …` local à une fonction, appelé depuis quatre autres). C'est une
// `ReferenceError` à l'exécution — donc il faut exécuter.
//
// Ce harnais monte un DOM minimal, évalue le script complet, puis exerce les
// fonctions qui touchent au DOM et que les tests purs ne peuvent pas couvrir.
// Il ne remplace pas un navigateur : il attrape les identifiants morts.
//
// Lancer : node deploy/karl-agent/cockpit/test_cockpit_runtime.js
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const vm = require("vm");

const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
let js = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]).join("\n");
// L'IIFE d'init démarre les boucles de poll de la page. On la NEUTRALISE : ce
// harnais teste des rendus, pas une page vivante — et un poll qui se replanifie
// ne rendrait jamais la main. Le reste du script s'évalue normalement, ce qui
// est précisément ce qu'on veut vérifier (déclarations et portées).
js = js.replace("(async function init() {", "(async function init() { if (globalThis.__NO_INIT) return;");

// — DOM factice : assez complet pour que le script s'évalue en entier —
function el(tag) {
  const e = {
    tagName: tag || "div", innerHTML: "", textContent: "", value: "", checked: false,
    style: {}, dataset: {}, options: [], children: [],
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    appendChild(c) { this.children.push(c); return c; },
    insertBefore(c) { this.children.push(c); return c; },
    removeChild() {}, remove() {}, focus() {}, blur() {}, click() {},
    setAttribute() {}, getAttribute: () => null, removeAttribute() {},
    addEventListener() {}, removeEventListener() {}, scrollIntoView() {},
    closest: () => null, querySelector: () => el(), querySelectorAll: () => [],
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0 }),
  };
  return e;
}
const store = { getItem: () => null, setItem() {}, removeItem() {} };
const sandbox = {
  console: { log() {}, warn() {}, error() {}, debug() {} },
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval,
  JSON, Math, Date, Number, String, Boolean, Array, Object, RegExp, Promise, Set, Map,
  encodeURIComponent, decodeURIComponent, parseInt, parseFloat, isNaN, isFinite, Error,
  URL, URLSearchParams,
  document: {
    getElementById: () => el(), querySelector: () => el(), querySelectorAll: () => [],
    createElement: t => el(t), addEventListener() {}, body: el("body"),
    documentElement: el("html"), hidden: false, title: "",
  },
  navigator: { userAgent: "node", clipboard: { writeText: async () => {} } },
  localStorage: store, sessionStorage: store,
  location: { origin: "http://x", port: "", protocol: "http:", hostname: "x", search: "", href: "http://x/" },
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}), text: async () => "" }),
  alert() {}, confirm: () => true, prompt: () => null,
  requestAnimationFrame: fn => fn(),
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  // API navigateur touchées par l'init différé (voix, flux, audio) : stubées pour
  // que le chargement complet de la page aille au bout — sinon le test ne dirait
  // rien de ce qui se passe APRÈS la première ligne en erreur.
  speechSynthesis: { getVoices: () => [], addEventListener() {}, speak() {}, cancel() {} },
  SpeechSynthesisUtterance: function () { return {}; },
  WebSocket: function () { return { addEventListener() {}, close() {}, send() {} }; },
  EventSource: function () { return { addEventListener() {}, close() {} }; },
  AbortController: function () { return { signal: {}, abort() {} }; },
  Audio: function () { return { play: async () => {}, pause() {} }; },
  MediaRecorder: function () { return { start() {}, stop() {} }; },
  IntersectionObserver: function () { return { observe() {}, disconnect() {} }; },
  ResizeObserver: function () { return { observe() {}, disconnect() {} }; },
  btoa: s => Buffer.from(String(s)).toString("base64"),
  atob: s => Buffer.from(String(s), "base64").toString(),
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.__NO_INIT = true;
const ctx = vm.createContext(sandbox);

// 1. le script s'évalue en ENTIER (une exception ici = page morte au chargement)
vm.runInContext(js, ctx, { filename: "index.html<script>" });
console.log("✓ le script du cockpit s'évalue en entier dans un DOM minimal");

// 2. les fonctions qui ont cassé la prod (RM2614 → RM2714) s'exécutent
//    sans identifiant mort. Le réseau et les notifications sont stubés : ce
//    qu'on teste, c'est la portée des identifiants, pas le rendu.
const errors = [];
ctx.toast = (msg, isErr) => { if (isErr) errors.push(String(msg)); };
ctx.api = async () => ({
  commands: [
    { name: "task-status", label: "Statut", category: "tickets", mutate: true,
      args: [{ name: "rm_id", type: "rm_id", required: true, label: "Ticket" },
             { name: "note", type: "text", max_len: 400, label: "Note" },
             { name: "statut", type: "enum", choices: ["a_faire", "en_cours"], label: "Statut" },
             { name: "force", type: "bool", label: "Forcer" }] },
    { name: "conso-report", label: "Conso", category: "métriques", args: [] },
  ],
});

(async () => {
  // — panneau « commandes pm » : c'est LUI qui était en erreur —
  await ctx.loadPmCommands();
  assert.deepStrictEqual(errors, [],
    "loadPmCommands ne doit produire aucune erreur (RM2714 : « val is not defined »)");
  console.log("✓ panneau « commandes pm » : catalogue chargé sans identifiant mort");

  // — le formulaire d'une commande (tous les types d'argument) —
  ctx.pmCommands = (await ctx.api()).commands;
  ctx.renderPmForm("task-status");
  ctx.renderPmForm("conso-report");
  console.log("✓ formulaire d'une commande PM rendu (enum, texte, bool, rm_id)");

  // — fil d'ariane des fichiers : même défaut, deux endroits —
  ctx.attached = "42";
  ctx.filesData = { ctxKey: "s:42", worktrees: [], projects: [
    { root: "/w/appli", name: "appli", client: "acme", project: "appli", docs: [] }] };
  ctx.fileNav = { wt: "/w/appli", path: "src/lib", entries: [{ name: "a.js", dir: false, size: 10 }],
                  commits: null, file: null, showCommits: false };
  ctx.renderFiles();
  console.log("✓ onglet fichiers : fil d'ariane rendu (session)");

  // — fiche projet : docs (`doval` n'a jamais existé) + fil d'ariane projet —
  ctx.currentProjectView = "acme/appli";
  ctx.projWts = { key: "acme/appli", worktrees: [{ path: "/w/appli", name: "appli", exists: true, kind: "code" }] };
  ctx.projFiles = { wt: "/w/appli", path: "docs", entries: [{ name: "x.md", dir: false, size: 3 }], file: null };
  ctx.renderProjFiles();
  ctx.renderProjectPane("acme/appli", {
    name: "Appli", total: 3, docs: [{ path: "/pm/x.md", name: "x.md" }],
    open_by_status: { en_cours: 1 }, open_recent: [], closed_recent: [], environments: [],
  });
  console.log("✓ fiche projet : docs et fil d'ariane rendus");

  assert.deepStrictEqual(errors, [], "aucune erreur signalée pendant les rendus");
  console.log("OK — le cockpit s'exécute sans identifiant hors portée");
})().catch(e => {
  console.error("ÉCHEC :", e && e.stack ? e.stack : e);
  process.exit(1);
});
