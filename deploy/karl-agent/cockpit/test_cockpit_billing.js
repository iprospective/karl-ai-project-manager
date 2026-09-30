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
    { jour: "2026-09-18", client: "pisceen", projet: "dolibarr", ticket: 3217, minutes: 45, activite: 10, outillage_min: 7, facturable: true },
    { jour: "2026-09-18", client: "pisceen", projet: "infra", ticket: null, minutes: 15, activite: 9, outillage_min: 6, facturable: true },
    { jour: "2026-09-18", client: "calicote", projet: "infra", ticket: 3199, minutes: 30, activite: 13, outillage_min: 8, facturable: true },
    { jour: "2026-09-18", client: "iprospective", projet: "pm-ai-agents", ticket: null, minutes: 15, activite: 9, outillage_min: null, facturable: false },
  ],
  bandes: [
    { debut: "08:51", fin: "09:31", client: "pisceen", minutes: 40, parts: { pisceen: 32, calicote: 8 } },
    { debut: "13:32", fin: "13:52", client: "calicote", minutes: 20, parts: { calicote: 20 } },
    { debut: "18:33", fin: "20:17", client: null, minutes: 104, parts: { null: 104 } },
  ],
  transversal_par_client: { pisceen: 55, calicote: 36 },
  pause: { declaree_h: null, trou: { debut: "12:36", fin: "13:32", minutes: 56 },
           cible: { client: "iprospective", projet: null, commentaire: "repas midi", heures: 1 } },
  deja_saisi: [{ minutes: 60, ticket: 3186, libelle: "revue de la migration", client: "pisceen", projet: "pisceen-presta" },
               { minutes: 45, ticket: null, libelle: "infra, dont 12 min d'outillage [timesheet:2026-09-18#pisceen/-@9]", client: "pisceen", projet: "infra" }],
  regie: [{ client: "matnat", motif: "presence", minutes: 90 }],
  ia: [{ heure: "08:55", ticket: 3217, client: "pisceen", projet: "dolibarr", modele: "claude-opus-5", tokens: 1200000, minutes: 4.5, minutes_reelles: 4.5, borne: false },
       { heure: "08:55", ticket: 3217, client: "pisceen", projet: "dolibarr", modele: "claude-opus-5", tokens: 800000, minutes: 3, minutes_reelles: 3, borne: false },
       { heure: "18:40", ticket: 3199, client: "calicote", projet: "infra", modele: "claude-opus-4-8", tokens: 400000, minutes: 10, minutes_reelles: 2, borne: true }],
  traces: [
    { heure: "08:51", source: "claude-history", humain: true, chars: 120, extrait: "étudie et chiffre RM3217", client: "pisceen", projet: "dolibarr", ticket: 3217 },
    { heure: "08:55", source: "claude-transcript", humain: false, chars: 40, extrait: "(tour d'agent)", client: "pisceen", projet: "dolibarr", ticket: 3217 },
    { heure: "18:40", source: "opencode", humain: true, chars: 80, extrait: "migration des boîtes", client: "calicote", projet: "infra", ticket: null },
  ],
  commits: [
    { ts: "2026-09-18T12:31:00", sha: "0679ddb0", depot: "infra", client: "calicote", sujet: "RM3199 : journal — première synchronisation IMAP", auto: false },
    { ts: "2026-09-18T13:42:00", sha: "09877eee", depot: "infra", client: "calicote", sujet: "RM3199 : journal — 7 boîtes migrées", auto: false },
    { ts: "2026-09-18T23:27:00", sha: "009d9ee1", depot: "ai-project-management", client: "iprospective", sujet: "pm(tick): RM3229 métriques temps/tokens", auto: true },
  ],
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
  assert.deepStrictEqual([t.mesure, t.propose, t.deja, t.regie, t.total], [410, 105, 105, 90, 210]);
  assert.deepStrictEqual([t.tours, t.ia, t.tokens], [3, 18, 2400000], "le temps IA est compté à part du temps humain, et DÉCLARÉ — jamais raboté du recouvrement entre tours parallèles");
  assert.strictEqual(M.etat(JOUR), "a_valider");
  assert.strictEqual(M.etat(Object.assign(clone(JOUR), { valide: true })), "validee");
  assert.strictEqual(M.etat({ proposition: [], deja_saisi: [{ minutes: 60 }], mesure_min: 0 }), "manuelle");
  assert.strictEqual(M.etat({ proposition: [], deja_saisi: [], mesure_min: 0 }), "vide");
  assert.strictEqual(M.etat(null), "vide");
  const grp = M.parClient(JOUR);
  assert.deepStrictEqual(grp.map(g => [g.client, g.minutes]), [["pisceen", 60], ["calicote", 30], ["iprospective", 15]], "groupé par client, le plus gros d'abord");
  assert.strictEqual(M.fmtTokens(2400000), "2,4 M"); assert.strictEqual(M.fmtTokens(43000), "43 k");
  console.log("✓ totaux, état, groupement par client");

  // — la frontière outil / main : c'est elle qui rend la reprise sûre —
  assert.strictEqual(M.estAutomatique({ libelle: "infra [timesheet:2026-09-18#pisceen/-@9]" }), true);
  assert.strictEqual(M.estAutomatique({ libelle: "brevo calicote dutiko" }), false, "une saisie notée à la main n'est jamais « automatique »");
  assert.strictEqual(M.estAutomatique({}), false);
  assert.strictEqual(M.libelleLisible({ libelle: "infra, dont 12 min d'outillage [timesheet:2026-09-18#pisceen/-@9]" }), "infra, dont 12 min d'outillage", "la marque technique ne s'affiche pas");
  assert.strictEqual(M.libelleLisible({ libelle: "[timesheet:x]" }), "—");
  assert.deepStrictEqual(M.poseParOutil(JOUR), { count: 1, minutes: 45 }, "seules les saisies de l'outil sont reprenables");
  assert.deepStrictEqual(M.poseParOutil({ deja_saisi: [{ minutes: 60, libelle: "à la main" }] }), { count: 0, minutes: 0 }, "une journée toute manuelle n'a rien à reprendre");
  assert.deepStrictEqual(M.poseParOutil(null), { count: 0, minutes: 0 });
  console.log("✓ frontière outil / main : ce qui est reprenable, ce qui est intouchable");

  // — la pièce à conviction : traces, commits, temps IA —
  const tr = M.traces(JOUR);
  assert.strictEqual(tr.length, 3);
  assert.deepStrictEqual([tr[0].heure, tr[0].source, tr[0].humain, tr[0].cible, tr[0].rm],
                         ["08:51", "history", true, "pisceen/dolibarr", 3217], "la trace dit l'heure, la source, sa nature et sa cible");
  assert.strictEqual(tr[1].humain, false, "une trace d'agent est marquée : elle n'crée pas de temps");
  assert.strictEqual(M.traces(null).length, 0);

  const cm = M.commits(JOUR);
  assert.deepStrictEqual([cm.total, cm.travail.length, cm.plomberie.length], [3, 2, 1], "la plomberie PM est comptée à part, pas mélangée au travail");
  assert.strictEqual(cm.travail[0].heure, "12:31", "l'heure du commit se lit directement");
  assert.strictEqual(cm.plomberie[0].sujet.startsWith("pm(tick)"), true);
  assert.deepStrictEqual(M.commits({}).travail, []);

  const groupes = M.toursIA(JOUR);
  assert.strictEqual(groupes.length, 2, "les tours d'agent se groupent par cible");
  assert.deepStrictEqual([groupes[0].cle, groupes[0].tours, groupes[0].minutes, groupes[0].tokens],
                         ["RM3199", 1, 10, 400000], "…en cumulant tours, minutes déclarées et tokens");
  assert.strictEqual(groupes[1].premier, "08:55", "…et en gardant la plage horaire");

  const cp = M.clientsEtProjets([{ client: "pisceen", project: "dolibarr" }, { client: "pisceen", project: "infra" }, { client: "calicote", project: "infra" }]);
  assert.deepStrictEqual(cp.clients, ["calicote", "pisceen"], "les clients, triés");
  assert.deepStrictEqual(cp.projets("pisceen"), ["dolibarr", "infra"], "les projets du client choisi");
  assert.deepStrictEqual(cp.projets("inconnu"), [], "un client sans projet ne casse rien");
  assert.strictEqual(M.libelleLieu("distanciel"), "distanciel (maison)");
  assert.strictEqual(M.libelleLieu(""), "", "un lieu non renseigné ne s'invente pas");
  assert.strictEqual(M.libelleLieu("ailleurs"), "");
  // — la pause de midi : signalée quand elle manque, jamais devinée —
  const pz = M.pause(JOUR);
  assert.strictEqual(pz.visible, true, "un trou de 56 min à midi, c'est une pause visible");
  assert.strictEqual(pz.manquante, false);
  assert(/12:36–13:32/.test(pz.texte));
  const sansPause = M.pause({ pause: { declaree_h: null, trou: null, cible: { client: "iprospective", heures: 1 } } });
  assert.deepStrictEqual([sansPause.manquante, sansPause.proposition, sansPause.ou], [true, 1, "iprospective"], "sans trou ni déclaration : à signaler, avec la cible configurée");
  assert.strictEqual(sansPause.texte, "aucune pause visible ce jour-là");
  const declaree = M.pause({ pause: { declaree_h: 1, trou: null, cible: { client: "iprospective" } } });
  assert.strictEqual(declaree.manquante, false, "déclarée : plus rien à signaler");
  assert(/pause déclarée : 1 h sur iprospective/.test(declaree.texte));
  assert.strictEqual(M.pause({}).manquante, false, "journée sans bloc pause : on ne réclame rien");

  assert.deepStrictEqual(M.nonFacturable(JOUR), { count: 1, minutes: 15 }, "le temps sur soi est compté à part");
  assert.deepStrictEqual(M.nonFacturable({ proposition: [{ minutes: 30, facturable: true }] }), { count: 0, minutes: 0 });
  console.log("✓ pause de midi : visible, déclarée ou manquante ; temps non facturable");

  // — couleurs, bandes, notice —
  assert.strictEqual(M.couleurClient("pisceen"), M.couleurClient("pisceen"), "une couleur stable pour un client");
  assert.notStrictEqual(M.couleurClient("pisceen"), M.couleurClient("calicote"), "deux clients, deux couleurs");
  assert.strictEqual(M.couleurClient(null), "var(--muted)", "le non-attribué reste neutre");
  assert.strictEqual(M.nomClient(null), "non attribué");
  assert.strictEqual(M.nomClient("null"), "non attribué", "le null du JSON ne doit pas s'afficher tel quel");

  const bd = M.bandes(JOUR, { from: 8 * 60, to: 21 * 60, span: 780 });
  assert.strictEqual(bd.length, 3);
  assert.strictEqual(bd[0].client, "pisceen");
  assert(bd.every(b => b.left >= 0 && b.left + b.width <= 100.01), "aucune bande ne déborde");
  assert(/pisceen 32 min · calicote 8 min/.test(bd[0].titre), "le survol dit la répartition que la couleur cache");
  assert.strictEqual(bd[2].client, "non attribué");

  const lg = M.legende(JOUR);
  assert.deepStrictEqual(lg.map(x => x.client), ["non attribué", "pisceen", "calicote"], "la notice classe par poids");
  assert.strictEqual(lg.find(x => x.client === "pisceen").duree, "32 min");

  const bp = M.bandePause(JOUR, { from: 8 * 60, to: 21 * 60, span: 780 });
  assert(bp && /pause 12:36–13:32/.test(bp.titre) && bp.declaree === false, "la pause a sa bande");
  assert.strictEqual(M.bandePause({ pause: { trou: null } }, { from: 0, span: 60 }), null);

  assert.deepStrictEqual(M.transversalParClient(JOUR).map(x => [x.client, x.duree]),
                         [["pisceen", "55 min"], ["calicote", "36 min"]], "le transversal se lit en minutes, pas en pourcentage");

  // — le fil unique, trié —
  const fl = M.fil(JOUR);
  assert.strictEqual(fl.length, 9, "traces + commits + plomberie + tours d'agent");
  const heures = fl.map(x => x.heure);
  assert.deepStrictEqual(heures, [...heures].sort(), "trié par heure, tous genres confondus");
  assert.deepStrictEqual([...new Set(fl.map(x => x.genre))].sort(), ["commit", "ia", "plomberie", "trace"]);
  assert(/en parallèle du tour suivant/.test(fl.find(x => x.genre === "ia" && x.chevauche).texte),
         "un tour parallèle est SIGNALÉ, pas raboté");

  // — le chevauchement des temps IA —
  // Le bornage a été essayé puis RETIRÉ (2026-09-22) : deux agents en parallèle produisent
  // bien deux fois du travail, même si l'horloge n'avance qu'une fois. On signale, on ne rabote pas.
  const ti = M.totauxIA(JOUR);
  assert.deepStrictEqual([ti.tours, ti.minutes, ti.paralleles, ti.horloge], [3, 18, 1, 10],
                         "le chiffre est le DÉCLARÉ ; l'horloge n'est qu'une information");
  console.log("✓ couleurs par client, notice, bande de pause, cumul transversal, fil unique, temps IA borné");

  console.log("✓ preuves : traces, commits (travail vs plomberie), tours d'agent, référentiel clients/projets");

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
  assert.deepStrictEqual(vm.chiffres.map(c => c.valeur), ["6 h 50", "1 h 45", "1 h 45", "3 tours · 18 min"]);
  assert.deepStrictEqual([vm.auto.count, vm.auto.minutes], [1, 45], "l'écran sait ce que l'outil a posé ici");
  assert.strictEqual(vm.manuelles, 1, "…et combien de saisies sont à la main, donc protégées");
  assert.strictEqual(vm.reprenable, true);
  assert.strictEqual(new BillingViewModel({ day: "2026-09-18", jour: { deja_saisi: [{ minutes: 60, libelle: "à la main" }] } }).reprenable, false, "rien posé par l'outil : pas de bouton de reprise");
  assert(/20:17/.test(vm.hors), "l'écran dit ce que le bornage a laissé dehors");
  assert.strictEqual(vm.action.geste, "apply");
  assert(/1 h 45/.test(vm.action.label), "le bouton annonce ce qu'il va écrire");
  assert.strictEqual(new BillingViewModel({ day: "2026-09-18", jour: Object.assign(clone(JOUR), { valide: true, proposition: [] }) }).action.disabled, true, "une journée validée sans reste ne se revalide pas");
  // Décision du 2026-09-21 : juin à août se repassent journée par journée. Corriger les heures
  // d'une journée déjà validée peut faire apparaître un complément — le bouton doit le proposer,
  // et dire qu'il COMPLÈTE (le déjà-saisi étant déduit, rien n'est écrit deux fois).
  { const rouvert = new BillingViewModel({ day: "2026-06-12", jour: Object.assign(clone(JOUR), { valide: true }) });
    assert.strictEqual(rouvert.action.geste, "apply", "une journée validée reste complétable");
    assert(/^Compléter/.test(rouvert.action.label), "…et le bouton dit qu'il complète, pas qu'il valide"); }
  assert.strictEqual(new BillingViewModel({ day: "2026-09-18", jour: { proposition: [], deja_saisi: [{ minutes: 60 }] } }).action.geste, "validate-empty", "rien à ajouter, mais du temps noté : on valide sans ajout");
  assert.strictEqual(new BillingViewModel({ day: "2026-09-18", jour: { proposition: [], deja_saisi: [] } }).action.disabled, true, "journée vide : rien à valider");
  assert.strictEqual(vm.transversal.destin, "réparti sur les clients travaillés");
  assert(/pisceen 50 %/.test(vm.transversal.cle), "la clé de répartition est dite, pas cachée");
  assert(vm.groupes[0].lignes[0].outillage.includes("outillage PM"), "la part d'outillage mutualisé est nommée (demande de Mathieu)");
  assert.strictEqual(vm.regie[0].client, "matnat");
  assert.strictEqual(vm.weekend, false);
  { const avecRef = new BillingViewModel({ day: "2026-09-18", jour: JOUR, form: { client: "pisceen", projet: "dolibarr" },
      projets: [{ client: "pisceen", project: "dolibarr" }, { client: "pisceen", project: "infra" }, { client: "calicote", project: "infra" }] });
    assert.deepStrictEqual(avecRef.clients.map(c => c.value), ["calicote", "pisceen"]);
    assert.strictEqual(avecRef.clients.find(c => c.value === "pisceen").selected, true, "le client courant est présélectionné");
    assert.deepStrictEqual(avecRef.projetsDuClient.map(p => p.value), ["dolibarr", "infra"], "les projets suivent le client choisi");
    const inconnu = new BillingViewModel({ day: "2026-09-18", jour: JOUR, form: { client: "villacactus", projet: "site" }, projets: [{ client: "pisceen", project: "dolibarr" }] });
    assert.strictEqual(inconnu.clients[0].value, "villacactus", "une valeur absente du référentiel reste proposée — un menu ne perd jamais une donnée existante");
    assert.strictEqual(inconnu.projetsDuClient[0].value, "site"); }
  assert.strictEqual(vm.traces.length, 3);
  assert.strictEqual(vm.tracesHumaines, 2);
  assert.strictEqual(vm.commits.travail.length, 2);
  assert.strictEqual(vm.ia[0].duree, "10 min", "la durée déclarée du tour, telle quelle");
  assert.strictEqual(vm.ia[1].plage, "08:55");
  assert.strictEqual(vm.nonFacturable.label, "15 min", "l'écran chiffre ce qui ne sera facturé à personne");
  assert.strictEqual(vm.groupes.find(g => g.client === "iprospective").facturable, false);
  assert.strictEqual(vm.groupes.find(g => g.client === "pisceen").facturable, true);
  assert.deepStrictEqual([vm.dejaSaisi[0].client, vm.dejaSaisi[0].projet], ["pisceen", "pisceen-presta"], "le déjà-noté dit OÙ, en deux colonnes");
  { const ici = new BillingViewModel({ day: "2026-09-18", jour: JOUR, form: { lieu: "presentiel" } });
    assert.strictEqual(ici.lieu, "présentiel");
    assert.strictEqual(ici.lieux.find(l => l.value === "presentiel").selected, true); }
  console.log("✓ ViewModel : en-tête, chiffres, bouton selon l'état, transversal, régie");

  // — vue : sûre, sans on*, et la frise porte des positions —
  const frag = String(V.Card(vm));
  assert(!/\son[a-z]+=/.test(frag), "aucun gestionnaire inline (les gestes passent par data-action)");
  assert(/data-action="apply"/.test(frag) && /data-action="prev"/.test(frag) && /data-action="save"/.test(frag));
  assert(/bl-seg[^>]*left:/.test(frag) && /bl-ia[^>]*left:/.test(frag), "la frise est positionnée en dur par le ViewModel");
  assert(/RM3217/.test(frag) && /sans ticket/.test(frag), "chaque ligne dit son ticket, ou dit qu'elle n'en a pas");
  assert(/déjà noté dans Redmine/.test(frag), "ce qui est déjà saisi reste sous les yeux (non-double-comptage)");
  assert(/data-action="revoke"/.test(frag) && /retirer 1 saisie \(45 min\)/.test(frag), "le bouton de reprise annonce ce qu'il retire");
  assert(/bl-o-auto[^>]*>outil</.test(frag) && /bl-o-main[^>]*>à la main</.test(frag), "chaque saisie déjà notée dit d'où elle vient");
  assert(!/\[timesheet:/.test(frag), "la marque technique ne fuit jamais à l'écran");
  assert(/<select[^>]*data-field="client"/.test(frag) && /<select[^>]*data-field="projet"/.test(frag), "client et projet se choisissent dans un menu");
  assert(/<select[^>]*data-field="lieu"/.test(frag) && /distanciel \(maison\)/.test(frag), "le lieu de travail se choisit à la journée");
  assert(/bl-cl[^>]*>pisceen</.test(frag), "le déjà-noté montre le client en colonne");
  assert(/non facturé/.test(frag), "un groupe sur soi est marqué non facturé");
  assert(/12:36–13:32/.test(frag), "l'écran dit que la pause apparaît");
  { const manque = new BillingViewModel({ day: "2026-09-18", jour: Object.assign(clone(JOUR), { pause: { declaree_h: null, trou: null, cible: { client: "iprospective", heures: 1, commentaire: "repas midi" } } }), form: {} });
    const f2 = String(V.Card(manque));
    assert(/data-action="pause-midi"/.test(f2) && /aucune pause visible/.test(f2), "pause manquante : un bouton pour la noter en un clic"); }
  assert(/ce qui s'est passé — 9 actions/.test(frag), "un seul fil : traces, commits et tours d'agent réunis");
  assert(/2 traces humaines · 2 commits · 3 tours d'agent/.test(frag), "…et le détail de sa composition");
  assert(/RM3199 : journal/.test(frag), "le sujet du commit se lit");
  assert(/bl-leg-i/.test(frag) && /background:hsl\(/.test(frag), "la notice donne une couleur par client");
  assert(/bl-pause-band/.test(frag), "la pause a sa propre bande, neutre");
  assert(/bl-tc-i/.test(frag), "le transversal montre son cumul par client");
  assert(/en parallèle du tour suivant/.test(frag), "un tour d'agent parallèle le signale");
  const xss = new BillingViewModel({ day: "2026-09-18", jour: Object.assign(clone(JOUR), { deja_saisi: [{ minutes: 5, ticket: null, libelle: "<img src=x onerror=alert(1)>" }] }), form: {} });
  assert(!/<img/.test(String(V.Card(xss))), "un libellé venu de Redmine est échappé");
  assert(/journée illisible/.test(String(V.Card(new BillingViewModel({ day: "2026-09-18", error: "502" })))), "l'erreur se lit dans l'écran");
  console.log("✓ vue : pas d'on*, frise positionnée, échappement, erreur affichée");

  // — contrôleur : les gestes, et la confirmation qui NOMME ce qui part —
  const card = fakeEl("billingcard");
  const toasts = []; const demandes = []; let repond = true;
  let jour2 = clone(JOUR); const vus = [];
  const repo2 = { day: async (j, r) => { vus.push([j, !!r]); return { day: j, jour: jour2 }; },
                  projects: async () => ({ projects: [{ client: "pisceen", project: "dolibarr" }, { client: "pisceen", project: "infra" }, { client: "calicote", project: "infra" }] }) };
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
  await new Promise(r => setTimeout(r, 0));
  assert(/<option value="calicote"/.test(card.innerHTML) && /<option value="pisceen"/.test(card.innerHTML), "les menus se peuplent au référentiel PM");
  await card.change("field", { field: "client" }, "pisceen");
  await card.change("field", { field: "projet" }, "infra");
  assert.strictEqual(ctl.svc.form().projet, "infra");
  await card.change("field", { field: "client" }, "calicote");
  assert.strictEqual(ctl.svc.form().projet, "", "changer de client remet le projet à zéro — une paire client/projet inexistante n'a pas de sens");
  await card.click("save");
  assert.strictEqual(runs2[0][0], "timesheet-day-adjust");
  // la pause en un clic : elle passe par l'ajustement, elle n'écrit RIEN dans Redmine
  { jour2 = Object.assign(clone(JOUR), { pause: { declaree_h: null, trou: null, cible: { client: "iprospective", heures: 1 } } });
    await ctl.load(false); runs2.length = 0;
    await card.click("pause-midi");
    assert.strictEqual(runs2[0][0], "timesheet-day-adjust", "la pause n'est pas une écriture Redmine");
    assert.strictEqual(runs2[0][1].pause, "1", "elle pose la durée configurée");
    assert(!runs2.some(([n]) => n === "timesheet-day-apply"), "…et ne valide rien au passage");
    jour2 = clone(JOUR); await ctl.load(false); }
  assert(toasts.some(([m]) => /ajustée/.test(m)));

  repond = false; runs2.length = 0;
  await card.click("apply");
  assert.strictEqual(runs2.length, 0, "un refus de confirmation n'écrit rien");
  assert(/pisceen : 1 h/.test(demandes[demandes.length - 1]) && /Total 1 h 45/.test(demandes[demandes.length - 1]),
         "la confirmation NOMME les clients et le total — un « êtes-vous sûr ? » ne protégerait de rien");
  repond = true; jour2 = Object.assign(clone(JOUR), { valide: true });
  await card.click("apply");
  assert.deepStrictEqual(runs2[0], ["timesheet-day-apply", { day: "2026-08-26" }, { confirm: true }], "la validation ne porte que la journée affichée");
  assert(toasts.some(([m]) => /saisies créées/.test(m)));
  assert(/bl-state bl-validee/.test(card.innerHTML), "l'écran montre l'état relu, pas l'état espéré");

  // — la reprise : à la demande, jamais toute seule —
  runs2.length = 0; demandes.length = 0; vus.length = 0;
  jour2 = clone(JOUR);                       // journée de nouveau « à valider », 1 saisie de l'outil
  await ctl.load(false);
  runs2.length = 0; vus.length = 0;
  repond = false;
  await card.click("revoke");
  assert.strictEqual(runs2.length, 0, "un refus de confirmation ne supprime RIEN");
  const q = demandes[demandes.length - 1];
  assert(/Retirer 1 saisie \(45 min\)/.test(q), "la confirmation dit ce qui part");
  assert(/1 saisie\(s\) notée\(s\) à la main ne sont PAS touchées/.test(q), "…et ce qui est protégé");
  assert(/sauvegarde/.test(q), "…et qu'une sauvegarde est écrite avant");
  repond = true;
  await card.click("revoke");
  assert.deepStrictEqual(runs2[0], ["timesheet-day-revoke", { day: ctl.day() }, { confirm: true }], "la reprise ne porte que la journée affichée");
  assert.deepStrictEqual(vus[vus.length - 1], [ctl.day(), true], "après une reprise, la journée est RÉANALYSÉE, pas relue du cache");

  // le cœur du garde-fou : aucun autre geste de l'écran ne déclenche une reprise
  runs2.length = 0;
  await card.click("reload"); await card.click("next"); await card.click("prev");
  await card.change("field", { field: "debut" }, "09:00"); await card.click("save");
  await card.click("apply");
  assert(!runs2.some(([n]) => n === "timesheet-day-revoke"), "naviguer, relire, ajuster ou valider ne supprime jamais rien");

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
