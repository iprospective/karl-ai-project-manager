#!/usr/bin/env node
// Tests du domaine sessions — VIEWMODELS et VUES (RM3018, scindé de test_cockpit_sessions.js) : en-tête droit RM2894, tuiles vivantes et
// grises, groupes, bandeau, bannière, revues, compteurs, titre — gestes en data-*, RM2673 selon setWritable, RM2795 marque.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { fakeEl, settle, now, SETS, writable, mkRepo } = require("./test_cockpit_sessions.helpers.js");
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
(async () => {
  const VM = await import(path.join(DIR, "src/modules/sessions/SessionsViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/sessions/Sessions.view.js"));
  const { esc } = await import(path.join(DIR, "src/core/html.js"));

  // — RM2894 : en-tête du panneau de droite —
  let h2894 = V.rTitleHtml("2894", { title: "titre transcript" }, { found: true, title: "Sujet Redmine" }, esc); assert(/RM2894/.test(h2894) && /Sujet Redmine/.test(h2894) && !/titre transcript/.test(h2894), "le sujet Redmine prime quand le ticket est résolu");
  h2894 = V.rTitleHtml("calicote-presta", { is_ticket: false, title: "MEP productcheck" }, null, esc); assert(!/RM/.test(h2894) && /calicote-presta/.test(h2894) && /MEP productcheck/.test(h2894), "slug : titre du transcript, pas de RM inventé");
  h2894 = V.rTitleHtml("2894", {}, { found: false }, esc); assert(/sans libellé/.test(h2894) && !/karl-/.test(h2894), "absence dite, jamais le nom tmux");
  h2894 = V.rTitleHtml("2894", { title: '<img src=x onerror="alert(1)">' }, null, esc); assert(!/<img/.test(h2894) && /&lt;img/.test(h2894), "le libellé est échappé");
  assert(html.indexOf('id="rtitle"') > 0 && html.indexOf('id="rtitle"') < html.indexOf('<nav class="rnav">'), "l'en-tête doit précéder la barre d'onglets .rnav");
  assert(/function afterTitle\(\) \{\s*\n\s*renderRTitle\(\);/.test(fs.readFileSync(path.join(DIR, "src/modules/sessions/sessions.controller.js"), "utf8")), "renderRTitle doit être rejoué à tout changement de vue (afterTitle)");
  assert(/if \(ctx\.afterTitle\) ctx\.afterTitle\(\);/.test(fs.readFileSync(path.join(DIR, "src/modules/center/center.controller.js"), "utf8")), "…et le routeur du centre les rejoue après chaque titre");
  console.log("✓ libellé de session (RM2894) : en-tête au-dessus des onglets, 3 sources, échappement, rejoué à chaque vue");


  // — ViewModels et vues —
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

  console.log("\nTous les tests des vues des sessions passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
