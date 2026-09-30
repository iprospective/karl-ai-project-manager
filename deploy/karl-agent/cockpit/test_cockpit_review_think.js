// Tests RM3089 — la réflexion d'un ticket sur SA fiche (lot L6 de RM3015).
//
// Avant : le « pourquoi » d'un ticket n'était atteignable que par le panneau CDC du projet. Depuis
// la fiche, on voyait le contrat et le journal, jamais les questions qui restent à trancher — celles
// qui, pourtant, refusent la clôture. Le chiffre doit s'afficher AVANT que le refus ne tombe.
// Lancer : node test_cockpit_review_think.js
import assert from "node:assert";
import { ReviewViewModel } from "./src/modules/review/ReviewViewModel.js";
import { ThinkPane } from "./src/modules/review/Review.view.js";

const THINK = {
  file: "RM3089_x.think.md",
  counts: { questions_open: 2, notes_pending: 1, decisions: 3, features: 1 },
  questions: [{ id: "Q001", text: "Où poser le bloc ?", state: "attente" },
              { id: "Q002", text: "Tranchée depuis", state: "valide", closed: true }],
  decisions: [{ id: "D001", text: "On réutilise la route de RM3064", state: "valide", prefix: "D" },
              { id: "C001", text: "Conseil", state: "propose", prefix: "C" }],
  notes: [{ id: "N001", text: "une remarque", state: "attente" }],
  features: [{ id: "F001", text: "un outil", state: "attente" }],
};
const vm = new ReviewViewModel({ r: { found: true, title: "T", think: THINK } }, {});

// ── ce que le ViewModel décide ──────────────────────────────────────────────
assert.strictEqual(vm.think.file, "RM3089_x.think.md");
assert.strictEqual(vm.think.openQuestions, 1, "une seule question reste ouverte (l'autre est tranchée)");
assert.strictEqual(vm.think.blocking, 3, "ce qui bloque la clôture = questions ouvertes + notes à trier");
assert.strictEqual(vm.think.questions[0].icon, "🕐");
assert.strictEqual(vm.think.questions[1].icon, "✅");
assert.strictEqual(vm.think.questions[0].open, true);
assert.strictEqual(vm.think.questions[1].open, false, "une entrée tranchée n'est plus « ouverte »");
assert.strictEqual(vm.think.decisions[1].open, true, "un conseil « proposé » attend encore un arbitrage");
assert.strictEqual(new ReviewViewModel({ r: { found: true } }, {}).think, null,
  "pas de carnet : pas de bloc — une fiche n'affiche pas une section vide");

// ── le rendu ────────────────────────────────────────────────────────────────
const h = String(ThinkPane(vm.think));
assert.ok(/🧠 Réflexion/.test(h) && /RM3089_x\.think\.md/.test(h), "le bloc nomme le carnet");
assert.ok(/2 question\(s\) ouverte\(s\)/.test(h) && /3 décision\(s\)/.test(h), "les compteurs sont là");
assert.ok(/clôture est refusée tant qu'il en reste/.test(h),
  "le refus de clôture est ANNONCÉ, pas découvert au moment où il tombe");
assert.ok(/❓ questions \(2\)/.test(h) && /⚖ décisions et conseils \(2\)/.test(h)
  && /✳ fonctionnalités \(1\)/.test(h) && /📝 notes \(1\)/.test(h), "les quatre rubriques");
assert.ok(h.indexOf("questions") < h.indexOf("décisions"), "les questions d'abord : ce sont elles qui bloquent");

