#!/usr/bin/env node
// Tests du registre des types d'entités (RM3002) — core/entities : types, icônes, infobulles, libellés d'onglet, recettes d'ouverture par l'api
// du centre, références cliquables ; les QUATRE NIVEAUX (row/card/panel/full) composés depuis sections() pour chaque type lié
// (session, review, project, mail, file, dir, client) ; la convention CSS unique ; et la garde « zéro kind === hors registre ».
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
(async () => {
  const E = await import(path.join(DIR, "src/core/entities.js"));
  const H = await import(path.join(DIR, "src/core/html.js"));
  const K = await import(path.join(DIR, "src/modules/center/viewKey.js"));
  // les modules lient leurs ViewModels au registre à l'import
  const SV = await import(path.join(DIR, "src/modules/sessions/SessionsViewModel.js"));
  const RV = await import(path.join(DIR, "src/modules/review/ReviewViewModel.js"));
  const PV = await import(path.join(DIR, "src/modules/projects/ProjectViewModels.js"));
  const CV = await import(path.join(DIR, "src/modules/center/CenterViewModels.js"));

  // — registre —
  const types = E.entityTypes();
  assert.deepStrictEqual(types, ["dash", "session", "review", "project", "newticket", "client", "conf", "file", "dir", "commit", "mail", "pm", "settings", "journal", "memory", "cdc-features", "cdc", "cdc-roadmap"], "les types du cockpit, dans l'ordre de déclaration");
  assert(E.entity("review").icon === "🧪" && E.iconOf("memory") === "🧠" && E.iconOf("inconnu") === "•" && !E.isEntity("inconnu") && E.entity("inconnu").type === "inconnu");
  assert.deepStrictEqual(E.surfaceTypes(), ["session", "review", "project", "newticket"]); assert.deepStrictEqual(E.panelTypes(), ["pm", "settings", "journal", "memory", "cdc-features", "cdc", "cdc-roadmap"]);
  assert(E.entity("dash").fixed && !E.entity("session").restorable && E.entity("review").restorable && E.entity("newticket").closeLast && !E.entity("session").closeLast);
  assert.strictEqual(E.entity("commit").errorTitle, "Commit indisponible"); assert.strictEqual(E.entity("file").errorTitle, "Contenu indisponible");
  const RC = { 42: { found: true, title: "Sujet" } }, parse = K.parseViewKey;
  assert.strictEqual(E.tooltipOf({ kind: "review", key: "42" }, RC, parse), "RM42 — Sujet"); assert.strictEqual(E.tooltipOf({ kind: "session", key: "calymix" }, RC, parse), "session calymix");
  assert.strictEqual(E.tooltipOf({ kind: "conf", key: K.viewKey(["project", "acme", "shop"]) }, {}, parse), "configuration — acme/shop"); assert.strictEqual(E.tooltipOf({}, {}, parse), ""); assert.strictEqual(E.tooltipOf({ kind: "zz", key: "k", label: "L" }, {}, parse), "L");
  assert.strictEqual(E.tabLabelOf("file", ["wt", "/w", "a/b/c.md"]), "c.md"); assert.strictEqual(E.tabLabelOf("dir", ["wt", "/w", ""]), "racine/"); assert.strictEqual(E.tabLabelOf("commit", ["1", "abcdef1234"]), "abcdef12"); assert.strictEqual(E.tabLabelOf("mail", ["k"], "x".repeat(40)).length, 30); assert.strictEqual(E.tabLabelOf("zz", [], "vue libre"), "vue libre");
  // recettes d'ouverture : chaque type parle à l'api du centre, jamais au DOM
  const calls = []; const api = new Proxy({}, { get: (_, k) => (...a) => { calls.push([k, ...a]); return k; } });
  E.entity("session").open(api, { key: "7" }, []); E.entity("review").open(api, { key: "42" }, []); E.entity("file").open(api, { key: "" }, ["wt", "/w", "p", "t"]); E.entity("mail").open(api, { key: "k", label: "Objet" }, ["k"]); E.entity("journal").open(api, {}, []); E.entity("dash").open(api, {}, []); E.entity("conf").open(api, {}, ["project", "a", "b"]);
  assert.deepStrictEqual(calls, [["openSessionTab", "7"], ["surface", "review", "open", "42"], ["openFile", "wt", "/w", "p", "t"], ["openMail", "k", "Objet"], ["openPanel", "journal"], ["openDashboard"], ["openConf", "project", "a", "b"]], JSON.stringify(calls));
  assert.strictEqual(E.entity("zz").open, null, "un type inconnu n'a pas de recette : le centre ne fait rien");
  const lk = []; E.linkAction("ticket")({ showTicket: (rm) => lk.push(["t", rm]) }, { dataset: { rm: "5" } }); E.linkAction("file")({ openFileRef: (p) => lk.push(["f", p]) }, { dataset: { path: "a.md" } }); E.linkAction("ext")({}, {}); assert.deepStrictEqual(lk, [["t", "5"], ["f", "a.md"]]); assert.strictEqual(E.linkAction("zz"), null);
  console.log("✓ registre : types, icônes, infobulles, libellés, recettes d'ouverture par l'api, références cliquables");

  // — les quatre niveaux —
  class DemoVM { constructor(e) { this.e = e; } get id() { return this.e.id; } get type() { return "review"; } get title() { return this.e.title; } get badges() { return [{ text: "ok", cls: "ok" }, "brut"]; } get subtitle() { return "acme/shop"; }
    sections() { return [{ id: "a", title: "A", summary: true, body: [["clé", "valeur <x>"]] }, { id: "b", title: "B", body: () => ["l1", "l2"] }, { id: "c", title: "C", level: "full", body: H.html`<pre>c</pre>` }, { id: "d", title: "D", body: null, empty: "rien" }]; } }
  const vm = new DemoVM({ id: "42", title: "T <b>" });
  assert.deepStrictEqual(E.sectionsAt(vm, "row").map(s => s.id), []); assert.deepStrictEqual(E.sectionsAt(vm, "card").map(s => s.id), ["a"]); assert.deepStrictEqual(E.sectionsAt(vm, "panel").map(s => s.id), ["a", "b", "d"]); assert.deepStrictEqual(E.sectionsAt(vm, "full").map(s => s.id), ["a", "b", "c", "d"]);
  assert.throws(() => E.sectionsAt(vm, "géant"), /niveau inconnu/);
  const row = String(E.renderEntity(vm, "row")); assert(/class="e-entity e-row" data-type="review" data-id="42"/.test(row) && /e-icon">🧪</.test(row) && /e-title">T &lt;b&gt;</.test(row) && /e-sub">acme\/shop</.test(row) && /e-badge ok"/.test(row) && /e-badge">brut</.test(row) && !/e-sec/.test(row), row);
  const card = String(E.renderEntity(vm, "card")); assert(/e-card/.test(card) && /data-sec="a"/.test(card) && /e-k">clé<\/span><span class="e-v">valeur &lt;x&gt;</.test(card) && !/data-sec="b"/.test(card), card);
  const panel = String(E.renderEntity(vm, "panel")); assert(/data-sec="b"/.test(panel) && /e-line">l1</.test(panel) && /data-sec="d"/.test(panel) && /e-empty">rien</.test(panel) && !/data-sec="c"/.test(panel));
  const full = String(E.renderEntity(vm, "full", { attrs: H.attrs({ "data-action": "open" }), icon: "★" })); assert(/data-sec="c"/.test(full) && /<pre>c<\/pre>/.test(full) && /data-action="open"/.test(full) && /e-icon">★</.test(full) && !/\son[a-z]+=/.test(full));
  console.log("✓ niveaux : row/card/panel/full composés depuis sections(), corps clé/valeur, listes, fragments, vides, échappement");

  // — chaque type lié expose ses quatre niveaux depuis une fixture —
  const now = Date.now();
  const FIX = {
    session: () => new SV.SessionTileViewModel({ rm_id: "7", state: "attention", client: "acme", project: "shop", engine: "claude", created: now - 60000 }, { resolved: { found: true, title: "Sujet 7", status: "en_cours", client: "acme", project: "shop" }, attached: null }),
    review:  () => new RV.ReviewViewModel({ r: { found: true, title: "Titre", client: "acme", project: "shop", status: "a_tester_demandeur", priority: "high", tags: ["front"], redmine_url: "https://r/1", test_protocol: { text: "1. ouvrir", source: "cf" }, description: "# desc", log_tail: "## x", environments: [{ name: "prod", url: "https://p" }], test_url: "https://t" }, q: null, tqLoaded: true, tqSize: 1, cfg: {} }, { rm: "42" }),
    project: () => new PV.ProjectSheetViewModel({ name: "Appli", redmine_project_url: "https://rp", open_by_status: { en_cours: 1, a_faire: 2 }, environments: [{ name: "prod", url: "https://p" }], docs: [{ path: "/pm/x.md", name: "x.md" }], open_recent: [{ rm_id: "5", status: "en_cours", title: "t5" }] }, { key: "acme/shop" }),
    mail:    () => new CV.EmailViewModel({ subject: "Devis", from: "a@b", from_name: "A", date: "2026-09-07", state: "à traiter", body: "Bonjour <b>", attachment_list: [] }),
    file:    () => new CV.FileViewModel({ path: "src/a.md", markdown: true, content: "# x", size: 2048 }, { md: (s) => "<md>" + s + "</md>" }),
    dir:     () => new CV.DirViewModel({ src: "wt", wt: "/w", path: "src", entries: [{ name: "a.js" }, { name: "sub", dir: true }] }),
    client:  () => new CV.ClientViewModel({ client: "acme", name: "ACME", status: "actif", contacts: [{ first_name: "A", last_name: "B", email: "a@b" }], projects: [{ project: "shop" }] }),
  };
  for (const t of Object.keys(FIX)) {
    assert(E.entity(t).ViewModel, t + " : ViewModel lié au registre");
    const v = FIX[t](); assert.strictEqual(v.type, t, t + " : type du ViewModel");
    for (const l of E.LEVELS) { const s = String(E.renderEntity(v, l)); assert(new RegExp('class="e-entity e-' + l + '" data-type="' + t + '"').test(s) && /e-title">[^<]+</.test(s), t + "/" + l + " : " + s.slice(0, 160)); }
    assert(String(E.renderEntity(v, "card")).includes("e-sec"), t + " : la carte porte au moins une section résumée");
    const nsec = (l) => (String(E.renderEntity(v, l)).match(/data-sec=/g) || []).length; assert(nsec("row") === 0 && nsec("card") <= nsec("panel") && nsec("panel") <= nsec("full"), t + " : les niveaux s'emboîtent");
  }
  const rv = String(E.renderEntity(FIX.review(), "full")); assert(/e-badge accent"[^>]*>a_tester_demandeur</.test(rv) && /e-badge warn"[^>]*>high</.test(rv) && /Redmine ↗/.test(rv) && /1\. ouvrir/.test(rv) && /# desc/.test(rv), "revue : pastilles, liens, protocole, description");
  const sv = String(E.renderEntity(FIX.session(), "card")); assert(/e-title">Sujet 7</.test(sv) && /e-badge warn"[^>]*>attention</.test(sv) && /e-k">moteur<\/span><span class="e-v">claude</.test(sv), sv);
  const mv = String(E.renderEntity(FIX.mail(), "full")); assert(/Bonjour &lt;b&gt;/.test(mv) && !/Bonjour <b>/.test(mv), "corps d'email échappé");
  const fv = String(E.renderEntity(FIX.file(), "card")); assert(/<md># x<\/md>/.test(fv) && /e-sub">2 Ko</.test(fv));
  assert(/aucun contact/.test(String(E.renderEntity(new CV.ClientViewModel({ client: "x" }), "panel"))), "section vide nommée");
  const L = E.entityLevels("client", { client: "acme", name: "ACME" }); assert(Object.keys(L).join() === "row,card,panel,full" && /e-full/.test(String(L.full))); assert.throws(() => E.entityLevels("conf", {}), /aucun ViewModel/);
  console.log("✓ types liés : session, review, project, mail, file, dir, client — quatre niveaux emboîtés depuis une fixture");

  // — convention CSS unique : les classes e-* vivent dans styles/_entities.scss, par niveau, jamais par type —
  const ent = fs.readFileSync(path.join(DIR, "src/styles/_entities.scss"), "utf8");
  for (const l of E.LEVELS) assert(new RegExp("\\.e-" + l + "\\b").test(ent), "niveau stylé : " + l);
  for (const t of types) assert(!new RegExp("\\.e-" + t + "\\b").test(ent), "aucune règle par type : .e-" + t);
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap(x => x.isDirectory() ? walk(path.join(d, x.name)) : [path.join(d, x.name)]);
  for (const f of walk(path.join(DIR, "src")).filter(f => f.endsWith(".scss") && !f.endsWith("_entities.scss"))) assert(!/\.e-(entity|row|card|panel|full|head|icon|title|sub|badges?|sec|kv|line|empty)\b/.test(fs.readFileSync(f, "utf8")), path.relative(DIR, f) + " : redéfinit une classe e-*");
  assert(/\.e-row\b/.test(fs.readFileSync(path.join(DIR, "cockpit.css"), "utf8")), "compilé");
  // — garde : zéro `kind === "<type>"` / `case "<type>":` hors du registre —
  const offenders = [];
  const rx = new RegExp("(kind\\s*[!=]==\\s*\"(" + types.join("|") + ")\"|case\\s+\"(" + types.join("|") + ")\"\\s*:)");
  for (const f of walk(path.join(DIR, "src")).filter(f => f.endsWith(".js") && !f.endsWith(path.join("core", "entities.js")))) {
    const code = fs.readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n");
    if (rx.test(code)) offenders.push(path.relative(DIR, f));
  }
  assert.deepStrictEqual(offenders, [], "dispatch par type hors du registre : " + offenders.join(", "));
  const cc = fs.readFileSync(path.join(DIR, "src/modules/center/center.controller.js"), "utf8"); assert(/def\.open\(api, t, parseViewKey\(t\.key\)\)/.test(cc) && /surfaceTypes\(\)/.test(cc) && /entity\(kind\)\.errorTitle/.test(cc) && /entity\(t0\.kind\)\.restorable/.test(cc), "le centre lit le registre");
  console.log("✓ convention CSS par niveau, aucune classe par type ; zéro dispatch par type hors core/entities.js");
  console.log("\nTous les tests du registre d'entités passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
