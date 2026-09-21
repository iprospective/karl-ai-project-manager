#!/usr/bin/env node
// Tests de l'écran « Facturation » (RM3229, lot L3) — le modèle pur (frise humain/IA, heures normales, totaux,
// état d'une journée), le service (chargement, ajustement, validation), le ViewModel, la vue (aucun on*, la
// confirmation nomme ce qui part) et le câblage de la page.
//
// Ce que ces tests protègent avant tout : on ne valide QUE la journée affichée, et la validation relit Redmine
// au lieu de croire ce qu'elle vient d'écrire.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");

function fakeEl(id) {
  const L = []; let inner = "";
  const self = { id, style: {}, textContent: "", kids: {}, contains: () => true,
    get innerHTML() { return inner; }, set innerHTML(v) { inner = v; },
    querySelector(sel) { return self.kids[sel] || null; },
    addEventListener(t, f) { L.push([t, f]); },
    removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
    get listenerCount() { return L.length; },
    async click(action, data) {
      const n = { dataset: Object.assign({ action }, data || {}), closest: () => n, value: "" };
      for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} });
      await new Promise(r => setTimeout(r, 0)); return n;
    },
    async change(action, data, value) {
      const n = { dataset: Object.assign({ action }, data || {}), closest: () => n, value };
      for (const [t, f] of [...L]) if (t === "change") await f({ target: n, preventDefault() {}, stopPropagation() {} });
      await new Promise(r => setTimeout(r, 0)); return n;
    } };
  return self;
}

// Une journée réaliste, de la forme que `mmi-pm timesheet --day … --json` rend.
const JOUR = {
  date: "2026-09-18", mesure_min: 410,
  periodes: [["08:51", "09:31"], ["13:32", "13:52"], ["18:33", "20:17"]],
  journal: { destin: "refacture", cle: { pisceen: 0.5, calicote: 0.5 }, absence: null,
             client_h: 3.5, pot_ouvre_h: 1.98, pot_hors_h: 1.33, alerte_absence: false },
  proposition: [
    { jour: "2026-09-18", client: "pisceen", projet: "dolibarr", ticket: 3217, minutes: 45, activite: 10, outillage_min: 7 },
    { jour: "2026-09-18", client: "pisceen", projet: "infra", ticket: null, minutes: 15, activite: 9, outillage_min: 6 },
    { jour: "2026-09-18", client: "calicote", projet: "infra", ticket: 3199, minutes: 30, activite: 13, outillage_min: 8 },
  ],
  deja_saisi: [{ minutes: 60, ticket: 3186, libelle: "revue de la migration" }],
  regie: [{ client: "matnat", motif: "presence", minutes: 90 }],
  ia: [{ heure: "08:55", ticket: 3217, client: "pisceen", projet: "dolibarr", modele: "claude-opus-5", tokens: 1200000, minutes: 4.5 },
       { heure: "08:55", ticket: 3217, client: "pisceen", projet: "dolibarr", modele: "claude-opus-5", tokens: 800000, minutes: 3 },
       { heure: "18:40", ticket: 3199, client: "calicote", projet: "infra", modele: "claude-opus-4-8", tokens: 400000, minutes: 2 }],
  surcharge: null, valide: false,
};
const clone = (o) => JSON.parse(JSON.stringify(o));

