#!/usr/bin/env node
// Tests du domaine sessions — MODÈLE et SERVICE (RM3018, scindé de test_cockpit_sessions.js) : computeGroups (RM2140/2283/2427/2327/2537/2344),
// fonctions pures (RM2332, RM2515, RM2346, RM2639, RM2787/2793, RM2699, infobulles, plis, ordre, messages).
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { fakeEl, settle, now, SETS, writable, mkRepo } = require("./test_cockpit_sessions.helpers.js");
(async () => {
  const M = await import(path.join(DIR, "src/modules/sessions/sessions.js"));
  const VM = await import(path.join(DIR, "src/modules/sessions/SessionsViewModel.js"));
  const { esc } = await import(path.join(DIR, "src/core/html.js"));
  const { SessionsService } = await import(path.join(DIR, "src/modules/sessions/sessions.service.js"));
  const otherGrp = M.OTHER_SETS_GROUP;

  // — computeGroups : groupement (jonction directe, repli /resolve, divers), compteurs, tri —
  const sessions = [
    { rm_id: "1", client: "acme", project: "shop", state: "working", created: 100 },
    { rm_id: "2", client: "acme", project: "shop", state: "idle", created: 200 },
    { rm_id: "3", state: "attention", created: 50 },
    { rm_id: "4", is_ticket: false, state: "working", created: 300 },
  ];
  const rcache = { "3": { found: true, client: "beta", project: "api" } };
  const { keys, groups, counts } = M.computeGroups(sessions, rcache, true);
  assert.deepStrictEqual(new Set(keys), new Set(["acme/shop", "beta/api", "divers"]), "clés de groupes");
  assert.strictEqual(groups.get("acme/shop").length, 2); assert.strictEqual(groups.get("beta/api")[0].rm_id, "3", "repli resolveCache"); assert.strictEqual(groups.get("divers")[0].rm_id, "4", "non résolu → divers");
  assert.deepStrictEqual({ ...counts }, { total: 4, attention: 1, choice: 0, idle: 1, working: 2, ghost: 0 }, "compteurs");
  const gh = M.computeGroups([{ rm_id: "1", client: "acme", project: "shop", state: "working", created: 100 }, { rm_id: "2", client: "acme", project: "shop", state: "ghost", ghost: true, created: null }, { rm_id: "3", ghost: true, state: "ghost" }], {}, true);
  assert.deepStrictEqual({ ...gh.counts }, { total: 1, attention: 0, choice: 0, idle: 0, working: 1, ghost: 2 }, "RM2427 : fantômes comptés à part");
  assert.strictEqual(gh.groups.get("acme/shop").length, 2, "le fantôme est groupé avec sa session vivante"); assert.strictEqual(gh.groups.get("divers")[0].rm_id, "3");
  const cg = M.computeGroups([{ rm_id: "9", client: "c", project: "p", state: "choice", created: 1 }, { rm_id: "8", client: "d", project: "q", state: "working", created: 999 }], {}, true);
  assert.strictEqual(cg.counts.choice, 1); assert.strictEqual(cg.keys[0], "c/p", "RM2327 : groupe avec choice priorisé");
  const oc = M.computeGroups([
    { rm_id: "1", client: "acme", project: "shop", state: "working", created: 100, in_current: true },
    { rm_id: "2", client: "beta", project: "api", state: "idle", created: 200, in_current: false },
    { rm_id: "3", client: "gamma", project: "web", state: "idle", created: 300, in_current: false },
    { rm_id: "4", ghost: true, state: "ghost", client: "beta", project: "api", in_current: false }], {}, true);
  assert(oc.keys.includes(otherGrp + " · beta/api") && oc.keys.includes(otherGrp + " · gamma/web"), "RM2537 : hors jeu, un groupe par chantier");
  assert.strictEqual(oc.keys[0], "acme/shop", "le jeu courant reste en tête"); assert(oc.keys.indexOf(otherGrp + " · beta/api") > 0 && oc.keys.indexOf(otherGrp + " · gamma/web") > 0, "les hors-jeu restent en fin de liste");
  assert.strictEqual(oc.groups.get("beta/api").length, 1, "un FANTÔME n'est jamais relégué hors du jeu"); assert.strictEqual(oc.groups.get(otherGrp + " · beta/api")[0].rm_id, "2");
  assert.deepStrictEqual([...keys], ["beta/api", "divers", "acme/shop"], "tri attention > activité récente > alpha");
  assert.deepStrictEqual([...M.computeGroups([{ rm_id: "10", client: "zeta", project: "z", state: "working", created: 10 }, { rm_id: "11", client: "alpha", project: "a", state: "working", created: 10 }], {}, true).keys], ["alpha/a", "zeta/z"], "alpha à égalité");
  assert.deepStrictEqual([...M.computeGroups(sessions, rcache).keys], ["acme/shop", "beta/api", "divers"], "RM2344 : ordre stable par défaut (tri dynamique = opt-in)");
  const empty = M.computeGroups([], {}); assert.deepStrictEqual([...empty.keys], []); assert.strictEqual(empty.counts.total, 0);
  console.log("✓ computeGroups : groupement, repli, divers, compteurs, RM2427 fantômes, RM2327 choice, RM2537 hors jeu par chantier, RM2344 ordre stable");

  // — fonctions pures déplacées —
  const cache = { "10": { state: "attention" }, "11": { state: "working" } };
  assert.strictEqual(M.approveShortcutVisible("10", cache), true); assert.strictEqual(M.approveShortcutVisible("11", cache), false); assert.strictEqual(M.approveShortcutVisible("99", cache), false); assert.strictEqual(M.approveShortcutVisible(null, cache), false);
  assert.strictEqual(M.effDisposition("idle", "parke"), "parke"); assert.strictEqual(M.effDisposition("idle", "termine"), "termine"); assert.strictEqual(M.effDisposition("idle", null), "a_traiter"); assert.strictEqual(M.effDisposition("idle", ""), "a_traiter");
  assert.strictEqual(M.effDisposition("working", "termine"), null); assert.strictEqual(M.effDisposition("attention", "parke"), null); assert.strictEqual(M.effDisposition("choice", "parke"), null, "RM2515 : cède au live");
  assert.strictEqual(M.sortFrozen(false, true, 0), false, "ordre stable → jamais gelé"); assert.strictEqual(M.sortFrozen(true, true, 99999), true); assert.strictEqual(M.sortFrozen(true, false, 500), true); assert.strictEqual(M.sortFrozen(true, false, 3000), false);
  assert.strictEqual(M.sessionInClient({ client: "acme", state: "working" }, null, ""), true); assert.strictEqual(M.sessionInClient({ client: "acme", state: "working" }, null, "acme"), true); assert.strictEqual(M.sessionInClient({ client: "bob", state: "working" }, null, "acme"), false);
  assert.strictEqual(M.sessionInClient({ client: "bob", state: "attention" }, null, "acme"), true, "RM2445 : en attente → jamais masquée"); assert.strictEqual(M.sessionInClient({ client: "bob", state: "choice" }, null, "acme"), true); assert.strictEqual(M.sessionInClient({ state: "working" }, { found: true, client: "acme" }, "acme"), true, "client résolu via resolveCache");
  assert.strictEqual(M.agoHM(now - 42), "42s"); assert.strictEqual(M.agoHM(now - 12 * 60), "12min"); assert.strictEqual(M.agoHM(now - (2 * 3600 + 14 * 60)), "2h14", "RM2787 : heures ET minutes"); assert.strictEqual(M.agoHM(now - (2 * 3600 + 4 * 60)), "2h04"); assert.strictEqual(M.agoHM(now - 3 * 3600), "3h"); assert.strictEqual(M.agoHM(now - 3 * 86400), "3j"); assert.strictEqual(M.agoHM(now + 500), "0s"); assert.strictEqual(M.agoHM(0), ""); assert.strictEqual(M.agoHM(null), "");
  assert(/#\{session_name\}/.test(fs.readFileSync(path.join(DIR, "..", "..", "..", "scripts", "karl-agent.py"), "utf8")), "le format tmux doit rester lisible côté serveur");
  assert.deepEqual(M.quietSince({ last_msg: 100, activity: 900 }), { ts: 100, exact: true }, "RM2793 : le dernier message prime"); assert.deepEqual(M.quietSince({ activity: 900 }), { ts: 900, exact: false }); assert.deepEqual(M.quietSince({}), { ts: null, exact: false }); assert.deepEqual(M.quietSince(null), { ts: null, exact: false });
  const qExact = VM.quietHtml({ last_msg: now - 3600 }, esc); assert(/Dernier message il y a/.test(qExact) && /récapitulatifs automatiques ne comptent pas/.test(qExact) && /⏳1h/.test(qExact) && !/~/.test(qExact), "mesure exacte : nommée, sans ~");
  const qApprox = VM.quietHtml({ activity: now - 3600 }, esc); assert(/Dernière sortie du terminal/.test(qApprox) && /⏳1h~/.test(qApprox), "repli : nommé, avec ~"); assert.strictEqual(VM.quietHtml({}, esc), ""); assert.strictEqual(VM.quietHtml(null, esc), "");
  assert.strictEqual(M.autoYesLeft(now + 7199), "1 h 59 min", "RM2699 : minutes tronquées"); assert.strictEqual(M.autoYesLeft(now + 15 * 60), "15 min"); assert.strictEqual(M.autoYesLeft(now - 5), "1 min");
  assert(/dernière sortie il y a/.test(M.tabTip({ rm_id: "1", activity: now - 60 }, null)) && /dernier message il y a/.test(M.tabTip({ rm_id: "1", last_msg: now - 60, activity: now }, null)), "l'infobulle NOMME la mesure"); assert(/ouvert il y a/.test(M.tabTip({ rm_id: "1", created: now - 60 }, null)), "l'âge d'ouverture reste");
  assert(/RM7 — Sujet\nacme\/shop · bug · en_cours/.test(M.tabTip({ rm_id: "7", state: "attention", registry_conflicts: [{ rm_id: "7", seqs: [2, 3] }] }, { found: true, title: "Sujet", client: "acme", project: "shop", type: "bug", status: "en_cours" })) && /⚠ demande une réponse/.test(M.tabTip({ rm_id: "7", state: "attention" }, null)) && /aussi ouvert en session #2, #3/.test(M.tabTip({ rm_id: "7", registry_conflicts: [{ rm_id: "7", seqs: [2, 3] }] }, null)));
  assert.strictEqual(M.displayId({ rm_id: "12" }), "RM12"); assert.strictEqual(M.displayId({ rm_id: "slug", is_ticket: false }), "slug"); assert.strictEqual(M.tmuxName("12"), "karl-RM12"); assert.strictEqual(M.tmuxName("slug"), "karl-slug");
  assert(/Redémarre toute seule/.test(M.restartTip("auto")) && /Attend un clic/.test(M.restartTip("idle")));
  const col = M.defaultCollapsed(); assert(M.isCollapsed(col, otherGrp + " · x/y"), "RM2537 : le préfixe replie ses sous-groupes"); M.toggleCollapsed(col, otherGrp + " · x/y"); assert(!M.isCollapsed(col, otherGrp + " · x/y") && M.isCollapsed(col, otherGrp + " · z/w"), "dépli explicite d'un sous-groupe, les autres restent pliés"); M.toggleCollapsed(col, "a/b"); assert(M.isCollapsed(col, "a/b")); M.toggleCollapsed(col, "a/b"); assert(!M.isCollapsed(col, "a/b"));
  assert.deepStrictEqual(M.orderSessions([{ rm_id: "3", state: "idle", disposition: "termine" }, { rm_id: "2", state: "working" }, { rm_id: "10", state: "idle" }]).map(s => s.rm_id), ["2", "10", "3"], "RM2515 : terminé coule en bas, sinon par id numérique");
  assert.strictEqual(M.approveAllMessage({ approved: [{ rm_id: "1" }, { rm_id: "slug" }] }), "✔ Oui envoyé à 2 session(s) : RM1, slug"); assert(/Aucune session/.test(M.approveAllMessage({}))); assert.strictEqual(M.approveMessage("5", { sent: "y" }), "✔ Oui envoyé à RM5 (y + Entrée)"); assert.strictEqual(M.approveMessage("slug", {}), "✔ Oui envoyé à slug (option 1)");
  console.log("✓ fonctions pures : RM2332 raccourci, RM2515 disposition, RM2346 gel, RM2639 client, RM2787/2793 silence, RM2699 auto-oui, infobulles, plis, ordre, messages");


  // — service : préférences de ce navigateur, gel, calcul de la liste, gestes Oui —
  const store = {}; const storage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
  const { repo, calls, st } = mkRepo(now);
  const svc = new SessionsService({ repo, storage, now: () => st.clock });
  assert(!svc.dynSort && svc.isCollapsed(otherGrp + " · a/b") && !svc.frozen(), "défauts : stable, hors jeu replié, pas gelé");
  assert(/Tri dynamique activé/.test(svc.setDynSort(true)) && store.karlDynSort === "1"); svc.enter(); assert(svc.frozen(), "RM2346 : survol → gelé"); svc.leave(); svc.moved(); assert(svc.frozen()); st.clock += 2500; assert(!svc.frozen(), "2 s après le mouvement → dégelé");
  svc.toggleGroup("a/b"); assert(svc.isCollapsed("a/b") && JSON.parse(store.karlCollapsed).includes("a/b"), "pli persisté"); const svc2 = new SessionsService({ repo, storage, now: () => st.clock }); assert(svc2.dynSort && svc2.isCollapsed("a/b"), "…et relu au démarrage");
  const d = svc.compute([{ rm_id: "2", client: "beta", project: "api", state: "idle", disposition: "termine" }, { rm_id: "1", client: "acme", project: "shop", state: "working" }, { rm_id: "3", client: "acme", project: "shop", state: "attention" }], {}, "");
  assert.deepStrictEqual(d.ordered.map(s => s.rm_id), ["1", "3", "2"], "à plat dans l'ordre d'affichage (RM2302), terminé en bas dans son groupe"); assert(d.hidden === 0 && d.visKeys.length === 2);
  const dc = svc.compute([{ rm_id: "1", client: "acme", project: "shop", state: "working" }, { rm_id: "2", client: "beta", project: "api", state: "working" }, { rm_id: "3", client: "beta", project: "api", state: "attention" }], {}, "acme");
  assert.deepStrictEqual(new Set(dc.visKeys), new Set(["acme/shop", "beta/api"]), "RM2639 : un groupe d'un autre client reste visible si une session y attend"); assert.strictEqual(svc.compute([{ rm_id: "2", client: "beta", project: "api", state: "working" }], {}, "acme").hidden, 1);
  assert.strictEqual(await svc.approve("5"), "✔ Oui envoyé à RM5 (y + Entrée)"); assert.deepStrictEqual(await svc.approveAll(), { n: 2, msg: "✔ Oui envoyé à 2 session(s) : RM1, RM2" }); assert(/armé pour 15 min/.test(await svc.autoYes("5", "15"))); assert.strictEqual(await svc.autoYes("5", 0), "auto-oui désarmé");
  console.log("✓ service : préférences persistées (RM2344/2448), gel (RM2346), ordre et visibilité (RM2302/2639), Oui / tout / auto-oui");


  console.log("\nTous les tests du modèle et du service des sessions passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
