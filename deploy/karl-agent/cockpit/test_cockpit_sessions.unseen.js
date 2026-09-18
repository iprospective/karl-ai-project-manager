#!/usr/bin/env node
// Tests RM3236 — les sessions « à voir » : celles qui ont FINI leur tour pendant qu'on regardait ailleurs. La tuile clignote, un
// compteur les compte, et tout s'éteint dès qu'on va voir la session. Trois couches : la règle pure, le service (persistance
// par navigateur), et le contrôleur de bout en bout (tuile, groupe replié, compteurs, onglet, titre, clic, retour sur l'onglet).
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { fakeEl, SETS, writable, mkRepo, now } = require("./test_cockpit_sessions.helpers.js");
let n = 0; const ok = (cond, msg) => { assert(cond, msg); n++; };
(async () => {
  const U = await import(path.join(DIR, "src/modules/sessions/unseen.js"));
  const KS = await import(path.join(DIR, "src/core/store.js")); const mkStore = (name) => new KS.Store(name, { ttl: 1e9, max: 1000 });
  const { SessionsService } = await import(path.join(DIR, "src/modules/sessions/sessions.service.js"));
  const { mountSessions } = await import(path.join(DIR, "src/modules/sessions/sessions.controller.js"));
  const { esc } = await import(path.join(DIR, "src/core/html.js"));

  // ── la règle pure ──────────────────────────────────────────────────────────
  const s = (rm, state, extra) => Object.assign({ rm_id: rm, state }, extra || {});
  const nobody = () => false;
  let prev = new Map(), u = new Set();
  u = U.trackUnseen(prev, u, [s("1", "idle"), s("2", "working")], nobody);
  ok(u.size === 0, "premier passage : rien n'est à voir — on ignore ce qui a déjà été vu");
  u = U.trackUnseen(prev, u, [s("1", "idle"), s("2", "idle")], nobody);
  ok(u.has("2") && !u.has("1"), "working → idle : la session vient de finir son tour, elle est à voir ; celle qui était déjà au repos non");
  u = U.trackUnseen(prev, u, [s("1", "idle"), s("2", "idle")], nobody);
  ok(u.has("2"), "elle reste à voir tant qu'on n'y est pas allé");
  u = U.trackUnseen(prev, u, [s("1", "idle"), s("2", "idle")], (rm) => rm === "2");
  ok(!u.has("2"), "on la regarde : elle n'est plus à voir");
  u = U.trackUnseen(prev, u, [s("3", "working")], nobody); u = U.trackUnseen(prev, u, [s("3", "attention")], nobody);
  ok(u.has("3"), "working → attention (question posée) : à voir aussi");
  u = U.trackUnseen(prev, u, [s("4", "working")], nobody); u = U.trackUnseen(prev, u, [s("4", "choice")], nobody);
  ok(u.has("4"), "working → choice : à voir aussi");
  u = U.trackUnseen(prev, u, [s("4", "working")], nobody);
  ok(!u.has("4"), "elle repart d'elle-même (auto-oui, relance) : plus rien à voir");
  u = U.trackUnseen(prev, new Set(["3"]), [], nobody);
  ok(!u.has("3") && !prev.has("3"), "session fermée : elle sort de l'ensemble ET de la mémoire des états");
  prev = new Map(); u = U.trackUnseen(prev, new Set(), [s("5", "working")], nobody); u = U.trackUnseen(prev, u, [s("5", "idle")], (rm) => rm === "5");
  ok(!u.has("5"), "la session qu'on regarde au moment où elle finit ne devient jamais à voir");
  prev = new Map(); u = U.trackUnseen(prev, new Set(), [s("6", "working", { ghost: true })], nobody); u = U.trackUnseen(prev, u, [s("6", "idle", { ghost: true })], nobody);
  ok(u.size === 0, "une tuile grise (enregistrée, non démarrée) n'est jamais à voir");
  ok(U.parseUnseen("pas du json").size === 0 && U.parseUnseen(null).size === 0 && U.parseUnseen('{"a":1}').size === 0, "stockage illisible : rien à voir, jamais d'erreur");
  ok(U.parseUnseen('[42,"7"]').has("42"), "les ids relus sont normalisés en chaînes");
  ok(U.unseenIn([s("1", "idle"), s("2", "idle"), s("3", "idle", { ghost: true })], new Set(["1", "3"])) === 1, "compte d'un groupe : les tuiles grises ne comptent pas");

  // ── le service : l'ensemble survit au rechargement de la page ─────────────
  const mem = {}; const storage = { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; } };
  const svcA = new SessionsService({ repo: mkRepo(now).repo, storage });
  svcA.trackUnseen([s("8", "working")], nobody); svcA.trackUnseen([s("8", "idle")], nobody);
  ok(JSON.parse(mem.karlUnseen).includes("8"), "l'ensemble est écrit dans le stockage du navigateur");
  const svcB = new SessionsService({ repo: mkRepo(now).repo, storage });
  ok(svcB.unseen.has("8"), "après rechargement, la session est toujours à voir");
  svcB.trackUnseen([s("8", "idle")], nobody);
  ok(svcB.unseen.has("8"), "…et le premier passage après rechargement ne l'efface pas");
  ok(svcB.markSeen("8") && !svcB.unseen.has("8") && !JSON.parse(mem.karlUnseen).includes("8"), "markSeen éteint et persiste");
  ok(svcB.markSeen("8") === false, "markSeen sur une session déjà vue : rien à faire, rien à repeindre");

  // ── le contrôleur, de bout en bout ─────────────────────────────────────────
  const list = fakeEl("runlist"), counters = fakeEl("hcnt"), navCount = fakeEl("ln-count"), navAtt = fakeEl("ln-att"), navSeen = fakeEl("ln-seen");
  const doc = fakeEl("document"); doc.hidden = false;
  const mem2 = {}; const storage2 = { getItem: (k) => (k in mem2 ? mem2[k] : null), setItem: (k, v) => { mem2[k] = v; } };
  const svc = new SessionsService({ repo: mkRepo(now).repo, storage: storage2 });
  let att = "10"; let title = ""; const ev = []; const sess = mkStore("sess");
  const ctr = mountSessions({ list, counters, navCount, navAtt, navSeen }, {
    service: svc, document: doc, notify: () => {}, later: (fn) => fn(), sess: () => sess, resolve: () => mkStore("r"), attached: () => att,
    selection: () => ({ on: false, set: new Set() }), sets: () => ({ sets: SETS, current: "default", view: "set" }), writable, setLabel: (x) => x,
    pin: () => "", titleLink: (rm, t) => esc(t), attach: (rm) => { ev.push(["attach", rm]); att = rm; }, refresh: () => ev.push("refresh"), docTitle: (t) => { title = t; },
  });
  const S1 = [s("10", "working", { client: "a", project: "p" }), s("11", "working", { client: "a", project: "p" }), s("12", "working", { client: "b", project: "q" })];
  ctr.render(S1);
  ok(!/unseen/.test(list.innerHTML) && navSeen.style.display === "none", "tout le monde travaille : rien ne clignote, le badge est masqué");
  const S2 = [s("10", "idle", { client: "a", project: "p" }), s("11", "idle", { client: "a", project: "p" }), s("12", "attention", { client: "b", project: "q" })];
  ctr.render(S2);
  let L = list.innerHTML;
  ok(/class="runitem unseen" data-action="attach" data-k="s:11"/.test(L), "la tuile de 11, qui a fini sans qu'on la regarde, clignote");
  ok(/data-k="s:12"/.test(L) && /class="runitem unseen" data-action="attach" data-k="s:12"/.test(L), "12 aussi (question posée)");
  ok(/class="runitem active" data-action="attach" data-k="s:10"/.test(L), "10 était attachée et l'onglet visible : pas de clignotement");
  ok(/👁 2 à voir/.test(counters.innerHTML), "le compteur du panneau dit 2 sessions à voir");
  ok(navSeen.textContent === "👁2" && navSeen.style.display === "", "le badge de l'onglet « en cours » aussi");
  ok(/^👁2 /.test(title), "le titre du navigateur porte le compteur, pour le voir depuis un autre onglet");
  ok(/data-key="a\/p"[^>]*>.*👁1/.test(L), "l'en-tête du groupe compte ses sessions à voir");

  ev.length = 0; await list.click("attach", { k: "s:11" });
  L = list.innerHTML;
  ok(!/runitem[^"]*unseen[^"]*" data-action="attach" data-k="s:11"/.test(L), "clic sur la tuile : elle s'arrête de clignoter tout de suite");
  ok(/👁 1 à voir/.test(counters.innerHTML) && navSeen.textContent === "👁1", "…et le compteur descend d'un cran, sans attendre le rafraîchissement");
  ok(ev.some(x => x[0] === "attach" && x[1] === "11"), "…et la session est bien attachée");

  // groupe replié : le clignotement serait invisible, l'en-tête doit le dire
  svc.toggleGroup("b/q"); ctr.render(S2); L = list.innerHTML;
  ok(!/data-k="s:12"/.test(L.replace(/attnband.*?<\/div><\/div>/s, "")) && /data-key="b\/q"[^>]*>.*👁1/.test(L), "groupe replié : ses tuiles sont cachées mais l'en-tête affiche 👁1");
  svc.toggleGroup("b/q");

  // l'onglet caché : la session attachée qui finit dans le dos de l'utilisateur doit l'attendre
  att = "13"; doc.hidden = true;
  ctr.render([...S2, s("13", "working")]); ctr.render([...S2, s("13", "idle")]);
  ok(svc.unseen.has("13"), "attachée mais onglet caché : elle a fini sans être vue, elle est à voir");
  doc.hidden = false; ev.length = 0; await doc.fire("visibilitychange", doc);
  ok(!svc.unseen.has("13") && ev.includes("refresh"), "retour sur l'onglet : elle s'éteint et la liste est repeinte aussitôt");

  // session fermée : elle ne laisse pas un compteur fantôme
  ctr.render([s("10", "idle")]);
  ok(svc.unseen.size === 0 && navSeen.style.display === "none" && !/à voir/.test(counters.innerHTML), "sessions fermées : le compteur retombe à zéro et disparaît");
  ctr.unmount();
  console.log("OK — sessions à voir : " + n + " assertions (RM3236)");
})().catch(e => { console.error("ÉCHEC :", e && e.message); process.exit(1); });
