#!/usr/bin/env node
// Tests du domaine sessions — CONTRÔLEUR et câblage (RM3018, scindé de test_cockpit_sessions.js) : rendu complet, compteurs → cadence, gestes
// délégués, sélection, contexte client, détachement, Oui / tout / auto-oui, titre et en-tête droit ; hôtes sans on*.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { fakeEl, settle, now, SETS, writable, mkRepo } = require("./test_cockpit_sessions.helpers.js");
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
(async () => {
  const M = await import(path.join(DIR, "src/modules/sessions/sessions.js"));
  const KS = await import(path.join(DIR, "src/core/store.js")); const mkStore = (name, obj) => { const s = new KS.Store(name, { ttl: 1e9, max: 1000 }); Object.entries(obj || {}).forEach(([k, v]) => s.set(k, v)); return s; };   // RM3005
  const { SessionsService } = await import(path.join(DIR, "src/modules/sessions/sessions.service.js"));
  const { esc } = await import(path.join(DIR, "src/core/html.js"));
  const { mountSessions } = await import(path.join(DIR, "src/modules/sessions/sessions.controller.js"));
  const otherGrp = M.OTHER_SETS_GROUP;

  const { repo, calls, st } = mkRepo(now);

  // — contrôleur —
  const list = fakeEl("runlist"), counters = fakeEl("hcnt"), navCount = fakeEl("ln-count"), navAtt = fakeEl("ln-att"), yesAll = fakeEl("yesall"), yesAtt = fakeEl("yesatt"), yesBtn = fakeEl("yesbtn"), autoYes = fakeEl("autoyes"), title = fakeEl("curtitle"), rtitle = fakeEl("rtitle"), dynsort = fakeEl("dynsort");
  list.innerHTML = '<div class="empty">chargement…</div>';
  const ev = []; const sess = mkStore("sess"); let att = "42"; let selOn = false; const selected = new Set(); let cc = ""; let reviews = []; let docTitle = "";
  const RC = { "42": { found: true, title: "Sujet 42" }, "12": { found: true, title: "R12" } };
  const svc3 = new SessionsService({ repo, storage: { getItem: () => null, setItem: () => {} }, now: () => st.clock });
  const ctr = mountSessions({ list, counters, navCount, navAtt, yesAll, yesAtt, yesBtn, autoYes, title, rtitle, dynsort }, {
    service: svc3, notify: (m, e) => ev.push(["toast", m, !!e]), later: (fn) => fn(), ticket: { ensureResolved: (rm) => ev.push(["resolve", rm]) },
    sess: () => sess, resolve: () => mkStore("r", RC), attached: () => att, stale: () => new Set(["7"]), selection: () => ({ on: selOn, set: selected }),
    sets: () => ({ sets: SETS, current: "default", view: "set" }), writable, setLabel: (n) => n, clientContext: () => cc, setClientContext: (c) => { cc = c; ev.push(["ctx", c]); },
    pin: (k, key) => "<i>" + k + key + "</i>", titleLink: (rm, tt) => esc(tt), composerRefresh: () => ev.push("composer"), attach: (rm) => ev.push(["attach", rm]), detach: () => { ev.push("detach"); att = null; }, refresh: () => ev.push("refresh"),
    kill: (rm) => ev.push(["kill", rm]), openDispositionMenu: (s, a) => ev.push(["menu", s.rm_id, a.dataset.action]), setDisposition: (rm, d) => ev.push(["disp", String(rm), d]), drop: (s) => ev.push(["drop", s.rm_id]), relaunch: (s) => ev.push(["relaunch", s.rm_id]), forget: (s) => ev.push(["forget", s.rm_id]), toggleRestart: (s) => ev.push(["restart", s.rm_id]),
    openProject: (k) => ev.push(["project", k]), review: { tabs: () => reviews, current: () => "12", open: (rm) => ev.push(["review", rm]), close: (rm) => ev.push(["review-close", rm]) },
    projectsVisible: () => true, renderProjects: () => ev.push("projects"), announce: (s) => ev.push(["voice", s.length]), renderTitle: () => ev.push("title"), docTitle: (t) => { docTitle = t; },
  });
  assert.strictEqual(list.innerHTML, '<div class="empty">chargement…</div>', "le montage garde l'attente initiale"); assert.strictEqual(dynsort.checked, false, "RM2344 : la case reflète la préférence");
  const S = [{ rm_id: "42", client: "acme", project: "shop", state: "attention", sets: ["default"] }, { rm_id: "7", client: "acme", project: "shop", state: "idle" }, { rm_id: "3", client: "beta", project: "api", state: "choice", in_current: false }, { rm_id: "77", ghost: true, client: "acme", project: "shop", title: "vieux", restart: "auto" }, { rm_id: "9", is_ticket: false, state: "working" }];
  reviews = ["12"];
  let c = ctr.render(S);
  assert.deepStrictEqual({ ...c }, { total: 4, attention: 1, choice: 1, idle: 1, working: 1, ghost: 1 }, "rend les compteurs (la pile /refresh y lit sa cadence, RM2613)");
  assert(sess.get("42") && sess.get("77") && sess.get("9"), "RM2166 : le registre partagé est rempli (store session.registry, RM3005)"); assert(ev.includes("composer") && ev.includes("projects") && ev.includes("title") && ev.some(x => x[0] === "voice" && x[1] === 5), "composer, panneau projets, titre et voix prévenus");
  assert(ev.some(x => x[0] === "resolve" && x[1] === "7") && ev.some(x => x[0] === "resolve" && x[1] === "3") && !ev.some(x => x[0] === "resolve" && x[1] === "42") && !ev.some(x => x[0] === "resolve" && x[1] === "9"), "RM2144 : /resolve pour les tickets non encore résolus, pas les slugs");
  let L = list.innerHTML;
  assert(/attnband/.test(L) && /à traiter \(2\)/.test(L) && /class="rghead" data-action="group" data-key="acme\/shop"/.test(L) && /class="runitem active" data-action="attach" data-k="s:42"/.test(L) && /data-k="g:77"/.test(L) && /🕓/.test(L) && /<i>session42<\/i>/.test(L) && /Sujet 42/.test(L) && /data-action="review" data-rm="12"/.test(L) && !/ctxbanner/.test(L), "liste : bandeau, groupes, tuiles, fantôme, question sans réponse (7), marque, revues");
  assert(/data-key="⋯ hors du jeu courant · beta\/api" title="[^"]*">▸/.test(L) && (L.match(/data-k="s:3"/g) || []).length === 1, "RM2537 : hors jeu replié par défaut — la session 3 n'apparaît que dans le bandeau");
  assert(/● 4/.test(counters.innerHTML) && /⏸ 1/.test(counters.innerHTML) && navCount.textContent === "4" && navAtt.textContent === "⚠2" && navAtt.style.display === "" && yesAll.style.display === "none" && docTitle === "⚠2 Cockpit karl-agent", "compteurs, badges, ✔ tout (1 seule en attention → masqué), titre du navigateur");
  assert.deepStrictEqual(ctr.ordered().map(s => s.rm_id), ["7", "42", "77", "9", "3"], "à plat dans l'ordre d'affichage (RM2515 par id, jeu courant d'abord, hors jeu en fin)"); assert.strictEqual(ctr.groups()["acme/shop"].length, 3, "RM2173 : groupes exposés à la fiche projet");
  // gestes
  ev.length = 0; await list.click("attach", { k: "s:7" }); assert.deepStrictEqual(ev[0], ["attach", "7"]); await list.click("approve", { k: "s:42" }); assert.deepStrictEqual(calls[calls.length - 1], ["approve", "42"]); assert(ev.some(x => x[0] === "toast" && /RM42/.test(x[1])) && ev.includes("refresh"), "✔ depuis la liste : Oui puis re-peint");
  ev.length = 0; await list.click("kill", { k: "s:7" }); await list.click("drop", { k: "s:42" }); await list.click("disp", { k: "s:7" }); await list.click("relaunch", { k: "g:77" }); await list.click("forget", { k: "g:77" }); await list.click("restart", { k: "g:77" }); await list.click("group", { key: "acme/shop" }); await list.click("review", { rm: "12" }); await list.click("review-close", { rm: "12" });
  assert.deepStrictEqual(ev, [["kill", "7"], ["drop", "42"], ["disp", "7", "parke"], ["relaunch", "77"], ["forget", "77"], ["restart", "77"], ["project", "acme/shop"], ["review", "12"], ["review-close", "12"]], "chaque geste va au bon prêteur — et RM2792 : la pastille BASCULE au lieu d'ouvrir un menu");
  // RM2792 : le menu complet reste atteignable — alt-clic, et clic droit (où le navigateur n'a rien d'utile à proposer)
  ev.length = 0; const dispEl = { dataset: { action: "disp", k: "s:7" }, closest: (sel) => (sel === "[data-action]" || sel === '[data-action="disp"]') ? dispEl : null };
  await list.fire("click", dispEl, { altKey: true }); assert.deepStrictEqual(ev, [["menu", "7", "disp"]], "alt-clic : tous les choix");
  ev.length = 0; let prevented = false; await list.fire("contextmenu", dispEl, { preventDefault() { prevented = true; } });
  assert.deepStrictEqual(ev, [["menu", "7", "disp"]], "clic droit : tous les choix"); assert(prevented, "…et le menu du navigateur ne s'ouvre pas par-dessus");
  ev.length = 0; await list.click("disp", { k: "s:inconnu" }); assert.strictEqual(ev.length, 0, "clé inconnue : aucune bascule");
  ev.length = 0; await list.click("fold", { key: "acme/shop" }); assert(svc3.isCollapsed("acme/shop") && ev.includes("refresh"), "RM2448 : le chevron replie et re-peint"); ctr.render(S); assert(!/data-k="s:7"/.test(list.innerHTML) && /data-key="acme\/shop" title="Déplier ce groupe">▸/.test(list.innerHTML), "groupe replié : plus de tuiles"); ctr.toggleGroup("acme/shop");
  await list.click("attach", { k: "s:inconnu" }); assert(!ev.some(x => x[0] === "attach"), "clé inconnue : rien");
  selOn = true; ev.length = 0; ctr.render(S); await list.click("attach", { k: "s:7" }); assert(selected.has("7") && ev.includes("refresh") && !ev.some(x => x[0] === "attach"), "RM2448 : en mode sélection, le clic retient au lieu d'attacher"); await list.click("relaunch", { k: "g:77" }); assert(selected.has("77") && !ev.some(x => x[0] === "relaunch"), "…et retient une tuile grise au lieu de la relancer (RM2448 correctif)"); await list.click("attach", { k: "s:7" }); assert(!selected.has("7"), "re-clic : déselectionne"); selOn = false;
  // contexte client
  cc = "acme"; ctr.render(S); L = list.innerHTML; assert(/ctxbanner/.test(L) && /<b>acme<\/b>/.test(L) && /data-key="⋯ hors du jeu courant · beta\/api"/.test(L), "RM2639 : bannière ; beta/api reste visible car sa session attend (choice)"); ev.length = 0; await list.click("ctx-clear"); assert.deepStrictEqual(ev[0], ["ctx", ""]); cc = "";
  // disparition de la session attachée, liste vide
  ev.length = 0; att = "42"; ctr.render([{ rm_id: "42", ghost: true }]); assert(ev.includes("detach") && att === null, "RM2427 : un fantôme du même id ne retient pas l'attache → détachée"); reviews = []; ctr.render([]); assert(/Aucune session — lances-en une/.test(list.innerHTML), "vide : le message"); reviews = ["12"]; ctr.render([]); assert(!/Aucune session/.test(list.innerHTML) && /revues ouvertes/.test(list.innerHTML), "des revues ouvertes : pas « aucune session »");
  // ✔ tout, auto-oui, raccourcis, titre
  att = "42"; ctr.render([{ rm_id: "42", state: "attention" }, { rm_id: "43", state: "attention" }]); assert.strictEqual(yesAll.style.display, "", "RM2327 : ✔ tout dès 2 en attention");
  ev.length = 0; calls.length = 0; await yesAll.fire("click", yesAll); assert.deepStrictEqual(calls[0], ["all"]); assert(ev.some(x => x[0] === "toast" && /2 session\(s\)/.test(x[1])) && ev.includes("refresh") && yesAll.disabled === false);
  ev.length = 0; calls.length = 0; autoYes.value = "30"; await autoYes.fire("change", autoYes); assert.deepStrictEqual(calls[0], ["auto", "42", "30"]); assert(ev.some(x => x[0] === "toast" && /armé pour 30 min/.test(x[1])) && ev.includes("refresh")); calls.length = 0; autoYes.value = ""; await autoYes.fire("change", autoYes); assert.strictEqual(calls.length, 0, "« ⏱ auto-oui… » : rien");
  ev.length = 0; calls.length = 0; await yesBtn.fire("click", yesBtn); await yesAtt.fire("click", yesAtt); assert.deepStrictEqual(calls, [["approve", "42"], ["approve", "42"]], "✔ Oui (barre + header) → la session attachée"); await title.click("approve"); assert.strictEqual(calls.length, 3, "…et le bouton du titre aussi");
  ev.length = 0; calls.length = 0; await ctr.approve("ko"); assert(ev.some(x => x[0] === "toast" && x[1] === "plus de question" && x[2]) && !ev.includes("refresh"), "refus serveur : dit, pas re-peint"); await ctr.approve(null); assert.strictEqual(calls.length, 1);
  sess.set("42", { rm_id: "42", state: "attention", auto_yes_until: now + 600 }); assert(/class="tid">RM42</.test(ctr.titleHtml()) && /Sujet 42/.test(ctr.titleHtml()) && /data-action="approve"/.test(ctr.titleHtml()), "titre prêté au routeur");
  ctr.afterTitle(); assert(rtitle.style.display === "" && /rt-id">RM42/.test(rtitle.innerHTML) && /Sujet 42/.test(rtitle.innerHTML) && rtitle.title === "Session attachée — karl-RM42" && yesBtn.style.display === "" && yesAtt.style.display === "" && /⏱✔ 10 min/.test(autoYes.options[0].textContent) && autoYes.style.color === "var(--ok)" && autoYes.value === "", "RM2894/2302/2327 : en-tête droit, ✔ Oui visibles, auto-oui armé");
  sess.set("42", { rm_id: "42", state: "working" }); ctr.afterTitle(); assert(yesBtn.style.display === "none" && yesAtt.style.display === "none" && autoYes.options[0].textContent === "⏱ auto-oui…" && autoYes.style.color === "", "au travail : raccourcis masqués, auto-oui au repos");
  att = null; ctr.afterTitle(); assert(rtitle.style.display === "none" && rtitle.innerHTML === "" && ctr.titleHtml() === "", "rien d'attaché : en-tête vide");
  ev.length = 0; dynsort.checked = true; await dynsort.fire("change", dynsort); assert(svc3.dynSort && ev.some(x => x[0] === "toast" && /Tri dynamique activé/.test(x[1])) && ev.includes("refresh"), "RM2344 : la case règle le tri");
  assert.strictEqual(ctr.restartTip("auto"), M.restartTip("auto")); assert.strictEqual(ctr.effDisposition("idle", null), "a_traiter");
  ctr.unmount(); assert.strictEqual([list, counters, yesAll, yesAtt, yesBtn, autoYes, title, dynsort].reduce((n, e) => n + e.listenerCount, 0), 0, "unmount libère tout");
  console.log("✓ contrôleur : rendu complet, compteurs → cadence, gestes délégués, sélection, contexte client, détachement, Oui / tout / auto-oui, titre et en-tête droit");

  // — hôtes et ponts dans index.html —
  ["runlist", "hcnt", "ln-count", "ln-att", "yesall", "yesatt", "yesbtn", "autoyes", "curtitle", "rtitle", "dynsort"].forEach(id => assert(html.includes('id="' + id + '"'), "hôte manquant : " + id));
  for (const id of ["yesall", "yesatt", "yesbtn", "autoyes", "dynsort"]) { const m = new RegExp('<(?:button|select|input)[^>]*id="' + id + '"[^>]*>').exec(html); assert(m && !/\son\w+=/.test(m[0]), "l'hôte #" + id + " ne porte plus de on*"); }
  assert(/onSessions: \(list\) => \{ sessionsCtl\.render\(list\); pollFeed\(\); \}/.test(fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8")) && /this\.hot = \(c\.attention \|\| 0\) \+ \(c\.choice \|\| 0\)/.test(fs.readFileSync(path.join(DIR, "src/modules/refresh/refresh.service.js"), "utf8")), "la pile /refresh (migrée) livre le bloc sessions au contrôleur et lit les compteurs rendus pour sa cadence (RM2613)");
  assert(/ordered: \(\) => sessionsCtl\.ordered\(\)/.test(fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8")) && !/orderedCache/.test(html.replace(/\/\/[^\n]*/g, "")), "RM2439 : les jeux (migrés) lisent les sessions AFFICHÉES sur le contrôleur");
  for (const src of [fs.readFileSync(path.join(DIR, "src/modules/sessions/Sessions.view.js"), "utf8"), fs.readFileSync(path.join(DIR, "src/modules/sessions/sessions.controller.js"), "utf8")]) assert(!/\son(click|change|input)=/.test(src), "aucun handler inline dans le code migré");
  console.log("✓ hôtes sans on*, ponts renderSessions / orderedSessions / restartTip en place");
  console.log("\nTous les tests du contrôleur des sessions passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
