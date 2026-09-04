#!/usr/bin/env node
// Tests des modules core/ du cockpit (RM2889, lot L0) — sans navigateur.
//
// Le test le plus important est le premier : il compare le module DÉPLACÉ à la
// fonction restée dans index.html, sur un jeu d'entrées piégeuses. Tant que la
// cohabitation dure, les deux DOIVENT rendre le même octet — c'est ce qui
// garantit qu'un déplacement n'est pas une réécriture déguisée (§ 15.7).
//
// Lancer : node deploy/karl-agent/cockpit/test_cockpit_core.js
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const vm = require("vm");

const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");

// Extrait une fonction de premier niveau en équilibrant ses accolades : la
// forme d'écriture (une ligne ou vingt) ne doit pas décider du test.
function fromIndex(name) {
  const start = html.search(new RegExp(`^function ${name}\\(`, "m"));
  assert(start >= 0, `${name} introuvable dans index.html`);
  let depth = 0, seen = false, end = start;
  for (let i = start; i < html.length; i++) {
    const c = html[i];
    if (c === "{") { depth++; seen = true; }
    else if (c === "}") { depth--; if (seen && depth === 0) { end = i + 1; break; } }
  }
  return vm.runInNewContext("(" + html.slice(start, end) + ")");
}
function fromIndexSource(name) {
  const start = html.search(new RegExp(`^function ${name}\\(`, "m"));
  assert(start >= 0, `${name} introuvable dans index.html`);
  let depth = 0, seen = false, end = start;
  for (let i = start; i < html.length; i++) {
    const c = html[i];
    if (c === "{") { depth++; seen = true; }
    else if (c === "}") { depth--; if (seen && depth === 0) { end = i + 1; break; } }
  }
  return html.slice(start, end);
}

const CAS = ["", null, undefined, "simple", "<b>gras</b>", 'guillemet "double"',
  "apostrophe 'simple'", "antislash \\ et \\\\", "& esperluette", "a<b>&\"'c\\d",
  "accentué : é à ù ç", "émoji 🙂", 0, 42, "  espaces  ", "<script>alert(1)</script>"];

// Document minimal — le cockpit ne dépend d'aucun paquet (C1) et ses tests
// tournent sous node nu (C5) : on fournit juste ce que core/dom.js utilise.
function fakeElement() {
  const listeners = [];
  return {
    innerHTML: "",
    contains: () => true,
    addEventListener(type, fn) { listeners.push([type, fn]); },
    removeEventListener(type, fn) {
      const i = listeners.findIndex(([t, f]) => t === type && f === fn);
      if (i >= 0) listeners.splice(i, 1);
    },
    get listenerCount() { return listeners.length; },
    dispatch(type, target) {
      for (const [t, fn] of [...listeners]) if (t === type) fn({ type, target });
    },
  };
}

