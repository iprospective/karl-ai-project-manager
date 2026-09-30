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
    routes: [{ module: "forge-gogs", method: "GET", url: "/api/modules/forge-gogs/etat",
               handler: "ctrl:etat", ok: true, errors: [] }],
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
  // RM3145 lot 4 : les routes qu'un module SERT — le préfixe dit qui répond, c'est ce qui rend un incident lisible
  assert.deepStrictEqual(rows[0].routes.map(r => r.url), ["/api/modules/forge-gogs/etat"]);
  assert.strictEqual(rows[1].triggers[1].ok, false, "un abonnement invalide se voit");
  const inv = vm.inventaire;
  assert.strictEqual(inv.pct, 40, "l'écart est chiffré");
  assert.deepStrictEqual(inv.lignes.map(l => l.registre), ["job", "provider"], "les registres sont triés");
  assert.deepStrictEqual(inv.lignes[1].manquants, ["llm/ollama"], "et ce qui n'est PAS décrit est nommé");

  // ── la vue montre ce qu'il faut, et rien en on* ─────────────────────────────
  const card = String(V.ModulesCard(vm));
  assert(/🧩 Modules/.test(card) && /4 décrit\(s\)/.test(card) && /2 à voir/.test(card));
  assert(/Noyau 3\.0\.0/.test(card) && /\/pm\/modules/.test(card), "d'où viennent les modules, et pour quel noyau");
  // RM3145 lot 1 : le panneau n'est plus en lecture seule — il dit ce qu'éteindre fait, et ne fait pas
  assert(/ne supprime rien/.test(card) && /est refusé/.test(card),
    "le panneau dit qu'éteindre ne supprime rien, et que casser une dépendance est refusé");
  assert(/description manquante/.test(card) && /dépendance absente/.test(card), "les motifs sont rendus");
  assert(/llm\/ollama/.test(card), "l'écart est visible, pas seulement compté");
  assert(/abonné : code 3/.test(card), "un abonné en échec se voit — sinon le module semble branché");
  const ouvertRoute = String(V.ModulesCard(new VM.ModulesViewModel({ data, open: "forge-gogs" })));
  assert(/\/api\/modules\/forge-gogs\/etat/.test(ouvertRoute), "les routes servies par le module sont lisibles");
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

  // ── RM3145 lot 1 : les GESTES — allumer, éteindre, forcer sous double sécurité ──────────────
  const d1 = JSON.parse(JSON.stringify(data));
  d1.modules[0].native = true; d1.modules[0].breaks = ["task-gogs-issues"];
  const vRefus = new VM.ModulesViewModel({ data: d1, open: "forge-gogs", refus: { "forge-gogs": "refusé : task-gogs-issues dépend de forge-gogs" } });
  const g = vRefus.rows()[0];
  assert(g.canDisable && !g.canEnable, "un module actif s'éteint, il ne s'allume pas");
  assert(g.native, "natif : il s'éteint, il ne se retire pas (Q001)");
  assert.deepStrictEqual(g.breaks, ["task-gogs-issues"], "ce qu'on casserait MAINTENANT est connu avant de cliquer");
  assert(g.refus && !g.canForce, "Q003 : forçage NON offert tant que l'instance ne le permet pas");
  const vPermis = new VM.ModulesViewModel({ data: Object.assign({}, d1, { allow_force: true }), open: "forge-gogs",
                                            refus: { "forge-gogs": "refusé" } });
  assert(vPermis.rows()[0].canForce, "réglage posé + refus : le forçage devient possible");
  const vConf = new VM.ModulesViewModel({ data: Object.assign({}, d1, { allow_force: true }), open: "forge-gogs",
                                          refus: { "forge-gogs": "refusé" }, confirming: "forge-gogs", confirmText: "forge-go" });
  assert(vConf.rows()[0].confirming && !vConf.rows()[0].confirmOk, "confirmation forte : un nom incomplet ne suffit pas");
  const vConfOk = new VM.ModulesViewModel({ data: Object.assign({}, d1, { allow_force: true }), open: "forge-gogs",
                                            refus: { "forge-gogs": "refusé" }, confirming: "forge-gogs", confirmText: "forge-gogs" });
  assert(vConfOk.rows()[0].confirmOk, "… le nom exact, oui");
  const cardConf = String(V.ModulesCard(vConfOk));
  assert(/Recopiez le nom du module/.test(cardConf) && /task-gogs-issues/.test(cardConf) && /reste en place/.test(cardConf),
    "la boîte dit ce qui cessera de fonctionner, et que rien n'est perdu");
  assert(!/forcer l'extinction<\/button>[^]*disabled/.test(cardConf.split("forcer l'extinction")[0] + "x"),
    "rendu cohérent");
  const off = JSON.parse(JSON.stringify(data)); off.modules[0].state = "éteint (forcé)"; off.modules[0].forced = true;
  const gOff = new VM.ModulesViewModel({ data: off }).rows()[0];
  assert(gOff.canEnable && !gOff.canDisable && gOff.forced, "un module éteint en forçant se rallume, et le dit");
  assert.strictEqual(gOff.icone, "⊘", "« éteint (forcé) » a sa propre marque — ce n'est pas un simple désactivé");

  // le contrôleur : refus → motif affiché ; forçage → confirmation ; nom exact → envoi
  const envois = []; let refuser = true;
  const svc2 = { data: Object.assign({}, d1, { allow_force: true }), error: null,
    async load() { return this.data; },
    async setState(b) { envois.push(b); if (refuser && !b.force && !b.enabled) throw new Error("refusé : task-gogs-issues dépend de forge-gogs"); return { etat: "eteint", casses: b.force ? ["task-gogs-issues"] : [] }; },
    async setPolicy() { return { allow_force: true }; } };
  const el2 = fakeEl("modulescard"); const notes = [];
  const c2 = mountModules(el2, { service: svc2, notify: (m) => notes.push(m) });
  await c2.open(); await el2.click("open", { name: "forge-gogs" });
  await el2.click("disable", { name: "forge-gogs" });
  assert(/dépend de forge-gogs/.test(c2.state.refus["forge-gogs"] || ""), "le refus du serveur est AFFICHÉ, pas avalé");
  await el2.click("force", { name: "forge-gogs" });
  assert.strictEqual(c2.state.confirming, "forge-gogs", "forcer… ouvre la confirmation, n'envoie rien");
  assert.strictEqual(envois.filter(b => b.force).length, 0, "rien n'est parti avant la confirmation");
  c2.state.confirmText = "forge-go"; await el2.click("force-confirm", { name: "forge-gogs" });
  assert.strictEqual(envois.filter(b => b.force).length, 0, "un nom incomplet n'envoie rien — la garde tient aussi côté client");
  c2.state.confirmText = "forge-gogs"; await el2.click("force-confirm", { name: "forge-gogs" });
  const forcé = envois.find(b => b.force);
  assert(forcé && forcé.confirm === "forge-gogs", "le nom exact part avec la demande de forçage");
  assert(notes.some(n => /FORÇANT/.test(n) && /task-gogs-issues/.test(n)), "et le retour dit ce qui a cessé de fonctionner");
  assert.strictEqual(c2.state.confirming, "", "la confirmation se referme après l'envoi");

  const src = fs.readFileSync(path.join(DIR, "src/modules/modules/modules.controller.js"), "utf8");
  // RM3145 lot 1 : le panneau ACTIVE désormais. Ce qui doit rester vrai : il n'importe aucun code de
  // module, et le forçage ne part jamais sans que le nom ait été recopié.
  assert(/enable/.test(src) && /disable/.test(src), "lot 1 : allumer et éteindre sont des gestes du panneau");
  assert(/confirmText !== name/.test(src), "la confirmation forte est vérifiée côté client aussi");
  assert(!/import\(.*modules\/[a-z-]+\//.test(src), "le panneau ne charge toujours aucun code de module");

  // ── câblage : un onglet des réglages, pas un bouton de plus dans l'en-tête ──
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  const nav = fs.readFileSync(path.join(DIR, "src/modules/setnav/SetnavViewModel.js"), "utf8");
  assert(/id="modulescard"/.test(html), "le panneau a son hôte");
  assert(/key: "modules", label: "🧩 Modules"/.test(nav), "c'est un onglet des réglages");
  assert(/modules: \(\) => modulesPane\.open\(\)/.test(boot), "chargé seulement quand on l'ouvre");
  assert(!/id="modulesbtn"/.test(html), "RM3150 : pas un bouton de plus dans l'en-tête qu'on vient d'alléger");

  console.log("✓ panneau Modules (RM3145 lots 3+1) : état, dépendances, écart, bus, gestes, refus motivé, forçage sous double sécurité");
})().catch(e => { console.error(e); process.exit(1); });