// ── les gestes : seulement sur ce qui est encore ouvert ────────────────────
const gestes = h.match(/data-action="think-state"[^>]*data-id="([^"]+)"[^>]*data-state="([^"]+)"/g) || [];
assert.ok(gestes.some(g => /Q001/.test(g) && /valide/.test(g)), "trancher une question ouverte est proposé");
assert.ok(!gestes.some(g => /Q002/.test(g)), "…mais pas sur une question DÉJÀ tranchée");
assert.ok(/data-state="invalide"/.test(h), "écarter est proposé aussi (le motif reste au carnet)");
assert.ok(!/\son\w+=/.test(h), "aucun gestionnaire inline");
assert.ok(/text-decoration:line-through/.test(h), "une entrée fermée se lit comme telle");

// ── D022 : une seule route d'écriture ──────────────────────────────────────
import fs from "node:fs";
const ctl = fs.readFileSync(new URL("./src/modules/review/review.controller.js", import.meta.url), "utf8");
assert.ok(/ctx\.cdc\.thinkEdit/.test(ctl), "la fiche écrit par la route de RM3064 (D022), pas par une seconde");
assert.ok(/T\.reload\(rm\)/.test(ctl), "après l'arbitrage, la fiche est relue : les compteurs suivent");
const srv = fs.readFileSync(new URL("../../../scripts/karl-agent.py", import.meta.url), "utf8");
assert.ok(/"think": _ticket_think\(tf\)/.test(srv), "le serveur sert la réflexion avec la fiche");
assert.ok(/def _ticket_think/.test(srv) && /limite: int = 40/.test(srv), "lecture bornée : une fiche s'ouvre souvent");

console.log("✓ réflexion sur la fiche d'un ticket (RM3089) : compteurs, rubriques, gestes sur l'ouvert, route unique");

// ── RM3227 : le commentaire joint à la réponse d'une question ──────────────
import { CdcService } from "./src/modules/cdc/cdc.service.js";
{
  const sent = [];
  const svc = new CdcService({ repo: { thinkEdit: async (b) => { sent.push(b); return { ok: true }; } } });
  await svc.thinkEdit({ rm: "44", id: "Q002", action: "state", state: "valide", comment: "copie dédiée" });
  await svc.thinkEdit({ rm: "44", id: "Q003", action: "state", state: "valide", comment: "" });
  await svc.thinkEdit({ rm: "44", id: "Q004", action: "state", state: "valide", force: true });
  assert.deepStrictEqual(sent[0], { rm: "44", id: "Q002", action: "state", state: "valide", comment: "copie dédiée" },
    "le service transmet le commentaire à la route");
  assert.ok(!("comment" in sent[1]), "sans commentaire, la requête est celle d'avant (pas de champ vide)");
  assert.strictEqual(sent[2].force, true, "RM3370 : le service transmet `force` — il le laissait tomber, et le geste n'atteignait jamais le serveur");
}
assert.ok(/if \(\/\^Q\/\.test\(id\)\)/.test(ctl), "la fiche ne demande une réponse que pour une QUESTION");
assert.ok(/if \(saisie === null\) return;/.test(ctl), "Annuler la saisie n'écrit rien");
// RM3370 : la requête se compose en objet (comment, et force quand on tranche sans décision) —
// on teste ce qui PART, plus la forme littérale de l'appel.
assert.ok(/if \(comment\) body\.comment = comment;/.test(ctl), "la réponse part avec le geste, par la même route");
assert.ok(/if \(force\) body\.force = true;/.test(ctl), "RM3370 : et « trancher sans décision » quand il est demandé");
assert.ok(/La DÉCISION qui tranche cette question/.test(ctl), "RM3370 : la saisie dit ce qu'elle deviendra — plus « facultatif »");
assert.ok(/else if \(!ask\(/.test(ctl), "une note garde sa simple confirmation");
const cdcCtl = fs.readFileSync(new URL("./src/modules/cdc/cdc.controller.js", import.meta.url), "utf8");
assert.ok(/RM3227/.test(cdcCtl) && /body\.comment = comment/.test(cdcCtl) && /n\.value = ""; return;/.test(cdcCtl),
  "le panneau CDC propose la même réponse, et Annuler remet le sélecteur");
assert.ok(/def _cdc_think_answer_args/.test(srv) && /--decide/.test(srv), "le serveur consigne la réponse en décision liée");
console.log("✓ RM3227/RM3370 : réponse d'une question — saisie EXIGÉE pour trancher, « sans décision » explicite, décision liée côté serveur");
