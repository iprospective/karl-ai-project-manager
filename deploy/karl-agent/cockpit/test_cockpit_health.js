#!/usr/bin/env node
// Tests du domaine health — santé du SYSTÈME PM (RM3369).
//
// Ce qui est vérifié ici, avant tout : le badge NE MONTE PAS pour un
// avertissement, et il monte pour ce qui perd de la donnée. Un compteur qui
// affiche un chiffre tous les jours ne se regarde plus — le jour où il compte
// quelque chose de grave, personne ne le voit.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;

function fakeElement() {
  const L = []; let inner = "";
  return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true,
    querySelector() { return null; },
    addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
    get listenerCount() { return L.length; },
    async click(action, extra) { const n = { dataset: { action, ...(extra || {}) }, previousElementSibling: extra && extra.code ? { textContent: extra.code } : null };
      for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => s === "[data-action]" ? n : null } }); return n; } };
}

(async () => {
  const M = await import(path.join(DIR, "src/modules/health/pmHealth.js"));
  const C = await import(path.join(DIR, "src/core/checks.js"));
  const { HealthBadgeViewModel, HealthStatusViewModel } = await import(path.join(DIR, "src/modules/health/HealthViewModels.js"));
  const { HealthBadge, HealthStatus } = await import(path.join(DIR, "src/modules/health/Health.view.js"));
  const { mountHealth } = await import(path.join(DIR, "src/modules/health/health.controller.js"));
  const badge = (d) => String(HealthBadge(new HealthBadgeViewModel(d || {})));
  const page = (rep, active) => String(HealthStatus(new HealthStatusViewModel(rep, { active })));

  // — modèle : ce que compte le badge —
  const SAIN = { items: [], count: 0, major: 0, worst: "ok" };
  const AVERTI = { items: [{ family: "Normes", label: "index", level: "warn", detail: "périmé", fix: "assemble" }], count: 1, major: 0, worst: "warn" };
  const GRAVE = { items: [
    { family: "Champs Redmine", label: "calicote/dolibarr", level: "error", detail: "8 champ(s) non activés", fix: "cocher le projet" },
    { family: "Normes", label: "index", level: "warn", detail: "périmé", fix: "assemble" }], count: 2, major: 1, worst: "error" };

  assert.strictEqual(M.healthBadgeState(SAIN).show, false, "parc sain : aucun badge");
  assert.strictEqual(M.healthBadgeState(null).show, false, "donnée pas encore reçue : aucun badge");
  assert.strictEqual(M.healthBadgeState(AVERTI).show, false, "un avertissement seul ne fait PAS monter le badge");
  const g = M.healthBadgeState(GRAVE);
  assert(g.show && g.count === 1, "un souci majeur allume le badge, et il compte les majeurs seuls");
  assert(/Champs Redmine/.test(g.title) && /8 champ\(s\) non activés/.test(g.title), "le survol dit QUOI, sans cliquer");
  assert(/1 avertissement\(s\) dans le détail/.test(g.title), "le survol signale ce qui n'est pas compté mais reste à lire");
  assert.strictEqual(g.cls, "ew-error", "un souci majeur se voit en rouge");
  const gros = M.healthBadgeState({ major: 12, items: Array.from({ length: 12 }, (_, i) => ({ family: "F", label: "L" + i, level: "error" })) });
  assert(/… et 4 autre\(s\)/.test(gros.title), "un survol reste lisible : huit lignes puis un total");

  assert.strictEqual(M.healthHeadline(null), "aucun rapport de santé n'a encore été produit");
  assert.strictEqual(M.healthHeadline({ groups: [], summary: {} }), "aucun rapport de santé n'a encore été produit");
  assert.strictEqual(M.healthHeadline({ groups: [{}], summary: { counts: { error: 0, warn: 0 } } }), "rien à signaler");
  assert.strictEqual(M.healthHeadline({ groups: [{}], summary: { counts: { error: 2, warn: 3 } } }), "2 souci(s) majeur(s) · 3 avertissement(s)");
  assert.strictEqual(M.healthHeadline({ error: "module indisponible" }), "module indisponible", "une panne serveur se dit telle quelle");

  const NOW = 1_700_000_000_000;
  assert.strictEqual(M.healthAge(0, NOW), "", "sans date, on n'invente pas d'âge");
  assert.strictEqual(M.healthAge(NOW / 1000 - 30, NOW), "il y a 30 s");
  assert.strictEqual(M.healthAge(NOW / 1000 - 600, NOW), "il y a 10 min");
  assert.strictEqual(M.healthAge(NOW / 1000 - 7200, NOW), "il y a 2 h");
  assert.strictEqual(M.healthAge(NOW / 1000 - 3 * 86400, NOW), "il y a 3 j");
  console.log("✓ modèle : le badge ne compte que les soucis majeurs, le survol dit quoi, l'âge est lisible");

  // — socle partagé : la présentation des rapports est la même que pour le poste —
  const GROUPS = [
    { name: "Champs Redmine", checks: [{ label: "a", level: "ok" }] },
    { name: "Normes", checks: [{ label: "index", level: "error", detail: "périmé", fix: "pm-norms-assemble.py index" }] },
  ];
  const tabs = C.checkTabs(GROUPS);
  assert.deepStrictEqual(tabs.map(t => [t.name, t.error, t.warn, t.n]), [["Champs Redmine", 0, 0, 1], ["Normes", 1, 0, 1]]);
  assert.strictEqual(C.checkDefaultTab(tabs), "Normes", "la page s'ouvre sur ce qui ne va pas");
  assert.strictEqual(C.checkDefaultTab([]), "", "aucun onglet : pas de défaut");
  const secs = C.checkSections([{ label: "x", level: "ok", section: "b" }, { label: "y", level: "error", section: "c" }, { label: "z", level: "ok" }]);
  assert.deepStrictEqual(secs.map(s => s.name), ["", "c", "b"], "sans-section en tête, puis ce qui est en défaut");
  const E = await import(path.join(DIR, "src/modules/env/envStatus.js"));
  assert(E.envStatusTabs === C.checkTabs && E.envStatusSections === C.checkSections,
    "RM3369 : le poste et le PM partagent LA même présentation — pas deux tables qui divergeront");
  console.log("✓ socle : une seule présentation des rapports, ré-exportée par le poste");

  // — vue —
  assert.strictEqual(badge(SAIN), "", "rien à afficher quand tout va bien");
  assert(/🩺 1/.test(badge(GRAVE)) && /pill/.test(badge(GRAVE)), "le badge porte l'icône doctor et son compte");
  const REPORT = { generated_at: Date.now() / 1000 - 120, generated_label: "2026-09-30T16:00:00",
                   groups: GROUPS, summary: { counts: { ok: 1, warn: 0, error: 1 } } };
  const h = page(REPORT);
  assert(/Champs Redmine/.test(h) && /Normes/.test(h), "un onglet par famille");
  assert(/pm-norms-assemble\.py index/.test(h), "la commande de réparation est à l'écran");
  assert(/es-copy/.test(h), "et elle est copiable");
  assert(/il y a 2 min/.test(h), "la page dit l'âge du rapport — un rapport vieux ne doit pas passer pour frais");
  assert(!/<script/i.test(h), "aucun script injecté");
  const inject = page({ groups: [{ name: "F", checks: [{ label: "<img src=x onerror=alert(1)>", level: "error" }] }], summary: {} });
  assert(!/<img/.test(inject) && /&lt;img/.test(inject), "un rapport est une donnée : il est échappé");
  assert(/aucun rapport de santé PM/.test(String(HealthStatus(new HealthStatusViewModel(null, {})))), "sans rapport, la page dit quoi lancer");
  console.log("✓ vue : badge, onglets, commande copiable, âge, échappement");

  // — contrôleur —
  const el = fakeElement();
  const appels = { check: 0, status: 0, pull: [], clip: [], modal: [] };
  const svc = {
    check: null, status: null,
    setBlock(d) { this.check = d; return this; },
    async reloadCheck() { appels.check++; this.check = GRAVE; return this.check; },
    async loadStatus() { appels.status++; this.status = REPORT; return this.status; },
  };
  let peint = "";
  const ctl = mountHealth(el, { service: svc, badge: (x) => { peint = String(x); },
    pull: (b) => { appels.pull.push(b); }, modal: (t) => appels.modal.push(t),
    clip: async (t) => { appels.clip.push(t); return true; }, notify: () => {} });

  ctl.boot();
  assert.deepStrictEqual(appels.pull, ["pmhealth"], "au démarrage, le badge passe par la pile /refresh — pas un appel de plus");
  assert.strictEqual(appels.check, 0, "et ne redemande donc rien au serveur");

  ctl.setBlock(GRAVE);
  assert(/🩺 1/.test(peint), "le bloc poussé peint le badge sans qu'on ait cliqué");
  ctl.setBlock(SAIN);
  assert.strictEqual(peint, "", "et le badge disparaît quand il n'y a plus rien");

  await ctl.openStatus();
  assert.deepStrictEqual(appels.modal, ["🩺 Santé du système PM"], "le clic ouvre la modale partagée");
  assert.strictEqual(appels.status, 1, "la page lit le rapport");
  assert(/Normes/.test(el.innerHTML), "et l'affiche");

  await el.click("tab", { tab: "Champs Redmine" });
  assert.strictEqual(ctl.state.tab, "Champs Redmine", "changer d'onglet ne redemande rien");
  assert.strictEqual(appels.status, 1);

  await el.click("copy", { code: "pm-norms-assemble.py index" });
  assert.deepStrictEqual(appels.clip, ["pm-norms-assemble.py index"], "la commande se copie depuis le <code> voisin");

  const avant = el.listenerCount;
  ctl.unmount();
  assert(el.listenerCount < avant, "le domaine se démonte sans laisser d'écouteur");

  // une panne de lecture ne laisse pas la page en « lecture du rapport… »
  const el2 = fakeElement();
  const ctl2 = mountHealth(el2, { service: { check: null, status: null, setBlock() { return this; },
    async reloadCheck() { return null; }, async loadStatus() { throw new Error("502"); } },
    badge: () => {}, modal: () => {}, notify: () => {} });
  await ctl2.openStatus();
  assert(/santé PM illisible : 502/.test(el2.innerHTML), "une panne se dit, elle ne laisse pas un chargement sans fin");
  console.log("✓ contrôleur : démarrage par la pile, badge poussé, page, onglets, copie, démontage, panne");

  console.log("\nTous les tests du domaine health passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
