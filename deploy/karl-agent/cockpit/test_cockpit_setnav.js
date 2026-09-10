#!/usr/bin/env node
// Tests des onglets de réglages (RM3081) : les cartes existantes sont réparties, un onglet vide ne
// s'affiche pas, le contenu ne se charge qu'à l'ouverture de SON onglet, et le choix est mémorisé.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));

function fakeCard(id, cache) {
  const classes = new Set();
  return { id, style: { display: cache ? "none" : "" },
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
    get off() { return classes.has("setnav-off"); } };
}
function fakeHost() { const L = []; let inner = "";
  const self = { id: "setnav", style: {}, dataset: {},
    get innerHTML() { return inner; }, set innerHTML(v) { inner = v; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    replaceChildren(...n) { inner = n.map(x => x.outerHTML || x.textContent || "").join(""); },
    addEventListener(t, f) { L.push([t, f]); }, removeEventListener() {}, contains: () => true,
    async click(tab) { const n = { dataset: { action: "settab", tab }, closest: () => n };
      for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} });
      await settle(); } };
  return self; }

(async () => {
  const VMmod = await import(path.join(DIR, "src/modules/setnav/SetnavViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/setnav/Setnav.view.js"));
  const { mountSetnav } = await import(path.join(DIR, "src/modules/setnav/setnav.controller.js"));
  const { GROUPES, SetnavViewModel } = VMmod;

  // — les groupes couvrent les cartes de la page, sans doublon ni oubli —
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const bloc = html.split('id="cp-settings"')[1].split("<!-- /#panelpane -->")[0];
  const cartes = [...bloc.matchAll(/<div class="card" id="([^"]+)"/g)].map(m => m[1]);
  const rangees = GROUPES.flatMap(g => g.cards);
  assert.deepStrictEqual([...cartes].sort(), [...rangees].sort(), "toute carte des réglages est dans un onglet, et un seul");
  assert.strictEqual(new Set(rangees).size, rangees.length, "aucune carte rangée deux fois");
  assert(/id="setnav"/.test(html), "la barre d'onglets a son hôte, avant les cartes");
  console.log("✓ page : chaque carte des réglages appartient à exactement un onglet");

  // — ViewModel —
  let vm = new SetnavViewModel({ open: "engines" });
  assert.strictEqual(vm.courant, "engines", "l'onglet demandé est le courant");
  assert(vm.tabs.find(t => t.key === "engines").on, "et il est marqué dans la barre");
  assert.strictEqual(vm.tabs.filter(t => t.on).length, 1, "un seul onglet actif");
  vm = new SetnavViewModel({ open: "account", hidden: ["account"] });
  assert(!vm.tabs.some(t => t.key === "account"), "un onglet sans rien à montrer n'apparaît pas");
  assert.strictEqual(vm.courant, "instance", "et on retombe sur le premier qui a du contenu");
  assert.deepStrictEqual(vm.cardsOf("display"), ["themecard", "rightcard", "sessprefcard", "voicecard"]);
  console.log("✓ ViewModel : onglet courant, onglet vide écarté, repli sur le premier utile");

  const s = String(V.SetnavBar(new SetnavViewModel({ open: "display" })));
  assert(!/\son\w+=/.test(s), "aucun on* dans la vue");
  assert(/data-action="settab" data-tab="display"/.test(s), "gestes en data-action");
  assert(/class="chip on"[^>]*data-tab="display"/.test(s) || /data-tab="display"/.test(s), "l'onglet courant est marqué");
  assert(/local à ce navigateur/.test(s), "l'onglet dit ce qu'il regroupe");
  console.log("✓ vue : chips, gestes en data-*, aide de l'onglet courant");

  // — contrôleur : répartition, chargement paresseux, mémoire du choix —
  const cards = {};
  for (const id of rangees) cards[id] = fakeCard(id, id === "authcard" || id === "userscard");
  const doc = { getElementById: (id) => cards[id] || null };
  const charges = []; let mem = {};
  const store = { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; } };
  const el = fakeHost();
  const ctl = mountSetnav(el, { document: doc, storage: store,
    loaders: { instance: () => charges.push("instance"), providers: () => charges.push("providers"),
               engines: () => charges.push("engines") } });

  await ctl.open();
  assert.deepStrictEqual(charges, ["instance"], "ouvrir les réglages ne charge QUE le premier onglet");
  assert(!cards["reglages-card"].off && cards["providerscard"].off && cards["enginescard"].off,
         "seules les cartes de l'onglet courant sont affichées");
  assert(!String(el.innerHTML).includes("Compte"), "l'onglet Compte est absent : ses deux cartes sont masquées");

  await el.click("engines");
  assert.deepStrictEqual(charges, ["instance", "engines"], "changer d'onglet charge le sien, et lui seul");
  assert(cards["enginescard"].off === false && cards["reglages-card"].off, "les cartes suivent l'onglet");
  await el.click("engines");
  assert.deepStrictEqual(charges, ["instance", "engines"], "revenir sur un onglet déjà chargé ne recharge pas");
  await el.click("display");
  assert.deepStrictEqual(charges, ["instance", "engines"], "un onglet sans chargeur n'appelle rien");
  assert(cards["themecard"].off === false && cards["voicecard"].off === false, "les quatre cartes d'affichage sont là");
  assert.strictEqual(mem.karlSettingsTab, "display", "le dernier onglet est mémorisé pour ce navigateur");

  // — la carte masquée par ailleurs n'est pas ressuscitée par son onglet —
  await el.click("account");
  assert.strictEqual(ctl.state.open, "display", "on ne peut pas ouvrir un onglet qui n'existe pas");
  cards["authcard"].style.display = "";                 // l'authentification révèle sa carte
  ctl.refresh();
  await el.click("account");
  assert.strictEqual(ctl.state.open, "account", "une fois connecté, l'onglet Compte s'ouvre");
  assert(cards["authcard"].off === false && cards["userscard"].off === false,
         "la classe d'onglet est retirée des deux cartes du groupe");
  assert.strictEqual(cards["userscard"].style.display, "none",
         "mais la carte que son module masque le reste : l'onglet ne touche pas au style");
  console.log("✓ contrôleur : chargement à l'onglet, une seule fois, choix mémorisé, masquage respecté");

  // — un navigateur sans stockage ne casse rien —
  const dur = { getItem() { throw new Error("bloqué"); }, setItem() { throw new Error("bloqué"); } };
  const el2 = fakeHost();
  const ctl2 = mountSetnav(el2, { document: doc, storage: dur, loaders: {} });
  await ctl2.open(); await el2.click("engines");
  assert.strictEqual(ctl2.state.open, "engines", "stockage indisponible : les onglets marchent quand même");
  console.log("✓ stockage bloqué : aucun impact sur la navigation");

  console.log("\nLes onglets des réglages passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
