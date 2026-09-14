#!/usr/bin/env node
// Tests du domaine worklog — MODÈLE (RM3019, scindé de test_cockpit_worklog.js) : décors RM2466, sections/onglets/documents, groupes RM2798,
// étape de MR RM2801, dérive RM2796, avancement RM2695, branches RM2591, lots RM2786/2720/2823/2719.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { settle, escO, fakeElement, CFG, SEL, W } = require("./test_cockpit_worklog.helpers.js");
(async () => {
  const M = await import(path.join(DIR, "src/modules/worklog/worklog.js"));

  // — RM2466 : décors —
  const dLive = M.pendingDecor({ kind: "live", state: "attention" }), dChoice = M.pendingDecor({ kind: "live", state: "choice" }), dStale = M.pendingDecor({ kind: "stale" });
  assert(dLive.cls.includes("ounres") && !dStale.cls.includes("ounres") && dLive.icon !== dStale.icon && dLive.tag !== dStale.tag && dChoice.icon !== dLive.icon && /bloqu/i.test(dLive.tag) && /sans réponse/i.test(dStale.tag) && M.pendingDecor(null).tag && M.pendingDecor(undefined).icon);
  const nc = M.notifyDecor("critical"), nw = M.notifyDecor("warn"), ni = M.notifyDecor("info"); assert(nc.icon !== nw.icon && nw.icon !== ni.icon && nc.label === "critical" && nw.label === "warn" && ni.label === "info" && nc.cls.includes("ounres") && !ni.cls.includes("ounres")); assert.strictEqual(M.notifyDecor(undefined).label, "warn");
  // — sections, onglets, documents —
  assert.deepStrictEqual(M.worklogSections({ todo: [{ ref: "RM1" }], waiting: [{ ref: "RM2" }], done: [{ ref: "RM3" }] }).map(s => s.key), ["todo", "waiting", "done"]);
  assert.deepStrictEqual(M.worklogSections({ todo: [{ ref: "RM1" }], mep: [{ ref: "RM2" }, { ref: "RM3" }], done: [{ ref: "RM4" }] }).map(s => s.key), ["todo", "mep", "done"], "RM2860 : MEP entre à faire et fait");
  assert.deepStrictEqual(M.worklogSections({ todo: [{ ref: "RM1" }], testing: [{ ref: "RM2" }], mep: [{ ref: "RM4" }], waiting: [{ ref: "RM5" }], done: [{ ref: "RM6" }] }).map(s => s.key), ["todo", "testing", "mep", "waiting", "done"], "RM2930 : à tester avant la MEP");
  assert.strictEqual(M.worklogSections({ mep: [] }).length, 0); assert.strictEqual(M.worklogSections({ todo: [], waiting: [{ ref: "RM2" }], done: [] }).length, 1); assert.strictEqual(M.worklogSections(null).length, 0); assert(M.worklogSections({ todo: [{}] }).every(s => s.icon && s.label));
  const secs2 = [{ key: "todo", icon: "⏳", label: "reste à faire", items: [1, 2] }, { key: "done", icon: "✅", label: "fait", items: [1] }];
  assert.deepStrictEqual(M.worklogTabList(secs2, 3, 0).map(t => [t.key, t.n]), [["todo", 2], ["done", 1], ["documents", 3]]); assert.strictEqual(M.worklogTabList([], 0, 0).length, 0); assert.strictEqual(M.worklogTabList([], 2, 0)[0].key, "documents"); assert.strictEqual(M.worklogTabList([{ key: "done", icon: "x", label: "fait", items: [1] }], 0, 2)[0].key, "todo", "RM2610 : orphelines → onglet à faire");
  const wd = M.worklogDocs({ RM1: [["a.py", "output"], ["b.md", "output"]], RM2: [["c", ""]] }); assert.strictEqual(wd.length, 3); assert.deepStrictEqual(wd[0], { ref: "RM1", name: "a.py", kind: "output" }); assert.strictEqual(M.worklogDocs({ RM3: ["str-seul"] })[0].name, "str-seul"); assert.strictEqual(M.worklogDocs(null).length, 0);
  // — RM2798 groupes, RM2801 étape, RM2796 dérive, RM2695 avancement, RM2591 branches —
  const WL = [{ ref: "RM1", client: "calicote", project: "presta" }, { ref: "RM2", client: "abatik", project: "infra" }, { ref: "RM3", client: "calicote", project: "presta" }, { ref: "RM4" }];
  const g = M.groupWorklogItems(WL); assert.deepEqual(g.map(x => x.key), ["calicote / presta", "abatik / infra", "hors projet"]); assert.deepEqual(g[0].items.map(i => i.ref), ["RM1", "RM3"]); assert.strictEqual(M.groupWorklogItems([{ ref: "A", project: "infra" }])[0].key, "infra"); assert.strictEqual(M.groupWorklogItems([{ ref: "A", client: "abatik" }])[0].key, "abatik"); assert.deepEqual(M.groupWorklogItems(null), []);
  assert.strictEqual(M.mrStage(null), null); assert.strictEqual(M.mrStage({}), null); assert.strictEqual(M.mrStage({ stage: "inconnue" }), null);
  const ouv = M.mrStage({ stage: "open", url: "https://g/mr/1", count: 1, mrs: [{ iid: "1", state: "opened", target: "dev" }] }); assert(ouv.txt === "⇥ MR" && ouv.cls === "warn" && /à merger/.test(ouv.tip) && ouv.url === "https://g/mr/1"); const integ = M.mrStage({ stage: "integration", url: "u", count: 1, mrs: [] }); assert(integ.txt === "✓ dev" && integ.cls === "ok" && /par lot \(dev → main\)/.test(integ.tip)); assert.strictEqual(M.mrStage({ stage: "prod", url: "u", count: 1, mrs: [] }).txt, "✓ prod");
  const multi = M.mrStage({ stage: "prod", url: "u", count: 2, mrs: [{ iid: "1", state: "merged", target: "dev", repo: "a/b" }, { iid: "2", state: "merged", target: "main" }] }); assert(/!1 merged → dev \(a\/b\)/.test(multi.tip) && /!2 merged → main/.test(multi.tip) && /2 MR/.test(multi.tip));
  assert.deepStrictEqual(M.statusInfo({ status: "en_cours" }), { status: "en_cours", drifted: false, tip: "" }); const der = M.statusInfo({ status: "a_tester_demandeur", opened_status: "en_cours", drifted: true }); assert(der.drifted && /en_cours → a_tester_demandeur/.test(der.tip)); assert(!M.statusInfo({ status: "en_cours", opened_status: "en_cours", drifted: true }).drifted); assert(!M.statusInfo({ status: "a_faire", drifted: true }).drifted); assert.strictEqual(M.statusInfo({}).status, "?"); assert.strictEqual(M.statusInfo(null).status, "?");
  assert.strictEqual(M.worklogProgress({ ref: "RM1", status: "en_cours" }), null, "sans checklist : rien, jamais 0/0"); assert.strictEqual(M.worklogProgress(null), null); assert.strictEqual(M.worklogProgress({ checklist: { done: 0, total: 0, items: [] } }), null);
  const wp = M.worklogProgress({ checklist: { done: 3, total: 6, items: ["reste A", "reste B"] } }); assert(wp.check.done === 3 && wp.check.total === 6 && wp.check.cls === "" && wp.check.items.length === 2); assert.strictEqual(M.worklogProgress({ checklist: { done: 6, total: 6, items: [] } }).check.cls, "ok"); assert.strictEqual(M.worklogProgress({ checklist: { done: 0, total: 4, items: ["a"] } }).check.cls, "warn"); assert(M.worklogProgress({ checklist: { done: 0, total: 60, items: ["a"], truncated: true } }).check.truncated);
  assert.deepStrictEqual(M.worklogProgress({ sub_tasks: [{ rm_id: "2696", status: "a_faire", title: "T2" }] }).subs, [{ rm: "2696", status: "a_faire", title: "T2" }]);
  assert.deepStrictEqual(M.branchesByRm(["2591-x", "2591-y", "sans", "7-z"]), { RM2591: ["2591-x", "2591-y"], RM7: ["7-z"] });
  console.log("✓ modèle (RM2466/2610/2584/2798/2801/2796/2695/2591) : décors, sections, onglets, documents, groupes, étape, dérive, avancement, branches");
  // — lots (RM2786/2720/2823/2719) —
  const nb = M.batchButtons(SEL, ["RM2"], CFG); assert.deepStrictEqual(nb, { traiter: 2, atester: 1, etudier: 1, fermer: 1, mr: 1 }); assert.strictEqual(M.batchButtons(SEL, [], CFG).mr, 0, "merger sans MR ne s'affiche pas"); assert.strictEqual(M.batchButtons([{ rm_id: "9", status: "a_tester_demandeur" }], [], CFG).traiter, 0); const inc = M.batchButtons([{ rm_id: "1", status: "zzz" }], [], CFG); assert(inc.traiter === 1 && inc.fermer === 1, "statut inconnu : compte partout"); assert.deepEqual(M.batchButtons([], [], CFG), { traiter: 0, atester: 0, etudier: 0, fermer: 0, mr: 0 }); assert.doesNotThrow(() => M.batchButtons(null, null, null));
  const pc = M.closeBatchPlan(SEL, CFG); assert(pc.count === 1 && pc.todo[0].rm_id === "3" && pc.skipped.length === 3 && pc.skipped.every(t => t.why) && /livré/.test(pc.skipped.find(t => t.rm_id === "4").why)); assert(M.closeBatchPlan([{ rm_id: "7", status: "zzz" }], CFG).skipped[0].why.includes("zzz"));
  assert(M.BATCH_MODES.atester && M.BATCH_MODES.traiter && M.BATCH_MODES.etudier && M.BATCH_MODES.atester.envoi !== M.BATCH_MODES.traiter.envoi && M.BATCH_MODES.atester.points === false && M.BATCH_MODES.etudier.points === false);
  const RC = { "10": { found: true, client: "acme", project: "boutique", cwd: "/w/acme/boutique" }, "11": { found: true, client: "acme", project: "boutique", cwd: "/w/acme/boutique" }, "20": { found: true, client: "beta", project: "api", cwd: "/w/beta/api" }, "30": { found: false } };
  const homo = M.offloadPlan([{ rm_id: "10" }, { rm_id: "11" }], RC); assert(!homo.mixed && homo.targets.map(t => t.rm_id).join(",") === "10,11" && homo.client === "acme" && homo.project === "boutique" && homo.cwd === "/w/acme/boutique" && homo.anchor === "10");
  const mel = M.offloadPlan([{ rm_id: "10" }, { rm_id: "20" }], RC); assert(mel.mixed && mel.projects.slice().sort().join(" ") === "acme/boutique beta/api"); const inco = M.offloadPlan([{ rm_id: "10" }, { rm_id: "30" }], RC); assert(inco.blocked.map(t => t.rm_id).join(",") === "30" && inco.targets.map(t => t.rm_id).join(",") === "10" && !inco.mixed); assert.strictEqual(M.offloadPlan([{ rm_id: "30" }], RC).anchor, null); assert.strictEqual(M.offloadPlan([{ rm_id: "RM10" }], RC).anchor, "10");
  const scoped = M.scopeItems([{ rm_id: "10", points: ["a", "b"] }, { rm_id: "11", points: ["c"] }], [{ ref: "10", value: "a", checked: true }, { ref: "10", value: "b", checked: false }, { ref: "11", value: "c", checked: true }]); assert.deepStrictEqual(scoped[0].scope, ["a"], "RM2719 : un point décoché restreint la portée"); assert.strictEqual(scoped[1].scope, undefined, "tous cochés = ticket entier");
  const lignes = M.spawnConfirmLines(homo, { engine: "claude", model: "opus" }, { titre: "Ouvrir une session sur ce lot", reste: "⊘ 2 au-delà" }); assert(/Ouvrir une session sur ce lot pour 2 ticket\(s\)/.test(lignes[0]) && lignes.includes("projet : acme / boutique") && lignes.includes("ancrage : RM10") && lignes.includes("moteur : claude  ·  modèle : opus") && lignes.includes("⊘ 2 au-delà"));
  console.log("✓ lots (RM2786/2720/2823/2719) : boutons selon la règle serveur, fermeture avec raisons, embarquement par projet, portée par points");
  // ── RM3174 : « déjà ticketé ? » — le geste doit RÉPONDRE, pas seulement exister ──────────────
  // Le premier jet appelait `this.api.get(...)` sur un service qui n'a pas d'`api` : la méthode
  // levait à sa première ligne, et le bouton n'a jamais pu fonctionner depuis sa livraison. Un test
  // qui ne lit que la forme du code ne voit pas ça — celui-ci APPELLE, et regarde l'URL demandée.
  {
    const A = await import(path.join(DIR, "src/core/api.js"));
    const { WorklogService } = await import(path.join(DIR, "src/modules/worklog/worklog.service.js"));
    const vus = [];
    A.configureApi({ fetch: async (p) => { vus.push(p);
      return { ok: true, status: 200, statusText: "", headers: { get: () => "application/json" },
               json: async () => ({ results: [{ rm_id: "3070", title: "sudo" }] }), text: async () => "" }; } });
    const svc = new WorklogService({});
    const r = await svc.anteriority("installer karl en mode sudo");
    assert.deepStrictEqual(r, [{ rm_id: "3070", title: "sudo" }], "l'antériorité répond");
    assert(/\/api\/ticket\/anteriority\?q=/.test(vus[0]), "…par la route déclarée : " + vus[0]);
    assert(/limit=6/.test(vus[0]), "…avec sa borne");
    assert.deepStrictEqual(await svc.anteriority("   "), [], "une recherche vide ne rend rien");
    assert.strictEqual(vus.length, 1, "…et ne part pas sur le réseau pour rien");
    const src = fs.readFileSync(path.join(DIR, "src/modules/worklog/worklog.service.js"), "utf8");
    // On cherche un USAGE, pas une mention : le commentaire qui explique le défaut cite `this.api`.
    assert(!/this\.api\s*\.\s*\w/.test(src), "RM3174 : l'accès réseau passe par le DÉPÔT, pas par le service");
    assert(/this\.repo\.anteriority\(/.test(src), "…et le service délègue au dépôt");
    console.log("✓ antériorité (RM3148/RM3174) : le geste répond, par la route déclarée, sans requête inutile");
  }

  console.log("\nTous les tests du modèle du worklog passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
