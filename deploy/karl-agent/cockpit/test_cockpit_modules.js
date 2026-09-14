#!/usr/bin/env node
// Tests du panneau Modules (RM3145, lot 3) : il LIT, il n'active rien ; il dit ce qui casserait en
// désactivant un module — la question qu'on se pose au moment de cliquer — et il montre ce que
// l'instance porte ENCORE sans module, parce qu'un panneau qui tairait l'écart serait flatteur et faux.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));
function fakeEl(id) { const L = []; let inner = ""; const kids = {};
  const self = { id, style: {}, dataset: {}, value: "", kids,
    get innerHTML() { return inner; }, set innerHTML(v) { inner = v; },
    querySelector(s) { return kids[s] || null; }, querySelectorAll() { return []; }, contains: () => true,
    replaceChildren(...n) { inner = n.map(x => x.outerHTML || x.textContent || "").join(""); },
    addEventListener(t, f) { L.push([t, f]); }, removeEventListener() {},
    async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n };
      for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} });
      await settle(); } };
  return self; }

(async () => {
  const VM = await import(path.join(DIR, "src/modules/modules/ModulesViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/modules/Modules.view.js"));
  const { mountModules } = await import(path.join(DIR, "src/modules/modules/modules.controller.js"));

  const data = {
    core_version: "3.0.0", root: "/pm/modules", order: ["forge-gogs", "task-gogs-issues"], cycles: [],
    modules: [
      { name: "forge-gogs", version: "1.0.0", label: "Dépôts · Gogs", description: "transport Gogs",
        state: "actif", provides: [["provider", "forge/gogs"]], requires: ["core >= 3.0"],
        required_by: ["task-gogs-issues"], errors: [], blocked: [], triggers: [] },
      { name: "task-gogs-issues", version: "1.0.0", label: "Tickets · Gogs", description: "les issues",
        state: "actif", provides: [["provider", "task/gogs_issues"]], requires: ["forge-gogs >= 1.0"],
        required_by: [], errors: [], blocked: [], triggers: [
          { module: "task-gogs-issues", on: "task.created", when: { to: "x" }, run: ["echo", "a"], ok: true, errors: [] },
          { module: "task-gogs-issues", on: "", when: {}, run: [], ok: false, errors: ["« event » manquant"] }] },
      { name: "casse", version: "0.0.0", label: "casse", description: "", state: "erreur",
        provides: [], requires: [], required_by: [], errors: ["description manquante"], blocked: [], triggers: [] },
      { name: "en-attente", version: "1.0.0", label: "en attente", description: "x", state: "bloqué",
        provides: [], requires: ["fantome >= 1.0"], required_by: [], errors: [],
        blocked: ["dépendance absente : fantome"], triggers: [] },
    ],
    inventory: { total: 5, decrits: 2, non_decrits: 3, registres: {
      provider: [{ item: "forge/gogs", decrit: true }, { item: "task/gogs_issues", decrit: true },
                 { item: "llm/ollama", decrit: false }],
      job: [{ item: "wiki-sync", decrit: false }, { item: "lock-gc", decrit: false }] } },
    bus: { pending: 2, errors: 1, by_name: { "task.created": 2 },
           last_errors: [{ name: "task.created", ts: "2026-09-14T04:00:00+02:00", error: "abonné : code 3" }] },
  };

  // ── le ViewModel décide ─────────────────────────────────────────────────────
  const vm = new VM.ModulesViewModel({ data });
  const rows = vm.rows();
  assert.strictEqual(rows.length, 4);
  assert.deepStrictEqual(vm.counts, { total: 4, actifs: 2, casses: 2 });
  assert.deepStrictEqual(rows[0].requiredBy, ["task-gogs-issues"], "ce qui casserait en désactivant");
  assert.deepStrictEqual(rows[0].provides, ["provider forge/gogs"], "ce qu'il fournit, lisible");
  assert.deepStrictEqual(rows[2].motifs, ["description manquante"], "un manifeste cassé dit pourquoi");
  assert.deepStrictEqual(rows[3].motifs, ["dépendance absente : fantome"], "un module bloqué aussi");
  assert.strictEqual(rows[1].triggers.length, 2);
  assert.strictEqual(rows[1].triggers[1].ok, false, "un abonnement invalide se voit");
  const inv = vm.inventaire;
  assert.strictEqual(inv.pct, 40, "l'écart est chiffré");
  assert.deepStrictEqual(inv.lignes.map(l => l.registre), ["job", "provider"], "les registres sont triés");
  assert.deepStrictEqual(inv.lignes[1].manquants, ["llm/ollama"], "et ce qui n'est PAS décrit est nommé");

  // ── la vue montre ce qu'il faut, et rien en on* ─────────────────────────────
  const card = String(V.ModulesCard(vm));
  assert(/🧩 Modules/.test(card) && /4 décrit\(s\)/.test(card) && /2 à voir/.test(card));
  assert(/Noyau 3\.0\.0/.test(card) && /\/pm\/modules/.test(card), "d'où viennent les modules, et pour quel noyau");
  assert(/ce panneau LIT/.test(card), "le panneau dit qu'il ne charge rien — c'est le lot 3, pas le lot 1");
  assert(/description manquante/.test(card) && /dépendance absente/.test(card), "les motifs sont rendus");
  assert(/llm\/ollama/.test(card), "l'écart est visible, pas seulement compté");
  assert(/abonné : code 3/.test(card), "un abonné en échec se voit — sinon le module semble branché");
  assert(!/\son(click|change|input)=/.test(card), "aucun handler inline");
  const ouvert = String(V.ModulesCard(new VM.ModulesViewModel({ data, open: "forge-gogs" })));
  assert(/requis par/.test(ouvert) && /task-gogs-issues/.test(ouvert), "le détail ouvert dit qui dépend de lui");
  assert(/registre illisible : boum/.test(String(V.ModulesCard(new VM.ModulesViewModel({ error: "boum" })))));
  const cyc = String(V.ModulesCard(new VM.ModulesViewModel({ data: Object.assign({}, data, { cycles: [["a", "b", "a"]] }) })));
  assert(/circulaire : a → b → a/.test(cyc), "un cycle est nommé dans la page");

  // ── le contrôleur : il ouvre, il referme, il n'active rien ──────────────────
  const calls = [];
  const svc = { data, error: null, async load() { calls.push("load"); return data; } };
  const el = fakeEl("modulescard");
  const ctr = mountModules(el, { service: svc });
  await ctr.open();
  assert.deepStrictEqual(calls, ["load"]);
  assert(/forge-gogs/.test(el.innerHTML));
  await el.click("open", { name: "forge-gogs" });
  assert.strictEqual(ctr.state.open, "forge-gogs", "un clic ouvre le détail");
  await el.click("open", { name: "forge-gogs" });
  assert.strictEqual(ctr.state.open, "", "un second clic referme — on compare deux modules tour à tour");
  assert.deepStrictEqual(calls, ["load"], "ouvrir un détail ne redemande rien au serveur");

  const src = fs.readFileSync(path.join(DIR, "src/modules/modules/modules.controller.js"), "utf8");
  assert(!/enable|disable|activer/i.test(src), "RM3145 lot 3 : ce panneau LIT — l'activation est le lot 1");

  // ── câblage : un onglet des réglages, pas un bouton de plus dans l'en-tête ──
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  const nav = fs.readFileSync(path.join(DIR, "src/modules/setnav/SetnavViewModel.js"), "utf8");
  assert(/id="modulescard"/.test(html), "le panneau a son hôte");
  assert(/key: "modules", label: "🧩 Modules"/.test(nav), "c'est un onglet des réglages");
  assert(/modules: \(\) => modulesPane\.open\(\)/.test(boot), "chargé seulement quand on l'ouvre");
  assert(!/id="modulesbtn"/.test(html), "RM3150 : pas un bouton de plus dans l'en-tête qu'on vient d'alléger");

  console.log("✓ panneau Modules (RM3145 lot 3) : état, dépendances dans les deux sens, écart, bus, lecture seule");
})().catch(e => { console.error(e); process.exit(1); });
