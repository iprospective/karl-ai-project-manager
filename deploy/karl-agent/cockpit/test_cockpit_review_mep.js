// Tests RM3225 — la mise en production d'un ticket sur SA fiche.
//
// Avant : ni les actions au déploiement (CF 8) ni le script de MEP n'apparaissaient au cockpit. La
// procédure se lisait dans Redmine ou sur disque — jamais là où l'on décide de mettre en prod.
// Lancer : node test_cockpit_review_mep.js
import assert from "node:assert";
import fs from "node:fs";
import { ReviewViewModel } from "./src/modules/review/ReviewViewModel.js";
import { MepPane, ReviewPane } from "./src/modules/review/Review.view.js";

const SCRIPT = {
  file: "RM3219_x.script-mep.sh", text: "#!/usr/bin/env bash\nset -euo pipefail\nrm -rf \"$MOD\" # <danger>\n",
  truncated: false, lines: 3, alias: "pisceen-presta", lint: [],
  launch: { check: "ssh pisceen-presta 'bash -s' < .mmi-pm/tasks/RM3219_x.script-mep.sh",
            apply: "ssh pisceen-presta 'bash -s -- --apply' < .mmi-pm/tasks/RM3219_x.script-mep.sh" },
};
const mk = (r) => new ReviewViewModel({ r: Object.assign({ found: true, title: "T" }, r) }, {});

// ── ce que le ViewModel décide ──────────────────────────────────────────────
assert.strictEqual(mk({}).mep, null, "ni actions ni script : pas de bloc");
assert.strictEqual(mk({ deploy_actions: ["", "  "] }).mep, null, "des actions vides ne font pas un bloc");
const vm = mk({ status: "a_mep", deploy_actions: ["Contrôle", "Exécution"], mep_script: SCRIPT });
assert.deepStrictEqual(vm.mep.actions, ["Contrôle", "Exécution"], "l'ordre des actions EST l'ordre d'exécution");
assert.strictEqual(vm.mep.focus, true, "à mettre en prod : la procédure est mise en avant");
assert.strictEqual(mk({ status: "en_cours", mep_script: SCRIPT }).mep.focus, false);
assert.strictEqual(vm.mep.script.aliasKnown, true);
assert.strictEqual(mk({ mep_script: SCRIPT }).mep.actions.length, 0, "un script seul suffit à faire le bloc");
assert.ok(vm.sections().some(s => s.id === "mep"), "la rubrique figure dans les sections de la fiche");

// ── le rendu ────────────────────────────────────────────────────────────────
const h = String(MepPane(vm.mep));
assert.ok(/🚀 Mise en production/.test(h) && /<ol[^>]*>.*Contrôle.*Exécution/s.test(h), "actions listées dans l'ordre");
assert.ok(/📜 Script de MEP/.test(h) && /RM3219_x\.script-mep\.sh · 3 lignes/.test(h), "le script est nommé");
assert.ok(/<details open>/.test(h), "déplié d'office en a_mep");
assert.ok(!/<details open>/.test(String(MepPane(mk({ status: "en_cours", mep_script: SCRIPT }).mep))), "replié hors MEP");
assert.ok(/bash -s -- --apply/.test(h) && /data-action="copy"/.test(h), "les deux commandes, copiables");
assert.ok(/&lt;danger&gt;/.test(h) && !/<danger>/.test(h), "le texte du script est échappé (il contient < et >)");
assert.ok(!/alias ssh inconnu/.test(h), "alias connu : pas d'avertissement");
const sansAlias = String(MepPane(mk({ mep_script: Object.assign({}, SCRIPT, { alias: null }) }).mep));
assert.ok(/alias ssh inconnu/.test(sansAlias), "alias inconnu : on le dit, la commande n'est pas prête");
const lint = String(MepPane(mk({ mep_script: Object.assign({}, SCRIPT, { lint: ["procédure de rollback"] }) }).mep));
assert.ok(/contrat du script : manque procédure de rollback/.test(lint), "un manque au contrat se voit");
assert.ok(!/\son\w+=/.test(h), "aucun gestionnaire inline");
assert.strictEqual(String(MepPane(null)), "", "rien à rendre sans procédure");
const vmFiche = new ReviewViewModel({ r: { found: true, title: "T", status: "a_mep", deploy_actions: ["Contrôle"], mep_script: SCRIPT },
  cfg: { statuses: ["a_mep"], actions: [] }, tqLoaded: true, tqSize: 1 }, { rm: "3219", prompt: { tpl: "", text: "" }, now: Date.parse("2026-09-19T10:00") });
const pane = String(ReviewPane(vmFiche, { md: (s) => s, titleLink: (rm, t) => t, mcBanner: () => "" }));
assert.ok(/🚀 Mise en production/.test(pane), "la fiche intègre le bloc");

// ── la copie et le câblage ─────────────────────────────────────────────────
const ctl = fs.readFileSync(new URL("./src/modules/review/review.controller.js", import.meta.url), "utf8");
assert.ok(/copy: \(n\) => copyText\(n\)/.test(ctl) && /ctx\.copyFallback/.test(ctl), "geste copier, avec repli");
const boot = fs.readFileSync(new URL("./src/boot.js", import.meta.url), "utf8");
assert.ok(/const copyFallback = /.test(boot) && (boot.match(/copyFallback,/g) || []).length >= 2,
  "une seule fonction de copie, prêtée au terminal ET à la fiche");
const srv = fs.readFileSync(new URL("../../../scripts/karl-agent.py", import.meta.url), "utf8");
assert.ok(/"mep_script": _ticket_mep_script\(tf, envs\)/.test(srv), "le serveur sert le script avec la fiche");
console.log("test_cockpit_review_mep : ok");
