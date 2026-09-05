#!/usr/bin/env node
// Tests de la recherche de tickets migrée (RM2889) — porte RM2770 (multi-source, filtres, absents signalés, panne Redmine à côté),
// RM2639 (contexte client), RM2830 (étiquettes), RM2832 (clic étiquette), RM2795 (marque d'épinglage).
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 10));
function fakeElement(id) { const L = []; let inner = ""; const kids = {}; const self = { id, kids, dataset: {}, value: "", style: {}, textContent: "", get innerHTML() { return inner; }, set innerHTML(v) { inner = v; self.options = [...v.matchAll(/<option value="([^"]*)"/g)].map(m => ({ value: m[1] })); }, options: [{ value: "" }], contains(n) { return this.id === "results" ? !!(n && n.dataset && n.dataset.rm) : true; }, focus() { this.focused = true; },
  insertAdjacentHTML(pos, h) { inner += h; self.options = [...inner.matchAll(/<option value="([^"]*)"/g)].map(m => ({ value: m[1] })); },
  querySelector(sel) { return kids[sel] || null; }, addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, target, extra) { for (const [t, f] of [...L]) if (t === type) await f(Object.assign({ target, preventDefault() {}, stopPropagation() {} }, extra || {})); },
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); return n; } }; return self; }
(async () => {
  const M = await import(path.join(DIR, "src/models/tickets/search.js"));
  const { SearchService } = await import(path.join(DIR, "src/services/search.service.js"));
  const VM = await import(path.join(DIR, "src/viewmodels/tickets/SearchViewModel.js"));
  const V = await import(path.join(DIR, "src/views/tickets/Search.view.js"));
  const { mountSearch } = await import(path.join(DIR, "src/controllers/search.controller.js"));
  // — RM2770 / RM2639 / RM2830 : la requête —
  assert.strictEqual(M.searchQuery("abc", { source: "local" }, ""), "/tickets/search?q=abc", "source locale = requête historique"); assert(M.searchQuery("x", { source: "redmine" }, "").includes("source=redmine") && M.searchQuery("x", { source: "both" }, "").includes("source=both"));
  assert(M.searchQuery("x", { client: "abatik" }, "calicote").includes("client=abatik"), "le filtre explicite prime sur le contexte"); assert(M.searchQuery("x", {}, "calicote").includes("client=calicote")); assert(!M.searchQuery("x", {}, "").includes("client="));
  const qFull = M.searchQuery("mep", { source: "both", client: "c", project: "p", status: "a_faire" }, ""); ["q=mep", "client=c", "project=p", "status=a_faire", "source=both"].forEach(f => assert(qFull.includes(f), f)); assert(M.searchQuery("a b&c", {}, "").includes("q=a%20b%26c")); assert.strictEqual(M.searchQuery(null, null, null), "/tickets/search?q=");
  assert(/tag=refacto/.test(M.searchQuery("x", { tag: "refacto" }, ""))); assert(!/tag=/.test(M.searchQuery("x", {}, "")));
  // — la ligne de contexte —
  assert.strictEqual(M.searchRowMeta({ client: "c", project: "p", status: "a_faire" }), "c / p · a_faire"); const m = M.searchRowMeta({ rm_id: "9", origin: "redmine", synced: false, status: "Nouveau", redmine_project: "Projet X", assigned_to: "Karl" }); assert(m.includes("⚠ pas en local") && m.includes("Projet X") && m.includes("→ Karl"));
  assert(M.searchRowMeta({ client: "c", project: "p", origin: "both", synced: true }).includes("🌐 Redmine") && !M.searchRowMeta({ client: "c", project: "p", origin: "both", synced: true }).includes("pas en local")); assert.strictEqual(M.searchRowMeta(null), "— · ?"); assert(/🏷 refacto/.test(M.searchRowMeta({ client: "a", project: "p", status: "a_faire", tags: ["refacto"] }))); assert(!/·\s*·/.test(M.searchRowMeta({ client: "a", project: "p", status: "a_faire" })));
  assert(M.isAbsent({ origin: "redmine", synced: false }) && !M.isAbsent({ origin: "redmine", synced: true }) && !M.isAbsent({ origin: "local" }));
  const PR = [{ client: "beta", project: "api" }, { client: "acme", project: "shop" }, { client: "acme", project: "bo" }, {}];
  assert.deepStrictEqual(M.sfClients(PR), ["acme", "beta"]); assert.deepStrictEqual(M.sfProjects(PR, "acme", "bo"), { options: ["shop", "bo"], value: "bo" }); assert.deepStrictEqual(M.sfProjects(PR, "acme", "api").value, "", "un projet d'un autre client ne survit pas"); assert.strictEqual(M.sfProjects(PR, "", "").options.length, 3);
  assert.deepStrictEqual(M.tagOptions([{ tag: "front", count: 3 }]), [{ value: "front", label: "front (3)" }]);
  console.log("✓ modèle (RM2770/2639/2830) : requête (filtre > contexte, sources, encodage), ligne de contexte, absents, filtres");
  // — vue —
  const R = [{ rm_id: 42, title: "Fix <b>x</b>", client: "c", project: "p", status: "a_faire", tags: ["front"] }, { rm_id: 9, title: "Absent", origin: "redmine", synced: false, status: "Nouveau", redmine_project: "PX" }];
  const view = (e) => String(V.SearchResults(new VM.SearchResultsViewModel(Object.assign({ results: R, error: "", base: "https://r" }, e)), { titleLink: (rm, t) => "<tl>" + String(t).replace(/</g, "&lt;") + "</tl>", pin: (k, key) => "<pin>" + key + "</pin>" }));
  const h = view({});
  assert(/<li title="Clic : préparer une session sur RM42" data-action="pick" data-rm="42"><div class="r-top"><span class="r-id">RM42<\/span><pin>42<\/pin><span class="r-title"><tl>Fix &lt;b>x&lt;\/b><\/tl><\/span><\/div><div class="r-meta">c \/ p · a_faire · 🏷 front<\/div><\/li>/.test(h), "résultat local : marque RM2795, titre par titleLink, méta");
  assert(/<li title="Pas encore de fichier local — clic : ouvrir RM9 dans Redmine" data-action="redmine" data-rm="9" data-url="https:\/\/r\/issues\/9">/.test(h) && /PX · Nouveau · ⚠ pas en local/.test(h), "RM2770 : l'absent ouvre Redmine, pas le lanceur"); assert(!/onclick=/.test(h));
  assert(/URL Redmine non configurée/.test(view({ base: "" })) && !/data-url=/.test(view({ base: "" }))); assert(/<div class="empty">aucun résultat<\/div>/.test(view({ results: [] })));
  assert.strictEqual(new VM.SearchResultsViewModel({ error: "API Redmine 502" }).error, "⚠ API Redmine 502"); assert.strictEqual(String(V.Options(["a", "b"], "b", "tous")), '<option value="">tous</option><option value="a">a</option><option value="b" selected>b</option>');
  // — service + contrôleur —
  const calls = []; let tagsResp = [{ tag: "front", count: 3 }, { tag: "bdd", count: 1 }];
  const repo = { async search(q, f, c) { calls.push(["search", q, Object.assign({}, f), c]); return { results: q === "zz" ? [] : R, redmine_error: f.source === "both" ? "API Redmine 502" : "" }; }, async tags() { calls.push(["tags"]); return tagsResp; } };
  const svc = new SearchService({ repo });
  const card = fakeElement("searchcard"), inp = fakeElement("search"), src = Object.assign(fakeElement("sf-source"), { value: "local" }), cs = fakeElement("sf-client"), ps = fakeElement("sf-project"), st = fakeElement("sf-status"), tg = fakeElement("sf-tag"), warn = fakeElement("sf-warn"), res = fakeElement("results");
  Object.assign(card.kids, { "#search": inp, "#sf-source": src, "#sf-client": cs, "#sf-project": ps, "#sf-status": st, "#sf-tag": tg, "#sf-warn": warn, "#results": res });
  const ev = []; let ctxClient = ""; let projects = PR;
  const ctr = mountSearch(card, { service: svc, notify: (m, e) => ev.push(["toast", m, !!e]), projects: () => projects, clientContext: () => ctxClient, statuses: () => ["a_faire", "en_cours"], redmineBase: () => "https://r", titleLink: (rm, t) => String(t), pinOf: () => "", pick: (rm) => ev.push(["pick", rm]), openExternal: (u) => ev.push(["open", u]), onTags: (t) => ev.push(["tags", t.map(x => x.tag).join(",")]) });
  ctr.init(); assert(/<option value="acme">acme<\/option><option value="beta">beta<\/option>/.test(cs.innerHTML) && /<option value="a_faire">/.test(st.innerHTML) && /shop/.test(ps.innerHTML) && /api/.test(ps.innerHTML), "init : clients, statuts NORMS, projets");
  st.value = "en_cours"; ctr.init(); assert(/<option value="a_faire">/.test(st.innerHTML), "les statuts ne sont posés qu'une fois (options déjà là)");
  ctxClient = "acme"; ctr.fillProjects(); assert(!/api/.test(ps.innerHTML) && /shop/.test(ps.innerHTML), "RM2639 : sans filtre client, le contexte décide des projets"); cs.value = "beta"; await card.fire("change", cs); assert(/api/.test(ps.innerHTML) && !/shop/.test(ps.innerHTML), "le filtre client prime"); assert(calls.some(c => c[0] === "search" && c[2].client === "beta" && c[3] === "acme"), "…et la recherche part avec le filtre ET le contexte (le modèle arbitre)");
  inp.value = "fix"; calls.length = 0; await card.fire("keydown", inp, { key: "a" }); assert.strictEqual(calls.length, 0); await card.fire("keydown", inp, { key: "Enter" }); assert.strictEqual(calls.length, 1, "Entrée lance la recherche"); assert(/data-rm="42"/.test(res.innerHTML) && warn.style.display === "none");
  src.value = "both"; await card.fire("change", src); assert(warn.style.display === "" && warn.textContent === "⚠ API Redmine 502" && /data-rm="42"/.test(res.innerHTML), "RM2770 : la panne Redmine s'affiche À CÔTÉ des résultats"); src.value = "local"; await card.fire("change", src); assert.strictEqual(warn.style.display, "none");
  await res.click("pick", { rm: "42" }); assert(ev.some(x => x[0] === "pick" && x[1] === "42"), "un résultat local prépare le lanceur"); await res.click("redmine", { rm: "9", url: "https://r/issues/9" }); assert(ev.some(x => x[0] === "open" && x[1] === "https://r/issues/9")); await res.click("redmine", { rm: "9" }); assert(ev.some(x => x[0] === "toast" && /non configurée/.test(x[1])));
  inp.value = "zz"; await ctr.search(); assert(/aucun résultat/.test(res.innerHTML)); calls.length = 0; inp.value = ""; ctr.refreshIfQuery(); assert.strictEqual(calls.length, 0, "sans requête : rien"); inp.value = "x"; ctr.refreshIfQuery(); await settle(); assert.strictEqual(calls.length, 1);
  await card.click("clear"); assert(inp.value === "" && inp.focused && res.innerHTML === "");
  ev.length = 0; tg.value = "front"; await ctr.loadTags(); assert(/<option value="front" selected>front \(3\)<\/option>/.test(tg.innerHTML) && /bdd \(1\)/.test(tg.innerHTML), "RM2830 : étiquettes en usage, filtre courant conservé"); assert(ev.some(x => x[0] === "tags" && x[1] === "front,bdd"), "…et le triage est prévenu"); assert.strictEqual(ctr.tags().length, 2);
  calls.length = 0; inp.value = "abc"; await ctr.setTag("refacto"); assert(tg.value === "refacto" && /<option value="refacto">refacto<\/option>/.test(tg.innerHTML) && inp.value === "" && calls.some(c => c[0] === "search" && c[2].tag === "refacto"), "RM2832 : une étiquette inconnue du menu y est ajoutée, la requête vidée, la recherche lancée");
  tagsResp = null; const svcKo = new SearchService({ repo: { async tags() { throw new Error("x"); } } }); assert.deepStrictEqual(await svcKo.loadTags(), [], "panne /tags : liste vide, pas d'exception");
  ctr.unmount(); assert.strictEqual(card.listenerCount + res.listenerCount, 0);
  console.log("✓ vue, service et contrôleur : résultats sûrs, Entrée, filtres (client > contexte), panne à côté, clics, étiquettes partagées");
  console.log("\nTous les tests de la recherche passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