(async () => {
  const H = await import(path.join(DIR, "src/core/html.js"));
  const E = await import(path.join(DIR, "src/core/endpoints.js"));

  // — 1. le déplacement n'a rien changé —
  for (const name of ["esc", "jarg"]) {
    const legacy = fromIndex(name);
    for (const v of CAS) {
      assert.strictEqual(H[name](v), legacy(v),
        `${name}(${JSON.stringify(v)}) diverge entre index.html et core/html.js`);
    }
  }
  console.log(`✓ esc et jarg identiques à index.html sur ${CAS.length} cas`);

  // — 2. jarg protège bien un handler inline en guillemets doubles —
  //      (le piège documenté : JSON.stringify refermerait l'attribut)
  const arg = H.jarg('il a dit "bonjour" et c\'est tout');
  assert(!arg.slice(1, -1).includes('"'), "jarg laisse passer un guillemet double");
  assert(arg.startsWith("'") && arg.endsWith("'"), "jarg doit rendre des simples");
  console.log("✓ jarg ne peut pas refermer un attribut HTML");

  // — 3. html : échappe par défaut, raw() seul fait exception —
  assert.strictEqual(String(H.html`<p>${"<b>"}</p>`), "<p>&lt;b&gt;</p>");
  assert.strictEqual(String(H.html`${H.raw("<i>ok</i>")}`), "<i>ok</i>");
  assert.strictEqual(String(H.html`${null}${undefined}${false}`), "");
  assert.strictEqual(String(H.html`${[1, 2]}`), "12");
  assert.strictEqual(String(H.html`${[H.html`<li>${"<x>"}</li>`]}`), "<li>&lt;x&gt;</li>");
  assert(H.isSafe(H.html`x`) && H.isSafe(H.raw("x")) && !H.isSafe("x"));
  console.log("✓ html : échappement par défaut, raw() et tableaux");

  // — 4. attrs : omission des valeurs vides, échappement des valeurs —
  assert.strictEqual(String(H.attrs({ id: "a", hidden: true, x: null, y: false })), 'id="a" hidden');
  assert.strictEqual(String(H.attrs({ t: 'a"b' })), 't="a&quot;b"');
  console.log("✓ attrs : omission et échappement");

  // — 5. endpoints : la table couvre la carte, et reste injective —
  const tsv = fs.readFileSync(path.join(DIR, "MIGRATION-ROUTES.tsv"), "utf8")
    .trim().split("\n").slice(1).map(l => l.split("\t"));
  const currents = new Set(Object.values(E.ROUTES).map(r => r.current));
  for (const [cur] of tsv) {
    assert(currents.has(cur), `route ${cur} absente de core/endpoints.js`);
  }
  assert.strictEqual(Object.keys(E.ROUTES).length, tsv.length,
    "endpoints.js et MIGRATION-ROUTES.tsv ont divergé — régénérer");
  assert.strictEqual(E.route("auth.login"), "/auth/login");
  assert.strictEqual(E.targetRoute("auth.login"), "/api/auth/login");
  assert.throws(() => E.route("nexistepas"), /route inconnue/);
  console.log(`✓ endpoints : ${tsv.length} routes, nommage injectif`);

  // — 6. store : LRU borné, péremption, abonnement rendu —
  const S = await import(path.join(DIR, "src/core/store.js"));
  const st = new S.Store("test", { ttl: 10000, max: 2 });
  st.set("a", 1); st.set("b", 2); st.get("a"); st.set("c", 3);
  assert.strictEqual(st.get("b"), undefined, "b aurait dû être évincé (LRU)");
  assert.strictEqual(st.get("a"), 1, "a, relu récemment, devait survivre");
  assert.strictEqual(st.stats().evictions, 1);
  const perime = new S.Store("perime", { ttl: -1 });
  perime.set("k", "v");
  assert.strictEqual(perime.get("k"), undefined, "une entrée périmée doit être invisible");
  assert.strictEqual(perime.stats().stale, 1);
  let vus = 0;
  const off = st.subscribe(() => vus++);
  st.set("d", 4);
  assert.strictEqual(vus, 1, "l'abonné doit être notifié");
  off();
  st.set("e", 5);
  assert.strictEqual(vus, 1, "un abonné désabonné ne doit plus rien recevoir");
  assert.strictEqual(st.stats().subscribers, 0);
  assert.throws(() => new S.Store("x", { max: 0 }), /max doit être/);
  console.log("✓ store : LRU borné, péremption, désabonnement effectif");

  // — 7. LA garde du chantier : un unmount() libère tout ce que mount() a créé —
  const D = await import(path.join(DIR, "src/core/dom.js"));
  const el = fakeElement();
  const store = new S.Store("monté", {});
  let clics = 0;
  const h = D.mount(el, "<button class=\"go\">ok</button>", {
    events: [["click", ".go", () => clics++]],
  });
  h.track(store.subscribe(() => {}));
  h.timer(() => {}, 1000);
  assert.strictEqual(el.listenerCount, 1, "un seul écouteur délégué, pas un par élément");
  el.dispatch("click", { closest: () => ({}) });
  assert.strictEqual(clics, 1, "le geste délégué doit atteindre le handler");
  assert.strictEqual(store.stats().subscribers, 1);
  assert.strictEqual(D.domStats().mounted, 1);

  h.unmount();
  assert.strictEqual(el.listenerCount, 0, "unmount doit retirer les écouteurs");
  assert.strictEqual(store.stats().subscribers, 0, "unmount doit rendre les abonnements");
  assert.strictEqual(el.innerHTML, "", "unmount doit vider l'hôte");
  assert.strictEqual(D.domStats().mounted, 0, "unmount doit sortir du registre");
  assert.strictEqual(h.pending, 0, "aucune libération ne doit rester en attente");
  el.dispatch("click", { closest: () => ({}) });
  assert.strictEqual(clics, 1, "un composant démonté ne doit plus réagir");
  console.log("✓ cycle de vie : unmount() libère écouteurs, abonnements et minuteries");

  // — 8. la coquille de cohabitation est réellement branchée —
  assert(/<script type="module" src="\/static\/src\/boot\.js"><\/script>/.test(html),
    "index.html ne charge plus le socle modulaire");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  for (const [, rel] of boot.matchAll(/from "(\.[^"]+)"/g)) {
    assert(fs.existsSync(path.join(DIR, "src", rel.replace(/^\.\//, ""))),
      `boot.js importe ${rel}, qui n'existe pas`);
  }
  // le pont est temporaire : il ne doit rien exposer qu'un module ne fournisse
  assert(boot.includes("window.karl"), "le pont de cohabitation a disparu de boot.js");
  console.log("✓ coquille : index.html charge le socle, imports de boot.js résolus");

  // — 9. api : comportement identique à index.html, erreurs à quatre champs —
  const A = await import(path.join(DIR, "src/core/api.js"));
  const ER = await import(path.join(DIR, "src/core/errors.js"));
  const legacyHeaders = vm.runInNewContext(
    "(" + fromIndexSource("headers") + ")", { CFG: { auth_required: true }, token: () => "T" });
  A.configureApi({ authRequired: true, token: () => "T" });
  assert.deepStrictEqual(A.headers({ a: "1" }), { ...legacyHeaders({ a: "1" }) },  // autre realm vm
    "headers() diverge entre index.html et core/api.js");
  const fakeFetch = (status, body, ct = "application/json") => async () => ({
    ok: status < 400, status, statusText: "ST",
    headers: { get: () => ct }, json: async () => body, text: async () => String(body),
  });
  A.configureApi({ fetch: fakeFetch(200, { ok: 1 }) });
  assert.deepStrictEqual(await A.api("/x"), { ok: 1 });
  A.configureApi({ fetch: fakeFetch(200, "brut", "text/plain") });
  assert.strictEqual(await A.api("/x"), "brut", "un corps texte doit rester texte");
  let unauthorized = 0;
  A.configureApi({ fetch: fakeFetch(401, { error: "jeton révoqué" }), onUnauthorized: () => unauthorized++ });
  await assert.rejects(A.api("/x"), e => e instanceof ER.ApiError && e.status === 401
    && e.message === "jeton révoqué" && e.code === "http.401");
  assert.strictEqual(unauthorized, 1, "un 401 doit rappeler l'écran de login");
  A.configureApi({ fetch: fakeFetch(500, "", "text/plain") });
  await assert.rejects(A.api("/x"), /500 ST/);
  A.configureApi({ fetch: fakeFetch(422, { code: "ticket.invalide", error: "titre vide", remedy: "renseigner un titre" }) });
  await assert.rejects(A.api("/x"), e => e.code === "ticket.invalide" && e.remedy === "renseigner un titre");
  const norm = ER.asAppError(new Error("boum"));
  assert(norm instanceof ER.AppError && norm.code === "unknown" && norm.cause);
  assert.deepStrictEqual(Object.keys(norm.toJSON()), ["code", "message", "detail", "remedy"]);
  console.log("✓ api : headers identiques, corps json/texte, 401, erreurs à quatre champs");

  // — 10. modèle : factory qui garantit l'invariant, repository qui cache —
  const F = await import(path.join(DIR, "src/models/Factory.js"));
  const RP = await import(path.join(DIR, "src/models/Repository.js"));
  const f = new F.Factory({ type: "ticket", required: ["id"], defaults: { tags: [] }, coerce: { id: Number } });
  const e1 = f.one({ id: "12", title: "t" });
  assert.strictEqual(e1.id, 12); assert.deepStrictEqual(e1.tags, []); assert.strictEqual(e1.type, "ticket");
  assert(Object.isFrozen(e1), "une entité est immuable");
  assert.throws(() => f.one({ title: "sans id" }), /champs manquants id/);
  assert.strictEqual(f.many({ items: [{ id: 1 }, { id: 2 }] }).length, 2);
  let appels = 0;
  A.configureApi({ fetch: async (p) => { appels++; return (await fakeFetch(200, { id: 7, title: p })()); } });
  const repo = new RP.Repository({ name: "ticket-test", factory: f, routes: { one: "auth.login", list: "auth.users" } });
  const t1 = await repo.one(7); const t2 = await repo.one(7);
  assert.strictEqual(t1, t2, "la 2e lecture doit venir du cache");
  assert.strictEqual(appels, 1);
  assert.throws(() => repo.path("nexiste"), /non déclarée/);
  console.log("✓ modèle : factory (invariants, défauts, coercition), repository (cache, routes nommées)");

  // — 11. ViewModel : inerte, testable sans réseau, héritage plat —
  const V = await import(path.join(DIR, "src/viewmodels/EntityViewModel.js"));
  class TicketVM extends V.withConso(V.EntityViewModel) {
    get badges() { return [...super.badges, this.e.priority]; }
    sections() { return [{ id: "resume", title: "résumé", summary: true }, this.consoSection()]; }
  }
  const vm2 = new TicketVM(f.one({ id: 3, title: "T", state: "en_cours", priority: "high" }), { user: "m" });
  assert.deepStrictEqual(vm2.badges, ["en_cours", "high"]);
  assert.deepStrictEqual(vm2.summary().map(s => s.id), ["resume"]);
  assert.strictEqual(vm2.user, "m"); assert.deepStrictEqual(vm2.actions(), []);
  assert.strictEqual(vm2.conso.tokens, 0);
  assert.throws(() => new V.EntityViewModel(null), /exige une entité/);
  console.log("✓ ViewModel : présente sans réseau, mixin withConso, contexte injecté");

  // — 12. garde d'imports entre couches (§ 7.3) : ce qu'une couche n'a PAS le droit de voir —
  const FORBIDDEN = {
    views:       [/core\/api\.js/, /services\//, /models\//],       // une vue rend, elle ne charge rien
    viewmodels:  [/core\/api\.js/, /core\/dom\.js/, /services\//],   // inerte : ni réseau ni DOM
    models:      [/core\/dom\.js/, /views\//, /controllers\//],      // jamais de DOM
    services:    [/core\/dom\.js/, /views\//, /controllers\//],      // aucun balisage
    components:  [/core\/api\.js/, /services\//, /models\//],
    controllers: [/core\/api\.js/],                                  // aucun appel réseau direct
  };
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap(x =>
    x.isDirectory() ? walk(path.join(d, x.name)) : (x.name.endsWith(".js") ? [path.join(d, x.name)] : []));
  let verifies = 0;
  for (const [layer, bans] of Object.entries(FORBIDDEN)) {
    const dir = path.join(DIR, "src", layer);
    if (!fs.existsSync(dir)) continue;
    for (const file of walk(dir)) {
      const src = fs.readFileSync(file, "utf8");
      for (const [, spec] of src.matchAll(/^import .* from "([^"]+)"/gm)) {
        for (const ban of bans) assert(!ban.test(spec),
          `${path.relative(DIR, file)} importe ${spec} — interdit à la couche ${layer}`);
        verifies++;
      }
    }
  }
  console.log(`✓ gardes d'imports : ${verifies} import(s) vérifié(s) sur 6 couches`);

  console.log("\nTous les tests core/ passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
