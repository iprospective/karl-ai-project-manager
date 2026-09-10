// Tests RM3074 — l'onglet MR du worklog : le cycle complet, groupé, avec son détail.
//
// L'angle mort que ce ticket ferme : le worklog ne listait que les MR OUVERTES. Une MR mergée dans
// l'intégration disparaissait de l'écran alors que le travail n'était PAS en production — « pas de
// MR » et « mergée, à promouvoir » se confondaient. Les tests verrouillent donc, d'abord, que ce
// groupe existe et qu'il compte dans le geste à faire.
// Lancer : node test_cockpit_worklog_mrs.js
import assert from "node:assert";
import { mrCycle, mrTodoCount, worklogTabList, MR_GROUPS } from "./src/modules/worklog/worklog.js";
import { WorklogViewModel, mrDetail } from "./src/modules/worklog/WorklogViewModel.js";
import { MrRow, MrPane, WorklogPane } from "./src/modules/worklog/Worklog.view.js";

const MRS = [
  { iid: 11, ref: "RM10", repo: "ai-pm-core", source: "10-feature", target: "dev", state: "opened", url: "http://f/11", ts: "2026-09-01T10:00" },
  { iid: 12, ref: "RM11", repo: "ai-pm-core", source: "11-fix", target: "dev", state: "merged", url: "http://f/12", ts: "2026-09-05T10:00" },
  { iid: 13, ref: "RM12", repo: "site", source: "dev", target: "main", state: "merged", url: "http://f/13", ts: "2026-09-06T10:00" },
  { iid: 14, ref: "RM13", target: "dev", state: "closed", ts: "2026-09-02T10:00" },
  { iid: 15, ref: "RM14", target: "dev", state: "reopened", ts: "2026-09-07T10:00" },
];

// ── le cycle ────────────────────────────────────────────────────────────────
const c = mrCycle(MRS, "dev");
assert.deepStrictEqual([c.open.length, c.integration.length, c.prod.length], [2, 1, 1],
  "ouvertes (dont rouverte), mergées dans l'intégration, promues");
assert.ok(!JSON.stringify(c).includes('"iid":14'), "une MR fermée sans merge ne dit rien du cycle : écartée");
assert.strictEqual(c.integration[0].iid, 12, "le groupe qui n'existait nulle part : mergé dans dev, pas encore en production");
assert.strictEqual(c.open[0].iid, 15, "au sein d'un groupe, la plus récente d'abord");
assert.strictEqual(c.open[0].stage, "open", "l'étape voyage avec la ligne");

// la branche d'intégration vient de la CONF, pas d'une liste en dur
const c2 = mrCycle(MRS, "integration");
assert.strictEqual(c2.prod.length, 2, "avec une autre branche d'intégration, « mergée vers dev » devient une promotion");
assert.strictEqual(mrCycle(MRS, undefined).integration.length, 1, "sans conf, repli sur dev — mais c'est bien un repli");

// ── le compteur ne compte que ce qui appelle un geste ───────────────────────
assert.strictEqual(mrTodoCount(MRS, "dev"), 3, "à merger (2) + à promouvoir (1) ; les promues ne gonflent pas le chiffre");
assert.strictEqual(mrTodoCount([], "dev"), 0);
const tabs = worklogTabList([], 0, 0, 3);
assert.deepStrictEqual(tabs.map(t => t.key + ":" + t.n), ["mrs:3"], "l'onglet MR porte ce compteur");
assert.strictEqual(worklogTabList([], 0, 0, 0).length, 0, "aucune MR : pas d'onglet vide");
assert.strictEqual(MR_GROUPS.length, 3);
assert.ok(MR_GROUPS.every(g => g.hint && g.hint.length > 20), "chaque groupe explique ce qu'il attend");
assert.ok(/lot/i.test(MR_GROUPS[1].hint), "le groupe « à promouvoir » rappelle que la promotion se fait par lot, pas MR par MR");

// ── le détail d'une ligne ───────────────────────────────────────────────────
const d = mrDetail(MRS[0], { ago: () => "il y a 9 j" });
assert.strictEqual(d.repo, "ai-pm-core"); assert.strictEqual(d.source, "10-feature"); assert.strictEqual(d.target, "dev");
assert.strictEqual(d.rm, "10", "le RM est extrait pour rendre le ticket cliquable");
assert.strictEqual(d.age, "il y a 9 j"); assert.strictEqual(d.mergeable, true);
assert.strictEqual(mrDetail(MRS[1], {}).mergeable, false, "une MR mergée n'offre pas le bouton merger");
assert.strictEqual(mrDetail({ iid: 9, alive: false }, {}).dead, true, "session éteinte signalée");
assert.strictEqual(mrDetail({}, {}).iid, "?", "une MR sans iid ne casse pas le rendu");

