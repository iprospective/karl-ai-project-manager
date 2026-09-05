#!/usr/bin/env node
// Tests de la liste des sessions migrée (RM2889) — porte RM2140/2283 (computeGroups, compteurs, tri), RM2427 (fantômes), RM2327 (choice),
// RM2537 (hors jeu par chantier), RM2344 (ordre stable), RM2332 (approveShortcutVisible), RM2515 (effDisposition), RM2346 (sortFrozen, bandeau),
// RM2639 (sessionInClient, bannière), RM2787/2793 (agoHM, silence), RM2894 (en-tête droit), RM2795 (marque), RM2673 (⊖ ⟳ selon setWritable),
// RM2598 (question sans réponse), RM2448 (pli, sélection), RM2302/2327 (Oui, tout, auto-oui), RM2210 (revues ouvertes), RM2613 (compteurs → cadence).
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
function fakeEl(id, extra) { const L = []; let inner = ""; const self = Object.assign({ id, style: {}, value: "", dataset: {}, kids: {}, textContent: "", title: "", checked: false, options: [{ textContent: "" }], get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, querySelector(sel) { return self.kids[sel] || null; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, target, extra2) { for (const [t, f] of [...L]) if (t === type) await f(Object.assign({ target, currentTarget: self, preventDefault() {}, stopPropagation() {} }, extra2 || {})); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: (sel) => (sel === "[data-action]" || sel === '[data-action="' + action + '"]') ? n : null, disabled: false }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, currentTarget: self, preventDefault() {}, stopPropagation() {} }); return n; } }, extra || {}); return self; }
const settle = () => new Promise(r => setTimeout(r, 0));
(async () => {
  const M = await import(path.join(DIR, "src/models/sessions/sessions.js"));
  const { SessionsService } = await import(path.join(DIR, "src/services/sessions.service.js"));
  const VM = await import(path.join(DIR, "src/viewmodels/sessions/SessionsViewModel.js"));
  const V = await import(path.join(DIR, "src/views/sessions/Sessions.view.js"));
  const { esc } = await import(path.join(DIR, "src/core/html.js"));
  const { mountSessions } = await import(path.join(DIR, "src/controllers/sessions.controller.js"));
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
  const now = Math.floor(Date.now() / 1000);
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

  // — RM2894 : en-tête du panneau de droite —
  let h2894 = V.rTitleHtml("2894", { title: "titre transcript" }, { found: true, title: "Sujet Redmine" }, esc); assert(/RM2894/.test(h2894) && /Sujet Redmine/.test(h2894) && !/titre transcript/.test(h2894), "le sujet Redmine prime quand le ticket est résolu");
  h2894 = V.rTitleHtml("calicote-presta", { is_ticket: false, title: "MEP productcheck" }, null, esc); assert(!/RM/.test(h2894) && /calicote-presta/.test(h2894) && /MEP productcheck/.test(h2894), "slug : titre du transcript, pas de RM inventé");
  h2894 = V.rTitleHtml("2894", {}, { found: false }, esc); assert(/sans libellé/.test(h2894) && !/karl-/.test(h2894), "absence dite, jamais le nom tmux");
  h2894 = V.rTitleHtml("2894", { title: '<img src=x onerror="alert(1)">' }, null, esc); assert(!/<img/.test(h2894) && /&lt;img/.test(h2894), "le libellé est échappé");
  assert(html.indexOf('id="rtitle"') > 0 && html.indexOf('id="rtitle"') < html.indexOf('<nav class="rnav">'), "l'en-tête doit précéder la barre d'onglets .rnav");
  assert(/function afterTitle\(\) \{\s*\n\s*renderRTitle\(\);/.test(fs.readFileSync(path.join(DIR, "src/controllers/sessions.controller.js"), "utf8")), "renderRTitle doit être rejoué à tout changement de vue (afterTitle)");
  assert(/if \(ctx\.afterTitle\) ctx\.afterTitle\(\);/.test(fs.readFileSync(path.join(DIR, "src/controllers/center.controller.js"), "utf8")), "…et le routeur du centre les rejoue après chaque titre");
  console.log("✓ libellé de session (RM2894) : en-tête au-dessus des onglets, 3 sources, échappement, rejoué à chaque vue");

  // — ViewModels et vues —
  const SETS = [{ name: "default", label: "Défaut" }, { name: "pm", label: "PM", derived: true }];
  const writable = (sets, name, view) => !/^client:/.test(String(view || "")) && !((sets || []).find(s => s && s.name === name) || {}).derived;
  const lend = { pin: (k, key) => '<span class="pin">' + k + ":" + key + "</span>", titleLink: (rm, t) => '<span class="tlink">' + esc(t) + "</span>" };
  const base = { attached: "42", stale: new Set(["7"]), selMode: false, selected: new Set(), set: { sets: SETS, current: "default", view: "set" }, writable, setLabel: (n) => (SETS.find(s => s.name === n) || {}).label || n };
  const live = new VM.SessionTileViewModel({ rm_id: "42", state: "attention", created: now - 120, last_msg: now - 60, sets: ["default"], auto_yes_until: now + 900 }, Object.assign({}, base, { resolved: { found: true, title: "Sujet" } }));
  assert(live.active && live.canApprove && live.canDrop && live.badge.text === "⚠" && live.quiet.text === "⏳1min" && live.autoTitle.includes("15 min") && live.title === "Sujet" && live.age === "2min" && !live.stale && live.setTag === null, "tuile vivante attachée en attention");
  assert.strictEqual(live.dropTitle, "Retirer du jeu « Défaut » — la session continue de tourner");
  let t = String(V.Tile(live, lend));
  assert(/class="runitem active" data-action="attach" data-k="s:42"/.test(t) && /data-action="disp" data-k="s:42"/.test(t) && /class="tid">RM42</.test(t) && /<span class="pin">session:42<\/span>/.test(t) && /class="tlink">Sujet</.test(t) && / · 2min</.test(t) && /class="tquiet" title="Dernier message il y a 1min/.test(t) && /class="tbadge">⚠</.test(t) && /⏱✔/.test(t) && /class="tyes" data-action="approve" data-k="s:42"/.test(t) && /class="tkill tdrop" data-action="drop"/.test(t) && /class="tkill" data-action="kill" data-k="s:42"/.test(t) && !/onclick=/.test(t), "tuile : marque RM2795, lien de titre, silence, pastilles, gestes en data-action");
  const idle = new VM.SessionTileViewModel({ rm_id: "7", state: "idle", disposition: "termine", in_current: false, set_labels: ["Chantier long"], sets: ["pm"] }, Object.assign({}, base, { set: { sets: SETS, current: "pm", view: "set" } }));
  assert(idle.badge.text === "✅" && /disp-termine/.test(idle.dotClass) && idle.stale && idle.setTag.text === "Chantier l" && !idle.canDrop, "RM2515 terminé · RM2598 question sans réponse · RM2446 jeu affiché · RM2673 : ⊖ masqué sur un jeu dérivé");
  t = String(V.Tile(idle, lend)); assert(/🕓/.test(t) && !/tdrop/.test(t) && /title="appartient au jeu « Chantier long »">Chantier l</.test(t) && /disp-termine/.test(t));
  const nolabel = new VM.SessionTileViewModel({ rm_id: "8", state: "attention", in_current: false }, base); assert(nolabel.setTag.text === "hors jeu" && !nolabel.stale, "aucun jeu : « hors jeu » ; en attention : 🕓 tait (même urgence, un seul signal)");
  assert.strictEqual(new VM.SessionTileViewModel({ rm_id: "9", state: "attention", sets: ["default"] }, Object.assign({}, base, { set: { sets: SETS, current: "default", view: "client:acme" } })).canDrop, false, "RM2536 : une vue par client ne désigne aucun jeu");
  const sel = new VM.SessionTileViewModel({ rm_id: "5", state: "working" }, Object.assign({}, base, { selMode: true, selected: new Set(["5"]) })); assert(/style="outline:1px solid var\(--accent\)"/.test(String(V.Tile(sel, lend))), "RM2448 : la sélection se voit");
  const ghost = new VM.GhostTileViewModel({ rm_id: "77", ghost: true, title: "nom mémorisé", engine: "claude", cwd: "/w", resumable: true, restart: "auto", last_active: now - 8 * 86400, group_label: "Jeu B" }, Object.assign({}, base, { set: { sets: SETS, current: "default", view: "all" } }));
  assert(ghost.title === "nom mémorisé" && ghost.inSet && ghost.faded && ghost.restartIcon === "⟳" && ghost.groupTag.text === "Jeu B" && /inactive depuis 8j/.test(ghost.age) && /conversation mémorisée/.test(ghost.tip) && /moteur : claude/.test(ghost.tip), "RM2439/2442/2451/2949 : tuile grise");
  t = String(V.Ghost(ghost)); assert(/class="runitem ghost" data-action="relaunch" data-k="g:77"/.test(t) && /style="opacity:.55"/.test(t) && /class="tbadge trestart" style="cursor:pointer" data-action="restart" data-k="g:77" title="Redémarre/.test(t) && /data-action="forget" data-k="g:77"/.test(t) && /title="Jeu B/.test(t) === false && /title="jeu « Jeu B »">Jeu B</.test(t));
  const ghostDerived = new VM.GhostTileViewModel({ rm_id: "78", ghost: true, restart: "idle" }, Object.assign({}, base, { set: { sets: SETS, current: "pm", view: "set" } })); assert(!ghostDerived.inSet && !/trestart|forget/.test(String(V.Ghost(ghostDerived))), "RM2673 : ⊖ et ⟳ des tuiles grises masqués sur un jeu dérivé"); assert(/conversation perdue/.test(ghostDerived.tip) && /Clic : retenir/.test(new VM.GhostTileViewModel({ rm_id: "1" }, Object.assign({}, base, { selMode: true })).tip));
  const gvm = new VM.GroupViewModel({ key: "acme/shop", sessions: [{ state: "attention" }, { state: "choice" }, { state: "idle" }], folded: false }); assert(gvm.att === 1 && gvm.cho === 1 && gvm.count === 3 && gvm.chevron === "▾");
  t = String(V.Group(gvm, [V.Tile(sel, lend)])); assert(/class="rghead" data-action="group" data-key="acme\/shop" title="acme\/shop\n\(clic : fiche projet/.test(t) && /class="gfold"[^>]*data-action="fold" data-key="acme\/shop" title="Replier ce groupe">▾</.test(t) && /⚠1/.test(t) && /❓1/.test(t) && /data-k="s:5"/.test(t), "en-tête : fiche projet au clic, chevron à part");
  t = String(V.Group(new VM.GroupViewModel({ key: "k", sessions: [], folded: true }), [V.Tile(sel, lend)])); assert(/▸/.test(t) && !/runitem/.test(t), "replié : aucune tuile");
  t = String(V.AttnBand([new VM.AttnChipViewModel({ rm_id: "3", state: "attention" }, { found: true, title: "T3" }), new VM.AttnChipViewModel({ rm_id: "slug", is_ticket: false, state: "choice" }, null)], lend));
  assert(/à traiter \(2\)/.test(t) && /class="attnchip" data-action="attach" data-k="s:3"/.test(t) && /class="tlink">T3</.test(t) && /class="tyes" data-action="approve" data-k="s:3"/.test(t) && /karl-slug/.test(t) && (t.match(/tyes/g) || []).length === 1, "RM2346 : bandeau, ✔ seulement sur attention"); assert.strictEqual(String(V.AttnBand([], lend)), "");
  t = String(V.CtxBanner("acme", 2)); assert(/Contexte client : <b>acme<\/b>/.test(t) && /2 groupe\(s\) hors client masqué/.test(t) && /data-action="ctx-clear"/.test(t) && !/onclick/.test(t)); assert(!/masqué/.test(String(V.CtxBanner("acme", 0))));
  t = String(V.ReviewGroup([new VM.ReviewTileViewModel("12", { found: true, title: "R12" }, true)], lend)); assert(/🧪 revues ouvertes/.test(t) && /class="runitem active" data-action="review" data-rm="12"/.test(t) && /<span class="pin">review:12<\/span>/.test(t) && /data-action="review-close" data-rm="12"/.test(t), "RM2210/RM2795");
  const cvm = new VM.CountersViewModel({ total: 3, attention: 2, choice: 1, idle: 1, working: 0, ghost: 2 }); assert(cvm.waiting === 3 && cvm.showYesAll && cvm.docTitle === "⚠3 Cockpit karl-agent");
  t = String(V.Counters(cvm)); assert(/● 3/.test(t) && /⏸ 2/.test(t) && /class="pill att"[^>]*>⚠ 2/.test(t) && /❓ 1/.test(t) && /💤 1/.test(t)); assert(!/⏸|❓/.test(String(V.Counters(new VM.CountersViewModel({ total: 0, attention: 0, choice: 0, idle: 0, working: 0, ghost: 0 })))) && !new VM.CountersViewModel({ attention: 1, choice: 0 }).showYesAll, "RM2327 : ✔ tout dès 2 en attention");
  const tv = new VM.SessionTitleViewModel({ attached: "42", sess: { state: "attention", auto_yes_until: now + 600 }, resolved: { found: true, title: "Sujet" } }); assert(tv.shown && tv.approveVisible && tv.autoYesArmed && /⏱✔ 10 min/.test(tv.autoYesLabel));
  t = String(V.SessionTitle(tv, lend)); assert(/class="tdot st-attention"/.test(t) && /class="tid">RM42</.test(t) && /class="tlink">Sujet</.test(t) && /<button class="mini" style="margin-left:8px" data-action="approve"/.test(t) && !/onclick/.test(t), "RM2283/2332 : titre + ✔ Oui sans on*");
  t = String(V.SessionTitle(new VM.SessionTitleViewModel({ attached: "slug", sess: { is_ticket: false, state: "choice" } }), lend)); assert(/class="tid">slug</.test(t) && /karl-slug/.test(t) && /❓/.test(t) && !/✔ Oui/.test(t)); assert.strictEqual(String(V.SessionTitle(new VM.SessionTitleViewModel({ attached: null }), lend)), "");
  assert.strictEqual(new VM.SessionTitleViewModel({ attached: null }).autoYesLabel, "⏱ auto-oui…");
  console.log("✓ ViewModels et vues : tuiles vivantes/grises, groupes, bandeau, bannière, revues, compteurs, titre — gestes en data-*, RM2673 selon setWritable, RM2795 marque");

  // — service : préférences de ce navigateur, gel, calcul de la liste, gestes Oui —
  const store = {}; const storage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
  let clock = 1000; const calls = [];
  const repo = { async approve(rm) { calls.push(["approve", rm]); if (rm === "ko") throw new Error("plus de question"); return { sent: "y" }; }, async approveAll() { calls.push(["all"]); return { approved: [{ rm_id: "1" }, { rm_id: "2" }] }; }, async autoYes(rm, m) { calls.push(["auto", rm, m]); return m ? { auto_yes_until: now + 60 * m } : {}; } };
  const svc = new SessionsService({ repo, storage, now: () => clock });
  assert(!svc.dynSort && svc.isCollapsed(otherGrp + " · a/b") && !svc.frozen(), "défauts : stable, hors jeu replié, pas gelé");
  assert(/Tri dynamique activé/.test(svc.setDynSort(true)) && store.karlDynSort === "1"); svc.enter(); assert(svc.frozen(), "RM2346 : survol → gelé"); svc.leave(); svc.moved(); assert(svc.frozen()); clock += 2500; assert(!svc.frozen(), "2 s après le mouvement → dégelé");
  svc.toggleGroup("a/b"); assert(svc.isCollapsed("a/b") && JSON.parse(store.karlCollapsed).includes("a/b"), "pli persisté"); const svc2 = new SessionsService({ repo, storage, now: () => clock }); assert(svc2.dynSort && svc2.isCollapsed("a/b"), "…et relu au démarrage");
  const d = svc.compute([{ rm_id: "2", client: "beta", project: "api", state: "idle", disposition: "termine" }, { rm_id: "1", client: "acme", project: "shop", state: "working" }, { rm_id: "3", client: "acme", project: "shop", state: "attention" }], {}, "");
  assert.deepStrictEqual(d.ordered.map(s => s.rm_id), ["1", "3", "2"], "à plat dans l'ordre d'affichage (RM2302), terminé en bas dans son groupe"); assert(d.hidden === 0 && d.visKeys.length === 2);
  const dc = svc.compute([{ rm_id: "1", client: "acme", project: "shop", state: "working" }, { rm_id: "2", client: "beta", project: "api", state: "working" }, { rm_id: "3", client: "beta", project: "api", state: "attention" }], {}, "acme");
  assert.deepStrictEqual(new Set(dc.visKeys), new Set(["acme/shop", "beta/api"]), "RM2639 : un groupe d'un autre client reste visible si une session y attend"); assert.strictEqual(svc.compute([{ rm_id: "2", client: "beta", project: "api", state: "working" }], {}, "acme").hidden, 1);
  assert.strictEqual(await svc.approve("5"), "✔ Oui envoyé à RM5 (y + Entrée)"); assert.deepStrictEqual(await svc.approveAll(), { n: 2, msg: "✔ Oui envoyé à 2 session(s) : RM1, RM2" }); assert(/armé pour 15 min/.test(await svc.autoYes("5", "15"))); assert.strictEqual(await svc.autoYes("5", 0), "auto-oui désarmé");
  console.log("✓ service : préférences persistées (RM2344/2448), gel (RM2346), ordre et visibilité (RM2302/2639), Oui / tout / auto-oui");

  // — contrôleur —
  const list = fakeEl("runlist"), counters = fakeEl("hcnt"), navCount = fakeEl("ln-count"), navAtt = fakeEl("ln-att"), yesAll = fakeEl("yesall"), yesAtt = fakeEl("yesatt"), yesBtn = fakeEl("yesbtn"), autoYes = fakeEl("autoyes"), title = fakeEl("curtitle"), rtitle = fakeEl("rtitle"), dynsort = fakeEl("dynsort");
  list.innerHTML = '<div class="empty">chargement…</div>';
  const ev = []; const sess = {}; let att = "42"; let selOn = false; const selected = new Set(); let cc = ""; let reviews = []; let docTitle = "";
  const RC = { "42": { found: true, title: "Sujet 42" }, "12": { found: true, title: "R12" } };
  const svc3 = new SessionsService({ repo, storage: { getItem: () => null, setItem: () => {} }, now: () => clock });
  const ctr = mountSessions({ list, counters, navCount, navAtt, yesAll, yesAtt, yesBtn, autoYes, title, rtitle, dynsort }, {
    service: svc3, notify: (m, e) => ev.push(["toast", m, !!e]), later: (fn) => fn(), ticket: { ensureResolved: (rm) => ev.push(["resolve", rm]) },
    caches: { sess }, resolve: () => RC, attached: () => att, stale: () => new Set(["7"]), selection: () => ({ on: selOn, set: selected }),
    sets: () => ({ sets: SETS, current: "default", view: "set" }), writable, setLabel: (n) => n, clientContext: () => cc, setClientContext: (c) => { cc = c; ev.push(["ctx", c]); },
    pin: (k, key) => "<i>" + k + key + "</i>", titleLink: (rm, tt) => esc(tt), composerRefresh: () => ev.push("composer"), attach: (rm) => ev.push(["attach", rm]), detach: () => { ev.push("detach"); att = null; }, refresh: () => ev.push("refresh"),
    kill: (rm) => ev.push(["kill", rm]), openDispositionMenu: (s, a) => ev.push(["disp", s.rm_id, a.dataset.action]), drop: (s) => ev.push(["drop", s.rm_id]), relaunch: (s) => ev.push(["relaunch", s.rm_id]), forget: (s) => ev.push(["forget", s.rm_id]), toggleRestart: (s) => ev.push(["restart", s.rm_id]),
    openProject: (k) => ev.push(["project", k]), review: { tabs: () => reviews, current: () => "12", open: (rm) => ev.push(["review", rm]), close: (rm) => ev.push(["review-close", rm]) },
    projectsVisible: () => true, renderProjects: () => ev.push("projects"), announce: (s) => ev.push(["voice", s.length]), renderTitle: () => ev.push("title"), docTitle: (t) => { docTitle = t; },
  });
  assert.strictEqual(list.innerHTML, '<div class="empty">chargement…</div>', "le montage garde l'attente initiale"); assert.strictEqual(dynsort.checked, false, "RM2344 : la case reflète la préférence");
  const S = [{ rm_id: "42", client: "acme", project: "shop", state: "attention", sets: ["default"] }, { rm_id: "7", client: "acme", project: "shop", state: "idle" }, { rm_id: "3", client: "beta", project: "api", state: "choice", in_current: false }, { rm_id: "77", ghost: true, client: "acme", project: "shop", title: "vieux", restart: "auto" }, { rm_id: "9", is_ticket: false, state: "working" }];
  reviews = ["12"];
  let c = ctr.render(S);
  assert.deepStrictEqual({ ...c }, { total: 4, attention: 1, choice: 1, idle: 1, working: 1, ghost: 1 }, "rend les compteurs (la pile /refresh y lit sa cadence, RM2613)");
  assert(sess["42"] && sess["77"] && sess["9"], "RM2166 : le registre partagé est rempli"); assert(ev.includes("composer") && ev.includes("projects") && ev.includes("title") && ev.some(x => x[0] === "voice" && x[1] === 5), "composer, panneau projets, titre et voix prévenus");
  assert(ev.some(x => x[0] === "resolve" && x[1] === "7") && ev.some(x => x[0] === "resolve" && x[1] === "3") && !ev.some(x => x[0] === "resolve" && x[1] === "42") && !ev.some(x => x[0] === "resolve" && x[1] === "9"), "RM2144 : /resolve pour les tickets non encore résolus, pas les slugs");
  let L = list.innerHTML;
  assert(/attnband/.test(L) && /à traiter \(2\)/.test(L) && /class="rghead" data-action="group" data-key="acme\/shop"/.test(L) && /class="runitem active" data-action="attach" data-k="s:42"/.test(L) && /data-k="g:77"/.test(L) && /🕓/.test(L) && /<i>session42<\/i>/.test(L) && /Sujet 42/.test(L) && /data-action="review" data-rm="12"/.test(L) && !/ctxbanner/.test(L), "liste : bandeau, groupes, tuiles, fantôme, question sans réponse (7), marque, revues");
  assert(/data-key="⋯ hors du jeu courant · beta\/api" title="[^"]*">▸/.test(L) && (L.match(/data-k="s:3"/g) || []).length === 1, "RM2537 : hors jeu replié par défaut — la session 3 n'apparaît que dans le bandeau");
  assert(/● 4/.test(counters.innerHTML) && /⏸ 1/.test(counters.innerHTML) && navCount.textContent === "4" && navAtt.textContent === "⚠2" && navAtt.style.display === "" && yesAll.style.display === "none" && docTitle === "⚠2 Cockpit karl-agent", "compteurs, badges, ✔ tout (1 seule en attention → masqué), titre du navigateur");
  assert.deepStrictEqual(ctr.ordered().map(s => s.rm_id), ["7", "42", "77", "9", "3"], "à plat dans l'ordre d'affichage (RM2515 par id, jeu courant d'abord, hors jeu en fin)"); assert.strictEqual(ctr.groups()["acme/shop"].length, 3, "RM2173 : groupes exposés à la fiche projet");
  // gestes
  ev.length = 0; await list.click("attach", { k: "s:7" }); assert.deepStrictEqual(ev[0], ["attach", "7"]); await list.click("approve", { k: "s:42" }); assert.deepStrictEqual(calls[calls.length - 1], ["approve", "42"]); assert(ev.some(x => x[0] === "toast" && /RM42/.test(x[1])) && ev.includes("refresh"), "✔ depuis la liste : Oui puis re-peint");
  ev.length = 0; await list.click("kill", { k: "s:7" }); await list.click("drop", { k: "s:42" }); await list.click("disp", { k: "s:7" }); await list.click("relaunch", { k: "g:77" }); await list.click("forget", { k: "g:77" }); await list.click("restart", { k: "g:77" }); await list.click("group", { key: "acme/shop" }); await list.click("review", { rm: "12" }); await list.click("review-close", { rm: "12" });
  assert.deepStrictEqual(ev, [["kill", "7"], ["drop", "42"], ["disp", "7", "disp"], ["relaunch", "77"], ["forget", "77"], ["restart", "77"], ["project", "acme/shop"], ["review", "12"], ["review-close", "12"]], "chaque geste va au bon prêteur");
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
  sess["42"] = { rm_id: "42", state: "attention", auto_yes_until: now + 600 }; assert(/class="tid">RM42</.test(ctr.titleHtml()) && /Sujet 42/.test(ctr.titleHtml()) && /data-action="approve"/.test(ctr.titleHtml()), "titre prêté au routeur");
  ctr.afterTitle(); assert(rtitle.style.display === "" && /rt-id">RM42/.test(rtitle.innerHTML) && /Sujet 42/.test(rtitle.innerHTML) && rtitle.title === "Session attachée — karl-RM42" && yesBtn.style.display === "" && yesAtt.style.display === "" && /⏱✔ 10 min/.test(autoYes.options[0].textContent) && autoYes.style.color === "var(--ok)" && autoYes.value === "", "RM2894/2302/2327 : en-tête droit, ✔ Oui visibles, auto-oui armé");
  sess["42"] = { rm_id: "42", state: "working" }; ctr.afterTitle(); assert(yesBtn.style.display === "none" && yesAtt.style.display === "none" && autoYes.options[0].textContent === "⏱ auto-oui…" && autoYes.style.color === "", "au travail : raccourcis masqués, auto-oui au repos");
  att = null; ctr.afterTitle(); assert(rtitle.style.display === "none" && rtitle.innerHTML === "" && ctr.titleHtml() === "", "rien d'attaché : en-tête vide");
  ev.length = 0; dynsort.checked = true; await dynsort.fire("change", dynsort); assert(svc3.dynSort && ev.some(x => x[0] === "toast" && /Tri dynamique activé/.test(x[1])) && ev.includes("refresh"), "RM2344 : la case règle le tri");
  assert.strictEqual(ctr.restartTip("auto"), M.restartTip("auto")); assert.strictEqual(ctr.effDisposition("idle", null), "a_traiter");
  ctr.unmount(); assert.strictEqual([list, counters, yesAll, yesAtt, yesBtn, autoYes, title, dynsort].reduce((n, e) => n + e.listenerCount, 0), 0, "unmount libère tout");
  console.log("✓ contrôleur : rendu complet, compteurs → cadence, gestes délégués, sélection, contexte client, détachement, Oui / tout / auto-oui, titre et en-tête droit");

  // — hôtes et ponts dans index.html —
  ["runlist", "hcnt", "ln-count", "ln-att", "yesall", "yesatt", "yesbtn", "autoyes", "curtitle", "rtitle", "dynsort"].forEach(id => assert(html.includes('id="' + id + '"'), "hôte manquant : " + id));
  for (const id of ["yesall", "yesatt", "yesbtn", "autoyes", "dynsort"]) { const m = new RegExp('<(?:button|select|input)[^>]*id="' + id + '"[^>]*>').exec(html); assert(m && !/\son\w+=/.test(m[0]), "l'hôte #" + id + " ne porte plus de on*"); }
  assert(/function renderSessions\(sessions\) \{ const c = karlCall\("sessions", "render", sessions\); if \(c\) hotSessions = c\.attention \+ c\.choice; \}/.test(html), "la pile /refresh livre le bloc sessions et lit la cadence (RM2613)");
  assert(/function orderedSessions\(\) \{ return karlCall\("sessions", "ordered"\)/.test(html) && !/orderedCache/.test(html.replace(/\/\/[^\n]*/g, "")), "RM2439 : les jeux lisent les sessions AFFICHÉES par le pont");
  for (const src of [fs.readFileSync(path.join(DIR, "src/views/sessions/Sessions.view.js"), "utf8"), fs.readFileSync(path.join(DIR, "src/controllers/sessions.controller.js"), "utf8")]) assert(!/\son(click|change|input)=/.test(src), "aucun handler inline dans le code migré");
  console.log("✓ hôtes sans on*, ponts renderSessions / orderedSessions / restartTip en place");
  console.log("\nTous les tests de la liste des sessions passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
