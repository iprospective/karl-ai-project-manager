#!/usr/bin/env node
// Tests de l'outline de conversation migré (RM2889) — porte RM2330 (sauts), RM2549 (décor, questions sans réponse, /scroll gardé),
// RM2596 (recherche, surlignage, accordéon), RM2601 (filtres de vue), RM2466 (chargement sans réentrance).
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 10));
const escO = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fakeElement(id) { const L = []; let inner = ""; const kids = []; return { id, textContent: "", value: "", dataset: {}, get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, kids,
  querySelector(sel) { return sel === ".oline.ocur" && /ocur/.test(inner) ? { scrollIntoView() { this.scrolled = true; } } : null; }, querySelectorAll() { return kids; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, target) { for (const [t, f] of [...L]) if (t === type) await f({ target, preventDefault() {}, stopPropagation() {} }); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); return n; } }; }
(async () => {
  const M = await import(path.join(DIR, "src/modules/outline/outline.js"));
  const { OutlineService } = await import(path.join(DIR, "src/modules/outline/outline.service.js"));
  const { OutlineViewModel } = await import(path.join(DIR, "src/modules/outline/OutlineViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/outline/Outline.view.js"));
  const { mountOutline } = await import(path.join(DIR, "src/modules/outline/outline.controller.js"));
  // — RM2330 : sauts —
  const oi = [{ line: 2, kind: "user", text: "premier" }, { line: 5, kind: "assistant", text: "réponse" }, { line: 9, kind: "user", text: "deuxième" }, { line: 14, kind: "user", text: "troisième" }];
  assert.strictEqual(M.outlineStep(oi, null, -1).line, 14); assert.strictEqual(M.outlineStep(oi, 14, -1).line, 9); assert.strictEqual(M.outlineStep(oi, 2, -1), null); assert.strictEqual(M.outlineStep(oi, 9, 1).line, 14); assert.strictEqual(M.outlineStep(oi, 14, 1), null); assert.strictEqual(M.outlineStep(oi, null, 1), null); assert.strictEqual(M.outlineStep([{ line: 1, kind: "assistant" }], null, -1), null);
  // — RM2549 : décor sur TROIS canaux, question suivante —
  const dUnres = M.outlineDecor({ kind: "question", resolved: false }), dRes = M.outlineDecor({ kind: "question", resolved: true, answer: "Option A" }), dAns = M.outlineDecor({ kind: "answer" });
  assert(dUnres.cls.includes("ounres") && dUnres.icon === "⚠" && /sans réponse/i.test(dUnres.tag)); assert(dRes.cls !== dUnres.cls && dRes.icon !== dUnres.icon && dRes.tag !== dUnres.tag && /Option A/.test(dRes.title)); assert(dAns.cls.includes("oans") && dAns.icon && /réponse/i.test(dAns.tag));
  assert.strictEqual(M.outlineDecor({ kind: "user" }).cls, "ouser"); assert.strictEqual(M.outlineDecor({ kind: "assistant" }).icon, "⏺"); assert.strictEqual(M.outlineDecor(null).icon, "⏺"); assert.strictEqual(M.outlineDecor({ kind: "question" }).cls, dUnres.cls, "resolved manquant = non résolu");
  const qi = [{ line: 0, kind: "user" }, { line: 1, kind: "question", resolved: true }, { line: 2, kind: "question", resolved: false }, { line: 3, kind: "assistant" }, { line: 4, kind: "question", resolved: false }];
  assert.strictEqual(M.outlineNextUnresolved(qi, null).line, 2); assert.strictEqual(M.outlineNextUnresolved(qi, 2).line, 4); assert.strictEqual(M.outlineNextUnresolved(qi, 4).line, 2, "reboucle"); assert.strictEqual(M.outlineNextUnresolved(qi.filter(i => i.resolved !== false), null), null); assert.strictEqual(M.outlineNextUnresolved([], null), null); assert.strictEqual(M.outlineNextUnresolved(null, null), null);
  // — RM2596 / RM2601 : recherche, filtres, texte complet, normalisation —
  const oitems = [{ line: 1, text: "corrige RM123", full: "le bug RM123" }, { line: 2, text: "autre", full: "rien" }];
  assert.strictEqual(M.outMatch(oitems, "rm123").length, 1); assert.strictEqual(M.outMatch(oitems, "bug")[0].line, 1); assert.strictEqual(M.outMatch(oitems, "").length, 2); assert.strictEqual(M.outMatch(oitems, "zzz").length, 0);
  const its2 = [{ kind: "user" }, { kind: "question" }, { kind: "answer" }, {}]; assert.strictEqual(M.outByKind(its2, "all").length, 4); assert.strictEqual(M.outByKind(its2, "user").length, 1); assert.strictEqual(M.outByKind(its2, "question").length, 1); assert.strictEqual(M.outByKind([], "user").length, 0);
  assert(/→ Réponse retenue : B/.test(M.outlineFull({ kind: "question", resolved: true, answer: "B", text: "q" })) && /SANS RÉPONSE/.test(M.outlineFull({ kind: "question", text: "q" })) && M.outlineFull({ kind: "user", text: "t", full: "plein" }) === "plein");
  assert.deepStrictEqual(M.normalizeItems([{ n: 7, kind: "user" }, { line: 3 }]).map(i => i.line), [7, 3], "transcript : n → line");
  assert.strictEqual(V.hlq("a <b> RM1", ""), "a &lt;b&gt; RM1"); assert(/<mark>RM1<\/mark>/.test(V.hlq("voir RM1", "rm1"))); assert(!/<b>/.test(V.hlq("<b>x</b>", "x"))); assert.strictEqual(V.hlq("aaa", "a"), "<mark>a</mark><mark>a</mark><mark>a</mark>");
  console.log("✓ modèle (RM2330/2549/2596/2601) : sauts, décor sur trois canaux, question suivante, recherche, filtres, surlignage sûr");
  // — ViewModel + vue —
  const items = [{ line: 2, kind: "user", text: "fix <b>RM42</b>", full: "fix RM42 dans a/b.py" }, { line: 5, kind: "assistant", text: "ok" }, { line: 7, kind: "question", resolved: false, text: "on merge ?" }, { line: 9, kind: "question", resolved: true, answer: "oui", text: "on livre ?" }];
  const view = (e) => String(V.OutlineList(new OutlineViewModel(Object.assign({ items, source: "tmux", query: "", filter: "all", pos: null, open: null, attached: "42" }, e)), { linkify: (s) => "<lk>" + escO(s) + "</lk>" }));
  assert(/attache une session…/.test(view({ attached: null }))); assert(/conversation vide/.test(view({ items: [] }))); assert(/aucun message ne contient « zzz »/.test(view({ query: "zzz" }))); assert(/aucun message pour ce filtre/.test(view({ items: [items[1]], filter: "user" })));
  const vm = new OutlineViewModel({ items, source: "tmux", query: "", filter: "all", attached: "42" }); assert.strictEqual(vm.count, "1 msg · ⚠ 1 sans réponse"); assert.strictEqual(new OutlineViewModel({ items, query: "on", attached: "42" }).count, "2 affichés"); assert.strictEqual(new OutlineViewModel({ items, filter: "user", attached: "42" }).count, "1 affiché");
  const hq = view({ query: "rm42" });
  assert(/class="oline ouser" title="Ton message — clic : lire \+ faire défiler le terminal" data-action="jump" data-line="2">🗣 fix &lt;b&gt;<mark>RM42<\/mark>&lt;\/b&gt;</.test(hq), "ligne user : décor, surlignage, source échappée"); assert(!/data-line="7"/.test(hq), "la recherche filtre");
  const h = view({ pos: 7, open: 2 }); assert(/class="oline oq ounres ocur"[^>]*data-line="7">⚠ <span class="otag">sans réponse<\/span>on merge \?/.test(h), "question sans réponse : icône, libellé, position courante");
  assert(/class="oline oq"[^>]*title="Question posée — réponse retenue : oui/.test(h)); assert(/<div class="oexp"><div class="oexpbar">[\s\S]*data-action="copy" data-line="2"[\s\S]*data-action="close-read"[\s\S]*<div class="oexptxt"><lk>fix RM42 dans a\/b.py<\/lk><\/div>/.test(h), "RM2596 : accordéon sous l'entrée cliquée, refs par linkify"); assert((h.match(/class="oexp"/g) || []).length === 1 && !/onclick=/.test(h));
  assert(/clic : lire ce message"/.test(view({ source: "transcript" })), "transcript : le clic ne pilote pas le terminal");
  // — service : une requête à la fois, transcript ne pilote pas tmux —
  const calls = []; let pending = null;
  const repo = { load: (sid) => { calls.push("load:" + sid); return new Promise(r => { pending = r; }); }, async scrollTo(sid, line) { calls.push(["scroll", sid, line]); }, async scrollBottom(sid) { calls.push(["bottom", sid]); } };
  const svc = new OutlineService({ repo, clipboard: { writeText: async (t) => calls.push(["clip", t]) } });
  const p1 = svc.load("42"); const p2 = svc.load("42"); assert.strictEqual(await p2, null, "RM2466 : pas de seconde requête pendant le vol"); pending({ items, total: 20, source: "tmux" }); await p1; assert.strictEqual(calls.filter(c => c === "load:42").length, 1); assert.strictEqual(svc.items.length, 4);
  assert.strictEqual(await svc.scrollTo("42", 7), true); assert.deepStrictEqual(calls[calls.length - 1], ["scroll", "42", 7]); assert.strictEqual(await svc.scrollLive("42"), true);
  svc.data.source = "transcript"; calls.length = 0; assert.strictEqual(await svc.scrollTo("42", 7), false); assert.strictEqual(await svc.scrollLive("42"), false); assert.strictEqual(calls.length, 0, "RM2549 : transcript ne touche pas à tmux"); assert.strictEqual(await svc.copy("x"), true); assert.strictEqual(await new OutlineService({ repo, clipboard: null }).copy("x"), false);
  console.log("✓ vue et service : minimap décorée, accordéon, compteur ; chargement sans réentrance, /scroll gardé par la source");
  // — le contrôleur —
  const body = fakeElement("outbody"), count = fakeElement("outcnt"), nav = fakeElement("outnav"); let att = null; const ev = [];
  const filterBtns = ["all", "user", "question"].map(f => ({ dataset: { of: f }, cls: new Set(f === "all" ? ["active"] : []), classList: { toggle(c, on) { on ? this.owner.cls.add(c) : this.owner.cls.delete(c); } } })); filterBtns.forEach(b => { b.classList.owner = b; }); nav.kids.push(...filterBtns);
  const repo2 = { async load(sid) { ev.push(["load", sid]); return { items: JSON.parse(JSON.stringify(items)), total_lines: 20, source: sid === "tr" ? "transcript" : "tmux" }; }, async scrollTo(sid, line) { ev.push(["scroll", line]); }, async scrollBottom() { ev.push(["bottom"]); } };
  const svc2 = new OutlineService({ repo: { load: async (sid) => { const r = await repo2.load(sid); return { items: M.normalizeItems(r.items), total: r.total_lines, source: r.source }; }, scrollTo: repo2.scrollTo, scrollBottom: repo2.scrollBottom }, clipboard: { writeText: async (t) => ev.push(["clip", t]) } });
  const ctr = mountOutline({ body, count, nav }, { service: svc2, attached: () => att, notify: (m, e) => ev.push(["toast", m, !!e]), linkify: (s) => escO(s) });
  assert(/attache une session…/.test(body.innerHTML)); await ctr.load(); assert(!ev.length, "sans session : rien n'est demandé");
  att = "42"; ctr.reset(); assert(/chargement au dépliage…/.test(body.innerHTML) && count.textContent === ""); await ctr.load(); assert.deepStrictEqual(ev, [["load", "42"]]); assert(/data-line="7"/.test(body.innerHTML) && count.textContent === "1 msg · ⚠ 1 sans réponse");
  await ctr.load(); assert.strictEqual(ev.filter(x => x[0] === "load").length, 1, "déjà chargé : pas de nouvelle requête"); await nav.click("reload"); assert.strictEqual(ev.filter(x => x[0] === "load").length, 2, "⟳ recharge");
  await body.click("jump", { line: "7" }); assert.strictEqual(ctr.state.pos, 7); assert.strictEqual(ctr.state.open, 7); assert(/oline oq ounres ocur/.test(body.innerHTML) && /class="oexp"/.test(body.innerHTML) && ev.some(x => x[0] === "scroll" && x[1] === 7), "clic : position, lecture dépliée, terminal déplacé");
  await body.click("jump", { line: "7" }); assert.strictEqual(ctr.state.open, null, "re-clic : l'accordéon se replie"); await body.click("jump", { line: "2" }); await body.click("copy", { line: "2" }); await settle(); assert(ev.some(x => x[0] === "clip" && /fix RM42 dans a\/b.py/.test(x[1])) && ev.some(x => x[0] === "toast" && x[1] === "Message copié"));
  await body.click("close-read"); assert.strictEqual(ctr.state.open, null); await nav.click("prev"); assert.strictEqual(ctr.state.pos, 2, "▲ moi : le dernier message user avant la position"); ev.length = 0; await nav.click("prev"); assert(ev.some(x => x[0] === "toast" && /plus haut/.test(x[1])), "au premier : dit, pas silencieux");
  await nav.click("next"); assert(ev.some(x => x[0] === "bottom") && ctr.state.pos === null && ev.some(x => x[0] === "toast" && /retour au direct/.test(x[1])), "▼ moi sans suivant : retour au direct");
  await nav.click("unresolved"); assert.strictEqual(ctr.state.pos, 7, "⚠ question : la prochaine sans réponse"); await nav.click("unresolved"); assert.strictEqual(ctr.state.pos, 7, "…et reboucle sur la seule");
  await nav.fire("input", { id: "outq", value: "merge" }); assert.strictEqual(ctr.state.query, "merge"); assert(/2 affichés|1 affiché/.test(count.textContent) && /<mark>merge<\/mark>/.test(body.innerHTML)); await nav.fire("input", { id: "outq", value: "" });
  await nav.click(undefined, { of: "user" }); assert.strictEqual(ctr.state.filter, "user"); assert(filterBtns[1].cls.has("active") && !filterBtns[0].cls.has("active"), "RM2601 : le bouton actif suit le filtre"); assert(!/data-line="7"/.test(body.innerHTML) && /data-line="2"/.test(body.innerHTML)); ctr.setFilter("zzz"); assert.strictEqual(ctr.state.filter, "all");
  att = "tr"; ctr.reset(); await ctr.load(); ev.length = 0; await body.click("jump", { line: "7" }); assert(!ev.some(x => x[0] === "scroll"), "RM2549 : transcript — le clic ne pilote pas tmux"); await ctr.scrollLive(); assert(!ev.some(x => x[0] === "bottom") && ctr.state.open === null && ctr.state.pos === null, "…ni le retour au direct : il referme juste la lecture");
  att = null; ctr.reset(); assert(/attache une session…/.test(body.innerHTML));
  ctr.unmount(); assert.strictEqual(body.listenerCount + nav.listenerCount, 0); assert.strictEqual(body.innerHTML, "");
  console.log("✓ contrôleur : chargé une fois, ⟳, saut + accordéon + terminal, ▲▼ moi, ⚠ question, recherche, filtres, transcript sans tmux, remise à zéro");
  console.log("\nTous les tests de l'outline passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
