// Tests RM3249 — bouton « compacter » sur la tuile de session, au palier critique du contexte.
//
// Ce qui casserait en silence :
//   - un bouton qui apparaît sous le palier (bruit), ou sur un moteur qui ne sait pas compacter (clic mort) ;
//   - un clic qui part pendant un tour ou sur une question : « /compact » serait tapé comme RÉPONSE au menu ;
//   - un geste qui n'atteint jamais le serveur (route non déclarée, cf. RM3174) — d'où l'appel réel, URL comprise.
// Lancer : node test_cockpit_sessions_compact.js
import assert from "node:assert";
import { SessionTileViewModel } from "./src/modules/sessions/SessionsViewModel.js";
import { Tile } from "./src/modules/sessions/Sessions.view.js";
import { SessionsService } from "./src/modules/sessions/sessions.service.js";
import { configureApi } from "./src/core/api.js";

const TH = { warn: 50, high: 75, crit: 90 };
const vm = (s) => new SessionTileViewModel(s, { ctxThresholds: TH });
// fenêtre 200k (claude-opus-4-8) : 184k = 92 %, 160k = 80 %
const s = (extra) => Object.assign({ rm_id: "42", model: "claude-opus-4-8", context: 184000, state: "idle", can_compact: true }, extra);

// ── quand le bouton existe ──────────────────────────────────────────────────
assert.strictEqual(vm(s({ context: 160000 })).compact, null, "80 % : sous le palier critique, pas de bouton");
assert.strictEqual(vm(s({ can_compact: undefined })).compact, null, "moteur sans commande de compaction (shell) : pas de bouton");
assert.strictEqual(vm(s({ context: 0 })).compact, null, "contexte inconnu : pas de bouton, jamais sur un chiffre inventé");
const pret = vm(s()).compact;
assert.ok(pret && pret.ready, "92 % au repos : bouton actif");
assert.ok(/92 %/.test(pret.title), "l'infobulle dit l'occupation qui justifie le geste");
const occupe = vm(s({ state: "working" })).compact;
assert.ok(occupe && !occupe.ready, "au travail : bouton visible mais éteint");
assert.ok(/au repos/.test(occupe.title), "…et il dit ce qu'il attend");
assert.ok(!vm(s({ state: "attention" })).compact.ready, "sur une question : éteint (« /compact » partirait comme réponse)");
assert.strictEqual(vm(s({ context: 184000 })).compact.ready, true);
assert.ok(vm(s()).compact && new SessionTileViewModel(s(), { ctxThresholds: { warn: 50, high: 75, crit: 95 } }).compact === null,
  "le seuil est celui du palier critique configuré, pas un 90 écrit en dur");

// ── rendu ───────────────────────────────────────────────────────────────────
const deps = { pin: () => "", titleLink: (rm, t) => t };
const H = String(Tile(vm(s()), deps));
assert.ok(/class="tcompact" data-action="compact" data-k="s:42"/.test(H), "la tuile porte le geste, délégué comme les autres (data-action)");
assert.ok(/class="tcompact off"/.test(String(Tile(vm(s({ state: "working" })), deps))), "éteint : classe `off`");
assert.ok(!/tcompact/.test(String(Tile(vm(s({ context: 100000 })), deps))), "sous le palier : rien dans la tuile");
console.log("✓ bouton compacter (RM3249) : au palier critique, si le moteur sait le faire, éteint hors repos");

// ── le geste atteint le serveur, par la route déclarée ──────────────────────
{
  const vus = [];
  configureApi({ fetch: async (p, o) => { vus.push([p, o && o.body]);
    return { ok: true, status: 200, statusText: "", headers: { get: () => "application/json" },
             json: async () => ({ rm_id: "42", engine: "claude", cmd: "/compact", sent: true }), text: async () => "" }; } });
  const svc = new SessionsService({});
  const msg = await svc.compact("42");
  assert.ok(/\/api\/session\/compact$/.test(vus[0][0]), "route déclarée : " + vus[0][0]);
  assert.deepStrictEqual(JSON.parse(vus[0][1]), { rm_id: "42" }, "le front demande « compacte », il n'envoie pas la commande");
  assert.ok(/\/compact/.test(msg) && /42/.test(msg), "le message dit ce qui a été tapé, et où");
  console.log("✓ compaction (RM3249) : le geste part sur /api/session/compact avec le seul rm_id");
}
console.log("\nTous les tests du bouton compacter passent.");
