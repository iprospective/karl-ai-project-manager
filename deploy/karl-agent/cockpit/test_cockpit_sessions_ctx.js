// Tests RM3082 — jauge de contexte des tuiles de session : paliers, silence, franchissement, bandeau.
//
// Ce qui casserait en silence :
//   - une jauge qui parle SOUS le premier palier (le signal devient du bruit, on cesse de le voir) ;
//   - un pourcentage calculé contre la mauvaise fenêtre (1M vs 200k) : 20 % affiché 100 % ;
//   - une animation qui se rejoue à CHAQUE tick (le rendu est reconstruit toutes les quelques secondes) ;
//   - une valeur inventée quand le transcript ne dit rien.
// Lancer : node test_cockpit_sessions_ctx.js
import assert from "node:assert";
import { contextGauge, contextCrossed } from "./src/modules/sessions/sessions.js";
import { ctxPct, modelWindow, fmtWin } from "./src/modules/ticket/ticketFormat.js";
import { SessionTileViewModel, AttnChipViewModel } from "./src/modules/sessions/SessionsViewModel.js";
import { CtxGauge, AttnBand } from "./src/modules/sessions/Sessions.view.js";

const TH = { warn: 50, high: 75, crit: 90 };
const g = (session, th = TH) => contextGauge(session, th, ctxPct, modelWindow, fmtWin);
// Un modèle à fenêtre 200k pour les cas de paliers (RM3084 : Opus 5 est à 1M — cf. la fin du fichier).
const claude = (ctx) => ({ rm_id: "1", context: ctx, model: "claude-opus-4-8" });

// ── paliers ─────────────────────────────────────────────────────────────────
assert.strictEqual(g(claude(80000)), null, "40 % : silence total, pas de jauge");
assert.strictEqual(g(claude(98000)), null, "49 % : encore sous le palier");
assert.strictEqual(g(claude(99000)).level, "warn", "49,5 % arrondit à 50 — même arrondi que l'encart méta, une seule vérité sur le chiffre");
assert.strictEqual(g(claude(100000)).level, "warn", "50 % pile : premier palier atteint");
assert.strictEqual(g(claude(152000)).level, "high", "76 % : palier élevé");
assert.strictEqual(g(claude(190000)).level, "crit", "95 % : palier critique");
const j = g(claude(152000));
assert.strictEqual(j.pct, 76); assert.strictEqual(j.label, "76 %"); assert.strictEqual(j.width, 76);
assert.ok(/152k \/ 200k \(76 %\)/.test(j.title) && /claude-opus-4-8/.test(j.title), "l'infobulle dit les jetons, la fenêtre et le modèle");
assert.ok(/compaction/.test(j.title), "l'infobulle dit ce qui va arriver, pas seulement un chiffre");
assert.ok(/consigne/.test(g(claude(190000)).title), "au palier critique, l'infobulle dit le geste à faire");

// la largeur ne déborde jamais, même au-delà de la fenêtre annoncée
assert.strictEqual(g({ rm_id: "1", context: 240000, model: "claude-opus-4-8", rates: { context_window: 200000 } }).width, 100,
  "au-delà de 100 %, la barre reste pleine (elle ne sort pas de la tuile)");

// ── la fenêtre du modèle décide, pas le nombre brut ─────────────────────────
assert.strictEqual(g({ rm_id: "1", context: 250000, model: "claude-opus-5" }), null,
  "250k dans une fenêtre 1M = 25 % : sous le palier, donc silence (et surtout pas 125 % d'une fenêtre 200k)");
assert.strictEqual(g({ rm_id: "1", context: 600000, model: "claude-opus-5" }).pct, 60,
  "600k sur 1M = 60 % — la fenêtre du modèle décide du chiffre");
assert.strictEqual(g({ rm_id: "1", context: 600000, model: "claude-opus-5" }).level, "warn",
  "…et donc du palier : « warn » là où une fenêtre 200k aurait crié au rouge");
assert.strictEqual(g({ rm_id: "1", context: 150000, model: "un-modele-inconnu" }), null,
  "modèle sans fenêtre connue : aucune jauge plutôt qu'un pourcentage inventé");
assert.strictEqual(g({ rm_id: "1", context: 0, model: "claude-opus-4-8" }), null,
  "aucun tour lu dans la queue du transcript : rien");
assert.strictEqual(g({ rm_id: "1" }), null, "session sans donnée de contexte : rien");

// ── seuils réglables ────────────────────────────────────────────────────────
assert.strictEqual(g(claude(80000), { warn: 30, high: 60, crit: 80 }).level, "warn",
  "40 % ne dit rien avec les seuils par défaut, mais « warn » avec un palier à 30 : les seuils sont bien des données");
assert.strictEqual(g(claude(170000), { warn: 30, high: 60, crit: 80 }).level, "crit",
  "85 % : critique dès 80");

// ── franchissement : monter, une seule fois ─────────────────────────────────
const seen = new Map();
assert.strictEqual(contextCrossed("42", "warn", seen), true, "premier franchissement : ça pulse");
assert.strictEqual(contextCrossed("42", "warn", seen), false, "même palier au tick suivant : silence");
assert.strictEqual(contextCrossed("42", "high", seen), true, "palier supérieur : ça pulse de nouveau");
assert.strictEqual(contextCrossed("42", "warn", seen), false, "redescendre (compaction) ne pulse pas");
assert.strictEqual(contextCrossed("42", "high", seen), true, "puis remonter pulse à nouveau");
assert.strictEqual(contextCrossed("43", "", seen), false, "sous le premier palier : jamais d'animation");