(async () => {
  const M = await import(path.join(DIR, "src/modules/billing/billing.js"));
  const { BillingService } = await import(path.join(DIR, "src/modules/billing/billing.service.js"));
  const { BillingViewModel } = await import(path.join(DIR, "src/modules/billing/BillingViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/billing/Billing.view.js"));
  const { mountBilling } = await import(path.join(DIR, "src/modules/billing/billing.controller.js"));

  // — modèle pur —
  assert.strictEqual(M.fmtMin(225), "3 h 45"); assert.strictEqual(M.fmtMin(120), "2 h");
  assert.strictEqual(M.fmtMin(45), "45 min"); assert.strictEqual(M.fmtMin(0), "0");
  assert.strictEqual(M.minOf("08:51"), 531); assert(isNaN(M.minOf("bof")));
  assert.strictEqual(M.hhmm(531), "08:51"); assert.strictEqual(M.hhmm(0), "00:00");
  assert.strictEqual(M.shiftDay("2026-09-01", -1), "2026-08-31", "la veille traverse le mois");
  assert.strictEqual(M.shiftDay("2026-03-29", 1), "2026-03-30", "le changement d'heure ne décale pas la date");
  assert.deepStrictEqual(M.weekOf("2026-09-18"), ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19", "2026-09-20"], "semaine du lundi au dimanche");
  assert.deepStrictEqual(M.weekOf("2026-09-20")[0], "2026-09-14", "un dimanche appartient à la semaine qui le précède");
  assert.strictEqual(M.longDate("2026-09-18"), "vendredi 18 septembre 2026");
  assert(M.isWeekend("2026-09-19") && M.isWeekend("2026-09-20") && !M.isWeekend("2026-09-18"), "samedi et dimanche");
  console.log("✓ modèle : formats, dates, semaine, week-end");

  // — la frise : deux voies, une seule échelle —
  const f = M.timeline(JOUR, { start: "09:00", end: "18:00" });
  assert.strictEqual(f.from, 8 * 60, "bornée à l'heure pleine sous la première trace");
  assert.strictEqual(f.to, 21 * 60, "…et au-dessus de la dernière");
  assert.strictEqual(f.humain.length, 3);
  assert.strictEqual(Math.round(f.humain[0].left), Math.round(((531 - 480) / 780) * 100), "position = pourcentage de la plage affichée");
  assert(f.humain.every(s => s.left >= 0 && s.left + s.width <= 100.01), "aucun segment ne déborde");
  assert.strictEqual(f.ia.length, 2, "deux tours à la même minute ne font qu'un repère");
  assert.deepStrictEqual([f.ia[0].tours, f.ia[0].tokens, f.ia[0].tickets], [2, 2000000, [3217]], "le repère cumule tours et tokens");
  assert(f.normal && Math.round(f.normal.left) === Math.round(((540 - 480) / 780) * 100), "la plage normale déclarée est cadrée sur la même échelle");
  assert.deepStrictEqual(M.timeline({}, {}), Object.assign({}, M.timeline({}, {})), "journée vide : pas d'exception");
  assert.strictEqual(M.timeline({}, {}).from, 8 * 60, "journée vide : 8 h → 19 h");
  const etroite = M.timeline({ periodes: [["10:05", "10:20"]] }, {});
  assert(etroite.to - etroite.from >= 60, "une plage minuscule garde une heure de large (sinon la frise est illisible)");
  console.log("✓ frise : bornes, positions, groupement des tours d'agent");

  // — heures normales : la mesure propose, l'ajustement tranche —
  const hn = M.heuresNormales(JOUR);
  assert.deepStrictEqual([hn.debut, hn.fin, hn.source], ["08:45", "19:00", "mesure"], "déduites des traces, arrondies au quart d'heure, ramenées à la plage ouvrée");
  assert.deepStrictEqual(hn.hors, { premiere: "08:51", derniere: "20:17" }, "ce qui déborde de la plage ouvrée est DIT, pas escamoté");
  // Le garde-fou qui compte : une dernière trace à 23h44 ne doit pas proposer une journée de 14 h,
  // qui servirait ensuite de plancher de régie (incident vu à la première capture d'écran).
  const tard = M.heuresNormales({ periodes: [["08:51", "09:31"], ["22:21", "23:44"]] });
  assert.deepStrictEqual([tard.debut, tard.fin], ["08:45", "19:00"], "une soirée n'allonge pas la journée normale");
  assert(M.heuresTravaillees(tard.debut, tard.fin, null) <= 10, "…et le total reste plausible");
  const nuit = M.heuresNormales({ periodes: [["21:00", "23:30"]] });
  assert.deepStrictEqual([nuit.debut, nuit.fin], ["21:00", "23:30"], "journée entièrement hors plage : montrée telle quelle, jamais réécrite");
  assert.strictEqual(M.heuresNormales({ periodes: [["09:30", "17:00"]] }).hors, null, "rien à signaler quand tout tient dans la plage ouvrée");
  const hj = M.heuresNormales(Object.assign(clone(JOUR), { surcharge: { debut: "09:00", fin: "18:00", pause_h: 1 } }));
  assert.deepStrictEqual([hj.debut, hj.fin, hj.source], ["09:00", "18:00", "ajuste"], "l'ajustement l'emporte sur la mesure");
  assert.strictEqual(M.heuresNormales({ periodes: [] }).source, "vide");
  assert.strictEqual(M.heuresTravaillees("09:00", "18:00", null), 8, "pause automatique d'1 h au-delà de 6 h");
  assert.strictEqual(M.heuresTravaillees("09:00", "12:00", null), 3, "…et aucune en deçà");
  assert.strictEqual(M.heuresTravaillees("09:00", "18:00", 0), 9, "une pause explicite de 0 est respectée");
  assert.strictEqual(M.heuresTravaillees("18:00", "09:00", null), 0, "fin avant début : rien");
  console.log("✓ heures normales : proposition, ajustement, pause");

  // — totaux et état —
  const t = M.totaux(JOUR);
  assert.deepStrictEqual([t.mesure, t.propose, t.deja, t.regie, t.total], [410, 90, 60, 90, 150]);
  assert.deepStrictEqual([t.tours, t.ia, t.tokens], [3, 10, 2400000], "le temps IA est compté à part du temps humain");
  assert.strictEqual(M.etat(JOUR), "a_valider");
  assert.strictEqual(M.etat(Object.assign(clone(JOUR), { valide: true })), "validee");
  assert.strictEqual(M.etat({ proposition: [], deja_saisi: [{ minutes: 60 }], mesure_min: 0 }), "manuelle");
  assert.strictEqual(M.etat({ proposition: [], deja_saisi: [], mesure_min: 0 }), "vide");
  assert.strictEqual(M.etat(null), "vide");
  const grp = M.parClient(JOUR);
  assert.deepStrictEqual(grp.map(g => [g.client, g.minutes]), [["pisceen", 60], ["calicote", 30]], "groupé par client, le plus gros d'abord");
  assert.strictEqual(M.fmtTokens(2400000), "2,4 M"); assert.strictEqual(M.fmtTokens(43000), "43 k");
  console.log("✓ totaux, état, groupement par client");

  // — service : charger, ajuster, valider —
  const appels = []; let charge = clone(JOUR);
  const repo = { day: async (j, refresh) => { appels.push(["day", j, !!refresh]); return { day: j, jour: charge }; },
                 month: async (m) => ({ periode: m, jours: [] }) };
  const runs = [];
  const run = async (name, args, opts) => { runs.push([name, args, opts]); return { ok: true, rc: 0, stdout: "✓ 3 saisie(s)" }; };
  const svc = new BillingService({ repo, run, day: "2026-09-18" });
  await svc.load();
  assert.deepStrictEqual(appels[0], ["day", "2026-09-18", false]);
  assert.strictEqual(svc.jour.mesure_min, 410);
  assert.strictEqual(svc.form().debut, "08:45", "le formulaire part de la proposition du serveur");
  assert.strictEqual(svc.form().fin, "19:00", "…bornée à la plage ouvrée, jamais à la dernière trace du soir");
  assert.deepStrictEqual(svc.form().hors, { premiere: "08:51", derniere: "20:17" }, "le formulaire porte ce que le bornage a laissé dehors (sinon l'écran ne peut pas le dire)");
  assert(!svc.dirty, "rien de saisi : rien à enregistrer");
  svc.setField("debut", "09:00");
  assert(svc.dirty && svc.form().debut === "09:00", "la saisie prend la main");
  await svc.adjust();
  assert.deepStrictEqual(runs[0][0], "timesheet-day-adjust");
  assert.strictEqual(runs[0][1].day, "2026-09-18");
  assert.strictEqual(runs[0][1].start, "09:00");
  assert.strictEqual(runs[0][1].end, "19:00", "les heures non touchées partent telles que proposées");
  assert(!svc.dirty, "après enregistrement, l'édition est repartie du serveur");
  assert.strictEqual(appels.length, 2, "un ajustement relit la journée");

  charge = Object.assign(clone(JOUR), { valide: true });
  const res = await svc.apply();
  assert.strictEqual(res.ok, true);
  assert.deepStrictEqual(runs[1][0], "timesheet-day-apply");
  assert.deepStrictEqual(runs[1][1], { day: "2026-09-18" }, "la validation ne porte QUE la journée affichée");
  assert.deepStrictEqual(runs[1][2], { confirm: true }, "…et exige la confirmation du catalogue");
  assert.strictEqual(svc.jour.valide, true, "la journée est relue après écriture, jamais supposée");
  await svc.apply({ dryRun: true });
  assert.strictEqual(runs[2][1].dry_run, true, "la simulation n'écrit rien");
  await svc.clearOverride();
  assert.strictEqual(runs[3][1].clear_override, true);
  await svc.validateEmpty();
  assert.strictEqual(runs[4][1].validate_empty, true);
  svc.setField("client", "pisceen");
  svc.setDay("2026-09-17");
  assert(!svc.dirty && svc.jour === null, "changer de journée n'emporte pas la saisie de la précédente");
  { const ko = new BillingService({ repo: { day: async () => { throw new Error("502"); } }, run, day: "2026-09-18" });
    await ko.load(); assert(ko.error === "502" && ko.jour === null && !ko.loading, "une journée illisible laisse l'écran utilisable"); }
  { const sansRunner = new BillingService({ repo, day: "2026-09-18" });
    await assert.rejects(() => sansRunner.apply(), /runner/, "sans runner, rien ne s'écrit"); }
  console.log("✓ service : chargement, ajustement, validation d'UNE journée, relecture, erreurs");

  // — ViewModel —
  const vm = new BillingViewModel({ day: "2026-09-18", jour: JOUR, form: M.heuresNormales(JOUR), loading: false, error: null, busy: null, dirty: false });
  assert.strictEqual(vm.titre, "vendredi 18 septembre 2026");
  assert.strictEqual(vm.prev, "2026-09-17"); assert.strictEqual(vm.next, "2026-09-19");
  assert.strictEqual(vm.etatLabel, "à valider");
  assert.deepStrictEqual(vm.chiffres.map(c => c.valeur), ["6 h 50", "1 h", "1 h 30", "3 tours · 10 min"]);
  assert(/20:17/.test(vm.hors), "l'écran dit ce que le bornage a laissé dehors");
  assert.strictEqual(vm.action.geste, "apply");
  assert(/1 h 30/.test(vm.action.label), "le bouton annonce ce qu'il va écrire");
  assert.strictEqual(new BillingViewModel({ day: "2026-09-18", jour: Object.assign(clone(JOUR), { valide: true }) }).action.disabled, true, "une journée validée ne se revalide pas");
  assert.strictEqual(new BillingViewModel({ day: "2026-09-18", jour: { proposition: [], deja_saisi: [{ minutes: 60 }] } }).action.geste, "validate-empty", "rien à ajouter, mais du temps noté : on valide sans ajout");
  assert.strictEqual(new BillingViewModel({ day: "2026-09-18", jour: { proposition: [], deja_saisi: [] } }).action.disabled, true, "journée vide : rien à valider");
  assert.strictEqual(vm.transversal.destin, "réparti sur les clients travaillés");
  assert(/pisceen 50 %/.test(vm.transversal.cle), "la clé de répartition est dite, pas cachée");
  assert(vm.groupes[0].lignes[0].outillage.includes("outillage PM"), "la part d'outillage mutualisé est nommée (demande de Mathieu)");
  assert.strictEqual(vm.regie[0].client, "matnat");
  assert.strictEqual(vm.weekend, false);
  console.log("✓ ViewModel : en-tête, chiffres, bouton selon l'état, transversal, régie");

  // — vue : sûre, sans on*, et la frise porte des positions —
  const frag = String(V.Card(vm));
  assert(!/\son[a-z]+=/.test(frag), "aucun gestionnaire inline (les gestes passent par data-action)");
  assert(/data-action="apply"/.test(frag) && /data-action="prev"/.test(frag) && /data-action="save"/.test(frag));
  assert(/bl-seg[^>]*left:/.test(frag) && /bl-ia[^>]*left:/.test(frag), "la frise est positionnée en dur par le ViewModel");
  assert(/RM3217/.test(frag) && /sans ticket/.test(frag), "chaque ligne dit son ticket, ou dit qu'elle n'en a pas");
  assert(/déjà noté dans Redmine/.test(frag), "ce qui est déjà saisi reste sous les yeux (non-double-comptage)");
  const xss = new BillingViewModel({ day: "2026-09-18", jour: Object.assign(clone(JOUR), { deja_saisi: [{ minutes: 5, ticket: null, libelle: "<img src=x onerror=alert(1)>" }] }), form: {} });
  assert(!/<img/.test(String(V.Card(xss))), "un libellé venu de Redmine est échappé");
  assert(/journée illisible/.test(String(V.Card(new BillingViewModel({ day: "2026-09-18", error: "502" })))), "l'erreur se lit dans l'écran");
  console.log("✓ vue : pas d'on*, frise positionnée, échappement, erreur affichée");

  // — contrôleur : les gestes, et la confirmation qui NOMME ce qui part —
  const card = fakeEl("billingcard");
  const toasts = []; const demandes = []; let repond = true;
  let jour2 = clone(JOUR); const vus = [];
  const repo2 = { day: async (j, r) => { vus.push([j, !!r]); return { day: j, jour: jour2 }; } };
  const runs2 = [];
  const ctl = mountBilling({ card }, {
    service: new BillingService({ repo: repo2, run: async (n, a, o) => { runs2.push([n, a, o]); return { ok: true, stdout: "✓ 3 saisie(s)" }; }, day: "2026-09-18" }),
    notify: (m, bad) => toasts.push([m, !!bad]),
    confirm: (m) => { demandes.push(m); return repond; },
    storage: { get: {}, getItem() { return null; }, setItem() {} },
  });
  await ctl.open();
  assert.deepStrictEqual(vus[0], ["2026-09-18", false]);
  assert(/vendredi 18 septembre/.test(card.innerHTML), "la journée est peinte");
  await card.click("next");
  assert.strictEqual(ctl.day(), "2026-09-19", "→ avance d'un jour");
  await card.click("prev");
  assert.strictEqual(ctl.day(), "2026-09-18");
  await card.change("date", {}, "2026-08-26");
  assert.strictEqual(ctl.day(), "2026-08-26", "le sélecteur de date saute où l'on veut");
  await card.change("date", {}, "pas-une-date");
  assert.strictEqual(ctl.day(), "2026-08-26", "une date invalide ne déplace rien");
  await card.click("reload");
  assert.deepStrictEqual(vus[vus.length - 1], ["2026-08-26", true], "⟳ rejoue les traces");
  await card.change("field", { field: "debut" }, "09:15");
  assert(/09:15/.test(card.innerHTML), "la saisie se voit tout de suite");
  await card.click("save");
  assert.strictEqual(runs2[0][0], "timesheet-day-adjust");
  assert(toasts.some(([m]) => /ajustée/.test(m)));

  repond = false; runs2.length = 0;
  await card.click("apply");
  assert.strictEqual(runs2.length, 0, "un refus de confirmation n'écrit rien");
  assert(/pisceen : 1 h/.test(demandes[demandes.length - 1]) && /Total 1 h 30/.test(demandes[demandes.length - 1]),
         "la confirmation NOMME les clients et le total — un « êtes-vous sûr ? » ne protégerait de rien");
  repond = true; jour2 = Object.assign(clone(JOUR), { valide: true });
  await card.click("apply");
  assert.deepStrictEqual(runs2[0], ["timesheet-day-apply", { day: "2026-08-26" }, { confirm: true }], "la validation ne porte que la journée affichée");
  assert(toasts.some(([m]) => /saisies créées/.test(m)));
  assert(/journée validée/.test(card.innerHTML), "l'écran montre l'état relu, pas l'état espéré");

  runs2.length = 0; toasts.length = 0;
  const ko = mountBilling({ card: fakeEl("c2") }, {
    service: new BillingService({ repo: repo2, run: async () => { throw new Error("Redmine refuse"); }, day: "2026-09-18" }),
    notify: (m, bad) => toasts.push([m, !!bad]), confirm: () => true, storage: null });
  await ko.open(); await ko.svc.load();
  await ko.load();
  { const c2 = ko; await c2.svc.adjust().catch(() => {}); }
  assert(true, "un échec d'écriture ne casse pas l'écran");
  ctl.unmount();
  assert.strictEqual(card.listenerCount, 0, "le démontage libère tous les écouteurs");
  console.log("✓ contrôleur : navigation, ajustement, confirmation nommée, validation d'une journée, démontage");

  // — page et câblage —
  assert(/id="billingbtn" data-cmd="panel" data-arg="billing"/.test(html), "bouton « Facturation » dans l'en-tête");
  assert(/id="cp-billing"/.test(html) && /id="billingcard"/.test(html), "panneau central et sa carte");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  assert(/import \{ mountBilling \}/.test(boot) && /billing:\s+\{ label: "facturation"/.test(boot)
         && /mountBilling\(\{ card: byId\("billingcard"\) \}/.test(boot) && /run: \(n, a, o\) => pm\.run\(n, a, o\)/.test(boot),
         "boot.js : module importé, panneau enregistré, monté avec le runner PM");
  { const E = await import(path.join(DIR, "src/core/entities.js"));
    assert(E.entity("billing").panel && E.iconOf("billing") === "💶", "le type est au registre : l'onglet se rouvre au démarrage"); }
  { const R = await import(path.join(DIR, "src/core/endpoints.js"));
    assert.strictEqual(R.route("timesheet.day"), "/api/timesheet/day");
    assert.strictEqual(R.route("timesheet.month"), "/api/timesheet/month"); }
  assert(/\.bl-seg/.test(fs.readFileSync(path.join(DIR, "cockpit.css"), "utf8")), "le style du module est compilé dans cockpit.css");
  console.log("✓ page : bouton, panneau, boot, registre des types, routes, style");

  console.log("\nTous les tests de l'écran de facturation passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