// ── le rendu ────────────────────────────────────────────────────────────────
const row = String(MrRow(d, { tip: () => "" }));
for (const attendu of ["!11", "RM10", "ai-pm-core", "10-feature", "dev", "il y a 9 j", "opened"]) {
  assert.ok(row.includes(attendu), "la ligne montre « " + attendu + " »");
}
assert.ok(/data-action="merge-one"/.test(row) && /data-iid="11"/.test(row), "le geste merger, avec ce qu'il faut pour l'exécuter");
assert.ok(!/\son\w+=/.test(row), "aucun gestionnaire inline");
assert.ok(!/data-action="merge-one"/.test(String(MrRow(mrDetail(MRS[1], {}), { tip: () => "" }))), "pas de bouton merger sur une MR déjà mergée");

const w = { found: true, mrs_pending: [MRS[0]], mrs_all: MRS, integration: "dev", buckets: {}, docs: {} };
const vm = new WorklogViewModel({ data: w, attached: true }, { ago: () => "il y a 2 j", integration: w.integration });
assert.strictEqual(vm.mrTodo, 3);
assert.deepStrictEqual(vm.mrGroups().map(g => g.key), ["open", "integration", "prod"]);
const pane = String(MrPane(vm.mrGroups(), { tip: () => "" }));
assert.ok(/à promouvoir en production/.test(pane) && /!12/.test(pane), "le groupe à promouvoir est rendu, avec sa MR");
assert.strictEqual(String(MrPane([], {})).includes("aucune MR"), true, "état vide explicite");

// ── la tête du worklog : un rappel, plus la liste (le détail est dans l'onglet) ─
const head = String(WorklogPane(vm, { tip: () => "", pin: () => "", linkify: (s) => s }));
assert.ok(/MR à merger/.test(head) && /voir l’onglet/.test(head), "un rappel compact, cliquable vers l'onglet");
assert.ok(/data-action="sub" data-key="mrs"/.test(head), "le rappel mène à l'onglet MR");
assert.ok(!/data-action="merge-one"/.test(head.split("rsub")[0]), "le bouton merger n'est plus dupliqué en tête");
assert.ok(/🔀 MR/.test(head), "l'onglet apparaît dans la barre de sous-onglets, même sans aucun ticket ouvert");
assert.ok(!/aucun ticket ouvert dans cette session/.test(head),
  "une session qui n'a QUE des MR n'est pas un worklog vide — sinon son onglet MR serait inatteignable");

console.log("✓ onglet MR du worklog (RM3074) : cycle complet, groupe « à promouvoir », détail, compteur, tête allégée");

// ── RM3088 : « ❓ à trancher », distinct de « 📥 à traiter » ─────────────────
// Une DEMANDE appelle une action, une QUESTION un arbitrage (RM3015-C008) : les fondre ferait
// perdre le sens des deux colonnes ; les séparer sans les montrer ensemble ferait perdre la vue.
const wq = { found: true, questions_open: [{ ref: "RM3015", rm: "3015", n: 4 }, { ref: "RM99", rm: "99", n: 1 }],
             requests_open: [{ n: 1, text: "une demande non ticketée" }], buckets: {}, docs: {} };
const vmq = new WorklogViewModel({ data: wq, attached: true }, { ago: () => "2min" });
assert.deepStrictEqual(vmq.questions().map(q => q.ref), ["RM3015", "RM99"]);
const hq = String(WorklogPane(vmq, { tip: () => "", pin: () => "", linkify: (s) => s }));
assert.ok(/❓ à trancher \(5\)/.test(hq), "le compteur additionne les questions, pas les tickets");
assert.ok(/>1<\/span> question sans réponse/.test(hq) && />4<\/span> questions sans réponse/.test(hq),
  "singulier et pluriel — le nombre est une pastille, la phrase s'accorde avec");
assert.ok(hq.indexOf("à trancher") < hq.indexOf("demandes à traiter"), "à trancher AVANT à traiter : l'arbitrage débloque le reste");
assert.ok(/data-action="ticket" data-rm="3015"/.test(hq), "le ticket est cliquable depuis le bloc");
assert.ok(!/à trancher/.test(String(WorklogPane(new WorklogViewModel({ data: { found: true, buckets: {}, docs: {} }, attached: true }, {}), { tip: () => "", pin: () => "", linkify: (s) => s }))),
  "aucune question ouverte : pas de bloc vide");

console.log("✓ bloc « à trancher » (RM3088) : compteur, singulier/pluriel, ordre, ticket cliquable");
