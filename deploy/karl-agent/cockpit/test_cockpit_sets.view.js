#!/usr/bin/env node
// Tests du domaine sets — VIEWMODELS et VUES (RM3017, scindé de test_cockpit_sets.js) : formulaire RM2741, carte (entrées RM2427/2673,
// dérivé RM2452, jeu réglé RM2955, réglages), versions RM2443, sélecteurs — aucun on*.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { fakeEl, facets, SETS3, now, R, mkRepo } = require("./test_cockpit_sets.helpers.js");
(async () => {
  const M = await import(path.join(DIR, "src/modules/sets/sets.js"));
  const VM = await import(path.join(DIR, "src/modules/sets/SetsViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/sets/Sets.view.js"));

  // — ViewModels et vues —
  const fNew = String(V.RuleForm(new VM.RuleFormViewModel({ rule: {}, isNew: true, shownCount: 5, facets })));
  assert(/id="rf-name"/.test(fNew) && /id="rf-seed"[^>]*checked/.test(fNew) && /5 session\(s\) affichée\(s\)/.test(fNew) && /manuel/.test(fNew) && /dérivé/.test(fNew) && /<option value="acme"[^>]*>acme \(3\)</.test(fNew) && /<option value="api"[^>]*>api</.test(fNew) && /<option value="urgent"/.test(fNew) && /<option value="wip"/.test(fNew) && /data-action="rule-apply" data-new="1">Créer</.test(fNew) && /data-action="rule-cancel"/.test(fNew) && !/onclick/.test(fNew), "RM2741 : formulaire unifié, facettes, gestes en data-action");
  assert(!/id="rf-seed"/.test(String(V.RuleForm(new VM.RuleFormViewModel({ rule: {}, isNew: true, shownCount: 0, facets })))), "sans session affichée, pas de case sans objet");
  const fEdit = String(V.RuleForm(new VM.RuleFormViewModel({ rule: { client: "acme", tickets: ["1", "2"] }, isNew: false, facets }))); assert(!/id="rf-name"/.test(fEdit) && !/id="rf-seed"/.test(fEdit) && /<option value="acme" selected>/.test(fEdit) && /value="1,2"/.test(fEdit) && /data-new="">Appliquer</.test(fEdit), "édition : ni nom ni peuplement, valeurs reprises");
  let vm = new VM.SetCardViewModel({ r: R, edited: "default", current: "default", sets: SETS3, ruleFormFor: null, facets, shownCount: 3, spawnPref: true });
  assert(vm.isCurrent && !vm.empty && vm.rows.length === 2 && vm.rows[0].editable && vm.rows[0].state === "🟢 active" && vm.rows[0].restartLabel === "⟳ auto" && /Redémarre toute seule/.test(vm.rows[0].restartTip) && vm.rows[1].state === "🔴 perdue" && vm.rows[1].inactive === "inactive depuis 1j" && vm.relaunchCount === 1 && vm.savedAgo === "1h" && vm.derivedHeader === null && !vm.newForm && !vm.editForm);
  let c = String(V.SetCard(vm));
  assert(/<b>Défaut<\/b> · 2 <span style="color:var\(--accent\)"[^>]*>● courant<\/span> session\(s\) · enregistré il y a 1h/.test(c) && /data-action="rename">✎</.test(c) && /<li><b>RM12<\/b> <span style="color:var\(--muted\)">claude<\/span> 🟢 active<span class="tkill"[^>]*data-action="entry-forget" data-sid="12">⊖<\/span><span[^>]*data-action="entry-restart" data-sid="12" data-restart="auto">⟳ auto<\/span><br><span style="font-size:11px">Sujet 12<\/span><br><span[^>]*>\/w\/12<\/span><\/li>/.test(c), "entrée éditable : ⊖ et ⟳ en data-action");
  assert(/<b>slug<\/b>[^]*🔴 perdue[^]*sans titre[^]*inactive depuis 1j · </.test(c) && /seulement s'il est le jeu courant\.<\/div>/.test(c) && /value="7" data-action="retention"/.test(c) && /checked data-action="spawn-pref"/.test(c) && /data-action="relaunch-card"[^>]*>▶ relancer \(1\)</.test(c) && /data-action="history">↩ versions</.test(c) && /data-action="delete">🗑 Effacer</.test(c) && /<div id="set-history"><\/div>/.test(c) && !/onclick|onchange/.test(c), "réglages et boutons sans on*");
  vm = new VM.SetCardViewModel({ r: Object.assign({}, R, { derived: true, rule: { client: "acme" }, truncated: true, total: 40 }), edited: "pm", current: "default", sets: SETS3, ruleFormFor: null, facets }); c = String(V.SetCard(vm));
  assert(/⚙ <b>jeu dérivé<\/b> — client=acme <span[^>]*data-action="rule-edit">modifier<\/span> · <span[^>]*data-action="materialize">figer<\/span>/.test(c) && !/entry-forget|entry-restart/.test(c) && !/● courant/.test(c) && / affichée\(s\) sur <b>40<\/b>/.test(c) && /\(ce n'est pas le cas ici\)/.test(c), "RM2673 : jeu dérivé — ni ⊖ ni ⟳ sur les entrées, modifier/figer offerts ; RM2452 : troncature dite ; RM2955 : pas courant");
  vm = new VM.SetCardViewModel({ r: Object.assign({}, R, { derived: true, rule: { client: "acme" } }), edited: "pm", current: "default", sets: SETS3, ruleFormFor: "pm", facets }); c = String(V.SetCard(vm)); assert(vm.editForm && /Règle du jeu/.test(c) && /<option value="acme" selected>/.test(c) && !/jeu dérivé<\/b> —/.test(c), "la règle s'édite dans le formulaire");
  vm = new VM.SetCardViewModel({ r: { exists: false }, edited: "pm", current: "default", sets: SETS3, ruleFormFor: "__new__", facets, shownCount: 2 }); c = String(V.SetCard(vm)); assert(vm.empty && /Nouveau jeu/.test(c) && /2 session\(s\) affichée\(s\)/.test(c) && /Jeu « PM » vide — c'est le jeu COURANT qui reçoit « 💾 »/.test(c), "vide + formulaire de création ; RM2955 : l'invite dit qui reçoit 💾");
  c = String(V.SetCard(new VM.SetCardViewModel({ r: { exists: true, count: 0 }, edited: "default", current: "default", sets: SETS3 }))); assert(/bouton « 💾 → Défaut » dans « ▶ en cours »/.test(c));
  c = String(V.History(new VM.HistoryViewModel({ versions: [{ id: "v1", at: now - 120, count: 3 }], keep: 20, label: "Défaut" }))); assert(/Rétablir « Défaut »/.test(c) && /data-action="restore" data-id="v1">↩ il y a 2min <span[^>]*>— 3 session\(s\)/.test(c)); assert(/Aucune version archivée pour « Défaut » \(max 20 conservées\)/.test(String(V.History(new VM.HistoryViewModel({ versions: [], keep: 20, label: "Défaut" })))));
  c = String(V.PickerOptions(M.pickerGroups({ live_count: 1 }, SETS3, "pm", "set"))); assert(/<optgroup label="vues"><option value="view:live">▶ sessions ouvertes \(1\)<\/option>/.test(c) && /<optgroup label="jeux"><option value="set:default">Défaut \(0\/undefined\)<\/option><option value="set:pm" selected>PM/.test(c)); assert.strictEqual(String(V.TargetOptions([{ value: "b", label: "vers B (2)" }])), '<option value="b">vers B (2)</option>');
  console.log("✓ ViewModels et vues : formulaire RM2741, carte (entrées RM2427/2673, dérivé RM2452, jeu réglé RM2955, réglages), versions RM2443, sélecteurs");

  console.log("\nTous les tests des vues des jeux passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