// ── ViewModel ───────────────────────────────────────────────────────────────
const vm = new SessionTileViewModel(claude(190000), { ctxThresholds: TH, ctxPulsing: new Set(["1"]) });
assert.strictEqual(vm.ctxGauge.level, "crit"); assert.strictEqual(vm.ctxPulse, true);
const vm2 = new SessionTileViewModel(claude(190000), { ctxThresholds: TH, ctxPulsing: new Set() });
assert.strictEqual(vm2.ctxPulse, false, "sans franchissement, la tuile ne bouge pas");
assert.strictEqual(new SessionTileViewModel(claude(10000), { ctxThresholds: TH }).ctxGauge, null);

// ── vue ─────────────────────────────────────────────────────────────────────
const html = String(CtxGauge(vm.ctxGauge, vm.ctxPulse));
assert.ok(/class="tctx ctx-crit ctx-cross"/.test(html), "classe de palier + marque de franchissement");
assert.ok(/width:95%/.test(html), "la barre porte la largeur");
assert.ok(/95 %/.test(html), "le chiffre est écrit — la couleur ne porte jamais l'info seule");
assert.ok(!/\son\w+=/.test(html), "aucun gestionnaire inline");
assert.strictEqual(String(CtxGauge(null, false)), "", "pas de jauge, pas de balise");
assert.ok(!/ctx-cross/.test(String(CtxGauge(vm.ctxGauge, false))), "sans franchissement, pas d'animation");

// ── bandeau « à traiter » ───────────────────────────────────────────────────
const chip = new AttnChipViewModel(claude(190000), { found: true, title: "Un ticket" }, g(claude(190000)));
const band = String(AttnBand([chip], { titleLink: (rm, t) => String(t || "") }));
assert.ok(/à traiter \(1\)/.test(band) && /95 %/.test(band), "une session au bout de son contexte remonte dans « à traiter », avec son pourcentage");
assert.strictEqual(new AttnChipViewModel(claude(152000), null, g(claude(152000))).ctxGauge, null,
  "seul le palier critique remonte dans le bandeau — les autres restent sur leur tuile");

console.log("✓ jauge de contexte (RM3082) : paliers, silence sous seuil, fenêtre du modèle, franchissement unique, bandeau");

// ── RM3084 : la fenêtre retenue est le MAXIMUM connu du modèle ──────────────
import { modelWindow as MW } from "./src/modules/ticket/ticketFormat.js";
import { contextLine } from "./src/modules/sessions/sessions.js";
import { tabTip } from "./src/modules/sessions/sessions.js";

assert.strictEqual(MW("claude-opus-5", null, 197000), 1000000,
  "Opus 5 : la variante 1M est la fenêtre retenue — c'est le bug vu sur RM3058 (197k rapportés à 200k = 99 %)");
assert.strictEqual(MW("claude-opus-5", { context_window: 200000 }, 197000), 1000000,
  "un context_window plus PETIT dans les tarifs ne fait pas baisser la fenêtre : on garde le max");
assert.strictEqual(MW("claude-opus-5[1m]", null, 10), 1000000, "le suffixe [1m] reste reconnu");
assert.strictEqual(MW("claude-opus-4-8", null, 10), 200000, "les modèles à 200k gardent 200k");
assert.strictEqual(MW("claude-opus-5", null, 10), 1000000,
  "…et la fenêtre ne dépend PAS de l'occupation courante : elle ne saute plus en cours de session");
assert.strictEqual(MW("un-modele-jamais-vu", null, 10), null, "modèle inconnu : aucune fenêtre, donc aucun pourcentage");
assert.strictEqual(MW("claude-experimental-x", null, 10), 200000, "un claude inconnu garde le repli prudent");
assert.strictEqual(MW("claude-experimental-x", null, 250000), 1000000, "…mais jamais une fenêtre plus petite que l'occupation constatée");

// le cas de Mathieu, bout en bout
const rm3058 = { rm_id: "3058", context: 197000, model: "claude-opus-5" };
assert.strictEqual(g(rm3058), null, "197k sur 1M = 20 % : sous le premier palier, donc silence (et non plus « 99 % » en rouge)");
assert.ok(/197k \/ 1M \(20 %\)/.test(contextLine(rm3058)), "l'infobulle donne l'occupation, la fenêtre et le pourcentage justes");
assert.ok(/opus-5/.test(contextLine(rm3058)) && !/claude-/.test(contextLine(rm3058)), "le modèle est nommé, sans son préfixe");
assert.strictEqual(contextLine({ rm_id: "1" }), "", "pas de donnée de contexte : pas de ligne");
assert.ok(/contexte : 197k/.test(tabTip(rm3058, null)), "…et elle apparaît au survol de la tuile, avec les autres infos");
assert.ok(!/contexte :/.test(tabTip({ rm_id: "1" }, null)), "une session sans contexte connu n'invente pas de ligne");

console.log("✓ fenêtre de contexte (RM3084) : maximum du modèle, stable en cours de session, visible au survol");
